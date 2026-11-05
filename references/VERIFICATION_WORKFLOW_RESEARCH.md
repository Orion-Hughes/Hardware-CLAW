# Verification Agent：自动化验证流程调研

本文用于第三个子 Agent 的设计讨论，不表示这些能力已接入 Hardware-CLAW。调研方式为联网阅读官方文档、测试文件及部分实现源码；未安装工具、执行仿真或调用项目 LLM API。

## 1. 结论与成熟度

有成熟的嵌入式自动化测试组织方法，也有 Wokwi 官方可执行测试与 Agent skills。尚不能据本次资料认定存在一个可直接接入、可靠验证任意自然语言硬件需求的通用 Agent。

建议采用：需求与实际能力 → Agent 制定测试计划 → 受控执行器运行 → 确定性断言与证据 → Agent 解释失败 → 主 Agent 将修改任务交给生成 Agent → 原测试回归。

“确定性断言”只能保证按规则判断，不能保证规则符合需求。判据的来源、覆盖程度以及观察能力必须单独检查。

| 资料/项目 | 已查阅内容 | 借鉴价值 | 限制 |
| --- | --- | --- | --- |
| Wokwi Automation Scenarios / part-tests | 官方步骤文档、摇杆与 SSD1306 场景、CI workflow | 最直接的执行层参考：刺激、等待、断言、截图对比、批量运行 | 文档仍标 alpha；元件测试不是任意生成工程的验收方案 |
| Wokwi agent skills | 四个 SKILL.md | 组织冒烟测试、UI 回归、调试和内存压力测试 | 技能指导不等于可靠执行器；版本、框架、服务器支持需要实测 |
| Renode + Robot Framework | 官方 testing 文档 | 隔离、setup/teardown、状态恢复、报告、失败调试 | 不是 Wokwi 的直接替代；未核验我们的板卡/外设支持 |
| Espressif pytest-embedded | 插件文档、ESP-IDF pytest 指南 | 测试 fixture、串口断言、参数化、多 DUT、后续实物测试组织 | ESP-IDF 特定约定不能直接套用到所有 Arduino/PlatformIO 工程 |
| firmware-testing-agent | graph、runner、Wokwi backend、evaluate 源码 | 需求→计划→输入时序→轨迹→判定→解释的职责划分 | Wokwi stub；部分示例专用判断和 mock 回退不符合本项目约束 |
| EmbedAgent / EmbedBench | README、公开文件树 | 126 个嵌入式任务与参考测试可用于未来 benchmark 研究 | 本轮未逐项审核数据集测试；不能当作已验证的通用执行框架 |

## 2. Wokwi 官方执行流程

来源：

