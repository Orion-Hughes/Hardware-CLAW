#pragma once
#include <cstddef>
#include <cstdint>

// Adapter for running the real Adafruit_GFX rasterizer without Arduino.
class Print {
public:
  virtual ~Print() = default;
  virtual size_t write(uint8_t byte) = 0;
  size_t print(const char *text) {
    size_t count = 0;
    while (*text) count += write(static_cast<uint8_t>(*text++));
    return count;
  }
};
