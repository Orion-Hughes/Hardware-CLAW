"""Stage-specific gates; a basic check never proves functional acceptance."""
VERSION = 2
STAGES = ("build", "simulation", "delivery")


def make_report(state, findings):
    stages = {stage: "fail" if any(stage in item["blocks"] for item in findings) else "pass"
              for stage in STAGES}
    return {
        "version": state["version"], "validator_version": VERSION,
        "verdict": "fail" if any(v == "fail" for v in stages.values()) else "pass",
        "stage_verdicts": stages, "issues": findings,
        "warnings": [item["message"] for item in findings if item["severity"] == "warning"],
        "unverified": [item["message"] for item in findings if item["severity"] == "unverified"],
        "scope": "basic_files_only",
        "note": "阶段pass只表示没有该阶段的静态阻断项；未确认项和功能验收不因此通过。",
        "build": "not_run", "simulation": "not_run", "behavior": "not_run",
    }


def allows(report, stage):
    return bool(isinstance(report, dict) and report.get("validator_version") == VERSION
                and report.get("stage_verdicts", {}).get(stage) == "pass")
