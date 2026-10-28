"""Host-bound MCP actions. Never expose server filesystem arguments to the model."""
from typing import Literal
from pydantic import Field, model_validator
from .project import StrictModel


OPERATIONS = ("wokwi_start_simulation", "wokwi_stop_simulation", "wokwi_resume_simulation",
              "wokwi_restart_simulation", "wokwi_get_status", "wokwi_write_serial",
              "wokwi_read_serial", "wokwi_read_pin", "wokwi_set_control",
              "wokwi_take_screenshot", "wokwi_export_vcd", "wait", "read_resource")


class MCPAction(StrictModel):
    operation: Literal[*OPERATIONS]
    arguments: dict = Field(default_factory=dict, description="read_pin: partId/string, pin/string（数字脚也传字符串）；set_control: partId/string, control/string, value/number；take_screenshot: partId/string；write_serial: text/string；read_serial: clear/bool可选；wait: milliseconds/int；read_resource: name=diagram.json或wokwi.toml。其他操作传{}。禁止projectPath、sdcard、sdcardOut、outputPath，路径由宿主绑定。")

    @model_validator(mode="after")
    def validate_arguments(self):
        fields = {
            "wokwi_write_serial": {"text": str}, "wokwi_read_serial": {"clear": bool},
            "wokwi_read_pin": {"partId": str, "pin": str},
            "wokwi_set_control": {"partId": str, "control": str, "value": (int, float)},
            "wokwi_take_screenshot": {"partId": str}, "wait": {"milliseconds": int},
            "read_resource": {"name": str},
        }.get(self.operation, {})
        if set(self.arguments) - set(fields):
            raise ValueError("Unsupported arguments; filesystem paths are host-bound")
        required = set(fields) if self.operation != "wokwi_read_serial" else set()
        if required - set(self.arguments):
            raise ValueError("Missing required arguments")
        for key, value in self.arguments.items():
            allowed = fields[key] if isinstance(fields[key], tuple) else (fields[key],)
            if type(value) not in allowed:
                raise ValueError("Invalid argument type")
            if isinstance(value, str) and (len(value) > (4096 if key == "text" else 128) or "\x00" in value):
                raise ValueError("Argument too long or contains NUL")
        if self.operation == "wait" and not 0 <= self.arguments["milliseconds"] <= 10000:
            raise ValueError("wait must be 0..10000 milliseconds")
        if self.operation == "read_resource" and self.arguments["name"] not in {"diagram.json", "wokwi.toml"}:
            raise ValueError("Only registered project resources may be read")
        if self.operation == "wokwi_set_control":
            import math
            if not math.isfinite(self.arguments["value"]):
                raise ValueError("Control value must be finite")
        return self


class InspectSimulationInput(StrictModel):
    expected_version: int = Field(ge=0)
    actions: list[MCPAction] = Field(min_length=1, max_length=32, description="单次独立MCP会话：宿主自动启动，依次执行动作，最后关闭。跨调用不保留仿真状态。")

    @model_validator(mode="after")
    def wait_budget(self):
        if sum(a.arguments["milliseconds"] for a in self.actions if a.operation == "wait") > 60000:
            raise ValueError("Total explicit wait exceeds 60 seconds")
        return self


class ReadSimulationEvidenceInput(StrictModel):
    expected_version: int = Field(ge=0)
    attempt: str = Field(pattern=r"^[a-f0-9]{32}$")
    filename: str = Field(pattern=r"^[a-z0-9-]+\.(json|log|vcd)$", description="inspect_simulation.evidence_sha256中登记的文件名。")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=4000, ge=1, le=16000)
