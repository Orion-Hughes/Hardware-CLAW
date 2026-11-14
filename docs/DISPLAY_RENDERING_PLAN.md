# 显示绘图：ESP-Claw 调研与 Hardware-CLAW 方案

## ESP-Claw 的做法

源码基线：[`50072775`](https://github.com/espressif/esp-claw/tree/50072775cfa20d7ce25a9b27591d9d7c8b9dbab5)。

| 源码 | 机制 | 可以借鉴 |
|---|---|---|
| [display 模块](https://github.com/espressif/esp-claw/blob/50072775cfa20d7ce25a9b27591d9d7c8b9dbab5/components/lua_modules/lua_module_display/README.md) | 用 `screen:info()` 获取设备尺寸和格式；`begin → draw → present` 绘制图形、文字和图片。支持裁剪、坐标变换、文字测量。此接口只面向内置屏幕，无控件。 | 给上层统一的尺寸、坐标、颜色、文字测量和区域更新接口。 |
| [display_core.c](https://github.com/espressif/esp-claw/blob/50072775cfa20d7ce25a9b27591d9d7c8b9dbab5/components/lua_modules/lua_module_display/src/display_core.c) 和 [display_service](https://github.com/espressif/esp-claw/tree/50072775cfa20d7ce25a9b27591d9d7c8b9dbab5/components/common/display_service) | 一或两个 PSRAM 帧缓冲，记录改动区域，只提交需要更新的像素；记录耗时、区域数和传输量。底层服务管理屏幕会话与提交。 | 默认只刷新变化的区域，运行中不频繁分配内存；不照搬依赖板载屏幕、PSRAM 和多 Lua 应用的调度。 |
| [LVGL 模块](https://github.com/espressif/esp-claw/blob/50072775cfa20d7ce25a9b27591d9d7c8b9dbab5/components/lua_modules/lua_module_lvgl/README.md) | 另一套控件接口，提供布局、按钮、列表、图表和触摸事件。RAW 和 LVGL 使用独占会话。 | 简单项目用轻量绘制，确实需要控件或多页面时再接 LVGL。 |
| [字体工具](https://github.com/espressif/esp-claw/blob/50072775cfa20d7ce25a9b27591d9d7c8b9dbab5/tools/font_subset/README.md) 和 [Dino 示例](https://github.com/espressif/esp-claw/blob/50072775cfa20d7ce25a9b27591d9d7c8b9dbab5/application/edge_agent/fatfs_image/system/apps/dino/scripts/dino.lua) | 先测文字边界再居中；按屏宽高布置元素。工具预先裁剪字体字符，资源可重复用。 | 字体、图标和颜色由资源层统一供给。按需引入中文字符集，不让模型生成像素数组。 |
| [Lua Web 模拟器](https://github.com/espressif/esp-claw/blob/50072775cfa20d7ce25a9b27591d9d7c8b9dbab5/tools/lua_lvgl_web_sim/README.md) | WebAssembly 浏览器运行，构建时复用多项 display/LVGL 核心源码。支持基础绘图；该版不支持 image loading，硬件模拟不验证布线和时序。 | 用同一套布局和绘制指令做预览与 MCU 渲染；预览证据只覆盖布局与像素，不覆盖 SPI 或整机。 |

## 建议的第一版

保留当前 C++ 固件和受控 PlatformIO 交付。先支持 ST7789 240×240 仿真基线；采购的 240×320 用独立资料和验收，不复用仿真尺寸、偏移或旋转。

1. **屏幕配置**：从硬件卡与 GPIO 表绑定驱动、SPI 接线、像素分辨率、旋转与逻辑宽高。实际固件初始化后用驱动的 `width()/height()` 对照预期尺寸。资料未知的值保留缺口。
2. **通用绘图模块**：在现有 Adafruit_GFX 上提供文字测量、对齐和裁剪、基本图形、区域刷新，以及少量可组合的数值卡片、条形进度和二维坐标区域。Agent2 负责数据来源、单位、状态、布局和界面文案；程序提供 API 约定并复用实现。仅选择显示驱动/绘图功能时带入，不生成业务案例模板。
3. **刷新与内存**：静态背景画一次，数据变化时更新控件区域；用小块 RGB565 画布先完成绘制再一次提交。240×240 全画布约 112.5 KiB，双缓冲约 225 KiB；可先用 240×40 的局部缓冲（18.75 KiB，不含其他开销），不假定仿真环境有可用 PSRAM。
4. **本地验收**：先让平台无关的布局/绘制输出在本地生成 PNG 或绘图命令记录。检查越界、文字截断、坐标映射、刷新的区域和内存上限；编译真实 Arduino 后端。没有 Wokwi CI 也能推进。然后用同一生成工程做 VS Code Wokwi 手动截图；确认 SPI、颜色、方向、刷新和动态数据后再谈支持。需要验证闪烁时看连续帧或刷新时序，单张截图不够。
5. **后续**：用第二种分辨率或单色屏验证接口可移植，再决定是否扩展字形裁剪、图标、图表或 LVGL。可先用既有时钟和摇杆需求验收通用组件，生产模块不包含两类应用的固定布局或预期读数。

首个交付物建议为共用的 C++ 绘图模块、短 API 指南、布局预览与离线测试；下一步才接入 Agent2。当前仅为源码调研和方案，未新增绘图库或运行 ESP-Claw 显示程序。
