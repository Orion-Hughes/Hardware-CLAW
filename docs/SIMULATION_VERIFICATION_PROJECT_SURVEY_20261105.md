# 不同硬件组合的仿真检测与修改建议：开源项目调研

调研日期：2026-11-05（本地任务日期；部分下载的 UTC 时间为 2026-11-06）。

## 1. 结论与证据范围

本次目标是研究：已有需求、接线和固件之后，如何制定测试、执行仿真、判断行为是否正确，再提出修改建议。不是 PCB 布局或单纯的代码生成。

在本次检索、文档和源码核查范围内，**尚未找到可直接接入、已充分证明能针对任意 Wokwi 硬件组合自动制定正确测试并完成修正的开源系统**。但找到了可以分别借鉴的实现：

| 项目 | 最有价值的部分 | 测试从哪里来 | 关键边界 |
|---|---|---|---|
| firmware-testing-agent | 需求、接口 → 场景 → 时间线 → 判定 → 故障假设 | 部分由 LLM 生成 | 实际参考对象偏 STM32F4 + SI7021；判定和回退存在专用逻辑 |
| ironharness / ironbench | 实际运行 → 日志反馈 → 有界固件修正 | 预先编写的 task.yaml | Wokwi 主要为 ESP32/MicroPython；公布榜单没有 Wokwi 计分运行 |
| Wokwi 官方 Skills + Automation Scenarios | 可执行测试动作、复现、串口/引脚/波形调试 | 人或外部 Agent 编写 | 不是自动测试规划器；官方部件测试也不是任意组合的系统验收 |
| EmbedAgent / EmbedBench | 多器件组合需求与测试数据集 | 数据集中预先提供 | 不是通用的自动测试生成与判定服务 |
| CorrectBench | 检查测试本身是否有问题；有限修正 | LLM 生成 testbench/checker | Verilog/HDL 领域，不能直接测 ESP32 固件 |
| Agentic Embedded Lab | 仿真能力路由、实验契约、证据包、重放和对比 | 接收结构化实验定义 | 开发预览，模型与实物等价性有明确未验证项 |

本次完成在线获取和源码静态阅读，**没有安装、执行或端到端复现这些项目，也没有调用本项目的付费 LLM API**。下文的“有实现”只表示找到相应代码，不表示本地验证通过。来源快照和下载元数据在根目录 `temp/verification-research-20261105/`；生产 Agent 未改动。

后续深读补充：见 [firmware-testing-agent 源码拆解](FIRMWARE_TESTING_AGENT_WALKTHROUGH_20261105.md)。发现其上层在固件文件不存在时会走 mock 并返回带 synthetic 说明的 PASS；计划声明的 UART 注入未在真实执行器实现；场景预期没有完整传入判定器。因此下文关于架构与真实执行路径的优点不能外推到所有入口或通用硬件验证能力。

## 2. firmware-testing-agent：最接近我们的测试规划问题

