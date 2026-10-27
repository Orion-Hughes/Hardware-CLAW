# 正式生成程序：模块、工程布局与数据流

更新：2026-10-27。正式程序已接入15个工具，默认vscode模式交付可直接打开的simulation文件夹。持久化、修订、基础检查、编译、统一Wokwi CLI观察与导出已实现；单工程专用场景已删除，通用功能验收和真机验收未实现。禁止针对某个工程添加特殊优化文件或分支。当前结构以[自主仿真](AGENT_SIMULATION.md)、[VS Code交付](VSCODE_DELIVERY.md)和[工具实现状态](TOOLS_IMPLEMENTATION_STATUS.md)为准，以下未同步的“待实现”描述为此前规划。

## 1. 保留与扩展

- 保留 `LangChain/main.py`、兼容入口 `agent.py`、`hardware_claw/agent.py` 和独立 `api_config.py`。新增Chainlit app.py与共用runtime.py；按用户要求逐工具进行真实API验证，见API_TOOL_TEST_REPORT.md。
- 继续使用LangChain `create_agent` 的模型/工具循环。后续从当前agent.py拆出命令行与运行管理职责时，保留兼容入口；不另起一套通用Agent框架。
- ESP-Claw仅为学习与架构参考，不是运行依赖。Circuit Lab提供需求到文件集合的交互参考；第一版是可持续扩展的正式生成程序，单次Prompt方案只另作评估基线。
- 生成能力面向明确支持范围，不把DHT示例硬编码成唯一目标。DHT可作为首个用例；缺失资料必须报告或澄清，不能编造参数。

## 2. 模块边界

| 位置 | 职责 | 依赖方向与当前状态 |
|---|---|---|
| `main.py` / `hardware_claw/agent.py` | 用户输入、LangChain装配、流式输出；未来组织任务状态和退出 | 已接入真实硬件查询tools；查询阶段保持只读，工程生命周期待实现 |
| `hardware_claw/api_config.py` | 模型与凭据配置 | 现有；密钥不流入工程或通用文件工具 |
| `hardware_claw/tools/` | 对模型可见的薄接口、参数说明和结果包装 | hardware_catalog.py已实现search_hardware/get_hardware_info，原教学fixture保留 |
| `hardware_claw/catalog/` | 读取、检索、组合知识，保留来源和未知项 | service.py已实现本地查询、分页、引用约束与可选例程；不调用LLM，不联网 |
| `hardware_claw/projects/` | 工程创建、状态、文件操作、修订与导出 | 本轮建目录；模型不得直接改元数据和快照 |
| `hardware_claw/contracts/` | 小型输入输出契约与版本说明 | 本轮建目录；不是全局Project IR；后续实现类型/schema |
| `hardware_claw/harness/` | 路径、权限、预算、取消、超时和资源管理 | 已有预留；约束所有工具，不只验证工具 |
| `hardware_claw/adapters/` | 编译器、Wokwi、串口等外部程序适配 | 已有预留；将来复用/改造现有runner |
| `hardware_claw/validation/` | 文件结构检查、测试模板和确定性判定 | 本轮建目录；第一版先做工具参数/文件完整性检查，行为验证后续加入 |
| `prompts/` | 版本化生成角色、工具使用与交付提示词 | 本轮建目录；未接入，当前PROMPT仍在agent.py |
| `templates/` | 框架相关工程骨架、必需文件清单 | 本轮建目录；不预置未经验证的接线 |
| `knowledge/` / `skills/` | 器件事实及开发方法 | knowledge已接入查询Agent；skills仍待实现，与事实分开 |

依赖方向：入口/Agent → tools → catalog或projects或adapters/validation；上述实现共用contracts与harness。catalog不导入Agent，projects不请求模型，验证器不修改需求。

## 3. 一次正式生成任务的数据流

```text
用户需求
  → 运行管理：创建run_id、预算、取消信号
  → LangChain Agent：获取工具描述与生成提示词
  → 查询工具 → catalog → 本地知识 + 可追溯上游来源
  ← 可用硬件、引脚/驱动/模型约束、未知项
  → 明确需求与设计：目标、元件实例、信号/GPIO分配、依赖
  → 工程工具 → projects：创建project_id并保存设计版本
  → Agent依据同一设计生成源码、diagram和构建配置
  → 文件工具 → harness校验 → projects保存工作文件
  → 文件完整性检查 → 保存不可变修订 → 导出工程
  → 返回文件位置、说明、假设、生成状态和未运行的验证项
```

用户可以只提交一次需求；Agent内部可多轮查询和写文件。关键歧义进入needs_input并保存已有进度，继续输入时恢复项目；不能要求“永不提问”。第一版没有完整行为验收，但参数检查、目录边界、文件完整性和可信状态管理必须实现。

