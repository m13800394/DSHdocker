"""Build and deploy versioned, independent DeepSeek Harness containers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import uuid
import zipfile
import webbrowser

ROOT = Path(__file__).resolve().parent.parent
RELEASES = ROOT / 'releases'
INSTANCES = ROOT / 'instances'
NAME = re.compile(r'[a-z][a-z0-9-]{0,39}\Z')
RELEASE = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z')


def run(*args: str, capture: bool = False, check: bool = True, cwd: Path = ROOT):
    result = subprocess.run(args, cwd=cwd, text=True, encoding='utf-8', errors='replace',
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if check and result.returncode:
        raise RuntimeError(f'{args[0]} {args[1]} failed ({result.returncode}). '
                           + ((result.stderr or '').strip() if capture else 'See output above.'))
    return result


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{uuid.uuid4().hex}.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def sha256(path: Path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else stream_hash(stream)


def stream_hash(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
    return digest.hexdigest()


def audit(event: str, **details):
    path = ROOT / 'logs' / 'deployment.jsonl'
    path.parent.mkdir(exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'time_utc': datetime.now(timezone.utc).isoformat(),
                                 'event': event, **details}, ensure_ascii=False) + '\n')


def preflight():
    if not shutil.which('docker'):
        raise RuntimeError('Docker is missing. Install/start Docker Desktop on Windows or Docker Engine with Compose on Linux.')
    info = json.loads(run('docker', 'info', '--format', '{{json .}}', capture=True).stdout)
    if info['OSType'] != 'linux':
        raise RuntimeError('Switch Docker Desktop to Linux containers.')
    run('docker', 'compose', 'version', capture=True)
    return info


def source_files():
    paths = ['Dockerfile', '.dockerignore', 'VERSION', 'upstream.json', 'deploy.ps1', 'deploy.sh',
             'runtime/package.json', 'runtime/package-lock.json']
    paths += [p.relative_to(ROOT).as_posix() for folder in ('container', 'scripts')
              for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return sorted(paths)


def source_snapshot():
    contents = {name: (ROOT / name).read_bytes() for name in source_files()}
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return contents, hashes, digest


def image_info(image: str):
    result = run('docker', 'image', 'inspect', image, capture=True, check=False)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def build():
    contents, hashes, digest = source_snapshot()
    version = contents['VERSION'].decode().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise RuntimeError('VERSION must contain a semantic version such as 0.1.0.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ').lower()
    release_id = f'{version}-{stamp}-{uuid.uuid4().hex[:12]}'
    directory = RELEASES / release_id
    directory.mkdir(parents=True, exist_ok=False)
    tag = f'mri-deepseek-harness:{release_id}'
    if image_info(tag):
        raise RuntimeError(f'Release tag already exists: {tag}')
    audit('build-started', release=release_id, source_sha256=digest)
    with zipfile.ZipFile(directory / 'source.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    with tempfile.TemporaryDirectory(prefix='harness-build-') as temp:
        context = Path(temp)
        for name, data in contents.items():
            path = context / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        run('docker', 'build', '--platform', 'linux/amd64', '--tag', tag,
            '--build-arg', f'RELEASE_ID={release_id}',
            '--build-arg', f'SOURCE_SHA256={digest}', str(context))
    image = image_info(tag)
    git = run('git', 'rev-parse', 'HEAD', capture=True, check=False) if shutil.which('git') else None
    manifest = {
        'schema': 1, 'release_id': release_id, 'version': version,
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'image_tag': tag, 'image_id': image['Id'], 'platform': 'linux/amd64',
        'repo_digests': image.get('RepoDigests', []),
        'source_sha256': digest, 'source_files': hashes,
        'source_archive_sha256': sha256(directory / 'source.zip'),
        'packaging_git_commit': git.stdout.strip() if git and git.returncode == 0 else None,
        'upstream': json.loads(contents['upstream.json']),
    }
    write_json(directory / 'manifest.json', manifest)
    write_json(RELEASES / 'latest.json', {'release_id': release_id})
    audit('build-completed', release=release_id, image_id=image['Id'])
    print(f'Created release {release_id}\nImage {image["Id"]}', flush=True)
    return manifest


def load_release(release_id: str | None):
    if not release_id:
        pointer = RELEASES / 'latest.json'
        if not pointer.exists():
            return build()
        release_id = read_json(pointer)['release_id']
    if not RELEASE.fullmatch(release_id):
        raise ValueError('Invalid release ID.')
    path = RELEASES / release_id / 'manifest.json'
    if not path.exists():
        raise RuntimeError(f'Release manifest not found: {path}')
    manifest = read_json(path)
    if manifest['release_id'] != release_id or manifest['schema'] != 1:
        raise RuntimeError('Release manifest identity/schema mismatch.')
    return manifest


def verify_image(manifest):
    image = image_info(manifest['image_id'])
    if not image or image['Id'] != manifest['image_id']:
        raise RuntimeError('Exact release image is missing. Import its export bundle or build a new release.')
    labels = image['Config'].get('Labels') or {}
    if labels.get('org.opencontainers.image.version') != manifest['release_id'] or labels.get('io.mri-harness.source-sha256') != manifest['source_sha256']:
        raise RuntimeError('Image labels do not match the release manifest.')
    if f"{image['Os']}/{image['Architecture']}" != manifest['platform']:
        raise RuntimeError('Image platform does not match its manifest.')


def compose_document(agent: str, port: int, manifest):
    return {
        'name': f'dsh-{agent}',
        'services': {'agent': {
            'image': manifest['image_id'], 'pull_policy': 'never', 'platform': manifest['platform'],
            'init': True, 'restart': 'unless-stopped', 'stop_grace_period': '30s',
            'ports': [f'127.0.0.1:{port}:3080'],
            'environment': {'HARNESS_PUBLIC_URL': f'http://127.0.0.1:{port}'},
            'volumes': ['state:/state', 'workspace:/workspace'],
            'read_only': True, 'tmpfs': ['/tmp:rw,exec,nosuid,nodev,size=256m'],
            'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
            'extra_hosts': ['host.docker.internal:host-gateway'],
            'logging': {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}},
            'labels': {'io.mri-harness.agent': agent, 'io.mri-harness.release': manifest['release_id']},
        }},
        'volumes': {'state': {}, 'workspace': {}},
    }


def compose(agent: str, *args: str, capture=False):
    path = INSTANCES / agent / 'compose.json'
    if not path.exists():
        raise RuntimeError(f'Instance {agent} does not exist. Run up first.')
    return run('docker', 'compose', '-f', str(path), *args, capture=capture)


def open_browser(agent):
    result = compose(agent, 'exec', '-T', 'agent', 'cat', '/tmp/harness-access.json', capture=True)
    url = json.loads(result.stdout)['url']
    if not re.fullmatch(r'http://127\.0\.0\.1:\d+/\?token=[A-Za-z0-9_-]+', url):
        raise RuntimeError('Unexpected local login URL.')
    if not webbrowser.open(url):
        raise RuntimeError('No desktop browser is available. Use an SSH tunnel and obtain the login URL with the url action.')
    print('Opened the authenticated local Web UI. Login tokens are not written to deployment logs.')


def up(args, manifest=None):
    directory = INSTANCES / args.agent
    active = directory / 'deployment.json'
    previous = read_json(active) if active.exists() else None
    selected = args.release or (previous['release_id'] if previous else None)
    manifest = manifest or load_release(selected)
    verify_image(manifest)
    port = args.port or (previous['port'] if previous else 3080)
    document = compose_document(args.agent, port, manifest)
    directory.mkdir(parents=True, exist_ok=True)
    if previous and previous['release_id'] != manifest['release_id']:
        # Image rollback is separate from application data migration.
        # Preserve the prior deployment descriptor for explicit recovery.
        history = directory / 'history'
        history.mkdir(exist_ok=True)
        write_json(history / f'{uuid.uuid4().hex}.json', previous)
    write_json(directory / 'compose.json', document)
    audit('deploy-started', agent=args.agent, release=manifest['release_id'], port=port)
    compose(args.agent, 'config', '--quiet')
    compose(args.agent, 'up', '-d', '--wait', '--wait-timeout', '180', '--pull', 'never')
    deployment = {'agent': args.agent, 'release_id': manifest['release_id'],
                  'image_id': manifest['image_id'], 'port': port}
    write_json(active, deployment)
    audit('deploy-completed', **deployment)
    print(f'Agent {args.agent} is ready: http://127.0.0.1:{port}\nRelease: {manifest["release_id"]}', flush=True)


def export_bundle(args):
    manifest = load_release(args.release)
    verify_image(manifest)
    target = Path(args.output).resolve() if args.output else ROOT / 'exports' / manifest['release_id']
    target.mkdir(parents=True, exist_ok=False)
    run('docker', 'image', 'save', '--output', str(target / 'image.tar'), manifest['image_id'])
    shutil.copy2(RELEASES / manifest['release_id'] / 'manifest.json', target / 'manifest.json')
    shutil.copy2(RELEASES / manifest['release_id'] / 'source.zip', target / 'source.zip')
    for name in ('deploy.ps1', 'deploy.sh', 'scripts/deploy.py'):
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
    write_json(target / 'bundle.json', {
        'schema': 1, 'release_id': manifest['release_id'],
        'files': {name: sha256(target / name) for name in
                  ('image.tar', 'manifest.json', 'source.zip', 'deploy.ps1', 'deploy.sh', 'scripts/deploy.py')},
    })
    audit('export-completed', release=manifest['release_id'], directory=str(target))
    print(f'Exported to {target}\nLinux: sh deploy.sh up --bundle .', flush=True)


def import_bundle(bundle_path: str):
    directory = Path(bundle_path).resolve()
    bundle = read_json(directory / 'bundle.json')
    if bundle['schema'] != 1 or not RELEASE.fullmatch(bundle['release_id']):
        raise RuntimeError('Unsupported bundle format.')
    for name in ('image.tar', 'manifest.json', 'source.zip', 'deploy.ps1', 'deploy.sh', 'scripts/deploy.py'):
        if sha256(directory / name) != bundle['files'].get(name):
            raise RuntimeError(f'Bundle checksum mismatch: {name}')
    manifest = read_json(directory / 'manifest.json')
    if manifest['release_id'] != bundle['release_id']:
        raise RuntimeError('Bundle release identity mismatch.')
    if sha256(directory / 'source.zip') != manifest['source_archive_sha256']:
        raise RuntimeError('Source archive checksum mismatch.')
    target = RELEASES / manifest['release_id']
    if (target / 'manifest.json').exists() and read_json(target / 'manifest.json') != manifest:
        raise RuntimeError('Refusing to overwrite an existing release with different contents.')
    run('docker', 'image', 'load', '--input', str(directory / 'image.tar'))
    verify_image(manifest)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(directory / 'manifest.json', target / 'manifest.json')
    shutil.copy2(directory / 'source.zip', target / 'source.zip')
    write_json(RELEASES / 'latest.json', {'release_id': manifest['release_id']})
    audit('import-completed', release=manifest['release_id'])
    return manifest


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', nargs='?', default='up', choices=['build', 'up', 'stop', 'status', 'logs', 'open', 'url', 'export', 'import', 'versions'])
    p.add_argument('--agent', default='mri-operator', help='Independent instance name')
    p.add_argument('--port', type=int)
    p.add_argument('--release', help='Exact immutable release ID')
    p.add_argument('--bundle', help='Verified exported bundle directory to import')
    p.add_argument('--output', help='New export directory')
    return p


def main():
    if sys.version_info < (3, 10):
        raise RuntimeError('Python 3.10 or newer is required.')
    args = parser().parse_args()
    if not NAME.fullmatch(args.agent):
        raise ValueError('Agent name: lowercase letter followed by up to 39 lowercase letters, numbers or hyphens.')
    if args.port is not None and not 1024 <= args.port <= 65535:
        raise ValueError('Port must be between 1024 and 65535.')
    if args.bundle and args.action not in ('up', 'import'):
        raise ValueError('--bundle is supported only with up or import.')
    if args.bundle and args.release:
        raise ValueError('Use --bundle or --release, not both.')
    if args.action == 'versions':
        for path in sorted(RELEASES.glob('*/manifest.json')):
            m = read_json(path)
            print(m['release_id'], m['image_id'])
        return
    preflight()
    if args.action == 'build':
        build()
    elif args.action == 'up':
        manifest = import_bundle(args.bundle) if args.bundle else None
        up(args, manifest)
    elif args.action == 'stop':
        compose(args.agent, 'down')
        audit('stopped', agent=args.agent)
    elif args.action == 'status':
        compose(args.agent, 'ps', '--all')
    elif args.action == 'logs':
        compose(args.agent, 'logs', '--tail', '100')
    elif args.action == 'open':
        open_browser(args.agent)
    elif args.action == 'url':
        result = compose(args.agent, 'exec', '-T', 'agent', 'cat', '/tmp/harness-access.json', capture=True)
        print(json.loads(result.stdout)['url'])
    elif args.action == 'export':
        export_bundle(args)
    elif args.action == 'import':
        if not args.bundle:
            raise ValueError('import requires --bundle DIRECTORY.')
        manifest = import_bundle(args.bundle)
        print(f'Imported {manifest["release_id"]}')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, KeyError) as error:
        audit('failed', message=str(error))
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
