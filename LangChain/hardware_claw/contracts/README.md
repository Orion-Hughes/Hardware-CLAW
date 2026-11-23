# 输入输出契约

`project.py` 定义工程设计的 Pydantic 模型，`verification.py` 定义规划契约，`simulation_mcp.py` 定义受控仿真操作参数。各模块分别维护，不建设强制全局 Project IR；主协调交接模型另外放在 `coordinator/contracts.py`。

字段以相应模型为准；校验覆盖软件输入结构，不证明硬件功能正确。权限和交接见 [当前架构](../../../docs/architecture/OVERVIEW.md)。
