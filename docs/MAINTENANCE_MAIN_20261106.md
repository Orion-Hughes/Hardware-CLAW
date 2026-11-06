# 本地 main 集成与维护记录（2026-11-06）

范围：修复通用换行校验、软件回归与真实任务恢复、清理测试残留、更新当前文档，合并到本地 main。本次不推送 GitHub，不执行仿真或真机烧录。

## 修复与验证

`ProjectService.write_files` 原样写入换行符，但 `_check_live_files` 用 `read_text()` 比较；Python 通用换行转换会将 CRLF / CR 转为 LF，使原样文件误报 `EXTERNAL_CHANGE`。

修复为读取字节并与快照内容的 UTF-8 编码比较，不改变生成源码、上游资料或快照。真实的字节变化，包括仅换行变化和非法 UTF-8，仍拒绝覆盖。修复提交：`69752d5`。

- 工程服务 21 项测试通过，覆盖 LF、CRLF、CR、混合换行、读写/补丁、不可变旧快照，以及外部篡改。
- 完整离线回归 219 项通过，77.481 秒；保留全部 20 个 `test_*.py` 测试源文件。
- CLI `--help` 冒烟检查通过，更新过期的 verification pending 描述。
- 合并提交 `6467641` 的代码树与修复提交一致；之后只更新文档及清理 Git 忽略的产物，没有再次修改 Agent 流程。
- 日志：`temp/merge-main-20261106/offline-tests.log`。离线 fixture 不证明硬件或端到端行为正确。

## 真实 Agent 恢复测试

沿用原失败任务 `16ccd3ab3564421ca88dbe6b34356bbd` 和原工程 `task-16ccd3ab3564-b7c62a793c11`，不重置预算。通过生产 `execute_turn`、主协调 Agent 与真实 generation / verification 执行器运行，没有替换工具结果或人工修补工程。

| 范围 | 模型调用 | 输入 tokens | 输出 tokens | 合计 tokens |
|---|---:|---:|---:|---:|
| 主协调 | 5 | 32,771 | 1,434 | 34,205 |
| generation | 7 | 146,928 | 1,487 | 148,415 |
| verification | 11 | 148,323 | 8,905 | 157,228 |
| 本轮总计 | **23** | **328,022** | **11,826** | **339,848** |

全轮耗时 **101.86 秒**，其中 generation 31.89 秒、verification 57.813 秒。用量全部来自提供方返回，`usage_complete=true`。原任务由 473,954 增至 **813,802 tokens**，未提高既有 1,000,000 上限；本轮没有再次重试。

实际结果：

1. 原工程字节校验恢复正常，基础文件检查通过，换行误报不再出现。
2. 真实编译失败。日志先出现 `Could not find the package with 'ESP32Servo @ 1.1.2' requirements`，再出现 `ESP32Servo.h: No such file or directory`。日志显示包管理器确实尝试安装，不能把问题直接解释成“系统禁止联网”。精确版本的仓库可用性/映射需另行核实。
3. Agent 仅修改生成工程 README，将不实的编译完成表述改为失败；前后源码、电路和构建配置哈希未变。旧版本与原失败保留。
4. 验证阶段生成 **8 个场景、6 个覆盖缺口**。计划引用 `3fcd5dcece4b4d45955ee335d43ba510`；只做规划，没有执行仿真。计划含人工操作/观测限制，不等于已经具备全自动执行条件。
5. `deliver_project` 返回 `BUILD_REQUIRED`，没有导出可启动文件夹。最终 `delivery_status=incomplete`。顶层回合的 `status=completed` 仅表示这轮对话正常结束，不能作为工程成功率指标。Agent 在最终回复中明确报告编译与交付失败。

原始证据：

- `temp/merge-main-20261106/resume/`：请求、前后状态与哈希、逐事件记录、summary、完整任务记录。
- `temp/e2e-budget-1m/20261106T075041Z/potentiometer_servo/`：首次失败与换行诊断，未覆盖。
- `temp/builds/task-16ccd3ab3564-b7c62a793c11/4aea747a2f9f4cdf9f44c6073519827c/build.log`：本轮编译原始日志。
- 工程 `.hwclaw/verification_plans/3fcd5dcece4b4d45955ee335d43ba510/`：实际提示词、响应、修正、用量及计划。

## 清理与文档

删除已核实的离线 fixture、旧机制测试残留、离线交付测试构建目录和程序/测试字节码缓存：**31 个目标目录，11,743 个文件，47,710,552 字节（约 47.7 MB）**。删除前核对绝对路径、Git 跟踪范围与重解析点；所有已选目标删除成功。

`temp/hardware-catalog-tests` 和 `temp/project-tests` 包含测试用重解析点，本轮保留，未跨链接递归清理。完整清单及跳过原因：`temp/merge-main-20261106/cleanup-{manifest,summary,skipped}.json`。

保留：全部测试源文件、真实生成工程及不可变修订、付费请求/响应、原始失败、计划、聊天、凭据、已安装工具链、研究与学校资料。未以清理名义删除真实任务构建证据，也未全量清空 temp。

根 README、PROJECT_STRUCTURE、工具状态、主协调说明、项目计划和能力草案更新为当前事实；新增 `docs/README.md` 区分当前指导与历史报告。旧架构和上下文文档标为历史设计，删除目录文档中失效的重复“预留/待实现”描述，保留历史实验依据。

## main 合并取舍

原 main 为 `417d78b`，功能分支为 `97c53df`，共同基点 `f1329ab`。原 main 独有提交是一套此前已回退的硬件库、上下文与审查架构，不是新的独立修复。

已检查该提交涉及的旧 `hardware_library`、driver API/association、context/message_view/token_budget、skills/review/build cache 及相应测试文档。这些与重建后的 `knowledge/cards`、固定阶段、当前预算和规划器互不兼容，不能只解决文本冲突后自动引回。

因此先保存修复，再用 **ours 合并策略**记录旧 main 的历史关系，保留重建后的完整代码树；不是挑选冲突文件后默认接受其他旧文件。合并提交 `6467641`，原 main 另备份在 `codex/backup-main-before-integration-20261106`。随后 main 快进到包含修复、集成和文档的功能分支。没有改写历史，没有推送远端。

## 下一步与已知限制

1. 将已有规划的静态转换结果接入官方 MCP；执行前核对工程版本、构建工件、计划哈希与真实控件支持。
2. 明确依赖来源、精确版本和包管理器安装标识的可用性。处理的是知识/构建机制，不向生产流程添加舵机或某个工程的特例补丁。
3. 区分“对话结束”“阶段完成”“工程交付”“功能通过”；统一最终汇报与成功率统计，避免只读顶层 completed。
4. 执行后记录刺激、模拟时间、观察值、原始证据和覆盖缺口；再接独立评估与有限修正。未支持或证据不足不计通过。
5. 计划里人工操作、PWM/机械反馈等缺口，以及模型将缺包推断成权限限制的问题仍需解决。本次没有以 fixture 通过或换行修复声称这些问题已消失。
