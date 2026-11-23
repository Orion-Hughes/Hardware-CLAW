# 执行约束的位置

此包目前仅作历史预留，没有独立运行实现。不要据此认为路径限制、预算或资源回收尚未实现，也不要把它当成所有安全检查的实际入口。

现有约束分布在 `projects/service.py`（授权工程、路径、文件与版本）、`coordinator/` 和 `stages/common.py`（持久化预算、阶段及调用限制）、`adapters/`（超时、取消及子进程回收），统一参数在 `limits.py`。

权限校验不限于仿真；这些是应用级约束，不是 OS 级沙箱。当前行为见 [当前架构](../../../docs/architecture/OVERVIEW.md) 和 [运行限制](../../../docs/guides/DEVELOPMENT_LIMITS.md)，失败证据不能随缓存一起清除。
