# 只读工程模板

`esp32s3_vscode.json`仅提供当前支持的ESP32-S3平台构建、UART0、Wokwi相对固件路径及扩展推荐。不提供任何工程的业务源码示例；业务代码必须依据需求和所选硬件资料生成。

load_template只读白名单ID，返回内容与SHA256；scaffold_project根据保存设计实例化固定配置。只读指Agent工具权限，维护者仍可修改模板，不依靠Windows文件只读属性。参数、业务逻辑与具体连接来自当前设计。模板改变后已有工程需新修订、检查并重新编译。

模板为本项目编写。参考Wokwi官方project-config、serial-monitor，以及circuit-synth的可复用模块思想；来源记录见docs/VSCODE_DELIVERY.md。
