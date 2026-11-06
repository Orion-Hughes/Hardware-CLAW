# Hardware-CLAW

电脑端嵌入式开发Agent：从需求生成固件和电路配置，通过编译、仿真与独立测试反馈进行有限修正。当前采用LangChain；ESP-Claw作为学习与架构参考，不是运行依赖。

当前约束：禁止为单个工程增加特殊优化文件或规则，详见[开发约束](AGENTS.md)。已删除单工程专用验收与业务模板；现在仿真统一采集日志，通用功能验收尚未实现，不能宣称功能通过。

## 当前进度（2026-11-05）

| 模块 | 状态 |
|---|---|
| 主协调Agent | 已实现任务状态、固定阶段委派、工程绑定与交付；网页用`/coordinator`进入 |
| 第一子Agent：选型 | 已实现硬件查询、兼容性判断、旧选型复用和结构化交接 |
| 第二子Agent：生成 | 已实现接线、固件、基础检查、编译、有限编译修正；真实测试已生成可在VS Code打开的工程 |
| 硬件资料读取 | 明确工具字段与mcu保留ID；缺项、可执行续读、累计读取状态已接入；默认56,000、最高120,000字符 |
| 仿真观测工具 | Wokwi CLI及官方MCP适配已有；不等于第三子Agent或通用功能验收已完成 |
| 第三子Agent：验证 | 已重建为FTA式只读规划器：提取需求→场景→逐例时间线→静态转换。摇杆与最新电位器测试已输出具体计划，仍有观察语义缺陷。尚不执行仿真或功能判定 |

2026-11-06更新：修复事件数量先报错、隐藏最终操作超限的问题；32项为本项目旧MCP封装限制，数值未改变。最新电位器计划7次调用、80,391 tokens，5个场景首次通过静态检查，未触发新修正反馈，不能据此证明修正成功率提升。见[本次修复、逐轮用量与计划问题](docs/AGENT3_COUNT_FEEDBACK_20261106.md)。

最新第三子Agent采用固定步骤，停止在具体计划；旧Agent3已备份并从开写前版本重建。两案例共四次真实规划尝试，43次API调用、538,105 tokens；最新摇杆计划9次调用、109,974 tokens，仍有时序与判据语义限制，不能当作已验收测试。见[实现与使用](docs/AGENT3_FTA_PLANNER.md)、[逐轮测试和限制](docs/AGENT3_FTA_TEST_RESULTS.md)。两个原测试工程及旧失败证据完整保留，未运行仿真。

历史两次相同摇杆＋屏幕任务均检查、编译、导出成功：各13次API调用，351,951和346,539 tokens；相对修改前单次558,568，平均降低37.5%。没有运行仿真，不能声称画面与交互已验收。当时测试采用临时100万token停止线，默认生成预算为8万。

2026-11-06预算更新：主协调模式每个任务累计上限为1,000,000 reported tokens，主Agent和三个子阶段共享，恢复任务不会重置。子阶段不再设更低的token门槛；调用次数、超时和无进展保护保留。按已返回用量拦截后续请求，最后一笔响应可能越过阈值。多任务实测见[100万预算测试记录](docs/AGENT_E2E_BUDGET_1M_20261106.md)。

2026-11-06后续更新：规划每场景事件上限24→32，MCP封装操作上限32→64（含等待），总计划等待仍为60秒。历史报告保留当时额度；最新配置、验证及实际仿真接入安排见[执行接入前检查点](docs/SIMULATION_EXECUTION_CHECKPOINT_20261106.md)。

生成阶段主要剩余成本是成功路径反复发送大段硬件资料。硬件设计/固件编写资料视图和阶段上下文切换已讨论，**尚未实现**。第三子Agent目前停在规划，下一步再决定计划语义检查与执行的接法；生成阶段历史结果见[进度与下一步](docs/PROGRESS_20261105.md)。

## 从这里开始

