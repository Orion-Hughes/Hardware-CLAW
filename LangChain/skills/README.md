# Hardware-CLAW领域技能包

这些是本程序的工作方法，不是Codex插件。由hardware_claw/skill_catalog.py自动发现，load_skill列目录/读取正文/分页读取已登记参考资料。工具无权编辑、安装或执行技能包。

每个目录包含SKILL.md，使用JSON frontmatter：name必须匹配目录，description描述用途；tool_groups是说明性映射，不自动授权或隐藏工具；references列出包内references/*.md。参考资料按需读取，包含内容哈希、分页位置和截断标志。无效包在目录中报告并跳过。

- wokwi_generation：总流程；需求、修改和兼容源码交付参考。
- hardware_selection：硬件、接口与资料范围。
- firmware_and_observation：先读API再设计固件；状态/时序/资源参考。
- build_and_delivery：当前VS Code构建与交付。
- simulation_feedback：已有观测能力及验收边界。

硬件参数继续保存在knowledge，get_driver_api从现有driver_profile派生入口，不复制维护第二套数据库。技能正文不会自动全部注入；宿主Context Provider只提供目录，模型按需加载。每个用户回合重新建立Agent，不承诺跨回合保留已加载技能正文。

灵感来自本地ESP-Claw 345073d，见docs/ESP_CLAW_SKILLS_TOOLS_STUDY.md；本次没有引入Lua运行时或上游业务脚本。
