---
{
  "name": "hardware_selection",
  "description": "选择器件、分配接口或改变连线时使用；核对本地硬件资料、仿真范围及资源约束。",
  "tool_groups": [
    "hardware",
    "project"
  ],
  "references": []
}
---

# 硬件选型与设计

适用：生成前。参数只从本地硬件工具读取，不在运行中联网猜规格。
1. search_hardware发现条目，get_hardware_info读取所选器件，板卡include_shared=true。
2. 区分已购实物、simulation_variant、参考条目。仿真能力不是实物兼容性；blocked不能绕过。
3. 查引脚、头文件、库版本、驱动API、采样间隔和共享构建基线。get_driver_api可读取驱动配置及已登记原始API文档；本轮已有完整driver_profile时不重复查询。资料不足明确说明，不能虚构。
4. 保存完整设计：板卡实例mcu、外设实例、供电/地/信号连接、固定依赖、pin_defines。实现方式默认catalog；使用框架API时在implementations按实例声明framework和已登记api_refs，并说明时序/协议依据。资料来源确认不等于功能可行性确认。
5. vscode模式当前仅支持ESP32-S3 UART0基线。服务会加入mcu:TX→$serialMonitor:RX、mcu:RX→$serialMonitor:TX，以返回的设计为准。
6. 模板仅提供构建配置，不能替代硬件资料；引脚和业务逻辑必须依据当前需求与保存设计。

灵感：circuit-synth可复用子电路和职责分离；这里使用Wokwi输出和独立校验。
