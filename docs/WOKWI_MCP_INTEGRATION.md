# 官方 Wokwi MCP 接入与实测

## 实现边界

使用本机官方 `wokwi-cli 0.29.0 (940b7237d26f)` 的 stdio MCP，通过 Python MCP SDK 1.30.0 连接。没有自行实现仿真底层协议，也没有修改官方CLI。官方将此功能标记为 experimental；适配层拒绝未经验证的新服务版本。

新增两个工程工具：

- `inspect_simulation(expected_version, actions)`：核对当前设计、基础检查和编译固件，复制只读快照到temp；通过官方MCP启动，顺序执行动作，结束时关闭进程。一个调用就是一个独立会话，不跨调用保留仿真状态。
- `read_simulation_evidence(expected_version, attempt, filename, offset, limit)`：按页读取本次MCP保存的原始JSON、日志或VCD。校验修订、固件/电路身份和文件哈希，拒绝旧版本证据或篡改。只有next_offset=null才读完。

`simulate_project/evaluate_tests`原有流程保持独立。新MCP观测不覆盖其报告、不生成业务pass，也不改变导出工程。查看画面、逻辑和需求是否正确仍需要通用验收机制。

## 11个官方工具的真实测试

| 官方工具 | 实测 | 数据与限制 |
| --- | --- | --- |
| wokwi_start_simulation | 通过 | 现有游戏与独立夹具均启动；同会话再次start可重新加载 |
| wokwi_stop_simulation | 通过 | 实际是暂停；running=false，间隔等待后nanos不变；彻底结束由SDK关闭进程 |
| wokwi_resume_simulation | 通过 | running恢复true，模拟时钟继续前进 |
| wokwi_restart_simulation | 通过 | 模拟时钟重置，固件重新运行 |
| wokwi_get_status | 通过 | running、connected、nanos、project；墙钟等待不等于精确模拟时间推进 |
| wokwi_write_serial | 通过 | ASCII输入被测试固件收到并回显；不宣称支持任意二进制/Unicode往返 |
| wokwi_read_serial | 通过但有限缓冲 | 读到启动/业务输出，clear后确认旧内容消失；官方最多保存1000个接收块，不保证无限历史、完整二进制编码 |
| wokwi_read_pin | **部分可用** | 数字输入释放/按下返回true/false；voltage始终undefined，映射为null。模拟输入的布尔值不能代表ADC数值，不能据此推断准确电压 |
| wokwi_set_control | 通过但须独立观察 | x=-1/+1使夹具固件ADC输出变化；pressed使GPIO变化。官方对不存在的control也回成功；宿主因此依据统一知识库检查控制名、来源、范围，且始终标记effect_verified=false |
| wokwi_take_screenshot | **无法获取完整图像** | 初始化SSD1306返回PNG Base64前100字符加省略号；官方源码有substring(0,100)，不能解码完整图。未初始化SSD1306报错；现有ST7789游戏返回无有效framebuffer，不外推其支持 |
| wokwi_export_vcd | 通过（有前提） | 接线逻辑分析仪夹具导出72 samples / 2 channels、1ns时间基准及实际变化。现有游戏没有分析仪，明确报错；不会偷偷插入元件改变电路 |

资源接口也实际测试：`tools/list`返回11个工具，`resources/list`返回diagram.json和wokwi.toml。Windows下官方列出的绝对file URI经SDK规范化后，官方readResource错误按字符串剥离协议，出现`/D:/...`。

适配层只对这两个已登记资源使用固定的`file://./文件名`兼容URI；服务cwd由宿主绑定，读取结果必须逐字等于快照。原始错误和兼容路径写入证据，没有开放任意资源路径。两个资源内容均核对通过。

## Harness与原始数据

