# VS Code仿真交付、Skills与模板

2026-10-27。默认入口`/new 需求`和CLI `--new-project`使用`vscode`模式。旧`--template arduino/platformio`与`/new-arduino`、`/new-pio`仍提供源码模式。

## 职责与顺序

1. LangChain维持现有Agent循环；每轮最多60次模型、160次工具调用；工程总时限3600秒、单次编译900秒，查询600秒；统一配置见 DEVELOPMENT_LIMITS.md。
2. load_skill提供选型、固件/观察、编译/交付规则；load_template提供固定格式与示例，两者均只能读取注册的ID。
3. update_project_design保存设计并为当前ESP32-S3 UART0基线加入串口交叉连线。
4. scaffold_project将固定构建配置、Wokwi配置和按设计组装的diagram写入新修订；业务C++与README由Agent生成。
5. check_project_files检查基础错误；新增串口连线、波特率与启动标记、固定配置一致性检查。启动标记检查只是文本存在性，不证明运行时可达；真正观察仍需仿真。
6. compile_project对快照进行实际PlatformIO编译，捕获日志/退出码，保存源码摘要和真实固件哈希。失败诊断返回Agent，修复后重新检查编译；相同修订失败禁止无改动重试。
7. export_project必须具有当前版本通过的基础检查及匹配固件，交付文件夹与ZIP；`simulation/behavior`保持`not_run`。2026-11-10起生成阶段不调用Wokwi CLI/MCP；仿真执行工具归属verification且当前未启用。宿主独立核对，不能靠模型口头宣布成功。预算退出时宿主尝试打包已经编译且检查通过的当前文件，不修改源码或判定。

## 文件位置

```text
LangChain/skills/                         5个领域技能（含流程入口和仿真反馈）
LangChain/templates/                      固定平台配置，无业务固件示例
LangChain/hardware_claw/projects/scaffold.py
LangChain/hardware_claw/adapters/compiler.py
LangChain/hardware_claw/projects/vscode_delivery.py
workspace/<project>/files/                工作源码和配置；不要在此目录直接编译
workspace/<project>/.hwclaw/build.json     当前编译报告
workspace/<project>/.hwclaw/builds/<id>/   受控固件副本
workspace/<project>/exports/vNNNNNN/
  project.zip / manifest.json
  simulation/                            VS Code打开这个文件夹
    src/main.cpp
    platformio.ini
    diagram.json
    wokwi.toml
    firmware/firmware.bin / firmware.elf
    .vscode/extensions.json
    README.md / OPEN_IN_VSCODE.md / _hwclaw_manifest.json
temp/builds/<project>/<attempt>/          编译工作目录与完整build.log
temp/vscode-delivery-20261027/             本轮公开参考资料与API测试证据
```

## 边界

- `ready_for_vscode`表示固件已编译且交付完整，不等于仿真或行为验收通过。生成程序不会自动操作VS Code，也不会自动启动Wokwi仿真；用户可在导出的simulation文件夹中手动运行VS Code Wokwi插件。
- 用户须装Wokwi扩展并持有有效授权。交付物不包含许可、API凭据或机器绝对固件路径。
- 此模式限已登记ESP32-S3 Arduino UART0基线、固定依赖。新增板卡需维护模板/检查器，不能直接套用串口端点。
- 默认application bin使用Wokwi标准bootloader/分区和4MB模拟Flash；不支持自定义分区、OTA、文件系统、芯片wasm资源，不证明采购实物存储配置。
- 修改源码不会使已有bin自动变化。回到Agent生成新修订，或在副本中手动pio run后更新firmware目录。导出目录被改动时服务拒绝当成原始有效交付。
- 编译在本机进程中运行，非OS安全沙箱。路径、依赖、配置白名单和环境筛选只提供应用级约束；不宜直接部署成接收不可信公网输入的服务。
- 失败/取消保留temp证据；子进程超时/取消回收已用真实子进程测试。尚无持久化任务队列或跨进程编译并发调度。

## 参考及采用方式

- [Wokwi VS Code入门](https://docs.wokwi.com/vscode/getting-started)：插件加载预编译固件，不负责编译。
- [工程配置](https://docs.wokwi.com/vscode/project-config)：version=1、相对固件路径与ESP32镜像边界。
- [串口监视器](https://docs.wokwi.com/guides/serial-monitor)：TX/RX交叉连接和display=always。
- [circuit-synth](https://github.com/circuit-synth/circuit-synth)：参考可复用子电路、职责划分；不将KiCad方案视为已适配Wokwi。本次在线读取其README，并结合此前已固定提交的实现分析。
- [Circuit Lab](https://github.com/PythonicVarun/llm-circuit-builder)：参考此前本地固定提交研究中的需求到文件集合、编译和串口事件链路；本次raw main README请求失败，不作为新增在线证据。

本项目模板是自行编写，未直接复制第三方模板。下载地址与SHA256记录于temp/vscode-delivery-20261027/sources.json。