| 想找什么 | 入口 |
|---|---|
| 最新第三子Agent重建、具体计划和预算失败 | [只读规划器](docs/AGENT3_FTA_PLANNER.md) · [测试记录](docs/AGENT3_FTA_TEST_RESULTS.md) |
| 最新进度、两次对照用量与第三子Agent计划 | [2026-11-05进度](docs/PROGRESS_20261105.md) |
| 新主Agent、固定阶段与当前实现边界 | [主协调层说明](docs/COORDINATOR_IMPLEMENTATION.md) |
| 选型子Agent、阶段工具与真实测试 | [选型子Agent](docs/SELECTION_AGENT.md) · [测试报告](docs/SELECTION_AGENT_TESTS_20261102.md) |
| 已确认选型复用、兼容性检查与本次用量 | [增量选型测试与限制](docs/SELECTION_REUSE_TESTS_20261102.md) |
| 第二个子Agent：生成、编译与用量停止记录 | [生成Agent说明](docs/GENERATION_AGENT_20261102.md) |
| 项目目标、进度和下一步 | [项目计划](docs/HARDWARE_CLAW_PROJECT_PLAN.md) |
| Agent、tools、测试与反馈怎么设计 | [Core与Capabilities](docs/HARDWARE_CLAW_CORE_AND_CAPABILITIES.md) |
| 哪些工具已实现、接下来实现什么 | [完整工具清单与当前状态](docs/TOOLS_IMPLEMENTATION_STATUS.md) |
| 技能、只读模板与可直接打开的仿真文件夹 | [VS Code交付说明](docs/VSCODE_DELIVERY.md) |
| DHT22为何编译通过却读取失败 | [成功工程与Agent交付物CLI对照](docs/DHT22_SIMULATION_COMPARISON_20261027.md) |
| Agent怎样自主仿真、评估并定位问题 | [仿真与固定场景评估](docs/AGENT_SIMULATION.md) |
| 每次真实API验证的结果与成本 | [逐工具与综合测试记录](docs/API_TOOL_TEST_REPORT.md) |
| 文件该放哪里 | [目录与访问边界](PROJECT_STRUCTURE.md) |
| Git提交范围与GitHub同步 | [版本管理](docs/VERSION_CONTROL.md) |
| 正式生成程序怎么建设 | [模块、数据流、工程布局与工具契约](docs/GENERATOR_ARCHITECTURE.md) |
| 运行当前LangChain原型 | [开发软件说明](LangChain/README.md) |
| 现有Wokwi工程与执行脚本 | [仿真目录说明](Wokwi/README.md) |
| 上游原文、硬件连接层和资料读取 | [器件知识入口](LangChain/knowledge/README.md) |
| Wokwi兼容库的来源与信息范围 | [硬件资料库调研](docs/WOKWI_LIBRARY_SOURCE_SURVEY.md) |
| 已购硬件 | [库存记录](references/HARDWARE_INVENTORY.md) |
| Circuit Lab、circuit-synth、元件库与验证调研 | [本轮研究](references/research-20261026/README.md) |
| 原始资料与来源 | [资料索引](references/SOURCES.md) |
| ESP-Claw参考源码 | [参考仓库说明](references/projects/README.md) |
| 报销、汇报、学校项目要求 | [项目总体信息](项目总体信息/README.md) |

## 日常存放原则

- `docs/`：我们自己的设计与项目指导；`references/`：外部资料和研究记录。
- `LangChain/`：开发软件；`Wokwi/`：现有仿真实验，保留已用路径。
- `workspace/`：生成目标工程；`examples/`：审核参考；`evaluations/`：正式验收与评估证据。
- `temp/`：所有临时脚本、下载中间件、构建缓存和调试记录，按任务归组，不主动清空。
- `pio/`与`tools/`：现有工具链，路径已被工程引用，避免手工挪动。
- `.secrets/`：收纳根目录原有的独立密钥文件，忽略Git跟踪；程序使用的 `LangChain/DS_Api.txt` 仍保持原位。

目录存在不表示功能已完成；新增发现的脚本也不自动代表已经实测通过。整理详情和迁移表见 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)。
