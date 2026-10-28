# 编译与VS Code交付

适用template=vscode；依赖版本的写操作不能并行。
1. get_project，查询所选硬件，load_skill读取hardware_selection与firmware_and_observation。
2. update_project_design→scaffold_project(expected_version)。后者从只读模板生成platformio.ini、wokwi.toml、diagram.json，不写业务源码。load_template("esp32s3_vscode")可查看固定模板。
3. write_project_files保存src/main.cpp与README.md。固定配置不要自行改写；设计变更后再次scaffold。
4. check_project_files通过→compile_project(expected_version)。这是真实编译，返回verdict、诊断与日志。
5. 编译失败定点修复→check→compile，在宿主统一预算内迭代；相同错误连续无进展时停止。不得削弱检查或替换假固件，不要求用满预算。
6. compile pass→simulate_project→evaluate_tests→export_project，导出simulation文件夹和ZIP。先加载simulation_feedback；修改文件后旧验证失效，重新检查编译仿真。
7. ready_for_vscode只确认可打开交付，给用户simulation_folder路径，另报行为verdict及范围。失败或unsupported也可以导出调试工程，不能称功能通过。

用户VS Code打开simulation文件夹→安装Wokwi插件并激活自己的授权→Wokwi: Start Simulator。交付包含固件，不需再次编译；修改源码需要重新编译。
限制：application bin由Wokwi补默认bootloader/partition，模拟4MB Flash。不支持自定义分区/OTA/文件系统，也不证明实物32MB/16MB布局兼容。自定义芯片资源尚不支持。

参考：https://docs.wokwi.com/vscode/getting-started 、 https://docs.wokwi.com/vscode/project-config
