# Hardware-CLAW 工具清单与实现状态

更新：2026-10-27。默认vscode模式已接入真实编译、统一Wokwi CLI限时观察及含固件文件夹交付。单工程专用验收与业务模板已删除，通用功能验收尚未实现。详见[仿真工具与评估](AGENT_SIMULATION.md)，根目录AGENTS.md禁止项目特例优化。

## 1. 已实现并接入Agent的15个工具

| 工具 | 作用 | 实现位置 | 当前验证范围 |
|---|---|---|---|
| search_hardware | 从本地库存/上游索引发现元件 | tools/hardware_catalog.py → catalog/service.py | 原有离线测试、真实API；本轮与技能及设计流程联合使用 |
| get_hardware_info | 参数、驱动、引脚、模拟模型、来源 | 同上 | 已查询DHT、板卡、屏幕与blocked/未知条目；不是实物验证 |
| load_skill | 列出/读取维护好的开发流程 | tools/skills.py → skills/wokwi_generation.md | 真实Agent联合搜索/详情查询通过；不可安装或修改技能 |
| load_template | 列出/读取只读平台配置 | tools/templates.py → templates/ | 白名单ID与SHA256；不提供专用业务示例 |
| scaffold_project | 从设计生成固定配置与电路图 | projects/scaffold.py | 自动串口连接；固定构建配置；真实Agent综合生成 |
| compile_project | 编译当前已检查修订 | adapters/compiler.py | 真实PlatformIO、420秒时限、取消进程树、源码/固件哈希绑定 |
| simulate_project | 当前固件与电路的统一限时观察 | adapters/simulator.py | CLI、凭据隔离、25秒模拟/90秒墙钟、每轮最多3次，原始证据与哈希；无元件条件 |
| evaluate_tests | 核验证据与报告执行状态、验收缺口 | validation/observation.py | 正常观察返回unsupported，功能未验证；不再使用专用预期和解析器 |
| get_project | 查看绑定工程、需求、设计、版本、文件及报告 | tools/project_tools.py → projects/service.py | 初始空工程、设计后、写入后、恢复工程的真实查询 |
| update_project_design | 保存选型、元件实例、端点、依赖、假设 | 同上；contracts/project.py | 查询真实资料后保存设计再读回；拒绝未知端点、重复ID、blocked硬件及过期版本 |
| read_project_file | 读取files内文本与哈希 | 同上 | 不存在文件、越界拒绝、写入后读回；不开放任意文件系统 |
| write_project_files | 批量保存完整文本并创建修订 | 同上 | 真实写README及完整Arduino工程；版本冲突、批次校验、链接/路径/大小限制有离线测试 |
| apply_project_patch | 唯一old_text→new_text定点替换 | 同上 | 真实读→改→读；过期版本拒绝；不是任意Shell或模糊补丁 |
| check_project_files | Python基础文件与部分一致性检查 | tools/project_tools.py → validation/files.py | 缺文件→Agent补齐→pass；错误GPIO定义、端点/连线不符、电源短接、依赖、配置检查 |
| export_project | 当前修订ZIP与哈希清单 | tools/project_tools.py → projects/service.py | 真实检查→导出；离线验证旧检查不能导出、包不含密钥/环境/日志 |

查询模式注册search_hardware/get_hardware_info/load_skill/load_template；绑定工程后注册全部15个。execution_status表示工具是否正常执行；行为读取evaluate_tests的verdict。默认底层服务、CLI及网页/new均使用vscode。导出可含失败工程供调试，ready_for_vscode不是行为通过。

## 2. 后续要实现的工具

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
| wokwi_generation | wokwi_generation.md | 需求到工程的整体工具顺序、设计与文件一致性、交付流程 |
| hardware_selection | hardware_selection.md | 查询资料、选型、适用范围、引脚与依赖设计 |
| firmware_and_observation | firmware_and_observation.md | 固件入口、依据资料调用驱动、串口可观察性及错误处理原则 |
| build_and_delivery | build_and_delivery.md | 脚手架、编译、有限修正、VS Code工程交付与范围说明 |
| simulation_feedback | simulation_feedback.md | 通用限时观察、原始证据、诊断边界、停止条件及未验证声明 |

没有单工程专用skill或业务源码模板。当前唯一注册模板是esp32s3_vscode，仅为已支持平台的构建/串口/Wokwi配置，不代表任意板卡支持。

## 下一次研究：2026-10-28（香港时间）

研究ESP-Claw如何约束和引导Agent完成ESP相关代码任务。用户观察其效果较好，研究目标是定位可复用机制，不能预设效果来自某个prompt。

先核实生成边界：模型究竟生成Lua应用/调用已有capability，还是生成底层驱动或可编译C/C++固件；哪些驱动和板级支持实际上已由开发者实现。不能把调用预置驱动等同于从零生成驱动。

按下列顺序跟踪源码和一次真实任务的数据流：

