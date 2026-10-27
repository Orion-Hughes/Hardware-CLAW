#include <Arduino.h>
#include <DHTesp.h>
#include <math.h>
// Example only: adapt this constant to the saved design.
constexpr int DHT_PIN = 4;
DHTesp dht;
void setup() {
  Serial.begin(115200);
  Serial.println("HWCLAW_BOOT");
  dht.setup(DHT_PIN, DHTesp::DHT22);
}
void loop() {
  delay(2000);
  TempAndHumidity reading = dht.getTempAndHumidity();
  if (dht.getStatus() != DHTesp::ERROR_NONE || isnan(reading.temperature) || isnan(reading.humidity)) {
    Serial.printf("DHT_ERROR: %s\n", dht.getStatusString());
    return;
  }
  Serial.printf("Temperature: %.1f C | Humidity: %.1f %%\r\n", reading.temperature, reading.humidity);
}
