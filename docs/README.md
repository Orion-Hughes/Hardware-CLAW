# 文档导航

当前基线：2026-11-08，选型 → 生成/编译（程序派生 GPIO 表）→ 只读测试规划。尚未接通自动仿真执行与功能纠错。旧报告的预算、工具数和状态仅对应当时版本。

## 当前指导

| 内容 | 入口 |
|---|---|
| 当前能力、使用、已知问题 | [根 README](../README.md)、[软件说明](../LangChain/README.md) |
| 文件位置与数据流 | [目录结构](../PROJECT_STRUCTURE.md) |
| Workspace 命名与清理 | [管理规则](WORKSPACE_MANAGEMENT.md)、[目录说明](../workspace/README.md) |
| 最终目标、导师要求 | [毕业设计计划](HARDWARE_CLAW_PROJECT_PLAN.md) |
| 阶段与工具范围 | [主协调层](COORDINATOR_IMPLEMENTATION.md)、[工具与技能](TOOLS_IMPLEMENTATION_STATUS.md) |
| 硬件资料 | [知识库](../LangChain/knowledge/README.md)、[读取服务](../LangChain/hardware_claw/catalog/README.md) |
| 当前硬件支持状态 | [活跃硬件支持矩阵](OWNED_HARDWARE_SUPPORT_MATRIX_20261109.md) |
| 子阶段实现 | [选型](SELECTION_AGENT.md)、[生成](GENERATION_AGENT_20261102.md)、[规划器](AGENT3_FTA_PLANNER.md) |
| GPIO 表与固定驱动版本 | [实现、测试与 Agent3 接入建议](GPIO_MAP_20261108.md) |
| Agent3 完整 IO 接线表 | [加入前后各两次真实对照](AGENT3_IO_TABLE_AB_20261108.md) |
| 当前版本检查点 | [宿主属性契约与本地驱动包](VERSION_CHECKPOINT_20261109.md) |
| 当前限制与下一步 | [预算](DEVELOPMENT_LIMITS.md)、[执行接入](SIMULATION_EXECUTION_CHECKPOINT_20261106.md) |
| 仿真接口边界 | [CLI](AGENT_SIMULATION.md)、[MCP](WOKWI_MCP_INTEGRATION.md) |
| 本次维护 | [修复、合并与测试](MAINTENANCE_MAIN_20261106.md) |
| 日常操作 | [版本管理](VERSION_CONTROL.md)、[会话管理](CHAT_HISTORY.md) |

## 历史证据与研究

日期命名的报告及原始失败引用保留，不为减少文件数量删除实验依据。

- [三组主协调测试](AGENT_E2E_BUDGET_1M_20261106.md)：历史两项交付、一项被换行校验阻塞；恢复结果另见维护报告。
- [规划测试](AGENT3_FTA_TEST_RESULTS.md)、[计划审阅](AGENT3_PLAN_REVIEW_20261106.md)、[数量反馈](AGENT3_COUNT_FEEDBACK_20261106.md)：对应当时配置。
- [旧 Agent3 备份](AGENT3_REBUILD_CHECKPOINT.md)、[2026-11-05 进度](PROGRESS_20261105.md)：版本演进和成本对照。
- [参考项目实现](FIRMWARE_TESTING_AGENT_WALKTHROUGH_20261105.md)、[仿真验证调研](SIMULATION_VERIFICATION_PROJECT_SURVEY_20261105.md)、[硬件库调研](WOKWI_LIBRARY_SOURCE_SURVEY.md)。
- `CONTEXT_OPTIMIZATION.md`、`GENERATOR_ARCHITECTURE.md` 和 Core/Capability 草案保留早期机制设计；当前状态以根 README、工具清单及代码为准。
- 2026-10 的 API、DHT、仿真报告对应旧流程，不能外推当前功能验收。

详细请求、响应和失败工程保存在本地 `temp/`、`workspace/`，不会整体提交 GitHub。
