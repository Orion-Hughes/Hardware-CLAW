# 文件位置与数据流

路径相对仓库根目录。启动见[环境配置](SETUP.md)，角色和接口见[架构](../architecture/OVERVIEW.md)。

```text
Hardware-CLAW/
  README.md / AGENTS.md              使用入口、开发约束
  THIRD_PARTY_NOTICES.md             上游来源与许可
  LangChain/
    main.py / app.py                 CLI / Chainlit网页入口
    Start-Agent.cmd / Stop-Agent.cmd 双击启动和停止
    Agent-Service.ps1                本机服务生命周期
    requirements*.txt                依赖范围及版本快照
    hardware_claw/
      runtime.py / api_config.py     请求入口、集中模型配置
      coordinator/                   主协调、任务状态、证据读取
      stages/                        三个子Agent及生成收尾
      tools/                         工具与技能注册/加载
      catalog/                       硬件检索、资料和本地驱动
      projects/                      修订、GPIO表、源码上下文、导出
      contracts/ / validation/       格式与确定性基础检查
      harness/                       上下文、预算和停止保护
      adapters/                      编译和仿真底层适配
      deployment/                    网页烧录与实物目标
    prompts/ / skills/ / templates/   提示、按需技能、只读格式
    knowledge/                       运行硬件库和上游资料
    integrations/wokwi_mcp/           已有实验性MCP适配
    tests/                           离线软件回归
  firmware/graphics/                 绘图库验收，非Agent答案模板
  references/                        连接卡引用的硬件配置与来源
  docs/                              使用指南、当前架构和状态
  workspace/                         本机运行数据，仅README纳入Git
  temp/                              本机缓存、日志和临时脚本
  tools/ / pio/                      本机工具和PlatformIO安装
  .secrets/                          本机凭据
```

## 一次任务

输入 → 主协调 → 选型与资料 → 接线/源码 → 提交候选 → 静态检查 → 编译/有限反馈修复 → VS Code导出；按任务委派Agent3生成测试计划。详情见[架构](../architecture/OVERVIEW.md)。

## 运行记录

```text
workspace/
  .tasks/coordinator.sqlite3        主任务和阶段记录
  .chat/                           聊天数据库
  <project_id>/
    files/                         当前受管源码和配置
    .hwclaw/
      project.json                 当前修订指针
      revisions/                   不可变历史
      gpio_maps/                   从工程派生的GPIO表
      build.json                   仿真构建报告
      build-physical.json          N32R16V实物构建报告
      builds/                      分开保存的编译工件
      verification_plans/          已委派的验证计划
      uploads/                     预览、网页任务、真实执行记录
    exports/v<version>/simulation/  VS Code仿真交付
```

计划不保证每个工程都有，只有完成验证规划才会有对应完整结果。源码、固件和报告须绑定同一修订；不把旧导出冒充新构建。

CLI与网页共享记录。外部直接修改`files/`可能触发版本冲突，手工实验时使用独立副本并明确标注。不要提交聊天、真实生成工程、工具安装、凭据或临时日志。
