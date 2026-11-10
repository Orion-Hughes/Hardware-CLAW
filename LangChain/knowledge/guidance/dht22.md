# DHT22：信号和驱动 API 关联

适用范围：Wokwi DHT22 与 Hardware-CLAW 本地维护的 DHTesp 1.19 驱动包。生产 Agent 流程已用 DHT22 串口工程完成一次编译、导出和仿真观察复验；通用功能验收仍未实现。

1. 模型数据端点名称是 `SDA`，表示 DHT 双向数据线，不能据此调用 I2C/Wire。`NC` 不连接。
2. 工程分配的 MCU GPIO 编号传给 `dht.setup(PIN_DATA, DHTesp::DHT22)`。`PIN_DATA` 是占位名称，不指定固定 GPIO。
3. DHTesp 头文件提示 ESP32 自动检测型号存在问题，应显式选择传感器型号。README 的默认参数说明不能覆盖该限制。
4. `getTempAndHumidity()` 返回含 temperature/humidity 浮点字段的结构；`getStatus()` 返回 `DHT_ERROR_t`，`getStatusString()` 是实例无参方法。
5. `getMinimumSamplingPeriod()` 在 DHT22 模式返回 2000ms。这个采样周期不等同已验证的上电首次读取延迟；后者要另查规格并验证。
6. 驱动由宿主以本地 `local_bundle` 注入，Agent 不修改 `lib/DHTesp`，也不把 DHTesp 写入 `platformio.ini` 的 `lib_deps`。
7. 当前 ESP32-S3 / Arduino / Wokwi 仿真基线已经用本地开漏释放版本完成无外加上拉对照验证；这不代表实物红板、其他板卡或所有仿真基线通过。
8. 采购红板是否自带上拉、实物针序、供电与接头仍未验证。

来源：

- [Wokwi DHT22](../upstream/wokwi-docs/docs/parts/wokwi-dht22.md)：端点、属性、ESP32 推荐库。
- [本地驱动包清单](../drivers/DHTesp/bundle.json)：版本、来源、文件清单和宿主注入方式。
- [本地 DHTesp.h](../drivers/DHTesp/DHTesp.h)：型号选择提示、方法声明、错误枚举和最小采样周期。
- [本地驱动 README](../drivers/DHTesp/README.md)：方法语义及返回内容。
- [本地 library.properties](../drivers/DHTesp/library.properties)：库身份、版本、架构声明。

本说明不诊断之前任何生成工程的失败原因，也不包含固定温湿度验收值。
