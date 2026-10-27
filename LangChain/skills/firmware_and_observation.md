# 固件与可观察性

- PlatformIO源码src/main.cpp显式include Arduino.h，setup/loop入口，引脚常量与设计一致。
- 当前ESP32-S3基线Serial.begin(115200)使用UART0；不要启用USB CDC、改用USBSerial或无限while(!Serial)。
- setup打印HWCLAW_BOOT；loop定期输出读数或明确错误。显示器需求必须更新屏幕，不能用串口代替显示。
- 使用Serial.println或printf的\r\n结束一行，避免VS Code终端仅换行不回到行首。
- DHT22首次和连续采样间隔至少2000ms；setup(pin,DHTesp::DHT22)，getTempAndHumidity后检查getStatus()和NaN。
- getStatus()返回DHTesp::DHT_ERROR_t；getStatusString()是实例无参数方法，不要编造TempError或静态带参调用。
- load_template("dht22_uart_example")是可参考示例，其他硬件按其资料实现。
- 稳定字段、单位与错误输出便于后续测试；编译不证明连线、显示或行为正确。

参考：https://docs.wokwi.com/guides/serial-monitor
