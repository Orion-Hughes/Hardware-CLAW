# 资料维护与统一补充格式

本轮只增加生成所需的少量配置和使用规则，引用原文，不重新编写每个器件的完整说明书。原始`upstream/`及其锁文件没有改动。

## 读取方式

`catalog.json → owned条目 → 原始引脚/属性定义 + 本地补充 + 公共S3配置`。

本轮owned目录的10个JSON使用schema_version=2，以下三组字段结构一致；历史SSD1306参考保留schema_version=1。未来读取器需识别版本，不把目录名当库存状态。

| 字段 | 作用 |
|---|---|
| electrical_profile | scope、supply_v、logic_v、rules、source_refs；未知值保持null |
| driver_profile | scope、framework、dependencies、headers、initialization、operations、example_refs、constraints、source_refs |
| generation_profile | target、build_profile_ref、status、blockers、pin_requirements、controls、manual_checks、limitations、source_refs |

`source_refs`和`*_ref`均相对knowledge根目录。库例程保留原文，只在JSON中给出需要使用的接口及模块差异；`PIN_*`是工程引脚分配占位符，不能直接复制后声称可编译。

生成状态只有资料级`documented_not_tested`或`blocked`；实际编译/仿真/真机状态独立，当前未运行。查询服务尚未实现；本轮只是准备其输入，不改变Agent权限。

## 共用内容只保存一份

[esp32_s3_simulation.json](esp32_s3_simulation.json)记录仿真构建基线、GPIO策略和diagram实际端点。暂选PlatformIO espressif32 6.12.0 / Arduino-ESP32 2.0.17，供后续复现；未改现有工程或安装版本。

这个PlatformIO板型原文是N8/8MB/无PSRAM，不能直接当成采购N32R16V的烧录配置。库版本来自本轮下载的官方标签/元数据；完整传递依赖和工具链包仍由包管理器解析并在实际构建时锁定。尤其Adafruit ST7735/ST7789还声明seesaw和SD依赖，不能将列出的三个主要库当成完整依赖集合。

资料获取和核对发生在维护阶段。任务运行时缺少必要硬件资料，应停止相应生成并说明缺口，不临时联网获取后直接采用。

## 本轮来源

完整URL、获取时间、SHA256、代码commit/tag见 [sources.lock.json](sources.lock.json)。`sources/`保留原始网页和选取的源码/例程，临时HTML文本提取件在项目temp目录。已有Wokwi说明直接引用原路径，不重复下载或抄写。

- Espressif：DevKitC-1 v1.1、S3 GPIO、ADC、USB Stream弃用说明及UVC组件入口。
- Wokwi：已有元件说明、自动化controls、S3仿真覆盖；另获取官方舵机与逻辑分析仪文章。
- 第三方ST7789模型：Whiteeeey/chip-st7789 v1.0.0，读取chip定义与实现，未编译或运行。
- 驱动维护者：DHTesp 1.19、ESP32Servo 1.1.2、Adafruit ST7735/ST7789 1.12.0、GFX 1.13.0、BusIO 1.17.4、NeoPixel 1.15.5。
- Waveshare、TowerPro、Adafruit：具体参考模块及电源/音频链路说明；采购型号不匹配时仅作为参考，不继承其额定值。

资料不是全部经过运行验证的规范：Waveshare DHT时序段存在单位冲突；Wokwi舵机文章区分了通用1–2ms说法和示例约0.5–2.4ms实测；TowerPro型号也不能覆盖所有标SG90的产品。相关限制已记录，不把网页某句话升级为所有模块的通用事实。

保留上游LICENSE/COPYING及版权头。DHTesp元数据声明GPL-3.0-only；其他库/网页按各自许可处理，源码摘选不构成一个统一许可的软件包。若将这些快照发布到GitHub，需逐项确认再分发条件；也可发布引用和哈希而不发布未确认授权的网页快照。
