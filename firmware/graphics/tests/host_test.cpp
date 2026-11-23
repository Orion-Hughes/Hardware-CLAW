#include <algorithm>
#include <array>
#include <cassert>
#include <fstream>
#include <iostream>
#include "HwClawSpiBitmap.h"
#include "scenes.h"

struct Surface {
  static constexpr int edges = 240;
  static constexpr uint16_t untouched = 0x2127;
  std::array<uint16_t, edges * edges> pixels;
  int calls = 0;
  hwclaw::Rect last{};
  Surface() { pixels.fill(untouched); }
  int width() const { return edges; }
  int height() const { return edges; }
  uint16_t at(int x, int y) const { return pixels[y * edges + x]; }
  void drawRGBBitmap(int16_t x, int16_t y, uint16_t *data, int16_t w, int16_t h) {
    ++calls;
    last = {x, y, w, h};
    assert(x >= 0 && y >= 0 && x + w <= edges && y + h <= edges);
    for (int r = 0; r < h; ++r) {
      std::copy_n(data + r * w, w, pixels.data() + (y + r) * edges + x);
    }
  }
  void preview(const char *path) const {
    std::ofstream file(path, std::ios::binary);
    file << "P6\n240 240\n255\n";
    for (auto p : pixels) {
      const unsigned char rgb[] = {static_cast<unsigned char>(((p >> 11) & 31) * 255 / 31),
                                   static_cast<unsigned char>(((p >> 5) & 63) * 255 / 63),
                                   static_cast<unsigned char>((p & 31) * 255 / 31)};
      file.write(reinterpret_cast<const char *>(rgb), sizeof(rgb));
    }
    assert(file.good());
  }
};

constexpr uint16_t Surface::untouched;

struct SpiPanel : Surface {
  int step = 0;
  unsigned lastBatch = 0;
  unsigned totalPixels = 0;
  hwclaw::Rect window{};
  void startWrite() { assert(step == 0); step = 1; }
  void setAddrWindow(int16_t x, int16_t y, int16_t w, int16_t h) {
    assert(step == 1);
    window = {x, y, w, h};
    step = 2;
  }
  void writePixels(uint16_t *data, uint32_t count) {
    assert(step == 2 && count == uint32_t(window.width) * window.height);
    lastBatch = count;
    totalPixels += count;
    drawRGBBitmap(window.x, window.y, data, window.width, window.height);
    step = 3;
  }
  void endWrite() { assert(step == 3); step = 0; }
};

int main(int argc, char **argv) {
  std::array<uint16_t, 120 * 120 + 2> scratch;
  scratch.front() = scratch.back() = 0xface;
  hwclaw::RegionCanvas canvas(scratch.data() + 1, scratch.size() - 2);
  Surface frame;
  assert(!canvas.present(frame));
  assert(!canvas.begin({0, 0, 240, 240}, bg));
  assert(!canvas.begin({0, 0, 0, 1}, bg));
  assert(!canvas.begin({-1, 0, 16, 16}, bg));
  assert(canvas.begin({235, 235, 10, 10}, bg));
  assert(!canvas.present(frame) && frame.calls == 0);

  // Real Adafruit GFX glyphs: verify horizontal offsets and vertical centering.
  std::array<int, 3> left{};
  int index = 0;
  for (auto alignment : {hwclaw::Horizontal::left, hwclaw::Horizontal::center,
                         hwclaw::Horizontal::right}) {
    assert(canvas.begin({0, 0, 30, 16}, bg));
    assert(canvas.drawText("H", ink, 1, alignment));
    assert(!canvas.drawText("overflow", ink));
    assert(!canvas.drawText("a\nb", ink));
    assert(!canvas.drawText("\xe4\xb8\xad", ink));
    assert(!canvas.drawText("H", ink, 3));
    assert(canvas.present(frame));
    assert(!canvas.present(frame));
    left[index] = 30;
    for (int y = 0; y < 16; ++y) {
      for (int x = 0; x < 30; ++x) {
        if (frame.at(x, y) == ink) {
          assert(y >= 4 && y < 12);
          left[index] = std::min(left[index], x);
        }
      }
    }
    ++index;
  }
  assert(left[0] < 6 && left[1] - left[0] == 12 && left[2] - left[0] == 24);

  SpiPanel ui;
  hwclaw::SpiBitmap<SpiPanel> target(ui);
  assert(showValue(canvas, target, "100"));
  assert(ui.calls == 1 && ui.lastBatch == 6400 && ui.step == 0);
  assert(showPoint(canvas, target, -34, 10));
  if (argc == 3) ui.preview(argv[1]);
  const auto before = ui.pixels;
  assert(showValue(canvas, target, "99"));
  assert(ui.calls == 3 && ui.last.width == 200 && ui.last.height == 32);
  Surface clean;
  assert(showValue(canvas, clean, "99"));
  for (int y = 0; y < ui.height(); ++y) {
    for (int x = 0; x < ui.width(); ++x) {
      const bool inText = x >= textRegion.x && y >= textRegion.y &&
                          x < textRegion.x + textRegion.width && y < textRegion.y + textRegion.height;
      assert(ui.at(x, y) == (inText ? clean.at(x, y) : before[y * ui.width() + x]));
    }
  }
  assert(ui.at(86, 152) == accent);
  unsigned movedPixels;
  unsigned prevTotal = ui.totalPixels;
  assert(movePoint(canvas, target, -34, 10, 33, -17, movedPixels));
  assert(ui.calls == 5 && movedPixels == 242 && ui.totalPixels - prevTotal == movedPixels);
  assert(ui.at(86, 152) == bg && ui.at(153, 125) == accent && ui.at(170, 142) == ink);
  assert(ui.at(0, 239) == Surface::untouched);
  assert(showPoint(canvas, clean, 33, -17) && clean.pixels == ui.pixels);
  prevTotal = ui.totalPixels;
  assert(movePoint(canvas, target, 33, -17, 34, -17, movedPixels));
  assert(ui.calls == 6 && movedPixels == 132 && ui.totalPixels - prevTotal == movedPixels);
  assert(showPoint(canvas, clean, 34, -17) && clean.pixels == ui.pixels);
  assert(movePoint(canvas, target, 34, -17, 34, -17, movedPixels));
  assert(ui.calls == 6 && movedPixels == 0);
  // A diagonal move can overlap while still using two blocks; compare the
  // full framebuffer so overlap, old pixels and the guide outline are covered.
  assert(movePoint(canvas, target, 34, -17, 42, -9, movedPixels) && movedPixels == 242);
  assert(showPoint(canvas, clean, 42, -9) && clean.pixels == ui.pixels);
  assert(canvas.begin({0, 0, 16, 16}, bg));
  canvas.fillRect(-3, -3, 5, 5, ink);
  canvas.drawPixel(16, 4, accent);
  canvas.drawPixel(4, 16, accent);
  assert(canvas.present(frame));
  assert(frame.at(0, 0) == ink && frame.at(1, 1) == ink && frame.at(2, 2) == bg);
  assert(scratch.front() == 0xface && scratch.back() == 0xface);
  if (argc == 3) ui.preview(argv[2]);
  std::cout << "PASS: text alignment/fit, clipping, buffer limits, one SPI write per block, dirty region pixels match full redraw\n";
}
