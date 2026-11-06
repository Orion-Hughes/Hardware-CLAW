# firmware-testing-agent：规划、执行与判定源码拆解

日期：2026-11-05。对象：[Divyanshu1405/firmware-testing-agent](https://github.com/Divyanshu1405/firmware-testing-agent)。

本次沿上次获取的源码快照逐函数阅读，未运行外部项目、未调用 LLM API、未修改 Hardware-CLAW 的生产流程。本文将“源码已实现”“设计意图”和“建议我们如何做”分开；源码路径对应本地 `temp/verification-research-20261105/sources/Divyanshu1405--firmware-testing-agent/`。线上 main 后续可能变化。

## 1. 最重要的结论

它采用**固定 LangGraph 工作流 + 几个独立 LLM 调用 + 确定性的执行/判定程序**。它不是由主 Agent 动态创建多个子 Agent，也不是一个自由选择工具、无限探索的对话循环。

这使执行顺序和每次模型任务比较清楚。但深入源码后，发现它的泛化能力比架构图显示的弱：部分计划不能被执行器实现，计划中的预期也未完整转成最终判据。不能据它的流程简单，推断我们只要照搬即可解决成本和正确性问题。

## 2. 主程序如何决定下一步

入口：`agent/run.py`、`backend/main.py` 最终调用 [`agent/graph.py::build_graph`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/graph.py#L168)。

```text
triage → profile → spec → plan → timeline → run → explain → report → END
```

这些是代码固定的边。模型不能自行决定跳过运行、反复查询或再进入规划。多数节点先判断 `state.error`，有错误则不继续实际工作；局部生成函数有有限重试。主图没有“失败 → 修改固件 → 重新测试”的回边，也没有独立的最终计划审查节点。

[`AgentState`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/models.py#L192) 是 Python 中的共享数据容器：

| 数据 | 含义 |
|---|---|
| firmware_path / spec_text | 被测 ELF 与规格文本 |
| firmware_profile / io_map | 固件线索、平台与输入输出接口 |
| requirements | 提取的需求 |
| test_plan | 场景目标与预期描述 |
| timelines | 具体输入事件 |
| traces | 运行轨迹 |
| monitors / verdicts | 判定规则和结果 |
| explanations / report_html / error | 故障假设、报告、流程错误 |

**State 里有某项数据，不代表它会自动发送给模型。** 每个节点的提示词函数显式挑选数据；没有统一把整个 state 和全部前文塞回模型。

## 3. 各步骤到底做什么

### 3.1 triage / profile：先确定能操作哪些接口

程序静态检查 ELF，读取架构、符号和字符串；`profile/infer.py` 根据这些线索选择平台和 I/O 映射。

参考 SI7021 配置包括温度、湿度输入通道，以及 UART 输出，映射到 Renode 的外设对象。规划器面对的是这些通道，而不是凭空猜测一组可以调用的硬件能力。

但实际映射以 STM32F4/SI7021 为主，未知目标也仍有 STM32 平台默认值；这不是任意 ELF 的可靠自动板卡识别器。

**我们的借鉴方式：** 我们已有生成工程、`diagram.json`、选型记录和器件资料，比从 ELF 猜测更有条件直接形成可测能力表。无需重做一套 ELF 猜测选型。能力应来自“工程实例 + 已知器件控件 + 当前工具实际支持范围”，运行前再检查环境是否可用。

### 3.2 spec：从需求文本形成可追溯的要求

[`spec.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/steps/spec.py#L96) 给规格文本加行号，再让模型输出：

```text
id、description、source、source_line、threshold、time_value_ms、ambiguous
```

关键提示词要求抽取编号需求，模糊需求也保留并标记 `ambiguous`，然后由 JSON Schema/Pydantic 检查结构。

需要注意：字段通过 Schema 不代表需求解释正确；源码中的行号字段也不等于已做来源内容核验。单个 `threshold` 没有表达完整的单位、比较方向和输入输出关系，无法涵盖任意系统需求。

**我们的借鉴方式：** 保留需求原文和来源，区分用户要求、设计假设、器件约束。不要把“阈值”当作所有需求的统一语义。对于摇杆方向、灯效顺序、板间通信，应保留事件、关系与状态含义。

### 3.3 plan：一次提出场景目标，不写仿真器命令

[`plan.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/steps/plan.py#L174) 的模型输入是全部结构化需求、I/O map 和可选场景类型。

提示词约束：最多 8 个场景；每个覆盖 1–2 条需求；只针对真实存在的接口。输出字段为：

| 字段 | 作用 |
|---|---|
| test_id / requirement_ids | 用例身份、需求关联 |
| fault_type / channel | 测试情形与目标通道 |
| reason | 为什么要测 |
| expected_observable | 期望看到什么 |

它没有要求模型在这一步处理嵌套工具调用、JSON Pointer 修改、证据索引和审查问题状态。

但是“最多 8 个、每例 1–2 条”只是该项目提示词里的设计选择，不是适用于我们所有任务的规则。

### 3.4 timeline：把场景转换为带时间的输入动作

[`timelines.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/steps/timelines.py#L122) 对每个场景单独请求模型，输入包括该场景、全部需求和 I/O map。

输出内容：

```text
test_id、requirement_ids、duration_ms
events:
  at_ms、action、channel、value / to / over_ms / for_ms
```

程序检查动作名称、通道是否存在、时间顺序、事件是否超出测试时长、需求引用和对象结构。`test_id`、`requirement_ids` 会由宿主按场景覆盖，因此模型不必承担这些标识的一致性维护。

注意，这个 timeline 基本描述的是**怎样施加输入**；它没有完整包含“怎样从结果中判定该场景预期”。最多尝试三次，但错误通常只写入日志，下一次仍使用原提示词，并没有把完整校验错误送回模型形成有针对性的修复。失败场景还可能不进入最终 timeline 列表，主图没有统一的缺失覆盖阻断。

### 3.5 run：程序把输入动作翻译成 Renode 操作

路径：`agent/steps/runner.py::_run_real` → `sim/runner.py::simulate` → [`sim/backend.py::RenodeBackend`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/sim/backend.py)。

每个用例单独执行，基本步骤为：

1. 检查 ELF、Renode、时长和 timeline。
2. `_compile_schedule` 按时间组织事件与故障恢复动作。
3. 加载平台、传感器模型和 ELF，开启 UART 记录。
4. 将相邻事件的时间差转换为 `emulation RunFor`，在事件点调用具体模型命令。
5. 读取串口记录、进程退出结果及故障日志，形成 trace。

例如下面只是对其已有动作的说明，不是我们生产系统新增的测试模板：

```text
0ms 设置某输入
500ms 改变输入
1000ms 注入暂时失效
1500ms 恢复
2000ms 结束
```

宿主负责把它翻译为“推进 500ms → 操作 → 再推进 500ms”，模型不用生成 Renode 启动命令或管理子进程。Renode 虚拟时间与宿主进程超时分开。

trace 样本字段为 `t_ms、dir、channel、value`。其中输入样本来自编译的计划，并非独立测得的“固件已收到输入”；串口输出才来自运行记录。采样记录的来源必须区分。

### 3.6 judge：用规则比较运行轨迹

[`judge/evaluate.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/judge/evaluate.py#L84) 选择 monitor，交给 `judge/judge.py` 计算结果，再补充崩溃、复位、无输出等规则。

monitor 的概念值得借鉴：

| 类型 | 意图 |
|---|---|
| always | 某个条件在观察范围内始终成立 |
| never | 不应出现某个状态 |
| eventually | 在指定期限内应出现某个结果 |
| within | 触发条件成立后，在时间窗口内出现响应 |

例如 `within` 判定会查找触发时间、计算截止时间、寻找满足条件的输出，返回实际观察值、预期和时间点。结果分 `PASS / FAIL / INCONCLUSIVE`。

但这是有限采样上的程序判断，不意味着覆盖了未采集的所有连续状态；monitor 语义和采样完整性本身也需要验证。

**核心断点：** `expected_observable` 只进入 timeline 生成提示词，并未作为可执行判据传入 `evaluate`。主路径传入的是 timeline、trace 和原需求。判定器随后选择预设 gold monitors，或用简化函数生成规则。因此“计划说测 A”不保证“程序最后真的判断 A”。

### 3.7 explain / report：解释失败，不改写事实

[`explain.py`](https://github.com/Divyanshu1405/firmware-testing-agent/blob/main/agent/steps/explain.py#L34) 对每条 FAIL/INCONCLUSIVE 结果调用模型，提示词提供需求、来源、失败证据和轨迹。

要求明确标注 hypothesis，引用需求与失败时间，说明可能涉及哪类固件逻辑。它不负责改写 verdict，也没有接着自动修改工程再运行的主图循环。

实际实现仍有不足：每条失败会重复发送完整 trace；相同 test_id 的多个解释写入同一字典键，可能覆盖前一条。不能把它直接当作完善的低成本故障汇总机制。

## 4. 它的上下文为什么看起来更可控

`agent/llm/router.py` 的调用形式是 `llm.invoke([HumanMessage(content=prompt)])`，每次发送当前构造的提示词，而不是持续追加全部对话。

因此共享 state 是**程序的记忆**，不是模型每次都要读取的长聊天记录。节点显式选择输入，有利于控制每轮内容。

但它仍存在重复：timeline 每个场景都发送全部 requirements；解释每条失败都发送完整 trace。重试也不都包含上次错误。

在不命中缓存、不重试、没有备用模型调用的理想情况下，若有 N 个场景、F 条需要解释的结果，逻辑请求数约为：

```text
1 次需求提取 + 1 次场景规划 + N 次 timeline + F 次解释
= 2 + N + F
```

这只是源码推导，不是实测调用量或 token 统计。不能据此宣称它一定比我们便宜。真正值得学习的是**显式输入边界**，而不是简单切断历史；修正阶段必须提供当前版本、全部相关错误与改动依据。

## 5. 深读发现的具体问题：不能照搬

| 问题 | 源码依据 | 对我们的教训 |
|---|---|---|
| 声明能力超过执行能力 | TimelineAction/提示词包含 UART 注入；`_compile_schedule` 无对应分支 | 能力表应由实际 adapter 能力生成，并有覆盖测试 |
| 动作语义不一致 | ramp/drift 分支直接设置目标值，未使用 over_ms 实现渐变 | 字段存在不代表语义已执行；需验证动作行为 |
| 预期与判据脱节 | expected_observable 未传入 judge；自动 monitor 只看 threshold/time 等 | 需求 → 测试 → 断言 → 证据必须能追踪 |
| 特例冒充通用规则 | 按固件名选 gold；温湿度日志正则、固定回退值 | 不将参考工程的答案、日志和驱动修复塞进通用逻辑 |
| 输入可能被当作输出证据 | 输入记录与解析输出可同名；`_get_channel_samples` 只按 channel 筛选 | 证据应标来源、方向、运行 ID；输入计划不能证明输出正确 |
| 文件缺失会走 mock | 上层 `run_simulations` 的 `not fw_p.is_file()` 分支返回 synthetic mock，并生成 PASS | 生产执行缺失应明确失败；mock 只能显式用于机制测试 |
| 重试不一定获得新信息 | timeline 失败后原提示词重试；plan 同提示词还可能命中相同缓存 | 反馈完整错误；识别无进展，不做相同无效重试 |
| 没测完可能缺少阻断 | timeline 失败可被跳过；CLI 无 verdict 也可能退出 0 | 空测试、缺失用例和未覆盖需求不能当作验收完成 |
| “确定性规则”也可能错误 | 通用阈值规则的 when/then 条件相同；UART 非空无法表达任意功能 | 确定性执行仅保证重复计算一致，不保证规则符合需求 |

进一步的边界：底层 `sim.runner` 对缺失 Renode 的处理确实返回 sim_error，上层 judge 会返回 INCONCLUSIVE；这与上层缺失固件走 mock 是不同路径。此前“它不会把基础设施失败变成通过”的描述需要限定到真实执行路径，不能概括所有入口。

同样，宿主超时不自动等于固件死锁；串口静默也不一定是异常。参考实现的这些规则必须带适用前提才能成为通用检测。

## 6. 与当前 Hardware-CLAW 的对应

本次对照了当前 `verification_context.py`、`verification_loop.py`、verification prompt 和 skill：

- 我们已经给 Agent3 提供工程身份、需求、器件控件和工具能力，不需要从零重写 profile。
- 当前 Agent3 仍为 planning_only，不启动仿真；完整提交 → 检查 → 总体审查 → 原子修改 → 再审查处于同一会话。
- 当前动作等待是墙钟时间，数字 pin 读取不是电压或 PWM 测量；没有通用功能断言执行器。不能因参考项目有 Renode 虚拟时间就声称我们已经有同样能力。
- 我们已有审查和修改留痕要求，参考项目没有最终总体审查，不是删除我们审查环节的理由。

建议借鉴以下机制，而不是照搬它的八个节点：

1. **固定可测能力，减少自由探索。** 基于当前工程生成控件、观察接口、证据语义和限制，缺能力时说明缺口，不让模型猜。
2. **测试与判据一起保持。** 每例清楚表达需求、刺激、观察对象、预期关系、允许误差及依据。宿主负责 ID、版本、执行调度和实际采证位置，减少模型维护机械索引。
3. **模型给业务意图，宿主负责机械展开。** 受支持的通用动作由 adapter 翻译；不能为了表面可执行，偷偷把未知动作改成默认通道。
4. **保留确定性校验和总体语义审查，但明确分工。** 程序检查格式、引用、能力和参数；模型审查需求覆盖与判据依据。审查意见不是事实证明，不得无依据削弱需求。
5. **未来的执行阶段返回结构化失败事实。** 包含用例/需求、执行状态、预期、实际、采证来源、时间基准及原始文件。环境故障停止；证据不足补测；真实行为失败再考虑固件修正。
6. **改动依旧批量反馈和留痕。** 汇总同轮全部已知问题后一次修改，再运行相关测试和回归；保留基线、错误、差异与次数/预算退出条件。

这些是职责边界，不要求新增六个 Agent、六个中间文件或六次模型调用。

## 7. 一个贯穿例子：按钮控制 LED

仅作理解流程的示例，不添加任何工程专用生产模板。

假设需求明确为“按下按钮灯亮，松开灯灭”：

1. 工程能力表确定哪个按钮可设置 pressed，LED 接到哪个引脚，以及实际可观察什么。
2. Agent 提出检查初始状态、按下后的输出、松开后的输出、重复操作；不强行扩展为与需求无关的故障注入。
3. 每次动作关联相应输出检查；宿主生成命令和采证身份。
4. 执行器运行，返回实际观察及其来源。GPIO 电平只能证明引脚状态，不能无条件证明实物 LED 已正确点亮。
5. 判定器依据连线极性和需求计算比较结果，不能固定“高电平必然亮”。
6. 若按下后输出不变，Agent 根据按钮输入、采证、接线和源码判断应补充什么观察，再给出可能的输入极性、引脚或状态逻辑问题。没有证据时不直接宣判根因。

如果需求没有明确响应时限，Agent 可以记录设计假设，但不能擅自把某个毫秒数变成用户要求。当前工具没有精确仿真时间证据时，也不作精确响应时延结论。

## 8. 建议下一步

先讨论并确定一个最小的**测试契约**：让测试意图、可执行输入、观察方式和判定依据保持一致；再检查现有 Agent3 字段哪些可以复用、哪些机械工作可交给程序。随后才接执行器与反馈。

不建议现在照搬此项目重写整个流程。它能帮助我们缩小问题边界，但没有替我们解决任意硬件组合的判据生成；后者仍是我们需要重点验证的部分。
