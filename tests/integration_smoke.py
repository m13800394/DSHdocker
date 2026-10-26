"""Exercise the actual deployed image without a model or remote desktop."""
import importlib.util
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
import http.cookiejar
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deploy', ROOT / 'scripts/deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def check_page(agent):
    access = json.loads(deploy.compose(agent, 'exec', '-T', 'agent', 'cat',
                                       '/tmp/harness-access.json', capture=True).stdout)
    root = access['url'].split('?')[0]
    try:
        urllib.request.urlopen(root, timeout=10)
        raise AssertionError('Anonymous homepage unexpectedly accessible')
    except urllib.error.HTTPError as error:
        assert error.code == 401, error.code
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    response = opener.open(access['url'], timeout=15)
    html = response.read().decode('utf-8')
    assert response.status == 200 and '<html' in html.lower()
    assert 'token=' not in response.url
    assets = re.findall(r'<script[^>]+src="([^"]+)"', html)
    for asset in assets:
        if asset.startswith('/'):
            result = opener.open(root.rstrip('/') + asset, timeout=15)
            assert result.status == 200
    return {'authenticated_http_status': 200, 'anonymous_http_status': 401,
            'script_assets_checked': len(assets)}


def main():
    deploy.preflight()
    current = deploy.read_json(ROOT / 'instances/mri-operator/deployment.json')
    release = deploy.load_release(current['release_id'])
    results = {'time_utc': datetime.now(timezone.utc).isoformat(),
               'release_id': current['release_id'], 'checks': {}}
    checks = results['checks']
    checks['main_web'] = check_page('mri-operator')
    cli = deploy.compose('mri-operator', 'exec', '-T', 'agent', 'dsh', '--version', capture=True).stdout.strip()
    assert cli == release['upstream']['package_version'], cli
    checks['harness_version'] = cli
    output = deploy.compose('mri-operator', 'exec', '-T', 'agent', 'node', '-e',
        "const p = require('/opt/harness/node_modules/node-pty').spawn('/bin/sh', ['-c', 'printf harness-pty-ok'], {name:'xterm', cols:80, rows:24}); let out=''; p.onData(s=>out+=s); p.onExit(e=>{if(e.exitCode!==0 || !out.includes('harness-pty-ok')) process.exit(1); console.log('PTY OK')});",
        capture=True).stdout
    assert 'PTY OK' in output
    checks['native_terminal'] = 'passed'
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    agent = 'qa-' + uuid.uuid4().hex[:8]
    marker = 'smoke-' + uuid.uuid4().hex
    args = deploy.parser().parse_args(['up', '--agent', agent, '--port', str(port), '--release', current['release_id']])
    try:
        deploy.up(args)
        checks['second_web'] = check_page(agent)
        script = f"const fs=require('fs'); for(const dir of ['/workspace','/state']) fs.writeFileSync(dir+'/{marker}','persisted');"
        deploy.compose(agent, 'exec', '-T', 'agent', 'node', '-e', script, capture=True)
        absent = f"const fs=require('fs'); if(['/workspace','/state'].some(d=>fs.existsSync(d+'/{marker}'))) process.exit(1);"
        deploy.compose('mri-operator', 'exec', '-T', 'agent', 'node', '-e', absent, capture=True)
        checks['state_and_workspace_isolation'] = 'passed'
        deploy.compose(agent, 'down')
        deploy.up(args)
        verify = f"const fs=require('fs'); for(const d of ['/workspace','/state']) if(fs.readFileSync(d+'/{marker}','utf8')!=='persisted') process.exit(1);"
        deploy.compose(agent, 'exec', '-T', 'agent', 'node', '-e', verify, capture=True)
        checks['state_and_workspace_survive_recreation'] = 'passed'
        checks['recreated_web'] = check_page(agent)
        cid = deploy.compose(agent, 'ps', '-q', 'agent', capture=True).stdout.strip()
        info = json.loads(deploy.run('docker', 'inspect', cid, capture=True).stdout)[0]
        assert info['Image'] == current['image_id']
        assert info['Config']['User'] == 'node'
        assert info['HostConfig']['ReadonlyRootfs'] is True
        assert info['NetworkSettings']['Ports']['3080/tcp'][0]['HostIp'] == '127.0.0.1'
        checks['exact_image_nonroot_readonly_loopback'] = 'passed'
        results['status'] = 'passed'
    finally:
        # Only this test's uniquely named project and volumes are removed.
        deploy.compose(agent, 'down', '--volumes')
        deploy.write_json(ROOT / 'docs/test-results/container-smoke.json', results)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
