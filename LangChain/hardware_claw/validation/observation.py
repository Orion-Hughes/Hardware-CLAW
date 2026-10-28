"""Report bounded simulator execution; no project-specific acceptance rules."""
from .. import limits

OBSERVATION = {
    "mode": "observation_v1",
    "simulation_timeout_ms": limits.SIMULATION_MS,
    "scope": "bounded simulation and raw log collection; no functional acceptance",
    "uncovered": ["需求符合性", "外设功能", "时序正确性", "真机电气正确性"],
}


def assess(record, serial, cli_log):
    execution = record["execution_verdict"]
    if execution == "timeout":
        verdict = "timeout"
    elif execution in {"tool_error", "cancelled", "log_limit"} or record["exit_code"] not in {0, 42}:
        verdict = "tool_error"
    else:
        verdict = "unsupported"
    return {
        "verdict": verdict,
        "reason": "当前仅采集仿真证据，尚无通用需求验收计划；不判定功能通过或失败。",
        "checks": [],
        "observations": {"serial_characters": len(serial), "cli_characters": len(cli_log),
                         "exit_code": record["exit_code"], "execution_verdict": execution},
        "scope": OBSERVATION["scope"], "uncovered": OBSERVATION["uncovered"],
        "full_project_acceptance": "not_evaluated",
    }
