$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot/../../..").Path
$gfx = "$root/LangChain/knowledge/upstream/drivers/Adafruit-GFX-Library"
$source = "$root/LangChain/knowledge/drivers/HwClawGraphics/src"
$out = New-Item -ItemType Directory -Path "$root/temp/display-rendering/host" -Force
$env:TMP = $env:TEMP = $env:TMPDIR = $out.FullName
$exe = "$out/graphics-test.exe"
& g++ -std=c++11 -DARDUINO=10800 -Wall -Wextra -Werror -I $source -I "$PSScriptRoot/host" -I $gfx `
    "$PSScriptRoot/host_test.cpp" "$source/HwClawGraphics.cpp" "$gfx/Adafruit_GFX.cpp" -o $exe
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $exe "$out/before.ppm" "$out/after.ppm"
exit $LASTEXITCODE
