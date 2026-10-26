import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deploy', Path(__file__).resolve().parents[1] / 'scripts' / 'deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeploymentTests(unittest.TestCase):
    def test_instances_use_separate_compose_names_and_loopback_ports(self):
        manifest = {'image_id': 'sha256:example', 'release_id': 'test', 'platform': 'linux/amd64'}
        first = deploy.compose_document('operator', 3080, manifest)
        second = deploy.compose_document('manager', 3081, manifest)
        self.assertNotEqual(first['name'], second['name'])
        self.assertEqual(first['services']['agent']['ports'], ['127.0.0.1:3080:3080'])
        self.assertEqual(second['services']['agent']['ports'], ['127.0.0.1:3081:3080'])
        self.assertEqual(first['services']['agent']['image'], 'sha256:example')
        self.assertEqual(first['services']['agent']['pull_policy'], 'never')

    def test_replaced_image_is_rejected(self):
        manifest = {'image_id': 'sha256:expected'}
        with patch.object(deploy, 'image_info', return_value={'Id': 'sha256:changed'}):
            with self.assertRaisesRegex(RuntimeError, 'missing'):
                deploy.verify_image(manifest)

    def test_mismatched_release_label_is_rejected(self):
        manifest = {'image_id': 'sha256:id', 'release_id': 'expected', 'source_sha256': 'hash'}
        image = {'Id': 'sha256:id', 'Config': {'Labels': {'org.opencontainers.image.version': 'other'}}}
        with patch.object(deploy, 'image_info', return_value=image):
            with self.assertRaisesRegex(RuntimeError, 'labels'):
                deploy.verify_image(manifest)

    def test_release_path_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Invalid release'):
            deploy.load_release('../outside')

    def test_modified_export_is_rejected_before_docker_load(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / 'image.tar').write_bytes(b'changed')
            (directory / 'bundle.json').write_text(json.dumps({
                'schema': 1, 'release_id': 'test', 'files': {'image.tar': 'expected'},
            }), encoding='utf-8')
            with patch.object(deploy, 'run') as command:
                with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                    deploy.import_bundle(temp)
                command.assert_not_called()

    def test_source_snapshot_detects_content_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'VERSION').write_text('0.1.0\n', encoding='utf-8')
            with patch.object(deploy, 'ROOT', root), patch.object(deploy, 'source_files', return_value=['VERSION']):
                old = deploy.source_snapshot()[2]
                (root / 'VERSION').write_text('0.1.1\n', encoding='utf-8')
                self.assertNotEqual(old, deploy.source_snapshot()[2])


if __name__ == '__main__':
    unittest.main()
