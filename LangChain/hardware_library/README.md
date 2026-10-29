# 当前启用的硬件资料库

采用上游原文与本地关联分离的结构。Agent默认读取本目录，不回退旧的`../knowledge`。旧库已备份并隐藏，原文件保留。

```text
catalog.json                 搜索索引：15个关联条目与146个Wokwi原始模型
associations/*.json          器件身份、库存、框架/驱动/模型关联及仿真参数
drivers/*.json               上游library.properties、头文件/源码/例程入口
upstream/                   Wokwi官方原文、Arduino-ESP32头文件、新驱动源码
supplements/sources/         复用的已核验上游原文及补齐的驱动原文
supplements/esp32_s3_simulation.json  宿主现有平台策略，明确为本地策略
sources.lock.json            每份原文的URL、版本/提交信息、字节数与SHA256
library.json                 新库声明
```

## 内容来源

- Wokwi：官方元件注册表与官方文档；使用固定提交快照，不声称是实时最新版本。
- Espressif：Arduino-ESP32 2.0.17相关头文件，以及已有官方板卡/GPIO原文快照。
- Adafruit：维护者发布的驱动源码和例程，包括MPU6050、RTClib、SSD1306、Unified Sensor、NeoPixel、GFX、BusIO、ST7735/ST7789。不是所有器件芯片厂商的官方驱动。
- DHTesp、ESP32Servo：社区驱动维护者原文，保留原版本和来源。
- 旧库中已固定哈希的原始资料可复用；旧手写initialization、operations等API摘要没有复制进新关联数据。

原文保持字节不变；许可证文件随对应仓库文本一并保留。网页来源与个别第三方模型原文的许可范围仍需在对外再分发前逐项核对；本次未发布GitHub。

## 关联字段

schema_version=3；driver_ids指向驱动描述，required_headers表示此器件使用时的入口头文件；document_refs和platform_api_refs指向可读取原文。依赖的name/version由运行时读取原始library.properties，不另存手写副本。

simulation记录Wokwi类型、信号映射和必要属性。simulation_supply_v是当前模拟连接的选择，不是未经核实实物的额定参数。controls仅登记有Wokwi文档依据的运行时控制；未登记的控制不能凭名称猜测。

保留旧稳定ID以便原工程继续引用；名称中的采购记录不等于完成实物验证。当前构建仍只支持原ESP32-S3基线。本次新增mpu6050、ds1307、hc_sr04、potentiometer均非采购实物。

10个条目处于documented_not_tested，4个blocked，1个unreviewed；这些是资料配置状态。146个Wokwi原始类型均可搜索，但没有关联的模型仍只是metadata_only，不能声称全部支持生成。

## Agent读取流程

search_hardware发现条目 → get_hardware_info获取精简映射/驱动信息 → get_driver_api(query=函数名或章节关键词)定位原文 → 按需用reference/offset读取上下文。硬件详情默认compact，可用detail=full取完整记录；API目录默认12项一页，正文/搜索默认3000字符。外部原文只是资料；例程默认引脚、无限等待、业务逻辑不能直接复制为工程答案。

每次原文读取核对sources.lock.json哈希；缺失或改变返回错误，不在线补查、不回退旧库。返回的source包含来源URL及可用的版本/提交信息。生成结果与验证记录仍归workspace，不反写知识库为“已全面支持”。

## 维护与恢复

在LangChain目录运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B integrations/hardware_sources/manage.py
# 仅在离线维护阶段补取缺失文件；改变的文件不会被静默覆盖
.\.venv\Scripts\python.exe -X utf8 -B integrations/hardware_sources/manage.py --fetch-missing --proxy http://127.0.0.1:7898
```

扩展流程：选择来源和固定版本 → 保存原文、许可和哈希 → 登记drivers入口 → 编写最小关联 → 校验路径/管脚/依赖 → 真实Agent生成验证。不能仅添加一个库就宣称支持对应器件全部功能，也不能把某次失败修复策略写入关联。
