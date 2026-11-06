# 100万共享预算：主 Agent 多任务端到端测试

日期：2026-11-06。每个案例从空任务开始，由正式 `execute_turn` 主协调入口运行，使用与 `main.py --coordinator` 相同的模型配置和阶段注册路径。测试脚本只输入需求、记录事件与用量，不指定阶段执行顺序或替代主 Agent 分发。

## 本次修改与边界

- `COORDINATOR_TOTAL_TOKENS=1,000,000`；三个子阶段 token 门槛均引用该值，不再有更低门槛。主 Agent 与子 Agent 累计共用总额，任务恢复不重置；不是每个子 Agent 各有100万。
- 其他调用次数、超时、无进展与格式检查保护保留。按提供方已返回累计用量停止后续请求，最后一笔响应仍可能越过阈值。
- 离线检查：54个协调/选型/生成/规划测试通过；JSON修复测试最初因运行方式的模块导入路径报错，使用unittest discover重新执行11个用例全部通过。共65个通过。
- 本次测量目标：选型、生成、基础检查、编译、工程导出、测试计划。没有执行仿真或烧录，completed及ready_for_vscode均不代表功能验收通过。
- 不修补生成工程，不添加业务专用prompt、skill或模板；各案例及原始失败保留。

## 各任务实测

| 任务 | 状态 | API次数 | 输入 | 输出 | 总tokens | 整轮秒 |
|---|---|---:|---:|---:|---:|---:|
| 摇杆串口检测 | completed | 33 | 452,639 | 20,085 | 472,724 | 146.69 |
| 电位器控制舵机 | blocked | 30 | 460,779 | 13,175 | 473,954 | 84.72 |
| 超声波测距与灯环 | completed | 32 | 529,765 | 17,418 | 547,183 | 136.38 |
| 合计 | | 95 | 1,443,183 | 50,678 | 1,493,861 | 367.79 |

数据来自提供方usage，包含缓存命中的输入；不是字符估算。每个需求仅测一次，因此不能据此估计稳定成功率或普遍平均成本。旧8万门槛失败的234,126 tokens不计入本批合计。

## 分阶段用量

| 任务 | 阶段 | API次数 | 输入 | 输出 | 总tokens | 阶段墙钟秒 |
|---|---|---:|---:|---:|---:|---:|
| 摇杆串口检测 | main | 6 | 36,512 | 1,833 | 38,345 | 未单独计量 |
| 摇杆串口检测 | selection | 4 | 34,152 | 1,988 | 36,140 | 13.440 |
| 摇杆串口检测 | generation | 12 | 230,788 | 5,032 | 235,820 | 50.880 |
| 摇杆串口检测 | verification | 11 | 151,187 | 11,232 | 162,419 | 67.843 |
| 电位器控制舵机 | main | 6 | 41,507 | 1,780 | 43,287 | 未单独计量 |
| 电位器控制舵机 | selection | 5 | 69,629 | 3,810 | 73,439 | 22.050 |
| 电位器控制舵机 | generation | 13 | 304,751 | 6,026 | 310,777 | 37.060 |
| 电位器控制舵机 | generation | 6 | 44,892 | 1,559 | 46,451 | 11.520 |
| 超声波测距与灯环 | main | 6 | 37,359 | 1,807 | 39,166 | 未单独计量 |
| 超声波测距与灯环 | selection | 4 | 35,357 | 2,050 | 37,407 | 12.750 |
| 超声波测距与灯环 | generation | 11 | 307,577 | 5,458 | 313,035 | 52.020 |
| 超声波测距与灯环 | verification | 11 | 149,472 | 8,103 | 157,575 | 56.579 |

阶段墙钟时间含本阶段工具执行，例如编译；不是纯API等待。main没有单独测量纯调用耗时，不用总时间相减冒充。

## 交付物与运行证据

### 摇杆串口检测

- 任务ID：`a85c9700af8c4bfd95a752653953aa91`。
- 工程ID：`task-a85c9700af8c-5eaf6eb751a6`；版本：4；交付状态：`ready_for_vscode`；编译：`pass`；仿真：`not_run`；行为：`not_run`。
- [VS Code工程](D:/Hardware_CLAW/workspace/task-a85c9700af8c-5eaf6eb751a6/exports/v000004/simulation)
- [压缩包](D:/Hardware_CLAW/workspace/task-a85c9700af8c-5eaf6eb751a6/exports/v000004/project.zip)
- `check_project_files`：fail；修订 3；问题码 ['OBSERVATION_REQUIRED']。
- `check_project_files`：pass；修订 4；问题码 []。
- `compile_project`：pass；修订 4；问题码 []。
- [测试计划](D:/Hardware_CLAW/workspace/task-a85c9700af8c-5eaf6eb751a6/.hwclaw/verification_plans/aa1beb7684434097bb671a25baf73832/plan.md)：6个场景、9项缺口；尚未执行。
- 规划校验反馈 `errors-002.json`：["T2:未知channel=joystick.x, joystick.y；可用=['joystick.pressed', 'joystick.x', 'joystick.y', 'joystick:GND', 'joystick:HORZ', 'joystick:SEL', 'joystick:VCC', 'joystick:VERT', 'mcu:3V3.1', 'mcu:4', 'mcu:6', 'mcu:7', 'mcu:GND.1', 'mcu:RX', 'mcu:TX', 'serial', 'status']"]
- 规划校验反馈 `errors-003.json`：["T4:未知channel=joystick.x, joystick.y；可用=['joystick.pressed', 'joystick.x', 'joystick.y', 'joystick:GND', 'joystick:HORZ', 'joystick:SEL', 'joystick:VCC', 'joystick:VERT', 'mcu:3V3.1', 'mcu:4', 'mcu:6', 'mcu:7', 'mcu:GND.1', 'mcu:RX', 'mcu:TX', 'serial', 'status']"]
- 规划校验反馈 `errors-010.json`：[{"type": "extra_forbidden", "loc": ["notes"], "msg": "Extra inputs are not permitted"}]
- 输入缓存命中：377,856 / 452,639（83.48%）。提供方用量完整：True。

