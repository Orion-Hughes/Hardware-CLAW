# SG90：ESP32-S3 仿真平台的 PWM 接口

适用范围：`esp32_s3_arduino_simulation`（PlatformIO `espressif32@6.12.0`，Arduino-ESP32 **2.0.17**）与 `wokwi-servo` 通用位置舵机模型。

- 只用 `<Arduino.h>` 提供的框架内置 LEDC 驱动舵机；本器件无额外 `lib_deps`。不包含 `ESP32Servo.h`、`ESP32PWM.h` 或 `Servo.h`，不添加第三方舵机依赖。若续改旧工程，先按照现行器件资料重存设计并运行 `scaffold_project`，让宿主移除已失效的旧依赖，勿手写构建配置。其他器件的依赖照常保留。
- Arduino-ESP32 2.0.17 的调用顺序：`ledcSetup(channel, frequencyHz, resolutionBits)`，检查返回的实际频率（0 表示未配置成功）；`ledcAttachPin(gpio, channel)`；`ledcWrite(channel, dutyCounts)`。`gpio` 取设计中实际连到舵机 PWM 的引脚。`ledcWrite` 的首参是 **通道**，第二参是 **计数**，不是角度。不要使用 3.x 的引脚式 API。
- 初始控制范围：50 Hz，约 20,000 µs 一个周期；用 1,000–2,000 µs 对应 0–180° 的**命令域**，中位约 1,500 µs。这是参考映射，不能保证仿真模型或实物恰好转到对应角度或机械端点。先按需求限制命令角，再换算脉宽。可用 14 位计数，以 `round(pulseUs * 2^bits / periodUs)` 换算并限制在 `0..2^bits-1`；若采用其他分辨率，按实际配置换算。硬件持续输出 PWM，应用只在需要时更新目标值。
- 独立的 PWM 输出使用独立通道；同一定时器上的通道不能要求不同频率或分辨率。串口显示的是命令角；验证 PWM 要看波形，验证位置要看仿真模型或实物，不能用命令日志替代反馈。上述时序不作为任何具体实物舵机的机械限位、供电或精度保证。

来源：[Arduino-ESP32 2.0.17 LEDC 头文件](https://github.com/espressif/arduino-esp32/blob/2.0.17/cores/esp32/esp32-hal-ledc.h)、[Wokwi 舵机模型](../upstream/wokwi-docs/docs/parts/wokwi-servo.md)、[Wokwi 的舵机波形指南](../upstream/vendor/wokwi-servo-timing.html)。
