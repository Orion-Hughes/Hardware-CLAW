# 运行资料来源索引

公开运行包使用`LangChain/knowledge/`的来源锁定资料；历史调研和独立示例保留在维护者本机，不是安装依赖。

- [硬件连接卡与读取规则](../LangChain/knowledge/README.md)
- [原始来源、修订与SHA-256](../LangChain/knowledge/sources.lock.json)
- [第三方许可与版权说明](../THIRD_PARTY_NOTICES.md)
- [新增硬件流程](../docs/guides/HARDWARE_ONBOARDING.md)

## 板卡

**B01：Espressif ESP32-S3-DevKitC-1 v1.1官方指南**，原文快照为[开发板说明](../LangChain/knowledge/upstream/vendor/espressif-devkitc.html)。该指南列出ESP32-S3-WROOM-2-N32R16V，32MB Flash与16MB PSRAM，以及存储器占用GPIO的限制。型号表不能替代实物核对。

## 器件与API

Wokwi原始元件定义、属性、连接端点及说明在`knowledge/upstream/wokwi-diagram-lint/`、`wokwi-docs/`和`wokwi-boards/`；驱动正式API、示例、元数据及许可在`knowledge/upstream/drivers/`。

Arduino-ESP32 2.0.17与PlatformIO资料位于`knowledge/upstream/platform/`，厂家电气说明位于`knowledge/upstream/vendor/`。每张连接卡提供对应`documents.simulation`、`documents.api`、`documents.guidance`入口，不把近似模块资料冒充精确规格。

## 实物烧录

实物目标还核对固定版本的已安装框架：OPI SDK、OPI bootloader、官方32MB分区表及PlatformIO构建规则。配置入口为`LangChain/hardware_claw/deployment/target.py`，用法与边界见[烧录指南](../docs/guides/FLASHING.md)。
