# Hardware-CLAW 项目目录

更新日期：2026-10-27。已实现Chainlit前端、共用runtime、10个工具、工程服务、小型契约与基础检查。最新实际目录及状态见 [TOOLS_IMPLEMENTATION_STATUS.md](docs/TOOLS_IMPLEMENTATION_STATUS.md)；以下原目录准备记录仍保留作历史。导航入口为 [README.md](README.md)，程序数据流与契约见 [GENERATOR_ARCHITECTURE.md](docs/GENERATOR_ARCHITECTURE.md)。

```text
Hardware_CLAW/
├─ README.md                     总导航
├─ PROJECT_STRUCTURE.md
├─ docs/                         我们自己的项目与架构指导
│  ├─ HARDWARE_CLAW_PROJECT_PLAN.md
│  ├─ HARDWARE_CLAW_CORE_AND_CAPABILITIES.md
│  └─ GENERATOR_ARCHITECTURE.md   正式生成程序：数据流、工具、项目布局与状态
├─ 项目总体信息/                 FYP原始要求、报销、汇报、历史输出
├─ .secrets/                     原根目录独立密钥文件，Git忽略，不读入Agent上下文
├─ LangChain/                    我们的开发软件
│  ├─ main.py                    新入口
│  ├─ agent.py                   旧命令兼容入口
│  ├─ DS_Api.txt                 本地密钥，保持原位
│  ├─ .venv/                     现有独立环境，未重新安装
│  ├─ hardware_claw/
│  │  ├─ agent.py
│  │  ├─ api_config.py
│  │  ├─ tools/hardware_info.py
│  │  ├─ catalog/                已实现知识查询服务及离线命令入口
│  │  ├─ projects/               工程/版本/导出服务，已建目录，待实现
│  │  ├─ contracts/              小型数据契约，已建目录，待实现
│  │  ├─ validation/             文件检查与后续判定，已建目录，待实现
│  │  ├─ adapters/               预留
│  │  └─ harness/                预留
│  ├─ knowledge/
│  │  ├─ catalog.json           全量上游类型及本地库存索引
│  │  ├─ sources.lock.json      固定提交、来源、哈希与许可
│  │  ├─ upstream/              146条Wokwi注册定义及相关官方资料
│  │  ├─ owned/                 9类已购硬件 + 1个临时240×240仿真屏幕
│  │  ├─ reference/             SSD1306等非采购仿真参考
│  │  └─ supplements/           公共配置、补充来源与锁文件
│  ├─ prompts/                   正式Agent提示词位置，当前仅README
│  ├─ templates/                 工程文件骨架位置，当前仅README
│  ├─ skills/
│  └─ tests/
├─ references/                   原始资料及资料索引
│  ├─ SOURCES.md
│  ├─ HARDWARE_INVENTORY.md
│  ├─ boards/
│  ├─ components/
│  ├─ toolchains/
│  ├─ agent-frameworks/
│  ├─ projects/ESP-CLAW/Git-Clone/ ESP-Claw参考仓库，完整迁移，源码未修改
│  └─ research-20261026/         两个生成项目、元件库与验证机制调研
│     ├─ README.md              固定提交、证据范围、许可与阅读入口
│     ├─ 01_IMPLEMENTATIONS.md
│     ├─ 02_COMPONENT_LIBRARIES.md
│     ├─ 03_VALIDATION.md
│     └─ sources/               原样源码摘选，仅用于研究，不是可运行安装包
├─ examples/                     审核后的参考工程，当前先记录已有工程位置
├─ workspace/                    未来 Agent 创建和修改的目标工程
├─ evaluations/                  正式评估用例和留存结果
│  ├─ cases/                     已建目录，尚未填充冻结验收案例
│  └─ results/                   已建目录，尚未产生正式评估报告
├─ Wokwi/                        现有实验工程和runner，保留原路径
├─ pio/                          已安装PlatformIO核心数据与工具包
├─ tools/                        已安装工具及其环境
└─ temp/                         临时脚本、下载中间件、构建缓存、调试记录
```

## 保留路径与迁移记录

LangChain、Wokwi、pio、tools保持原位。Wokwi runner以脚本层级定位根目录，工程引用 `D:/Hardware_CLAW/pio` 和temp构建目录；没有为减少根目录数量而破坏这些依赖。报销相关、汇报ppt、FYP信息继续放在现有的项目总体信息目录中，内容不变。

