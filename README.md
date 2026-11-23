# Hardware-CLAW

电脑端嵌入式开发 Agent：通过文本需求完成硬件选型、接线设计、固件生成、静态检查、编译和 Wokwi 工程导出，并生成测试计划。基于 LangChain，采用主协调 Agent 和三个固定职责的子 Agent。

本页用于启动、使用和定位代码。支持范围及待办见 [当前状态](docs/STATUS.md)，详细操作见 [文档导航](docs/README.md)。目前以 Windows / PowerShell 为支持环境。

## 1. 启动与使用

首次使用或队友在新电脑上运行，先按 [环境配置指南](docs/guides/SETUP.md) 安装 Python 依赖、配置本地 API 密钥与编译工具链。Git 仓库不包含这些本机环境。

```powershell
git clone https://github.com/Orion-Hughes/Hardware-CLAW.git
cd Hardware-CLAW
```

需要 Python 3.12、Git，以及你自己的模型 API 密钥。查看仿真还需 VS Code 和 Wokwi 扩展。首次安装/编译需要联网；克隆仓库本身不包含 Python 环境或编译器。

环境已就绪时：

1. 双击 `LangChain/Start-Agent.cmd`，打开网页前端。
2. 输入需求，例如“用 ESP32-S3 和摇杆生成串口输入监测工程，并生成测试计划”。
3. 在同一对话中继续描述修改；`/new 需求` 新建任务，`/project 工程ID` 绑定已有工程。侧栏可切换聊天。
4. 用完后双击 `LangChain/Stop-Agent.cmd`。关闭网页不会停止服务；改动代码或配置后需重启。

命令行也使用同一主协调流程：

```powershell
cd LangChain
.\.venv\Scripts\python.exe -X utf8 -B main.py --help
.\.venv\Scripts\python.exe -X utf8 -B main.py --question "描述需要生成的嵌入式系统"
.\.venv\Scripts\python.exe -X utf8 -B main.py --task 任务ID --question "继续修改此前任务"
.\.venv\Scripts\python.exe -X utf8 -B main.py --project 工程ID --question "检查并导出已有工程"
```

真实任务会产生 API 费用；运行结束查看调用次数、耗时、提供方 token 和工程交付状态。只运行 `--help` 不调用模型。

## 2. 查看生成结果

成功导出后，用 VS Code 打开整个目录：

```text
workspace/<project_id>/exports/v<version>/simulation/
```

安装并授权 VS Code 的 Wokwi 扩展后，运行 `Wokwi: Start Simulator`。交付目录包含电路、配置和预编译固件，具体见 [VS Code 交付指南](docs/guides/VSCODE_DELIVERY.md)。

注意：当前 Agent3 只生成测试计划，尚未自动执行计划、评估功能或完成仿真纠错。烧录接口需用户显式确认，尚未实物验证；静态检查、编译、导出成功不等于功能验收通过。

点击聊天网页顶部“固件烧录”，即可在独立页面选择工程文件夹、串口和目标配置，编译准备、查看镜像、二次确认并执行，无需命令行。打开页面或准备预览不写入硬件，也不调用 LLM；实际烧录尚待实物验证。见 [烧录指南](docs/guides/FLASHING.md)。

烧录页当前单独构建采购记录的 N32R16V（32MB OPI Flash / 16MB OPI PSRAM），不覆盖8MB/无PSRAM的Wokwi构建和旧导出。型号尚未实物核对，外设和可用内存仍需真机验证。

## 3. 文件位置

| 位置 | 用途 |
|---|---|
| `LangChain/main.py`、`app.py` | 命令行与网页入口 |
| `LangChain/hardware_claw/` | 主协调、三个阶段、工具、工程管理、检查及编译适配 |
| `LangChain/prompts/`、`skills/`、`templates/` | 提示词、技能、只读配置与规划格式 |
| `LangChain/knowledge/` | 运行时硬件库：连接卡、上游资料、API、来源锁及本地驱动 |
| `LangChain/tests/`、`firmware/graphics/` | Python 软件回归、独立 C++ 绘图测试 |
| `workspace/` | 本机工程、修订、编译报告、测试计划、导出和任务/聊天数据库 |
| `docs/` | 安装使用、开发指南、当前架构和支持范围 |
| `references/` | 知识库引用的硬件配置清单与来源索引 |
| `temp/` | 临时脚本、构建缓存、服务日志和调试证据 |
| `tools/`、`pio/`、`.secrets/` | 本机工具安装、PlatformIO 数据和凭据，不提交 Git |

完整目录与数据流见 [文件结构](docs/guides/PROJECT_STRUCTURE.md)。历史研究、实验报告、旧示例、个人材料和本机备份不属于公开运行包。第三方资料与许可见 [来源说明](THIRD_PARTY_NOTICES.md)。

## 4. 开发从哪里看

| 要修改什么 | 优先查看 |
|---|---|
| 网页与启动 | `LangChain/app.py`、`Agent-Service.ps1`、`chainlit-config.toml` |
| 主 Agent 调度、证据与修复交接 | `hardware_claw/runtime.py`、`coordinator/`、`prompts/coordinator.md` |
| 选型 / 生成 / 验证规划 | `hardware_claw/stages/`、对应 `prompts/` 与 `skills/stages/` |
| 硬件检索及资料读取 | `hardware_claw/catalog/`、`tools/hardware_catalog.py`、[入库指南](docs/guides/HARDWARE_ONBOARDING.md) |
| 工程、GPIO 表、检查与交付 | `hardware_claw/projects/`、`validation/`、`adapters/compiler.py` |
| 烧录界面、镜像与显式执行 | `hardware_claw/deployment/http.py`、`deployment/ui/`、[烧录指南](docs/guides/FLASHING.md) |
| API 接入与运行上限 | `hardware_claw/api_config.py`、`limits.py` |

上表代码路径除特别注明外相对 `LangChain/`。阶段职责、工具边界和数据流见 [架构说明](docs/architecture/OVERVIEW.md)。

在 `LangChain/` 运行离线回归：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
```

离线回归不调用真实模型，不能代替真实 Agent 或硬件验收。真实集成测试需先明确预算，并保留请求、响应、用量和失败证据。

协作前阅读 [开发约束](AGENTS.md) 和 [Git 指南](docs/guides/VERSION_CONTROL.md)。不要提交 API 密钥、聊天、生成工程、虚拟环境或安装目录；不要手改 Agent 输出后宣称生成成功，也不要加入只为某个工程通过的规则。
