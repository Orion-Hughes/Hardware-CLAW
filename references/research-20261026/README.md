# 需求到嵌入式工程：源码深入调研

本轮对应用户要求：深入前两个项目的实现、框图、数据流和提示词；寻找可关联 Wokwi 的元件库；提炼可执行的验证办法。目录沿用本轮调研日期命名。

## 阅读顺序

1. [01：两个项目的程序结构、输入、数据流和关键 Prompt](01_IMPLEMENTATIONS.md)
2. [02：元件库来源及 Wokwi 映射](02_COMPONENT_LIBRARIES.md)
3. [03：验证与仿真的核心实现办法](03_VALIDATION.md)

关键结论：Circuit Lab 是轻量的需求到工程文件原型；circuit-synth 值得借鉴的是电路建模和 KiCad 库复用，所查几条内部 Agent 路径并非完整可用闭环；目前对我们最直接的新增资源是 Wokwi 官方 diagram-lint 注册表和 wokwi-part-tests。

## 证据与范围

本轮为静态源码审阅和在线官方文档核对。没有安装这两个项目，没有运行其代码，没有调用模型生成工程，没有编译或执行 Wokwi 仿真。下文“源码实现”与“本地实测通过”严格区分。

`sources/` 是选定文件的原样源码快照，供逐行学习，不是完整仓库或可运行安装包。未另行标记的示意图与建议均为本项目研究笔记，不能当成上游已经实现的功能。

| 来源 | 固定提交 | 本地快照 | 授权信息 |
|---|---|---|---|
| [Circuit Lab](https://github.com/PythonicVarun/llm-circuit-builder) | `f1b3cd9ce47e6a9444c96a15308cc5c9bbab97ee` | `sources/circuit-lab/` | MIT，保留 LICENSE |
| [circuit-synth](https://github.com/circuit-synth/circuit-synth) | `3aaff18c056de7cbe8f5b0a3e1e6e7e7895f544e` | `sources/circuit-synth/` | MIT，保留 LICENSE |
| [Wokwi CLI / diagram-lint](https://github.com/wokwi/wokwi-cli) | `f23ed6fe2a8df332a9020fafb3c82b6ca95aa61c` | `sources/wokwi-cli/` | 根目录 MIT，保留 LICENSE；diagram-lint README 指向的包内 LICENSE 路径返回404，使用仓库根许可核查 |
| [Wokwi part tests](https://github.com/wokwi/wokwi-part-tests) | `b224080de2c4fb54a420fd60a3daf1eb0fa2ab81` | 仅链接和研究描述 | 所查树未发现 LICENSE，不能假设有 MIT 授权 |
| [Wokwi boards](https://github.com/wokwi/wokwi-boards) | `962b19d5636756537a93bb5337ac99abd775eae0` | 仅链接和研究描述 | 本轮未确认独立许可，复用前另核对 |
| [Wokwi Elements](https://github.com/wokwi/wokwi-elements) | `5178c0cc1b455719fdf562169293797e29d73dac` | 在线阅读 | README 声明 MIT；仅显示组件，不含硬件功能仿真 |
| [PlatformIO espressif32](https://github.com/platformio/platform-espressif32) | `7afb0a703a5f6492fd695a4c2ced9ad843745280` | 在线阅读 | 本轮用于核对构建资料，不复制发行整个库 |

其他参考包括 KiCad 官方 GitLab 库及许可、modm-devices README、Wokwi 官方 DHT22 和场景测试文档。它们是在线版本；导入数据库前应再固定版本和来源。

## 对上一轮结论的修正

- circuit-synth 的 `Component` 实际加载 `kicad/kicad_symbol_cache.py` 中的 `SymbolLibCache`，不是此前重点介绍的 `core/symbol_cache.py`。
- 名为 Agent 的文件不能直接证明已经实现 LLM 推理和自动修复。已找到关键词模板、未使用的增强 Prompt、连线 TODO、缺失的注册模块引用。
- Wokwi 有可复用的机器可读元件注册表，不必从零手写所有模拟引脚。
- 注册表中有 ST7789，但追到 board 定义后是第三方芯片实现的 240×240 模型，不能直接等同我们购买的 240×320 模块。
- Wokwi CLI 的模拟时间超时不能代替宿主进程的墙钟超时。
