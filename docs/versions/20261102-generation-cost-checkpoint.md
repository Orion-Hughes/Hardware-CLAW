# 生成成本检查点：暂停测试，准备版本对比

## 保存范围

运行代码基线为 `6d722a3`，本检查点只补充测试记录和回退索引，未修改Agent、工具、提示词、资料卡或验证器。所有预算扩大都只发生在临时测试进程，已恢复生产默认值。

按用户要求仅本地Git提交，不推送GitHub。原始API响应、请求快照和任务数据库保留在根目录temp，生成工程保留在workspace；它们不进入Git，密钥、聊天记录和安装目录同样不提交。此提交保存代码与汇总结论，不声称把未跟踪的实验数据备份到了Git。

## 实际API测试

均使用当时配置的deepseek-flash，数字来自提供方usage。生成完成、编译、仿真是不同判据。

| 尝试 | API次数 | 耗时/秒 | 输入tokens | 输出tokens | 本次tokens | 结果 |
|---|---:|---:|---:|---:|---:|---|
| 电位器生成，临时15万；复用已接受选型 | 10 | 21.03 | 148,795 | 3,034 | 151,829 | 预算停止；文件已写，未检查或编译 |
| DHT22 + SSD1306，任务累计30万 | 5 | 18.593 | 59,605 | 3,501 | 63,106 | 选型报告修正后因屏幕卡unreviewed被拒；无工程 |
| 同一任务改为ST7789 240×240 | 12 | 35.062 | 231,890 | 6,428 | 238,318 | 选型完成；累计301,424触线，工程v0，无已接受设计 |
| 同一ST7789工程，累计上限100万 | 16 | 52.234 | 545,041 | 10,963 | 556,004 | 达16次模型调用限制；工程v6，基础检查fail，未编译 |

后三行共享任务，累计33次API、输入836,536、输出20,892、总计857,428 tokens。不能把每次任务累计值再相加。本次ST7789续跑输入缓存512,896、非缓存32,145；费用不能直接按总token数计算，日志不含人民币账单。

最新运行没有重新选型，恢复同一工程及已接受交接。不过当前生成执行器每次创建新的子Agent图，不恢复上一次生成的完整模型/工具消息，所以会重新读取使用资料。这不是从被停止的那次模型上下文原位续跑。

## 已定位问题

1. 大资料包在后续请求历史中重复携带。ST7789必读文件超过单次返回长度时，Agent需要补读；遗漏必读项会先提交失败，再补读。整个头文件是否都必须加载，需要另行评估，未为本例放宽约束。
2. 板卡/外设设计Schema使用错误反复发生。最新续跑第3、4、5次分别收到DUPLICATE_INSTANCE、INVALID_BOARD、DUPLICATE_INSTANCE，第6次才保存设计。
3. 写入源码后发生多轮主动重写，包含一次PATCH_MISMATCH，均发生在真实编译之前。
4. 最新第16次调用执行基础检查，随后被GENERATION_MODEL_CALLS=16阻止继续；没有触及100万token线。错误为ModelCallLimitExceededError。
5. 基础检查存在通用误报：源码定义`static const uint32_t SERIAL_BAUD = 115200;`，调用`Serial.begin(SERIAL_BAUD)`，也打印`HWCLAW_BOOT`；但`hardware_claw/validation/files.py`只用正则匹配字面量`Serial.begin(115200)`，返回OBSERVATION_REQUIRED。不能据此认定实际串口初始化失败。未修改验证器或源码来掩盖此失败。
6. SSD1306历史样板可运行不等于当前资料连接层已完整接入。当前卡的驱动头文件/依赖字段为空，状态unreviewed；推荐测试前没有核对该状态是准备遗漏。

## 当前限制和工程状态

- generation：80,000 tokens、16次模型调用、40次业务工具调用、600秒。
- selection：100,000 tokens；任务累计：500,000 tokens。
- 临时100万上限已退出，不是永久配置变更；Web服务未改。
- `workspace/task-dcd24458b92f-18fa28c08241`：版本6，有设计、接线、配置、源码与README，基础检查失败，build/simulation/behavior均not_run，无导出的simulation文件夹。
- 本检查点不重新运行付费测试；文档和数字以本地记录核对，不将历史软件单元测试外推为工程成功。

## 本地证据索引

- `temp/generation-150k/result.json`、`COST_BREAKDOWN.md`
- `temp/generation-oled-300k/result.json`、`REPORT.md`
- `temp/generation-st7789-300k/result.json`、`REPORT.md`
- `temp/generation-st7789-1m/result.json`、`api-responses.json`、`request-*.json`
- 隔离任务数据库：`temp/generation-oled-300k/tasks/coordinator.sqlite3`

回退候选与比较口径见[版本清单](ROLLBACK_OPTIONS_20261102.md)。
