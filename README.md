# SCADA Modbus TCP + MQTT Mini Demo

This demo includes:
- A **pymodbus** TCP server simulating an inverter/BMS device (10–20 registers).
- A **Python client** polling every second with **timeout/retry/exponential backoff**, and a **hysteresis + duration** alarm rule (temperature > 60°C for > 5s).
- MQTT publish via **paho-mqtt**.
- A simple **web HMI** (HTML/JS) showing live chart and alarm list using **mqtt.js** and **Chart.js** over **WebSockets** (Mosquitto).

## Quick Start

### 0) Requirements
- Python 3.10+
- `pip install -r requirements.txt`
- Docker (for Mosquitto broker with WebSockets)

### 1) Start MQTT broker (with WebSockets)
```bash
docker compose up -d
# MQTT:    localhost:1883
# WS-MQTT: localhost:9001
```

### 2) Start the Modbus TCP simulator
```bash
python server_sim.py
# Server listens on 0.0.0.0:5020
```

### 3) Start the polling client (Modbus -> MQTT)
```bash
python client_poll.py
```

### 4) Open the HMI
Just open `web/index.html` in your browser.
It connects to `ws://localhost:9001` and subscribes to:
- `demo/telemetry` for live data
- `demo/alarms` for alarms

## Register Map (Holding Registers)
| Addr | Name            | Unit | Scaling | Notes                          |
|-----:|-----------------|------|---------|--------------------------------|
| 0    | device_id       | -    | 1       | 1001                           |
| 1    | status_bits     | -    | 1       | bitfield                       |
| 2    | power_w         | W    | 1       | simulated                      |
| 3    | voltage_v_x10   | V    | /10     | e.g., 230.0 V stored as 2300   |
| 4    | current_a_x100  | A    | /100    | e.g., 5.13 A stored as 513     |
| 5    | temp_c_x10      | °C   | /10     | e.g., 62.5°C stored as 625     |
| 6    | soc_pct_x10     | %    | /10     | e.g., 72.0% stored as 720      |
| 7    | setpoint_w      | W    | 1       | write target power             |
| 8    | reserved1       | -    | 1       | -                              |
| 9    | reserved2       | -    | 1       | -                              |

## Alarm Rule (Hysteresis + Duration)
- Raise alarm: **temp > 60°C** continuously for **> 5 seconds**
- Clear alarm: temp **< 58°C** continuously for **> 3 seconds**

## Notes
- The client uses **timeout + retry + exponential backoff (max 30s)**.
- On successful read after backoff, it resets the backoff stage.
- Telemetry is published as JSON with a timestamp and quality.
