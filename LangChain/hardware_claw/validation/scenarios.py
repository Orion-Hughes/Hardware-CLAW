"""Maintainer-owned acceptance contracts. No model-authored YAML or expected values."""
import json
import re
from ..projects.service import atomic_json, digest, fail

CONTRACT_ID = "dht22_serial_v1"
VALUES = [(24.0, 40.0), (30.0, 65.0), (24.0, 40.0), (24.0, 40.0)]
LINE_FORMAT = "Temperature: {t:.1f} C | Humidity: {h:.1f} %"
MEASUREMENT = re.compile(r"(?<![A-Za-z0-9_])Temperature:\s*(-?\d+(?:\.\d+)?)\s*(?:°|\\u00b0)?C\s*[|,]\s*Humidity:\s*(\d+(?:\.\d+)?)\s*%(?:RH)?(?=\s|Temperature:|$)")


def get_plan(project, state):
    """Freeze the contract on first simulation. Changing the design cannot select an easier test."""
    path = project.meta / "test_plan.json"
    if path.exists():
        plan = json.loads(path.read_text(encoding="utf-8"))
        if plan.get("contract_id") != CONTRACT_ID or plan.get("expected") != [list(v) for v in VALUES]:
            fail("TEST_PLAN_CHANGED", "冻结测试契约已变化，需维护者检查。")
        return plan
    sensors = [name for name, info in state.get("hardware", {}).items() if info["summary"]["part_type"] == "wokwi-dht22"]
    if len(sensors) != 1:
        return {"contract_id": None, "verdict": "unsupported", "reason": "当前行为场景仅支持恰好一个DHT22；不把启动检查当功能通过。"}
    plan = {"contract_id": CONTRACT_ID, "expected": VALUES, "scope": "DHT22 serial follows changed temperature/humidity; not full project acceptance",
            "serial_format": LINE_FORMAT, "simulation_timeout_ms": 25000,
            "uncovered": ["显示内容", "其他外设与业务逻辑", "精确采样周期", "真机电气正确性"]}
    atomic_json(path, plan)
    return plan


def scenario(state, plan):
    sensors = [name for name, info in state.get("hardware", {}).items() if info["summary"]["part_type"] == "wokwi-dht22"]
    if len(sensors) != 1:
        fail("TEST_TARGET_CHANGED", "冻结DHT22测试仍要求一个DHT22，不能通过删除器件绕过测试。")
    name = sensors[0]
    # JSON is valid YAML, and quoting instance IDs is handled by json.dumps.
    steps = []
    for index, (t, h) in enumerate(plan["expected"]):
        if index < 3:
            steps.extend([{"set-control": {"part-id": name, "name": "temperature", "value": t}},
                          {"set-control": {"part-id": name, "name": "humidity", "value": h}}])
        steps.append({"wait-serial": LINE_FORMAT.format(t=t, h=h)})
    return json.dumps({"name": CONTRACT_ID, "version": 1, "author": "Hardware-CLAW test harness", "steps": steps}, indent=2)


def assess(record, serial, cli_log, plan):
    """Evaluate actual serial bytes, not the CLI's echoed expected-text messages."""
    # Wokwi serial-log-file can concatenate matched messages without their line endings.
    # Parse complete measurement frames from the actual byte stream, not assumed lines.
    observed = [[float(m[1]), float(m[2])] for m in MEASUREMENT.finditer(serial)]
    errors = []
    for line in serial.splitlines():
        line = line.strip()
        if re.search(r"\b(?:ERROR|DHT_ERROR|TIMEOUT|PANIC|ABORT)\b|Guru Meditation", line, re.I):
            errors.append(line[:250])
    position, matched = 0, []
    for expected in plan["expected"]:
        found = None
        while position < len(observed):
            value = observed[position]
            position += 1
            if all(abs(a-b) <= 0.05 for a,b in zip(value, expected)):
                found = value
                break
        matched.append({"expected": list(expected), "matched": found is not None, "observed": found})
    ran = "Starting simulation" in cli_log
    success = record["exit_code"] == 0 and f"[{CONTRACT_ID}] Scenario completed successfully" in cli_log
    execution = record["execution_verdict"]
    if execution in {"cancelled", "tool_error", "log_limit"} or (not ran and execution != "timeout"):
        verdict = "tool_error"
    elif execution == "timeout":
        verdict = "timeout"
    elif errors:
        verdict = "fail"
    elif not success:
        verdict = "timeout" if record["exit_code"] == 42 else "fail"
    else:
        verdict = "pass" if all(item["matched"] for item in matched) else "fail"
    findings = []
    if errors:
        findings.append({"code": "FIRMWARE_REPORTED_ERROR", "evidence": errors[:6]})
    if not observed:
        findings.append({"code": "NO_MEASUREMENT", "message": "未捕获Temperature/Humidity读数；检查驱动、串口与输出协议，不能以CLI回显当实测。"})
    if observed and not all(x["matched"] for x in matched):
        findings.append({"code": "SENSOR_SEQUENCE_MISMATCH", "message": "实际读数没有按测试顺序覆盖变化和恢复。"})
    if not success and observed and all(x["matched"] for x in matched):
        findings.append({"code": "SCENARIO_NOT_COMPLETED", "message": "读数已出现，但固定串口协议或CLI执行未通过，检查场景日志。"})
    if verdict == "tool_error":
        findings.append({"code": "SIMULATOR_EXECUTION_ERROR", "message": "工具/网络/授权错误，不据此断言固件功能错误。"})
    return {"verdict": verdict, "checks": matched, "observed": observed[:30], "errors": errors[:8],
            "findings": findings, "scope": plan["scope"], "uncovered": plan["uncovered"],
            "full_project_acceptance": "not_evaluated"}
