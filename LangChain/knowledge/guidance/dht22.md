# DHT22：信号和驱动 API 关联

适用范围：Wokwi DHT22 与所存 DHTesp 1.19 源码；Arduino/ESP32 框架的运行兼容性尚未重新验证。

1. 模型数据端点名称是 `SDA`，表示 DHT 双向数据线，不能据此调用 I2C/Wire。`NC` 不连接。
2. 工程分配的 MCU GPIO 编号传给 `dht.setup(PIN_DATA, DHTesp::DHT22)`。`PIN_DATA` 是占位名称，不指定固定 GPIO。
3. DHTesp 头文件提示 ESP32 自动检测型号存在问题，应显式选择传感器型号。README 的默认参数说明不能覆盖该限制。
4. `getTempAndHumidity()` 返回含 temperature/humidity 浮点字段的结构；`getStatus()` 返回 `DHT_ERROR_t`，`getStatusString()` 是实例无参方法。
5. `getMinimumSamplingPeriod()` 在 DHT22 模式返回 2000ms。这个采样周期不等同已验证的上电首次读取延迟；后者要另查规格并验证。
6. 不额外强制添加未验证的 GPIO 模式或驱动补丁。采购红板是否自带上拉、实物针序仍未知。

来源：

- [Wokwi DHT22](../upstream/wokwi-docs/docs/parts/wokwi-dht22.md)：端点、属性、ESP32 推荐库。
- [DHTesp.h](../upstream/drivers/DHTesp/DHTesp.h)：型号选择提示、方法声明、错误枚举和最小采样周期。
- [驱动 README](../upstream/drivers/DHTesp/README.md)：方法语义及返回内容。
- [library.properties](../upstream/drivers/DHTesp/library.properties)：库身份、版本、架构声明。

本说明不诊断之前任何生成工程的失败原因，也不包含固定温湿度验收值。
