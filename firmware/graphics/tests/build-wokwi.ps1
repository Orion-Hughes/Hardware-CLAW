param([ValidateSet('clock', 'joystick')][string]$Case)
$ErrorActionPreference = 'Stop'
if (-not $Case) { throw 'Choose clock or joystick.' }
$root = (Resolve-Path "$PSScriptRoot/../../..").Path
$fixture = Join-Path $PSScriptRoot 'esp32s3'
$out = New-Item -ItemType Directory -Path "$root/temp/display-rendering/fast-$Case" -Force
$src = New-Item -ItemType Directory -Path "$out/src" -Force
$scratch = New-Item -ItemType Directory -Path "$out/tmp" -Force
$diagram = Get-Content -Raw -LiteralPath "$fixture/diagram.json" | ConvertFrom-Json -AsHashtable
Copy-Item -LiteralPath "$fixture/platformio.ini", "$fixture/wokwi.toml" -Destination $out.FullName
$graphics = "$root/LangChain/knowledge/drivers/HwClawGraphics/src"
Copy-Item -LiteralPath "$PSScriptRoot/scenes.h", "$graphics/HwClawGraphics.h", "$graphics/HwClawGraphics.cpp", "$graphics/HwClawSpiBitmap.h" -Destination $src.FullName
Copy-Item -LiteralPath "$fixture/$Case.cpp" -Destination "$src/main.cpp"
if ($Case -eq 'clock') {
    Add-Content -LiteralPath "$out/platformio.ini" -Value '    RTClib@2.1.4'
    $diagram.parts += @{type='wokwi-ds1307'; id='rtc'; top=-65; left=210; attrs=@{initTime='now'}}
    $diagram.connections += ,@('mcu:5V', 'rtc:5V', 'red', @())
    $diagram.connections += ,@('mcu:GND.1', 'rtc:GND', 'black', @())
    $diagram.connections += ,@('mcu:8', 'rtc:SDA', 'blue', @())
    $diagram.connections += ,@('mcu:9', 'rtc:SCL', 'green', @())
} else {
    $diagram.parts += @{type='wokwi-analog-joystick'; id='stick'; top=-100; left=210; attrs=@{}}
    $diagram.connections += ,@('mcu:3V3.1', 'stick:VCC', 'red', @())
    $diagram.connections += ,@('mcu:GND.1', 'stick:GND', 'black', @())
    $diagram.connections += ,@('mcu:4', 'stick:HORZ', 'blue', @())
    $diagram.connections += ,@('mcu:5', 'stick:VERT', 'green', @())
}
$diagram | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "$out/diagram.json" -Encoding utf8
$env:PLATFORMIO_CORE_DIR = Join-Path $root 'pio'
$env:TEMP = $env:TMP = $env:TMPDIR = $scratch.FullName
$log = "$out/build.log"
& "$root/tools/platformio-venv/Scripts/pio.exe" run -d $out.FullName -j 4 > $log 2>&1
$code = $LASTEXITCODE
Get-Content -LiteralPath $log -Tail 18
exit $code
