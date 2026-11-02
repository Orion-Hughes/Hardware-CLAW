# 硬件选型与设计

适用：生成前。参数只从本地硬件工具读取，不在运行中联网猜规格。
1. search_hardware返回足够选型的功能、输入输出、接口、资源约束和缺口。选定后用read_hardware一次读取板卡及所需外设，自动获得基础原文和平台配置；明确ID可直接读取。
2. 区分已购实物、simulation_variant、参考条目。仿真能力不是实物兼容性；blocked不能绕过。
3. 查引脚、头文件、库版本、驱动API、采样间隔和共享构建基线。资料不足明确说明，不能虚构。
4. 保存完整设计：板卡实例mcu、外设实例、供电/地/信号连接、固定依赖、pin_defines。
5. vscode模式当前仅支持ESP32-S3 UART0基线。服务会加入mcu:TX→$serialMonitor:RX、mcu:RX→$serialMonitor:TX，以返回的设计为准。
6. 模板仅提供构建配置，不能替代硬件资料；引脚和业务逻辑必须依据当前需求与保存设计。
7. documents中included为已返回原文，reference是可选扩展，omitted表示预算未装入。确有需要时用read_hardware的references仅补读所需文件；不要为收齐所有参考文档反复查询。complete只表示本次资料返回完整。
8. 同一选型目标先用一个关键词，结果不足再换词；不并行搜索同义词或子串。不同器件可以并行搜索。

灵感：circuit-synth可复用子电路和职责分离；这里使用Wokwi输出和独立校验。
