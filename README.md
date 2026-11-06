# Hardware-CLAW

电脑端嵌入式开发 Agent：从文本需求生成接线设计、固件和 Wokwi 工程，并编写测试计划。采用 LangChain 主协调 Agent 与固定职责的子阶段。ESP-Claw 是架构灵感与研究对象，不是运行依赖。

## 当前能力（2026-11-06）

```text
用户需求 → 主协调 Agent
             → selection：查询硬件、选型、兼容性与交接
             → generation：接线、固件、基础检查、编译
             → verification：需求 → 场景 → 时间线 → 静态检查
             → 主程序交付工程与测试计划
```

| 模块 | 已实现 | 边界 |
|---|---|---|
| 主协调层 | 固定阶段委派、任务持久化、工程绑定与交付 | 通过 `/coordinator` 或 `--coordinator` 显式进入 |
| 硬件选型 | 查询、批量读取、来源与缺项、已确认选型复用 | 本地连接卡引用上游资料；并非所有 Wokwi 元件都有完整编程支持 |
| 工程生成 | 接线与固件、修订、基础检查、PlatformIO 编译、VS Code 导出 | 当前构建基线为 ESP32-S3 仿真，不等于采购板实物配置 |
| 验证规划 | 从工程和可用能力生成需求、场景及时间线，程序转换并检查 | **仅规划，不执行仿真，也不判定功能通过** |
| 仿真适配 | 已有 Wokwi CLI 和官方实验性 MCP 受控观测适配器 | 尚未将 Agent3 计划接入执行；引脚读取仅数字电平 |
| 待开发 | 计划执行、证据评估、有限修正、真机上传监控、更多板卡、Edge-AI 顾问 | 不以编译或模型回答代替功能验收 |

主协调任务共享 **1,000,000 reported tokens**，恢复不重置；调用次数、超时及无进展保护仍有效。每场景最多 **32 个事件、64 个转换后操作（含等待）**，显式等待总计最多 60 秒。见[运行限制](docs/DEVELOPMENT_LIMITS.md)。

## 使用

在 `LangChain` 目录双击 `Start-Agent.cmd` 启动前端，网页输入 `/coordinator` 进入分阶段流程；`Stop-Agent.cmd` 停止服务。旧单 Agent 入口仍保留，工具范围不同。

```powershell
cd D:\Hardware_CLAW\LangChain
.\.venv\Scripts\python.exe -X utf8 -B main.py --coordinator --question "描述需要生成的嵌入式系统，并生成测试计划，本次不执行仿真"
.\.venv\Scripts\python.exe -X utf8 -B main.py --task 任务ID --question "继续此前任务"
```

安装、API 配置和其他入口见 [LangChain 使用说明](LangChain/README.md)。API 会产生费用；每轮统计提供方报告的 token、调用次数和耗时。密钥仅保存在本地。

成功导出的工程位于 `workspace/<project_id>/exports/v<version>/simulation`；用 VS Code 打开该文件夹，运行 `Wokwi: Start Simulator`。生成、编译、规划完成和功能验收通过是不同状态。

## 最近验证与已知问题

- 全量离线回归 **219 项通过**；已修复 CRLF / 混合换行误报 `EXTERNAL_CHANGE`，真实外部修改仍会被拦截。
- 此前三组主协调测试中，摇杆串口、距离与灯环完成编译/导出/规划；均未执行仿真。
- 本次恢复电位器与舵机任务：基础检查恢复，生成 8 个场景；但包管理器找不到 `ESP32Servo@1.1.2`，编译失败，宿主拒绝导出。源码与电路未手工修改，原失败保留。
- 计划时序、观测充分性与判据仍需真实执行检验。任务回合 `completed` 不代表工程已交付，需同时查看阶段结果与 `delivery_status`。

用量、合并取舍、清理范围和待办见[维护报告](docs/MAINTENANCE_MAIN_20261106.md)。下一步是[将计划接入真实仿真](docs/SIMULATION_EXECUTION_CHECKPOINT_20261106.md)，随后实现证据评估与有限修正。

## 文档与目录

- [文档导航](docs/README.md)、[文件结构与数据流](PROJECT_STRUCTURE.md)。
- [工具与技能](docs/TOOLS_IMPLEMENTATION_STATUS.md)、[主协调层](docs/COORDINATOR_IMPLEMENTATION.md)、[Agent3 规划器](docs/AGENT3_FTA_PLANNER.md)。
- [毕业设计最终目标](docs/HARDWARE_CLAW_PROJECT_PLAN.md)、[硬件资料](LangChain/knowledge/README.md)、[已购硬件](references/HARDWARE_INVENTORY.md)。
- [版本管理](docs/VERSION_CONTROL.md)、[开发约束](AGENTS.md)：禁止单工程特例优化，不手工修补生成工程冒充 Agent 成功。

`temp/` 集中存放临时数据。可再生成的测试残留可清理，付费调用和原始失败保留。`workspace/`、密钥、聊天、工具链及虚拟环境不提交 Git。`pio/`、`tools/`、`Wokwi/` 和个人项目资料保持既有路径。
