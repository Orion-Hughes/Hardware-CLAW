"""Generic source/context mechanics; these fixtures are not production answers."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

from hardware_claw import limits
from hardware_claw.coordinator import Coordinator, TaskStore, WorkflowError
from hardware_claw.coordinator.agent import make_coordinator_tools
from hardware_claw.projects.service import ProjectService, ROOT, atomic_json
from hardware_claw.stages.generation import GenerationTrace
from hardware_claw.stages.generation_finish import prepare_repair, request_repair, validate_repair_batch, GenerationRepair, inspect_candidate
from hardware_claw.projects.source_context import line_excerpt

BOARD = 'esp32_s3_devkitc1_n32r16v'


class ReadThenRepairModel(BaseChatModel):
    mode: str = 'read'
    _requests: list = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return 'generic-repair-reader-fixture'

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._requests.append(messages)
        if self.mode in {'wrong_patch', 'multi_submit'}:
            name = 'GenerationRepair'
            args = {'edits': [{'path': 'src/main.cpp',
                              'old_text': 'void loop(){}' if isinstance(messages[-1], ToolMessage) else 'wrong source',
                              'new_text': 'void loop(){delay(1);}'}]}
        elif isinstance(messages[-1], ToolMessage) and self.mode != 'repeat':
            assert json.loads(messages[-1].content)['start_line'] == 1
            name = 'GenerationRepair'
            args = {'edits': [{'path': 'include/settings.h',
                              'old_text': 'constexpr int VALUE = 1;',
                              'new_text': 'constexpr int VALUE = 2;'}]}
        else:
            name = 'ReadRepairSource'
            args = {'path': '../outside.h' if self.mode == 'outside' else 'include/settings.h',
                    'start_line': 1, 'end_line': 20}
        msg = AIMessage(content='', tool_calls=[{'name': name, 'args': args, 'id': str(len(messages))}],
                        usage_metadata={'input_tokens': 10, 'output_tokens': 2, 'total_tokens': 12})
        if self.mode in {'multi_read', 'multi_submit'} and not isinstance(messages[-1], ToolMessage):
            msg.tool_calls.append({'name': name, 'args': args, 'id': f'second-{len(messages)}', 'type': 'tool_call'})
        return ChatResult(generations=[ChatGeneration(message=msg)])


class DiagnosticContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        base = ROOT / 'temp' / 'diagnostic-context-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.project = ProjectService.create('context fixture', 'software mechanism fixture', workspace=root / 'projects')
        self.project.update_design(0, {'goal': 'context fixture', 'simulation_only': True, 'board_id': BOARD,
                                      'components': [], 'connections': [], 'dependencies': [],
                                      'pin_defines': {}, 'assumptions': []})
        self.project.scaffold(1)
        self.source = ('#include <Arduino.h>\n' + '// declaration context\n' * 180
                       + 'void setup(){Serial.begin(115200);Serial.println("boot");}\nvoid loop(){}\n')
        self.project.write_files(2, {'src/main.cpp': self.source, 'README.md': 'fixture',
                                    'include/settings.h': 'constexpr int VALUE = 1;\n'})
        store = TaskStore(root / 'tasks')
        self.coordinator = Coordinator(store.create(self.project.id), store=store, project=self.project)
        self.coordinator.begin_turn('context fixture')
        self.tools = {t.name: t for t in make_coordinator_tools(self.coordinator)}
        self.evidence = {'step': 'build', 'report': {'verdict': 'fail',
                         'diagnostics': ['src/main.cpp:182:1: error: undeclared identifier']}}

    def test_source_line_range_has_exact_text_and_unambiguous_units(self):
        tool = self.tools['read_task_evidence']
        data = tool.invoke({'kind': 'source', 'ref': 'src/main.cpp',
                            'start_line': 30, 'end_line': 80})['data']
        self.assertEqual(data['content'], ''.join(self.source.splitlines(keepends=True)[29:80]))
        self.assertEqual((data['unit'], data['start_line'], data['end_line']), ('lines', 30, 80))
        self.assertEqual(data['next_start_line'], 81)
        self.assertEqual(data['line_character_counts'],
                         [len(s) for s in self.source.splitlines()[29:80]])
        wrong = tool.invoke({'kind': 'source', 'ref': 'src/main.cpp', 'offset': 110, 'limit': 70})
        self.assertEqual(wrong['error_code'], 'SOURCE_RANGE_REQUIRED')
        chars = tool.invoke({'kind': 'source', 'ref': 'src/main.cpp', 'source_unit': 'characters',
                             'offset': 110, 'limit': 70})['data']
        self.assertEqual(chars['content'], self.source[110:180])
        self.assertEqual(chars['unit'], 'characters')

    def test_source_reader_never_splits_lines_at_size_boundary(self):
        data = line_excerpt('aaa\nbbb\nccc\n', max_characters=6)
        self.assertEqual(data['content'], 'aaa\n')
        self.assertEqual(data['next_start_line'], 2)
        with self.assertRaises(WorkflowError):
            line_excerpt('x' * 100, max_characters=6)

    def test_normal_repair_includes_declarations_far_from_error(self):
        raw, excerpts, _, _ = prepare_repair(self.project, 3, self.evidence, reserved=False)
        self.assertEqual(excerpts['src/main.cpp'][0]['text'], self.source)
        self.assertIn('source_files', json.loads(raw))
        self.assertLessEqual(len(raw.encode()), limits.GENERATION_REPAIR_INPUT_BYTES)

    async def test_normal_repair_can_read_a_related_header_then_submit_one_batch(self):
        trace = GenerationTrace(self.coordinator, [BOARD])
        model = ReadThenRepairModel()
        version = await request_repair(trace, model, 'a' * 32, 3, self.evidence, reserved=False)
        self.assertEqual(version, 4)
        self.assertEqual(trace.metrics()['api_attempts'], 2)
        self.assertEqual(trace.metrics()['tokens_reported'], 24)
        self.assertEqual(self.project.read_file('include/settings.h')['content'], 'constexpr int VALUE = 2;\n')
        self.assertEqual(self.project.read_file('src/main.cpp')['content'], self.source)
        self.assertEqual(len([e for e in trace.events if e['kind'] == 'candidate_repair_applied']), 1)
        self.assertEqual(len([e for e in trace.events if e['kind'] == 'candidate_repair_read']), 1)

    async def test_repair_read_scope_and_request_count_remain_bounded(self):
        for mode, error in [('outside', 'REPAIR_SCOPE'), ('repeat', 'REPAIR_READ_LIMIT')]:
            with self.subTest(mode=mode):
                trace = GenerationTrace(self.coordinator, [BOARD])
                with self.assertRaises(WorkflowError) as caught:
                    await request_repair(trace, ReadThenRepairModel(mode=mode), 'a' * 32, 3, self.evidence, reserved=False)
                self.assertEqual(caught.exception.code, error)
                self.assertLessEqual(trace.metrics()['api_attempts'], limits.GENERATION_REPAIR_MODEL_CALLS)
                self.assertEqual(self.project.get()['version'], 3)

    async def test_invalid_patch_feedback_retries_without_partial_writes(self):
        trace = GenerationTrace(self.coordinator, [BOARD])
        version = await request_repair(trace, ReadThenRepairModel(mode='wrong_patch'), 'a' * 32,
                                       3, self.evidence, reserved=False)
        self.assertEqual(version, 4)
        self.assertEqual(trace.metrics()['api_attempts'], 2)
        feedback = [e for e in trace.events if e['kind'] == 'candidate_repair_feedback']
        self.assertEqual(feedback[0]['errors'][0]['code'], 'REPAIR_SCOPE')
        self.assertEqual(self.project.read_file('src/main.cpp')['content'],
                         self.source.replace('void loop(){}', 'void loop(){delay(1);}'))

    async def test_all_tool_calls_are_answered_for_parallel_reads_and_rejected_submissions(self):
        for mode in ('multi_read', 'multi_submit'):
            with self.subTest(mode=mode):
                version = self.project.get()['version']
                trace = GenerationTrace(self.coordinator, [BOARD])
                model = ReadThenRepairModel(mode=mode)
                revised = await request_repair(trace, model, 'a' * 32, version, self.evidence, reserved=False)
                self.assertGreater(revised, version)
                second_request = model._requests[1]
                self.assertEqual({c['id'] for m in second_request if isinstance(m, AIMessage) for c in m.tool_calls},
                                 {m.tool_call_id for m in second_request if isinstance(m, ToolMessage)})

    def test_idempotent_edit_does_not_discard_other_valid_edits(self):
        excerpts = {'src/main.cpp': [{'text': self.source}]}
        repair = GenerationRepair(edits=[
            {'path': 'src/main.cpp', 'old_text': 'void loop(){}', 'new_text': 'void loop(){}'},
            {'path': 'src/main.cpp', 'old_text': 'Serial.begin(115200)', 'new_text': 'Serial.begin(115200); delay(1)'}])
        files, errors = validate_repair_batch(self.project, 3, repair, excerpts, set())
        self.assertEqual(errors, [])
        self.assertIn('delay(1)', files['src/main.cpp'])
        self.assertEqual(self.project.get()['version'], 3)

    def test_registered_library_reference_is_never_an_edit_target(self):
        repair = GenerationRepair(edits=[{'path': 'lib/fixture/Api.h', 'old_text': 'old', 'new_text': 'new'}])
        _, errors = validate_repair_batch(self.project, 3, repair,
                                          {'lib/fixture/Api.h': [{'text': 'old', 'read_only': True}]}, set())
        self.assertEqual(errors[0]['code'], 'REPAIR_SCOPE')

    async def test_current_failed_build_is_reused_as_diagnostic_instead_of_recompiled(self):
        self.project.write_files(3, {'src/main.cpp': self.source.replace('"boot"', '"HWCLAW_BOOT"')})
        report = {'version': 4, 'verdict': 'fail', 'diagnostics': ['src/main.cpp:10:1: error: fixture']}
        atomic_json(self.project.meta / 'build.json', report)
        with patch('hardware_claw.adapters.compiler.compile_project', new_callable=AsyncMock) as compiler:
            result = await inspect_candidate(self.project, 4)
        self.assertEqual(result['step'], 'build')
        self.assertEqual(result['report'], report)
        compiler.assert_not_called()
