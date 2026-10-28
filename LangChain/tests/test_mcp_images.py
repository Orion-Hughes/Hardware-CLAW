import base64
import binascii
import hashlib
import json
import struct
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from hardware_claw.adapters.png_evidence import decode_png, png_info
from hardware_claw.adapters.wokwi_mcp import decode_result, inspect, read_evidence
from hardware_claw.adapters.mcp_backend import select_backend, PATCH_VERSION
from hardware_claw.projects.service import ProjectError, atomic_json
from tests import test_vscode_delivery as fixtures


def sample_png():
    def chunk(kind, payload):
        return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',binascii.crc32(kind+payload)&0xffffffff)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,1,8,6,0,0,0))
            +chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00\xff\x00\xff\x00\xff'))+chunk(b'IEND',b''))


class PNGTests(unittest.TestCase):
    def test_complete_image_and_truncation(self):
        png = sample_png()
        decoded, info = decode_png(base64.b64encode(png).decode())
        self.assertEqual(decoded,png)
        self.assertEqual((info['width'],info['height']),(2,1))
        for invalid in (png[:-1], png[:40], png+b'extra', b'not a png', png[:20]+b'bad'+png[23:]):
            with self.subTest(size=len(invalid)), self.assertRaises(ValueError):
                png_info(invalid)

    def test_patched_pin_does_not_invent_voltage(self):
        for value in (True, False):
            result = decode_result({'structuredContent':{'scope':'digital_logic_only','value':value,'voltage':None,'rawResponse':{'value':value}},'content':[]},'wokwi_read_pin')
            self.assertEqual(result['status'],'ok')
            self.assertEqual(result['pin_state']['value'],value)
            self.assertIsNone(result['pin_state']['voltage'])
            self.assertIn('不能读取电压值',result['limitation'])


class ImageEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture=fixtures.VSCodeTests()
        self.fixture.setUp()
        self.p=self.fixture.p
        self.p.check_files()
        self.fixture.fake_build()

    async def test_png_readback_checks_identity_and_content(self):
        async def fake_session(work, actions, token):
            (work/'screenshot-001.png').write_bytes(sample_png())
            return {'records':[],'execution_status':'completed','full_project_acceptance':'not_evaluated'}
        with patch('hardware_claw.adapters.wokwi_mcp.run_session',side_effect=fake_session), patch('hardware_claw.adapters.wokwi_mcp.read_token',return_value='TEST_ONLY'), patch('hardware_claw.adapters.wokwi_mcp.CLI',Path(__file__)):
            report=await inspect(self.p,3,[{'operation':'wokwi_get_status'}])
        result=read_evidence(self.p,3,report['attempt'],'screenshot-001.png')
        self.assertTrue(result['image']['complete'])
        self.assertEqual(Path(result['image_path']).read_bytes(),sample_png())
        Path(result['image_path']).write_bytes(b'forged')
        with self.assertRaises(ProjectError):
            read_evidence(self.p,3,report['attempt'],'screenshot-001.png')

    def test_backend_hash_and_fallback(self):
        folder=self.fixture.base/'backend'
        folder.mkdir()
        with patch('hardware_claw.adapters.mcp_backend.PATCH_FOLDER',folder):
            self.assertEqual(select_backend()['kind'],'official_binary')
            (folder/'cli.cjs').write_bytes(b'test-fixture')
            atomic_json(folder/'manifest.json',{'patch_version':PATCH_VERSION,'upstream_revision':'940b7237d26f','bundle_sha256':hashlib.sha256(b'test-fixture').hexdigest()})
            self.assertEqual(select_backend()['version'],PATCH_VERSION)
            (folder/'cli.cjs').write_bytes(b'changed')
            with self.assertRaises(ProjectError): select_backend()
