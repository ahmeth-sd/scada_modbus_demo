#!/usr/bin/env python3
"""
Polling client: reads Modbus TCP every second, publishes to MQTT, and raises an alarm
if temperature > 60C for over 5 seconds (clears below 58C for 3 seconds).
Includes timeout/retry with exponential backoff.
"""
import json
import time
from datetime import datetime, timezone
from typing import Optional

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException
import paho.mqtt.client as mqtt

MODBUS_HOST = "127.0.0.1"
MODBUS_PORT = 5020

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883
TOPIC_TELE = "demo/telemetry"
TOPIC_ALARM = "demo/alarms"

READ_TIMEOUT = 1.0  # seconds
BASE_PERIOD = 1.0   # polling period
MAX_BACKOFF = 30.0

# Register addresses
ADDR_DEVICE_ID = 0
ADDR_STATUS    = 1
ADDR_POWER_W   = 2
ADDR_VOLT_x10  = 3
ADDR_CURR_x100 = 4
ADDR_TEMP_x10  = 5
ADDR_SOC_x10   = 6

def now_iso():
    return datetime.now(timezone.utc).isoformat()

class AlarmState:
    def __init__(self, hi=60.0, lo=58.0, raise_after=5.0, clear_after=3.0):
        self.hi = hi
        self.lo = lo
        self.raise_after = raise_after
        self.clear_after = clear_after
        self.high_since: Optional[float] = None
        self.low_since: Optional[float] = None
        self.active = False

    def update(self, temp_c: float, ts: float):
        if self.active:
            # When active, look for clear condition
            if temp_c < self.lo:
                if self.low_since is None:
                    self.low_since = ts
                if ts - self.low_since >= self.clear_after:
                    self.active = False
                    self.low_since = None
                    return "cleared"
            else:
                self.low_since = None
        else:
            # When inactive, look for raise condition
            if temp_c > self.hi:
                if self.high_since is None:
                    self.high_since = ts
                if ts - self.high_since >= self.raise_after:
                    self.active = True
                    self.high_since = None
                    return "raised"
            else:
                self.high_since = None
        return None

def publish_json(client, topic, payload):
    client.publish(topic, json.dumps(payload), qos=1, retain=False)

def main():
    # MQTT
    mqc = mqtt.Client(client_id="poller-1", clean_session=True)
    mqc.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    mqc.loop_start()

    # Modbus
    mb = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT, timeout=READ_TIMEOUT)
    backoff = 0.0
    alarm = AlarmState()

    try:
        while True:
            start = time.time()
            try:
                if not mb.connect():
                    raise ModbusIOException("connect failed")

                # read 0..9 as a block
                rr = mb.read_holding_registers(0, 10, unit=1)
                if rr.isError():
                    raise ModbusIOException(str(rr))

                regs = rr.registers
                device_id = regs[ADDR_DEVICE_ID]
                power_w = regs[ADDR_POWER_W]
                voltage_v = regs[ADDR_VOLT_x10] / 10.0
                current_a = regs[ADDR_CURR_x100] / 100.0
                temp_c = regs[ADDR_TEMP_x10] / 10.0
                soc = regs[ADDR_SOC_x10] / 10.0

                payload = {
                    "ts": now_iso(),
                    "device_id": device_id,
                    "values": {
                        "power_w": power_w,
                        "voltage_v": voltage_v,
                        "current_a": current_a,
                        "temp_c": temp_c,
                        "soc_pct": soc
                    },
                    "quality": "good"
                }
                publish_json(mqc, TOPIC_TELE, payload)

                # alarm evaluation
                evt = alarm.update(temp_c, time.time())
                if evt == "raised":
                    publish_json(mqc, TOPIC_ALARM, {
                        "ts": now_iso(),
                        "device_id": device_id,
                        "type": "TEMP_HIGH",
                        "state": "RAISED",
                        "threshold_hi": alarm.hi
                    })
                elif evt == "cleared":
                    publish_json(mqc, TOPIC_ALARM, {
                        "ts": now_iso(),
                        "device_id": device_id,
                        "type": "TEMP_HIGH",
                        "state": "CLEARED",
                        "threshold_lo": alarm.lo
                    })

                # success -> reset backoff
                backoff = 0.0

            except Exception as e:
                # Failure handling: publish degraded quality + backoff
                payload = {
                    "ts": now_iso(),
                    "device_id": None,
                    "values": {},
                    "quality": "bad",
                    "error": str(e)
                }
                publish_json(mqc, TOPIC_TELE, payload)

                # exponential backoff (1,2,4,8,... max MAX_BACKOFF)
                backoff = 1.0 if backoff == 0.0 else min(MAX_BACKOFF, backoff * 2.0)

            # sleep respecting base period + backoff
            elapsed = time.time() - start
            sleep_time = max(0.0, BASE_PERIOD - elapsed) + backoff
            time.sleep(sleep_time)

    finally:
        mqc.loop_stop()
        mqc.disconnect()
        mb.close()

if __name__ == "__main__":
    main()
