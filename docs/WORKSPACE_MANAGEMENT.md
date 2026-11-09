# Workspace 管理与命名规则

更新：2026-11-09。本文适用于本机生成工程目录；Git 只维护命名与清理机制，不提交 `workspace/` 内的生成工程和聊天证据。

## 目录 ID

新工程统一使用：

```text
<tester>-<hardware>-<task>-<random6>
```

示例：

```text
hmy-dht22_esp32_s3-serial_output-9f8638
hmy-joystick_display-input_visualizer-a1b2c3
```

规则：

1. `tester` 是测试者标识，只允许小写 ASCII 字母、数字、`-`、`_`，最长 16 字符。
2. `hardware` 是可读硬件组合。程序从标题和需求中识别常见硬件词；多个词用 `_` 连接，无法识别时为 `hardware`。
3. `task` 是主要测试任务词，如 `serial_output`、`input_visualizer`、`environment_monitor`；无法识别时为 `embedded_task`。
4. `random6` 是 6 位随机十六进制后缀。
5. 命名信息不作为生成、验收、修复或硬件选择的依据；完整事实在 `.hwclaw/`。

## 测试者配置

优先级：

1. `HARDWARE_CLAW_TESTER` 环境变量；
2. `LangChain/tester.txt` 第一行；
3. `local` fallback。

`LangChain/tester.txt` 已加入 `.gitignore`，适合每台机器单独配置。当前本机为 `hmy`。

## 旧工程兼容

旧目录名不迁移、不重命名。`ProjectService.get()` 对缺少 `tester` 的历史 state 返回 `tester: null`。是否为新工程由 state 结构和创建路径决定，不通过目录名猜测。

## 清理与退役

清理顺序：

1. 用文档和报告引用确定保留对象；
2. 保留真实付费调用记录、失败证据、硬件问题基准、可复查工程和 `.chat/`、`.tasks/`；
3. 将重复中间态、无引用旧网页工程和已被新流程取代的测试工程移动到 `temp/workspace-retired-<date>/`；
4. 用户确认后再永久删除退役目录。

本轮退役目录位于 `temp/workspace-retired-20261109/`，共 22 个：

```text
agent-trial-0905a5451985
agent-trial-1c17620077a6
agent-trial-814c5a5e9b7d
cost-f1329ab-st7789-1d435d2c900d
joystick-display-f1329ab-c28aac0a9184
knob-servo-1793249865-f21282789a09
task-090d6e1319df-fa0f268b8128
task-15c11c9b2945-7a4f03f18993
task-5ba274da006e-fd8246249936
task-8851d8a8353a-8bd0a98b1ac7
task-bb68d4c64d64-36194c0747bb
web-project-15c5c7d3a686
web-project-2c984825f501
web-project-34727f8f81d6
web-project-5edea35dea8f
web-project-73d28ad241b4
web-project-a23212ce4250
web-project-ad68134c9af8
web-project-c72dcddddeab
web-project-cdb28465fda0
web-project-ddd7409108bc
web-project-eb7fb3ab4e5d
```

这些目录未永久删除。若需要恢复，先确认目标名不存在，再把目录移动回 `workspace/`；不要覆盖现有工程。
