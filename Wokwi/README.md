# Wokwi 仿真实验

此目录保留原位：执行器通过目录层级定位项目根目录，工程配置也引用现有pio、tools与temp路径。整理时未移动或修改运行代码。

| 位置 | 内容 |
|---|---|
| `wokwi_dht22_oled_cli/` | ESP32-S3 + DHT22 + SSD1306示例，包含源码、diagram、构建/模拟配置与测试清单 |
| `runner/run_wokwi_test.py` | 现有编译、lint、场景执行与结果汇总脚本 |
| `../temp/wokwi_dht22_oled_cli/` | 已配置的构建缓存和运行输出目录 |

本次仅检查脚本、配置路径及CLI帮助入口，没有执行构建、付费模拟服务或硬件操作，也不据此认定执行器已通过全部测试。该脚本尚不能等同已经接入LangChain的完整仿真tool。

示例使用SSD1306，不是采购的ST7789屏幕。Wokwi CLI默认依赖远程Simulation API；请区分本机文件与离线模拟引擎。
