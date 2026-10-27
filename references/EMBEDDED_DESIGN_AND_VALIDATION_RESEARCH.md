# 需求驱动嵌入式设计与仿真验证：第一轮调研

调研日期：2026-10-26。范围：后续计划第1项——研究现有项目如何管理硬件知识、生成电路、校验正确性。

方法：GitHub仓库搜索、维护者README、关键源码和官方文档阅读。没有安装或运行这些项目，没有调用付费模型，没有验证它们的宣传成功率。本报告中的“源码可见”不等于本地复现成功。链接多指向可变的main/master分支；正式复现前应固定提交及依赖版本。

> 深入源码后的补充与修正：见 [第二轮详细报告](research-20261026/README.md)。circuit-synth 的 Component 实际调用 `kicad/kicad_symbol_cache.py`，其若干内部 Agent 入口仍有关键词模板、连线 TODO 和缺失模块引用，不能视为已完成的 LLM 闭环。另找到 Wokwi 官方 diagram-lint 的 JSON 元件注册表；其中有 ST7789，但对应 board 定义是第三方 240×240 模型，不等同采购的240×320屏幕。

## 1. 结论先行

1. 已找到直接从自然语言生成Wokwi工程的小型项目，以及AI辅助生成KiCad电路的项目，但本轮未找到并验证一个能直接覆盖我们全部需求的成熟系统。
2. 比较有参考价值的实现通常把“器件库/模型”“电路连接”“图形布局”“测试结果”分开。数据库不一定是SQL：元件库文件、带版本的模块包、JSON/YAML元数据和文档检索库各司其职。
3. 电路生成首先是生成连接关系，不是画图片。之后由确定性程序生成Wokwi diagram、原理图或PCB；PCB铜线布线又是另一层任务。
4. 正确性需要分层证明：格式和连接有效、规则满足、固件编译、场景行为符合要求、实物适用性。任何单层通过都不能替代其他层。
5. 建议重点学习 circuit-synth 的元件查询/网络/工具封装，atopile 的模块与约束，Wokwi 的可执行场景，以及固件测试研究中的错误注入和结果协议。暂不引入整个PCB设计工具链。

## 2. 项目对比

| 项目/方案 | 定位 | 硬件资料怎么管理 | 电路怎么生成 | 正确性怎么检查 | 对我们的用途 |
|---|---|---|---|---|---|
| Circuit Lab / llm-circuit-builder | 自然语言生成Wokwi工程的小型浏览器原型 | 常见板卡/元件名称、针脚写在system prompt里；未见独立硬件数据库 | LLM直接输出含diagram.json和源码的JSON文件集合 | JSON解析、有限编译路径、串口观察；所读流程未见独立自动功能断言 | 学习最小交互，不作为可靠数据库/验证方案 |
| circuit-synth | Python描述电路，结合AI工具生成KiCad工程 | 解析KiCad符号库，缓存针脚、datasheet等；另有供应链搜索模块 | Component、Net、子电路函数，经生成器导出KiCad | 语法/运行检查、KiCad ERC接口；有仿真模块但部分测试台实现未完成 | 很适合学习Python工具边界和复用元件库 |
| atopile | 声明式电路语言与编译器，可由AI编写 | 标准库、registry模块包、版本依赖、具体供应商零件资产 | .ato模块实例及接口连接，编译到KiCad工作流 | 单位、范围、方程和assert约束；不能替代固件运行测试 | 学习接口级连接和可计算约束 |
| tscircuit | TypeScript/React电路描述及生成工具 | registry复用组件；Circuit JSON分离逻辑/原理图/PCB对象 | TSX组件与连接，经core生成Circuit JSON，再渲染或导出 | Schema、连接/引脚规则及单元测试；另有SPICE转换生态 | 学习图形与逻辑分离、结构化诊断 |
| Wokwi CLI + Automation | 嵌入式固件仿真及场景测试，不是需求生成器 | 部件类型/引脚/controls定义与文档；项目存parts、attrs和connections | 消费diagram.json，不替Agent决定完整设计 | lint、输入注入、串口匹配、引脚断言、截图比较等 | 当前最直接的仿真验证路线 |
| llm-firmware-testing | LLM生成固件测试的研究原型 | module.yaml记录测试模块的设备/引脚/依赖；文档RAG另存 | 使用基准项目电路，不以自动电路设计为主 | 编译、avr8js/Wokwi/真机后端、串口协议、变异测试 | 学习适配器、判定器和测试有效性评价 |
| Renode + Robot Framework | 自动化固件/系统测试平台 | 平台描述和外设行为模型；不是采购器件库 | 平台描述配置模拟设备和连接，不是生成PCB | UART/网络断言、虚拟时间、重置、报告、失败快照 | 学习测试组织；其他开发板及板间通信可进一步评估 |

