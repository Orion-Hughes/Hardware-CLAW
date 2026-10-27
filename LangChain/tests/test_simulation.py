import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from hardware_claw.validation.scenarios import assess, CONTRACT_ID, VALUES, LINE_FORMAT
from hardware_claw.adapters.simulator import simulate, evaluate
from hardware_claw.projects.service import ProjectError, ProjectService
from tests import test_vscode_delivery as fixtures

PLAN = {"expected": VALUES, "scope": "test", "uncovered": ["other functions"]}
GOOD = '\n'.join(LINE_FORMAT.format(t=t,h=h) for t,h in VALUES)
DONE = f'Starting simulation...\n[{CONTRACT_ID}] Scenario completed successfully'
RECORD = {"exit_code": 0, "execution_verdict": "completed"}


class EvaluationTests(unittest.TestCase):
    def test_changed_and_restored_values_pass(self):
        result = assess(RECORD, GOOD, DONE, PLAN)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["full_project_acceptance"], "not_evaluated")

    def test_constant_sensor_and_fake_cli_echo_fail(self):
        constant = '\n'.join([LINE_FORMAT.format(t=24,h=40)]*10)
        self.assertEqual(assess(RECORD, constant, DONE, PLAN)["verdict"], "fail")
        self.assertEqual(assess(RECORD, '', DONE + GOOD, PLAN)["verdict"], "fail")

    def test_cli_serial_file_without_line_endings(self):
        self.assertEqual(assess(RECORD, GOOD.replace('\n',''), DONE, PLAN)['verdict'],'pass')

    def test_missing_restore_and_error_are_failures(self):
        self.assertEqual(assess(RECORD, '\n'.join(GOOD.splitlines()[:2]), DONE, PLAN)["verdict"], "fail")
        self.assertEqual(assess(RECORD, GOOD + '\nDHT_ERROR: TIMEOUT', DONE, PLAN)["verdict"], "fail")

    def test_timeout_auth_failure_distinct(self):
        self.assertEqual(assess({"exit_code":42,"execution_verdict":"completed"},'', 'Starting simulation...',PLAN)["verdict"],"timeout")
        self.assertEqual(assess({"exit_code":1,"execution_verdict":"completed"},'', 'Unauthorized',PLAN)["verdict"],"tool_error")
        self.assertEqual(assess({"exit_code":None,"execution_verdict":"timeout"},'', '',PLAN)["verdict"],"timeout")


class SimulationStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = fixtures.VSCodeTests()
        self.fixture.setUp()
        self.p = self.fixture.p
        self.p.check_files()
        self.fixture.fake_build()

    async def fake_cli(self, work, token):
        (work/'serial.txt').write_text(GOOD,encoding='utf-8')
        (work/'cli.log').write_text(DONE,encoding='utf-8')
        return "completed", 0

    async def run_fake(self):
        with patch('hardware_claw.adapters.simulator.read_token',return_value='TEST_ONLY_TOKEN'), patch('hardware_claw.adapters.simulator.run_cli',side_effect=self.fake_cli):
            return await simulate(self.p, 3)

    async def test_default_is_vscode(self):
        p = ProjectService.create('default','example',workspace=self.fixture.base)
        self.assertEqual(p.get()['template'],'vscode')

    async def test_report_round_trip_cache_and_invalidation(self):
        first = await self.run_fake()
        report = evaluate(self.p, 3)
        self.assertEqual(report['verdict'],'pass')
        self.assertEqual(self.p.get()['behavior'],'pass')
        second = await self.run_fake()
        self.assertTrue(second['cached'])
        self.assertEqual(first['attempt'],second['attempt'])
        self.p.write_files(3, {'README.md':'new revision'})
        self.assertEqual(self.p.get()['behavior'],'not_run')
        with self.assertRaises(ProjectError):
            evaluate(self.p, 4)

    async def test_evidence_tampering_rejected(self):
        report = await self.run_fake()
        (Path(report['evidence_directory'])/'serial.txt').write_text('forged',encoding='utf-8')
        self.assertEqual(self.p.get()['behavior'],'not_run')
        with self.assertRaises(ProjectError) as caught:
            evaluate(self.p,3)
        self.assertEqual(caught.exception.code,'EVIDENCE_CHANGED')

    async def test_evaluate_requires_simulation_and_current_build(self):
        with self.assertRaises(ProjectError):
            evaluate(self.p,3)
        await self.run_fake()
        evaluate(self.p,3)
        path = next((self.p.meta/'builds').rglob('firmware.bin'))
        path.write_bytes(b'changed')
        self.assertEqual(self.p.get()['behavior'],'not_run')
        with self.assertRaises(ProjectError):
            evaluate(self.p,3)

    async def test_cannot_weaken_plan(self):
        await self.run_fake()
        path = self.p.meta/'test_plan.json'
        plan=json.loads(path.read_text(encoding='utf-8'))
        plan['expected']=[[24,40]]
        path.write_text(json.dumps(plan),encoding='utf-8')
        with self.assertRaises(ProjectError):
            evaluate(self.p,3)
