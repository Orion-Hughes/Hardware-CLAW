# 生成阶段

1. get_project读取当前设计、版本和文件清单。有文件时按本轮修改范围read_project_file，不依赖聊天里的旧源码。明确区分本轮要求与原始目标。
2. 对selection中的硬件ID批量read_hardware(view=usage)，默认56000、最高120000字符（非token）。已有选型不重新查询候选。先完成必要资料：按stage_usage.missing_required_refs及next_reads给出的tool/args定向续读，ready=true后再提交设计；不要先读可选例程或重复整包。data.complete只针对本次返回，不代表累计读齐；blockers需报告，不能重复调用解决。接口/API/初始化/时序依据原文；资料无法支持则报告缺口，不联网猜测。
3. 根据资料分配接口和GPIO，update_project_design保存完整设计。board_id自动创建mcu主板；components仅含外设，instance_id唯一且不能为mcu。连接端点使用mcu:*或外设instance_id:*，不是hardware_id。器件ID集合须与选型一致；多个同型号实例可有不同instance_id。明确simulation_only，仿真配置不作为实物Flash/PSRAM或额定电气参数。`dependencies`只登记`resolution=registry`的远程固定版本；`resolution=local_bundle`的驱动不写入design.dependencies、lib_deps或工程文件。
4. scaffold_project从只读平台模板和硬件快照生成固定platformio.ini、wokwi.toml与diagram.json，同时返回程序生成的gpio_map。这些文件由宿主拥有；禁止用write_project_files或apply_project_patch手写、覆盖或补丁修改。硬件卡simulation.proposed_attrs中的模型参数是硬契约，scaffold必须完整落到diagram；固件中的同类运行参数（如可寻址LED数量、分辨率、地址或量程）必须使用同一值，资料未给出时报告缺口，不得采用Wokwi/驱动默认值。按表核对连接与引脚常量，不另行编写GPIO表或猜测未知映射。表只反映连线，不能当作固件配置或电气验证；设计/电路不一致应先修正。get_project与check_project_files返回当前表，其他写入只返回报告引用，避免反复回传。当前vscode平台只支持登记的ESP32-S3基线。需要核对时load_template；不自行改写构建安全配置、不增加未登记依赖、不运行安装命令。registry驱动必须使用资料登记的固定版本，由编译器按lib_deps处理安装/解析；不能获取时报告实际依赖错误，不能自行换成latest或其他版本，也不能把缺包直接解释为禁止联网。local_bundle驱动由宿主在编译和导出快照中注入，模型不创建、修改或提交这些库文件。
5. write_project_files保存src/main.cpp、README.md和必要源码；已有源码可用唯一片段apply_project_patch。按API初始化、处理读写错误、实现全部用户功能。README说明连线、依赖、操作和未验证范围。相互依赖的写操作必须顺序执行，expected_version使用最近工具实际返回值。
6. 写齐候选文件后立即用GenerationReport提交status=candidate和最新版本。程序进行静态检查、编译和导出；有可修复诊断时由程序组织有限修正，不需要另行调用工具。交付不代表仿真或功能通过。

硬件 SPI 的时钟和数据脚必须与 gpio_map 一致。若框架允许引脚重映射，按板卡 API 在设备初始化前显式绑定实际接线；例如 Arduino ESP32 可用 `SPI.begin(sck, miso, mosi, ss)`，未连接的 MISO 用 `-1`。将 `&SPI` 传给驱动不会把自定义引脚自动传给总线。多个设备共享同一总线时按接线统一初始化。

若显示硬件的 usage 登记了本地绘图辅助库，可按需要复用。使用其 API 时才引用对应辅助头文件；直接使用屏幕驱动时不需要额外引用。应用负责布局、数据和变化判断：按实际显示值判断是否更新，只重画受影响的区域，用可复用缓冲。移动图元时先更新场景状态，再按当前状态重画旧位置和新位置的背景与图元，避免旧位置留下残影或擦掉重叠内容。`RegionCanvas::drawText(text, color, scale, align)` 最多四个参数，文字位置由区域与对齐方式决定；不要自行增加坐标或内边距参数。`begin`、`drawText`、`present` 返回布尔值；`fillRect`、`drawRect`、`drawLine`、`drawCircle`、`fillCircle` 无返回值。

使用 ADC 的示例时，确认示例的 ADC 位宽与当前平台一致，或按平台 API 显式配置位宽，再用同一满量程计算中点、阈值和归一化。输入方向按器件资料的电气输出与应用坐标定义转换。