- Agent不能传projectPath、outputPath、sdcard、sdcardOut，VCD输出由宿主分配；当前拒绝额外配置、自定义芯片文件和SD卡挂载，尚未测试这些可选参数。
- MCP一次最多32动作，总显式等待60秒；单请求45秒、会话180秒，与旧仿真共享每轮10次预算。时间/输出预算位于limits.py。
- 原始JSON累计最多16MiB，单个证据文件最多16MiB；模型每项只收最多4000字符摘要，完整保存内容可分页读取。这不能恢复官方接口已经截掉或缓冲区丢失的数据。
- 原始证据在`workspace/<id>/.hwclaw/mcp/<attempt>/`，含inventory、逐项response、binding、服务日志、VCD、哈希manifest；过程与失败证据保留在`temp/mcp-simulations/`。取消和过期修订不会覆盖现有验收结果。
- 真实测过1秒超时，以及仿真已启动后取消；返回timeout/cancelled并关闭MCP进程。未发现残留wokwi-cli.exe。
- 固件没有任何针对俄罗斯方块或其他生成工程的修改。独立串口/ADC/显示/逻辑分析仪夹具只在tests/fixtures下，生产Agent不读取这些测试文件。
- 当前Agent可读取VCD原文；尚无通用波形语义解码或独立验收。生成器若要自动加入逻辑分析仪，仍需维护有来源的本地生成配置；这里的夹具不是生产答案模板。

## 验证证据与复现

- 未修改的游戏：`workspace/web-project-f12d321cc23b/.hwclaw/mcp/4f419150f32145f4a825a9498348932f/`。早期URI失败记录同目录保留。
- 最终独立夹具：`temp/mcp-probes/1bc6fe85f0bd4b38876e25c6df3c6dd1/`；probe-checks.json中10项传输/时序检查通过，截图和电压缺口另列，不能称全部数据完整。
- 数字按键状态及未知控制名探测：`temp/mcp-probes/99e5888a538b43b894f920db522fffa1/`。
- 超时：`temp/mcp-probes/aa2a1bc7b84440d3ac4172e835b9ee7d/`；运行中取消：`temp/mcp-probes/fa1e285c8d6a4d7a8bccba9e6276c029/`。
- 将`LangChain/tests/fixtures/mcp_transport`复制到temp构建；复制真实firmware.bin/elf至其firmware目录，然后运行 `LangChain/.venv/Scripts/python.exe -X utf8 -B LangChain/tests/probe_wokwi_mcp.py --prepared-project <已编译夹具目录>`。所有新结果独立保存在temp/mcp-probes；此脚本不调用LLM。
- 离线测试覆盖参数/路径拒绝、缺失电压、截图截断、未登记控制名、证据版本及篡改、分页读回、完整LangChain工具回填。

最终全量回归104项通过。过程中原有导出目录发布两次遇到Windows WinError 5；针对所有工程统一增加最多5次、总退避0.75秒的目录重命名重试，目标存在仍拒绝覆盖，持续错误仍抛出。没有修改任何生成工程来规避测试。

## 真实LLM联调

| 任务 | 模型调用 | 耗时 | 输入tokens | 输出tokens | 总tokens |
| --- | ---: | ---: | ---: | ---: | ---: |
| get_project→inspect_simulation | 4 | 27.59秒 | 29259 | 764 | 30023 |
| read_simulation_evidence | 2 | 5.81秒 | 9978 | 481 | 10459 |

第一轮有一次pin数字类型被Schema拒绝，模型改为字符串后成功；最终报告区分缺失电压和未验收。第二轮指定的response-005实际是停止响应，模型如实报告无引脚读数；这次证明证据读取回填，没有证明获取了引脚数据。分页机制另由离线逐页重组与哈希测试验证。两轮工程版本均保持6，无源码修改。

## 官方依据

- [官方MCP配置说明](https://github.com/wokwi/wokwi-cli#MCP-Server)
- [已测试版本工具源码](https://github.com/wokwi/wokwi-cli/blob/940b7237d26f/packages/cli/src/mcp/WokwiMCPTools.ts)
- [仿真会话与缓冲区源码](https://github.com/wokwi/wokwi-cli/blob/940b7237d26f/packages/cli/src/mcp/SimulationManager.ts)
- [资源读取源码](https://github.com/wokwi/wokwi-cli/blob/940b7237d26f/packages/cli/src/mcp/WokwiMCPResources.ts)
