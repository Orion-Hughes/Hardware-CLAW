# Hardware-CLAW 当前进度与下一步

更新：2026-10-29（香港时间）。本文件汇总当前实现和已有证据；具体工具、架构与实验记录见文末入口。历史计划中的旧状态不作为当前完成情况。

## 1. 当前目标

构建一个运行在电脑端的嵌入式开发Agent：接收需求，选择器件、设计连接、生成C/C++固件及完整Wokwi工程，再通过真实工具反馈进行有限修改。开发板最终独立运行生成的固件，不依赖持续和板上Agent聊天。

当前重点是提高通用生成功能的质量和成本可控性，随后完善独立验收。最终仍需覆盖真机上传/监控、Edge-AI部署建议、benchmark及毕业设计报告。多板卡支持是长期目标，当前构建基线仍为ESP32-S3。

ESP-Claw是Core Loop、capability/tool、skills和上下文组织的灵感来源，不是运行依赖；当前用LangChain的create_agent作为核心。项目设计JSON用于连接工具，不把Hardware Project IR作为项目核心或不可变格式。

## 2. 已接通的运行流程

```text
Chainlit网页 / CLI接收需求
  → 创建或恢复workspace内的工程；同一对话继续修改同一工程
  → System Prompt + 生成/查询Prompt + Context Provider
  → 模型消息视图：保留近期资料，旧大结果转可追溯回执；原始证据不变
  → token预算预检、模型/工具调用次数与超时约束
  → LangChain请求LLM
  → 按需查硬件、加载技能、读取上游API
  → 保存设计、生成配置与固件、检查、编译
  → Wokwi CLI观察 / 官方MCP交互取证
  → 工具结果回填；Agent可以继续修改，直到结束或预算阻断
  → 导出VS Code仿真文件夹、ZIP及运行记录
```

这条路径提供了反复观察和修改的执行能力，但尚未形成可靠的需求验收机制。模型能够继续改文件，不代表修正有效；工具返回ok、编译通过、ready_for_vscode都不能单独证明需求满足。

## 3. 现有模块

| 模块 | 当前实现 | 边界 |
|---|---|---|
| 交互 | Chainlit、CLI、聊天历史、同工程后续修改 | 最近完成问答进入下一轮；不是完整历史无限回传 |
| Agent核心 | LangChain循环、分模式Prompt、动态工程上下文、模型消息视图 | 仍需改进资料阶段收敛和诊断质量 |
| 工具层 | 18个已注册工具，结构化参数/返回、工程访问边界 | 查询模式只开放5个只读工具 |
| Skills | 5个技能包，目录发现、正文和参考资料按需加载 | 技能是指导，强制约束由宿主/工具执行 |
| 硬件资料库 | 上游原文、精简索引、字面API检索、本地薄关联、来源哈希 | 库中有条目不代表可生成或已实测 |
| 工程服务 | 设计、显式实现选择、不可变修订、当前状态及导出 | 仅宿主确认输入/环境身份匹配时可复用编译，标明原版本 |
| 检查与编译 | 分级/分阶段Python检查、配置语义核对、真实PlatformIO编译 | 基础检查不等于C++语义或电气验证 |
| 仿真观测 | CLI日志；MCP串口、控制、状态、引脚、截图/波形等 | 引脚仅数字电平；截图受模型支持限制，VCD需接入分析仪 |
| 功能评估 | evaluate_tests核验证据/执行状态并报告缺口 | 通用需求验收尚未实现，不会据观察就判功能通过 |
| Harness | 路径/修订/哈希校验、超时取消、成本预算、跨修订编译重试约束 | 已识别相同构建输入；通用语义无进展检测、崩溃恢复仍待完善 |

### 工具清单

| 分组 | 工具 |
|---|---|
| 资料与开发指导（5） | search_hardware、get_hardware_info、get_driver_api、load_skill、load_template |
| 工程设计与编辑（6） | get_project、update_project_design、scaffold_project、read_project_file、write_project_files、apply_project_patch |
| 检查和交付（3） | check_project_files、compile_project、export_project |
| 仿真与证据（4） | simulate_project、inspect_simulation、read_simulation_evidence、evaluate_tests |

### 技能清单

| Skill | 用途 |
|---|---|
| hardware_selection | 器件选型、适用范围、引脚及依赖 |
| firmware_and_observation | 查阅驱动API、固件结构、时序、错误处理与可观察性 |
| wokwi_generation | 设计、源码、电路与生成流程的一致性 |
| build_and_delivery | 构建、修正及VS Code交付 |
| simulation_feedback | 原始证据、诊断边界和停止条件 |

唯一注册的平台模板是esp32s3_vscode，用于构建/串口/Wokwi配置，不包含某个业务工程的答案。

## 4. 资料库的最新方案

默认读取`LangChain/hardware_library/`。旧`LangChain/knowledge/`已备份并隐藏，原文件保留，不作为默认回退。备份在`backups/knowledge-20261028T085405Z/`。

