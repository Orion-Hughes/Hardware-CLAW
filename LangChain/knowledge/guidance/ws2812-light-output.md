# WS2812 / NeoPixel：亮度与闪烁

适用范围：使用 Adafruit NeoPixel 库的可寻址 RGB 灯环和灯带。用户指定的颜色、亮度和节奏优先；以下是固件生成指引，数值示例不是器件规格。

- **亮度只设一处。** `setBrightness(0–255)` 会缩放后续写入的 RGB 通道。在 Wokwi 中需要清楚可见、用户没有指定亮度时，可以用明亮的基础色加一个适中的全局亮度，例如 `Color(0, 255, 0)` 配合 `setBrightness(160)`；也可以保留全局默认值，直接用 RGB 通道值控制亮度。避免低 RGB 和低全局亮度叠加。仿真参数不能用于判断实物电流或供电能力；实物按灯珠数、数据手册和供电预算设限。
- **全局亮度用于初始化。** 如果要渐变或呼吸，从保存的原始颜色和当前效果进度计算每一帧的 RGB 值。不要反复调用 `setBrightness()` 实现动画：这个驱动会重缩放缓存里的颜色，多次调整可能损失精度。
- **常亮、闪烁和刷新频率分开。** 用户只要求灯光表示状态时，让灯在两次状态变化之间维持原样；写好整帧，再调用一次 `show()`，不要把清空和点亮各作为一帧发出。输入在阈值附近导致灯光抖动时，优先对输入加滞回或按需要滤波。输入采样率、动画更新率和人眼看到的闪烁频率是不同的量。
- **需要闪烁时写明周期。** 用户要求闪烁但没指定频率时，例如状态提示可以从 `1 Hz` 开始，即亮 `500 ms`、灭 `500 ms`，完整周期 `1000 ms`。用 `millis()` 定时切换，避免 `delay()` 阻塞输入采样或其他任务。每 `1000 ms` 翻转一次只能得到 `0.5 Hz`；用户没要求闪烁时不要自行加入。

来源：[NeoPixel 亮度和像素写入实现](../upstream/drivers/Adafruit_NeoPixel/Adafruit_NeoPixel.cpp)、[官方非阻塞动画示例](../upstream/drivers/Adafruit_NeoPixel/examples/strandtest_nodelay/strandtest_nodelay.ino)、[Wokwi 灯环模型文档](../upstream/wokwi-docs/docs/parts/wokwi-led-ring.md)。
