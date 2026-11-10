"""Wokwi execution tools reserved for the verification stage.

No current stage registers these tools. Keep this module separate from generation
tools so a generation agent cannot spend Wokwi CI quota accidentally.
"""
import asyncio

from langchain.tools import tool

from .hardware_catalog import _invalid_input
from .project_tools import result
from .. import limits
from ..contracts.project import VersionInput
from ..contracts.simulation_mcp import InspectSimulationInput, ReadSimulationEvidenceInput
from ..projects.service import ProjectError


def make_simulation_tools(project):
    """Build disabled-by-policy Wokwi tools for a future verification executor."""
    simulation_calls = 0
    simulation_lock = asyncio.Lock()

    @tool(args_schema=VersionInput)
    async def simulate_project(expected_version: int) -> dict:
        """Run real Wokwi CLI on the current compiled vscode revision. No arbitrary
        commands, credentials, expected outputs or YAML arguments. Collects raw serial
        and CLI logs without requiring a particular component or output format.
        No functional acceptance is implemented. Call evaluate_tests to report this gap.
        Bounded by the shared development budgets; no unlimited execution.
        """
        from ..adapters.simulator import simulate
        nonlocal simulation_calls
        async with simulation_lock:
            if simulation_calls >= limits.SIMULATION_CALLS:
                return {"execution_status": "error", "error_code": "SIMULATION_BUDGET", "summary": f"本轮仿真预算{limits.SIMULATION_CALLS}次已用完，停止修正并报告证据。", "data": None}
            simulation_calls += 1
            try:
                data = await simulate(project, expected_version)
                return {"execution_status": "ok", "error_code": None, "summary": "仿真执行记录已返回；需evaluate_tests判定行为。", "data": data}
            except ProjectError as exc:
                return {"execution_status": "error", "error_code": exc.code, "summary": str(exc), "data": None}
            except (OSError, ValueError):
                return {"execution_status": "error", "error_code": "SIMULATOR_IO_ERROR", "summary": "仿真文件或进程操作失败。", "data": None}

    @tool(args_schema=VersionInput)
    def evaluate_tests(expected_version: int) -> dict:
        """Verify current evidence identity and report execution status and coverage gap.
        No functional acceptance rules are implemented: normal observation returns
        unsupported, never pass. Infrastructure failures return timeout/tool_error.
        Raw logs may support diagnosis, but do not establish requirements compliance.
        """
        from ..adapters.simulator import evaluate
        return result(lambda: evaluate(project, expected_version))

    @tool(args_schema=InspectSimulationInput)
    async def inspect_simulation(expected_version: int, actions: list) -> dict:
        """Interact with official Wokwi MCP on current checked and compiled firmware.

        Each call starts an independent simulation, executes actions sequentially, then
        closes the server. Use status/read_serial/read_pin/set_control, pause (stop),
        resume/restart, screenshot or VCD; use official wokwi_ operation names.
        Host binds paths; no SD card/custom chip filesystem access. wait is wall time.
        read_pin ONLY reads digital high/low: cannot measure voltage, ADC or PWM.
        Complete PNGs require the installed generic upstream MCP patch; stock CLI
        0.29.0 truncates images. Screenshot support depends on the display model. VCD requires
        a wired logic analyzer. No full functional acceptance. Raw evidence is saved.
        This supplements simulate_project/evaluate_tests, does not replace their reports.
        """
        from ..adapters.wokwi_mcp import inspect
        nonlocal simulation_calls
        async with simulation_lock:
            if simulation_calls >= limits.SIMULATION_CALLS:
                return {"execution_status": "error", "error_code": "SIMULATION_BUDGET", "summary": "本轮仿真预算已用完。", "data": None}
            simulation_calls += 1
            try:
                data = await inspect(project, expected_version, actions)
                return {"execution_status": "ok", "error_code": None, "summary": "读取data.execution_status及逐项status；不代表功能验收通过。", "data": data}
            except ProjectError as exc:
                return {"execution_status": "error", "error_code": exc.code, "summary": str(exc), "data": None}
            except (OSError, ValueError):
                return {"execution_status": "error", "error_code": "MCP_IO_ERROR", "summary": "MCP配置或证据操作失败。", "data": None}

    @tool(args_schema=ReadSimulationEvidenceInput)
    def read_simulation_evidence(expected_version: int, attempt: str, filename: str, offset: int = 0, limit: int = 4000) -> dict:
        """Read a page of saved MCP JSON/serial response, server log or VCD waveform.
        PNG filenames return verified image path and dimensions, not base64 text.

        Use attempt and filenames from inspect_simulation. Verifies current version,
        firmware/circuit identity and file hash. Follow next_offset to read all pages.
        No arbitrary paths; old evidence remains on disk but cannot validate new firmware.
        """
        from ..adapters.wokwi_mcp import read_evidence
        return result(lambda: read_evidence(project, expected_version, attempt, filename, offset, limit))

    tools = [simulate_project, evaluate_tests, inspect_simulation, read_simulation_evidence]
    for item in tools:
        item.handle_validation_error = _invalid_input
    return tools
