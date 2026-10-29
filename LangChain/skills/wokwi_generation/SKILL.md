---
{
  "name": "wokwi_generation",
  "description": "生成或修改完整Wokwi工程时使用；组织需求、设计、源码和交付。解释性问题不要求写工程。",
  "tool_groups": [
    "hardware",
    "project",
    "build",
    "simulation"
  ],
  "references": [
    "references/requirements.md",
    "references/modification.md",
    "references/source_delivery.md"
  ]
}
---

# 嵌入式工程生成与修改

负责把用户目标组织为一致的硬件设计、固件和可交付工程。先读取当前工程；讨论和解释只读，不强行生成。

## 选择本次工作
- 首次生成：明确输入、输出、触发条件、时间要求和交付范围。需求有歧义或涉及多个交互行为时读取 references/requirements.md。
- 已有工程修改：读取当前设计和相关文件；参考 references/modification.md，不从旧聊天答案重建。
- 没有绑定工程：说明可在前端 /new 或 CLI --new-project 创建；不能声称保存了文件。

## 工作流程
1. 选型或接口变化时加载 hardware_selection，查询本地资料。不从元件名称猜引脚、API或供电。
2. 编写固件时加载 firmware_and_observation。先明确行为、接口和时序，再写代码；设计决策放现有 design/assumptions 和 README，无须新增庞大的中间文档。
3. 用 update_project_design 保存完整设计。board实例固定为mcu；器件实例、连接、依赖和pin_defines相互一致。
4. template=vscode：加载 build_and_delivery。scaffold_project 生成默认配置和连线图；write_project_files 写 src下的源码与README.md。随后 check_project_files → 按build阶段结果编译 → 按simulation阶段结果仿真/评估 → 按delivery阶段结果导出。warnings/unverified如实保留；执行仿真前加载 simulation_feedback。
5. template=arduino/platformio：仅按需读取 references/source_delivery.md，不将其源码交付规则套到vscode。
6. 写操作使用最新版本且顺序执行；失败先理解反馈。根据已确认的通用原因修正，不生成专用补丁、测试答案或固定业务日志协议。
7. 最终说明实际生成/修改、交付目录、验证范围与缺口。工具完成和功能通过是不同结论。

只加载本次需要的技能和参考资料；同一轮已读且未变化的资料不重复读取。详细工具参数以实际工具Schema为准。
