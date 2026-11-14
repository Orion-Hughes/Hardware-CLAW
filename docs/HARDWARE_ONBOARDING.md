# 新硬件入库指南

一个 Wokwi 模型只说明我们有对应的仿真资料。要让 Hardware-CLAW 用它设计工程，还需要核对引脚、驱动和目标平台，并保留每一层的验证结果。当前默认构建基线为 ESP32-S3、PlatformIO `espressif32@6.12.0`、Arduino-ESP32 2.0.17。换开发板或框架后应重新验证。

## 1. 定义这次要支持的范围

- 写清器件型号、接口和用途：支持的是哪个 Wokwi 模型、哪个模块版本、哪些功能。相似型号的针脚、屏幕尺寸或供电不同，要明确差异。
- 优先在 `LangChain/knowledge/catalog.json` 的 `upstream_parts` 和现有文档快照中查找；复用已有文件。没有对应模型时记录缺口，不用近似元件冒充。
- `inventory.owned` 只记录持有情况。仿真参考卡不推断手上的实物接线或电气兼容。

## 2. 找齐资料，按原样保存

| 来源 | 至少核对什么 |
|---|---|
| Wokwi 模型定义和文档 | `part_type`、大小写完全匹配的引脚名称、必要属性及默认值；只有文档明确支持时才登记刺激或观测项。 |
| 厂家规格或模块原理图 | 有条件接实物时核对供电、信号电平、接口地址、上下拉、负载与引脚顺序。缺资料就标注适用范围。 |
| 框架或驱动维护者 | 实际使用的头文件、初始化与核心 API、合法参数、返回值和示例；区分框架内置、包管理器安装和本地驱动。 |

新增的上游原文放在 `LangChain/knowledge/upstream/`，保留适用的许可证；在 `sources.lock.json` 登记仓库、固定版本/提交和文件 SHA-256。仓库标签与 PlatformIO Registry 的发包记录是两件事；以实际安装结果确认可用版本。

## 3. 建立一张薄连接卡

在 `LangChain/knowledge/cards/<id>.json` 建立 v3 卡并登记到 `catalog.json` 的 `records`。字段以 `schemas/hardware-card.schema.json` 和 [读取服务](../LangChain/hardware_claw/catalog/README.md) 为准。

- `selection`：检索别名、用途、输入输出、接口、资源和限制。区分 I²C/SPI 的共享总线信号和设备独占引脚。
- `simulation`：从逻辑信号映射到模型端点。影响布线、程序或测试行为的参数要核对模型、属性与固件是否一致；被动器件不为满足格式虚填供电脚。
- `programming`：限定平台、声明头文件和依赖。`dependency_properties` 指向上游原版库清单；框架内置时依赖列表为空。本地驱动按现有宿主包清单管理，避免同时装同名上游库。
- `documents`：把模型、正式 API 与补充指引分开。必读只放完成布线/编程所需的小文件；长说明、可选示例设为 `reference`。指引写器件通用的约束和用法。
- `availability`：关键资料缺失时保留 `unreviewed` 或 `blocked` 并描述原因；资料齐备时可用现有 `documented_not_tested` 开放选型，编译、仿真、真机验证另记。该选型状态不会因为最小程序编译成功而改成“功能已验证”。

## 4. 依次检查并留下证据

1. **资料与读取**：检查 JSON、唯一 ID、登记路径、来源哈希、引脚/属性和文档链接。用生产查询接口查别名，并一次读取新器件和板卡，确认必要资料返回、共享资料去重、安装声明是预期的。若有必要续读，验证工具给出的 `next_reads`；不能把一次调通当作资料一定完整。
2. **安装与最小编译**：在 `temp/` 中开独立工程，用生成器的构建配置和依赖解析方式；从空的工程依赖目录构建。核对实际包身份、版本、传递依赖、安装警告和固件产物。最小程序要调用初始化和一个关键 API，不能只包含头文件。任何声明依赖缺失，即使编译器退出码为 0 也不能通过。
3. **原样生成和静态交付**：对一项包含新器件的代表性需求运行正常选型和生成流程。检查 Agent 用了对应卡、依赖和正确引脚，输出工程按原样通过静态检查和编译。若有编译错误，保留原始证据。
4. **仿真功能**：运行原样 Wokwi 工程，先检查正常运行，再将输入设为一个初始值并改变它，验证读数、输出或状态随之正确变化；适用时覆盖边界值、空闲/复位行为。证据可用串口、引脚、VCD 或画面，按功能选择。记录使用了手动方式或自动测试及模拟时间，未运行写 `not_run`。
5. **实物（适用时）**：按模块说明核对接线、电压和安全边界，再烧录与实测。样板成功只证明该模块、板卡和配置。没有器件就保留未测试。

从 `LangChain` 目录执行，例如（将尖括号内容换成对应硬件）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog search "<器件别名>"
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog read esp32_s3_devkitc1_n32r16v <器件ID>
.\.venv\Scripts\python.exe -X utf8 -B -m unittest tests.test_hardware_cards tests.test_hardware_catalog tests.test_hardware_bundles -v
```

每批至少留一条记录：硬件 ID / 模型、目标平台、实际包及版本、读取 / 编译 / 生成 / 仿真 / 真机结果、复现命令或日志路径、剩余缺口。临时工程与日志集中在根目录 `temp/`；Agent 正常生成的工程留在 `workspace/`。测试工程不作为生产 Agent 的参考答案。只有相应步骤实际通过，才能宣称该层已验证。

## 试点记录：轻触按钮与 BMP180

| 器件 | Wokwi 模型 | 最小构建 |
|---|---|---|
| `pushbutton_12mm` | `wokwi-pushbutton` | 通过。使用框架内置的 `INPUT_PULLUP` 与 `digitalRead()`，无需额外库。 |
| `bmp180` | `board-bmp180` | 通过。实际安装 Adafruit BMP085 Library 1.2.4、Adafruit Unified Sensor 1.1.15、Adafruit BusIO 1.17.4，并编译初始化和气压、温度读取 API。 |

- 两张卡均能通过别名命中，与目标板卡联合读取时无必要资料缺项。离线回归共 250 项通过。
- 试点需求：按下按钮时读一次气压和温度，按住不重复。真实选型阶段选择了两张新卡；生成阶段写出接线和固件后触及本次 16 万 token 测试上限，未完成检查和交付。将原始文件复制到 `temp/` 后独立编译成功；Wokwi lint 无错误，有两条模型标记提示。
- Wokwi CLI 免费 CI 额度耗尽，未运行功能用例。待验证：上电初始化，按下和释放各两次，改变传感器输入后核对测量结果，按住时无重复读数。未做真机验证。
- 本地复核：`temp/hardware-deps-20261114-122301/report.json`（安装及最小构建），`temp/hardware-onboarding/`（读取、模型调用、原始工程副本、独立编译及仿真拒绝日志）。