上述项目并非都自带“自然语言到完整嵌入式系统”的Agent；区分生成应用、设计后端与验证后端，是本轮比较的重要前提。

## 3. Circuit Lab：最接近我们交互目标，但验证很薄

仓库：[PythonicVarun/llm-circuit-builder](https://github.com/PythonicVarun/llm-circuit-builder)。已读README、llm.js、build.js及app.js关键路径。

### 数据管理

`llm.js` 的SYSTEM_PROMPT直接列出常见开发板、元件类型、引脚和Wokwi格式。例如DHT22被描述为VCC/SDA/NC/GND。不是从数据库查询后注入，而是维护一段大提示词。会话与工程版本使用浏览器localStorage保存，这也不是硬件知识数据库。

### 电路生成

要求模型返回一个wokwi-project代码块，内部包含files字典及start参数。files中保存diagram.json、sketch.ino等字符串。宿主提取JSON，上传文件并调用嵌入式Wokwi接口，串口输出显示在页面中。

### 校验和实际限制

- `extractProject()` 主要检查JSON可解析且files为对象，不是完整schema、电气或功能验证。
- `build.js` 的板卡映射仅包含AVR Uno/Mega/Nano/ATtiny85。文件明确说明不提供ESP32/Pico Arduino编译器。
- 但 `llm.js` 提示词仍写ESP32/Pico Arduino可以在浏览器编译；存在提示词与实现不一致。不能据README或提示词认定支持ESP32-S3端到端生成。
- 所读运行流程把串口输出呈现给用户，未看到需求级断言、自动测试判定与修正闭环。
- 使用experimental embed路径，稳定性与适用条款应另行核查；我们的自动化优先看官方CLI。

借鉴：输出多个工程文件的交互和工程版本保存。避免照搬：提示词硬编码全部器件、只做JSON.parse、把运行状态当成功能正确。

源码：[llm.js](https://github.com/PythonicVarun/llm-circuit-builder/blob/master/llm.js)、[build.js](https://github.com/PythonicVarun/llm-circuit-builder/blob/master/build.js)、[app.js](https://github.com/PythonicVarun/llm-circuit-builder/blob/master/app.js)。

## 4. circuit-synth：复用元件库，用代码连接电路

仓库：[circuit-synth/circuit-synth](https://github.com/circuit-synth/circuit-synth)。README提供ESP32-C6开发板生成示例，并描述需求到电路代码的AI工作流。生成工程和可制造/功能正确不是同一项保证。

### 数据管理

仓库存在多套符号缓存相关代码。深入调用链后确认：`Component` 实际使用 `kicad/kicad_symbol_cache.py` 中的 `SymbolLibCache`，查找和解析真实KiCad库，维护内存索引、磁盘JSON缓存及源文件哈希，再据符号数据构建Pin对象。此前重点阅读的 `core/symbol_cache.py` 中也有SymbolDefinition等结构，但不应将它直接等同Component主调用路径。核心借鉴仍是复用现有符号资料，而非要求用户为每种零件重新手填所有针脚。

供应商查询与符号库是不同层：仓库另有JLCPCB、DigiKey相关代码入口，本轮未逐项验证供应商接口、数据完整性或可用性。符号信息也不自动包含所有电气极限、模块接线说明或Wokwi行为模型。

### 生成方式

Component选择库符号和封装，Net表示电气网络，`component[pin] += net`把具体针脚加入网络；子电路可封装成函数。随后生成KiCad工程。应借鉴的是“明确连接关系后再输出”，而不是让LLM直接画图。

### 检查方式与发现的边界

- `simple_validator.py`做AST语法、导入、结构和子进程执行检查，并设置超时与尝试上限。它主要证明设计代码可执行，不证明电路功能正确。
- 其所谓isolated execution实际可见的是普通子进程，不是安全沙箱；不能直接在不受限环境执行模型生成代码。
- `quality_assurance/erc.py`调用kicad-cli sch erc，读取JSON报告，封装violation、severity、component、pin等，并设置30秒执行超时。需要匹配KiCad版本核验真实报告格式，不能仅凭封装名称相信其解析正确。
- `simulation/testbench.py`包含测试台生成结构，但 `_add_signal_source()` 与 `_add_load()` 仍为pass。不能把自动测试台描述视为完整可运行的仿真闭环。

对HW-CLAW：复用库 + 查询工具 + 连接模型 + 结构化检查返回，值得学；直接搬整个框架与“自动验证已完成”的宣传，不建议。

源码：[symbol_cache.py](https://github.com/circuit-synth/circuit-synth/blob/main/src/circuit_synth/core/symbol_cache.py)、[simple_validator.py](https://github.com/circuit-synth/circuit-synth/blob/main/src/circuit_synth/ai_integration/validation/simple_validator.py)、[erc.py](https://github.com/circuit-synth/circuit-synth/blob/main/src/circuit_synth/quality_assurance/erc.py)、[testbench.py](https://github.com/circuit-synth/circuit-synth/blob/main/src/circuit_synth/simulation/testbench.py)。

## 5. atopile：以接口和约束描述设计

仓库：[atopile/atopile](https://github.com/atopile/atopile)。这是设计语言/工具链，不是现成的通用固件Agent。

### 数据管理

- `ato.yaml`记录工具要求、构建入口及registry依赖版本。
- ESP32示例从包导入USB连接器、LDO和ESP32-C3模块，而不是每次重新描述所有针脚。
- 具体零件文件可包含manufacturer、partnumber、supplier ID、datasheet、symbol、footprint、3D model以及来源checksum。
- 阅读到的电阻零件包明确保存EasyEDA来源和LCSC编号，说明其做法是复用既有零件资产，再加机器可读的身份关联。

### 生成与验证

模块间通过电源/USB等接口连接，底层再解析成具体端口关系。方程示例用带单位、容差和范围的assert约束分压电路，而不是只在注释里写“约3.3V”。编译器根据已编码的模型和约束进行求解/检查，不能证明任意未建模的物理行为。

源码例子有一个值得注意的错误：esp32_minimal.ato的说明字符串写S3，但实际导入、实例化的是ESP32_C3_MINI_1。我们应以实例和依赖为准，不照抄注释。

对HW-CLAW：先借鉴“接口有类型、参数有单位/范围、规则可执行”和可复用模块；无需现在就引入整套语言或把Project IR提升为核心。

证据：[ESP32实例](https://github.com/atopile/atopile/blob/main/examples/esp32_minimal/esp32_minimal.ato)、[依赖配置](https://github.com/atopile/atopile/blob/main/examples/esp32_minimal/ato.yaml)、[方程与约束](https://github.com/atopile/atopile/blob/main/examples/equations/equations.ato)、[具体零件资产](https://github.com/atopile/atopile/blob/main/examples/esp32_minimal/parts/UNI_ROYAL_0402WGF1002TCE/UNI_ROYAL_0402WGF1002TCE.ato)。本轮README中的两个旧文档链接返回404，因此上述判断主要基于仓库源码。

## 6. tscircuit：将电气关系与画面表示分离

仓库：[tscircuit](https://github.com/tscircuit/tscircuit)、[Circuit JSON](https://github.com/tscircuit/circuit-json)、[core](https://github.com/tscircuit/core)。它是适合AI编写的电路代码后端，不等于已经有完整的需求到固件Agent。

### 数据与生成

可复用电路作为registry包；TypeScript/React代码经过core变成Circuit JSON。该格式以带ID和引用的对象区分source_component/source_port/source_net、schematic对象、pcb对象。逻辑上同一个元件，可以有多种图形表示，不应把图形坐标和电气连接混为一谈。

Circuit JSON用Zod定义结构，提供类型和解析能力；设计为可与SQL互操作，不代表我们必须安装SQL数据库。它也不是已经收集完所有器件使用说明的“万能硬件数据库”。

### 校验

源码中存在引脚属性、供电/地定义、欠缺规格等检查入口。已读一个具体单元测试：为两个针脚设置mustBeConnected却不连线，调用checkPinMustBeConnected后断言返回两个错误，并包含component/port标识。这里的校验是程序规则，不是另问LLM一句“对不对”。

对HW-CLAW：最值得借鉴的是有稳定ID的诊断，以及把连接数据、展示布局、器件资料分开；当前阶段不必采用完整Circuit JSON或PCB自动布线生态。

证据：[数据格式](https://github.com/tscircuit/circuit-json/blob/main/README.md)、[必须连接的引脚测试](https://github.com/tscircuit/core/blob/main/tests/components/normal-components/chip-must-be-connected-error.test.tsx)、[引脚规格检查](https://github.com/tscircuit/core/blob/main/lib/components/base-components/NormalComponent/NormalComponent_doInitialSourcePinSpecificationChecks.ts)。

## 7. Wokwi：最贴近我们近期目标的执行验证

### 数据与电路

`diagram.json`中parts描述元件实例、类型、位置和attrs；connections描述partId:pin之间的连线。型号/针脚定义来自仿真部件体系，不是每个项目重复定义。官方CLI文档说明lint会获取registry定义来检查部件与针脚。

这支持我们采用“小范围可支持部件集合 + 官方类型映射 + 程序生成diagram”的路线，但不代表存在可直接下载且覆盖全部现实器件的开放数据库；第二项调研仍需单独研究访问方式、维护和许可。

### 验证能力（官方文档，不是本地已复现）

- `wokwi-cli lint`：未知part type、无效引脚连接、重复ID等结构问题。不能当成全面电气安全分析。
- 场景YAML：`set-control`修改传感器/按钮，`delay`等待，`wait-serial`匹配输出，`expect-pin`检查引脚。
- `take-screenshot`可保存或与基准图比较，适合受支持显示元件的显示验证；截图可用性和基准稳定性需实际测试。
- CLI支持串口日志、仿真时限、期待/失败文本、逻辑分析仪VCD等。仿真时限之外，调用方仍需墙钟超时和取消机制。
- 当前文档说明场景API仍是alpha；0.22.1起set-control/expect-pin使用name替代旧control/pin字段，旧字段仍支持。实现前应固定版本核验，不能凭历史示例猜字段。

### 适用于DHT的最小验证设计

以下是测试计划，不是本轮已执行结果：

1. 检查电路DATA连接与固件DHT_PIN一致，而不只检查该GPIO存在。
2. 注入一组温湿度，等待采样后匹配数值；再注入第二组，排除代码只打印常量。
3. 对“高温报警”案例加入低于阈值、等于阈值、高于阈值及回落场景；边界规则由需求确定。
4. 报警通过输出引脚或受支持外设状态验证，不能只相信程序打印“报警成功”。
5. 显示测试单独做截图或其他外部观察，不能把串口数值正确当成屏幕内容正确。
6. 每个场景设时限；区分test_failed、timeout、tool_error，不自动修改验收标准迎合生成结果。

资料：[diagram格式](https://docs.wokwi.com/diagram-format)、[CLI](https://docs.wokwi.com/wokwi-ci/cli-usage)、[自动化场景](https://docs.wokwi.com/wokwi-ci/automation-scenarios)。

## 8. llm-firmware-testing：验证测试本身能否发现错误

仓库：[SherAlex1998/llm-firmware-testing](https://github.com/SherAlex1998/llm-firmware-testing)。这是个人研究项目，不是成熟产品；本轮只核查公开代码，不复述其README实验数字为已验证结论。

### 数据组织

`benchmark/.../module.yaml`包含来源、许可、backend、固件函数、库版本、device的Wokwi类型/id/pins/attrs等。文档RAG单独放kb。它将“结构化执行信息”和“解释性文档检索”分开，值得我们借鉴。

但这些是适配过的基准模块，不是自动生成完整电路的通用硬件数据库。读到的恒温器样例还通过包装函数和shadow buffer暴露LCD内容，这验证的是应用写出的字符串，不自动证明显示器物理输出。

### 可调用仿真与判定

`backends.py`统一ExecResult：verdict、tests、serial_log、backend、duration_s、exit_code、error、retries。后端可选择avr8js、Wokwi或真机。

`run_wokwi.py`准备固件、ELF、diagram和wokwi.toml，调用CLI，记录串口日志；设置仿真时限和独立子进程时限，并区分云端故障重试与固件超时。

`protocol.py`解析 @RUN_BEGIN、@TEST PASS/FAIL、@RUN_END。没有结束标记判超时，零测试不能判通过。但仍应注意：当前解析逻辑会相信结束摘要中的计数，未充分核对逐条记录是否一致。我们若借鉴，应加强完整性检查，并防止被测程序自己打印PASS绕过外部验证。

README描述变异测试：正常程序通过后，对注入错误的版本重复运行相同测试，观察是否能发现错误。本轮核查了相关模块路径与运行后端，未复现实验、审核全部变异算子或验证报告统计。

对HW-CLAW：借鉴固定测试、结构化结果、错误注入、运行证据和成本/耗时记录。应同时区分测试错误、生成代码错误、工具失败与等价变异，不能把所有失败归为同一种“发现bug”。

源码：[module.yaml示例](https://github.com/SherAlex1998/llm-firmware-testing/blob/main/benchmark/ds18b20_thermostat/module.yaml)、[后端接口](https://github.com/SherAlex1998/llm-firmware-testing/blob/main/framework/harness/backends.py)、[Wokwi适配器](https://github.com/SherAlex1998/llm-firmware-testing/blob/main/framework/harness/run_wokwi.py)、[串口判定](https://github.com/SherAlex1998/llm-firmware-testing/blob/main/framework/common/protocol.py)。

## 9. Renode：借鉴测试框架，不急于替换Wokwi

[官方测试文档](https://renode.readthedocs.io/en/latest/introduction/testing.html)展示Robot Framework集成：通过renode-test启动模拟器、执行测试、输出可解析XML及HTML报告。测试可等待UART输出、发送串口输入、检查网络数据包、重置仿真、重复执行以及保存失败状态。

阅读的[STM32F4 Discovery测试](https://github.com/renode/renode/blob/master/tests/platforms/STM32F4_Discovery.robot)不仅等待Alarm文本，还检查虚拟时间为2/4/6/8秒，之后验证UART静默。这体现“输出内容 + 时间 + 不该发生的行为”三个维度，而不是仅找到一个成功字符串。

Renode的平台/外设模型描述的是模拟硬件，不是元件采购或管脚使用知识库。尚未核查我们ESP32-S3及全部外设的适配，因此不推荐立即替换现有仿真。后续如选择受支持的STM32/RISC-V等平台或研究板间通信，可进一步评估。

## 10. 对我们当前设计的具体启发

### 数据管理：先明确职责，不急于选择数据库产品

建议区分四种数据：器件型号与管脚事实、可复用接线/驱动方案、具体项目实例、执行与测试证据。说明文档可检索，数值和连接检查则应读取结构化字段。我们当前DHT JSON混合了其中几类信息，先作为试验，不急于扩大手填规模。

### 电路生成：逻辑连线优先

Agent选择器件并提出端口连接，程序检查端口存在性、GPIO占用、电源/逻辑兼容以及代码与连线一致性，然后输出diagram和说明。显示布局可独立处理。基于PCB工具的铜线自动布线目前不属于MVP必需项。

### 校验：让每个结果说明“检查了什么”

| 层次 | 应检查的内容 | 不能据此声称 |
|---|---|---|
| 结构检查 | 格式、元件ID、端口存在、引用有效 | 电气和功能必然正确 |
| 规则检查 | GPIO能力/冲突、电压规则、必须连接端子 | 真实时序或长期稳定性通过 |
| 构建检查 | 编译/链接、依赖、资源用量 | 程序符合需求 |
| 行为检查 | 输入变化、输出、边界、时间、错误处理 | 所有未测场景正确 |
| 电气/实物验证 | 适用的SPICE分析或真机测量 | 模型未覆盖效应也被证明 |

固定需求与独立验收用例，不允许修复Agent随意改宽容差、删除断言或将失败测试排除。LLM交叉审查是补充，不能替代执行证据。Harness记录Token、分阶段时间、版本、轮数和退出原因，并限制总预算、工具时限和无进展重试。

## 11. 下一步阅读顺序

1. circuit-synth的symbol_cache.py：学习现有库如何变成可查询的针脚资料。
2. circuit-synth的Component/Net例子 + atopile的模块依赖：理解连接生成与复用。
3. Wokwi官方场景：用DHT验证一次输入改变能否被固件正确读取；这是后续实施建议，不是本轮已执行。
4. llm-firmware-testing的backends.py、run_wokwi.py、protocol.py：设计我们的可调用仿真接口和严格结果判定。
5. 给一个已通过的案例注入阈值错误、引脚错误或卡死，确认测试确实能失败。

第2项“现成硬件数据库专项筛选”仍待开展：本轮只是发现KiCad库、atopile包、tscircuit registry、Wokwi部件体系等入口，未完成覆盖率、授权和接入成本评估。第3项仿真模块尚未在本轮实现。
