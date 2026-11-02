# Wokwi 兼容硬件资料库调研

调研日期：2026-11-02。范围：联网检索、读取仓库源码及数据样本；没有运行任何第三方代码、器件仿真、编译或 LLM API。生产知识库及工具未修改。

## 结论

在本次检索和抽查的公开项目中，尚未找到同时满足“广泛覆盖 Wokwi 元件、准确端点与属性、完整电气参数、板卡适配、正式驱动 API、持续维护”的单一数据库。

建议采用 Wokwi 官方元件定义作为基础，关联官方说明、板卡定义和驱动维护者资料。保留上游文件原文；本地只维护必要的关联、适用范围、采购变体及确实缺失的有来源信息。这不是重新发明元件目录。

## 候选来源与实际内容

| 来源 | 本次快照范围 | 实际提供 | 缺口与采用建议 |
| --- | --- | --- | --- |
| [Wokwi CLI diagram-lint](https://github.com/wokwi/wokwi-cli/tree/f23ed6fe2a8df332a9020fafb3c82b6ca95aa61c/packages/diagram-lint/src/registry/parts) | 146 个元件定义 JSON | type、pins、attrs、属性类型/部分枚举、documented、分类、isBoard | 作为端点和类型基础；不是 146 种硬件均经功能验证，也不包含完整驱动与电气知识 |
| [Wokwi Docs](https://github.com/wokwi/wokwi-docs/tree/f1f6736158d4473ff64f60e25e9fa128f5df3a7d/docs/parts) | 70 篇元件 Markdown | 功能、针脚含义、属性默认值、模拟行为、部分协议/地址、库推荐和示例链接 | 最重要的使用说明来源；各页详略不同，不保证每个模型都有专页 |
| [Wokwi Boards](https://github.com/wokwi/wokwi-boards/tree/962b19d5636756537a93bb5337ac99abd775eae0/boards) | 56 个 board.json | 引脚到 MCU/芯片的映射、部分 MCU/FQBN、内部芯片、显示尺寸、坐标和外观 | 补充板卡和组合模块；文件中存在尾逗号，不能假设所有原文都是严格 JSON；采购变体规格另查 |
| [Wokwi Elements](https://github.com/wokwi/wokwi-elements/tree/5178c0cc1b455719fdf562169293797e29d73dac) | 前端元件实现 | SVG、pinInfo、坐标、部分信号标记、可视属性 | README 明确仅提供外观，不包含功能仿真代码。不能用可视元素存在来判定仿真支持 |
| [Wokwi Library Index](https://github.com/wokwi/wokwi-library-index/tree/813cd4fdb14dde90654759f0023abbb46f9d9fd4) | 10,308 个软件库名称 | Arduino 库名集合 | update.js 从 Arduino 官方 library_index.json 只提取名称；不提供 API、版本或硬件到库的映射，不证明库在特定 MCU 上可用 |
| [Velxio](https://github.com/davidmonterocrespo24/velxio/tree/7a060cbdf730ebda1529f438276ef03752ab10c9) | 157 条组件元数据 | 名称、分类、描述、标签、属性、默认值、pinCount 等 | 自有仿真器和扩展，不是可原样替换的 Wokwi 库；抽查 DHT22 的 pinCount=0、properties=[]，详细编程资料并不完备 |
| [CircuitMind](https://github.com/Piyush-Thakkarr/circuitmind/tree/05f3d5e83326efae78619461fe5dc54b8f41deab) | 29 条元件 | 从 Wokwi lint 探测出的端点，配人工一行说明 | 可参考维护方法，但范围比官方注册表小，缺少系统化驱动/API 资料；lint 接受不等于仿真通过 |
| [CircuitLM](https://github.com/Khandakar227/circuitlm/tree/a5648880dc8e613a2a8741fa6f7f8d6af0274a48) | 73 条元件 | pins、aliases、description、category、typical_usage、compatible_with、specs、图形尺寸 | 可参考搜索字段；端点不是 Wokwi 原样兼容，规格描述也缺少逐字段来源，不建议作为基础事实库 |

以上数量是文件/目录条目统计，不代表独立器件型号数、实际可用数或验证通过数。

其他搜索结果包括 bw-parts（侧重 SVG、端点坐标及部分额定值）、SparkPlan（其 README 明示未实现 Wokwi 仿真）、散落的 Wokwi 自定义芯片仓库。本轮没有发现它们提供更完整且可直接使用的 Wokwi 硬件总库。

## 样本核对

### DHT22：官方资料比单纯注册定义丰富

[官方说明](https://docs.wokwi.com/parts/wokwi-dht22)包含：

- 元件端点 VCC、SDA、NC、GND，其中 SDA 是双向数字数据脚。
- temperature、humidity 属性及默认值 24°C、40% RH。这些是模拟初值，不是验收预期。
- 运行时通过界面改变温湿度的方式。
- ESP32 推荐使用 DHT sensor library for ESPx 的明确提示与示例链接。

单纯读取注册 JSON 只能取得端点和属性类型，会丢失库推荐、使用说明等关键内容。还需关联驱动维护者文档、正式 API 和版本；不能从端点 SDA 推断其是 I²C 设备。

CircuitLM 的 DHT22 条目使用 DATA，而官方 Wokwi 定义使用 SDA。直接拿它生成 diagram.json 会存在端点不匹配风险。该条目的 compatible_with 字符串也不能作为完整板卡适配证明。

### ST7789：收录不代表采购模块完全匹配

[官方板定义](https://github.com/wokwi/wokwi-boards/blob/962b19d5636756537a93bb5337ac99abd775eae0/boards/st7789/board.json)描述 240×240 屏幕，并引用第三方 `github:Whiteeeey/chip-st7789@1.0.0`。

[芯片维护者说明](https://github.com/Whiteeeey/chip-st7789)也以 240×240 为目标，BL 背光标注尚未实现。采购记录为 240×320；必须保留两者差异，不能自动覆盖真实规格。本轮没有运行该模型，也未重新验证驱动初始化参数。

### Velxio：导入导出格式相似不等于逐元件兼容

其 `frontend/src/utils/wokwiZip.ts` 对原生板与 `board-velxio-*` 板型分开处理，注释说明不同板卡端点命名可能不同；`component-metadata-generator.md` 还描述自有属性覆盖。DHT22 的简短说明推荐其他驱动，并不包含 Wokwi 官方针对 ESP32 的同一推荐。因此不能把这套数据整体认定为 Wokwi 官方行为说明。

## 对采购硬件的覆盖

| 采购对象 | 可采用的 Wokwi 信息 | 必须保留的边界 |
| --- | --- | --- |
| ESP32-S3 DevKitC-1 N32R16V | DevKitC-1 板定义、GPIO 映射、ESP32 指南 | 模拟板型与采购 Flash/PSRAM 变体、烧录配置分开 |
| DHT22 红板 | DHT22 模型、官方说明、推荐驱动入口 | 模拟裸传感器端点不代表红板实际针序与板载上拉 |
| ST7789 240×320 | 已收录的 240×240 第三方模型 | 分辨率不同；另列仿真变体 |
| WS2812 8 灯灯环 | LED ring 模型、pixels 属性、NeoPixel 驱动入口 | 采购 8 灯与上游默认灯数分开，实物电气规格另核对 |
| SG90 舵机 | 通用 servo 模型和 PWM 使用说明 | 模型不证明实物电流、精度或机械行程 |
| PS2 摇杆 | analog-joystick 模型和模拟/按键端点说明 | 实物接头顺序另核对 |
| USB 摄像头 | 本轮未找到可直接对应采购 UVC 摄像头的完整现成模型资料 | ESP32-CAM 板型不是 USB 摄像头替代品 |
| 裸驻极体咪头 | 注册表存在未正式文档化的 microphone 条目 | 不能据此宣称已覆盖该咪头及偏置、放大、采样电路 |
| 8Ω/1W 扬声器 | 本轮未找到对该扬声器和功放链路的完整对应资料 | buzzer 不等同采购扬声器 |

面包板和两类连接线沿用用户此前“不纳入程序硬件库”的范围决定，不重新添加。

## 后续资料格式的依据

标准化应是这些来源的组合视图，至少区分：

1. **Wokwi 定义**：官方 type、端点、attrs、模型来源和文档状态。
2. **使用说明**：针脚角色、协议、地址、初始化、读写、单位、时序、错误处理；引用原文而不是为每个工程写修复教程。
3. **驱动与构建**：库标识、固定版本、正式头文件/API、依赖、框架适用范围和官方示例。
4. **实物与变体**：采购身份、电气限制及与模拟模型的差异；未知项显式保留。
5. **资料来源与验证状态**：固定提交、文件哈希、出处、覆盖范围；文档存在不等于器件仿真或真机通过。

只从官方元件目录和说明生成视图仍不足以自动生成可靠固件；必须补上器件与驱动的关联。Wokwi Library Index 可用于确认名称，版本和 API 应从 Arduino 官方索引与驱动维护者获取。

下一步才是确定采用的来源、标准化首批器件、编写批量读取接口。器件使用验证继续留到后续阶段。本轮没有实现这些功能。

## 调研证据位置

仓库元数据、完整文件树及抽查原文保存在根目录 `temp/hardware-library-research/`，仅作为临时研究资料，不进入 Git。正式资料入库时应重新生成可追溯来源清单，不能把本轮临时目录变成运行时依赖。
