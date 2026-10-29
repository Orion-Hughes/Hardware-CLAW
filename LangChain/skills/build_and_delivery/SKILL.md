---
{
  "name": "build_and_delivery",
  "description": "构建和交付template=vscode工程时使用；维护配置、编译反馈和可打开的仿真目录。",
  "tool_groups": [
    "project",
    "build",
    "simulation"
  ],
  "references": []
}
---

# 编译与VS Code交付

适用template=vscode；依赖版本的写操作不能并行。
1. 确认get_project、所选硬件及hardware_selection、firmware_and_observation资料；本轮已读且未变化的内容直接复用，不重复加载。
2. update_project_design→scaffold_project(expected_version)。后者从只读模板生成platformio.ini、wokwi.toml、diagram.json，不写业务源码；已有且未变更的设计直接复用。仅需要检查模板时使用load_template("esp32s3_vscode")，生成固定配置无需先读取模板正文。
3. write_project_files保存src下的源码与README.md；源码可以分文件组织。配置按解析后的含义检查，允许注释、键顺序和等价格式；平台、依赖来源及受控路径仍需一致。设计变更后同步配置，可再次scaffold。
4. 运行check_project_files，读取stage_verdicts和issues中的severity/blocks。build=pass即可compile_project；全局fail可能仅阻断仿真。warning与unverified需如实说明，不当作已验证，也不要求为了消除提示硬改代码。
5. 编译错误依据诊断修改后再check→compile。相同编译输入和工具链的确定性错误会跨版本阻止重试；依赖/环境错误允许300秒内最多两次，工具链登记状态变化可重试。不能通过改README、改版本号或来回还原源码规避。不得削弱检查或替换假固件，不要求用满预算。
6. get_project显示匹配的build pass后，simulation阶段无阻断项才simulate_project→evaluate_tests，delivery阶段无阻断项才export_project。执行仿真前加载simulation_feedback。只改README可复用编译；只改diagram可复用编译但需核对/重跑仿真；源码、构建配置或依赖变化需重建。复用由宿主按输入及环境身份决定，不由模型自行宣称。
7. ready_for_vscode只确认可打开交付，给用户simulation_folder路径，另报行为verdict及范围。失败或unsupported也可以导出调试工程，不能称功能通过。

驱动实现可以声明为catalog（默认）或framework。切换时在design.implementations按实例保存mode与已登记framework_api_refs，并同步dependencies、配置与源码。引用API资料不证明自行实现协议正确。没有登记的库别名、版本范围、下载URL仍不接受；遇到包安装失败应报告依赖来源问题，不能猜一个包名绕过。

若build包含identity_supported=false，它是尚未迁移的旧编译记录，即使旧verdict为pass也不能直接仿真或导出；先重新check和compile。不要修改或删除旧报告来绕过身份核验。

用户VS Code打开simulation文件夹→安装Wokwi插件并激活自己的授权→Wokwi: Start Simulator。交付包含固件，不需再次编译；修改源码需要重新编译。
限制：application bin由Wokwi补默认bootloader/partition，模拟4MB Flash。不支持自定义分区/OTA/文件系统，也不证明实物32MB/16MB布局兼容。自定义芯片资源尚不支持。

参考：https://docs.wokwi.com/vscode/getting-started 、 https://docs.wokwi.com/vscode/project-config
