# Agent自主仿真与评估

2026-10-27。底层ProjectService、CLI新建入口、Chainlit `/new` 均默认vscode输出；显式旧模式仍保留。默认输出为含BIN/ELF的simulation文件夹。

## 新工具

`simulate_project(expected_version)`核对当前源码、基础检查及固件，按硬件选择受控场景，复制仿真输入到temp，在子进程中运行Wokwi CLI。Token由宿主从`.secrets/wokwi-cli-token.txt`读取，仅进入子进程环境，不传给模型、不打进交付包。捕获真实串口流与CLI日志，并将证据保存到工程`.hwclaw/simulations/<attempt>/`。

`evaluate_tests(expected_version)`校验当前版本、固件/电路/场景身份及证据哈希，按Python规则判定。它不接受调用方传入预期值、任意YAML、日志路径或pass/fail。测试在第一次仿真时冻结于`.hwclaw/test_plan.json`；删除传感器不能自动换成更容易的测试。

输出包括：verdict、逐项expected/observed/matched、错误记录、findings、测试覆盖范围和未覆盖项目。LLM根据证据诊断，不能自己决定判定结果。

## 当前支持范围

首个行为场景`dht22_serial_v1`：恰好一个DHT22，输入24°C/40%→30°C/65%→恢复24°C/40%，随后再等一次恢复值。

串口协议：`Temperature: 24.0 C | Humidity: 40.0 %`，一位小数，建议CRLF。场景等待该固定格式；评估器单独解析实际serial-log-file，并容忍CLI把多条完整消息拼接而省略换行。CLI回显预期文字不能充当实测。常量传感器输出、没有恢复输出、错误输出均不能通过。

不覆盖显示内容、其他外设、阈值业务、精确采样间隔或实物正确性。DHT22场景通过只代表该场景；`full_project_acceptance=not_evaluated`。没有支持场景时返回unsupported，不能偷偷改成启动即pass。

## 执行与退出

- Agent按检查→编译→仿真→评估→导出执行。失败后可读源码、修补，重新走完整链路。
- 每轮模型20次、工具32次、仿真工具最多3次，任务总墙钟900秒。每次模拟时限25秒、进程墙钟90秒；输出上限1MiB，取消/超时回收进程树。
- 已完成的相同固件/电路/契约可复用原始证据；仅改README不能靠重试掩盖失败。工具或网络错误可在预算内重试。
- `completed`是CLI执行结束，不意味着行为通过。业务错误为fail；宿主时限或场景等待超时为timeout；连接/授权/执行故障为tool_error。
- 修改文件导致旧报告失效；重新编译后固件哈希变化也会使旧结果失效。证据被改动拒绝评估。
- 原始交付包不会为新诊断而自动改写。当前诊断以`.hwclaw/evaluation.json`与UI摘要为准；新导出包记录导出时的判定。
- 用户仍可获得失败工程的simulation文件夹用于查看。宿主状态会显示validation_failed或validation_unavailable，不能把可打开文件夹误认为功能通过。
- 正常结束或预算退出时，若当前版本已检查、编译且尚未导出，宿主尝试打包已有文件。此兜底不编辑源码、不重新编译、不改变失败判定；没有有效固件则不能承诺可运行交付。

本轮离线与实际API测试见[测试报告](AGENT_SIMULATION_TEST_REPORT_20261027.md)。

## 已知边界与下一步

当前已知ESP32-S3+DHTesp1.19组合可在Wokwi中TIMEOUT。Agent可以自行仿真、评估并关联这个已知问题，但尚不能自动安装用户参考工程中的修订驱动和上拉电路。下一步应维护并实现受控driver variant安装，不能靠人工改生成工程或让模型凭空补底层驱动。

扩大测试覆盖应扩展受控场景库（显示、舵机、灯环、板间通信），不一定每个器件都新增tool。更完整的日志检索可后续加入绑定工程的报告读取接口。真机阶段仍需detect_devices、flash_firmware、monitor_serial；edge-AI建议器也尚未实现。

编译器与CLI仍是本机子进程，不是OS沙箱；未实现跨进程任务调度或持久化队列。一个真实连接中断已被正确记录为tool_error，不宣称网络可靠性已解决。
