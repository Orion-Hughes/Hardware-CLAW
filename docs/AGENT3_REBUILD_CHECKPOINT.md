# Agent3 重建前备份与进度

用户决定停止扩展旧规划器，回到第三个 Agent 开始前，再参考 firmware-testing-agent 实现只读规划链路。

## 旧版本实际状态

- 当前代码基线：`bc63ab8`，原分支 `codex/selection-reuse-20261102`。
- Agent1 选型、Agent2 生成已有实现；旧 Agent3 为整份计划生成、JSON 检查、总体审查、原子 JSON Pointer 修改。
- 旧 Agent3 尚未执行仿真。离线机制测试通过不能替代真实模型验收。
- 最近两个真实规划测试均失败：电位器/舵机 324,148 token；摇杆串口 177,877 token。主要失败涉及采证动作索引、反复修正、审查误判和预算。详见 `VERIFICATION_WHOLE_PLAN_LIVE_20261105.md`。
- firmware-testing-agent 调研已保存为 `SIMULATION_VERIFICATION_PROJECT_SURVEY_20261105.md` 和 `FIRMWARE_TESTING_AGENT_WALKTHROUGH_20261105.md`。参考项目存在专用回退、能力与后端不一致、预期与判据脱节等限制，不将这些当作通用方案照搬。

## 保留内容

- `workspace/case-potentiometer-servo-b8103bbfa13f`
- `workspace/case-joystick-serial-7e47feee5f2b`

这两个工程是已有人工编写的规划输入，非本轮 Agent2 生成结果；只读使用，保留全部原始失败证据。原件留在 workspace，额外副本和 SHA256 清单放根目录 temp，不提交 Git。

## 回退与重建边界

- 回退目标：`c3e79ef`（第三个 Agent 开写前，包含前两个 Agent 和仿真调研）。
- 先提交备份并设置备份分支，再从该目标建立重建分支；不删除原分支或历史，不推送 GitHub。
- 参考链路：程序准备现有工程/接口 → LLM 提取需求 → LLM 一次规划场景 → LLM 逐场景生成具体时间线 → 程序校验并输出仿真步骤。
- 不建立原来复杂的审查/JSON Pointer 多轮机制。不启动仿真、不编译、不修改被测工程。
- 模型输出使用短 JSON 契约与示例；器件接口取本地有来源资料，映射到现有 Wokwi 工具能力。
- 每个模型步骤明确提供的上下文；错误带具体诊断有限重试；保存真实请求、响应与提供方用量。
- 完成后主动运行离线机制测试与两个保留案例的真实 API 规划测试；沿用每例 300,000 token 上限，不增加预算，按调用报告 token/耗时。成功仅表示计划生成并通过静态校验，不是仿真或功能验收。

本文件记录重建前状态；重建实现和实测结果另行记录，不预先宣称成功。
