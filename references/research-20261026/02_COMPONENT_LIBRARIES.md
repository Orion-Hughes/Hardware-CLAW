# 可用元件库：优先建立与 Wokwi 的对应关系

## 1. 最值得优先使用的来源

没有发现一个已核实可同时覆盖“商品模块、所有电气约束、驱动说明、仿真模型”的统一数据库。比较实际的做法是组合下面几类来源，通过小规模映射表连接，不从零收集全部元件，也不把 HTML 原样当成已验证的数据库。

| 来源 | 已核对的内容 | 适合解决的问题 | 不能代替 |
|---|---|---|---|
| [Wokwi diagram-lint](https://github.com/wokwi/wokwi-cli/tree/f23ed6fe2a8df332a9020fafb3c82b6ca95aa61c/packages/diagram-lint) | JSON type、pins、attrs、documented、category；独立规则检查器 | 生成合法 diagram，查模拟端点和属性 | 真实器件电气限值、模块接头顺序、行为模型实现 |
| [Wokwi boards](https://github.com/wokwi/wokwi-boards/tree/962b19d5636756537a93bb5337ac99abd775eae0) | board 定义、引脚到内部 chip 的映射、外观/显示区域等 | 补全 board-* 的定义，追踪模型来源 | 仿真引擎和全部真机兼容性 |
| [Wokwi 元件文档](https://docs.wokwi.com/parts/wokwi-dht22) + [part-tests](https://github.com/wokwi/wokwi-part-tests/tree/b224080de2c4fb54a420fd60a3daf1eb0fa2ab81) | 接线端点、初始属性、操作说明、测试工程和场景 | 驱动候选、输入注入、验证范例 | 当前本地版本已测试的保证 |
| [KiCad symbols](https://gitlab.com/kicad/libraries/kicad-symbols) | 标准符号与引脚描述；circuit-synth 从中解析 Pin 信息 | 后续原理图输出、针脚编号和电气类型 | 自动固件驱动、Wokwi 模型、所有模块电路 |
| [PlatformIO 板卡 JSON](https://github.com/platformio/platform-espressif32/blob/7afb0a703a5f6492fd695a4c2ced9ad843745280/boards/esp32-s3-devkitc-1.json) | MCU、框架、编译配置、上传与内存设置 | 固件构建目标的规范化 | 接口电气规则、采购板具体内存型号 |
| [Wokwi Elements](https://github.com/wokwi/wokwi-elements) | 可视化 Web Components；README 明确不含功能仿真 | 如果以后开发自己的连线编辑界面 | 不能把它当成离线 Wokwi 模拟引擎 |
| [modm-devices](https://github.com/modm-io/modm-devices) | 从厂家数据整理的 MCU 数据，README 列出 STM32、AVR、nRF、RP 等系列 | 以后扩展 MCU 型号、研究外设/引脚数据整理 | 当前 ESP32-S3 专用数据库；也不自动映射 Wokwi |

维护情况：查到 diagram-lint 在固定提交发布0.1.2，提交日期为2026-10-23；它有独立测试和同步脚本，值得优先评估，但仍是早期版本。其他项目的最近提交时间不等于每条元件资料都已核实。使用时固定版本，更新后跑回归工程。

## 2. diagram-lint：可以直接对接的机器可读资料

实际目录：

```text
packages/diagram-lint/
  src/registry/
    part-registry.ts
    part-definitions.ts
    parts/
      wokwi-dht22.json
      board-esp32-s3-devkitc-1.json
      board-st7789.json
      board-ssd1306.json
      wokwi-analog-joystick.json
      wokwi-servo.json
      wokwi-led-ring.json
      ...
  src/rules/
    invalid-pin.ts
    missing-component.ts
    duplicate-id.ts
    ...
```

[DHT22 原始记录](sources/wokwi-cli/packages/diagram-lint/src/registry/parts/wokwi-dht22.json)：

```json
{
  "type": "wokwi-dht22",
  "pins": ["VCC", "SDA", "NC", "GND"],
  "attrs": [
    {"name": "temperature", "type": "number"},
    {"name": "humidity", "type": "number"}
  ],
  "documented": true,
  "category": "sensors"
}
```

它能回答“端点叫 SDA 还是 DATA”“这个 part type 是否已登记”。它不能回答“红色三针模块接头的左右顺序”“是否自带上拉”。此外，**初始 attrs 与运行时 control 不是天然等价**：DHT22 的 temperature/humidity 恰好都有对应运行控制，需要用文档或场景确认，不能对所有属性自动推断。

[PartRegistry](sources/wokwi-cli/packages/diagram-lint/src/registry/part-registry.ts) 在内存中用 Map 保存条目，提供 `has`、`getPins`、`isValidPin`、`getAttributes`。也能读取官方 `boards.json` bundle，把 board ID 变成 `board-*` 类型并导入针脚。

对我们而言可分两步接入：

1. Python tool 读取固定版本的必要 JSON，返回器件与模拟端点。
2. 独立 Node 适配器调用官方 DiagramLinter，返回 `valid/issues`。不必把 TypeScript 规则全重写成 Python；也可以评估 CLI 的 lint 命令。

上面是建议，当前没有安装包或接入 Agent。

## 3. ST7789：需要记录的具体不匹配

[注册表条目](sources/wokwi-cli/packages/diagram-lint/src/registry/parts/board-st7789.json) 中有：

```json
{
  "type": "board-st7789",
  "pins": ["BL", "CS", "DC", "GND", "RST", "SCL", "SDA", "VCC"],
  "documented": false,
  "isBoard": true,
  "category": "boards"
}
```

继续读 [实际 board 定义](https://github.com/wokwi/wokwi-boards/blob/962b19d5636756537a93bb5337ac99abd775eae0/boards/st7789/board.json)，发现：

- 名称：`ST7789 1.54in Display`。
- 描述和显示尺寸：240×240。
- 内部芯片：`github:Whiteeeey/chip-st7789@1.0.0`，即引用第三方仿真芯片。
- `SCL`、`SDA` 等板上端点映射到内部 `chip:SCL`、`chip:SDA`。

现有采购档案记录的是2英寸240×320 SPI蓝板。因此我们现在能得出的结论是 **找到同控制器的候选模拟模型，但尺寸不一致，兼容性未测**。应核查模型命令覆盖、窗口地址偏移、旋转、初始化和 framebuffer 读取，不应把240×240截图通过标记成240×320实物通过。

另外，ST7789 模块把 SPI 时钟/数据标作 SCL/SDA 并不表示它采用 I²C。映射必须同时考虑协议。

## 4. PlatformIO 默认板型也不能等同采购板

已读 `esp32-s3-devkitc-1.json` 的名称明确写：

> Espressif ESP32-S3-DevKitC-1-N8 (8 MB QD, No PSRAM)

其中 flash_size 为8MB。它不直接代表库存中记录的 N32R16V。我们应分别存：Wokwi 模拟 board type、PlatformIO 构建目标/覆盖项、实际模组参数。不能只凭三者都叫 ESP32-S3 就合成一条完全兼容记录。

## 5. 建议的最小映射，不重做大数据库

下面为研究提案，不是当前知识 JSON 已经具备的新 schema：

```json
{
  "component_family": "DHT22",
  "hardware_variant": "red_module_variant_unconfirmed",
  "simulation": {
    "backend": "wokwi",
    "part_type": "wokwi-dht22",
    "signal_to_pin": {"POWER": "VCC", "DATA": "SDA", "GROUND": "GND"},
    "unused_model_pins": ["NC"],
    "controls": ["temperature", "humidity"],
    "registry_commit": "f23ed6fe2a8df332a9020fafb3c82b6ca95aa61c",
    "validation_state": "source_checked_not_run"
  },
  "physical_connector_order": null
}
```

这里最重要的关系是：

```text
真实模块/型号资料 → 逻辑信号 DATA
                        ↓ 适配映射
                 Wokwi 端点 dht:SDA
                        ↓ 项目分配
                 某个已确认可用的 MCU GPIO
```

同时给 firmware generator 使用同一份 GPIO 分配，避免 diagram 接GPIO4、源码却读取GPIO5。这只需要小型连接数据，不要求先建大型 Project IR。

仿真引脚合法、电气兼容、实物接头顺序是三个不同状态。不能因为 registry 找到了端点，就自动把硬件档案的 `verified_for_wiring` 改成 true。

## 6. 补充库与许可边界

- KiCad 当前官方符号库在 GitLab，旧 GitHub README 明确提示迁移。库许可为 CC-BY-SA 4.0 附设计产物例外；复制/改造库集合与生成自己的设计文件不是同一许可场景。[许可原文](https://gitlab.com/kicad/libraries/kicad-symbols/-/blob/master/LICENSE.md)。
- modm-devices README 声明 MPLv2，说明数据生成与每周 CI 核对。其当前范围已超出标题里的 AVR/STM32，但所列设备表没有 ESP32。它适合后续 STM32/RP 等方向，当前不必为了 ESP32-S3 全量导入。
- Wokwi Elements 的 MIT 许可不覆盖整个 Wokwi 商业模拟服务；显示组件代码和仿真服务应分开理解。
- part-tests 和 boards 本轮未确认独立 LICENSE；先作为文档和设计参考，正式复制分发前核查对应授权。

**建议优先级：**diagram-lint + 官方 DHT22 文档/测试 → 小型硬件映射 → PlatformIO 构建参数 → ST7789 模型差异测试。KiCad 和更大 MCU 数据库放在后续扩展阶段。
