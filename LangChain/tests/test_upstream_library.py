"""Source-first catalog mechanisms, not project-specific generation fixtures."""
import json
from pathlib import Path
import shutil
import unittest
import uuid
from hardware_claw.catalog import KnowledgeCatalog, CatalogError
from hardware_claw.catalog.service import DEFAULT_KNOWLEDGE_ROOT
from hardware_claw.catalog.driver_api import get_driver_api
from hardware_claw.catalog.associations import properties


class UpstreamLibraryTests(unittest.TestCase):
    def test_sources_match_manifest(self):
        c = KnowledgeCatalog()
        lock, _ = c._json('sources.lock.json', prefixes=('sources.lock.json',))
        for item in lock['files']:
            raw = c._bytes(item['local_path'], prefixes=('upstream/', 'supplements/sources/'))
            self.assertEqual(len(raw), item['bytes'])

    def test_associations_do_not_store_handwritten_api(self):
        c = KnowledgeCatalog()
        index, _ = c._index()
        self.assertEqual(index['schema_version'], 3)
        for entry in index['records']:
            a, _ = c._json(entry['path'], prefixes=('associations/',))
            self.assertNotIn('driver_profile', a)
            self.assertNotIn('initialization', a)
            p = c.get(entry['id'])['profile']
            self.assertNotIn('operations', p['driver_profile'])
            self.assertEqual(p['driver_profile']['api_format'], 'upstream_original_documents')

    def test_versions_are_parsed_from_original_properties(self):
        c = KnowledgeCatalog()
        for ident in ('mpu6050', 'ds1307', 'ws2812_ring_8'):
            p = c.get(ident)['profile']['driver_profile']
            for d in p['dependencies']:
                source = properties(c._bytes(d['source_ref'], prefixes=('upstream/', 'supplements/sources/')).decode('utf-8'))
                self.assertEqual((d['name'], d['version']), (source['name'], source['version']))

    def test_new_non_owned_parts_expose_original_docs_and_controls(self):
        c = KnowledgeCatalog()
        for ident in ('mpu6050', 'ds1307', 'hc_sr04', 'potentiometer'):
            d = get_driver_api(c, ident)
            self.assertFalse(d['hardware']['owned'])
            self.assertTrue(d['references'])
            first = d['references'][0]
            page = get_driver_api(c, ident, first, limit=100)['reference']
            self.assertTrue(page['source']['url'].startswith('https://'))
            self.assertEqual(page['sha256'], page['source']['sha256'])
        controls = c.get('mpu6050')['profile']['generation_profile']['controls']
        self.assertIn('accelX', [x['name'] for x in controls])

    def test_changed_or_missing_source_never_falls_back_to_old_library(self):
        root = DEFAULT_KNOWLEDGE_ROOT.parents[1] / 'temp/upstream-library-tests' / uuid.uuid4().hex
        shutil.copytree(DEFAULT_KNOWLEDGE_ROOT, root)
        c = KnowledgeCatalog(root)
        ref = 'upstream/wokwi-docs/docs/parts/wokwi-dht22.md'
        p = root / ref
        p.write_text('modified source', encoding='utf-8')
        with self.assertRaises(CatalogError) as result:
            c._bytes(ref, prefixes=('upstream/',))
        self.assertEqual(result.exception.code, 'SOURCE_CHANGED')
        p.unlink()
        with self.assertRaises(CatalogError) as result:
            c._bytes(ref, prefixes=('upstream/',))
        self.assertEqual(result.exception.code, 'MISSING_REFERENCE')

    def test_missing_lock_is_not_treated_as_unverified_success(self):
        root = DEFAULT_KNOWLEDGE_ROOT.parents[1] / 'temp/upstream-library-tests' / uuid.uuid4().hex
        root.mkdir(parents=True)
        (root / 'library.json').write_text('{}', encoding='utf-8')
        p = root / 'upstream/file.h'
        p.parent.mkdir()
        p.write_text('fixture', encoding='utf-8')
        with self.assertRaises(CatalogError):
            KnowledgeCatalog(root)._bytes('upstream/file.h', prefixes=('upstream/',))
