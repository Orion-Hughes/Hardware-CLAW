#include <Adafruit_ST7789.h>
#include <SPI.h>
#include <math.h>
#include "HwClawSpiBitmap.h"
#include "scenes.h"

Adafruit_ST7789 screen(&SPI, 12, 13, 14);
hwclaw::SpiBitmap<Adafruit_ST7789> bitmap(screen);
uint16_t scratch[plotRegion.width * plotRegion.height];
hwclaw::RegionCanvas canvas(scratch, sizeof(scratch) / sizeof(scratch[0]));
uint32_t lastSample;
uint32_t lastLog;
int16_t lastX = INT16_MAX, lastY = INT16_MAX;

void setup() {
  Serial.begin(115200);
  SPI.begin(10, -1, 11, 12);
  screen.init(240, 240, SPI_MODE0);
  screen.setSPISpeed(10000000);
  screen.setRotation(2);
  screen.fillScreen(0x2127);
  analogReadResolution(12);
  pinMode(4, INPUT);
  pinMode(5, INPUT);
}

void loop() {
  const uint32_t now = millis();
  if (now - lastSample < 40) return;
  lastSample = now;
  // Wokwi model: left and up increase voltage, while screen x/y increase right/down.
  float x = 1.0f - 2.0f * analogRead(4) / 4095.0f;
  float y = 1.0f - 2.0f * analogRead(5) / 4095.0f;
  const float distance = sqrtf(x * x + y * y);
  if (distance > 1.0f) { x /= distance; y /= distance; }
  if (distance < 0.06f) x = y = 0;
  const int16_t px = lroundf(44 * x), py = lroundf(44 * y);
  if (px == lastX && py == lastY) return;
  const bool first = lastX == INT16_MAX;
  unsigned pixels = plotRegion.width * plotRegion.height;
  const uint32_t startUs = micros();
  const bool rendered = first ? showPoint(canvas, bitmap, px, py)
                              : movePoint(canvas, bitmap, lastX, lastY, px, py, pixels);
  if (rendered) {
    const uint32_t elapsedUs = micros() - startUs;
    lastX = px;
    lastY = py;
    if (first || now - lastLog >= 250) {
      lastLog = now;
      Serial.printf("point=%d,%d refresh_us=%lu pixels=%u\n", px, py,
                    static_cast<unsigned long>(elapsedUs), pixels);
    }
  }
}
