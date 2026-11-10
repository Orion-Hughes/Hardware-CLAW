# DHT22成功工程与Agent交付物对照

日期：2026-10-27。只读检查两个原始工程，复制至temp进行CLI测试；未人工修改或修复Agent交付物。测试前后文件摘要确认两个原始目录均未变化。

## 实测结论

Wokwi CLI 0.29.0已使用本机`.secrets/wokwi-cli-token.txt`成功连接。凭据只在子进程环境WOKWI_CLI_TOKEN中传递，不写入命令行、日志、生成工程或本文；.secrets已被根.gitignore忽略。

| 实验 | 结果 | CLI退出码 | 墙钟时间 |
|---|---|---|---|
| Agent原始交付物v5，固件与电路不改动 | 启动标记出现，但DHT22返回TIMEOUT | 1 | 40.03秒 |
| 用户成功工程，固件与电路不改动 | 24°C/40%→30°C/65%→24°C/40%，并再次读取恢复值，全部匹配 | 0 | 23.70秒 |
| 保留成功工程的业务源码、电路、10kΩ上拉，只恢复上游原版DHTesp.cpp并重新编译 | 编译通过，但DHT读取失败 | 1 | 16.00秒（不含编译） |

这证明在本次组合中，增加上拉并不能单独解决问题；驱动实现差异是关键因素。没有进行“修订驱动但去掉上拉”的实验，不能宣称单独驱动补丁足够，也不推断所有ESP32或真实硬件都存在此问题。

## 主要差异

| 项目 | Agent交付物 | 用户成功工程 |
|---|---|---|
| MCU/构建基线 | ESP32-S3，espressif32@6.12.0，Arduino | 相同基线 |
| 数据GPIO/采样间隔 | GPIO4，至少2000ms | GPIO4，2000ms |
| 驱动来源 | PlatformIO安装DHT sensor library for ESPx@1.19原版 | lib/DHTesp本地修订源码 |
| 总线释放 | OUTPUT拉低后切INPUT，再digitalWrite(HIGH) | OUTPUT_OPEN_DRAIN拉低，保持开漏模式写HIGH释放总线 |
| 外部上拉 | 无 | 数据线到3V3的10kΩ电阻 |
| 电路表现 | 物理连线颜色为空；板卡属性默认 | 可见连线；flashSize=8；显式传感器初值 |
| 行为验证 | 交付时只有基础检查与编译 | 场景改变传感器值并逐步匹配串口 |
| 固件发布 | 宿主编译工具复制固件 | PlatformIO post脚本复制固件 |

空颜色、flashSize属性、发布脚本与本次失败的因果关系不能仅凭差异推断；保持成功电路不变而换回原版库仍失败，已将重点定位到驱动兼容性。此前单独更换连线颜色也未解决错误。

## 驱动差异与证据边界

上游代码：

```cpp
digitalWrite(pin, LOW);
pinMode(pin, OUTPUT);
// DHT22低脉冲
delay(2);
pinMode(pin, INPUT);
digitalWrite(pin, HIGH);
```

本地修订：

```cpp
digitalWrite(pin, LOW);
pinMode(pin, OUTPUT_OPEN_DRAIN);
delay(2);
digitalWrite(pin, HIGH); // 开漏释放，外部上拉使总线回到高电平
```

DHT通信不仅要求GPIO号和接口名称正确，也要求MCU释放总线后正确接收传感器握手及数据脉冲。成功工程PATCH.md及其既有诊断日志记录原版在edge=79、age_us=91时超时，表明读边沿序列与响应未对齐。本轮重新验证了成功场景和原版驱动的失败，没有重新采集该边沿诊断，也不能由此确定Wokwi内部实现的具体缺陷。

知识库保存的原版DHTesp.cpp与Agent实际编译安装的源码SHA256相同：98c86a410b8fad1e68d40b0828f9e5fd832f78a11ca622e085899a0542e88913。不是仅凭相同库名推断。

## 对Agent流程的改进建议

1. **兼容性资料按组合维护**：记录MCU、Arduino core、仿真后端、驱动版本/修订、必需外围电路、测试场景和证据。官方推荐或可编译，不等于该组合已运行通过。
2. **受控驱动资源**：将审查过的修订作为独立driver variant管理，固定上游版本、补丁ID、文件哈希和适用范围；由宿主工具复制到生成工程lib目录。保留原许可证与补丁说明，不将其伪称未改动的1.19。当前库只按name/version选依赖，尚不能可靠选择这种变体。
3. **电路需求随驱动绑定**：选择此开漏实现时，把上拉作为明确要求写入设计、diagram和校验规则。不能只在Skill中写一句“注意上拉”。当前库存不含电阻时，应补登记的基础元件资料，不由模型猜接头或偷偷修改上游库。
4. **增加simulate_project工具**：接收绑定工程的当前版本及受控场景ID，宿主读取token，核对固件/电路哈希后运行CLI。返回pass/fail/timeout/tool_error、退出码、预期与实际、日志引用、模拟及墙钟时间。凭据不得进入模型上下文。
5. **测试预期独立于生成**：使用可参数化场景，刺激24/40→30/65→24/40；输出协议可统一为稳定字段。不要只检查启动、进程退出0或任意一行Temperature。场景不能由被测Agent随失败修改成宽松规则。
6. **有限反馈循环**：失败证据返回Agent，Agent自行选取支持的驱动/连线或报告unsupported，修改后重新检查、编译、仿真。绑定新修订、限制次数、禁止无进展重复，保留每轮Token/时间。
7. **状态分层**：ready_for_vscode仅说明编译及可加载交付条件满足；独立记录simulation verdict与behavior verdict，不把可启动当作功能通过。

当前尚未将CLI仿真注册成Agent tool，也未改Agent知识库或自动导入本地驱动。上述是基于实测的下一步改进方案。继续使用现有受控发布工具即可，不必向Agent开放任意extra_scripts。

## 位置与证据

- 成功工程：`workspace/esp32-dht22-serial/`
- Agent原始交付：`workspace/dht-vscode-ready-0a6dcf3dfa59/exports/v000005/simulation/`
- 驱动解释：成功工程`lib/DHTesp/PATCH.md`
- 本轮结果和哈希：`temp/dht-comparison-20261027/results.json`
- 成功日志：`temp/dht-comparison-20261027/user-original.log`
- 原始失败：`temp/dht-comparison-20261027/agent-original.log`
- 对照失败：`temp/dht-comparison-20261027/original-driver-control.log`
- 对照编译：`temp/dht-comparison-20261027/control-build.log`
- 本轮LLM API调用：0；实际Wokwi CLI仿真调用：3。Wokwi服务的配额/计费以账户为准。

## 2026-11-09补充

本文写作时“修订驱动但去掉上拉”尚未运行。随后已按用户要求完成更简单的控制实验：仅保留 ESP32-S3 `3V3`、`GND`、`GPIO4→SDA` 三线，不加入电阻；使用 Hardware-CLAW 本地 DHTesp 1.19 开漏释放版本，通过受控 PlatformIO 编译、Wokwi CLI lint，并完成 `24°C/40% → 30°C/65% → 24°C/40%` 场景。日志见 `temp/dht22-local-driver-no-pullup-20261109/verification/no-pullup-serial.log`。

该结果只证明当前 ESP32-S3 / Arduino / Wokwi / 本地驱动组合不需要外接上拉；不能推广到采购实物红板、其他板卡或所有仿真基线。当前知识卡的 API 只暴露这个本地驱动包，不再提供上游 DHTesp 作为可选驱动。
