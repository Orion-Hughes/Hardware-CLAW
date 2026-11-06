# 主Agent协调层（2026-11-02）

**Agent3重建后的变更：** verification已接入只读规划器，主Agent可委派生成具体计划，但不能执行仿真。该模式不要求已有构建，完成时检查本次工程版本的计划记录；`verified`交付仍要求真实功能证据。新数据流与实际测试见[规划器说明](AGENT3_FTA_PLANNER.md)及[测试记录](AGENT3_FTA_TEST_RESULTS.md)。下文“verification尚未接入/需要构建”的表述保留为旧协调层开发记录，当前规划入口以此更新为准。

已实现主Agent、selection选型子Agent和generation生成子Agent；verification尚未接入。原生成流程仍可用；新协调模式需要显式进入。选型职责见[选型说明](SELECTION_AGENT.md)；生成职责与早期预算停止记录见[生成说明与测试](GENERATION_AGENT_20261102.md)。2026-11-05两次宿主调度实际子Agent的测试已编译导出成功，主协调LLM没有参与；使用临时100万token上限、未仿真，不能称默认预算下已稳定可用。最新结果和第三子Agent计划见[当前进度](PROGRESS_20261105.md)。

## 职责与工具

主Agent继续使用LangChain `create_agent`，负责理解请求、分派任务、解释结果和交付。阶段角色由宿主固定注册，不提供任意spawn_agent，不允许子Agent递归创建角色。

| 主Agent工具 | 职责 |
|---|---|
| get_task_state | 当前需求、任务版本、工程版本、阶段可用性、简要交接、已报告用量 |
| run_stage | 委派selection、generation或verification，返回状态、摘要、交接引用和阻碍 |
| deliver_project | 导出当前可交付工程；verified必须有宿主记录的功能通过证据 |

旧生成Agent的17个工具没有直接暴露给主Agent。selection读取资料并确定需求/选型；generation开放10个业务工具，设计连线、生成或修正代码并检查、编译；verification预留采集仿真证据并诊断，交回生成阶段修正。

## 文件与数据流

```text
用户 → runtime.execute_turn → 主Agent（prompts/coordinator.md）
                            ↓ get_task_state / run_stage / deliver_project
                     coordinator/service.py
                            ↓ 固定阶段执行器接口（selection、generation已接入）
                     简要交接 / 状态 / 引用

LangChain/hardware_claw/coordinator/
  agent.py       LangChain工具封装与预算中间件
  contracts.py   阶段输入、交接、交付参数
  service.py     调度、前置条件、版本与完成证据检查
  store.py       SQLite任务状态、阶段记录、主Agent运行记录
LangChain/hardware_claw/stages/selection.py   选型子Agent与阶段范围/交接校验
LangChain/hardware_claw/stages/selection_state.py   已接受选型的证据快照与增量复用
LangChain/hardware_claw/stages/generation.py  生成子Agent、工具范围与编译交接
LangChain/hardware_claw/stages/common.py      共享用量统计和有限JSON报告修正
LangChain/prompts/selection.md               子Agent系统提示词
LangChain/skills/stages/selection.md         宿主自动加载的选型流程
workspace/.tasks/coordinator.sqlite3   本地任务记录，不提交Git
```

交接记录需求、硬件ID、决策、摘要、阻碍、工程版本及简短兼容性分析。历史阶段通过ID引用，不递归复制。通用执行器接口收到本次目标、初始/当前用户请求、交接记录、current_handoffs及工程绑定，不接收主对话的完整历史。选型执行器进一步整理为accepted_selection（来源仍有效的旧选型资料）和简短失败反馈，只要求查询新增或资料变化的器件，再检查整体兼容性。完整证据快照存于详细记录，不回传主Agent。具体机制及限制见[选型说明](SELECTION_AGENT.md)。

同一任务保留工程绑定。只有讨论/选型时不自动建工程。generation委派先检查有效选型；首次无工程由宿主创建vscode工程并保存绑定，之后必须使用原工程和当前版本。前端在本轮结束/取消时保存绑定，下次请求也会从任务记录恢复。主Agent工具不能编辑任意文件或改写角色Prompt。

## 宿主已实现的约束

