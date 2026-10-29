# Hardware-CLAW

电脑端嵌入式开发Agent：从需求生成固件和电路配置，通过编译、仿真与独立测试反馈进行有限修正。当前采用LangChain；ESP-Claw作为学习与架构参考，不是运行依赖。

当前约束：禁止为单个工程增加特殊优化文件或规则，详见[开发约束](AGENTS.md)。已删除单工程专用验收与业务模板；现在仿真统一采集日志，通用功能验收尚未实现，不能宣称功能通过。

## 从这里开始

| 想找什么 | 入口 |
|---|---|
| 当前已完成什么、验证结果、预算和下一步 | [当前进度总览](docs/CURRENT_STATUS.md) |
| 资料读取优化、本次测试用量和验收缺口 | [上下文优化实验记录](docs/CONTEXT_EFFICIENCY_TEST_REPORT_20261029.md) |
| 项目目标、进度和下一步 | [项目计划](docs/HARDWARE_CLAW_PROJECT_PLAN.md) |
| Agent、tools、测试与反馈怎么设计 | [Core与Capabilities](docs/HARDWARE_CLAW_CORE_AND_CAPABILITIES.md) |
| 哪些工具已实现、接下来实现什么 | [完整工具清单与当前状态](docs/TOOLS_IMPLEMENTATION_STATUS.md) |
| 技能、只读模板与可直接打开的仿真文件夹 | [VS Code交付说明](docs/VSCODE_DELIVERY.md) |
| DHT22为何编译通过却读取失败 | [成功工程与Agent交付物CLI对照](docs/DHT22_SIMULATION_COMPARISON_20261027.md) |
| Agent怎样自主仿真、评估并定位问题 | [仿真观测与评估边界](docs/AGENT_SIMULATION.md) |
| 每次真实API验证的结果与成本 | [逐工具与综合测试记录](docs/API_TOOL_TEST_REPORT.md) |
| 文件该放哪里 | [目录与访问边界](PROJECT_STRUCTURE.md) |
| Git提交范围与GitHub同步 | [版本管理](docs/VERSION_CONTROL.md) |
| 正式生成程序怎么建设 | [模块、数据流、工程布局与工具契约](docs/GENERATOR_ARCHITECTURE.md) |
| 运行当前LangChain原型 | [开发软件说明](LangChain/README.md) |
| 现有Wokwi工程与执行脚本 | [仿真目录说明](Wokwi/README.md) |
| 当前硬件资料、上游API与仿真关联 | [硬件资料库](LangChain/hardware_library/README.md) |
| 资料库迁移与真实Agent验证 | [迁移记录](docs/HARDWARE_LIBRARY_MIGRATION.md) |
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
