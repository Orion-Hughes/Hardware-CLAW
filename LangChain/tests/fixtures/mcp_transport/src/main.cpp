// Protocol test fixture ONLY. Never used by the production generator or acceptance evaluator.
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_SSD1306.h>
Adafruit_SSD1306 screen(128, 64, &Wire, -1);
constexpr int SIGNAL_PIN = 5;
unsigned long tick = 0;
bool level = false;
void setup() {
  Serial.begin(115200);
  pinMode(SIGNAL_PIN, OUTPUT);
  pinMode(4, INPUT_PULLUP);
  Serial.println("MCP_TRANSPORT_FIXTURE");
  Wire.begin(6, 7);
  if (screen.begin(SSD1306_SWITCHCAPVCC, 0x3c)) {
    screen.clearDisplay();
    screen.drawRect(0, 0, 128, 64, SSD1306_WHITE);
    screen.display();
  }
}
void loop() {
  while (Serial.available()) Serial.write(Serial.read());
  if (millis() - tick >= 250) {
    tick = millis();
    level = !level;
    digitalWrite(SIGNAL_PIN, level);
    Serial.printf("probe t=%lu adc=%d button=%d\n", tick, analogRead(2), digitalRead(4));
  }
  delay(1);
}
