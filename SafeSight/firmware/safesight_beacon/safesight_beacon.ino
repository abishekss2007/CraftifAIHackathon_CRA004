// SafeSight beacon: closes the loop from PipeGen vision to a physical siren.
// SafeSight writes one character per alert over USB serial (115200 baud):
//   C = critical (man down)  -> fast red strobe + buzzer until ACK button
//   H = high (fall)          -> red on + 3 beeps
//   W = warning (zone/crowd) -> amber blink for 3 s
//   I = info (recovered)     -> green
// Wiring (ESP32 DevKit): red LED GPIO 25, amber LED GPIO 26, green LED GPIO 27,
// active buzzer GPIO 14, ACK push button GPIO 0 (BOOT button) to GND.

const int RED = 25, AMBER = 26, GREEN = 27, BUZZ = 14, ACK = 0;
char state = 'I';
unsigned long since = 0;

void setAll(bool r, bool a, bool g) {
  digitalWrite(RED, r); digitalWrite(AMBER, a); digitalWrite(GREEN, g);
}

void setup() {
  Serial.begin(115200);
  pinMode(RED, OUTPUT); pinMode(AMBER, OUTPUT); pinMode(GREEN, OUTPUT);
  pinMode(BUZZ, OUTPUT); pinMode(ACK, INPUT_PULLUP);
  setAll(false, false, true);
  Serial.println("SAFESIGHT_BEACON_READY");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == 'C' || c == 'H' || c == 'W' || c == 'I') {
      // never downgrade an unacknowledged critical alarm
      if (state == 'C' && c != 'C') continue;
      state = c; since = millis();
      Serial.printf("ALERT %c\n", c);
    }
  }
  unsigned long t = millis() - since;
  switch (state) {
    case 'C': {
      bool on = (millis() / 120) % 2;
      setAll(on, false, false); digitalWrite(BUZZ, on);
      if (digitalRead(ACK) == LOW) { state = 'I'; digitalWrite(BUZZ, LOW); Serial.println("ACK"); }
      break;
    }
    case 'H':
      setAll(true, false, false);
      digitalWrite(BUZZ, t < 900 && (t / 150) % 2 == 0);
      if (t > 10000) state = 'I';
      break;
    case 'W':
      setAll(false, (millis() / 300) % 2, false); digitalWrite(BUZZ, LOW);
      if (t > 3000) state = 'I';
      break;
    default:
      setAll(false, false, true); digitalWrite(BUZZ, LOW);
  }
}
