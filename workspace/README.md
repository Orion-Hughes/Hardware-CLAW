# Agent 工作工程

此目录用于后续生成工程，每个工程独立子目录。现在尚未开放文件工具权限。

工程源码、电路、构建配置与产物版本应关联；验收条件和可信测试证据需保护，不默认允许模型改写。临时构建缓存放 `../temp/<project-id>/`。

正式程序采用以下实例约定，由未来create_project服务创建，本轮未创建样例工程：

```text
<project_id>/
  files/           工程文件；Agent受控写入，编译/Wokwi工作根
  .hwclaw/         工程/需求/设计元数据、revisions、runs；工程服务维护
  exports/         交付服务输出，不含密钥、缓存和软件环境
```

普通文件工具只作用于files；元数据通过专门接口变更。目录名称并不提供权限隔离，实际控制待实现。正式验收条件位于evaluations/cases，工程仅记录其ID/版本；临时中间件统一放temp/<project_id>/<run_id>。详见 [程序设计](../docs/GENERATOR_ARCHITECTURE.md)。
