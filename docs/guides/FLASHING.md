# 固件烧录：准备、确认与执行

当前提供独立网页和可选 CLI，复用现有 PlatformIO 环境中的 esptool，不调用 LLM 或 Wokwi。**接口已经离线与真实编译测试；尚未实际连接/复位/烧录开发板，不能宣称实物验证通过。**

## 支持范围

当前网页烧录按采购记录的 **ESP32-S3-WROOM-2-N32R16V** 单独构建：PlatformIO `espressif32@6.12.0`、基于 `esp32-s3-devkitc-1`、Arduino-ESP32 2.0.17、32MB OPI Flash、启用 OPI PSRAM（模组标称16MB，实际可用量尚未实测）、80MHz。上传程序为 `tool-esptoolpy@2.40900.250804` 中的 esptool 4.9.0。

配置在 `LangChain/hardware_claw/deployment/target.py`，依据乐鑫模组表、Arduino-ESP32 2.0.17 `boards.txt`、其 OPI SDK/bootloader 和 PlatformIO 构建器。采用官方 `large_fat_32MB.csv`（双4.5MiB应用分区及FAT），不是自写分区表；OPI引导镜像的头部模式为 `dout`，不表示运行时 Flash 改用传统 DOUT。

**实物不在手边，型号目前只来自采购记录，尚未确认丝印、实测启动或PSRAM。** 第一次真正烧录前务必核对模组，不能把编译通过当成实物适配通过。其他板卡、分区、框架和存储模式需建立并验证对应配置；不写 eFuse、不调整供电电压、不通过 `--force` 忽略不匹配。

Wokwi生成与导出仍使用原来的8MB/无PSRAM仿真基线。网页准备时只在根目录 `temp/builds/` 的编译快照中叠加实物参数，**不修改 Agent 生成源码、原 `files/platformio.ini`、旧导出或仿真构建记录**。日志可能仍显示基础板型的 N8/8MB 名称；实际构建配置和二进制头部须以实物构建记录为准，不能依据该显示名称验收。

N32R16V 的 GPIO35/36/37 被内部存储器占用，准备阶段拒绝这样的接线，不静默换脚。串口输出保留 UART0，优先连接 USB 转串口口；尚未启用原生 USB CDC，不保证两个 USB 接口的日志表现相同。

实物前还需确认供电、模块型号/Flash、接口连接、屏幕规格及数据覆盖风险。仿真屏 240×240 与实物 240×320 不能仅靠上传就自动适配。

## 1. 网页操作（推荐，无需命令行）

刷新聊天网页，点击顶部 **固件烧录**。独立页面与聊天区分开，入口路径为 `/hardware-claw-flash`。

1. **选择工程文件夹**：搜索并选择 `workspace/` 内的受管工程，页面显示完整路径、版本、需求和现有检查/编译状态。当前不导入任意外部文件夹或裸 bin，也不把本机密钥目录当作工程浏览。
2. **选择串口**：点击刷新，选择开发板对应 COM 口。枚举不打开串口、不探测芯片、不复位设备。未枚举到串口时，仍可以编译和查看预览，但不能烧录。
3. **选择目标配置**：选择 N32R16V，核对页面显示的 Flash、PSRAM 和板型。当前只有该实物目标配置，仍需核对实际模组，不自动识别板型。
4. **准备固件**：旧工程建议保留“准备前重新检查并编译”。点击准备按钮，程序进行静态检查、编译、完整镜像校验和预览；不修改生成源码，不替换旧导出，不写入硬件。
5. **人工核对**：确认实物参数、供电/接线及覆盖风险后勾选两项声明，再准备预览。确认绑定当前工程版本、构建、镜像和串口；任何选择变化都会使页面当前预览失效。
6. **真正烧录**：预览满足条件后，点击“确认并烧录到开发板”，在二次确认窗口核对目标并输入“确认烧录”，再点击“开始真实烧录”。后端代管一次性确认码，不需要用户复制命令或长令牌。

页面右侧显示检查/编译/烧录进度及日志，可取消运行中的任务；刷新页面可恢复当前会话的任务状态。网络连接中断不代表后台已停止；服务重启后需要刷新重建会话，重新准备，不能依赖旧页面继续烧录。

这些操作由主程序执行，不发送给 LLM。Agent1/2/3 没有烧录权限，普通聊天也不会自动烧录。`/ports`、`/flash-plan` 仅保留为只读快捷命令。

