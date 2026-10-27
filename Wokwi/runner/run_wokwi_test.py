from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_NAME = "hwclaw-test.json"


class ConfigurationError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_from(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def load_manifest(target: Path) -> tuple[Path, Path, dict[str, Any]]:
    target = target.resolve()
    manifest_path = target / MANIFEST_NAME if target.is_dir() else target
    if not manifest_path.is_file():
        raise ConfigurationError(f"Test manifest not found: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read test manifest: {exc}") from exc

    if manifest.get("schema_version") != 1:
        raise ConfigurationError("Unsupported or missing schema_version; expected 1")

    return manifest_path, manifest_path.parent, manifest


def find_tools(workspace_root: Path) -> tuple[Path, Path]:
    pio = workspace_root / "tools" / "platformio-venv" / "Scripts" / "pio.exe"
    if not pio.is_file():
        found = shutil.which("pio")
        if not found:
            raise ConfigurationError("PlatformIO executable was not found")
        pio = Path(found)

    wokwi_found = shutil.which("wokwi-cli")
    if wokwi_found:
        wokwi = Path(wokwi_found)
    else:
        wokwi = Path.home() / ".wokwi" / "bin" / "wokwi-cli.exe"
    if not wokwi.is_file():
        raise ConfigurationError("Wokwi CLI executable was not found")

    return pio, wokwi


def run_stage(
    name: str,
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        exit_code: int | None = completed.returncode
        output = completed.stdout
        error = None
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        raw_output = exc.stdout or ""
        output = raw_output.decode("utf-8", "replace") if isinstance(raw_output, bytes) else raw_output
        error = f"Process timeout after {timeout_seconds} seconds"
    except OSError as exc:
        exit_code = None
        output = ""
        error = str(exc)

    return {
        "name": name,
        "status": "passed" if exit_code == 0 else "failed",
        "exit_code": exit_code,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "command": command,
        "output": output,
        "error": error,
    }


def artifact_info(path: Path) -> dict[str, Any]:
    exists = path.is_file()
    return {
        "path": str(path),
        "exists": exists,
        "size": path.stat().st_size if exists else None,
    }


def public_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result["status"],
        "project": result["project"],
        "failed_stage": result["failed_stage"],
        "duration_ms": result["duration_ms"],
        "result_file": result["result_file"],
        "stages": [
            {
                "name": stage["name"],
                "status": stage["status"],
                "exit_code": stage["exit_code"],
                "duration_ms": stage["duration_ms"],
            }
            for stage in result["stages"]
        ],
        "artifacts": result["artifacts"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build, lint, simulate, and report a Hardware-CLAW Wokwi project."
    )
    parser.add_argument(
        "target",
        help=f"Project directory or path to {MANIFEST_NAME}",
    )
    args = parser.parse_args()

    started = time.monotonic()
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "failed",
        "project": None,
        "manifest": None,
        "started_at": utc_now(),
        "finished_at": None,
        "duration_ms": None,
        "failed_stage": "configuration",
        "stages": [],
        "artifacts": [],
        "result_file": None,
        "error": None,
    }

    try:
        manifest_path, project_dir, manifest = load_manifest(Path(args.target))
        workspace_root = Path(__file__).resolve().parents[2]
        pio, wokwi = find_tools(workspace_root)

        result["project"] = str(project_dir)
        result["manifest"] = str(manifest_path)

        required = ["platformio.ini", "diagram.json", "wokwi.toml"]
        missing = [name for name in required if not (project_dir / name).is_file()]
        if missing:
            raise ConfigurationError(f"Missing project files: {', '.join(missing)}")

        simulation = manifest.get("simulation", {})
        scenario_value = simulation.get("scenario")
        if not scenario_value:
            raise ConfigurationError("simulation.scenario is required")
        scenario_path = resolve_from(project_dir, scenario_value)
        if not scenario_path.is_file():
            raise ConfigurationError(f"Scenario file not found: {scenario_path}")

        if not os.environ.get("WOKWI_CLI_TOKEN"):
            raise ConfigurationError("WOKWI_CLI_TOKEN is not set")

        artifact_config = manifest.get("artifacts", {})
        serial_log = resolve_from(
            project_dir,
            artifact_config.get("serial_log", "wokwi-serial.log"),
        )
        serial_log.parent.mkdir(parents=True, exist_ok=True)

        result_path = resolve_from(
            project_dir,
            manifest.get("result_file", "wokwi-result.json"),
        )
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result["result_file"] = str(result_path)

        build_config = manifest.get("build", {})
        build_stage = run_stage(
            "build",
            [str(pio), "run"],
            project_dir,
            int(build_config.get("timeout_seconds", 600)),
        )
        result["stages"].append(build_stage)

        if build_stage["status"] == "passed":
            lint_stage = run_stage(
                "lint",
                [str(wokwi), "lint", "."],
                project_dir,
                int(simulation.get("lint_timeout_seconds", 60)),
            )
            result["stages"].append(lint_stage)
        else:
            lint_stage = None

        if lint_stage and lint_stage["status"] == "passed":
            scenario_relative = scenario_path.relative_to(project_dir).as_posix()
            simulation_stage = run_stage(
                "simulation",
                [
                    str(wokwi),
                    "--timeout",
                    str(int(simulation.get("timeout_ms", 15000))),
                    "--scenario",
                    scenario_relative,
                    "--serial-log-file",
                    str(serial_log),
                    ".",
                ],
                project_dir,
                int(simulation.get("process_timeout_seconds", 90)),
            )
            result["stages"].append(simulation_stage)

        failed_stage = next(
            (stage["name"] for stage in result["stages"] if stage["status"] != "passed"),
            None,
        )
        result["failed_stage"] = failed_stage
        result["status"] = "passed" if failed_stage is None else "failed"

        artifact_paths = [serial_log]
        artifact_paths.extend(
            resolve_from(project_dir, value)
            for value in artifact_config.get("files", [])
        )
        result["artifacts"] = [artifact_info(path) for path in artifact_paths]

    except ConfigurationError as exc:
        result["error"] = str(exc)
    except Exception as exc:
        result["failed_stage"] = "internal"
        result["error"] = f"Unexpected runner error: {exc}"

    result["finished_at"] = utc_now()
    result["duration_ms"] = round((time.monotonic() - started) * 1000)

    result_file = result.get("result_file")
    if result_file:
        Path(result_file).write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(json.dumps(public_summary(result), ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
