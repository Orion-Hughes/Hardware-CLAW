# 选型子Agent：职责与使用（2026-11-02）

selection已作为固定子Agent接入主协调器，使用现有LangChain和API配置。每次委派创建独立工具循环与上下文，不继承主Agent的完整对话；主Agent接收简要交接，不接收所有硬件原文。

## 职责、输入与输出

职责：概括需求、搜索候选、确认接口与资源需求、判断平台/仿真适用范围、给出有依据的选型和资料缺口。无工程写入、编译、仿真、烧录、联网或递归创建Agent权限。

输入：objective、用户原话、工程ID、当前交接ID映射、历史阶段简要交接。主Agent只转达目标和约束，不应凭记忆补充硬件候选或实现细节。

输出：status、summary、requirements、hardware_ids、decisions、assumptions、blockers、source_refs、next_stage。宿主补入detail_ref，指向本地完整阶段记录。next_stage仅为建议，主Agent遵从用户范围决定是否继续，子Agent不能主动启动其他阶段。

退出状态：

- completed：需求和硬件明确、所选硬件已在本轮实际读取、资料状态允许且无未解决阻碍。仅表示完成选型，不保证兼容性推理全部正确，更不是硬件验收。
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
- 选型视图：`LangChain/hardware_claw/catalog/bundles.py`；不新增一套硬件数据库。

## 校验、成本和记录

宿主校验最终硬件ID是否本轮读过、资料状态与阻碍、来源引用是否真实返回、交接长度与格式。校验拒绝时将具体原因返回子Agent，最多允许一次修正；原始错误调用保留，不能只留下最终成功结果。这不是对所有自然语言断言的事实核验，也不是仿真验收器。

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

实测结果、失败案例与用量见[测试报告](SELECTION_AGENT_TESTS_20261102.md)。仍需改进：补读的必要性判断、自然语言断言的准确性、交接简洁度；选型循环在部分案例中仍耗费较多token。后续工作是generation子Agent，再接verification子Agent。
