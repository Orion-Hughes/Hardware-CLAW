import json
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock, Mock
from hardware_claw.validation.observation import assess, OBSERVATION
from hardware_claw.adapters.simulator import simulate, evaluate, current_report, run_cli
from hardware_claw.projects.service import ProjectError, ProjectService, atomic_json
from tests import test_vscode_delivery as fixtures


class EvaluationTests(unittest.TestCase):
    def test_observation_never_claims_acceptance(self):
        for code in (0, 42):
            for serial in ("", "Hello", "Temperature: 24.0 C | Humidity: 40.0 %", "ERROR is a quoted example"):
                result = assess({"exit_code": code, "execution_verdict": "completed"}, serial, "arbitrary log")
                self.assertEqual(result["verdict"], "unsupported")
                self.assertEqual(result["checks"], [])
                self.assertEqual(result["full_project_acceptance"], "not_evaluated")

    def test_infrastructure_failures_are_not_business_verdicts(self):
        self.assertEqual(assess({"exit_code":1,"execution_verdict":"completed"},'', 'Unauthorized')["verdict"],"tool_error")
        self.assertEqual(assess({"exit_code":None,"execution_verdict":"timeout"},'', '')["verdict"],"timeout")


class SimulationStorageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = fixtures.VSCodeTests()
        self.fixture.setUp()
        self.p = self.fixture.p
        self.p.check_files()
        self.fixture.fake_build()

    async def fake_cli(self, work, token):
        self.assertFalse((work/'scenario.yaml').exists())
        (work/'serial.txt').write_text('arbitrary device output',encoding='utf-8')
        (work/'cli.log').write_text('observation window reached',encoding='utf-8')
        return "observation_limit", 42

    async def run_fake(self):
        with patch('hardware_claw.adapters.simulator.read_token',return_value='TEST_ONLY_TOKEN'), patch('hardware_claw.adapters.simulator.run_cli',side_effect=self.fake_cli), patch('hardware_claw.adapters.simulator.CLI', Path(__file__)):
            return await simulate(self.p, 3)

    async def test_default_is_vscode(self):
        p = ProjectService.create('default','example',workspace=self.fixture.base)
        self.assertEqual(p.get()['template'],'vscode')

    async def test_cli_command_has_no_special_scenario(self):
        work = self.fixture.base / 'cli-observation'
        work.mkdir()
        process = Mock(returncode=42)
        process.stdout.read = AsyncMock(side_effect=[b'observation ended', b''])
        process.wait = AsyncMock(return_value=42)
        with patch('hardware_claw.adapters.simulator.asyncio.create_subprocess_exec', new_callable=AsyncMock, return_value=process) as spawn:
            verdict, code = await run_cli(work, 'TEST_ONLY_TOKEN')
        self.assertEqual((verdict, code), ('observation_limit', 42))
        args = spawn.call_args.args
        self.assertNotIn('--scenario', args)
        self.assertIn('--serial-log-file', args)
        self.assertEqual(spawn.call_args.kwargs['env']['WOKWI_CLI_TOKEN'], 'TEST_ONLY_TOKEN')
        self.assertNotIn('TEST_ONLY_TOKEN', (work/'cli.log').read_text())

    async def test_board_only_runs_and_no_test_plan_is_created(self):
        self.assertEqual(self.p._load()['design']['components'], [])
        result = await self.run_fake()
        self.assertEqual(result['execution_verdict'], 'observation_limit')
        self.assertFalse((self.p.meta/'test_plan.json').exists())
        self.assertEqual(evaluate(self.p, 3)['verdict'], 'unsupported')

    async def test_report_round_trip_cache_and_invalidation(self):
        first = await self.run_fake()
        self.assertEqual(evaluate(self.p, 3)['verdict'],'unsupported')
        self.assertEqual(self.p.get()['behavior'],'unsupported')
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
        next((self.p.meta/'builds').rglob('firmware.bin')).write_bytes(b'changed')
        self.assertEqual(self.p.get()['behavior'],'not_run')
        with self.assertRaises(ProjectError):
            evaluate(self.p,3)

    async def test_legacy_report_is_not_current_and_plan_untouched(self):
        legacy = {'version':3, 'execution_verdict':'completed', 'contract_id':'legacy_specific', 'attempt':'old'}
        atomic_json(self.p.meta/'simulation.json', legacy)
        atomic_json(self.p.meta/'evaluation.json', {'version':3,'attempt':'old','verdict':'pass'})
        atomic_json(self.p.meta/'test_plan.json', {'contract_id':'legacy_specific'})
        self.assertIsNone(current_report(self.p, self.p._load()))
        self.assertEqual(self.p.get()['behavior'], 'not_run')
        await self.run_fake()
        self.assertEqual(evaluate(self.p, 3)['verdict'], 'unsupported')
        self.assertEqual(json.loads((self.p.meta/'test_plan.json').read_text())['contract_id'], 'legacy_specific')
