"""Behavior of the public two-tool interface; no device or paid model calls."""
import json
import unittest
from unittest.mock import Mock, patch

from hardware_claw.catalog import KnowledgeCatalog, CatalogError
from hardware_claw.catalog.bundles import read_hardware_bundle
from hardware_claw.catalog.service import DEFAULT_KNOWLEDGE_ROOT as ROOT
from hardware_claw.tools.hardware_catalog import HARDWARE_TOOLS, read_hardware, search_hardware
from hardware_claw import limits


class HardwareBundleTests(unittest.TestCase):
    def test_large_document_continuation_crosses_old_wrapper_limit(self):
        ref = 'upstream/large-api.h'
        sources = {ref: b'x' * 70000}
        catalog = self.source_fixture(sources)
        with patch('hardware_claw.tools.hardware_catalog.KnowledgeCatalog', return_value=catalog):
            first = read_hardware.invoke({'hardware_ids': ['fixture']})['data']
            self.assertEqual(first['missing_required_refs'], [ref])
            self.assertEqual(len(first['next_reads']), 1)
            call = first['next_reads'][0]
            self.assertGreater(call['args']['max_characters'], 64000)
            second = read_hardware.invoke(call['args'])
        self.assertEqual(second['execution_status'], 'ok')
        self.assertTrue(second['data']['complete'])
        self.assertEqual(second['data']['documents'][0]['content'], 'x' * 70000)
        self.assertLessEqual(len(json.dumps(second['data'], ensure_ascii=False)), call['args']['max_characters'])
        self.assertEqual(second['data']['next_reads'], [])

    def test_continuations_split_by_size_and_reference_count(self):
        for sources in ({f'upstream/api{i}.h': b'x' * 50000 for i in range(4)},
                        {f'upstream/api{i}.h': b'x' * 2000 for i in range(28)}):
            with self.subTest(count=len(sources)):
                catalog = self.source_fixture(sources)
                first = read_hardware_bundle(catalog, ['fixture'], max_characters=18000)
                self.assertGreater(len(first['next_reads']), 1)
                seen = {d['ref'] for d in first['documents'] if d['status'] == 'included'}
                for call in first['next_reads']:
                    args = call['args'].copy(); args.pop('view')
                    self.assertLessEqual(len(args['references']), 24)
                    self.assertFalse(seen.intersection(args['references']))
                    supplement = read_hardware_bundle(catalog, **args)
                    self.assertTrue(supplement['complete'])
                    self.assertLessEqual(len(json.dumps(supplement, ensure_ascii=False)), args['max_characters'])
                    seen.update(args['references'])
                self.assertEqual(seen, set(sources))

    def test_unreadable_and_oversized_sources_have_no_futile_retry(self):
        sources = {'upstream/large.h': b'x' * limits.HARDWARE_READ_MAX_CHARACTERS,
                   'upstream/bad.h': b'\xff'}
        data = read_hardware_bundle(self.source_fixture(sources), ['fixture'])
        self.assertEqual(set(data['missing_required_refs']), set(sources))
        self.assertEqual(data['next_reads'], [])
        self.assertEqual({b['error_code'] for b in data['blockers']},
                         {'SOURCE_EXCEEDS_SINGLE_READ', 'INVALID_TEXT'})
        self.assertFalse(data['complete'])

    def test_real_combinations_follow_returned_calls_without_losing_sources(self):
        combinations = [
            ['esp32_s3_devkitc1_n32r16v', 'ps2_joystick', 'st7789_240x240_simulation'],
            ['esp32_s3_devkitc1_n32r16v', 'mpu6050', 'ds1307', 'sg90_180'],
        ]
        for ids in combinations:
            with self.subTest(ids=ids):
                first = read_hardware.invoke({'hardware_ids': ids, 'max_characters': 32000})['data']
                self.assertIsNotNone(first)
                self.assertTrue(first['missing_required_refs'])
                self.assertEqual(first['blockers'], [])
                required = {d['ref'] for d in first['documents'] if d['essential_for']}
                seen = {d['ref'] for d in first['documents'] if d['status'] == 'included'}
                for call in first['next_reads']:
                    result = read_hardware.invoke(call['args'])
                    self.assertEqual(result['execution_status'], 'ok')
                    data = result['data']
                    self.assertTrue(data['complete'])
                    self.assertLessEqual(len(json.dumps(data, ensure_ascii=False)), call['args']['max_characters'])
                    for doc in data['documents']:
                        self.assertNotIn(doc['ref'], seen)
                        self.assertEqual(doc['content'], (ROOT/doc['ref']).read_bytes().decode('utf-8-sig'))
                        seen.add(doc['ref'])
                self.assertLessEqual(required, seen)

    @staticmethod
    def source_fixture(sources):
        """In-memory source fixture, independent of real devices and project outputs."""
        catalog = Mock()
        catalog.get.return_value = {'summary': {}, 'upstream_definition': {},
            'shared_configuration': None, 'provenance': {}, 'profile': {
                'availability': {}, 'simulation': {}, 'driver_profile': {}, 'electrical_profile': {},
                'generation_profile': {'controls': []}, 'documents': {'api': [
                    {'ref': ref, 'purpose': 'API source', 'read_when': 'implementation', 'load': 'essential'}
                    for ref in sources]}}}
        def read(ref, **kwargs):
            value = sources[ref]
            if isinstance(value, Exception): raise value
            return value
        catalog._bytes.side_effect = read
        return catalog

    def test_later_hashes_and_errors_do_not_overflow_earlier_text(self):
        sources = {'upstream/first.h': ('"\\\n汉' * 1200).encode('utf8'),
                   'upstream/oversized.h': b'x' * 65000,
                   'upstream/invalid.h': b'\xff',
                   'upstream/missing.h': CatalogError('MISSING_REFERENCE', 'missing')}
        catalog = self.source_fixture(sources)
        baseline = read_hardware_bundle(catalog, ['fixture'], max_characters=60000)
        self.assertEqual(baseline['documents'][0]['status'], 'included')
        boundary = len(json.dumps(baseline, ensure_ascii=False))
        # One character short used to fit the first file, then fail on later metadata.
        for budget in (boundary - 1, boundary, boundary + 1):
            with self.subTest(budget=budget):
                catalog._bytes.reset_mock()
                result = read_hardware_bundle(catalog, ['fixture'], max_characters=budget)
                self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), budget)
                self.assertFalse(result['complete'])
                self.assertEqual(result['documents'][0]['status'], 'omitted' if budget < boundary else 'included')
                self.assertEqual(result['documents'][1]['status'], 'omitted')
                self.assertEqual(result['documents'][2]['reason'], 'INVALID_TEXT')
                self.assertEqual(result['documents'][3]['reason'], 'MISSING_REFERENCE')
                self.assertEqual(catalog._bytes.call_count, len(sources))

    def test_exact_complete_packet_budget_and_supplement(self):
        sources = {'upstream/first.h': b'a' * 2500, 'upstream/second.h': b'b' * 2500}
        catalog = self.source_fixture(sources)
        complete = read_hardware_bundle(catalog, ['fixture'], max_characters=60000)
        exact = len(json.dumps(complete, ensure_ascii=False))
        self.assertTrue(read_hardware_bundle(catalog, ['fixture'], max_characters=exact)['complete'])
        partial = read_hardware_bundle(catalog, ['fixture'], max_characters=exact - 1)
        self.assertLessEqual(len(json.dumps(partial, ensure_ascii=False)), exact - 1)
        self.assertFalse(partial['complete'])
        omitted = [d['ref'] for d in partial['documents'] if d['status'] == 'omitted']
        supplement = read_hardware_bundle(catalog, ['fixture'], references=omitted)
        self.assertTrue(supplement['complete'])
        self.assertEqual([d['ref'] for d in supplement['documents']], omitted)

    def test_metadata_alone_over_budget_still_errors(self):
        catalog = self.source_fixture({'upstream/first.h': b'x'})
        catalog.get.return_value['summary'] = {'description': 'x' * 5000}
        with self.assertRaises(CatalogError) as caught:
            read_hardware_bundle(catalog, ['fixture'], max_characters=4000)
        self.assertEqual(caught.exception.code, 'RESULT_TOO_LARGE')

    def test_only_two_hardware_tools_registered(self):
        self.assertEqual([t.name for t in HARDWARE_TOOLS], ['search_hardware', 'read_hardware'])

    def test_search_provides_selection_without_source_text(self):
        item = search_hardware.invoke({'query': '温湿度'})['data']['items'][0]
        for field in ('description', 'inputs', 'outputs', 'interfaces', 'constraints', 'pin_requirements'):
            self.assertIn(field, item['selection'])
        self.assertIn('missing_information', item)
        self.assertNotIn('content', json.dumps(item))

    def test_all_cards_default_read_is_explicit_and_local(self):
        index = json.loads((ROOT / 'catalog.json').read_text('utf8'))
        for entry in index['records']:
            with self.subTest(ident=entry['id']), patch('socket.create_connection', side_effect=AssertionError('network')):
                result = read_hardware.invoke({'hardware_ids': [entry['id']]})
                self.assertEqual(result['execution_status'], 'ok')
                data = result['data']
                self.assertEqual(data['hardware'][0]['availability']['physical_test'], 'not_run')
                self.assertLessEqual(len(json.dumps(data, ensure_ascii=False)), 56000)
                for doc in data['documents']:
                    if doc['status'] == 'included':
                        self.assertEqual(doc['content'], (ROOT / doc['ref']).read_bytes().decode('utf-8-sig'))
                    else:
                        self.assertNotIn('content', doc)

    def test_multiple_devices_deduplicate_platform_and_shared_docs(self):
        data = read_hardware.invoke({'hardware_ids': ['ps2_joystick', 'sg90_180', 'ps2_joystick']})['data']
        self.assertTrue(data['complete'])
        self.assertEqual(len(data['hardware']), 2)
        self.assertEqual(len(data['platforms']), 1)
        refs = [d['ref'] for d in data['documents']]
        self.assertEqual(len(refs), len(set(refs)))
        shared = next(d for d in data['documents'] if d['ref'] == 'guidance/usage-boundaries.md')
        self.assertEqual(set(shared['essential_for']), {'ps2_joystick', 'sg90_180'})

    def test_budget_omissions_can_be_read_without_repeating_packet(self):
        data = read_hardware.invoke({'hardware_ids': ['dht22_red_module'], 'max_characters': 13000})['data']
        self.assertIsNotNone(data)
        self.assertFalse(data['complete'])
        refs = [d['ref'] for d in data['documents'] if d['status'] == 'omitted']
        self.assertTrue(refs)
        second = read_hardware.invoke({'hardware_ids': ['dht22_red_module'], 'references': refs})['data']
        self.assertTrue(second['complete'])
        self.assertEqual(second['platforms'], [])
        self.assertEqual({d['ref'] for d in second['documents']}, set(refs))
        self.assertNotIn('programming', second['hardware'][0])

    def test_optional_source_only_read_when_explicit(self):
        ref = 'drivers/DHTesp/README.md'
        data = read_hardware.invoke({'hardware_ids': ['dht22_red_module']})['data']
        self.assertEqual(next(d['status'] for d in data['documents'] if d['ref'] == ref), 'reference')
        second = read_hardware.invoke({'hardware_ids': ['dht22_red_module'], 'references': [ref]})['data']
        self.assertTrue(second['complete'])
        self.assertEqual(len(second['documents']), 1)

    def test_unknown_id_does_not_discard_valid_hardware(self):
        data = read_hardware.invoke({'hardware_ids': ['unknown', 'dht22_red_module']})['data']
        self.assertFalse(data['complete'])
        self.assertEqual(data['errors'][0]['error_code'], 'NOT_FOUND')
        self.assertEqual(data['hardware'][0]['id'], 'dht22_red_module')
        upstream = read_hardware.invoke({'hardware_ids': ['wokwi:wokwi-dht22']})['data']
        self.assertEqual(upstream['errors'][0]['error_code'], 'NO_CARD')

    def test_unregistered_and_cross_hardware_refs_rejected(self):
        for ref in ('../DS_Api.txt', 'upstream/drivers/RTClib/src/RTClib.h'):
            result = read_hardware.invoke({'hardware_ids': ['dht22_red_module'], 'references': [ref]})
            self.assertEqual(result['error_code'], 'UNSAFE_REFERENCE')

    def test_corrupt_source_does_not_claim_complete(self):
        catalog = KnowledgeCatalog()
        original = catalog._bytes
        ref = 'drivers/DHTesp/DHTesp.h'
        def read(path, **kwargs):
            if path == ref:
                raise CatalogError('SOURCE_CHANGED', 'source hash mismatch')
            return original(path, **kwargs)
        with patch.object(catalog, '_bytes', side_effect=read):
            data = read_hardware_bundle(catalog, ['dht22_red_module'])
        self.assertFalse(data['complete'])
        self.assertEqual(data['documents'], [])
        self.assertEqual(data['errors'][0]['error_code'], 'SOURCE_CHANGED')

    def test_invalid_inputs_do_not_run(self):
        for args in ({'hardware_ids': []}, {'hardware_ids': ['a'] * 9},
                     {'hardware_ids': ['a'], 'references': []}):
            result = read_hardware.invoke(args)
            if isinstance(result, str): result = json.loads(result)
            self.assertEqual(result['error_code'], 'INVALID_ARGUMENT')