- [Automation Scenarios](https://docs.wokwi.com/wokwi-ci/automation-scenarios)
- [CLI Usage](https://docs.wokwi.com/wokwi-ci/cli-usage)
- [官方元件测试库](https://github.com/wokwi/wokwi-part-tests)
- [实际 CI workflow](https://github.com/wokwi/wokwi-part-tests/blob/main/.github/workflows/wokwi-test.yml)

官方元件测试的主流程为：PlatformIO 编译 → 按工程选择 YAML 场景 → Wokwi CI 执行 → 按退出状态报告，同时输出串口日志。Workflow 用 matrix 覆盖多个板卡/元件组合。

Scenario 提供的基础动作包括：

- `set-control`：改变模拟元件的输入，例如摇杆方向或传感器环境值。
- `write-serial`：输入串口命令。
- `wait-serial`：等待符合预期的串口文本。
- `expect-pin`：检查引脚值，不能扩张为测量真实电压或验证全部模拟电气特性。
- `delay`：按仿真时间等待。
- `take-screenshot`：取得元件 framebuffer，可保存并与参考 PNG 对比。

最新版文档还有触摸步骤及其他 CLI 能力；不能据此声称本地版本和当前 Agent 已暴露这些能力。应锁定版本并探测实际支持。

具体实例：

1. [摇杆场景](https://github.com/wokwi/wokwi-part-tests/blob/main/wokwi-analog-joystick/joystick-uno/joystick.test.yaml)：改变 x、y 与 pressed，等待相应固件读数/按键事件。示例采用 Uno 的读数，不得把其数值直接复制为其他板卡的判据。该文件的 name 还误写为 DHT22，说明官方示例同样需要核对。
2. [SSD1306 场景](https://github.com/wokwi/wokwi-part-tests/blob/main/board-ssd1306/oled-esp32/ssd1306.test.yaml)：等待初始化与计数事件，截取不同状态，与预先保存的参考图片比较。

对本项目，Scenario 适合固定测试与回归；MCP 适合交互探查和失败诊断。无需为了采用官方方案放弃已有 MCP，但宜避免每一个测试动作都消耗一轮模型调用。

## 3. Wokwi 官方 Agent skills

[仓库](https://github.com/wokwi/skills) 为 MIT 许可。本轮只研究其内容，没有安装或将其作为当前会话指令执行。

| Skill | 实际流程 | 可借鉴部分 |
| --- | --- | --- |
| [verify-esp-idf-build](https://github.com/wokwi/skills/blob/main/skills/verify-esp-idf-build/SKILL.md) | 检查环境、编译运行、等待成功/失败文本、超时退出 | 有限执行；成功信号应覆盖被测流程，不能只检查启动横幅 |
| [test-lvgl-ui](https://github.com/wokwi/skills/blob/main/skills/test-lvgl-ui/SKILL.md) | 注入交互、同步屏幕状态、截图、像素级回归、保留失败图片 | 屏幕验证应观察实际 framebuffer，日志不能替代画面 |
| [debug-esp32-firmware](https://github.com/wokwi/skills/blob/main/skills/debug-esp32-firmware/SKILL.md) | 用对应 ELF 解码异常、场景复现、VCD 总线观察、GDB 调试 | 诊断证据绑定准确构建版本；复现用例保留为回归测试 |
| [find-memory-leaks](https://github.com/wokwi/skills/blob/main/skills/find-memory-leaks/SKILL.md) | 重复输入负载、堆采样、设置阈值、检查测试是否能检出泄漏 | 没有采样数据不能算通过；阈值随构建变化，不能照抄示例 |

适配注意：

- `verify-esp-idf-build` 依赖特定 ESP-IDF/idf-wokwi 版本，不是当前 Arduino 工程的直接命令模板。
- CLI 仿真超时与宿主墙钟超时需要分别设置；官方 idf-wokwi skill 还说明其 timeout 语义不同于 CLI。
- 官方 UI skill 的参考图需经过检查。首次生成工程的实际截图，不能未经确认就成为自己的正确答案。
- 像素级比较受字体、驱动、旋转、颜色和捕获时机影响。它证明与已确认基线一致，不能独立证明自然语言需求已实现。
- 不把特定示例的输出、等待顺序、数值或名字写进通用生产 skill。仅抽取通用工作方法。
- 调试用逻辑分析仪等观测接线应作为可追踪测试变体，不静默覆盖生成工程。

## 4. 成熟测试框架的共性

### Renode + Robot Framework

[官方测试文档](https://renode.readthedocs.io/en/latest/introduction/testing.html)

`renode-test` 管理模拟器启动、测试连接、运行、结束清理，产出 XML 和 HTML 报告。默认测试 teardown 会 Reset Emulation，避免前一个测试污染下一个。还提供 UART 读写与等待、网络包检查、命名快照恢复和失败交互调试。

应借鉴测试生命周期和隔离机制，不需要现在更换仿真器。

### pytest-embedded

- [插件文档](https://docs.espressif.com/projects/pytest-embedded/en/latest/)
- [ESP-IDF 测试指南](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/contribute/esp-idf-tests-with-pytest.html)

通过 DUT fixture 将设备准备和测试逻辑分开，使用 `dut.expect` 等检查串口，支持目标/配置参数化。ESP-IDF 指南明确 multi-DUT 情况提供多个 DUT 对象；这对以后板间通信测试有参考价值，但不代表 Wokwi 已支持我们需要的所有板间连接。

## 5. 对开源 Agent 实现的审查

[firmware-testing-agent](https://github.com/Divyanshu1405/firmware-testing-agent) 的 `agent/graph.py` 有 triage → profile → spec → plan → timeline → run → explain → report 链路；值得参考数据分层。

但实际读取源码发现：

- `backend/sim/wokwi_backend.py` 明确为 compatibility stub，调用抛出 NotImplementedError。
- `agent/steps/runner.py` 在 mock 模式或固件路径不存在时走 synthetic mock，且产生带 mock 标记的 PASS。我们应让固件缺失成为工具错误，不能借此回退为通过。
- `judge/evaluate.py` 按固件文件名选择校准监视器，并将一般 threshold 映射至固定温度通道；不适合作为通用需求判据。
- 无 threshold 的需求可能变成“串口最终非空”，这最多证明存在输出，不能证明原需求满足。

因此不建议直接采用其验证后端或判定器，只借鉴职责划分。本结论来自静态代码检查，没有运行其完整系统。

[EmbedAgent / EmbedBench](https://github.com/icip-cas/EmbedAgent) 适合作为后续测试集研究入口。其 README 声明数据包含 problem、diagram、sketch、test，覆盖 Arduino、ESP32、Pico；这些项目声明不等于我们已经复验其全部案例。

## 6. 建议的第三 Agent 流程（待实现）

| 步骤 | 输入/输出 | 约束 |
| --- | --- | --- |
| 接收工程与能力 | 原始需求、选型/接线、准确工程版本、构建产物；实际元件 controls、可观察信号和工具限制 | 能力包来自工具与元件支持情况，不能仅靠 System Prompt 宣称支持 |
| 形成验收项 | 需求 ID、预期行为、判据来源、缺失参数 | 可以读取代码了解接口，但不能仅按代码现状定义正确性 |
| 制定测试计划 | 初始状态、输入序列、观察通道、断言、仿真时间窗口、清理方式 | 测试计划与实现细节分开；无法观察的项明确标注 |
| 校验计划 | 元件/控件/引脚有效、路径受控、动作可执行、资源预算有效 | 错误计划先修计划，不直接判固件失败 |
| 执行与采证 | Scenario 或受控 MCP 序列 → 串口、引脚、图片、VCD、执行状态 | 固定场景批量执行；宿主和仿真双重超时；保证会话关闭 |
| 判定与覆盖报告 | 每项状态、预期/实际、证据引用、未覆盖需求 | 断言确定性执行；图片语义若靠模型判断需单列依据与不确定性 |
| 有限诊断 | 区分固件错误、测试错误、环境错误和能力缺口 | 每次追加观察须有具体问题；设置次数、时间和 token 上限 |
| 交接修正 | 最小失败复现、相关证据、可能原因 → 主 Agent → 生成 Agent | 验证 Agent 不直接改固件；修改后固定原判据回归 |

对结果建议分开表达：执行状态（正常/工具错误/超时）与需求状态（通过/失败/证据不足/不支持）。正常退出不能自动成为所有需求通过。

每个证据绑定 source/diagram/firmware 哈希和测试版本。修复后若确需改测试，记录理由并保留原测试，防止通过降低标准消除失败。

第一版可先覆盖启动、可控输入变化、可观察输出响应；复杂协议解码、图像语义和长时性能测试逐步扩展。不能观察到的要求保留未验证。

## 7. 对“摇杆＋屏幕圆点”需求的说明

可从需求设计：居中、各方向、回中、边界输入，观察圆点位置是否对应变化、是否处于规定区域。精确坐标和像素误差须来自需求或明确设计约定。

- 只读取摇杆串口值，证明不了屏幕确实绘制正确。
- 成功设置摇杆控件，证明不了固件已读取它。
- 如果显示模型不能返回有效截图，则该图形要求暂不能自动判定通过。
- 若没有可信参考图或通用图像检查能力，首次图形验收需要人工检查或另行建设评估能力；不能为这个样例在生产逻辑加入专用识别器。

这是测试设计说明，没有为该工程添加特殊模板或硬编码规则。

## 8. 资料留存与核查范围

原始响应、提取正文、下载 URL、HTTP 状态和内容 SHA256 保存在 `temp/verification-research-20261105/`。这些是研究临时资料，不是生产知识库。

本轮获取的 Git tree SHA（不是 commit SHA）：

- wokwi/skills：`a283887f5b02325b54f1b925ae044c28ef158b69`
- wokwi/wokwi-part-tests：`277b91b8337053e71ce84a3a19709f1b9b2c01fb`
- Divyanshu1405/firmware-testing-agent：`408434b83427b4b363a091a631de96817e2049fc`
- icip-cas/EmbedAgent：`877bae655797d01180b562a673a4dfdaaddbadd6`

网页和 main 分支可能变化；文档抓取与源码树请求非原子快照，具体已读文本以本地内容哈希为准。Zephyr Twister 页面本轮返回内容不足，未据此形成结论。其他已下载但未深入审查的框架不列为推荐实现。
