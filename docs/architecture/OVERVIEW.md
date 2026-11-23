# 当前架构与开发入口

## 职责

主程序通过LangChain调用模型，由主协调Agent安排三个固定阶段。阶段不是任意创建角色，宿主程序始终负责权限、版本、文件和执行边界。

| 角色 | 负责 | 不负责 |
|---|---|---|
| 主协调Agent | 理解任务、阶段委派、进度/证据读取和有限修复交接 | 任意Shell、无界重试、未经确认的烧录 |
| Agent1 / selection | 查询连接卡与上游资料、硬件选型、兼容性和选型复用 | 固件生成、虚构缺失参数 |
| Agent2 / generation | 接线设计、固件源码、版本化修改、提交候选 | 手写宿主配置、安装任意库、运行Wokwi或烧录 |
| Agent3 / verification | 理解需求与工程、生成测试用例/步骤、总体审查 | 当前尚不实际执行测试计划或判定功能通过 |
| 宿主程序 | 目录/修订、配置生成、GPIO表、静态检查、编译、导出、人工确认的实物上传 | 把编译成功或Agent口头声明当成硬件功能证明 |

## 一次需求的数据流

1. `app.py`（网页）或`main.py`（CLI）把输入交给`runtime.py`。
2. `coordinator/`保存任务状态，注册委派和诊断读取工具；预算统一受`limits.py`约束。
3. `stages/selection.py`读取本地连接卡、驱动API和资料，保存选型报告。
4. `stages/generation.py`读取已选硬件，设计接线，调用工程工具保存源码与修订并提交候选。
5. `generation_finish.py`接管静态检查、编译和导出；失败时提供有界诊断反馈。不得手改输出后冒充Agent成功。
6. 委派verification时，`stages/verification.py`利用需求、当前工程、完整GPIO表和可用观察能力生成计划。当前尚不执行计划。
7. 用户在VS Code手动仿真；实物上传在独立网页中选择工程、端口和目标，准备镜像并人工二次确认，不交给模型直接执行。

## 工具与资料

- `tools/hardware_catalog.py`：`search_hardware` / `read_hardware`。连接卡链接Wokwi模型、驱动API、指导文件；资料从本地来源锁定库读取。
- `tools/project_tools.py`：设计保存、只读配置生成、源码读写/补丁、版本和候选提交等。具体工具范围由阶段注册决定。
- `catalog/`、`knowledge/`：名称/依赖/属性/引脚与来源。正式API、资料状态和实测状态分开维护，不能为单个工程加入答案模板。
- `projects/`：不可变修订、目录保护、GPIO表及VS Code导出；`validation/`提供确定性的基础检查。
- `coordinator/evidence.py`、`projects/source_context.py`：让主协调层读取实际阶段、源码和错误证据。
- `adapters/`与`integrations/wokwi_mcp/`：编译和已有仿真观察适配。适配存在不等于已接入Agent3执行。
- `deployment/`：本机网页、串口枚举、实物构建、镜像校验、人工授权、日志和取消。执行权限不注册给Agent。
- `prompts/` / `skills/` / `templates/`：系统提示、阶段规则、按需技能以及宿主只读格式。不要把演示工程或测试fixture放进生产提示作为答案。

## 仿真与实物构建

共用生成源码与固定Arduino 2.0.17，PlatformIO平台固定`espressif32@6.12.0`，但不是同一份二进制：

| 用途 | 构建 | 报告 |
|---|---|---|
| Wokwi / VS Code交付 | 通用ESP32-S3，8MB，未启用PSRAM | `.hwclaw/build.json` |
| 当前网页实物上传 | 按采购记录N32R16V，32MB OPI Flash，启用OPI PSRAM | `.hwclaw/build-physical.json` |

实物构建在临时快照加入固定参数，不覆盖生成源码、Wokwi构建或旧导出。尚未核对实物丝印、实际烧录；16MB物理PSRAM不等于已验证应用可用16MB。分区与存储模式不能跨板卡猜测复用。

## 扩展顺序

扩展板卡/硬件先维护有来源的规格与驱动，再做软件检查、真实编译以及独立功能验收。新增观察与执行能力时同时设计输入输出、时限、取消、失败证据和退出条件。约束见[AGENTS](../../AGENTS.md)。
