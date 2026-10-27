# 官方资料索引与阅读顺序

## 专项调研报告

- [需求驱动嵌入式设计与仿真验证：第一轮调研（2026-10-26）](EMBEDDED_DESIGN_AND_VALIDATION_RESEARCH.md)：比较Circuit Lab、circuit-synth、atopile、tscircuit、Wokwi、固件测试研究和Renode的数据管理、生成与验证机制；附实际阅读的源码入口与限制。未安装或复现这些项目。

检索与归档日期：2026-10-24。按项目原型和已到货清单开始收集，不宣称所有器件资料已齐全。

搜索接口本次不可用；通过用户已有的本地代理直接访问官方文档和维护者仓库，并跟随官方链接获取资料。下列资料均已实际访问并保存页面/文本快照。HTML 不打包附属图片；下载成功不等于已逐页审查或已完成工具集成。

## A. Agent 与执行框架

| ID | 原始来源 | 本地快照 | 用于什么 |
|---|---|---|---|
| A01 | [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents) | [Markdown](agent-frameworks/langchain-agents-20261024.md) | create_agent、工具循环、状态和扩展点 |
| A02 | [LangChain Tools](https://docs.langchain.com/oss/python/langchain/tools) | [Markdown](agent-frameworks/langchain-tools-20261024.md) | 工具定义、Schema、运行上下文 |
| A03 | [Middleware](https://docs.langchain.com/oss/python/langchain/middleware/overview) | [Markdown](agent-frameworks/langchain-middleware-20261024.md) | Harness 钩子与运行约束 |
| A04 | [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) | [Markdown](agent-frameworks/langgraph-overview-20261024.md) | 后续自定义流程参考，非当前必须改造项 |

## B. 开发板与 ESP-Claw 参考

| ID | 原始来源 | 本地快照 | 用于什么 |
|---|---|---|---|
| B01 | [ESP32-S3-DevKitC-1 v1.1 官方指南](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html) | [HTML](boards/esp32-s3-devkitc-1-v11-20261024.html) | 型号表、硬件说明、引脚及原理图入口；列出 N32R16V |
| B02 | [ESP-Claw 项目架构总览](https://esp-claw.com/zh-cn/reference-project/) | [HTML](boards/esp-claw-reference-project-20261024.html) | 架构研究；当前该页不是购买套件的完整BOM/电路图 |

## C. 器件、驱动与仿真

| ID | 原始来源 | 本地快照 | 适用范围 |
|---|---|---|---|
| C01 | [Wokwi DHT22](https://docs.wokwi.com/parts/wokwi-dht22) | [HTML](components/wokwi-dht22-20261024.html) | 仿真引脚、属性及温湿度输入 |
| C02 | [Wokwi SSD1306](https://docs.wokwi.com/parts/board-ssd1306) | [HTML](components/wokwi-ssd1306-20261024.html) | 现有OLED仿真基线，不是已购ST7789 |
| C03 | [Wokwi Servo](https://docs.wokwi.com/parts/wokwi-servo) | [HTML](components/wokwi-servo-20261024.html) | 通用舵机仿真，不是具体SG90厂商规格 |
| C04 | [Wokwi Analog Joystick](https://docs.wokwi.com/parts/wokwi-analog-joystick) | [HTML](components/wokwi-joystick-20261024.html) | 摇杆仿真及输出定义 |
| C05 | [Wokwi LED Ring](https://docs.wokwi.com/parts/wokwi-led-ring) | [HTML](components/wokwi-neopixel-ring-20261024.html) | WS2812兼容环仿真，需按实物设置8灯 |
| C06 | [Adafruit DHT 库](https://github.com/adafruit/DHT-sensor-library) | [README](components/adafruit-dht-library-20261024.md) | 固件库依赖和实现入口，不等同于红板模块规格 |
| C07 | [Adafruit ST77xx 库](https://github.com/adafruit/Adafruit-ST7735-Library) | [README](components/adafruit-st7789-library-20261024.md) | ST7789驱动路线；需核对采购屏的初始化参数 |
| C08 | [Adafruit NeoPixel 库](https://github.com/adafruit/Adafruit_NeoPixel) | [README](components/adafruit-neopixel-library-20261024.md) | 灯环驱动与接口 |
| C09 | [ST77xx graphicstest 示例](https://github.com/adafruit/Adafruit-ST7735-Library/blob/master/examples/graphicstest/graphicstest.ino) | [源码快照](components/adafruit-st7789-example-20261024.ino) | 显示初始化示例；其中板卡引脚不是我们的接线建议 |
| C10 | [Espressif USB Stream](https://docs.espressif.com/projects/esp-iot-solution/en/latest/usb/usb_host/usb_stream.html) | [HTML](components/espressif-usb-host-uvc-20261024.html) | USB摄像头/音频接入的官方技术入口，具体相机兼容性待确认 |

## T. 编译与仿真工具链

| ID | 原始来源 | 本地快照 | 实现关联 |
|---|---|---|---|
| T01 | [Arduino CLI compile 1.5](https://arduino.github.io/arduino-cli/1.5/commands/arduino-cli_compile/) | [HTML](toolchains/arduino-cli-compile-v1.5-20261024.html) | 编译适配器候选；仅归档文档，不表示已安装此版本 |
| T02 | [PlatformIO pio run](https://docs.platformio.org/en/latest/core/userguide/cmd_run.html) | [HTML](toolchains/platformio-run-20261024.html) | 当前已有工程使用PlatformIO，优先核实复用 |
| T03 | [Wokwi CLI](https://docs.wokwi.com/wokwi-ci/cli-usage) | [HTML](toolchains/wokwi-cli-20261024.html) | CLI令牌、日志、时限、电路lint；工具可用性需实测 |
| T04 | [Wokwi Automation Scenarios](https://docs.wokwi.com/wokwi-ci/automation-scenarios) | [HTML](toolchains/wokwi-automation-20261024.html) | 场景输入、串口等待、引脚断言等；官方注明接口仍可能变化 |
| T05 | [diagram.json 格式](https://docs.wokwi.com/diagram-format) | [HTML](toolchains/wokwi-diagram-20261024.html) | 电路生成和静态检查 |
| T06 | [wokwi.toml 配置](https://docs.wokwi.com/vscode/project-config) | [HTML](toolchains/wokwi-config-20261024.html) | 固件、ELF及项目配置 |

## 阅读后对实现方案的调整

1. 先读 A02，再把现有 Tool 与工具参数约定对应起来；无需立即引入新框架。
2. 现有工程用 PlatformIO，所以编译适配器先核对已有环境，不默认另装 Arduino CLI。
3. Wokwi CLI 文档提供 lint，可作为 validate_project 的部分底层检查。它不能替代真机电气检查或完整需求验收。
4. Wokwi CLI 的 `--timeout` 是仿真时间，适配器还需独立的主机墙钟超时与进程回收。
5. 场景文档中的输入控制和断言应按当前版本逐项实测；不能直接采用此前草案中未经核实的动作名称。
6. 真机屏是ST7789，现有仿真是SSD1306。仿真显示适配范围与实际屏幕驱动必须分别确认。

## 缺口与获取方式

| 缺口 | 如何补齐 |
|---|---|
| 实物板卡版本和模组丝印 | 用户照片，对照B01；再下载匹配的原理图及模组datasheet |
| ST7789蓝板接头和电路 | 用户背面照片/卖家规格，不能套用其他厂家的显示模块供电设计 |
| DHT22红板电路和厂家资料 | 用户模块照片与商品资料；补充对应器件的厂家datasheet |
| SG90、WS2812版本和电源条件 | 商品资料、实物标记和必要测量 |
| 摄像头、音频扩展电路 | 摄像头/转接板型号、USB描述符和卖家原理图 |
| 咪头、喇叭、线材规格 | 原始商品规格和接头标记；无法确认时记录unknown |

## 获取记录

### 需求生成项目与仿真验证深入阅读

参见 [源码研究入口](research-20261026/README.md)：包含 Circuit Lab 和 circuit-synth 的固定提交源码摘选、程序框图及提示词分析，Wokwi diagram-lint 元件注册表、ST7789模型差异、官方DHT22/SSD1306场景和验证工具建议。未安装或运行外部项目；参考源码与许可保存在该目录的 `sources/`。

### 本次器件标准化补充阅读（2026-10-24）

以下在线源码在2026-10-24已阅读，未另存源码快照，当时记录于两份手工知识档案；旧knowledge已在2026-10-26按用户要求替换。以下链接保留为后续补充驱动资料的线索，不计入下述22项本地正文快照：

- [DHTtester](https://github.com/adafruit/DHT-sensor-library/blob/master/examples/DHTtester/DHTtester.ino)：DHT22初始化、2秒采样、NaN处理和接线原则；不是红板接头定义。
- [DHT.cpp](https://github.com/adafruit/DHT-sensor-library/blob/master/DHT.cpp)：MIN_INTERVAL及缓存行为。
- [Adafruit_ST7789.h](https://github.com/adafruit/Adafruit-ST7735-Library/blob/master/Adafruit_ST7789.h)：软件SPI构造函数和init接口。
- [ST77xx library.properties](https://github.com/adafruit/Adafruit-ST7735-Library/blob/master/library.properties)：直接依赖；完整依赖需由包管理器解析。

当前资料布局见 [器件知识入口](../LangChain/knowledge/README.md)。在线master链接可能变化；首次可复现构建前需锁定实际使用的库版本。本轮未编译或运行这些例程。

### Wokwi上游库与库存映射重建（2026-10-26）

已下载固定提交的全部146条diagram-lint注册定义、相关官方说明和S3/ST7789/SSD1306的board定义，共169份上游文件。版本、URL、获取时间、哈希和许可见 [sources.lock.json](../LangChain/knowledge/sources.lock.json)，每个已购器件的对应程度及缺口见 [覆盖清单](../LangChain/knowledge/COVERAGE_AND_GAPS.md)。docs使用官方站点对应的main提交，而非仓库API默认分支。导入完整性与映射检查通过，不等于编译/仿真通过；boards快照的再分发许可尚待核对。

### 仿真优先的资料补充（2026-10-26）

另新增临时240×240屏幕并补充现有9类硬件的接线、驱动和仿真限制，见 [补充资料说明](../LangChain/knowledge/supplements/README.md) 及 [补充来源锁文件](../LangChain/knowledge/supplements/sources.lock.json)。原始Wokwi快照不改动。注意本轮发现C10的usb_stream已标停止维护，官方推荐usb_host_uvc/usb_host_uac；旧接口限制不直接套用新驱动。模拟屏幕BL/部分命令未实现，S3仿真I2S未实现。所有这些结论均注明适用来源；未运行仿真。

共22项有效正文快照（A01–A04、B01–B02、C01–C10、T01–T06）。额外保留 `arduino-cli-compile-20261024.html` 作为最初的跳转页，不计入有效文档。该跳转最终指向已下载的1.5版文档。

最初不带版本的 Espressif user_guide.html 返回404，已改为实际存在的 user_guide_v1.1.html；旧ESP-IDF入口及尝试的docs.arduino.cc入口也返回404，未列为有效来源。未运行下载的代码示例，未修改任何本地凭据。
