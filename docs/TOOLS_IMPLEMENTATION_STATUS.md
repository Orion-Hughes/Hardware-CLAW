# Hardware-CLAW 工具清单与实现状态

更新：2026-10-29。默认vscode模式已接入真实编译、Wokwi CLI/MCP观测及含固件文件夹交付；累计token预算已启用。单工程专用验收与业务模板已删除，通用功能验收尚未实现。详见[当前进度](CURRENT_STATUS.md)和[仿真工具与评估](AGENT_SIMULATION.md)，根目录AGENTS.md禁止项目特例优化。

## 1. 已实现并接入Agent的18个工具

| 工具 | 作用 | 实现位置 | 当前验证范围 |
|---|---|---|---|
| search_hardware | 从本地库存/上游索引发现元件 | tools/hardware_catalog.py → catalog/service.py | 原有离线测试、真实API；本轮与技能及设计流程联合使用 |
| get_hardware_info | 默认精简参数/驱动/引脚/模拟模型；full和sections按需读取 | 同上 | 保留状态/未知项/来源；错误字段返回合法分组；不是实物验证 |
| load_skill | 技能用途目录、包正文与登记参考资料分页 | tools/skills.py → skill_catalog.py → skills/<id>/SKILL.md | 自动发现、哈希、包边界与真实Agent加载；不可安装或修改技能 |
| get_driver_api | 精简分页索引、字面API检索、登记原文分页 | tools/driver_api.py → catalog/driver_api.py | 精确原文偏移/哈希，拒绝未登记路径；资料不代表运行验证 |
| load_template | 列出/读取只读平台配置 | tools/templates.py → templates/ | 白名单ID与SHA256；不提供专用业务示例 |
| scaffold_project | 从设计生成默认配置与电路图 | projects/scaffold.py | 自动串口连接；配置按含义检查；catalog/framework对应依赖 |
| compile_project | 编译当前build阶段允许的修订 | adapters/compiler.py、build_state.py | 真实PlatformIO、900秒时限、取消进程树、输入/环境身份、跨修订重复失败和有界环境重试 |
| simulate_project | 当前固件与电路的统一限时观察 | adapters/simulator.py | CLI、凭据隔离、30秒模拟/180秒墙钟、每轮最多10次，原始证据与哈希；无元件条件 |
| inspect_simulation | 官方MCP交互批次，自动关闭会话 | adapters/wokwi_mcp.py | 11个官方工具逐项实测；补丁版支持完整PNG；引脚仅数字电平，不测电压；详见WOKWI_MCP_INTEGRATION.md |
| read_simulation_evidence | 当前修订MCP证据分页读取 | 同上 | 哈希/修订检查、路径拒绝、分页测试与真实Agent回填 |
| evaluate_tests | 核验证据与报告执行状态、验收缺口 | validation/observation.py | 正常观察返回unsupported，功能未验证；不再使用专用预期和解析器 |
| get_project | 查看绑定工程、需求、设计、版本、文件及报告 | tools/project_tools.py → projects/service.py | 初始空工程、设计后、写入后、恢复工程的真实查询 |
| update_project_design | 保存选型、元件实例、端点、依赖、实现方案、假设 | 同上；contracts/project.py、projects/implementations.py | framework须引用登记API原文并保存哈希；拒绝未知端点、重复ID、blocked硬件及过期版本 |
| read_project_file | 读取files内文本与哈希 | 同上 | 不存在文件、越界拒绝、写入后读回；不开放任意文件系统 |
| write_project_files | 批量保存完整文本并创建修订 | 同上 | 真实写README及完整Arduino工程；版本冲突、批次校验、链接/路径/大小限制有离线测试 |
| apply_project_patch | 唯一old_text→new_text定点替换 | 同上 | 真实读→改→读；过期版本拒绝；不是任意Shell或模糊补丁 |
| check_project_files | 分级、分阶段基础文件与部分一致性检查 | tools/project_tools.py → validation/ | error/warning/unverified；build/simulation/delivery门槛；配置语义检查，源码扫描不能确认时保留未知 |
| export_project | 当前修订ZIP与哈希清单 | tools/project_tools.py → projects/service.py | 真实检查→导出；离线验证旧检查不能导出、包不含密钥/环境/日志 |

