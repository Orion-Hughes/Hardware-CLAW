#pragma once
#include <cstdint>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <string>

using String = std::string;
class __FlashStringHelper;
#define PROGMEM
inline float radians(float degrees) { return degrees * (3.141592653589793f / 180); }
