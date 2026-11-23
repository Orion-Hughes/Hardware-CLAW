#pragma once

#include <Adafruit_GFX.h>
#include <stddef.h>

namespace hwclaw {

struct Rect {
  int16_t x, y, width, height;
};

enum class Horizontal { left, center, right };

// Coordinates used to draw are local to the region. The caller owns the
// scratch pixels, which must outlive this object.
class RegionCanvas : private Adafruit_GFX {
public:
  RegionCanvas(uint16_t *scratch, size_t pixels);
  RegionCanvas(const RegionCanvas &) = delete;
  RegionCanvas &operator=(const RegionCanvas &) = delete;

  bool begin(Rect region, uint16_t background);
  bool drawText(const char *text, uint16_t color, uint8_t scale = 1,
                Horizontal align = Horizontal::center);

  void drawPixel(int16_t x, int16_t y, uint16_t color) override;
  using Adafruit_GFX::drawCircle;
  using Adafruit_GFX::drawLine;
  using Adafruit_GFX::drawRect;
  using Adafruit_GFX::fillCircle;
  using Adafruit_GFX::fillRect;

  // The region must fit. Use SpiBitmap for contiguous transfers on SPITFT.
  template <typename Target> bool present(Target &target) {
    if (!active_ || int32_t(region_.x) + region_.width > target.width() ||
        int32_t(region_.y) + region_.height > target.height()) {
      return false;
    }
    target.drawRGBBitmap(region_.x, region_.y, scratch_, region_.width,
                         region_.height);
    active_ = false;
    return true;
  }

private:
  uint16_t *scratch_;
  size_t capacity_;
  Rect region_{};
  bool active_ = false;
};

} // namespace hwclaw
