# VS Code仿真交付、Skills与模板

网页与 CLI 当前默认走主协调流程，生成阶段按 VS Code / Wokwi 模式交付。网页用 `/new 需求`，CLI 用 `main.py --question "需求"`；完整用法见 [环境配置](SETUP.md)。不再把旧单 Agent 的模板参数和命令当作当前入口。

## 职责与顺序

1. LangChain 执行主协调和固定阶段；预算、超时和有限修正见 [运行限制](DEVELOPMENT_LIMITS.md)，不沿用旧入口上限。
2. 阶段技能由宿主装入；generation 的 `load_template` 只读取登记的平台配置，不提供专用业务答案。
3. update_project_design保存设计并为当前ESP32-S3 UART0基线加入串口交叉连线。
4. scaffold_project将固定构建配置、Wokwi配置和按设计组装的diagram写入新修订；业务C++与README由Agent生成。
5. Agent2 提交候选后，宿主调用静态检查服务，核对必需文件、端点、连线、依赖及配置等基础错误。这不是功能验收。
6. 宿主编译快照，捕获日志/退出码，保存源码与固件哈希。可定位诊断按有限流程返回 Agent 修正，再检查编译；同修订失败不无改动重编译。
7. 宿主核对当前版本的检查与匹配固件后导出文件夹和 ZIP，`simulation/behavior` 保持 `not_run`。检查、编译、导出接口不直接注册给当前 Agent2；Wokwi 执行也不注册。预算停止后能否接管候选以宿主门槛为准，不靠模型宣布成功。

## 文件位置

```text
LangChain/skills/                         宿主按阶段加载的指导
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

本项目模板是自行编写，未直接复制第三方模板。早期参考下载及 API 测试证据保留于本机 `temp/vscode-delivery-20261027/`；不把该次结果外推为当前所有工程验收。
