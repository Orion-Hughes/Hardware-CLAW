# Hardware-CLAW 局部绘图库

源码和简明 API 位于 [HwClawGraphics 本地包](../../LangChain/knowledge/drivers/HwClawGraphics/README.md)。Agent2 从登记的 ST7789 240×240 仿真硬件卡获得 API，编译和交付由宿主注入同一份库。这里保留独立验收。依赖 Adafruit GFX 1.13.0，目标屏幕须支持 `width()`、`height()` 和 `drawRGBBitmap()`。屏幕初始化、旋转、输入处理和更新时机由应用负责。

```cpp
#include "HwClawGraphics.h"
#include "HwClawSpiBitmap.h"

// tft 是已初始化且使用硬件 SPI 的 ST7789 实例。
hwclaw::SpiBitmap<Adafruit_ST7789> bitmap(tft);
uint16_t pixels[200 * 32];  // 常驻 RGB565 缓冲；不要在 loop() 内反复分配
hwclaw::RegionCanvas region(pixels, 200 * 32);

// 每次更新前清理这个区域的缓冲，再一次提交到屏幕。
if (region.begin({20, 22, 200, 32}, 0x10a3)) {
    if (region.drawText(label, 0xffff, 3, hwclaw::Horizontal::center)) {
        region.present(bitmap);
    }
}
```

- `begin` 使用屏幕坐标指定矩形；`drawText` 和图形函数使用区域内坐标。单行文本使用内置 ASCII 字体，水平可左对齐、居中或右对齐，垂直居中。超出区域或字符集时返回 `false`，不隐式换行或截断。
- `begin` 会用背景色覆盖缓冲。更新圆点时，调用方必须把该区域内要保留的圆框等内容重新画上去；库不会记录上一帧的图层。
- `present` 检查区域是否在目标屏幕内。对于兼容 Adafruit_SPITFT 的屏幕，使用 `hwclaw::SpiBitmap<Adafruit_ST7789> bitmap(tft)`，再用 `region.present(bitmap)`。它为每个矩形设置一次地址窗口，连续提交 RGB565 像素，避免驱动的 `drawRGBBitmap()` 逐行调用。初始化应使用硬件 SPI：如两个验收工程中的 `SPI.begin(...)` 和带 `&SPI` 的屏幕构造函数。仅换绘图接口不会自动把软件 SPI 切换成硬件 SPI。
- 返回值表示已提交给驱动，不能确认屏幕效果。库每次使用 `宽 × 高 × 2` 字节，不使用整屏缓冲，也不依赖 PSRAM。画面只有部分变化时，调用方可以分别提交旧对象和新对象覆盖的区域，或在相近时合成一个矩形，并在每个区域重画当前画面。

## 验证方法

在仓库根目录执行。电脑端测试使用仓库里固定的 Adafruit GFX 绘制源码，仅替换 Arduino 基础接口，不替换画字或画圆的实现。需要 `g++`。

```powershell
pwsh -File firmware/graphics/tests/run-host.ps1
pwsh -File firmware/graphics/tests/build-wokwi.ps1 -Case clock
pwsh -File firmware/graphics/tests/build-wokwi.ps1 -Case joystick
```

- 电脑端检查对齐、越界拒绝、裁剪、缓冲容量和每个 SPI 地址窗口只提交一批像素；局部移动后的画面与重画整个区域逐像素比较。两帧 PPM 及编译产物输出到 `temp/display-rendering/`。
- 新版 Wokwi 工程分别生成到该目录的 `fast-clock/`、`fast-joystick/`，原慢版产物可保留对照。在 VS Code 打开相应文件夹并运行 `Wokwi: Start Simulator`：看时钟是否每秒更新；摇杆首帧需要画圆框，之后移动只传输圆点前后覆盖的块，最多 242 个像素。串口的 `refresh_us` 是固件从开始绘制到驱动返回的时间，不是电脑上观察到的刷新耗时。以上是测试工程，应用代码与接线不会提供给生产 Agent 当答案模板。