- 同一任务阶段串行运行，任务/工程使用版本检查；拒绝跨任务交接引用。
- 当前有效交接以current_handoffs为准，历史引用不能替换当前选型。最近一次选型未完成时不能使用旧选型继续生成。
- 生成需要需求与有效硬件ID；完成生成需要当前修订检查、编译通过。当前verification仅规划，要求已有设计和源文件，不以编译为前置；未来真实执行必须绑定当前有效构建。功能通过仍需要独立证据。
- STAGE_UNAVAILABLE明确保留blocked记录；不重试缺失执行器、不偷偷改走旧流程。超时、取消、异常和格式错误均保留非成功状态。
- 2026-11-06起任务累计已报告token上限1,000,000，主Agent与selection/generation/verification共享。阶段token门槛与总额一致，不再提前以8万等较低额度中断；恢复任务不重置累计用量。阶段委派上限20次；单阶段超时900秒。主Agent每轮16次模型响应、48次工具，协调模式一轮总时限900秒；实际生效的是先达到的限制。
- token在每次模型调用前检查已返回用量，单次仍可能超出阈值；提供方未报告用量会明确标记不完整。按角色分别记账，前端本轮总用量包含子Agent；详细查询不注入主Agent上下文。selection保留12次模型响应、24次业务工具、240秒阶段上限；交接校验最多允许一次修正（第二次拒绝即停止）。
- 主对话仍保留现有最多6轮问答；CLI恢复任务读取持久化状态，不回放完整聊天。
- generation保留16次模型响应、40次业务工具、600秒上限；同一修订同一工具参数超过两次会停止循环。token到线或重复无进展会停止本轮后续模型调用，主Agent不能另开委派绕过；只有新的用户轮次恢复机会，任务累计预算不重置。最终一笔响应可能越过token阈值。

限制：进程强制退出可能留下active_run，此时拒绝重复执行并报告TASK_BUSY；自动恢复/中断任务处理尚未实现。当前没有通用功能验收，因此不能完成verified交付。verification已接入只读规划器，真实仿真执行与判读仍为后续工作。next_stage仅为建议，不自动执行；主Agent必须遵从用户本轮范围。

## 使用入口

网页发送 `/coordinator`，或 `/coordinator 先为我选择一个监测方案`。已有工程绑定保留；在历史侧栏恢复聊天会恢复任务ID。通过 `/query`、`/new 需求` 或 `/project 工程ID` 回到旧流程。

在LangChain目录执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B main.py --coordinator --question "先帮我选型，不生成工程"
.\.venv\Scripts\python.exe -X utf8 -B main.py --task <任务ID> --question "继续讨论这个需求"
```

selection可实际查询并交接；generation可创建绑定工程并调用读写、检查和编译工具。早期真实测试在编译前因token预算停止；后续扩预算测试的成功与限制见[当前进度](PROGRESS_20261105.md)。verification仍返回STAGE_UNAVAILABLE。

## 验证记录

离线测试使用隔离的假执行器验证调度、交接、版本冲突、取消、超时、预算、证据门槛及真实LangChain工具循环；它们不作为生产答案或硬件验收结果。

主Agent初版全套145项离线测试通过（18.433秒），含14项协调层测试；以下为子Agent接入前的历史记录。接入后的测试见[选型子Agent测试报告](SELECTION_AGENT_TESTS_20261102.md)。任务数据库与临时日志已确认在Git忽略范围内。

真实API测试任务 `efa79e3567624a628828569452122301`：查询任务状态 → 委派selection → 返回blocked/STAGE_UNAVAILABLE。没有创建工程，也没有执行硬件查询。3次LLM调用，5.73秒；提供方报告输入5,594、输出483、合计6,077 tokens。原始日志位于本地 `temp/coordinator-main/live-cli.log`。随后收紧了缺失执行器时的解释规则，避免要求用户粘贴已有资料绕过实现缺口；这项措辞调整没有再次付费实测。

generation接入后的早期结果见[生成测试](GENERATION_AGENT_20261102.md)。最新安排是先开发第三个verification子Agent，资料按硬件/软件阶段拆分仍为后续优化；不能将选型completed或编译通过当成功能验证。实施顺序见[当前计划](PROGRESS_20261105.md)。