查询模式注册search_hardware/get_hardware_info/get_driver_api/load_skill/load_template；绑定工程后注册全部18个。execution_status表示工具是否正常执行；行为读取evaluate_tests的verdict。默认底层服务、CLI及网页/new均使用vscode。导出可含失败工程供调试，ready_for_vscode不是行为通过。

资料来源已切换至hardware_library：15条薄关联、146个上游模型定义、495份锁定原文。get_driver_api返回登记的原文及来源，不再依赖旧手写API操作摘要；详见[迁移与验证](HARDWARE_LIBRARY_MIGRATION.md)。

最新完整回归170项通过（41.101秒），其中新增23项通用审核机制测试；该离线改造阶段没有付费API。见[审核调整](REVIEW_POLICY_REFACTOR_20261029.md)。原始工具证据保留，模型消息视图仍主要按三轮取舍正文，按任务优先级保留尚未实现。此前电位器＋舵机两次真实测试在预算预检处停止，没有生成固件；[实验记录](CONTEXT_EFFICIENCY_TEST_REPORT_20261029.md)列出实际用量，不能外推表中的历史成功结果。

50万预算历史复测生成源码、执行两次失败编译与修改，最终达到20次模型调用上限；当时v6检查fail，无仿真交付，见[历史复测](AGENT_500K_RETRY_20261029.md)。随后在新审核机制下续接旧v6：编译pass、CLI到观察上限、第一次MCP取得部分观察、第二次MCP启动超时；仍在20次模型调用上限停止，未调用evaluate_tests/export_project，宿主打包出VS Code目录。32次工具请求，357.39秒，提供方输入406,009/输出2,907/总408,916 tokens；源码和旧证据未改，完整功能验收未完成。见[最新真实测试](AGENT_REVIEW_LIVE_TEST_20261029.md)。

## 2. 后续要实现的工具

### 官方MCP已接入，存在已确认的数据缺口

通过官方stdio MCP + Python SDK新增inspect_simulation和read_simulation_evidence。保留原simulate_project/evaluate_tests；新观测不冒充功能验收。11个官方工具、两个资源已实测，详细记录与边界见[官方MCP接入](WOKWI_MCP_INTEGRATION.md)。

状态、串口读写、控制、暂停/恢复/重启可用；VCD需接线分析仪。原版截图截断已通过通用MCP返回补丁修复；仍取决于模型framebuffer支持。pinRead明确只提供数字高低电平，不读取电压。官方对未知control也可能返回成功，宿主按统一知识库检查控制名和范围。完整波形分析和需求验收仍待实现。

### 观测之后：通用评估与修正（待实现）

需求→可核对的验收条件→选择观察手段与输入刺激→执行并保存证据→独立规则评估→模型提出有证据的修正→重编译及复测。

- 验收条件来自用户需求及可信规格，应在纠错前确定；用户改变需求时显式建立新版，不能为通过而削弱标准。
- 证据需绑定固件/电路版本、模拟时间、输入和采集方式；日志、单点引脚值、波形和图片的覆盖范围不同。缺少可靠观察时标记证据不足。
- 数值、逻辑和时序尽量采用可复用的确定性评估；复杂画面可辅助使用视觉模型，但不能把模型意见直接当成最终通过依据。
- 诊断与判定分开；修正需关联失败证据，重新构建并复测。设置调用/时间/token预算、最大修正次数和无进展停止条件。
- 不新增单工程专用技能、业务模板、固定预期、解析器或驱动补丁。测试参数由通用结构表达，不写成核心程序的案例特例。

以下名称是开发计划，不代表已经注册的工具。通用验收优先完善现有simulate_project/evaluate_tests；是否拆出新工具待接口设计，不以工具数量衡量完成度。

| 工具 | 输入/输出方向 | 现状与前置工作 |
|---|---|---|
| 通用需求验收机制（待设计） | 需求、可观察能力→经核对的验收计划与证据判定 | 尚未实现；禁止以专用驱动补丁、单工程固定场景替代 |
| detect_devices | 受控接口→串口/设备与识别置信度 | 真机阶段；不把串口名等同准确型号 |
| flash_firmware | 明确设备、固件修订和授权→烧录日志 | 真机阶段；不得用仿真基线直接保证N32R16V可烧录 |
| monitor_serial | 设备、波特率、受控时限→日志 | 真机阶段；串口锁、超时、取消与日志上限 |
| reset_device（按需） | 明确设备及授权→复位结果 | 尚未实现，是否单独暴露待真机流程决定 |
| estimate_edge_ai | 模型、MCU、运行时/量化方案→估算与假设 | 最终要求之一，尚未实现；需要实际资源资料和可验证的估算模型 |

