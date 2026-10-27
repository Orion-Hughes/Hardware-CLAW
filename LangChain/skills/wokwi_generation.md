# Wokwi 工程开发流程 v2

新增默认vscode模式：先加载hardware_selection、firmware_and_observation、build_and_delivery三个技能。
按get_project→查硬件→update_project_design→scaffold_project→写src/main.cpp和README.md→check_project_files→compile_project→simulate_project→evaluate_tests→export_project。加载simulation_feedback学习固定输出协议和反馈规则。
vscode固定配置由scaffold生成，导出包含真实固件的simulation文件夹；按build_and_delivery技能执行。
以下为兼容旧arduino/platformio源码模式的流程，不能将其中“编译未运行”或旧.pio固件路径套用到vscode模式。

这是开发方法，具体参数必须来自硬件查询工具。本阶段只生成仿真工程，不直接烧录实物。

1. 用 search_hardware 选型，get_hardware_info 读取所选器件；板卡读取 include_shared。blocked/unreviewed/metadata_only不可充当已支持配置。没有查过不能宣称库里不存在。
2. get_project 查看绑定的工程和当前 version。无工程时说明应先在界面使用 `/new 工程需求`，或CLI的 `--new-project 名称 --question 需求`。
3. update_project_design 保存目标、board_id、components（instance_id/hardware_id）、connections（完整Wokwi端点对）、dependencies（库名和版本）、assumptions。board固定实例名 mcu；所有端点使用资料原名。整个设计用 simulation_only=true 明确仿真范围。
4. 生成两类布局之一：arduino包含 sketch.ino、diagram.json、libraries.txt、README.md，便于复制到Wokwi网页；platformio包含 src/main.cpp、diagram.json、platformio.ini、wokwi.toml、README.md，便于本地编译和CLI。模板类型由入口绑定；不要擅自变更。
5. 文件用 write_project_files 批量保存。每次写入传 get_project 返回的 expected_version；依赖前一步结果的调用顺序执行，不并行猜版本。文件总量限制，禁止访问 .hwclaw、密钥、项目外文件。修订由服务管理。
6. Arduino源码必须用#include <Arduino.h>或正常Arduino工程结构，库按所选硬件驱动；首次采样、错误处理和显式引脚声明应遵循资料。diagram的连接与设计保持一致。不要从真实硬件型号推断未经确认的引脚。
7. PlatformIO采用所选板卡的共享构建基线；一个env名称。wokwi.toml必须有[wokwi]表、整数version = 1，firmware/elf分别为.pio/build/<env>/firmware.bin和firmware.elf；构建缓存由未来编译适配器重定向到temp。禁止extra_scripts、任意构建命令、外部源码目录或绝对路径。不要声称已经构建出固件。lib_deps采用设计中库名@版本，不猜测未登记的owner。
8. read_project_file 读取，apply_project_patch 用唯一的old_text→new_text定点修改。修改后再运行check_project_files；检查只涵盖文件/格式/端点/部分配置一致性，不证明功能或电气正确。
9. export_project 只交付当前版本且基础检查通过的文件。若检查失败，依据问题修改并重测；预算不足则保留工程并说明。编译、仿真、行为与真机结果保持not_run。
10. README记录需求、接线、依赖、使用步骤、假设和未验证项。不要将聊天里的方案描述当作已经保存的工程。