| 数据 | 内容 |
|---|---|
| catalog.json | 15条本地关联与146个上游模型定义的索引 |
| associations/ | 器件身份、库存、仿真信号映射、驱动及文档关联 |
| drivers/ | 原始library.properties、头文件、实现和例程入口，共10个描述 |
| upstream/及supplements/sources/ | 495份原始资料；sources.lock.json记录来源与哈希 |

Wokwi、Espressif部分来自官方；Adafruit部分来自库维护者；DHTesp、ESP32Servo为社区维护者来源，不能都称为芯片厂商官方API。这里的驱动API是固件调用库函数的接口，不是LLM在线服务API。

运行时只读已准备的原文，不临时联网补器件信息；缺失或哈希不符时明确失败。版本从library.properties派生，本地不再复制旧的手写初始化/操作摘要。仍需维护最小关联和平台适用范围，不能完全取消本地数据。

| 资料状态 | 当前条目 |
|---|---|
| documented_not_tested（10） | ESP32-S3、DHT22、WS2812灯环、SG90、摇杆、ST7789 240×240仿真版本、MPU6050、DS1307、HC-SR04、电位器 |
| blocked（4） | 已购ST7789 240×320屏、USB摄像头、驻极体咪头、8Ω/1W扬声器 |
| unreviewed（1） | SSD1306参考条目 |

MPU6050、DS1307、HC-SR04和电位器是新增的非采购资料关联。documented_not_tested是资料级状态；146个模型也不等于146种硬件已经可用。240×240仿真屏不代表已购240×320实物屏完成适配。

## 5. 已有验证结果

最新完整离线回归为170项通过（41.101秒），覆盖工具、工程服务、资料库、上下文投影、API检索、token预算及本次新增23项审核机制测试。495份上游原文通过锁定来源校验。

审核改造已实现：error/warning/unverified分级，build/simulation/delivery阶段门槛，配置语义检查，catalog/framework显式实现选择，编译复用及跨修订重复失败识别。已同步工具、Prompt、Skills和上下文；详见[审核调整](REVIEW_POLICY_REFACTOR_20261029.md)。改造本身的离线测试使用模型/编译进程替身，当时API调用0次；下述续接测试是之后单独进行的真实实验。

最近一次真实Agent续接测试复用ESP32-S3＋电位器＋SG90的旧v6。源码和电路未改，真实编译通过；CLI运行至30秒模拟观察上限，第一次MCP取得两端ADC/目标角度变化，中点和实际舵机动作未验证；第二次MCP自动启动等待45秒超时。最终达到20次模型调用上限，未调用evaluate_tests，runtime仍为error；宿主打包出含真实固件的VS Code仿真文件夹，交付检查和ZIP CRC通过。**可打开交付物已存在，完整功能验收未完成**。357.39秒，输入406,009、输出2,907，共408,916 tokens；20个响应均带usage，runtime仍保留usage_complete=false。详见[真实续接测试](AGENT_REVIEW_LIVE_TEST_20261029.md)。ESP32Servo包获取警告仍存在，Agent也未声明新的framework实现方案，不能声称这两项已得到端到端验证。

此前的50万预算实验生成源码和电路，v3/v5基础检查通过，两次编译因依赖未成功安装失败；最后改写为LEDC的v6被当时的固定驱动头文件检查拒绝。该次73.91秒、20次模型调用，输入329,478、输出7,155，共336,633 tokens，当时没有可启动simulation目录。见[历史复测](AGENT_500K_RETRY_20261029.md)。旧运行/修订记录保留，后续成功编译不改写当时的失败结论。

此前两次同工程测试共12次模型调用、25次工具请求、17.86秒；提供方报告输入152,230、输出2,046，共154,276 tokens。两次均被保守预算预检挡住，只保存设计v1。原始失败证据保留，见[上下文优化初次实验](CONTEXT_EFFICIENCY_TEST_REPORT_20261029.md)。

精简默认资料返回已经生效，旧记录离线回放的消息字符减少56.49%，但排除了系统提示词和工具Schema，不能当作实际token降幅。最新实验回放发现：第16、17次请求时第一份MCP观察仍完整，第18次前因超过三轮被省略，随后模型重读证据。下一步优先按任务、版本与未解决问题维护工作记忆，而非单纯增加历史轮数；具体方案尚未实现。

此前真实Agent实验使用ESP32-S3＋MPU6050＋DS1307。它确实读取了新库的原文、生成并自行修改工程、通过编译，并调用CLI/MCP观察；部分历史修订中可以看到模拟温度和角速度变化。但最终v16仍包含错误的RTC寄存器检查，误报有效时间，最后一次CLI仿真超时，运行达到模型调用上限而停止。

没有人工修补生成工程，失败修订和证据保留。旧实验说明资料入口到生成/执行的链路可用，不能证明当前流程最终功能正确或纠错稳定。

| 上次实验统计（旧预算） | 提供方/运行记录 |
|---|---|
| 模型 | 响应元数据为deepseek-flash |
| 模型调用 / 工具请求 | 60 / 71 |
| 总耗时 | 784.34秒 |
| 输入 / 输出 / 总tokens | 4,176,393 / 16,757 / 4,193,150 |
| 用量完整性 | usage_complete=false；只报告已返回统计 |
| 最终结果 | 编译pass；仿真timeout；行为未验收；宿主保留可打开的调试交付物 |