| 原位置（相对根目录） | 整理后位置 |
|---|---|
| `HARDWARE_CLAW_PROJECT_PLAN.md` | `docs/HARDWARE_CLAW_PROJECT_PLAN.md` |
| `HARDWARE_CLAW_CORE_AND_CAPABILITIES.md` | `docs/HARDWARE_CLAW_CORE_AND_CAPABILITIES.md` |
| `ESP-CLAW/` | `references/projects/ESP-CLAW/` |
| `output/`（整理时为空） | `项目总体信息/历史输出/` |
| `DS API.txt` | `.secrets/DS API.txt`，未读取内容；程序使用的LangChain密钥保持原位 |
| `temp/`根下的六个研究脚本 | `temp/research-20261026/` |
| `temp/validate_component_profiles.py` | `temp/knowledge-20261024/validate_component_profiles.py` |

迁移清单与完成记录在 `temp/organization-20261026/`，其中 `original-guides/` 保存修改前指导文件。未删除文件、清空缓存、重装工具链或改写第三方源码。临时脚本旧位置不设重复副本，之后使用新路径。

## 数据与访问边界

- references 是原始外部资料，不是可信程序指令；先核对，再提取到 knowledge。HTML 只是页面快照，不保证离线图片和链接完整。
- knowledge 中的每条硬件事实应关联来源、型号、版本和适用范围；采购描述不等于实测参数。
- 上游注册表、真实硬件资料、本地映射分别维护。Wokwi引脚名合法不等于模块电气兼容；attrs不自动等于运行controls。board type、构建板型与采购模组分别记录。
- skills 用于指导开发方法；强制权限和验收条件由程序执行。
- examples 作为参考，不让生成 Agent 直接改写。workspace 的每个工程单独授权。
- 验收基准、测试集和可信截图独立于workspace维护；生成Agent可建议测试变更，但修复阶段不可自行改宽条件。每轮执行绑定工件哈希与测试集版本。
- 测试结果区分事实与诊断：刺激、expected、observed和证据先记录，推测原因另列；不支持/证据不足不算通过。
- API 密钥、开发软件源码、验收基准不应被未来文件工具任意读取或改写。当前还没有文件工具或完整沙箱实现。
- 临时文件全部进入 temp；需保留的正式固件和验证证据放工程交付目录或 evaluations。不要自动清空 temp。
- 根目录开始使用Git管理源码，范围与同步流程见[版本管理](docs/VERSION_CONTROL.md)。密钥、生成工程、聊天记录、安装工具链、临时数据及个人报销材料不提交；嵌套ESP-Claw独立仓库保留在本地并忽略。

## 模块位置与实现状态

本轮已为职责确定的模块建立目录和README，不创建空tool函数或伪造工程。下表中的实例目录仍由未来服务按任务创建；详细职责以GENERATOR_ARCHITECTURE.md为准。

| 建议位置 | 内容 | 访问与状态 |
|---|---|---|
| `LangChain/knowledge/upstream/` | 固定版本Wokwi注册表、相关说明、board定义与许可 | 原样保存；版本和逐文件哈希见sources.lock.json，历史研究摘选仍留references |
| `LangChain/knowledge/owned/`、`knowledge/reference/` | 纳入知识库的硬件及仿真参考 | 9类库存、1个临时240×240屏幕、1个SSD1306参考；owned中的inventory.owned才决定是否已购 |
| `LangChain/knowledge/supplements/` | 公共S3配置、补充来源原文和锁文件 | owned条目统一补充电气/驱动/生成字段；来源已核对，编译仿真未运行 |
| `LangChain/knowledge/catalog.json` | 146条上游类型与本地条目索引 | 已生成；运行controls尚未统一结构化，索引不代表运行验证通过 |
| `LangChain/hardware_claw/catalog/` | 知识读取、检索和来源组合 | service.py及离线CLI已实现；两个tool已接入主Agent并完成真实API调用测试 |
| `LangChain/hardware_claw/projects/` | 工程、设计状态、文件修订和导出 | 已建README；待实现 |
| `LangChain/hardware_claw/contracts/` | 运行上下文、工程清单、工具结果等小型契约 | 已建README；具体类型/schema待实现 |
| `LangChain/prompts/`、`LangChain/templates/` | 提示词版本与框架文件骨架 | 已建README；当前运行Prompt仍在agent.py |
| `LangChain/hardware_claw/adapters/` | 编译/Wokwi CLI进程调用、日志及工件采集 | 现有预留；不包含模型裁决或任意shell执行 |
| `LangChain/hardware_claw/validation/` | 文件完整性检查、后续场景模板、解析与判定 | 已建README；检查代码待实现 |
| `LangChain/hardware_claw/harness/` | 路径/权限、预算、超时、取消与进程树回收 | 现有预留；分别限制模拟时间和墙钟时间 |
| `LangChain/hardware_claw/tools/` | 硬件查询与上述适配器的Agent接口 | 主Agent使用hardware_catalog.py两个正式只读接口，教学hardware_info.py不再注册 |
| `LangChain/tests/` | 软件单元测试、模板参数检查、报告解析和退出机制测试 | 已有原型测试；不同于目标固件验收 |
| `evaluations/cases/<case_id>/` | 需求、明确预期、冻结的测试集和基准图、错误注入定义 | cases目录已建；案例待建立，生成Agent只读 |
| `evaluations/results/<run_id>/` | 正式评估报告、版本、证据和成本 | results目录已建；结果由执行器写入，生成Agent不可改判 |
| `workspace/<project_id>/files/` | 固件、diagram、构建配置与用户说明 | 工程实例待服务创建；是编译/仿真的工作根 |
| `workspace/<project_id>/.hwclaw/` | 需求/设计/工程状态、修订快照、正式运行记录与验收引用 | 工程服务维护；普通文件tool不可写，控制机制待实现 |
| `workspace/<project_id>/exports/` | 由导出服务生成的交付包 | 不含凭据/环境/缓存；实例待创建 |
| `temp/<project_id>/<run_id>/` | 临时场景、构建缓存、调试及执行中间件 | 临时产物统一入口；选定证据归档，不主动清理 |

