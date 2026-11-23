#pragma once

#include <stdint.h>

namespace hwclaw {

// Adapter for an Adafruit_SPITFT-compatible driver. RegionCanvas validates
// the region and supplies tightly packed native-endian RGB565 pixels.
template <typename Panel> class SpiBitmap {
public:
  explicit SpiBitmap(Panel &panel) : panel_(panel) {}
  int16_t width() const { return panel_.width(); }
  int16_t height() const { return panel_.height(); }

  void drawRGBBitmap(int16_t x, int16_t y, uint16_t *pixels, int16_t w, int16_t h) {
    panel_.startWrite();
    panel_.setAddrWindow(x, y, w, h);
    panel_.writePixels(pixels, uint32_t(w) * h); // Blocking, driver handles byte order.
    panel_.endWrite();
  }

private:
  Panel &panel_;
};

} // namespace hwclaw
