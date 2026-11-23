# 本机环境配置与使用

适用于当前 Windows / PowerShell 实现。队友需要自行配置 Python、API 密钥和编译器；仓库不包含本机安装目录，不保证跨平台直接运行。以下命令在根目录执行，实际克隆位置可以不同。

先取得源码：

```powershell
git clone https://github.com/Orion-Hughes/Hardware-CLAW.git
cd Hardware-CLAW
```

## 1. Python 环境

安装 Python 3.12 和 Git 后，在仓库根目录运行：

```powershell
py -3.12 -m venv LangChain\.venv
.\LangChain\.venv\Scripts\python.exe -m pip install -r LangChain\requirements-lock.txt
```

`requirements-lock.txt` 是依赖版本快照，`requirements.txt` 是主要依赖范围。先用快照复现；如遇网络或版本不可用，应保留安装错误并核对，不要无记录地升级全部依赖。源码包回归不等于已在空白电脑完成全部工具安装。

后续始终使用项目 `.venv` 的解释器，无需激活环境，不要混用系统 Python。

## 2. 模型配置

自行创建 `LangChain/DS_Api.txt`，使用 UTF-8，只写一行 API 密钥，不加标签、引号或说明。文件已忽略，不能提交。也可以使用本机 `DEEPSEEK_API_KEY` 环境变量。

优先级为：项目密钥文件 → 环境变量 → 显式 `--ask-key` 的隐藏输入。存在但为空/非法的密钥文件会报错，不会自动改用环境变量。

模型默认值、服务地址和客户端创建均在 `LangChain/hardware_claw/api_config.py`。当前代码默认模型名为 `deepseek-flash`；可用 `DEEPSEEK_MODEL` 环境变量覆盖，需保证账号支持且服务进程继承该变量。这里记录代码配置，不承诺提供方永远提供该型号。

问题、必要工程资料和工具结果会发送给模型提供方。不要把隐私资料混入生成需求；调用会计费，取消已经发出的请求不保证免除费用。

## 3. PlatformIO 编译器

当前编译适配器固定寻找仓库内 `tools/platformio-venv/Scripts/pio.exe`，并使用根 `pio/` 作为 PlatformIO Core 数据目录。已有工具时不要重复安装。

在新电脑上，可以按当前本机版本准备该位置：

```powershell
py -3.12 -m venv tools\platformio-venv
.\tools\platformio-venv\Scripts\python.exe -m pip install platformio==6.2.0
.\tools\platformio-venv\Scripts\pio.exe --version
```

平台、框架、编译器与固件库由构建配置解析，首次编译可能需要联网下载；源库版本和目标平台仍须匹配。仅安装 PlatformIO Core 或显示版本号，不代表这些依赖已经齐全。当前支持范围以平台配置、连接卡及 [入库指南](HARDWARE_ONBOARDING.md) 为准。

## 4. 启动、停止与继续

- 双击 `LangChain/Start-Agent.cmd`。服务只监听 `127.0.0.1:8000`；端口被其他程序占用时不会替你关闭其他程序。
- 网页普通文本进入主协调流程；`/new 需求` 新建任务，`/project 工程ID` 绑定工程。
- 双击 `LangChain/Stop-Agent.cmd` 停止服务。关闭网页不等于停机。
- 改动源码、密钥或配置后重启。服务日志与启动状态在 `temp/chainlit-runtime/`，界面配置从程序目录复制过去，不应直接改运行缓存。

CLI（先进入 `LangChain/`）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B main.py --help
.\.venv\Scripts\python.exe -X utf8 -B main.py --question "你的需求"
.\.venv\Scripts\python.exe -X utf8 -B main.py --task 任务ID --question "后续修改"
```

离线检查入口和库读取：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.catalog search joystick
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v
```

这两条不调用真实模型。主程序实际处理需求才会计费；统计以提供方返回为准。

## 5. 交付和故障定位

- 最终工程：`workspace/<project_id>/exports/v<version>/simulation/`。打开整个目录，按 [VS Code 指南](VSCODE_DELIVERY.md) 手动仿真；插件需要单独安装和有效授权。
- 测试计划：工程 `.hwclaw/verification_plans/<id>/`。不要求每个工程都有计划，只有委派并完成规划才会生成完整结果。
- 任务/聊天和具体修订位置见 [目录说明](PROJECT_STRUCTURE.md)、[会话说明](CHAT_HISTORY.md)。
- 没导出时先看阶段状态、静态检查、编译报告与原始日志；不能只看模型口头回复。自动仿真执行未开放；烧录可通过网页顶部独立入口完成，CLI 为可选入口，均需人工确认且尚未实物验证，见 [烧录指南](FLASHING.md)。
- 外部直接改动受管 `files/` 可能触发版本冲突，不要绕过快照校验。需要手工实验时另用副本，并明确它不再是原始交付。

## 6. 队友协作

修改前 `git status --short`；无冲突时 `git pull --ff-only`。阅读 [AGENTS.md](../../AGENTS.md) 后在自己的分支开发，先离线回归，再按授权预算做真实集成验证。提交前检查暂存内容，不提交密钥、聊天、安装环境、`workspace` 和 `temp`。详细步骤见 [版本管理](VERSION_CONTROL.md)。
