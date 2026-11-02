"""Main agent exposes orchestration tools only; never child implementation tools."""
from pathlib import Path
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain.tools import tool

from .contracts import RunStageInput, DeliverInput
from .store import WorkflowError
from ..projects.service import ProjectError
from ..tools.hardware_catalog import _invalid_input
from .. import limits

PROMPT_PATH = Path(__file__).resolve().parents[2] / 'prompts/coordinator.md'


def _result(operation):
    try:
        return {'execution_status': 'ok', 'error_code': None, 'data': operation()}
    except (WorkflowError, ProjectError) as exc:
        return {'execution_status': 'error', 'error_code': exc.code, 'summary': str(exc), 'data': None}


def make_coordinator_tools(coordinator):
    @tool
    def get_task_state() -> dict:
        """Read task version, request, project revision, available stages and compact handoffs.

        Use before delegation. No raw hardware documents or source files are returned.
        Stage availability is real host registration, never inferred from the role name.
        """
        return _result(coordinator.state)

    @tool(args_schema=RunStageInput)
    async def run_stage(stage: str, objective: str, expected_task_version: int,
                        input_refs: list[str] | None = None, expected_project_version: int | None = None) -> dict:
        """Delegate a bounded task to selection, generation or verification.

        Only host-installed executors can run; there is no arbitrary spawn or prompt editing.
        Returns status, handoff_ref, task_version and blockers. STAGE_UNAVAILABLE means
        implementation is absent: report it and stop retrying. A returned report alone
        never proves hardware acceptance. Calls for the same task must be sequential.
        """
        try:
            data = await coordinator.run_stage(stage, objective, expected_task_version, input_refs, expected_project_version)
            return {'execution_status': 'error' if data['error_code'] else 'ok',
                    'error_code': data['error_code'], 'data': data}
        except (WorkflowError, ProjectError) as exc:
            return {'execution_status': 'error', 'error_code': exc.code, 'summary': str(exc), 'data': None}

    @tool(args_schema=DeliverInput)
    def deliver_project(expected_task_version: int, expected_project_version: int,
                        scope: str = 'checked_artifacts') -> dict:
        """Export only current, actually exportable project artifacts.

        checked_artifacts preserves all unverified/failed behavior labels. verified
        requires the host's current functional pass evidence. This tool neither
        creates nor repairs source files. No bound project means no delivery.
        """
        return _result(lambda: coordinator.deliver(expected_task_version, expected_project_version, scope))

    tools = [get_task_state, run_stage, deliver_project]
    for t in tools:
        t.handle_validation_error = _invalid_input
    return tools


class TaskBudgetMiddleware(AgentMiddleware):
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def before_model(self, state, runtime):
        self.coordinator.check_budget()


def build_coordinator(model, coordinator):
    return create_agent(model=model, tools=make_coordinator_tools(coordinator),
        system_prompt=PROMPT_PATH.read_text(encoding='utf8'),
        middleware=[TaskBudgetMiddleware(coordinator),
                    ModelCallLimitMiddleware(run_limit=limits.QUERY_MODEL_CALLS, exit_behavior='error'),
                    ToolCallLimitMiddleware(run_limit=limits.QUERY_TOOL_CALLS, exit_behavior='error')])
