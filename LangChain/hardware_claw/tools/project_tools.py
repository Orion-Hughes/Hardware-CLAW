"""Project tool closures bind a host-selected project, never model-selected paths."""
import time
import asyncio
from langchain.tools import tool
from .hardware_catalog import _invalid_input
from ..projects.service import ProjectError
from .. import limits
from ..contracts.project import UpdateDesignInput, ReadFileInput, WriteFilesInput, PatchInput, VersionInput


def result(operation):
    start = time.monotonic()
    try:
        data = operation()
        value = {"execution_status": "ok", "error_code": None, "summary": "工具操作完成；具体结论读取data中的verdict和scope。", "data": data, "retryable": False}
    except ProjectError as exc:
        value = {"execution_status": "error", "error_code": exc.code, "summary": str(exc), "data": None, "retryable": exc.code == "PROJECT_BUSY"}
    except (OSError, UnicodeError, ValueError):
        value = {"execution_status": "error", "error_code": "PROJECT_IO_ERROR", "summary": "工程文件操作失败，请检查本地工程。", "data": None, "retryable": False}
    value["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
    return value


def make_project_tools(project):
    simulation_calls = 0
    simulation_lock = asyncio.Lock()
    @tool
    def get_project() -> dict:
        """Read the bound project's requirements, design, version and file manifest.

        Call before writing; use its version as expected_version. No project path arguments.
        """
        return result(project.get)

    @tool(args_schema=UpdateDesignInput)
    def update_project_design(expected_version: int, design: dict) -> dict:
        """Save a simulation design with selected hardware, endpoints and dependencies.

        Read hardware details first. Board instance is mcu. Reject unsupported profiles,
        duplicate IDs, unknown pins and stale versions. Changes invalidate prior file checks.
        """
        if hasattr(design, "model_dump"):
            design = design.model_dump()
        return result(lambda: project.update_design(expected_version, design))

    @tool(args_schema=ReadFileInput)
    def read_project_file(path: str) -> dict:
        """Read an existing UTF-8 file within the bound project's files directory.

        Returns content, hash and current project version. Missing files are NOT_FOUND.
        """
        return result(lambda: project.read_file(path))

    @tool(args_schema=WriteFilesInput)
    def write_project_files(expected_version: int, files: dict[str, str]) -> dict:
        """Write full text artifacts into the bound project and create an immutable revision.

        Save a design first. files is relative path -> full content. Use one batch for
        related files. Reject stale versions, external edits, paths outside files and scripts.
        Writing does not compile, execute or validate firmware.
        """
        return result(lambda: project.write_files(expected_version, files))

    @tool(args_schema=PatchInput)
    def apply_project_patch(path: str, expected_version: int, old_text: str, new_text: str) -> dict:
        """Replace exactly one matching text span in a previously read project file.

        Creates a revision, rejects stale versions and ambiguous/missing old_text.
        This is literal replacement, not a shell command or unified-diff parser.
        """
        return result(lambda: project.patch_file(expected_version, path, old_text, new_text))

    @tool
    def check_project_files() -> dict:
        """Check current artifacts deterministically: required files, diagram endpoints,
        design consistency, basic source declarations and supported build configuration.

        data.verdict=pass means ONLY basic files passed. It never compiles or simulates.
        Modifying design/files invalidates this version-bound report.
        """
        return result(project.check_files)

    @tool(args_schema=VersionInput)
    def scaffold_project(expected_version: int) -> dict:
        """For vscode projects, instantiate fixed platformio.ini/wokwi.toml/diagram.json
        from the saved design and read-only templates. Preserves business source/README.
        Call after update_project_design, then write src/main.cpp and README.md.
        """
        return result(lambda: project.scaffold(expected_version))

    @tool(args_schema=VersionInput)
    async def compile_project(expected_version: int) -> dict:
        """Actually compile a checked vscode revision using controlled PlatformIO.
        Returns verdict pass/fail/timeout and bounded diagnostics; never simulates.
        Fresh temporary build, 420s deadline, kills children on cancellation.
        Fix errors then recheck before retrying; do not retry unchanged failed source.
        """
        from ..adapters.compiler import compile_project as compile_bound
        start = time.monotonic()
        try:
            data = await compile_bound(project, expected_version)
            value = {"execution_status": "ok", "error_code": None, "data": data,
                     "summary": "编译执行完成，请读取verdict；仿真和行为未验证。", "retryable": False}
        except ProjectError as exc:
            value = {"execution_status": "error", "error_code": exc.code, "data": None, "summary": str(exc), "retryable": False}
        except (OSError, ValueError):
            value = {"execution_status": "error", "error_code": "COMPILER_IO_ERROR", "data": None, "summary": "编译文件操作失败。", "retryable": False}
        value["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
        return value

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

    @tool(args_schema=VersionInput)
    def export_project(expected_version: int) -> dict:
        """Export a revision-bound ZIP and manifest after the current basic file check passes.

        vscode requires compile_project pass and exports a ready-to-open simulation
        folder with actual firmware. Legacy modes export source only. Never simulates.
        Export only project artifacts, never keys,
        Python environments or chat logs. Returns archive path and SHA256.
        """
        return result(lambda: project.export(expected_version))

    tools = [get_project, update_project_design, scaffold_project, read_project_file, write_project_files, apply_project_patch, check_project_files, compile_project, simulate_project, evaluate_tests, export_project]
    for item in tools:
        item.handle_validation_error = _invalid_input
    return tools
