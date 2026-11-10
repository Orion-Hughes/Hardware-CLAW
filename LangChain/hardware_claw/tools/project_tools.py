"""Generation-facing project tools bound to a host-selected project.

Wokwi execution tools live in simulation_tools and are owned by the future
verification stage. Generation agents must not receive them by accident.
"""
import time
from langchain.tools import tool
from .hardware_catalog import _invalid_input
from ..projects.service import ProjectError
from .. import limits
from ..contracts.project import UpdateDesignInput, ReadFileRangeInput, WriteFilesInput, PatchInput, VersionInput


def compact_build(data):
    """Omit successful build chatter, never failure diagnostics or evidence identity."""
    if isinstance(data, dict) and data.get("verdict") == "pass" and "log_tail" in data:
        return {k: v for k, v in data.items() if k != "log_tail"} | {"log_tail_omitted": True}
    return data


def mutation_receipt(data):
    """Full immutable state is retained by ProjectService; avoid echoing design."""
    keys = ("project_id", "version", "design_version", "files_design_version", "files",
            "file_check", "build", "simulation", "behavior", "evaluation")
    return {k: compact_build(data[k]) if k == "build" else data[k] for k in keys if k in data} | {
        "details_tool": "get_project"}


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
    def receipt_with_gpio(data, *, full=False):
        receipt = mutation_receipt(data)
        if not any(f['path'] == 'diagram.json' for f in data['files']):
            return receipt
        report = project.gpio_map(data['version'])
        receipt['gpio_map' if full else 'gpio_map_ref'] = report if full else {
            k: report[k] for k in ('version', 'status', 'artifacts')}
        return receipt

    @tool
    def get_project() -> dict:
        """Read the bound project's requirements, design, version and file manifest.

        Includes a host-derived gpio_map from diagram.json and source-backed board pins.
        This is wire connectivity, not firmware validation. Call before writing;
        use its version as expected_version. No project path arguments.
        """
        def read():
            data = project.get()
            return data | {"build": compact_build(data.get("build")),
                           "gpio_map": project.gpio_map(data['version'])}
        return result(read)

    @tool(args_schema=UpdateDesignInput)
    def update_project_design(expected_version: int, design: dict) -> dict:
        """Save a simulation design with selected hardware, endpoints and dependencies.

        Read hardware details first. board_id automatically creates mcu; components
        contains peripherals ONLY, never a second mcu or board. instance_id is the
        endpoint prefix, hardware_id is the catalog ID. Submit the full design.
        Reject unsupported profiles, duplicate IDs, unknown pins and stale versions. dependencies
        only contains registry dependencies; resolution=local_bundle drivers are omitted and
        injected by the host. Changes invalidate prior file checks.
        """
        if hasattr(design, "model_dump"):
            design = design.model_dump()
        return result(lambda: receipt_with_gpio(project.update_design(expected_version, design)))

    @tool(args_schema=ReadFileRangeInput)
    def read_project_file(path: str, start_line: int = 1, end_line: int | None = None) -> dict:
        """Read an existing UTF-8 file within the bound project's files directory.

        Optional inclusive line range; default reads all. Returns full-file hash and
        version, total_lines and partial flag. Reuse current content; reread after changes.
        """
        def read():
            data = project.read_file(path)
            lines = data["content"].splitlines(keepends=True)
            if (end_line is not None and end_line < start_line) or start_line > max(1, len(lines)):
                raise ProjectError("INVALID_ARGUMENT", "行范围无效或起始行超过文件末尾。")
            end = min(end_line if end_line is not None else len(lines), len(lines))
            return data | {"content": "".join(lines[start_line-1:end]), "start_line": start_line,
                           "end_line": end, "total_lines": len(lines), "partial": start_line > 1 or end < len(lines)}
        return result(read)

    @tool(args_schema=WriteFilesInput)
    def write_project_files(expected_version: int, files: dict[str, str]) -> dict:
        """Write full text artifacts into the bound project and create an immutable revision.

        Save a design first. files is relative path -> full content. Use one batch for
        related files. Reject stale versions, external edits, paths outside files and scripts.
        In vscode projects, diagram.json, platformio.ini and wokwi.toml are host-owned:
        update the design and call scaffold_project instead. Model-authored files are normally
        src/main.cpp, README.md and additional headers/sources. Writing does not compile,
        execute or validate firmware.
        """
        return result(lambda: receipt_with_gpio(project.write_files(expected_version, files)))

    @tool(args_schema=PatchInput)
    def apply_project_patch(path: str, expected_version: int, old_text: str, new_text: str) -> dict:
        """Replace exactly one matching text span in a previously read project file.

        Creates a revision, rejects stale versions and ambiguous/missing old_text.
        This is literal replacement, not a shell command or unified-diff parser. Host-owned
        vscode configuration files cannot be patched; change the design and re-scaffold.
        """
        return result(lambda: receipt_with_gpio(project.patch_file(expected_version, path, old_text, new_text)))

    @tool
    def check_project_files() -> dict:
        """Check current artifacts deterministically: required files, diagram endpoints,
        design consistency, basic source declarations and supported build configuration.

        Also returns the program-generated GPIO wiring map, including mapping gaps.
        data.verdict=pass means ONLY basic files passed. It never compiles or simulates.
        Modifying design/files invalidates this version-bound report.
        """
        def check():
            report = project.check_files()
            return report | {'gpio_map': project.gpio_map(report['version'])}
        return result(check)

    @tool(args_schema=VersionInput)
    def scaffold_project(expected_version: int) -> dict:
        """For vscode projects, instantiate fixed platformio.ini/wokwi.toml/diagram.json
        from the saved design and read-only templates. Preserves business source/README and injects
        local driver bundles only in compile/export snapshots. Dependencies in platformio.ini are
        registry dependencies only. Returns a program-generated gpio_map; do not author a second pin-table format.
        Returns a program-generated gpio_map; do not author a second pin-table format.
        Call after update_project_design, then write src/main.cpp and README.md.
        """
        return result(lambda: receipt_with_gpio(project.scaffold(expected_version), full=True))

    @tool(args_schema=VersionInput)
    async def compile_project(expected_version: int) -> dict:
        """Actually compile a checked vscode revision using controlled PlatformIO.
        Returns verdict pass/fail/timeout and bounded diagnostics; never simulates.
        Fresh temporary build, shared deadline, kills children on cancellation.
        Fix errors then recheck before retrying; do not retry unchanged failed source.
        """
        from ..adapters.compiler import compile_project as compile_bound
        start = time.monotonic()
        try:
            data = compact_build(await compile_bound(project, expected_version))
            value = {"execution_status": "ok", "error_code": None, "data": data,
                     "summary": "编译执行完成，请读取verdict；仿真和行为未验证。", "retryable": False}
        except ProjectError as exc:
            value = {"execution_status": "error", "error_code": exc.code, "data": None, "summary": str(exc), "retryable": False}
        except (OSError, ValueError):
            value = {"execution_status": "error", "error_code": "COMPILER_IO_ERROR", "data": None, "summary": "编译文件操作失败。", "retryable": False}
        value["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
        return value

    @tool(args_schema=VersionInput)
    def export_project(expected_version: int) -> dict:
        """Export a revision-bound ZIP and manifest after the current basic file check passes.

        vscode requires compile_project pass and exports a ready-to-open simulation
        folder with actual firmware. Legacy modes export source only. Never simulates.
        Export only project artifacts, never keys,
        Python environments or chat logs. Returns archive path and SHA256.
        """
        return result(lambda: project.export(expected_version))

    tools = [get_project, update_project_design, scaffold_project, read_project_file, write_project_files, apply_project_patch, check_project_files, compile_project, export_project]
    for item in tools:
        item.handle_validation_error = _invalid_input
    return tools