1. Core loop：消息构建、工具描述注入、工具调用与结果回填、结束条件、错误重试及预算。
2. Prompt：系统提示词、动态硬件/能力上下文、任务提示、是否包含示例；记录装配位置与生效时机。
3. Skills：发现、选择和加载方式，内容如何影响工具调用，是否按设备能力限制适用范围。
4. 执行边界：Lua、capability、已有驱动及固件之间的关系；生成内容如何保存、加载、执行。
5. 反馈：语法/执行错误和日志如何交回模型，怎样判断有效修改，如何停止无效循环。
6. 对照本项目：区分可迁移的通用机制、ESP-Claw运行环境特有条件和仍待验证的假设。

预期输出：带代码位置的调用流程、关键prompt/skill装配证据、输入输出示例和通用改进清单。只借鉴可泛化机制，不引入单工程特例。此次仅记录研究计划，未执行研究、未设置定时提醒。

## 3. 实际数据流与目录

入口创建/恢复工程 → LangChain循环 → 查询/技能/配置模板 → 保存设计 → 脚手架 → 业务文件 → 基础检查 → 编译 → 统一仿真观察 → 核验证据并报告验收缺口 → 有依据的有限修正或导出。宿主核对版本、固件、证据及交付物，不依赖模型口头宣布通过。

```text
LangChain/
  app.py                       Chainlit适配
  main.py                      CLI入口
  hardware_claw/agent.py        工具注册、Prompt、预算
  hardware_claw/runtime.py      事件、取消、统计、宿主交付判定
  hardware_claw/contracts/project.py
  hardware_claw/projects/service.py
  hardware_claw/tools/{hardware_catalog,skills,project_tools}.py
  hardware_claw/validation/files.py
  skills/wokwi_generation.md
workspace/<project_id>/
  files/                       工作文本工程
  .hwclaw/project.json         当前修订指针
  .hwclaw/revisions/vNNNNNN/state.json
                               需求、设计、知识快照/来源、文件内容的不可变修订
  .hwclaw/check.json            最近基础检查（绑定版本）
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

网页：`/new 需求` 创建Arduino工程；`/new-pio 需求` 创建PlatformIO工程；`/project ID` 恢复后可直接提出修改；`/query` 切回查询。普通咨询不会创建空工程。

CLI：`python main.py --new-project 名称 --template arduino --question "需求"`；恢复用`--project ID`，若要求完整交付可加`--require-delivery`。使用项目.venv解释器。

- Arduino布局：sketch.ino、diagram.json、libraries.txt、README.md。用于复制到Wokwi网页，不声称网页支持任意ZIP自动导入。
- PlatformIO布局：src/main.cpp、diagram.json、platformio.ini、wokwi.toml、README.md；配置绑定共享基线，固件不存在直到编译。构建缓存重定向属于后续编译适配器。
- 查询预算：6次模型、16次工具、40图步；工程模式按用户要求调整为20次模型、32次工具、128图步。总运行时限180秒；单次API30秒、无自动重试；输出上限分别1024/4096 tokens。
- 工程创建、读写及导出由Python执行；模型没有任意Shell、密钥读取或项目外写入工具。
- 文件最多32个、单个64000字节、总计256000字节；默认仅文本源码/配置/说明。外部直接修改files会报EXTERNAL_CHANGE，当前没有自动导入/合并外部修改功能。
- 每次写入需expected_version；同工程线程锁+进程文件锁；旧修订与旧ZIP保留。检测符号链接、junction和硬链接。这是应用层约束，不是抵御同机恶意进程竞争的操作系统沙箱。
- 停止会取消Agent后续执行；已经开始的短文件事务可能先完成，保存的进度保留。未调用编译/仿真，因此当前无需回收那些进程。
- 运行记录是本地项目记录，可能包含用户问题、源码和工具内容；不包含API请求头或原始SDK异常。分享工程使用导出包，不要盲目分享整个.hwclaw。
- 未实现需求澄清专用状态机、Token硬预算和崩溃自动恢复；不能将这些规划写成已经完成。

## 5. 本轮暴露的真实问题

1. 一次批量文件生成有模型最终文本却没有有效写入调用，实际文件未生成，记录为失败。现在记录无法解析的工具参数；显式生成任务还必须由宿主检查当前版本的检查报告和真实ZIP，不以模型最终声明判成功。
2. 补丁测试曾完成操作后触发图步数上限。按模式调整有限预算后重测通过，没有删除上限。
3. 生成源码出现不存在的TempError类型，基础检查没有发现。核对本地DHTesp.h后通过Agent补丁修正为auto；未据此声称编译通过。说明后续compile_project是必要的独立证据。
4. 分文件写入能降低单次工具参数复杂度，但多轮历史累积导致输入Token明显上升。应后续比较批量写入、工具摘要与上下文压缩，不通过删减错误证据美化用量。

逐次调用的模型数、工具数、耗时、Token与异常见同目录API验证报告和temp中的原始事件。所有基础检查结果都不等于功能验证。
