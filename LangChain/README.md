# Hardware-CLAW：硬件工程生成Agent

可选主协调模式已接入选型、生成和只读仿真规划子Agent：网页输入 `/coordinator`，CLI使用 `--coordinator`；主Agent有状态、阶段委派、交付3个工具。生成阶段可完成接线、固件、检查、真实编译，并由主Agent导出；verification参考firmware-testing-agent，固定提取需求、规划场景、逐例生成时间线并检查，输出计划后停止，不执行仿真。原生成入口保留。最新边界与实测见[第三Agent实现](../docs/AGENT3_FTA_PLANNER.md)、[测试记录](../docs/AGENT3_FTA_TEST_RESULTS.md)。

本轮明确了工具字段、mcu保留ID和修正反馈；`read_hardware`默认56,000、最高120,000字符，返回必要缺项和可直接执行的续读参数。两次真实生成均编译导出成功，但使用的是临时100万token测试上限，生成阶段各约30万；默认生成预算仍为8万。未进行这两次工程的仿真验收，不能把测试成功外推为默认预算可完成或功能正确。详情见[读取服务](hardware_claw/catalog/README.md)。

当前功能：通过API运行LangChain Agent，查询硬件、读取通用技能/配置模板、生成文件、检查、编译、Wokwi CLI限时观察，并交付VS Code仿真文件夹。工程专用验收规则已移除，通用功能验收尚未实现。见[仿真工具说明](../docs/AGENT_SIMULATION.md)和[工具状态](../docs/TOOLS_IMPLEMENTATION_STATUS.md)。

网页支持同一工程持续修改与原生历史侧栏；聊天和工程绑定保存在本地SQLite，详见[会话管理](../docs/CHAT_HISTORY.md)。

正式第一版建设方向为完整的需求到工程生成程序，见[程序架构与数据流](../docs/GENERATOR_ARCHITECTURE.md)。工程操作、修订、检查、编译、仿真日志采集与交付已实现；需求驱动的通用验收待实现，禁止用单工程特例替代。

2026-11-02硬件接口改为两个：`search_hardware`提供选型信息，`read_hardware`批量读取板卡与外设的基础使用资料，共用文档去重，扩展原文按需补读。旧查询包装不再向Agent注册。现有工程工具通过内存适配读取新卡，不保留重复的手写profile。见 [知识库结构](knowledge/README.md)、[硬件查询工具说明](hardware_claw/catalog/README.md) 和 [双工具测试记录](../docs/HARDWARE_QUERY_TESTS_20261102.md)。

官方MCP交互观测已接入：inspect_simulation与read_simulation_evidence支持交互批次及完整证据分页读取；已确认的截图、电压等限制见[接入与实测](../docs/WOKWI_MCP_INTEGRATION.md)。

## 运行

### 网页前端依赖

Chainlit 2.12.0已安装在本项目`.venv`，网页已接入现有Agent、工程工具和本地聊天历史。

- 双击 `Start-Agent.cmd`：启动后台服务并打开 `http://127.0.0.1:8000`；服务已运行时直接打开网页。
- 双击 `Stop-Agent.cmd`：停止本项目服务。关闭网页不会停止服务；未设置开机自启。
- 网页输入问题即可。工具步骤可展开查看参数与结果，每轮显示耗时、Token与状态；停止按钮取消当前任务，已经发送的API请求仍可能计费。
- 每个聊天独立保存工程绑定和最近六轮完成问答；完整消息及工具步骤持久化到本地历史，工具原始结果不全部跨轮发送给模型。侧栏可切换历史，重启服务后仍可恢复。
- 支持文本查询、工程生成和Wokwi CLI仿真观察；当前没有自动功能验收，不支持真机上传。

网页默认生成模式，直接输入需求即可创建含固件的VS Code工程；`/new 需求`另建工程；`/new-arduino 需求`、`/new-pio 需求`保留源码模式；`/project 工程ID`恢复；`/query`切换只读查询。绑定工程后可要求修改、检查、编译和导出；结果附simulation文件夹路径和ZIP。CLI仍通过`--new-project`显式创建工程。

`app.py`只负责网页适配；`hardware_claw/runtime.py`是网页和CLI共用的执行层；`hardware_claw/agent.py`负责Agent及调用预算。API仍由`api_config.py`在服务端读取，浏览器不接触密钥。

`chainlit-config.toml`与`chainlit.md`是界面配置和说明，启动时复制到`../temp/chainlit-runtime/`。运行日志、生成配置与附件缓存均保存在该临时目录。修改代码或配置后先停止再启动。端口8000被其他服务占用时会报错，不会停止其他服务。

### 当前命令行入口

只生成已有工程的仿真计划（付费API，不编译/不仿真）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.stages --stage verification --project 工程ID --question "根据当前需求与可用接口生成具体仿真计划，不执行"
```

结果在工程 `.hwclaw/verification_plans/<ID>/plan.md` 与 `plan.json`；失败保留原始候选和错误，无完整plan时不可视为完成。无需重复调用API来查看已有计划。只读规划成功不代表预期正确或功能通过。

生成与恢复（使用项目.venv解释器）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B main.py --new-project dht-monitor --question "用ESP32-S3与DHT22每2秒采样并输出串口，仅仿真"
.\.venv\Scripts\python.exe -X utf8 -B main.py --project 工程ID --question "检查并导出" --require-delivery
```