### 电位器控制舵机

- 任务ID：`16ccd3ab3564421ca88dbe6b34356bbd`。
- 工程ID：`task-16ccd3ab3564-b7c62a793c11`；版本：3；交付状态：`unavailable_due_to_file_check`；编译：`not_run`；仿真：`not_run`；行为：`not_run`。
- `check_project_files`：EXTERNAL_CHANGE；修订 None；问题码 []。
- `check_project_files`：EXTERNAL_CHANGE；修订 None；问题码 []。
- 输入缓存命中：379,392 / 460,779（82.34%）。提供方用量完整：True。

- 运行时主记录状态：`write_failed`。测试runner另行保存了summary和完整events，子阶段数据库记录仍在；不把主记录写入失败说成无记录。

### 超声波测距与灯环

- 任务ID：`2edc698ab32843ceb7c12eee2b8dbee6`。
- 工程ID：`task-2edc698ab328-902884fe012f`；版本：5；交付状态：`ready_for_vscode`；编译：`pass`；仿真：`not_run`；行为：`not_run`。
- [VS Code工程](D:/Hardware_CLAW/workspace/task-2edc698ab328-902884fe012f/exports/v000005/simulation)
- [压缩包](D:/Hardware_CLAW/workspace/task-2edc698ab328-902884fe012f/exports/v000005/project.zip)
- `check_project_files`：pass；修订 5；问题码 []。
- `compile_project`：pass；修订 5；问题码 []。
- [测试计划](D:/Hardware_CLAW/workspace/task-2edc698ab328-902884fe012f/.hwclaw/verification_plans/4db35200294a42ceb2ec5a5303c9967c/plan.md)：8个场景、4项缺口；尚未执行。
- 规划校验反馈 `errors-003.json`：["events[2]:at_ms必须有序且不超过duration_ms"]
- 输入缓存命中：449,280 / 529,765（84.81%）。提供方用量完整：True。

## 本批判断与待处理问题

两个完成交付的任务分别使用472,724与547,183 tokens；生成分别占235,820与313,035，测试规划分别占162,419与157,575。当前样本显示完整链路大约需要47–55万，生成是最大项，规划约16万；8万生成门槛明显不足，100万总额在本批有余量。不能用一次失败的473,954作为电位器任务的正常完成成本，也不能据此断言更复杂任务都够用。

### 电位器阻碍：通用换行符误报，非外部编辑

原始 `write_project_files` 参数编码为UTF-8后的SHA256，与磁盘 `src/main.cpp` 字节SHA256均为 `6e4e69c09c6f3fc284126d365732d674b73096b23b34d8f801a00fe539bf313c`。文件包含4个CR字符、120个LF字符，磁盘字节与原始提交完全相同。

`projects/service.py` 的 `write_files` 使用 `newline=""` 保留换行，但 `_check_live_files` 使用默认 `read_text`，将CRLF转换为LF后再与保存的原文字符串比较，因此误报 `EXTERNAL_CHANGE`。这不是用户或助手修改了文件。该错误还使运行时最后的delivery读取报错，主记录标记 `write_failed`；runner的summary/events及子阶段数据库记录保留了实际调用量。

本次仅只读取证，没有修改文件或绕过检查。下一步宜修复通用读写比较的一致性，并用LF/CRLF/混合换行和真实外部变更做回归；不能只为这个工程替换换行来宣称Agent成功。取证结果在测试目录的 `potentiometer_servo/newline-diagnosis.json`。

### 摇杆基础检查的额外修正

最初固件已经有 `HWCLAW_BOOT`，且 `SERIAL_BAUD=115200`，但写成 `Serial.begin(SERIAL_BAUD)`。检查器返回OBSERVATION_REQUIRED，Agent改为 `Serial.begin(115200)`后通过。不是遗漏启动标记，原先进度口述已更正。这揭示了静态匹配对等价源码的限制；本次没有修改该检查器。

### 交付检查及保留边界

已核对两个导出目录的 `diagram.json`、`src/main.cpp`、`wokwi.toml`，以及TOML所指向的firmware.bin/firmware.elf均存在；没有实际启动Wokwi。测试计划仍有此前已知的语义局限，此次按用户要求不继续细化。当前网页服务未运行；下次正常启动会加载新的100万预算，本批测试进程已使用该设置。

## 原始记录索引

- 测试目录：`D:\Hardware_CLAW\temp\e2e-budget-1m\20261106T075041Z`。
- [逐次调用用量CSV](D:/Hardware_CLAW/temp/e2e-budget-1m/20261106T075041Z/usage-by-call.csv)。
- 每个案例目录保留 task.json（完整输入）、events.jsonl、summary.json、records.json；工程的.hwclaw目录保留编译与规划证据。
- 同一批运行中没有改提示词、资料、工具或生成工程。报告中的结果是当前代码与输入的单次样本，不代表未来任务保证通过。