已支持显式创建/恢复工程与运行记录；网页用/new、/new-pio、/project，CLI用--new-project、--project。需求澄清专用状态机和崩溃自动恢复仍未实现。

## 4. 未来工程实例的固定布局

实际工程由入口调用ProjectService.create创建，不暴露同名tool让模型决定是否创建。以下是设计布局；实际实现将需求/设计/文件内容统一保存于.hwclaw/revisions/vNNNNNN/state.json，project.json保存当前版本指针；check.json与export.json记录版本化结果。完整实际树见TOOLS_IMPLEMENTATION_STATUS.md。

```text
workspace/<project_id>/
  files/                     Agent可通过受控文件工具修改的工程根
    diagram.json
    platformio.ini           按选用框架决定，不强制所有项目相同
    src/main.cpp             或Arduino工程的sketch.ino
    wokwi.toml
    README.md                用法、接线说明、依赖和已知限制
  .hwclaw/                   仅工程服务维护，普通文件工具不可写
    project.json             项目身份、状态、引用与版本
    requirements.json        原始需求、澄清、假设；变更有记录
    design.json              当前目标、元件实例、信号/GPIO分配、依赖
    revisions/<revision_id>/ 文件快照、哈希清单与对应设计版本
    runs/<run_id>/           正式运行摘要、脱敏事件、Token/耗时和工具记录
  exports/<revision_id>/     由导出服务写入的交付包和清单

evaluations/cases/<case_id>/ 受保护的验收条件和基准图
evaluations/results/<run_id>/ 正式评估结果与证据
temp/<project_id>/<run_id>/ 临时场景、构建缓存、调试与执行中间件
```

`files/`才是编译/Wokwi的工程根。适配器负责将固件、场景和基准图引用解析到正确位置，不能假设项目外层目录就是CLI工作目录。修订快照需同时绑定设计/需求版本；设计改变后旧文件不能继续被标记为最新可交付版本。

验收版本引用放project.json；具体验收标准在evaluations中，不能由修复Agent改宽。工作需求可以通过专门接口更新，已冻结验收的修改要单独记录新版本。

正式运行记录不是临时文件；原始调试中间件留temp，选定证据由执行器归档并引用。交付包只收纳目标工程文件和必要说明，不含密钥、软件环境、完整聊天或临时缓存。实际访问控制尚待实现，目录名称本身不提供隔离。

## 5. 最小数据契约

这些契约分别维护，不合并成强制全局IR；字段在实现时采用schema_version明确演进。

| 数据 | 关键字段/语义 | 谁可以修改 |
|---|---|---|
| RunContext | run_id、project_id（创建前可空）、模式、预算、deadline、取消标识 | 运行管理；不由模型直接传入任意路径或预算 |
| Requirements | 原始文本、澄清项、显式假设、需求版本、验收引用 | 需求管理接口；关键变化保留历史 |
| HardwareSelection | board/profile来源、component实例ID、逻辑信号、GPIO分配、驱动和模拟模型引用、未知项 | Agent提出，工程服务检查并版本化 |
| ProjectManifest | project_id、当前阶段、文件根、设计版本、latest_revision、验收引用 | projects服务 |
| ArtifactRevision | 文件清单/哈希、设计和需求版本、提示词/模型/知识版本 | 保存服务生成；不可原地覆盖 |
| ToolResult | execution_status、error_code、summary、data、artifact_refs、duration、retryable | 工具；实际测试结论放data.verdict |
| ValidationReport | artifact_revision、test_suite_revision、刺激、expected、observed、证据、模拟/墙钟耗时 | 后续执行器；先预留契约 |

逻辑信号分配是固件和diagram的共同依据；第一版采用生成上下文约束与基本一致性检查，不声称仅保存design.json就能自动保证所有源码正确。

## 6. 拟实现的工具目录

当前查询模式注册search_hardware/get_hardware_info/load_skill；绑定工程后再注册get_project/update_project_design/read_project_file/write_project_files/apply_project_patch/check_project_files/export_project。原get_board_info仅保留在历史文件/测试中。后续编译仿真工具不注册空函数。

| 组 | 工具 | 输入与输出重点 |
|---|---|---|
| 发现硬件 | search_hardware（已实现） | 名称、分类、范围、状态、分页 → 稳定ID及摘要；上游元数据不自动成为生成配置 |
| 硬件详情 | get_hardware_info（已实现） | ID → 本地配置和原始定义；按需读取公共规则/原始例程 |
| 开发参考 | load_skill | 开发方法按需读取；例程暂复用get_hardware_info，不另设tool |
| 工程生命周期 | get_project；创建为入口服务 | 程序创建并绑定工程；模型查看身份、阶段、需求与文件清单 |
| 更新设计 | update_project_design | 预期设计版本、明确字段 → 新设计版本、未解决项 |
| 文件操作 | read_project_file / write_project_files / apply_project_patch | 工程由运行上下文绑定，模型传files内相对路径/预期版本；文件清单由get_project返回 |
| 文件完整性 | check_project_files | project_id、模板/构建类型 → 必需文件、格式与引用问题；不是行为验收 |
| 保存交付 | export_project | 工程服务负责写入/修改/导出时的修订保存，不另暴露保存修订tool |
| 后续验证 | compile_project / simulate_project / evaluate_tests | 工件修订、测试集引用 → 结构化状态与证据 |