项目：[Divyanshu1405/firmware-testing-agent](https://github.com/Divyanshu1405/firmware-testing-agent)

源码链路：

```text
固件 ELF / 规格
  → triage：初步分析
  → profile：硬件接口与可操作通道
  → spec：提取需求
  → plan：测试目标与场景
  → timeline：带时间的输入动作
  → run：仿真并收集 trace，调用判定
  → explain：根据失败证据提出假设
  → report
```

当前参考后端是 Renode，不能因为旧搜索描述提到 Wokwi，就认为当前链路可直接接入 Wokwi。

### 怎样规划

[`agent/steps/plan.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/steps/plan.py) 的提示词输入包括：

- 已提取的需求；
- 实际硬件接口；
- 允许的场景/故障类型。

提示词要求最多 8 个场景，每个覆盖 1–2 条需求，只针对已存在的通道。场景字段只有 `test_id`、`requirement_ids`、`fault_type`、`channel`、`reason`、`expected_observable`。

其核心提示词是：

> Given the extracted requirements and available hardware interfaces, generate an executable test plan.
> Target only channels available in the hardware interfaces.

随后 [`agent/steps/timelines.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/steps/timelines.py) 将各场景展开为 `duration_ms` 和 `events`。事件描述时间、操作、通道、值或持续时间；程序检查时间范围、接口和动作合法性，再转换为结构化对象。

这里值得借鉴的是**先约束可操作接口，再由模型选择测试**。不代表我们应该照搬它的每一个阶段或逐场景 API 调用方式；那仍可能产生大量调用。

### 怎样判断并提出建议

[`judge/evaluate.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/judge/evaluate.py) 根据轨迹与 monitor 规则计算结果。仿真基础设施失败返回 `INCONCLUSIVE`，不会直接当成功能失败或通过。

[`agent/steps/explain.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/steps/explain.py) 再向 LLM 提供需求、失败证据、时间点和轨迹，请它生成故障假设，并明确要求：

> Be explicitly labelled as a hypothesis (not a fact).
> Cite requirement ... Reference the evidence ... at t=... ms.
> Suggest what aspect of the firmware code might be responsible.

这是“证据支持的修改方向”，不是宣称已经找到根因。[`agent/graph.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/graph.py) 中该链路到 report 结束，未见主图中的自动固件补丁与复测循环。

### 不能照搬的部分

- 根据固件文件名、`mutant` 或 `si7021` 等选择预设 monitor。
- 泛用阈值 monitor 中仍固定使用 `temp_c`；其他情况可能退化为 UART 是否非空。
- 规划和时间线的失败回退含固定传感器通道和数值。
- 有些非法接口会被替换为默认接口，而不是明确报告不可执行。
- 解释提示词说关注相关时间的轨迹，但代码实际序列化该 trace 的全部 samples；不能把它当成已经解决上下文成本的方案。

因此，应借鉴流程与证据契约，不能借用这些特例充当我们的通用验收机制。另见项目自身的 [LIMITATIONS.md](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/LIMITATIONS.md)。

## 3. ironharness / ironbench：真正把仿真结果送回模型修正

项目：[cezman/ironharness](https://github.com/cezman/ironharness)

```text
task.yaml：任务 + 输入刺激 + expect/fail + 超时
  → LLM 生成 MicroPython main.py
  → runner 准备工程并调用仿真器
  → 读取串口，按规则评分
  → 保存本轮代码与日志
  → 成功退出 / 环境故障停止 / 把失败反馈给 LLM 修正
```

### 输入与执行

[`tasks/debounce/task.yaml`](https://github.com/cezman/ironharness/blob/main/src/ironbench/tasks/debounce/task.yaml) 是一个很直观的例子：按键接到 GPIO，脚本注入按下、短暂释放和再次按下，要求固件只计一次有效按键。`stimulus` 是动作序列，`expect`/`fail` 是串口规则。

**这些规则由任务作者预先提供，不是 Agent 从任意用户需求自动推导。** 固定字符串适合此 benchmark 的任务契约，不能作为 Hardware-CLAW 对所有工程的生产验收模板。

[`runner_wokwi.py`](https://github.com/cezman/ironharness/blob/main/src/ironbench/runner_wokwi.py) 将代码通过 MicroPython REPL 送入运行环境，拼入刺激序列和串口等待，调用 `wokwi-cli --scenario ...`，保留串口日志和退出状态。

[`runner_common.py`](https://github.com/cezman/ironharness/blob/main/src/ironbench/runner_common.py) 提供结构化结果，包括 `passed`、`missed`、`hit_fail`、`error_kind`、耗时和日志路径。Wokwi runner 会额外检查 expect/fail，而不是把 CLI 正常退出直接等同于测试通过；还处理 REPL 回显造成的假匹配。

### 修正循环

[`agent.py::solve_attempt`](https://github.com/cezman/ironharness/blob/main/src/ironbench/agent.py) 中：

1. 运行后先保存本轮代码和串口记录。
2. 成功则退出。
3. 如果是环境故障，停止，不要求模型不断修改无关代码。
4. 其他失败反馈运行输出，要求重新生成代码；受最大迭代次数约束。

其反馈是相当直接的：

> The check failed. ... Run output: ... Fix the code ...

串口反馈保留最后 40 行；若有 MicroPython traceback，则附异常类别和位置。它仍保留对话历史，并不是零上下文增长方案。runner 虽保存了 `missed`/`hit_fail`，当前模型反馈也不等于完整、理想的失败报告；我们可以借鉴结构化字段，不必原样复制其提示词。

### 成熟度边界

README 明确说明公布的榜单没有 Wokwi-scored runs，且 Wokwi 的部分输出判据缺少可靠的刺激接收时间锚点。不能据此声称 Wokwi 整体闭环已被充分实测。它最适合学习**有界执行循环、错误分类和证据保存**，不适合作为现成的通用规划器。

## 4. Wokwi 官方：执行能力的依据，不是系统测试的答案库

来源：[Automation Scenarios](https://docs.wokwi.com/wokwi-ci/automation-scenarios)、[官方 Skills](https://github.com/wokwi/skills)、[部件测试](https://github.com/wokwi/wokwi-part-tests)。

官方场景使用 YAML 顺序执行动作，当前文档包括：

- `set-control`：改变支持的部件控件，如按键、输入传感器值。
- `delay`：等待指定时间。
- `wait-serial` / `write-serial`：串口等待匹配和发送。
- `expect-pin`：检查引脚值；不能解释为任意电压测量。
- `take-screenshot`：保存指定部件 framebuffer，或与既有图像比较。
- `touch` 及 press/move/release：支持的触摸部件操作。

`set-control` 的旧字段 `control` 在 CLI 0.22.1 后改名为 `name`，文档注明旧字段仍兼容；不能仅见旧字段就判定外部案例不可运行。

官方文档仍将 Automation Scenarios 标为 alpha。文档存在某项动作，也不等于本机 CLI、当前 MCP wrapper 或每个器件都支持；后续执行应以实际版本和能力清单为准。

[`debug-esp32-firmware/SKILL.md`](https://github.com/wokwi/skills/blob/main/skills/debug-esp32-firmware/SKILL.md) 的主要思路：保留准确 ELF 解码崩溃位置；写可重放场景复现；需要协议/时序时收集逻辑分析仪 VCD；修复后保留回归测试。

[`verify-esp-idf-build/SKILL.md`](https://github.com/wokwi/skills/blob/main/skills/verify-esp-idf-build/SKILL.md) 区分构建、运行和外设场景。其 ESP-IDF 6+ / idf-wokwi 路线不能原样替代我们的 Arduino/PlatformIO 构建。

需要特别区分：

- `wokwi-part-tests` 主要证明单个仿真部件和驱动路径可工作，不是任意组合工程的验收集。
- 官方 Skills 是工作流程指导，不是已经部署好的规划 Agent。
- 截图比较需要可信基线；截图能生成不代表当前文本模型能理解它。
- 仅匹配串口里的“角度正确”，不能独立证明舵机引脚波形或部件动作正确。

## 5. EmbedAgent / EmbedBench：适合学习组合任务与覆盖，不是自动判定器

来源：[项目](https://github.com/icip-cas/EmbedAgent)、[EmbedBench.json](https://github.com/icip-cas/EmbedAgent/blob/main/dataset/EmbedBench.json)、[infer.py](https://github.com/icip-cas/EmbedAgent/blob/main/eval/infer/infer.py)。

本次读取的数据文件有 126 条记录，实际顶层字段都是 `id`、`problem`、`diagram`、`sketch`、`test`。不要把其他描述中的字段当成这个文件已存在的统一元件接口。

例如第 0 条是多个 LED、按键和数码管组成的交互游戏，需求包含初始化、反应时限、分数和结束状态；其他条目包括舵机扫描等。测试项包含时间、器件状态、说明。

它能启发我们：复杂组合应按**用户可观察的功能链路和状态变化**测试，而不是只逐一测试器件。但这些测试已经写在数据集里，有些是字符串化结构，并非可直接交给 Wokwi CLI 的 YAML。当前推理代码可看到编译反馈修正，但这不等于自动为任意工程建立可靠行为判据。

用途：作为后续评估用例来源，挑选组合任务、覆盖维度和测试表达；不把标准答案注入生产 Agent，也不把数据集所有预期值直接视作已验证真值。

## 6. CorrectBench：必须考虑“测试也可能错”

来源：[AutoBench/CorrectBench](https://github.com/AutoBench/CorrectBench)、[`TB3_funccheck.py`](https://github.com/AutoBench/CorrectBench/blob/master/autoline/TB3_funccheck.py)、[论文](https://arxiv.org/abs/2411.08510)。

```text
自然语言规格 → Verilog 激励 + Python checker
  → 多个候选 RTL 分别仿真
  → 候选实现 × 测试场景 的结果矩阵
  → 识别可能错误的测试
  → 修正并重新运行
```

源码有显式判别规则。例如默认模式会把所有候选都失败的场景列为可疑测试；也有按比例判定的模式。这是启发式证据，不是“多数实现都失败，所以测试一定错”。多个候选可能共享错误。

修正次数有限；错误场景增多、连续无改善或达到次数上限时退出该阶段。修正引入语法错误时允许有限回滚重试。它还可能请求外层流程 reboot，因此实际使用仍需要外层总预算，不能只限制内层循环。

对我们最重要的启发：**模型审查发现问题本身，也只是待验证的判断。** 不能因为审查模型说 action 序号错，就直接覆盖本来合法的计划。应先用程序确认结构和引用，再讨论行为判据是否符合需求。

不建议直接照搬默认约 20 个候选 RTL 的方法：它属于 HDL 场景，会增加成本，也不直接适用于 MCU + 外设。

## 7. 其他参考与取舍

### Agentic Embedded Lab

[项目](https://github.com/eust-w/agentic-embedded-lab)、[`service.py`](https://github.com/eust-w/agentic-embedded-lab/blob/main/src/ael/service.py)、[`router.py`](https://github.com/eust-w/agentic-embedded-lab/blob/main/src/ael/router.py)、[生产就绪说明](https://github.com/eust-w/agentic-embedded-lab/blob/main/docs/production-readiness.md)。

接收 `ExperimentSpec` 和系统清单，验证模型状态、调度与执行，生成证据包；支持 `replay`、`compare` 和 `explain`。其中 `explain` 是整理失败断言、最近事件和仿真精度边界，不等于 LLM 已诊断根因。

路由区分可执行、需要模型生成和需要实物验证，值得借鉴。项目处于开发预览，有未完成的实物对照和校准；不适合直接作为成熟通用替代品。

### Renode + Robot Framework

[官方测试文档](https://renode.readthedocs.io/en/latest/introduction/testing.html) 展示了更成熟的执行组织方式：平台/固件定义、测试初始化、可组合的关键词动作、串口/网络等待断言、报告和失败调试。适合学习测试执行器；它不是自动理解用户需求的 Agent，平台和外设模型也需要明确支持。

### vibe-analog / OpenBench

[vibe-analog 的 evaluator](https://github.com/DeconBear/vibe-analog/blob/main/skills/circuit-design-ngspice/scripts/evaluate_against_spec.py) 将仿真指标与规格比较，区分缺失/失败指标和通过条件，适合学习“测量”和“判定”分开；但它是模拟电路/ngspice 方向。

[OpenBench 的 engine-status](https://github.com/shuvamk/openbench/blob/main/.context/engine-status.md) 本次获取仍列 PlatformIO 为 partial、QEMU 为 stubbed，并说明真实连接链路缺口，因此未列为优先复现对象。

## 8. 对 Hardware-CLAW 的建议：先学习职责，不急着再改阶段数量

下面是本次调研后提出的设计建议，**不是已经实施的改动**。

### 通用的部分应该是什么

不是给每一种“传感器 + 执行器”写专用测试模板，而是让执行机制支持：输入刺激、时间推进、观察、断言、证据保存；具体测试由 Agent 基于需求和本工程的实际可操作能力组合。

| 职责 | 输入 | 输出 | 主要承担者 |
|---|---|---|---|
| 明确可测性 | 工程、需求、仿真工具和器件能力 | 可控输入、可观测输出、限制 | 程序提供真实能力；Agent 分析需求 |
| 设计测试 | 上述信息 | 目标、刺激、预期关系、允许误差、证据来源 | Agent |
| 校验/执行 | 可执行场景、断言 | 原始日志/波形/观察和执行状态 | 程序与仿真器 |
| 形成结论 | 观察和测试规则 | 通过/失败/证据不足及具体差异 | 能确定性计算的交给程序 |
| 解释与修正 | 失败差异、需求、相关代码 | 根因假设、补充实验或修改清单 | Agent；修复后复测 |

这些是职责边界，不意味着每一行都应新建一个子 Agent、阶段文件或 API 调用。

### 对当前问题最直接的启发

1. **保留必要的 JSON/引用检查，但不要让模型承担计数和格式搬运。** 可考虑由程序处理稳定步骤 ID 到位置的映射；这是一项待设计的通用机制，不是调研项目都已采用的事实。
2. **把审查意见与可验证错误区分。** 规则检查能确定的问题直接返回完整清单；模型提出的语义问题应附需求依据，不能凭意见反复推翻合法计划。
3. **将结果分为功能失败、测试不成立和环境故障。** 环境没启动、工具不支持、证据缺失，都不应进入无意义的固件修正循环。
4. **失败反馈给预期、实际、时间和来源，而不是只给“没有通过”。** 保留原始证据，按需读取，不反复把全部资料和波形发回模型。
5. **判据不能从待测固件的实际行为直接抄出来。** 需求决定“应该怎样”；固件用于确认引脚、接口和日志位置。需求未定的数值应注明设计假设，不能假装来自用户。
6. **修正必须产生可比较的新证据。** 问题列表没有变化、错误增加、预算耗尽时停止；保留失败，不能靠降低验收条件获得通过。

例如“电位器控制舵机”应关注输入改变后 PWM/角度是否按设计关系变化、边界和响应，而不是只检查固件打印了某句文本；“摇杆串口检测”则应关注各方向、回中和按键对应的串口变化。是否能测 PWM、读部件状态以及达到何种精度，必须由实际工具能力决定。**这些是需求派生的测试思路，不是新增生产特例。**

### 建议阅读顺序

1. `firmware-testing-agent` 的 `plan.py → timelines.py → evaluate.py → explain.py`：学习规划到证据，同时辨认其特例。
2. `ironharness` 的 `task.yaml → runner_wokwi.py → solve_attempt`：学习执行、错误分类和修正闭环。
3. Wokwi 官方场景与调试 Skill：确认我们能真实操作和观察什么。
4. CorrectBench：学习怎样质疑测试本身、何时退出修正。

下一步应先选取上述项目的一条完整链路做源码 walkthrough，明确可借鉴的最小机制，再决定如何修改 Agent3；不宜仅凭“另一个项目也分阶段”就继续增加我们的阶段和上下文。
