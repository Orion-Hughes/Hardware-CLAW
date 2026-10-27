#include <Arduino.h>
#include <Wire.h>
#include <DHT.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

constexpr uint8_t DHT_PIN = 18;
constexpr uint8_t OLED_SDA = 8;
constexpr uint8_t OLED_SCL = 9;
constexpr uint8_t OLED_ADDRESS = 0x3c;
constexpr uint16_t SAMPLE_INTERVAL_MS = 2000;

DHT dht(DHT_PIN, DHT22);
Adafruit_SSD1306 display(128, 64, &Wire, -1);

void setup() {
  Serial.begin(115200);
  delay(500);

  dht.begin();
  Wire.begin(OLED_SDA, OLED_SCL);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
    Serial.println("OLED_INIT_FAILED");
    while (true) {
      delay(1000);
    }
  }

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Hardware-CLAW");
  display.println("Waiting for data...");
  display.display();

  Serial.println("HWCLAW_READY");
}

void loop() {
  const float temperature = dht.readTemperature();
  const float humidity = dht.readHumidity();

  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("DHT_READ_FAILED");
    delay(SAMPLE_INTERVAL_MS);
    return;
  }

  Serial.printf("DATA T=%.1f H=%.1f\n", temperature, humidity);

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("Hardware-CLAW");
  display.println();
  display.printf("Temp: %.1f C\n", temperature);
  display.printf("Humidity: %.1f %%\n", humidity);
  display.display();

  delay(SAMPLE_INTERVAL_MS);
}
