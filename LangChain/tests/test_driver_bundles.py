"""General host-managed local driver bundle guarantees."""
import copy
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from hardware_claw.adapters.compiler import compile_project, fingerprint
from hardware_claw.catalog import KnowledgeCatalog
from hardware_claw.catalog.cards import read_documents
from hardware_claw.catalog.driver_bundles import bundle_bytes, load_bundle, project_driver_bundles
from hardware_claw.projects.service import ProjectService, ROOT
from hardware_claw.validation.files import check
from tests.test_projects import DESIGN


class DriverBundleTests(unittest.TestCase):
    def test_dht_profile_exposes_one_local_driver_bundle(self):
        catalog = KnowledgeCatalog()
        info = catalog.get('dht22_red_module')
        documents = [doc['ref'] for group in info['profile']['documents'].values() for doc in group]
        self.assertFalse([ref for ref in documents if ref.startswith('upstream/drivers/DHTesp/')])
        dependencies = info['profile']['driver_profile']['dependencies']
        self.assertEqual(len(dependencies), 1)
        self.assertEqual(dependencies[0]['resolution'], 'local_bundle')
        self.assertEqual(dependencies[0]['bundle_manifest_ref'], 'drivers/DHTesp/bundle.json')
        refs = ['drivers/DHTesp/bundle.json', 'drivers/DHTesp/DHTesp.h',
                'drivers/DHTesp/library.properties', 'drivers/DHTesp/README.md']
        result = read_documents(catalog, 'dht22_red_module', refs, 60_000)
        self.assertTrue(result['complete'], result)
        self.assertEqual([item['ref'] for item in result['documents']], refs)

    def test_bundle_loader_and_output_files_are_host_owned(self):
        catalog = KnowledgeCatalog()
        bundle = load_bundle(catalog, 'drivers/DHTesp/bundle.json')
        self.assertEqual(bundle['library_name'], 'DHT sensor library for ESPx')
        self.assertEqual(bundle['version'], '1.19')
        self.assertEqual(bundle['install']['platformio_lib_deps'], False)
        outputs = bundle_bytes(bundle)
        self.assertIn('lib/DHTesp/DHTesp.cpp', outputs)
        self.assertIn('lib/DHTesp/bundle.json', outputs)

    def setUp(self):
        self.workspace = ROOT / 'temp' / 'driver-bundle-tests' / uuid.uuid4().hex
        self.project = ProjectService.create('driver-bundle-test', 'DHT22本地驱动包测试', 'vscode',
                                              workspace=self.workspace)
        self.project.update_design(0, copy.deepcopy(DESIGN))
        self.project.scaffold(1)
        self.project.write_files(2, {
            'src/main.cpp': '#include <Arduino.h>\n#include <DHTesp.h>\n'
                            'constexpr int DHT_PIN = 4;\n'
                            'void setup() { Serial.begin(115200); Serial.println("HWCLAW_BOOT"); }\n'
                            'void loop() { delay(1000); }\n',
            'README.md': 'Local driver bundle mechanism test.',
        })

    def test_local_dependency_and_model_authored_files_are_rejected(self):
        state = self.project._load()
        with_local_dependency = copy.deepcopy(state)
        with_local_dependency['design']['dependencies'] = [
            {'name': 'DHT sensor library for ESPx', 'version': '1.19'}
        ]
        codes = {item['code'] for item in check(with_local_dependency)['issues']}
        self.assertIn('LOCAL_DEPENDENCY_MUST_BE_HOST_MANAGED', codes)

        self.project.write_files(3, {'lib/DHTesp/DHTesp.cpp': '// model authored'})
        codes = {item['code'] for item in self.project.check_files()['issues']}
        self.assertIn('HOST_MANAGED_DEPENDENCY', codes)

    def test_compile_snapshot_and_vscode_delivery_inject_bundle(self):
        self.assertEqual(self.project.check_files()['verdict'], 'pass')
        state = self.project._load()
        bundles = project_driver_bundles(state)
        self.assertEqual(len(bundles), 1)
        original_hash = fingerprint(state)
        with patch('hardware_claw.adapters.compiler.project_driver_bundles',
                   return_value=[{**bundles[0], 'manifest_sha256': 'changed'}]):
            self.assertNotEqual(fingerprint(state), original_hash)

        async def fake_run_process(command, cwd, env, log, timeout):
            expected = Path(cwd) / 'lib/DHTesp/DHTesp.cpp'
            manifest = Path(cwd) / 'lib/DHTesp/bundle.json'
            if not expected.is_file() or not manifest.is_file():
                return 'fail', 1
            output = Path(cwd) / '.pio/build/esp32s3'
            output.mkdir(parents=True)
            for name in ('firmware.bin', 'firmware.elf'):
                (output / name).write_bytes(b'test:' + name.encode())
            return 'pass', 0

        with patch('hardware_claw.adapters.compiler.PIO', Path(__file__)), \
                patch('hardware_claw.adapters.compiler.run_process', side_effect=fake_run_process):
            import asyncio
            build = asyncio.run(compile_project(self.project, 3))
        self.assertEqual(build['verdict'], 'pass')
        self.assertEqual(build['driver_bundles'][0]['library_name'], 'DHT sensor library for ESPx')
        self.assertIn('lib/DHTesp/DHTesp.h', build['driver_bundles'][0]['files'])

        exported = self.project.export(3)
        folder = Path(exported['simulation_folder'])
        self.assertTrue((folder / 'lib/DHTesp/DHTesp.cpp').is_file())
        self.assertNotIn('DHT sensor library for ESPx', (folder / 'platformio.ini').read_text('utf8'))
        self.assertEqual(json.loads((folder / 'lib/DHTesp/bundle.json').read_text('utf8'))['version'], '1.19')


if __name__ == '__main__':
    unittest.main()