工程保存在`../workspace/<project_id>/files/`；设计和不可变修订、运行记录在`.hwclaw/`；导出在`exports/`。文件工具不访问软件源码、密钥或其他工程。当前检测到files被外部修改会停止并提示人工核对，不自动合并或覆盖。

在 PowerShell 中执行，不必激活虚拟环境：

```powershell
cd D:\Hardware_CLAW\LangChain
.\.venv\Scripts\python.exe -X utf8 -B main.py
```

`hardware_claw/api_config.py` 统一管理 API 接入。仍读取 `LangChain/DS_Api.txt`，密钥文件未搬动。文件内只放密钥本身（UTF-8 文本，无标签、引号或说明），已加入 `.gitignore`。更换密钥后重启程序即可，无需改代码。旧命令 `python -B agent.py` 保留兼容。

优先级：`DS_Api.txt` → `DEEPSEEK_API_KEY` 环境变量 → 使用 `--ask-key` 时的隐藏输入。若密钥文件存在但为空或格式错误，会明确报错，不会静默切换到其他密钥。密钥文件位置与启动命令的当前目录无关。

默认模型为官方文档当前列出的 `deepseek-flash`，如需更换：

```powershell
$env:DEEPSEEK_MODEL = '你的可用模型名'
```

真实运行会产生 API 用量，需要有效密钥和账户余额。模型兼容性、网络及真实工具调用效果必须通过这一步验证。程序未配置云端追踪；问题与工具结果会发送给 DeepSeek。

默认问题查询可用开发板与元件；自定义问题使用`--question "你的问题"`。观察 `[tool request]`、`[tool result]`、`[model]`。最后显示耗时和服务端提供的Token数据；`Query round trip completed`只表示工具请求已回填且模型给出最终回答，不是事实正确性或硬件验收结论。

## 文件与学习顺序

1. `hardware_claw/tools/hardware_catalog.py`：两个正式只读tool、参数Schema和返回包装。
2. `hardware_claw/catalog/service.py`：查询、组合知识和受控读取。
3. `hardware_claw/agent.py`：`create_agent`循环、查询提示词、中间件和流式输出。
4. `tests/test_agent.py`、`tests/test_hardware_catalog.py`：不联网的工具/循环测试。
5. `requirements.txt`：主要依赖范围；`requirements-lock.txt`：安装版本快照。

API 配置单独放在 `hardware_claw/api_config.py`，由 Agent 调用 `create_model()`。`tests/test_api_config.py` 使用模拟数据测试读取优先级和配置传递，不接网络、不读取真实密钥。

当前读取knowledge中的本地硬件配置与Wokwi元数据。资料状态与运行验证状态分别记录，未知规格不补造；上游metadata_only和本地blocked均不等于可生成。

## 最小 Harness

- 每次模型请求超时120秒，不自动重试；查询总时限600秒、工程3600秒、单次编译900秒。
- 查询模式最多16次模型、48次工具、128图步；工程模式最多60次模型、160次工具、512图步。预算统一在 hardware_claw/limits.py 中配置，见 [测试阶段预算](../docs/DEVELOPMENT_LIMITS.md)。达到上限退出并保留已保存工程。
- 查询模式只读；绑定工程后提供受控files写入。没有任意Shell和真机操作工具。
- 不输出密钥或原始异常请求；Token 缺失标记为 unavailable，不伪造为零。
- 编译/仿真进程支持超时和取消回收；尚未实现 Token 硬预算与真机验收。`ready_for_vscode`只表示交付完整，行为判定单独展示；不支持的测试场景不会标记通过。

## 离线测试

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

覆盖已知/未知资料、完整工具回填循环和无限调用的停止限制。模拟模型通过不代表 DeepSeek 在线已验证。

本项目使用 Python 3.12；系统默认 `python` 是 3.8，不要混用。依赖在 `.venv`，临时文件统一放在 `D:\Hardware_CLAW\temp\langchain`。

## 官方参考

- https://docs.langchain.com/oss/python/langchain/agents
- https://docs.langchain.com/oss/python/integrations/chat/deepseek
- https://api-docs.deepseek.com/quick_start

接入文档的模型示例可能滞后，以 DeepSeek 官方当前可用型号为准。

## 整理后的目录（2026-10-24）

- `main.py`：新的统一启动入口；`agent.py` 仅兼容旧命令。
- `hardware_claw/tools/`：硬件查询、技能/模板读取和工程工具，完整工程模式共15个工具。
- `hardware_claw/adapters/`：PlatformIO编译器和Wokwi CLI适配器。
- `hardware_claw/harness/`：预留公共约束，现有调用上限暂留 Agent 配置中。
- `knowledge/`：upstream保存146条Wokwi定义，owned记录9类已购硬件及临时240×240屏幕，reference保留SSD1306，supplements保存公共配置/来源。已由查询tools接入主Agent，不代表真实接线已验证。见 [知识库说明](knowledge/README.md)。
- `skills/`：待编写的项目领域指导，不自动加载参考文档。
- `tests/`：开发工具自身的离线测试。

总目录用途见 `../PROJECT_STRUCTURE.md`；采购硬件清单见 `../references/HARDWARE_INVENTORY.md`；网络资料索引见 `../references/SOURCES.md`。
