# FirmGen PRD: SafeSight Beacon (Closed Loop bonus)

Paste into FirmGen v0.4.1 (ESP-IDF v5.5, ESP32 DevKit). Freeze the PRD before generating.

## Goal
A physical alarm beacon that reacts in real time to SafeSight alerts produced from the PipeGen vision pipeline.

## Bridge (perception → board)
- **REQ-BR-1:** The board receives alerts over **USB serial (UART0, 115200 8N1)** as single ASCII characters: `C` critical (man down), `H` high (fall), `W` warning (zone/crowding), `I` info (recovered).
- **REQ-BR-2:** Each received alert is echoed on the UART as `ALERT <char>` within 50 ms.

## Outputs
- **REQ-OUT-1:** `C` → red LED (GPIO25) strobes at about 4 Hz and the buzzer (GPIO14) sounds until the ACK button is pressed.
- **REQ-OUT-2:** `H` → red LED solid plus 3 short beeps; returns to idle after 10 s.
- **REQ-OUT-3:** `W` → amber LED (GPIO26) blinks for 3 s.
- **REQ-OUT-4:** `I` or idle → green LED (GPIO27) solid.
- **REQ-OUT-5:** An unacknowledged `C` is never downgraded by a later `H`, `W` or `I`.

## Input
- **REQ-IN-1:** ACK button on GPIO0 (BOOT, active low) clears a critical alarm and prints `ACK`.

## Acceptance criteria (shown on the UART monitor + physically)
1. On boot it prints `SAFESIGHT_BEACON_READY` and the green LED is on.
2. Sending `W` gives `ALERT W` and the amber LED blinks, then green again after 3 s.
3. Sending `C` then `I` gives `ALERT C` and the strobe plus buzzer keep going (I ignored); pressing BOOT prints `ACK` and the board goes green.
4. Live: lying down in front of the camera makes the beacon go H, then C after 4 s.

Reference implementation (Arduino): `firmware/safesight_beacon/safesight_beacon.ino`. On the GPU machine run SafeSight with `--serial /dev/ttyUSB0` (`run_with_pipegen.sh` adds this automatically).