`validate_connections`的基础端点/供电轨规则合并在check_project_files；这不等于完整电气验证。`list_files`合并到get_project；保存修订由写入服务自动完成。工程创建由入口服务完成。长任务的get_job_status/read_job_log/cancel_job待异步作业需求确定后再决定，不先增加空接口。

## 已注册的5个Skills

均在LangChain/skills/，由load_skill按ID读取。它们是我们程序的领域技能，不是Codex插件技能；技能提供指导，强制约束由工具与宿主实现。

| Skill ID | 文件 | 作用 |
|---|---|---|
| wokwi_generation | wokwi_generation/SKILL.md | 需求到工程的整体工具顺序、设计与文件一致性、交付流程 |
| hardware_selection | hardware_selection/SKILL.md | 查询资料、选型、适用范围、引脚与依赖设计 |
| firmware_and_observation | firmware_and_observation/SKILL.md | 固件入口、依据资料调用驱动、串口可观察性及错误处理原则 |
| build_and_delivery | build_and_delivery/SKILL.md | 脚手架、编译、有限修正、VS Code工程交付与范围说明 |
| simulation_feedback | simulation_feedback/SKILL.md | 通用限时观察、原始证据、诊断边界、停止条件及未验证声明 |

没有单工程专用skill或业务源码模板。当前唯一注册模板是esp32s3_vscode，仅为已支持平台的构建/串口/Wokwi配置，不代表任意板卡支持。

## ESP-Claw研究计划（历史记录，已完成源码调研）

调研结论见[技能、工具与Lua调研](ESP_CLAW_SKILLS_TOOLS_STUDY.md)，当前实现见[生成上下文与技能](GENERATION_CONTEXT_AND_SKILLS.md)。以下保留原计划，不表示这些功能仍未实现。

研究ESP-Claw如何约束和引导Agent完成ESP相关代码任务。用户观察其效果较好，研究目标是定位可复用机制，不能预设效果来自某个prompt。

先核实生成边界：模型究竟生成Lua应用/调用已有capability，还是生成底层驱动或可编译C/C++固件；哪些驱动和板级支持实际上已由开发者实现。不能把调用预置驱动等同于从零生成驱动。

按下列顺序跟踪源码和一次真实任务的数据流：

1. Core loop：消息构建、工具描述注入、工具调用与结果回填、结束条件、错误重试及预算。
2. Prompt：系统提示词、动态硬件/能力上下文、任务提示、是否包含示例；记录装配位置与生效时机。
3. Skills：发现、选择和加载方式，内容如何影响工具调用，是否按设备能力限制适用范围。
4. 执行边界：Lua、capability、已有驱动及固件之间的关系；生成内容如何保存、加载、执行。
5. 反馈：语法/执行错误和日志如何交回模型，怎样判断有效修改，如何停止无效循环。
6. 对照本项目：区分可迁移的通用机制、ESP-Claw运行环境特有条件和仍待验证的假设。

预期输出：带代码位置的调用流程、关键prompt/skill装配证据、输入输出示例和通用改进清单。只借鉴可泛化机制，不引入单工程特例。原记录仅为研究计划，未设置定时提醒；源码调研现已完成。

## 3. 实际数据流与目录

入口创建/恢复工程 → LangChain循环 → 查询/技能/配置模板 → 保存设计 → 脚手架 → 业务文件 → 基础检查 → 编译 → 统一仿真观察 → 核验证据并报告验收缺口 → 有依据的有限修正或导出。宿主核对版本、固件、证据及交付物，不依赖模型口头宣布通过。

