# 选型子Agent：职责与使用（2026-11-02）

selection已作为固定子Agent接入主协调器，使用现有LangChain和API配置。每次委派创建独立工具循环与上下文，不继承主Agent的完整对话；主Agent接收简要交接，不接收所有硬件原文。

## 职责、输入与输出

职责：概括需求、搜索候选、确认接口与资源需求、判断平台/仿真适用范围、给出有依据的选型和资料缺口。无工程写入、编译、仿真、烧录、联网或递归创建Agent权限。

输入：objective、original_request（初始目标）、user_request（本轮修改）、工程ID、accepted_selection（宿主提供的有效选型资料）、未完成阶段的简短反馈。主Agent只转达目标和约束，不应凭记忆补充硬件候选或实现细节。

输出：status、summary、requirements、hardware_ids、decisions、assumptions、blockers、source_refs、next_stage，以及compatibility、removed_hardware_ids、change_reason。宿主补入detail_ref和selection_update，分别指向详细记录和本次复用/读取/移除的实际记录。next_stage仅为建议，主Agent遵从用户范围决定是否继续，子Agent不能主动启动其他阶段。

退出状态：

- completed：需求和硬件明确，所选硬件已有宿主认可的有效旧证据或在本轮实际读取，资料状态允许且无未解决阻碍。增量选型还须提交覆盖最终组合的兼容性分析。仅表示完成选型，不保证兼容性推理全部正确，更不是硬件验收。
- needs_input：用户必须决定的关键约束缺失。
- blocked：资料、模型或预算等条件不满足；不擅自换器件或虚构参数。
- failed/cancelled：运行失败或被取消，保留已有用量与记录。

## 工具与Prompt

| 功能 | 范围 |
|---|---|
| search_hardware | 现有只读硬件搜索，返回连接层的选型摘要 |
| read_hardware | 子Agent默认view=selection；返回功能/I/O、平台范围、依赖摘要、资料缺口和目录，不自动读取全部原文 |
| read_hardware定向补读 | view=usage必须同时指定references；用于核对影响选型的具体信息，禁止整包加载编程资料 |
| SelectionReport | LangChain ToolStrategy提供的结构化提交工具；不是第三个硬件查询工具 |

普通生成Agent的read_hardware仍默认usage，行为兼容；选型限制由阶段自己的Schema和工具适配器执行，不只依赖提示词。

- 系统提示词：`LangChain/prompts/selection.md`。
- 阶段Skill：`LangChain/skills/stages/selection.md`，宿主自动加载，不需要模型额外调用load_skill。
- 执行器、独立上下文、用量与提交校验：`LangChain/hardware_claw/stages/selection.py`。
- 已接受选型的证据快照与复用：`LangChain/hardware_claw/stages/selection_state.py`。
- 选型视图：`LangChain/hardware_claw/catalog/bundles.py`；不新增一套硬件数据库。

## 校验、成本和记录

宿主校验最终硬件ID是否有有效继承证据或本轮读过、资料状态与阻碍、来源引用是否真实返回、交接长度与格式。可解析的结构化提交校验失败时将原因返回子Agent，最多允许一次修正；原始错误调用保留。当前模型返回非法JSON时，可能直接以MISSING_REPORT结束，尚未加入这类错误的自动修复。这不是对所有自然语言断言的事实核验，也不是仿真验收器。

## 增量选型

1. 宿主从同一任务的最新已接受选型及其详细记录恢复证据，不信任模型自行提供的旧结论或其他任务的引用。
2. 每次阶段开始时，在本地检查已使用的连接卡、上游定义、平台与已解析依赖元数据等来源哈希。未变化的器件以精简资料包继承；资料变化、被删除或映射改变的器件单独失效。无关的目录新增不会让全部器件失效。这是本地检查，不调用LLM重新选型。
3. 子Agent只查询新增或失效器件。重复读取有效旧器件的selection请求由工具适配器返回复用提示；确实需要查证细节仍可用usage定向补读。首次选型必须实际读取所选器件。
4. 结合新旧资料分析需求覆盖、接口、资源、供电适用范围和平台。优先局部调整，确实不可行才重选；移除旧器件必须列明ID及原因。宿主检查分析字段、覆盖范围和结论状态，不保证自然语言分析的数值推理正确。
5. 仅completed替换已接受方案。失败或阻塞保留旧方案，但不能据此声称新增需求已满足，也不能绕过未完成选型进入生成。selection_update的applied标识本次交接是否被接受；失败不记为移除了全部旧硬件。

旧记录若有真实read_hardware证据，可在内存中恢复快照并核对派生元数据，不改写历史。缺乏可信记录时重新读取。原始工具记录仍完整存储；给模型的继承包不包含全部API原文。来源新鲜度在阶段开始检查，不覆盖运行过程中并发修改资料的情况。

主子共享任务500,000已报告token预算，选型阶段另有100,000已报告token、12次模型响应、24次业务工具、240秒限制。额度在调用前根据已返回用量检查，单次请求仍可能越界；无用量或异常中断的请求不伪造token。最终提交因校验被拒绝时，提供方已返回的计费响应也记录。

完整阶段记录存于 `workspace/.tasks/coordinator.sqlite3`，包含委派输入、原始工具结果、模型输出、校验反馈、来源记录和逐次provider usage。任务handoff_ref与detail_ref分别标识简要交接和详细记录；不能把详细记录当作下一阶段交接。数据不提交Git。前端显示阶段开始、阶段用量、本轮主子合计与最终解释。

## 如何使用

网页打开 http://127.0.0.1:8000，输入 `/coordinator` 后给出选型需求。原生成模式仍保留，不能把它当作已经完成的generation子Agent。

在LangChain目录独立运行选型子Agent，不调用主Agent模型：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.stages --question "只做选型：用ESP32-S3、测距传感器和灯环做距离提示，运行于Wokwi"
```

由主Agent委派：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B main.py --coordinator --question "只做选型：用摇杆控制舵机，并用灯环显示状态，用于Wokwi"
```

初版实测见[测试报告](SELECTION_AGENT_TESTS_20261102.md)，增量复用结果与失败记录见[增量选型测试](SELECTION_REUSE_TESTS_20261102.md)。仍需改进：结构化输出可靠性、补读的必要性判断、自然语言断言的准确性、交接简洁度。后续工作是generation子Agent，再接verification子Agent。
