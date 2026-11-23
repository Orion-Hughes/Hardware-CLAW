# 第三方来源与许可

`LangChain/knowledge/upstream/`包含为离线硬件检索、驱动API阅读和软件测试保留的上游文档/源码快照。**这些文件不是Hardware-CLAW原创，也不因本仓库公开而统一改用某个新许可证。**

具体仓库、版本、原路径和原始SHA-256见[来源锁](LangChain/knowledge/sources.lock.json)。保留各文件的版权、许可和来源；部分许可位于`LICENSE`、`license.txt`、`COPYING`或源码头部，不能只按文件名判断。

| 来源类别 | 对应内容 |
|---|---|
| Wokwi文档、板卡、diagram-lint | `upstream/wokwi-docs/`、`wokwi-boards/`、`wokwi-diagram-lint/` |
| Adafruit驱动及说明 | `upstream/drivers/Adafruit*`、`RTClib/` |
| DHTesp / ESP32Servo | 对应驱动目录及其文件头、许可 |
| Espressif / PlatformIO | `upstream/platform/`、`upstream/vendor/` |
| 第三方ST7789仿真模型 | `upstream/models/chip-st7789/` |

本地`LangChain/knowledge/drivers/DHTesp/`保留其上游许可与本地变更说明；`HwClawGraphics/`为本项目本地绘图组件。宿主注入本地驱动时保留包清单和哈希，不静默替换为另一份库。

第三方原文中的链接、图像和示例属于相应维护者。资料收录不等于得到厂商认证，不代表当前Agent生成工程一定适配对应实物。上游数据的进一步分发应继续保留其原有通知。

本文件是来源索引，不替代各上游的实际许可证；当前未为项目自写代码新增统一LICENSE，不能把整个仓库称作统一MIT授权。
