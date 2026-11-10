# Local ESP32-S3 / Wokwi compatibility patch

Base: beegee-tokyo/DHT sensor library for ESPx 1.19.0 (upstream library.json reports 1.19).
Upstream: https://github.com/beegee-tokyo/DHTesp
Original source headers and GPL-3.0 LICENSE are retained.

This project vendors the library as the single DHTesp driver source used by Hardware-CLAW.
It is maintained as a hardware-level local bundle, not as a project-specific generator patch.

In DHTesp::readSensor(), configure the start pulse as OUTPUT_OPEN_DRAIN. Release the line by writing HIGH while remaining in open-drain mode, instead of switching from OUTPUT to INPUT.

In the original ESP32-S3 simulation, the first sample timed out at edge index 79 (91 us). Diagnostic edge durations showed that the read loop was misaligned with the response handshake and ultimately waited for an absent final edge. Removing only the digitalWrite after pinMode(INPUT) did not fix it. Open-drain release passed the same 24 C / 40%, 30 C / 65%, and restored 24 C / 40% serial scenario without changing GPIO, sensor wiring, sample interval, or expectations.

A no-external-pull-up control run on 2026-11-09 kept only VCC, GND and GPIO4 wiring, compiled with the controlled PlatformIO baseline, passed Wokwi CLI lint, and completed the same 24 C / 40%, 30 C / 65%, restored 24 C / 40% scenario. Therefore an external 10 kOhm pull-up is not required for this verified ESP32-S3 / Arduino / Wokwi simulation baseline.

This establishes a bus-release/timing compatibility observation in the tested simulator and driver combination. It does not establish a defect on physical ESP32-S3 hardware, verify the purchased red module's onboard pull-up, or identify the simulator's internal cause.