## 6. 当前成本限制

| 限制 | 工程模式 | 查询模式 |
|---|---|---|
| 每轮累计输入＋输出预算 | 500,000 tokens | 80,000 tokens |
| 单次输出上限 | 16,384 tokens | 4,096 tokens |
| 每轮模型调用上限 | 20 | 8 |

token预算预检在动态上下文及消息视图形成后、请求发送前执行，计入聊天协议输入、工具Schema、此前工具结果及输出，不计本地LangChain用量/追踪元数据；缓存命中也计入。先保守估算并预留，收到有效usage后校正。信息缺失/异常不按零消耗处理，不会自动追加额度。

每条用户消息是新一轮预算，并非整个聊天或账户累计限额。本地估算可能提前停止，不是服务端人民币账单硬限制。达到限制保留已生成文件，不宣称任务完成。单次输出保留较大额度，是为了方便写完整代码，控制重点放在累计总量。

## 7. 当前主要问题与建议顺序

| 顺序 | 工作 | 需要看到的证据 |
|---|---|---|
| 1 | 扩展Context Provider，按任务、证据及版本优先级组织工作记忆 | 未解决观察不因轮次变旧而丢失；可跨用户回合续接；离线回放核对保留内容，真实成本收益仍待测量 |
| 2 | 改善通用生成与诊断：先依据正式API，诊断有证据；核对基础检查器的误报 | 用不同器件组合验证，不加入工程特例、不手工修生成结果 |
| 3 | 核对构建包映射与显式实现选择；澄清MCP启动、错误和时间语义 | 旧v6可编译交付，但依赖获取/方案选择未实测解决；观察需对应新模拟采样，保留超时根因 |
| 4 | 在现有小预算下重新测多种任务 | 分别记录首次编译率、最终行为、调用量、耗时和预算退出；失败照实保留 |
| 5 | 建设通用需求验收，再闭合可靠纠错 | 需求→验收条件→刺激/观察→独立判定；同时测错误检出与正确结果误报 |
| 后续 | 多板卡、真机工具、Edge-AI、正式benchmark | 对应工具和真实数据验证，避免只增加目录或接口名称 |

精简索引、字面API检索、确定性消息视图及相同编译输入的跨修订停止已实现；按任务优先级管理历史、跨轮工作记忆、额外LLM摘要、动态工具组和更广泛的语义无进展检测仍未实现。当前有执行循环，不等于已经有可靠的验收和修正闭环。应先提高生成功能本身，再让验证承担独立核对职责。

导师提出的方向继续保留：评价包含token和时间；可用不同LLM做交叉审查，但不替代真实工具证据；最终综合演示可考虑板间通信；Harness必须防止无界循环、死锁和无法退出的验证。

## 8. 文件与阅读入口

| 位置 | 作用 |
|---|---|
| LangChain/hardware_claw/ | Agent核心、上下文、预算、tools、资料读取、工程服务和适配器 |
| LangChain/prompts/、skills/、templates/ | 系统/模式提示词、技能包、只读平台模板 |
| LangChain/hardware_library/ | 当前硬件资料入口 |
| workspace/<工程ID>/files/ | 生成工程的工作文件 |
| workspace/<工程ID>/.hwclaw/ | 设计/修订、编译/仿真证据及运行统计 |
| workspace/<工程ID>/exports/ | VS Code交付目录和ZIP |
| docs/ | 项目指导与实验报告 |
| references/ | 外部研究与ESP-Claw参考源码 |
| temp/、backups/ | 临时证据/缓存与旧库备份，不提交Git |

当前服务健康检查通过，访问`http://127.0.0.1:8000`；日常使用Start-Agent.cmd/Stop-Agent.cmd。近期实现仍有本地未提交内容，本次整理不提交或推送Git，也不清理生成工程和失败证据。

- [全部工具和技能状态](TOOLS_IMPLEMENTATION_STATUS.md)
- [总体毕业设计要求](HARDWARE_CLAW_PROJECT_PLAN.md)
- [架构与数据流](GENERATOR_ARCHITECTURE.md)
- [上下文和技能实现](GENERATION_CONTEXT_AND_SKILLS.md)
- [资料精简与本次失败测试](CONTEXT_EFFICIENCY_TEST_REPORT_20261029.md)
- [50万预算复测与依赖阻碍](AGENT_500K_RETRY_20261029.md)
- [审核分级、实现选择与编译复用](REVIEW_POLICY_REFACTOR_20261029.md)
- [审核调整后的真实续接测试](AGENT_REVIEW_LIVE_TEST_20261029.md)
- [新资料库说明](../LangChain/hardware_library/README.md)
- [迁移及真实Agent失败记录](HARDWARE_LIBRARY_MIGRATION.md)
- [预算规则与计费边界](DEVELOPMENT_LIMITS.md)
- [官方MCP能力与限制](WOKWI_MCP_INTEGRATION.md)

所有工作继续遵守[AGENTS.md](../AGENTS.md)：禁止工程特例优化；不手工修补生成结果冒充成功；资料有来源；API调用报告用量；临时文件集中到temp。
