"""Incremental selection contracts and evidence freshness; not hardware acceptance."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hardware_claw.catalog import KnowledgeCatalog
from hardware_claw.catalog.service import DEFAULT_KNOWLEDGE_ROOT
from hardware_claw.coordinator import Coordinator, TaskStore, WorkflowError
from hardware_claw.coordinator.store import ROOT
from hardware_claw.stages.selection import SelectionTrace, SelectionReport
from hardware_claw.stages.selection_state import SelectionEvidence, accepted_baseline
from hardware_claw.tools.hardware_catalog import read_hardware


class ReuseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        root = ROOT / 'temp/selection-reuse-tests'
        root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        self.path = Path(self.tmp.name)
        self.store = TaskStore(self.path / 'tasks')
        self.c = Coordinator(self.store.create(), store=self.store)
        self.ids = ['dht22_red_module', 'ws2812_ring_8']
        self.data = read_hardware.invoke({'hardware_ids':self.ids,'view':'selection'})['data']
        self.evidence = SelectionEvidence()
        self.evidence.observe(self.data)
        self.save_accepted(self.evidence)

    async def asyncTearDown(self): self.tmp.cleanup()

    def save_accepted(self, evidence, *, legacy=False):
        self.ref, detail_ref = 'a'*32, 'b'*32
        result = {'status':'completed','summary':'fixture accepted','hardware_ids': self.ids,
                  'requirements':['fixture'], 'detail_ref':detail_ref}
        detail = {'run_id':detail_ref,'kind':'selection_detail','stage_run_id':self.ref,'result':result,
                  'events':[{'kind':'tool','name':'read_hardware','result':{'data':self.data}}]}
        if not legacy: detail['selection_snapshot'] = evidence.dump(self.ids)
        with self.store.edit(self.c.task_id) as (state, con):
            state['latest']['selection'] = self.ref
            self.store.save_record(con,self.c.task_id,{'run_id':self.ref,'stage':'selection','status':'completed','result':result})
            self.store.save_record(con,self.c.task_id,detail)

    def isolated_catalog(self):
        target = self.path / 'knowledge'
        for ref in set(self.evidence.hashes) | {'catalog.json'}:
            p = target / ref
            p.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(DEFAULT_KNOWLEDGE_ROOT/ref,p)
        return KnowledgeCatalog(target)

    @staticmethod
    def report(ids, **kwargs):
        return SelectionReport(status='completed',summary='fixture',requirements=['fixture'],hardware_ids=ids,
            compatibility={'verdict':'compatible','hardware_ids':ids,
                **{k:'fixture analysis' for k in ('requirements','interfaces','resources','electrical','platform')}}, **kwargs)

    def test_fresh_evidence_reusable_without_model_read(self):
        evidence, baseline = accepted_baseline(self.c)
        self.assertEqual(set(baseline['reusable_ids']), set(self.ids))
        self.assertEqual(baseline['invalidated'], [])
        trace = SelectionTrace(self.c,evidence,baseline)
        trace.validate(self.report(self.ids,source_refs=['cards/dht22_red_module.json']))
        self.assertFalse(trace.read_ids)
        self.assertEqual(trace.changes(self.report(self.ids))['reused_hardware_ids'], sorted(self.ids))
        self.assertNotIn('documents',baseline['hardware'][0])

    def test_old_record_can_be_upgraded_without_mutation(self):
        self.save_accepted(self.evidence,legacy=True)
        old = self.store.record(self.c.task_id,'b'*32)
        _, baseline = accepted_baseline(self.c)
        self.assertEqual(set(baseline['reusable_ids']),set(self.ids))
        self.assertEqual(old,self.store.record(self.c.task_id,'b'*32))

    def test_changed_card_invalidates_only_affected_hardware(self):
        catalog = self.isolated_catalog()
        (catalog.root/'cards/dht22_red_module.json').write_bytes(b'changed')
        evidence, baseline = accepted_baseline(self.c,catalog)
        self.assertEqual(baseline['reusable_ids'],['ws2812_ring_8'])
        trace = SelectionTrace(self.c,evidence,baseline)
        with self.assertRaises(WorkflowError) as caught: trace.validate(self.report(self.ids))
        self.assertEqual(caught.exception.code,'UNREAD_HARDWARE')

    def test_shared_platform_change_invalidates_affected_set(self):
        catalog = self.isolated_catalog()
        (catalog.root/'platforms/esp32_s3_simulation.json').write_bytes(b'changed')
        _, baseline = accepted_baseline(self.c,catalog)
        self.assertFalse(baseline['reusable_ids'])
        self.assertEqual(len(baseline['invalidated']),2)

    def test_unrelated_catalog_addition_does_not_require_reread(self):
        catalog = self.isolated_catalog()
        path = catalog.root/'catalog.json'
        value=json.loads(path.read_text('utf8'));value['note']='unrelated update'
        path.write_text(json.dumps(value),encoding='utf8')
        _, baseline = accepted_baseline(self.c,catalog)
        self.assertEqual(set(baseline['reusable_ids']),set(self.ids))

    def test_remapped_or_missing_card_not_reused(self):
        catalog=self.isolated_catalog();path=catalog.root/'catalog.json'
        value=json.loads(path.read_text('utf8'))
        value['records']=[r for r in value['records'] if r['id']!='dht22_red_module']
        path.write_text(json.dumps(value),encoding='utf8')
        _, baseline=accepted_baseline(self.c,catalog)
        self.assertEqual(baseline['reusable_ids'],['ws2812_ring_8'])

    def test_upstream_registry_remap_invalidates_matching_hardware(self):
        catalog=self.isolated_catalog();path=catalog.root/'catalog.json'
        value=json.loads(path.read_text('utf8'))
        value['upstream_parts']['wokwi-dht22']='upstream/different.json'
        path.write_text(json.dumps(value),encoding='utf8')
        _, baseline=accepted_baseline(self.c,catalog)
        self.assertEqual(baseline['reusable_ids'],['ws2812_ring_8'])

    def test_missing_or_cross_task_detail_cannot_supply_evidence(self):
        other = Coordinator(self.store.create(),store=self.store)
        with self.store.edit(other.task_id) as (state,con):
            state['latest']['selection']='c'*32
            self.store.save_record(con,other.task_id,{'run_id':'c'*32,'stage':'selection','status':'completed',
                'result':{'hardware_ids':self.ids,'detail_ref':'b'*32}})
        _, baseline = accepted_baseline(other)
        self.assertFalse(baseline['reusable_ids'])

    def test_compatibility_must_cover_final_set_and_not_be_unresolved(self):
        e,b=accepted_baseline(self.c);trace=SelectionTrace(self.c,e,b)
        report=self.report(self.ids);report.compatibility=None
        with self.assertRaises(WorkflowError) as caught: trace.validate(report)
        self.assertEqual(caught.exception.code,'COMPATIBILITY_REQUIRED')
        for verdict in ('conflict','unknown'):
            report=self.report(self.ids);report.compatibility.verdict=verdict
            with self.assertRaises(WorkflowError) as caught: trace.validate(report)
            self.assertEqual(caught.exception.code,'COMPATIBILITY_UNRESOLVED')
        report=self.report(self.ids);report.compatibility.hardware_ids=self.ids[:1]
        with self.assertRaises(WorkflowError):trace.validate(report)

    def test_removing_old_hardware_requires_explicit_change_reason(self):
        e,b=accepted_baseline(self.c);trace=SelectionTrace(self.c,e,b)
        with self.assertRaises(WorkflowError):trace.validate(self.report(self.ids[:1]))
        trace.validate(self.report(self.ids[:1],removed_hardware_ids=self.ids[1:],change_reason='user removed output'))

    async def test_only_new_hardware_reads_and_reuse_survives_next_stage(self):
        e,b=accepted_baseline(self.c);trace=SelectionTrace(self.c,e,b)
        tool=trace.make_tools()[1]
        reused=await tool.ainvoke({'hardware_ids':self.ids,'view':'selection'})
        self.assertEqual(reused['data']['mode'],'selection_reuse')
        self.assertFalse(trace.read_ids)
        result=await tool.ainvoke({'hardware_ids':self.ids+['potentiometer'],'view':'selection'})
        self.assertEqual([h['id'] for h in result['data']['hardware']],['potentiometer'])
        report=self.report(self.ids+['potentiometer'])
        trace.validate(report)
        self.assertEqual(trace.read_ids,{'potentiometer'})
        self.ids=report.hardware_ids
        self.save_accepted(trace.evidence)
        _, again=accepted_baseline(self.c)
        self.assertEqual(set(again['reusable_ids']),set(self.ids))

    def test_failed_attempt_does_not_replace_accepted_baseline(self):
        with self.store.edit(self.c.task_id) as (state,con):
            state['latest_attempts']={'selection':'d'*32}
            self.store.save_record(con,self.c.task_id,{'run_id':'d'*32,'stage':'selection','status':'blocked',
                'result':{'status':'blocked','hardware_ids':['usb_camera']}})
        _,baseline=accepted_baseline(self.c)
        self.assertEqual(baseline['handoff_ref'],self.ref)
        self.assertEqual(set(baseline['reusable_ids']),set(self.ids))

    def test_failed_report_does_not_claim_old_hardware_was_removed(self):
        evidence, baseline = accepted_baseline(self.c)
        trace = SelectionTrace(self.c, evidence, baseline)
        changes = trace.changes(SelectionReport(status='blocked', summary='format failure'))
        self.assertFalse(changes['applied'])
        self.assertEqual(changes['removed_hardware_ids'], [])
        changes = trace.changes(self.report(self.ids[:1], removed_hardware_ids=self.ids[1:], change_reason='user request'))
        self.assertTrue(changes['applied'])
        self.assertEqual(changes['removed_hardware_ids'], self.ids[1:])
