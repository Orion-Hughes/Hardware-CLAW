# 上游硬件资料库迁移与Agent实测

记录日期：2026-10-29（香港时间）。目标是以原始文档、驱动源码与最小本地关联替代手写API摘要；不是宣称所有Wokwi器件或所有板卡均已支持。

## 已完成的迁移

- 默认根目录：`LangChain/hardware_library/`，`legacy_fallback=false`。
- 旧`LangChain/knowledge/`原文件保留，设置Windows Hidden及VS Code文件/搜索隐藏；不参与默认查询。
- 备份：`backups/knowledge-20261028T085405Z/knowledge.zip`及`manifest.json`，240个文件、1,883,657字节。ZIP SHA256：`ab17153f4fc9ed01d9f9fd4b1908fd9ce179c758d95bb25e2153657f242669cd`。旧文件与清单逐项核验一致。
- 新库：15个关联条目、146个上游模型定义、10个驱动描述、495份带来源和哈希的原文。
- 新增非采购条目：MPU6050、DS1307、HC-SR04、电位器。10条documented_not_tested、4条blocked、1条unreviewed；不代表10条均已功能验证。
- 本轮没有扩展板卡构建支持，仍使用现有ESP32-S3仿真基线。没有推送GitHub。

## 来源与本地维护边界

Wokwi官方文档、Espressif平台头文件来自各自上游。Adafruit库来自驱动维护者，DHTesp和ESP32Servo来自社区维护者；不能统称为所有芯片厂商的官方API。

`associations/`只关联身份、库存、Wokwi模型、管脚、驱动与原文入口。`drivers/`登记原始library.properties、头文件、实现和例程；依赖版本读取原文，不复写手工API用法。供电选择等仿真策略仍明确标为本地信息，不冒充实物电气结论。

Agent运行时按需读取已下载原文，逐文件校验锁定哈希；缺失或改变时返回错误，不联网补查、不静默退回旧库。`integrations/hardware_sources/manage.py`是维护阶段工具，不提供给Agent。全部495份原文校验通过；补取缺失文件模式尚未做端到端恢复测试。

146个模型中未配关联的仍为metadata_only。许可证原文随仓库来源保留；部分旧网页及第三方模型的再分发范围仍需在发布前核对。

## 软件测试

在LangChain目录执行项目虚拟环境的`python -X utf8 -B -m unittest discover -s tests -q`：127项通过，20.349秒。覆盖原查询、工程流程及新增来源哈希、缺失/篡改拒绝、版本派生、来源字段和无旧库回退。

这些测试验证软件机制，不能替代生成固件的功能验收。

## 真实Agent测试

需求：ESP32-S3连接MPU6050和DS1307，共用I2C，每秒报告时间、三轴加速度及温度，初始化失败时有限退出，并实际编译、仿真观察、导出。没有在问题中提供I2C地址冲突的解法。

工程：`workspace/upstream-imu-rtc-1793244281-f363414869a3/`。

Agent通过生产入口读取技能、器件映射与上游API，调用工具创建及修正工程。最初出现缺少驱动依赖、基础检查要求未满足及配置版本过期；Agent自行更新设计、生成配置、修改源码后通过检查和编译。宿主没有手工修补生成文件。

测试暴露的通用缺口：

1. 原始library.properties会包含例程所需依赖，例如MPU6050库声明GFX和SSD1306；不能假设仅使用传感器时依赖清单只有两个库。
2. 现有基础检查对串口启动的字面形式敏感；使用常量不一定被接受。这是检查器能力边界，不是固件语义错误的充分证据。
3. Agent曾用read_simulation_evidence读取不属于MCP证据入口的内容，收到参数/未找到错误，随后改用inspect_simulation。CLI和MCP证据访问方式仍需统一或澄清。
4. Agent读取原文后仍可能自创错误判断。例如某修订把DS1307秒寄存器的BCD十位当成必须为零，导致合法10至59秒被误报INVALID。上游RTClib的RTC_DS1307::now会对寄存器执行bcd2bin(buffer[0] & 0x7F)。这是生成代码问题，不足以证明仿真器地址冲突。

原始版本、编译和仿真证据均保留在工程`.hwclaw/`；完整本轮事件在`temp/hardware-library-migration/agent-events.json`。最终结果和API统计见下节。

## 最终结果

本轮已结束，run_id=`b2f8bf1e53654f019496aa9b8b6cacec`。达到60次模型调用上限，`ModelCallLimitExceededError`，状态error；未人工追加预算。

| 项目 | 实测结果 |
|---|---|
| 当前修订 | v16，基础检查和真实编译通过 |
| 最终CLI仿真 | timeout，墙钟180.36秒；已取得部分串口输出，超时具体原因尚未确定 |
| 生成固件问题 | v16仍有错误BCD掩码检查，将有效时间误报INVALID；不能交付为功能正确 |
| MCP交互 | 5次请求，4次执行成功，最后一次参数不合法；曾改变加速度、温度和角速度 |
| 可确认的观测 | v11串口温度由24变为33°C，Z角速度变为90deg/s；X加速度输入3.5g时读到约19.61m/s²，不能等同目标输入全范围正确 |
| 验收 | behavior=not_run，未调用evaluate_tests；没有功能通过结论 |
| 交付 | 宿主在停止后自动导出v16已编译工程，ready_for_vscode仅表示可打开，不是Agent成功完成需求 |

可打开目录：`workspace/upstream-imu-rtc-1793244281-f363414869a3/exports/v000016/simulation/`；ZIP在同级`project.zip`。没有人工修补生成文件。历史观测不外推到v16。

API：响应元数据model_name=`deepseek-flash`；60次模型响应、71次工具请求，耗时784.34秒。提供方累计报告输入4,176,393、输出16,757、总计4,193,150 tokens；其中缓存读取1,601,920 tokens。`usage_complete=false`：runtime对错误终止保守标记不完整，此处只报告已返回数据，不推算账单费用。原始统计在工程`.hwclaw/runs/`及`temp/hardware-library-migration/agent-summary.json`。

同一轮输入从6,322增长到108,976 tokens，get_driver_api原文结果累计68,881字符、get_hardware_info累计32,056字符；本轮未压缩成针对该案例的生产答案。需要继续改进按需原文检索、重复证据处理和无进展停止机制，不能仅提高调用上限。

结论：新资料入口、真实工具读取、生成、编译和交互观测链路已经打通；这个组合的生成质量与自主纠错未通过端到端验收。优先改进有来源的诊断与通用证据访问，再使用不同器件组合复测，不向资料库写入本案例的修复答案。

前端原有服务已重启，健康检查成功；新进程默认使用新资料库。9份相关文档的本地链接检查和git diff --check通过。
