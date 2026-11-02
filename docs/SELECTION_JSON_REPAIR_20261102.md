# 选型报告JSON错误反馈与重提（2026-11-02）

原问题：模型在SelectionReport参数里输出了没有双引号的文字值。LangChain将其记入invalid_tool_calls，而ToolStrategy的Schema校验只处理成功解析的tool_calls；只有错误调用时，循环直接结束为MISSING_REPORT，没有机会反馈。

## 修改

`LangChain/hardware_claw/stages/selection.py`的SelectionTrace增加after_model钩子：

1. 识别无法解析的SelectionReport，保留原始模型消息与用量。
2. 返回匹配调用ID的错误ToolMessage，包含原始参数raw_arguments和JSON解析器的错误、行、列、偏移。错误参数明确作为数据，而非指令。
3. 在同一LangChain图内回到模型，保留已有需求和工具结果。下一次只暴露SelectionReport；新业务查询即使被模型发出也不执行。同批先前已发出的查询允许先完成。
4. JSON语法错误与原有Schema/证据校验共用一次修正机会。修正后的报告仍按原标准检查；再次失败、预算不足或超时就停止，不新开阶段重试。

不对错误JSON做替换、补引号或容错解析。无报告和无关工具参数错误维持非成功；同一响应同时提交有效与错误报告时返回AMBIGUOUS_REPORT。无法关联调用ID或错误参数超过32,000字符时停止反馈，原始内容仍在详细记录内。阶段原有token、模型次数和总超时继续约束修正。

## 实测：把真实错误JSON交回模型

取上一轮摇杆/舵机失败日志的原始模型消息，未手工改写错误：

```text
"change_reason": 首次选型，无旧器件；无删除或替换。
```

在隔离测试任务里回放此前5条模型响应，并实际执行其本地只读查询，然后通过当前模型进行一次真实修正。回放响应标记test_replay、新增API用量为0，不能算新增付费请求或自然端到端生成成功；修正调用经过生产SelectionExecutor、错误反馈钩子、ToolStrategy和原有校验。

结果：completed，原三个器件ID保留，来源与Schema校验通过。模型返回：

```json
"change_reason": "首次选型，无旧器件；无删除或替换。"
```

错误反馈之后的硬件查询为0。原始失败记录未改写。该结果证明本次报告修复和接受机制生效，不证明硬件组合或所有自然语言断言已验证。

| 实际API调用 | 模型调用耗时 | 输入tokens | 输出tokens | 合计tokens |
|---:|---:|---:|---:|---:|
| 1 | 6.26秒 | 20,432 | 1,628 | 22,060 |

模型为当前配置的DeepSeek deepseek-flash。回放加修复总耗时6.94秒；上表用量为提供方本次返回，不包含历史计费。没有额外运行自然端到端选型或硬件仿真；不据此估算普遍修复率。

本地可检查文件（不提交Git）：

- `temp/selection-json-repair/original-malformed.json.txt`：错误参数原文。
- `temp/selection-json-repair/repaired-report.json`：模型修正且通过校验的报告。
- `temp/selection-json-repair/replay-live-result.json`：回放标记、实际请求/响应、用量与完整阶段记录。
- `temp/selection-json-repair/replay_live.py`：临时重现脚本；不会被生产Agent加载。

## 离线回归与部署

新增11项测试，覆盖原文/位置反馈、已有资料保留、只提供报告工具、一次重提、JSON与语义错误共享额度、Schema和来源校验不被绕过、token/模型次数限制、同批调用、有歧义报告及禁止新查询。全套181项测试通过，耗时35.747秒；本地日志`temp/selection-json-repair/offline.log`。

测试fixture仅用于软件机制，不向生产Agent提供硬件答案。修改不涉及硬件资料、工程模板或生成工程。服务需重启加载新代码；正常选型无需用户手工粘贴错误JSON，宿主会自动反馈。
