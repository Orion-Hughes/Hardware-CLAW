# Hardware-CLAW 程序目录

完整操作入口见 [根 README](../README.md)，首次安装见 [环境配置](../docs/guides/SETUP.md)。本目录是正式程序，不是 ESP-Claw 板载 Agent 的移植版。

## 常用操作

- 网页：双击 `Start-Agent.cmd`；结束时双击 `Stop-Agent.cmd`。
- CLI：`.\.venv\Scripts\python.exe -X utf8 -B main.py --question "需求"`。
- 恢复任务：加 `--task 任务ID`；绑定工程：加 `--project 工程ID`。
- 离线回归：`.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v`。
- 查看参数：`.\.venv\Scripts\python.exe -X utf8 -B main.py --help`，不调用 API。
- 烧录：点击网页顶部“固件烧录”，选择工程、串口，编译准备并人工二次确认；无需命令行。CLI 保留为可选入口，见 [烧录指南](../docs/guides/FLASHING.md)。

网页烧录使用独立 N32R16V 实物构建（32MB OPI Flash / 启用OPI PSRAM，采购记录标称16MB，未实物验证）。仿真 `build.json` 与实物 `build-physical.json` 分开，不改原工程源码和Wokwi导出。

API 配置集中在 `hardware_claw/api_config.py`。本地 `DS_Api.txt` 只放密钥本身，不提交 Git；也支持 `DEEPSEEK_API_KEY` 环境变量。更换后重启服务。

## 代码导航

| 目录 / 文件 | 职责 |
|---|---|
| `main.py` / `app.py` | CLI / Chainlit 网页适配 |
| `hardware_claw/runtime.py` | 统一执行、消息事件和运行摘要 |
| `hardware_claw/coordinator/` | 任务持久化、阶段委派、交接、诊断与交付 |
| `hardware_claw/stages/` | selection / generation / verification 固定子 Agent |
| `hardware_claw/tools/` | 模型可调用的受控接口，实际权限按阶段注册 |
| `hardware_claw/catalog/` / `knowledge/` | 本地资料读取服务 / 硬件连接卡及来源 |
| `hardware_claw/projects/` | 工程修订、脚手架、GPIO 表及 VS Code 导出 |
| `hardware_claw/contracts/` / `validation/` | 输入输出契约 / 静态检查和观察结果边界 |
| `hardware_claw/adapters/` | 编译及预留的仿真适配器 |
| `hardware_claw/deployment/` | 完整烧录镜像、串口枚举、计划预览与用户确认执行，不向模型开放 |
| `prompts/` / `skills/` / `templates/` | 系统提示、阶段指导和只读格式 |
| `tests/` | 软件机制回归，fixture 不作生产答案 |
| `Agent-Service.ps1` | 本机服务启停；运行配置及日志放根 `temp/chainlit-runtime/` |
| `requirements.txt` / `requirements-lock.txt` | 依赖范围 / 版本快照 |

工程和运行记录放根 `workspace/`，不放程序目录。导出位置、计划位置与数据流见 [文件结构](../docs/guides/PROJECT_STRUCTURE.md)。支持范围见 [项目状态](../docs/STATUS.md)，阶段职责见 [架构](../docs/architecture/OVERVIEW.md)。
