"""Card metadata and document-access tests, not firmware/device acceptance."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from hardware_claw.catalog import KnowledgeCatalog, CatalogError
from hardware_claw.catalog.cards import HardwareCard, read_documents
from hardware_claw.catalog.service import DEFAULT_KNOWLEDGE_ROOT as ROOT
from hardware_claw.tools.hardware_catalog import read_hardware_documents


class HardwareCardsTests(unittest.TestCase):
    def test_all_cards_and_links_and_registry_definitions(self):
        catalog = KnowledgeCatalog()
        index = json.loads((ROOT / 'catalog.json').read_text('utf8'))
        self.assertEqual(len(index['records']), len({entry['id'] for entry in index['records']}))
        self.assertEqual({entry['path'] for entry in index['records']},
                         {f'cards/{file.name}' for file in (ROOT / 'cards').glob('*.json')})
        self.assertEqual(sum(r['owned'] for r in index['records']), 9)
        for entry in index['records']:
            with self.subTest(entry=entry['id']):
                card = HardwareCard.model_validate_json((ROOT / entry['path']).read_bytes())
                info = catalog.get(entry['id'], include_shared=True)
                self.assertEqual(card.id, info['summary']['id'])
                for group in card.documents.model_dump().values():
                    for doc in group:
                        catalog._bytes(doc['ref'], prefixes=('upstream/', 'guidance/', 'drivers/'))
                self.assertEqual(card.simulation['simulation_test'], card.availability['simulation_test'])
                self.assertEqual(card.simulation['hardware_test'], card.availability['physical_test'])
        for part in index['upstream_parts']:
            self.assertIsNotNone(catalog.get('wokwi:' + part)['upstream_definition'])

    def test_every_upstream_file_is_locked_and_unchanged(self):
        lock = json.loads((ROOT / 'sources.lock.json').read_text('utf8'))
        refs = {entry['local_path'] for entry in lock['files']}
        actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / 'upstream').rglob('*') if p.is_file()}
        self.assertEqual(refs, actual)
        for entry in lock['files']:
            self.assertEqual(hashlib.sha256((ROOT / entry['local_path']).read_bytes()).hexdigest(), entry['sha256'])

    def test_documents_are_batched_and_no_network_is_used(self):
        catalog = KnowledgeCatalog()
        for ident in ('dht22_red_module', 'mpu6050', 'ws2812_ring_8', 'st7789_240x240_simulation'):
            docs = catalog.get(ident)['profile']['documents']
            refs = [docs['simulation'][0]['ref'], docs['api'][0]['ref'], docs['guidance'][-1]['ref']]
            with patch('socket.create_connection', side_effect=AssertionError('network forbidden')):
                result = read_documents(catalog, ident, refs, 60000)
            self.assertTrue(result['complete'], ident)
            self.assertEqual(len(result['documents']), 3)
            for item in result['documents']:
                self.assertEqual(item['content'], (ROOT / item['ref']).read_text('utf-8-sig'))

    def test_budget_does_not_silently_truncate(self):
        result = read_documents(KnowledgeCatalog(), 'dht22_red_module',
                                ['drivers/DHTesp/DHTesp.h'], 1000)
        self.assertFalse(result['complete'])
        self.assertEqual(result['documents'], [])
        self.assertEqual(result['omitted'][0]['reason'], 'response_budget')

    def test_cross_card_and_unregistered_and_secret_paths_rejected(self):
        for ref in ['../DS_Api.txt', 'upstream/drivers/Adafruit_MPU6050/Adafruit_MPU6050.h',
                    'upstream/unknown.md']:
            result = read_hardware_documents.invoke({'hardware_id':'dht22_red_module','references':[ref]})
            self.assertEqual(result['error_code'], 'UNSAFE_REFERENCE')
        result = read_hardware_documents.invoke({'hardware_id':'unknown-device','references':['guidance/usage-boundaries.md']})
        self.assertEqual(result['error_code'], 'NOT_FOUND')

    def test_changed_upstream_text_rejected(self):
        temp_root = ROOT.parents[1] / 'temp/hardware-card-tests'
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            target = Path(tmp)
            for ref in ['library.json', 'sources.lock.json', 'upstream/wokwi-docs/docs/parts/wokwi-dht22.md']:
                path = target / ref; path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / ref, path)
            (target / 'upstream/wokwi-docs/docs/parts/wokwi-dht22.md').write_text('changed', encoding='utf8')
            with self.assertRaises(CatalogError) as caught:
                KnowledgeCatalog(target)._bytes('upstream/wokwi-docs/docs/parts/wokwi-dht22.md', prefixes=('upstream/',))
            self.assertEqual(caught.exception.code, 'SOURCE_CHANGED')

    def test_failed_card_validation_is_explicit(self):
        from hardware_claw.catalog.cards import to_profile
        card = json.loads((ROOT / 'cards/dht22_red_module.json').read_text('utf8'))
        card['documents']['api'][0].pop('purpose')
        with self.assertRaises(CatalogError) as caught:
            to_profile(KnowledgeCatalog(), card)
        self.assertEqual(caught.exception.code, 'INVALID_CARD')


if __name__ == '__main__':
    unittest.main()
