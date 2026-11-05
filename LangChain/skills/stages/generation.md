# 生成阶段

1. get_project读取当前设计、版本和文件清单。有文件时按本轮修改范围read_project_file，不依赖聊天里的旧源码。明确区分本轮要求与原始目标。
2. 对selection中的硬件ID批量read_hardware(view=usage)，默认56000、最高120000字符（非token）。已有选型不重新查询候选。先完成必要资料：按stage_usage.missing_required_refs及next_reads给出的tool/args定向续读，ready=true后再提交设计；不要先读可选例程或重复整包。data.complete只针对本次返回，不代表累计读齐；blockers需报告，不能重复调用解决。接口/API/初始化/时序依据原文；资料无法支持则报告缺口，不联网猜测。
3. 根据资料分配接口和GPIO，update_project_design保存完整设计。board_id自动创建mcu主板；components仅含外设，instance_id唯一且不能为mcu。连接端点使用mcu:*或外设instance_id:*，不是hardware_id。器件ID集合须与选型一致；多个同型号实例可有不同instance_id。明确simulation_only，仿真配置不作为实物Flash/PSRAM或额定电气参数。
4. scaffold_project从只读平台模板生成固定配置与diagram.json。当前vscode平台只支持登记的ESP32-S3基线。需要核对时load_template；不自行改写构建安全配置、不增加未登记依赖、不运行安装命令。
5. write_project_files保存src/main.cpp、README.md和必要源码；已有源码可用唯一片段apply_project_patch。按API初始化、处理读写错误、实现全部用户功能。README说明连线、依赖、操作和未验证范围。相互依赖的写操作必须顺序执行，expected_version使用最近工具实际返回值。
6. check_project_files通过后compile_project。编译失败读取诊断，做最小必要修改，再检查编译；不要对未变代码重复编译，遇到资料/平台/工具缺口如实停止。编译与修改都保留原始修订。
7. 当前版本检查与编译均pass后提交GenerationReport。此处没有仿真、功能验收、烧录或导出权限；不加载旧的simulation_feedback流程，不声称行为正确。主Agent负责交付或委派下一阶段。
