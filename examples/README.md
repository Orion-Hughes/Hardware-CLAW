# 参考工程

当前已有工程保留在 `../Wokwi/wokwi_dht22_oled_cli/`，不复制构建缓存，不改变其已有路径。

本次只读检查确认：

- diagram.json 使用 ESP32-S3 仿真板、DHT22 和 SSD1306 OLED。
- 当前该文件的接线为 DHT 数据 GPIO18、OLED SDA GPIO8、SCL GPIO9；这是文件现状，不是对实物的接线建议。
- platformio.ini 选用 Arduino framework 和 PlatformIO，并引用已有 pio 及 temp 目录。
- 用户此前已完成网页手工仿真；本次未重新执行编译或 CLI 仿真，不对现有自动化状态作成功判定。

实物屏幕为 ST7789 SPI TFT，与这个 SSD1306 I2C OLED 仿真案例不同。保留已有案例作为基线，后续另建 ST7789 实物案例，不能只替换名称就沿用接线。
