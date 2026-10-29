# 技能包与生成上下文：真实Agent验证

日期：2026-10-28。使用现有api_config.py配置，提供方返回model_name=deepseek-flash。测试调用与完整事件位于temp/generation-skills-20261028；未读取/显示密钥，未提交生成工程。

## API使用记录

| 回合 | 宿主状态 | 模型调用 | 工具请求 | 总耗时/秒 | 输入token | 输出token | 总token | 缓存输入token |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| query | completed | 6 | 10 | 18.44 | 49,517 | 2,860 | 52,377 | 36,864 |
| generation | validation_unavailable | 17 | 23 | 192.28 | 349,837 | 6,148 | 355,985 | 139,392 |

所有token来自提供方usage，不是估算。耗时包含工具与仿真。总计23次模型调用、33次工具请求、210.72秒、399,354输入、9,008输出、408,362总token。未做旧版本对照，不能声称本次改动降低token或提高总体成功率。

## 资料链路

Agent加载firmware_and_observation正文和references/firmware_design.md，搜索SG90与240×240仿真屏幕，读取对应驱动配置及源码/头文件原文。发生1次UNSAFE_REFERENCE：模型尝试读取未登记ESP32Servo.h；工具拒绝后，模型改读已登记ESP32Servo.cpp并完成分页。

这证明拒绝路径及后续恢复链路可用，也说明模型仍会构造参考路径。未注册头文件没有被临时加入白名单。模型回答较长；其中数值/源码解释仍需审查，不能当作官方文档替代。

## 完整生成链路

需求：ESP32-S3、PS2摇杆、8灯WS2812；水平轴控制亮度，按钮消抖并切换红绿蓝，避免长时间阻塞，低频串口输出，实际编译/仿真/导出。

工程：workspace/joystick-ring-skills-1793175690-3b85adef6962

- Agent加载wokwi_generation、build_and_delivery、firmware_and_observation、simulation_feedback。
- 没有加载hardware_selection正文，虽使用了硬件查询工具；不能声称模型完整遵循了所有技能加载建议。
- 已从get_hardware_info读取完整driver_profile，因此没有重复调用get_driver_api。
- 一次设计提交、一次脚手架、一次源码写入、一次基础检查和一次编译，编译pass。
- simulate_project到达观察窗口，返回observation_limit。
- Agent另外调用inspect_simulation，用控制输入与串口观察收集交互证据。不是自动功能验收。
- evaluate_tests返回unsupported，full_project_acceptance=not_evaluated；宿主status=validation_unavailable。
- 导出v3的simulation文件夹，delivery_status=ready_for_vscode，包含真实固件。可打开交付不等于功能通过。
- 原始生成结果和证据保留；没有手工修补源码或电路。

导出目录：`D:/Hardware_CLAW/workspace/joystick-ring-skills-1793175690-3b85adef6962/exports/v000003/simulation`。

## 回读发现，保留问题

1. Agent自行添加了以亮度控制点亮灯珠数量的效果，超出原请求仅控制亮度的描述。该行为不能当作技能改进成功的证据。
2. refreshRing按点亮数量与颜色决定是否刷新；亮度改变但数量未跨档时不会重新发送RGB值，存在量化/更新遗漏。这是源码回读发现，不是本次自动验收检测结果。
3. 未做灯环发光、消抖时序或长期运行的完整验证。串口自报值不代表外设实际输出。
4. 本次生成输入缓存命中约39.8%；动态上下文和工具历史的成本还需后续对比优化，不声称获得缓存收益。

这些问题作为后续通用需求遵循和设计检查研究的样本，不能据此新增摇杆灯环专用Skill、提示词例外或验收规则。

## 软件机制回归

初次完整回归121项通过；新文件tests/test_generation_context.py覆盖技能包发现/参考边界/分页、现有本地API来源读取、未知与blocked/metadata状态、同步异步完整工具循环、当前工程上下文刷新、旧构建失效。测试fixture只验证软件机制，不作为生产答案模板。
