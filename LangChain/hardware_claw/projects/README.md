# 工程管理服务（预留）

负责project_id解析、项目状态、设计版本、files目录的读写、修订快照和交付导出。复用harness检查路径、权限与并发版本；不调用LLM。

未来工程采用 `workspace/<project_id>/{files,.hwclaw,exports}/`。普通文件工具只能操作授权files，元数据与快照由服务维护；目录本身不提供隔离。详细契约见 [程序设计](../../../docs/GENERATOR_ARCHITECTURE.md)。本轮未实现文件操作权限或持久化。
