# 第三个 Agent：参考 firmware-testing-agent 的只读规划器

本轮从第三个 Agent 开写前的 `c3e79ef` 建立 `codex/agent3-fta-planner`。旧代码、失败记录和调研已提交为 `1cd3033`，保留在 `codex/backup-agent3-before-fta-rebuild`；没有推送 GitHub。回退范围与原始进度见 [备份说明](AGENT3_REBUILD_CHECKPOINT.md)。

## 实际实现范围

参考 [firmware-testing-agent](https://github.com/Divyanshu1405/firmware-testing-agent) 的 `spec → plan → timeline`：

```text
程序读取已有工程、需求、器件资料，形成 io_map
    ↓
一次 LLM 调用提取 requirements
    ↓ JSON/来源行号检查，失败携带候选和错误有限重试
一次 LLM 调用生成 test_plan 与 gaps
    ↓ JSON/需求引用/覆盖/主通道检查
每个场景一次 LLM 调用生成 timeline
    ↓ JSON/参数/时序/工具操作检查
程序输出 plan.json + plan.md，结束
```

不是自由调用工具的第三套循环。主协调层仍使用 LangChain Agent，`run_stage(verification)` 调用固定 Python 流程；每一步通过现有 LangChain 模型客户端发送独立 system/user 两条消息。没有新增 Agent、上下文压缩服务、审查 Agent 或 JSON Pointer 修改流程。旧版总体审查没有带入这次重建；这是按本次“尽量参考项目、先给出具体计划”的范围选择。

规划器不拥有编译、仿真、固件修改或再次委派权限。实际模型请求 `tools=[]`；程序仅使用现有 MCP 参数 Schema 做离线校验，不调用 MCP 服务。无需为了规划先构建工程。未来真实执行仍必须检查构建与运行环境。

## 与参考项目的对应和适配

| 参考项目 | 本地适配 |
|---|---|
| ELF profile / io_map | 直接读已有设计、diagram、源文件和登记器件控件，不猜 ELF 平台 |
| requirements | 需求 ID、描述、原文行号、可选阈值/时间、歧义标识 |
| test_plan | 场景 ID、需求 ID、情形、主通道、理由、预期观察；另列 gaps |
| timeline | 相对时间、set/read/write、已登记通道、值；读取附文字预期 |
| backend 转换 | 程序转换为现有 Wokwi MCP 操作与等待，不执行 |
| 最多三次局部生成 | 每次都反馈当前候选及真实校验错误；失败不丢弃场景冒充完成 |

不复制默认温度通道、缺失固件走 mock、金标准专用日志规则、未实现的故障注入和静默删除失败用例。

## 文件与信息流

| 文件 | 职责 |
|---|---|
| `LangChain/hardware_claw/stages/verification_context.py` | 本地工程快照、器件操作表、资料包和版本身份 |
| `LangChain/hardware_claw/stages/verification.py` | 固定调用、预算、有限修正、记录与计划输出 |
| `LangChain/hardware_claw/contracts/verification.py` | 短 JSON 契约、覆盖检查、时间线转换 |
| `LangChain/prompts/verification/{requirements,plan,timeline}.md` | 三种任务的固定提示词 |
| `LangChain/templates/verification/*.json` | 通用格式示例，占位通道不构成业务答案 |
| `LangChain/hardware_claw/coordinator/service.py` | 委派和真实规划记录校验，功能交付门槛不变 |
| `LangChain/tests/test_verification_planning.py` | 隔离的机械流程测试，不提供生产场景答案 |

程序读取当前绑定工程的所有受管文本文件，以及所选器件的 simulation/guidance 来源；不读取驱动 API 全文，不让模型重新查询器件库。控件必须有来源与参数范围。数字 pin 列表来自已连接且有模型定义的引脚，它只表示可提出数字快照读取，不承诺模拟电压或 PWM 测量。

每轮发给模型的信息：

| 调用 | 输入 |
|---|---|
| requirements | 带行号的原始工程需求；另行标明本次规划请求，避免把工作指令提取成固件需求 |
| plan | 原始需求、提取要求、工程文本、仿真资料、io_map、能力限制与资料缺口 |
| timeline | 同一工程资料包、当前场景和该场景关联的要求，不携带其他场景完整对话 |
| 同步骤重试 | 当前步骤的上述输入，加上前一候选与实际错误；不继承全部失败历史 |

共享资料仍会随场景重复发送；固定前缀有利于提供方缓存，但缓存不等于减少总输入 tokens。没有声称已经彻底解决成本问题。每包超过 100,000 字符会明确停止，不截掉资料继续猜。

## 输出位置与判定范围

输出位于原工程的 `.hwclaw/verification_plans/<plan_id>/`，工程 `files/` 与不可变修订不变：

- `context.json`：程序准备的完整资料包。
- `request-NNN.json`：实际 system/user 内容、格式约束、各部分字符量。
- `response-NNN.json`：原始响应、提供方 usage、耗时和响应元数据。
- `errors-NNN.json`：本轮候选与真实校验错误。
- `requirements.json`、`test_plan.json`、`timeline-T*.json`：通过对应检查的中间结果。
- `plan.json`：成功时包含需求、场景、时间线、MCP 参数、采证位置和缺口。
- `plan.md`：成功时生成的人可读操作表。
- `failure.json`、`metrics.json`：失败原因和每次规划的用量；失败也保留中间结果。

`completed` 表示有本次工程快照对应的完整静态计划，**不表示预期语义正确、仿真已执行或功能通过**。文字预期尚不是自动断言。全为 gaps、某场景失败、项目变化或达到预算都会阻止阶段完成；不能将旧计划作为新工程的完成证据。`deliver_project(scope=verified)` 仍要求真实功能证据。

每场景独立仿真会话的计划，`at_ms` 是宿主相对调度时间，不是精确仿真时钟。同一时间的多项操作仍顺序执行。没有截图或图像判断；VCD 只在工程已经有逻辑分析仪时暴露导出描述，没有自动波形判定器。

## 预算

当前主任务累计 1,000,000 已报告 tokens，主Agent、选型、生成与规划共享，子阶段不设更低token门槛，恢复任务不重置。规划保留30次模型调用、600秒；每个步骤最多三次尝试，最多八个场景。单次输出上限16,384。每场景最多32事件、转换后最多64操作（含等待）、计划等待合计最多60秒；上限不是需要凑够的目标。

预算在下一次调用前检查，最后一次响应可能越线；响应和错误仍保存。无usage时停止后续付费请求。重建早期历史测试曾额外使用300,000停止线，该历史额度不代表当前配置。

## 如何使用

在 `D:\Hardware_CLAW\LangChain`：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.stages --stage verification --project case-joystick-serial-7e47feee5f2b --question "依据当前工程需求生成具体仿真计划，不执行仿真"
```

这条命令会产生新的付费调用。只查看已生成结果请直接打开已有 `plan.md`。也可使用 `--task <任务ID>` 恢复已有任务；不同时传 `--project`。

主协调入口已注册verification。网页 `/project <工程ID>` 后进入 `/coordinator`，要求“仅生成仿真计划”；前端返回Markdown计划下载与用量。原生成模式不会自动切换到此只读阶段。早期真实API测试直接调用第三子Agent；2026-11-06已完成主Agent从需求到工程与计划的真实测试，见[多任务用量与结果](AGENT_E2E_BUDGET_1M_20261106.md)，尚未执行功能仿真。

实测结果、逐轮成本、原始工程完整性及已知计划错误见 [重建测试记录](AGENT3_FTA_TEST_RESULTS.md)。
