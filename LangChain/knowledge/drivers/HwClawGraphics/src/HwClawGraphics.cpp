#include "HwClawGraphics.h"

namespace hwclaw {

RegionCanvas::RegionCanvas(uint16_t *scratch, size_t pixels)
    : Adafruit_GFX(0, 0), scratch_(scratch), capacity_(pixels) {
  setTextWrap(false);
}

bool RegionCanvas::begin(Rect region, uint16_t background) {
  active_ = false;
  if (!scratch_ || region.x < 0 || region.y < 0 || region.width <= 0 ||
      region.height <= 0 || size_t(region.height) > capacity_ / region.width) {
    return false;
  }
  region_ = region;
  _width = region.width;
  _height = region.height;
  const size_t pixels = size_t(_width) * _height;
  for (size_t i = 0; i < pixels; ++i) {
    scratch_[i] = background;
  }
  active_ = true;
  return true;
}

void RegionCanvas::drawPixel(int16_t x, int16_t y, uint16_t color) {
  if (active_ && x >= 0 && y >= 0 && x < _width && y < _height) {
    scratch_[size_t(y) * _width + x] = color;
  }
}

bool RegionCanvas::drawText(const char *text, uint16_t color, uint8_t scale,
                            Horizontal align) {
  if (!active_ || !text || !*text || !scale || 8 * scale > _height) {
    return false;
  }
  // First version uses only the classic 6x8 cell, printable ASCII, no wrap.
  // Bound the length before calling GFX's int16_t cursor arithmetic.
  const size_t maxChars = _width / (6 * scale);
  size_t len = 0;
  for (auto p = reinterpret_cast<const unsigned char *>(text); *p; ++p) {
    if (++len > maxChars || *p < 0x20 || *p > 0x7e) {
      return false;
    }
  }
  setTextSize(scale);
  int16_t x1, y1;
  uint16_t w, h;
  getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
  if (!w || !h || w > _width || h > _height) {
    return false;
  }
  int16_t x = 0;
  if (align == Horizontal::center) {
    x = (_width - w) / 2;
  } else if (align == Horizontal::right) {
    x = _width - w;
  }
  setTextColor(color);
  setCursor(x - x1, (_height - h) / 2 - y1);
  print(text);
  return true;
}

} // namespace hwclaw