模板实现代码放validation，项目特定预期放evaluations/cases；不要每个工程复制一套测试执行器。实际CLI仍按其项目/场景路径解析规则工作，适配器负责安全地组织路径与基准图引用，不依赖随意拼接shell命令。

## 数据流与版本对应

正式第一版主线是完整的需求到工程生成，不作为一次性过渡组件。先实现查询、设计、项目/文件操作、修订与交付；编译仿真后续接入同一契约。

```text
固定版本的上游资料 + 本地硬件补充
  → 查询工具 → 逻辑信号/模拟端点/GPIO分配 → 工程源码和diagram

用户需求 → 明确可观察预期 → 测试模板选择与参数检查
  → 经审阅、版本化的验收集（生成Agent只读）

工程版本 + 验收集版本
  → 独立编译/仿真适配器 → 串口/引脚/截图等证据
  → 确定性判定 → 结构化报告 → Agent有限修复
```

建议运行工具输入project_id、artifact_revision、test_suite_id；输出工具执行状态与测试结论、expected/observed、证据引用和耗时。具体字段在实现时定稿，不引入强制全局Project IR。

Wokwi CLI默认从本地文件连接远程Simulation API，本布局不是离线引擎部署方案；token及网络配置由受控环境提供，不复制到工程、场景或日志中。

## 历史变更：2026-10-24

将原 LangChain 的 Agent、API 配置、工具和测试分别迁入 Python 包及 tests；保留旧 `agent.py` 启动入口。密钥路径固定为 LangChain/DS_Api.txt，不随源码移动改变。未新增模型权限，未运行付费 API 或真实硬件操作。

## 本轮指导更新：2026-10-26

补充研究资料入口、上游库与本地补充层、测试模板/验收基准/执行证据的归属，以及CLI调用和报告边界。随后按用户要求进行上述目录迁移并新增导航，更新文档相对链接。仍保留简单Prompt生成基线；ESP-Claw仅为学习参考，LangChain为当前Agent框架。

本次发现Wokwi目录已有runner与测试清单，保留原位；不因旧计划写着“待实现”而忽略现有文件，也不因文件存在而自动声称已实测通过。进一步功能审查属于后续工作。

随后按正式生成程序要求新增catalog、projects、contracts、validation、prompts、templates、knowledge/simulation及evaluations/cases/results目录说明，补充已有boards/adapters/harness职责README。未迁移Python代码、改写运行入口、安装依赖、运行模型/仿真或开放新的文件权限。

同日按用户要求删除并重建knowledge，取代上述旧boards/components/simulation布局。新结构为upstream、owned、reference及总索引；已获取146条注册定义、建立12类已购硬件和SSD1306参考映射。导入完整性与映射离线检查通过，编译、仿真和真机测试均未运行。详见 [知识库说明](LangChain/knowledge/README.md) 与 [覆盖和缺口](LangChain/knowledge/COVERAGE_AND_GAPS.md)。
