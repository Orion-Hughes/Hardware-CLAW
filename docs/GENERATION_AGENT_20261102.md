# 第二个子Agent：生成阶段（2026-11-02）

generation已实现并接入主协调器，复用现有工程工具。192项离线测试通过；第一轮真实API测试在生成阶段达到80,000 tokens停止线，未完成编译，后续付费测试全部停止。因此本次只确认结构与部分真实工具链路，不能声称多轮生成/交付验证成功。

## 职责、输入、输出

负责已选器件的接线与固件设计、保存源码、基础文件检查、真实编译及基于编译错误的有限修正。仿真、功能验收和真机操作不属于此阶段。

输入是原始目标、本轮请求、主Agent简短委派、有效selection交接、工程绑定与版本、相关阶段简短反馈；不继承主Agent完整历史或选型工具原文。首次generation前宿主检查选型证据新鲜度，没有工程则在workspace创建并持久绑定；后续必须继续同一工程。讨论/选型不创建工程。

输出GenerationReport包含状态、当前project_version、全部hardware_ids、摘要、决策、假设、引用和阻碍。completed要求当前修订的基础检查与编译pass，不能凭模型声明。主Agent调用deliver_project导出，verified仍需要尚未实现的功能通过证据。

## 工具与资料范围

| 工具 | 范围 |
|---|---|
| read_hardware | 仅已选器件，默认usage、32,000字符；必要原文被省略时用references补读 |
| load_template | 只读平台模板，不是业务答案 |
| get_project / read_project_file | 当前绑定工程状态、设计和源码 |
| update_project_design | 全部已选器件、接口、GPIO、依赖；拒绝未经selection确认的型号变化 |
| scaffold_project | 根据设计产生固定配置和电路文件 |
| write_project_files / apply_project_patch | 保存源码和说明，受版本/路径/大小检查约束 |
| check_project_files | 基础结构与部分一致性检查，不是功能验收 |
| compile_project | 现有PlatformIO受控编译，当前版本必须检查通过 |

共10个业务工具，另有GenerationReport结构化提交。没有search_hardware、load_skill、模拟工具、烧录、export_project或任意shell。generation的Skill与通用固件Skill由宿主直接加载。

生产文件：

- `LangChain/hardware_claw/stages/generation.py`：阶段执行器、工具适配、来源/选型/编译状态检查。
- `LangChain/hardware_claw/stages/common.py`：从selection抽取的公共计费、报告JSON修正与记录；selection原行为有回归覆盖。
- `LangChain/prompts/generation.md`、`LangChain/skills/stages/generation.md`：职责和阶段流程。
- `coordinator/service.py`：首次建工程、固定绑定、预算停止传播；`runtime.py`汇总主子用量和新工程交付。
- `app.py`：显示阶段名称，保存/恢复宿主创建的工程绑定。

## 用量与停止约束

- 每次generation：80,000已报告tokens、16次模型响应、40次业务工具、600秒。
- 同一修订的同一工具参数最多调用两次，第三次停止；资料不足不通过重复查询消耗预算。
- 达到生成token线或重复无进展时停止本轮所有后续模型调用；主Agent不能重新委派绕过。新用户轮次可再请求，任务500,000累计预算仍保留。
- JSON与Schema/来源校验共用一次报告修正机会，保留原始失败。修正语法时只提供报告提交工具。
- 本轮付费测试另设累计150,000 tokens停止线；只按提供方返回用量统计，最后一笔响应可能略超单阶段阈值。触线后不重试、不提高预算、不手工补工程。

## 离线测试

新增11项生成测试：独立子Agent图、主Agent委派和交付、首次工程绑定、续改复用、缺选型/缺证据拒绝、工具范围、未经读取/检查/编译的完成声明拒绝、JSON报告修正、预算阻止主Agent继续委派、重复调用停止、取消后保留文件并释放任务。

全套192项通过，49.310秒。fixture编译产物有TEST_DOUBLE_ONLY标记，全部保存在root temp，只证明软件机制。它们不是生产固件或真实端到端验收。日志：`temp/generation-offline.log`。

## 第一轮真实测试：触线停止

请求：生成仅供Wokwi使用的ESP32-S3＋电位器工程，每500ms读取模拟量并输出串口；完成选型、生成、检查和编译，不仿真/烧录。

使用真实selection，然后独立调用真实generation；没有用fixture替代选型，没有修改模型生成物。

| 阶段 | 结果 | 模型调用 | 输入tokens | 输出tokens | 总tokens |
|---|---|---:|---:|---:|---:|
| selection | completed | 4 | 24,104 | 2,379 | 26,483 |
| generation | blocked / GENERATION_TOKEN_BUDGET | 6 | 79,952 | 2,526 | 82,478 |
| **合计** | **停止全部后续付费测试** | **10** | **104,056** | **4,905** | **108,961** |

整轮27.84秒。API为当前DeepSeek deepseek-flash配置。生成阶段各次输入为4,551、13,983、14,517、15,114、15,490、16,297 tokens；并没有无限重复查库，主要问题是读取24,426字符的硬件使用资料后，每次模型请求持续携带它们及工具Schema/历史结果。

额外回合：selection最初引用未实际读取的原文，被拒绝后自行移除；generation第一次把SERIAL_BAUD=115200和SAMPLE_INTERVAL_MS=500放进只接受GPIO常量的pin_defines，被拒绝后自行改为仅POT_ADC_PIN=4。随后生成设计、运行scaffold并读取固定配置。第6次响应提出write_project_files时累计用量触线，宿主没有执行该写入。

保留状态：工程v2，仅设计和固定配置；源码拟写参数保留在模型事件中，未由人工写入工程。检查/编译/仿真均not_run，无simulation导出目录。原始失败不可算生成成功。

本地证据（不提交Git）：

- 任务`1b9c48b3d81548199a37d669c64cc068`，隔离库`temp/generation-live/tasks/`。
- `temp/generation-live/potentiometer-1793626545.json`：逐阶段原始工具和模型记录。
- `temp/generation-live/api-ledger.json`：逐次provider usage及停止标志。
- `temp/generation-live/usage-audit.json`：统计核对。临时测试驱动的外部累计字段因Pydantic复制字典而残留0，逐次usage与生产阶段预算不受影响；按逐次provider数据核对实际108,961。修正了驱动引用共享账本的方式，但保留原始日志和审计说明，未为验证该修正再调用API。
- 工程`workspace/task-1b9c48b3d815-ee15dd670246/`，未手工修补。

## 未完成测试与下一步

计划中的主Agent真实委派、同一工程真实续改、第二种硬件组合、多轮编译成功测试均未执行，因为首轮已触发用户要求的用量停止条件。离线模拟测试不能替代这些验收。

下一步应先缩减生成阶段每轮携带的原文和重复配置，保留来源与关键API事实；改善通用字段语义提示（pin_defines只装GPIO）。不能靠提升预算掩盖成本，也不能写电位器专用模板。是否及何时恢复付费测试由后续用户请求决定。

使用入口仍为`/coordinator`。CLI单独调用生成子Agent时必须提供已有有效选型任务：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.stages --stage generation --task <任务ID> --question "基于已选硬件生成工程"
```

此命令会发出真实API请求；本轮因预算停止，没有继续执行。verification子Agent仍未实现；当前编译平台仍限登记的ESP32-S3基线，并非通用多板卡支持。