网页只监听本机服务：会话 Cookie、来源与 CSRF 校验防止外站直接发起写入请求；该设计不是公网多用户服务或 OS 级安全沙箱。服务端同时只允许一个网页编译/烧录任务，失败或取消不自动重试。退出页面不自动取消已经确认的任务；强制结束服务也不能视为硬件写入已安全回滚。

旧工程如果只有仿真固件，或者本地驱动/实物配置改变使编译指纹过期，会明确要求重新编译，不偷偷使用旧 bin、其他工程的镜像。32MB实物镜像不会替代VS Code交付中的Wokwi镜像。

## 2. 可选命令行准备

以下命令在 `LangChain/` 执行，均不会烧录：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.deployment --help
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.deployment ports
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.deployment prepare --project 工程ID
```

需要更新旧编译记录、补齐镜像时，显式加 `--rebuild`：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.deployment prepare --project 工程ID --rebuild
```

这会检查、编译和保存预览，不修改生成源码，但会新增构建及计划记录并更新 `build-physical.json`。原 `build.json` 与旧导出目录不会被替换。

## 3. 实际执行前的确认

**本轮没有执行本节操作。以下仅是接口说明，不能在未核对实物时照抄串口。**

人工核对后，用真实串口和匹配的目标构建板重新准备：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.deployment prepare --project 工程ID --port COM实际编号 --board esp32-s3-devkitc-1 --hardware-reviewed
```

只有所有前置条件满足才会返回 `ready=true`、计划 ID 和一次性确认码。确认绑定工程修订、构建、镜像、目标配置、串口记录及烧录工具，15 分钟过期。USB 标识不足时不能证明设备身份，尤其需要人工核对。

用户检查预览后，才可以显式调用：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m hardware_claw.deployment execute --project 工程ID --plan 计划ID --confirm 一次性确认码
```

执行会写入启动、分区、OTA 初始化及应用镜像并复位设备；可能使原固件或数据不可用。不执行全片擦除、不使用 `--force`，不支持 OTA、任意 Shell 或自动选择串口。

超时为 180 秒，取消会回收子进程。计划在首次硬件操作前记为已使用；失败、取消和进程启动失败也不会原样自动重试，需要检查日志并重新准备。`uploaded` 只代表烧录工具退出成功，行为状态仍是 `not_run`。

## 镜像与记录

编译时保存完整镜像，不能拿仿真应用 bin 单独冒充完整烧录包：

| 镜像 | 当前平台偏移 |
|---|---|
| `bootloader.bin` | `0x0000` |
| `partitions.bin` | `0x8000` |
| `boot_app0.bin` | `0xe000` |
| `firmware.bin` | `0x10000` |

偏移和 Flash 设置依据固定版本 PlatformIO `builder/main.py`、Arduino-ESP32 `tools/platformio-build.py` 与板卡定义；不是所有 ESP32 的通用地址。程序核对镜像大小、重叠、边界和 SHA-256。

```text
workspace/<工程ID>/.hwclaw/
  builds/<编译ID>/        完整镜像与原有固件
  build.json             原仿真编译记录，不作为N32R16V实物烧录依据
  build-physical.json    实物构建报告，绑定源码/驱动指纹及有效构建配置
  uploads/<计划ID>/
    plan.json            修订/构建/设备/工具身份及确认码摘要
    images/              本次预览绑定的镜像快照
    execution.json       实际执行状态；没有执行就没有此文件
    upload.log           真实执行日志；预览不会生成
  uploads/web_jobs/       网页任务状态、结果与错误，不含一次性确认码
```

临时执行工作目录为根 `temp/uploads/`。计划和设备标识只留本地，不提交 Git。

## 开发入口与后续

- `hardware_claw/deployment/images.py`：平台范围、包解析、完整镜像保存与校验。
- `hardware_claw/deployment/service.py`：串口枚举、预览、确认、执行及留痕。
- `hardware_claw/deployment/__main__.py`：用户 CLI；`deployment/web.py`：网页只读预览。
- `hardware_claw/deployment/http.py`、`deployment/ui/`：独立页面、会话与来源校验、任务/日志、人工确认和取消。
- `adapters/compiler.py`：编译通过后保存辅助镜像；镜像缺失不把仿真编译误标为失败，而单独标记无法烧录。
- `tests/test_deployment.py`：接口与拒绝路径测试，执行进程用替身，不触碰硬件。

下一步是真机核对及授权烧录，再考虑串口监控、受控设备识别和 Agent3 的实物证据。当前没有自动串口监控，也没有用串口名推断具体板型。
