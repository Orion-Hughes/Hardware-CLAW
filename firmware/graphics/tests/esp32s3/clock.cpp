#include <Adafruit_ST7789.h>
#include <RTClib.h>
#include <SPI.h>
#include <Wire.h>
#include "HwClawSpiBitmap.h"
#include "scenes.h"

Adafruit_ST7789 screen(&SPI, 12, 13, 14);
hwclaw::SpiBitmap<Adafruit_ST7789> bitmap(screen);
RTC_DS1307 rtc;
uint16_t scratch[textRegion.width * textRegion.height];
hwclaw::RegionCanvas canvas(scratch, sizeof(scratch) / sizeof(scratch[0]));
bool ready;
uint32_t lastPoll;
uint32_t lastDisplayed = UINT32_MAX;

void setup() {
  Serial.begin(115200);
  SPI.begin(10, -1, 11, 12);
  screen.init(240, 240, SPI_MODE0);
  screen.setSPISpeed(10000000);
  screen.setRotation(2);
  screen.fillScreen(0x2127);
  Wire.begin(8, 9);
  ready = rtc.begin(&Wire) && rtc.isrunning();
  Serial.println(ready ? "RTC ready" : "RTC unavailable");
  if (!ready) showValue(canvas, bitmap, "RTC error");
}

void loop() {
  const uint32_t now = millis();
  if (!ready || now - lastPoll < 100) return;
  lastPoll = now;
  const DateTime value = rtc.now();
  if (!value.isValid() || value.unixtime() == lastDisplayed) return;
  char label[9];
  snprintf(label, sizeof(label), "%02u:%02u:%02u", static_cast<unsigned>(value.hour()),
           static_cast<unsigned>(value.minute()), static_cast<unsigned>(value.second()));
  const uint32_t startUs = micros();
  if (showValue(canvas, bitmap, label)) {
    const uint32_t elapsedUs = micros() - startUs;
    lastDisplayed = value.unixtime();
    Serial.printf("%s refresh_us=%lu pixels=%d\n", label,
                  static_cast<unsigned long>(elapsedUs), textRegion.width * textRegion.height);
  }
}
