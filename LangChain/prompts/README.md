# 系统提示词与上下文

- system.md：稳定职责、资料使用与通用边界。
- generation.md：绑定工程后的生成/修改规则。
- query.md：没有绑定工程时的只读范围。

hardware_claw/context.py读取system.md及当前模式提示词，GenerationContextMiddleware在每次模型调用前组装SystemMessage：本回合技能目录、驱动API入口、实际注册工具名、最新工程摘要。工程状态每次重新读取，不追加旧快照；源码与长日志仍由工具按需读取。

CLI和Chainlit均通过build_agent使用同一装配。没有额外LLM调用，没有复制ESP-Claw的C框架，没有动态隐藏工具；路径权限、版本检查、预算和交付判定仍由现有服务执行。
