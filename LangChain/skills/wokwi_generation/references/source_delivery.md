# 兼容源码交付模式

仅适用于当前绑定template=arduino或platformio；不适用于默认vscode模式。

- arduino：sketch.ino、diagram.json、libraries.txt、README.md。
- platformio：src/main.cpp、diagram.json、platformio.ini、wokwi.toml、README.md。使用所选板卡的共享构建配置、固定依赖；wokwi.toml中[wokwi]的version为整数1，固件路径与该配置一致。
- 使用实际工具保存文件、执行基础检查，再导出。scaffold_project与现有编译/仿真服务若返回不支持该模式，应如实保留源码交付，不套用vscode流程。
- 不添加extra_scripts、任意构建命令、外部源码目录或绝对依赖路径。
- 只按工具结果报告编译、仿真与功能状态；源码打包本身不代表已经构建固件。
