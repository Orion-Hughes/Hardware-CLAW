# 文件结构与数据流

更新：2026-11-06。本文描述当前实现；长期目标见 [项目计划](docs/HARDWARE_CLAW_PROJECT_PLAN.md)。

```text
Hardware_CLAW/
├─ LangChain/
│  ├─ main.py / app.py                 CLI / Chainlit 前端
│  ├─ Start-Agent.cmd / Stop-Agent.cmd
│  ├─ hardware_claw/
│  │  ├─ runtime.py / api_config.py   执行、事件、用量 / 模型配置
│  │  ├─ coordinator/                固定委派、任务状态与交接
│  │  ├─ stages/                     selection、generation、verification
│  │  ├─ catalog/                    硬件检索、资料组合、来源与补读
│  │  ├─ projects/                   工程、修订、脚手架、交付
│  │  ├─ contracts/                  工具参数、报告、测试计划
│  │  ├─ tools/                      受控 Agent 工具
│  │  ├─ adapters/                   PlatformIO / Wokwi CLI / MCP
│  │  ├─ validation/                 文件与证据检查；非完整功能验收
│  │  └─ limits.py                   统一预算与限制
│  ├─ knowledge/
│  │  ├─ cards/                      选型信息与资料引用的连接卡
│  │  ├─ upstream/                   固定版本的上游原文
│  │  ├─ guidance/ / platforms/      有来源的补充 / 限定平台配置
│  │  └─ schemas/、catalog.json、sources.lock.json、library.json
│  ├─ prompts/ / skills/             提示词、通用开发指导与阶段职责
│  ├─ templates/                     平台配置、通用规划 JSON 示例
│  ├─ tests/                         软件回归测试
│  └─ .venv/ / DS_Api.txt             本地环境和密钥，Git 忽略
├─ workspace/                        本地运行数据，Git 忽略
│  ├─ .tasks/coordinator.sqlite3     任务、阶段交接、用量与记录
│  └─ <project_id>/
│     ├─ files/                      当前受管固件、diagram 和配置
│     ├─ .hwclaw/
│     │  ├─ revisions/v<version>/    不可变设计与文件快照
│     │  ├─ builds/ / runs/          编译工件 / 原生成入口运行记录
│     │  └─ verification_plans/<id>/ 请求、响应、修正、用量、计划
│     └─ exports/v<version>/        ZIP、manifest、simulation 文件夹
├─ docs/ / references/               项目指导与实验报告 / 外部研究资料
├─ examples/ / evaluations/          参考与正式评估位置
├─ Wokwi/                            既有仿真实验，保留路径
├─ pio/ / tools/ / .secrets/          本机工具链和凭据，Git 忽略
├─ 项目总体信息/                     学校、报销及汇报资料
└─ temp/                             临时脚本、测试沙盒、构建与调试数据
```

## 当前主流程

1. CLI / 前端将需求交给 `runtime.execute_turn`；恢复任务沿用 task ID、工程绑定与累计用量。
2. 主 Agent 通过 `get_task_state`、`run_stage`、`deliver_project` 调度，不直接获得全部工程工具。
3. selection 查询连接卡与使用资料，形成选型和兼容性交接。卡片分别引用仿真、驱动 API、指导资料；保留来源、缺项和续读方法。
4. generation 读取已选硬件资料，设计连线、生成文件、检查并编译。每次写入形成新修订，旧检查和固件不能冒充新版本结果。
5. verification 由程序准备工程、需求和 `io_map`，模型依次生成需求、场景、时间线；程序检查并转换操作，保存计划后停止。实际请求、响应、错误与用量留存。
6. 主程序只导出满足门槛的当前工程。计划可以在没有成功构建时生成，但不能绕过固件交付门槛。

下一步：工程与计划身份核对 → MCP 执行 → 原始证据 → 判定与缺口 → 有界修正 → 重编译及复测。**这条闭环尚未接通。**

## 边界与保留原则

- 资料不是可执行指令。来源、版本和适用范围必须保留；运行库是 `knowledge`，旧 `hardware_library` 未重新启用。
- `documented_not_tested`、编译通过、规划完成、功能通过不能互换。
- `files/` 外部字节变化会被拒绝；Agent 写入的 LF、CRLF 和混合换行原样保持。通过版本化工具修改，不绕过快照。
- 不把单工程修复策略写入生产 skills、模板或通用检查；fixture 只证明软件机制。
- 密钥、聊天、生成工程、安装目录和临时证据不提交 Git。可清理离线 fixture、缓存；原始失败、付费运行记录与复查工程保留。
- 旧源码由 Git 保留；历史文档不改写成新版本结果。当前入口见[文档导航](docs/README.md)。