```text
LangChain/
  app.py                       Chainlit适配
  main.py                      CLI入口
  hardware_claw/agent.py        工具与上下文中间件注册、预算
  hardware_claw/context.py      每轮工程摘要与技能目录
  prompts/                     固定规则与生成/查询模式
  hardware_claw/runtime.py      事件、取消、统计、宿主交付判定
  hardware_claw/contracts/project.py
  hardware_claw/projects/service.py
  hardware_claw/tools/{hardware_catalog,skills,project_tools}.py
  hardware_claw/validation/files.py
  skills/wokwi_generation/SKILL.md
workspace/<project_id>/
  files/                       工作文本工程
  .hwclaw/project.json         当前修订指针
  .hwclaw/revisions/vNNNNNN/state.json
                               需求、设计、知识快照/来源、文件内容的不可变修订
  .hwclaw/check.json            最近基础检查（绑定版本）
  .hwclaw/builds/<attempt>/result.json
                               每次编译的不可变结果，成功/失败均保留，身份匹配时复用
  .hwclaw/export.json           最近导出记录（绑定版本）
  .hwclaw/runs/<run_id>/run.json
                               问题、事件、状态、耗时和Token（项目模式）
  exports/vNNNNNN/{project.zip,manifest.json}
temp/project-service/          写入中间文件；不主动清理
temp/project-tests/            离线测试工程
temp/agent-tools-20261027/      逐工具真实API测试证据
```

需求和设计目前随同一个state.json快照保存，而非维护多份可能不同步的requirements.json/design.json。design仍是小型工程契约，不作为必须覆盖所有硬件的通用Project IR。

## 4. 使用与边界

网页：`/new 需求` 默认创建VS Code工程；`/new-pio 需求` 创建兼容PlatformIO源码工程；`/project ID` 恢复后可直接提出修改；`/query` 切回查询。普通咨询不会创建空工程。

CLI：`python main.py --new-project 名称 --template arduino --question "需求"`；恢复用`--project ID`，若要求完整交付可加`--require-delivery`。使用项目.venv解释器。

- Arduino布局：sketch.ino、diagram.json、libraries.txt、README.md。用于复制到Wokwi网页，不声称网页支持任意ZIP自动导入。
- PlatformIO布局：src/main.cpp、diagram.json、platformio.ini、wokwi.toml、README.md；配置绑定共享基线，固件不存在直到编译。构建缓存重定向属于后续编译适配器。
- 当前预算：查询每轮累计8万tokens、8次模型；工程每轮累计50万tokens、20次模型。发送前预估完整输入并预留输出额度，超额不请求；工具/图步/时间限制保留。单次API120秒，无自动重试；单次输出分别4096/16384 tokens。估算和计费边界见DEVELOPMENT_LIMITS.md。
- 工程创建、读写及导出由Python执行；模型没有任意Shell、密钥读取或项目外写入工具。
- 当前文件最多128个、单个256KiB、总计2MiB（以limits.py为准）；默认仅文本源码/配置/说明。外部直接修改files会报EXTERNAL_CHANGE，当前没有自动导入/合并外部修改功能。
- 每次写入需expected_version；同工程线程锁+进程文件锁；旧修订与旧ZIP保留。检测符号链接、junction和硬链接。这是应用层约束，不是抵御同机恶意进程竞争的操作系统沙箱。
- 停止会取消Agent后续执行；已经开始的短文件事务可能先完成，保存的进度保留。编译/仿真适配器执行超时与取消清理，不让子进程无限运行。
- 运行记录是本地项目记录，可能包含用户问题、源码和工具内容；不包含API请求头或原始SDK异常。分享工程使用导出包，不要盲目分享整个.hwclaw。
- 已实现本地累计token预算阻断；未实现需求澄清专用状态机和崩溃自动恢复。

## 5. 本轮暴露的真实问题

1. 一次批量文件生成有模型最终文本却没有有效写入调用，实际文件未生成，记录为失败。现在记录无法解析的工具参数；显式生成任务还必须由宿主检查当前版本的检查报告和真实ZIP，不以模型最终声明判成功。
2. 补丁测试曾完成操作后触发图步数上限。按模式调整有限预算后重测通过，没有删除上限。
3. 生成源码出现不存在的TempError类型，基础检查没有发现。核对本地DHTesp.h后通过Agent补丁修正为auto；未据此声称编译通过。说明后续compile_project是必要的独立证据。
4. 分文件写入能降低单次工具参数复杂度，但多轮历史累积导致输入Token明显上升。应后续比较批量写入、工具摘要与上下文压缩，不通过删减错误证据美化用量。

逐次调用的模型数、工具数、耗时、Token与异常见同目录API验证报告和temp中的原始事件。所有基础检查结果都不等于功能验证。
