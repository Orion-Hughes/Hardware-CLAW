#pragma once
#include <stdlib.h>
#include "HwClawGraphics.h"

// Shared test scenes; not part of the graphics library or Agent input.
constexpr uint16_t bg = 0x10a3;
constexpr uint16_t ink = 0xffff;
constexpr uint16_t accent = 0x07ff;
constexpr hwclaw::Rect textRegion{20, 22, 200, 32};
constexpr hwclaw::Rect plotRegion{60, 82, 120, 120};
constexpr int16_t plotCenter = 60;
constexpr int16_t pointRadius = 5;
constexpr int16_t pointSide = 2 * pointRadius + 1;

template <typename T>
bool showValue(hwclaw::RegionCanvas &canvas, T &target, const char *value) {
  return canvas.begin(textRegion, bg) && canvas.drawText(value, ink, 3) &&
         canvas.present(target);
}

template <typename T>
bool drawPlot(hwclaw::RegionCanvas &canvas, T &target, hwclaw::Rect patch,
              int16_t dx, int16_t dy) {
  if (!canvas.begin(patch, bg)) return false;
  const int16_t cx = plotRegion.x + plotCenter - patch.x;
  const int16_t cy = plotRegion.y + plotCenter - patch.y;
  canvas.drawCircle(cx, cy, 50, ink);
  canvas.fillCircle(cx + dx, cy + dy, pointRadius, accent);
  return canvas.present(target);
}

template <typename T>
bool showPoint(hwclaw::RegionCanvas &canvas, T &target, int16_t dx, int16_t dy) {
  return drawPlot(canvas, target, plotRegion, dx, dy);
}

template <typename T>
bool movePoint(hwclaw::RegionCanvas &canvas, T &target, int16_t oldX, int16_t oldY,
               int16_t x, int16_t y, unsigned &pixels) {
  if (oldX == x && oldY == y) { pixels = 0; return true; }
  const hwclaw::Rect oldPatch{int16_t(plotRegion.x + plotCenter + oldX - pointRadius),
                             int16_t(plotRegion.y + plotCenter + oldY - pointRadius),
                             pointSide, pointSide};
  const hwclaw::Rect newPatch{int16_t(plotRegion.x + plotCenter + x - pointRadius),
                             int16_t(plotRegion.y + plotCenter + y - pointRadius),
                             pointSide, pointSide};
  const hwclaw::Rect both{oldPatch.x < newPatch.x ? oldPatch.x : newPatch.x,
                         oldPatch.y < newPatch.y ? oldPatch.y : newPatch.y,
                         int16_t(pointSide + abs(x - oldX)), int16_t(pointSide + abs(y - oldY))};
  // Large jumps are cheaper as two small submissions. Both patches render
  // the final scene, so the overlap never erases part of the new dot.
  if (both.width * both.height <= 2 * pointSide * pointSide) {
    pixels = both.width * both.height;
    return drawPlot(canvas, target, both, x, y);
  }
  pixels = 2 * pointSide * pointSide;
  return drawPlot(canvas, target, oldPatch, x, y) && drawPlot(canvas, target, newPatch, x, y);
}
