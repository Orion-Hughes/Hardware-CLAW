# 工程管理服务

`service.py` 管理 project_id、项目状态、设计版本、files 读写及修订快照，检查路径、文件哈希和并发版本；不调用 LLM。

`scaffold.py` 生成受管配置，`gpio_map.py` 派生接线表，`vscode_delivery.py` 核对固件并导出，`source_context.py` 为诊断提供可续读源码。普通工具仅操作绑定工程的 files；元数据和快照由服务维护，这不是 OS 级沙箱。

实际路径和数据流见 [目录说明](../../../docs/guides/PROJECT_STRUCTURE.md)，交付边界见 [当前架构](../../../docs/architecture/OVERVIEW.md)。
