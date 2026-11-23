# 局部绘图 API（HwClawGraphics 0.1.0）

这是宿主注入的本地包，包含 `HwClawGraphics.h` 和 `HwClawSpiBitmap.h`。与登记的 Adafruit GFX 1.13.0 配合使用；本地包不写入 `lib_deps`。`SpiBitmap<Panel>` 面向兼容 Adafruit_SPITFT 的硬件 SPI 屏幕。屏幕的接线、初始化尺寸、旋转和 SPI 设置以对应硬件资料为准。

```cpp
// screen 是应用按照实际接线初始化的硬件 SPI 屏幕。
hwclaw::SpiBitmap<Adafruit_ST7789> bitmap(screen);
static uint16_t scratch[120 * 24];
hwclaw::RegionCanvas canvas(scratch, sizeof(scratch) / sizeof(scratch[0]));
// 放在更新函数中；label 是当前要显示的字符串。
if (canvas.begin({0, 0, 120, 24}, 0x0000) &&
    canvas.drawText(label, 0xffff, 2, hwclaw::Horizontal::center)) {
    canvas.present(bitmap);
}
```

- `begin({x,y,width,height}, background)` 用屏幕坐标选区并填充 RGB565 背景。之后 `drawText`、`drawLine`、`drawRect`、`fillRect`、`drawCircle`、`fillCircle` 用区域内坐标绘制，图形自动裁剪。`drawText` 支持单行可打印 ASCII，默认居中，也可指定 `Horizontal::left` 或 `Horizontal::right`；文字放不下时返回 `false`。
- `present(bitmap)` 检查区域是否落在当前屏幕内，随后一次提交矩形像素。它的成功返回表示已提交驱动，不能当成显示正确的证据。屏幕需使用硬件 SPI 构造函数，只换绘图 API 不会切换总线。
- 应用在首帧绘制静态背景；后续比较实际显示的内容（例如格式化后的文字、映射后的像素坐标），没变就跳过传输，有变化才重画相应区域。移动物体时应覆盖旧位置和新位置，并重画这些区域中需要保留的背景与图元。库不追踪前一帧或图层。
- 一个 RGB565 区域占 `宽 × 高 × 2` 字节。使用可复用缓冲，避免在循环中分配内存或反复清全屏。检查 `begin` / `drawText` / `present` 的返回值；屏幕坐标以旋转后的宽高为准。