Tool schema不暴露任意主机路径、shell或密钥。工程由入口绑定；已检查路径穿越、符号链接/Windows junction、硬链接、大小和并发版本；同项目写入串行化，过期版本返回冲突。属于应用层约束，不是操作系统沙箱；崩溃自动恢复和外部编辑导入尚未实现。

## 7. 核心执行逻辑与后续修复

### 后续控制LangChain时必须应用的约定

1. 只有收到明确的新建生成任务才由入口创建project_id和run_id，写入workspace中的原始需求；启动空界面不创建空工程。继续已有工程时复用project_id，新建run_id。该工程服务尚未实现。
2. 运行上下文在程序侧绑定工程根、预算和取消信号。模型不决定任意主机路径；普通文件tool只能访问绑定工程的files目录，.hwclaw元数据由工程服务维护。
3. LangChain负责模型请求→工具执行→ToolMessage回填→模型继续。流式事件用于UI与脱敏日志，不在astream之外另写无界修复循环。资料在维护阶段准备，任务运行中不联网补硬件规格。
4. 工具执行成功与任务结论分开：execution_status=ok不代表generation_status可用，也不代表检查通过。失败结果提供稳定错误码、具体文件/端点及可修正信息。
5. 存在依赖的工具调用必须先后执行，同工程写入串行化并检查版本；修改文件后旧检查结果失效，检查与导出绑定当前修订。
6. 模型最终回答不决定交付成功。程序核对必需文件、当前修订的基础检查及导出结果；缺失则标记incomplete/failed。编译、仿真未运行继续记not_run。不得沿用当前教学代码“出现一次tool调用就成功”的判据。
7. 达到截止时间/调用预算、取消或出现阻塞时保存已有进度并退出。当前查询阶段已调整为6次模型调用、8次tool调用、180秒总时限、图步数24；单次API仍30秒且不自动重试。正式工程的进度持久化仍待实现，不取消预算上限。
8. 2026-10-27已注册hardware_catalog.HARDWARE_TOOLS并替换旧Prompt。主程序只判断工具请求已回填且出现最终回答来报告查询往返完成，不把它当回答正确性或工程交付成功的证明。

生成阶段建议：collecting → designing → generating → checking_files → generated；分支可进入needs_input、failed、cancelled、timed_out或budget_exceeded。文件检查失败可反馈修正格式，不等于已经接通编译/仿真纠错。

生成状态与验证结果分开：未运行的build/simulation/behavior明确为not_run；supported范围外为unsupported，证据不足为inconclusive。不能因模型发出最终消息或调用过一个tool就判定工程交付成功；后续必须由工程服务核对必需文件、修订和交付清单。

接入验证后仍使用同一个LangChain循环：验证某修订 → 返回证据 → Agent提出修改 → 新修订 → 对同一验收版本重测。增加检查点、有限修复策略和退出条件，不另写无界外层while。工具故障和设计错误分开，模拟时间上限之外必须有墙钟截止与进程树回收。

已有 `Wokwi/runner/run_wokwi_test.py` 提供编译/lint/场景执行及汇总的参考入口，本轮只静态阅读、未执行。它目前使用路径配置和较粗passed/failed汇总；接入前需审查受控路径、进程树取消、版本绑定和结果分类，不能直接开放给模型任意传参。

## 8. 实现顺序与完成判据

1. 实现projects与基础contracts/harness：能创建、读取、修改并保存完整工程；正确拒绝越界和过期写入。
2. 接入catalog与现有器件档案：可查真实资料并诚实返回unknown/not_found；不把教学fixture冒充采购板。
3. 编写并装配正式生成Prompt、工程模板与上述tools；保留原入口兼容，运行时明确模式。
4. 交付完整生成路径：一次需求可生成支持范围内的工程，具备版本、说明、日志和未验证状态；资料不足可恢复澄清，失败有可诊断结果。
5. 在同一工程/版本/反馈契约上接入现有runner的受控适配与测试模板，增加验证修复。

截至本轮，查询→设计→文件→基础检查→导出已经通过真实Agent组合测试，网页和CLI共用执行层。查询模式6次模型/16次工具/40图步；工程模式按用户要求20次模型/32次工具/128图步；总时限180秒。宿主根据当前修订、检查与ZIP哈希判交付，编译/仿真/行为保持not_run。下一阶段接入受控编译仿真，并优化反馈质量与Token成本。
