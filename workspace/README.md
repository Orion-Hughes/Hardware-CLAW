# Agent 生成工程

此目录保存本机真实运行生成的工程、失败证据和交付结果，不提交 Git。每个工程独立子目录，由 `ProjectService` 创建和维护。

## 新工程命名

```text
<tester>-<hardware>-<task>-<random6>
```

示例：

```text
user-dht22_esp32_s3-serial_output-9f8638
user-joystick_display-input_visualizer-a1b2c3
```

- `tester`：测试者标识，来自 `HARDWARE_CLAW_TESTER` 环境变量，或本地忽略文件 `LangChain/tester.txt`；未配置时使用 `local`。
- `hardware`：从标题/需求提取的可读硬件组合，多个硬件用 `_` 连接；无法识别时使用 `hardware`。
- `task`：主要测试任务，如 `serial_output`、`input_visualizer`、`environment_monitor`；无法识别时使用 `embedded_task`。
- `random6`：6 位随机十六进制后缀，避免重名。

目录名只服务人工检索，不参与选型、固件生成、验证判定或修复策略。完整需求、版本、选型、GPIO 表、编译和运行证据以 `.hwclaw/` 为准。

## 工程结构

```text
<project_id>/
  files/           当前受管源码、diagram.json 和构建配置
  .hwclaw/         state、不可变 revisions、builds、runs、verification_plans、gpio_maps
  exports/         版本化 ZIP 与 VS Code/Wokwi 交付目录
```

普通文件工具只作用于 `files/`；元数据和修订必须通过工程服务接口变更。外部手工改动 `files/` 会被字节校验拒绝。临时构建和调试数据放入 `../temp/<project_id>/`。

## 清理原则

保留有文档引用的工程、真实付费调用记录、失败证据、硬件问题基准和当前复查对象。重复中间态、无引用旧网页工程和已被新流程取代的测试工程先移动到 `temp/workspace-retired-<date>/` 退役；确认不再需要后再永久删除。旧命名工程仍可直接打开，其 `tester` 字段显示为 `null`。
