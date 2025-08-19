#!/usr/bin/env python3
"""
Modbus TCP inverter/BMS simulator using pymodbus.
Listens at 0.0.0.0:5020 and updates registers every second.
"""
import asyncio
import random
import threading
import time
from datetime import datetime
from pymodbus.server import StartTcpServer, ModbusTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext, ModbusSequentialDataBlock
from pymodbus.device import ModbusDeviceIdentification

HOST = "0.0.0.0"
PORT = 5020

# Register map length
HR_LEN = 16

temp_high_mode = [False]
high_start_time = [None]

class UpdatingDataBlock(ModbusSequentialDataBlock):
    def __init__(self, address, values):
        super().__init__(address, values)
        self.lock = threading.Lock()

    def set_reg(self, addr, value):
        with self.lock:
            super().setValues(addr, [value])

    def get_reg(self, addr):
        with self.lock:
            return super().getValues(addr, 1)[0]

    def get_regs(self, addr, count):
        with self.lock:
            return super().getValues(addr, count)

def make_context():
    # Init holding registers with defaults
    initial = [0] * HR_LEN
    initial[0] = 1001        # device_id
    initial[1] = 0b00000001  # status_bits (running)
    initial[2] = 1200        # power_w
    initial[3] = 2300        # voltage_v_x10 -> 230.0V
    initial[4] = 500         # current_a_x100 -> 5.00A
    initial[5] = 550         # temp_c_x10 -> 55.0°C
    initial[6] = 700         # soc_pct_x10 -> 70.0%
    initial[7] = 1200        # setpoint_w
    block = UpdatingDataBlock(0, initial)
    slave = ModbusSlaveContext(hr=block, zero_mode=True)
    context = ModbusServerContext(slaves=slave, single=True)
    return context, block



# Sıcaklık periyodik olarak yükselip düşer
def updater(block: UpdatingDataBlock, interval=1.0):
    t = 0.0
    while True:
        try:
            sp = block.get_reg(7)
            pw = block.get_reg(2)
            delta = max(-50, min(50, sp - pw))
            if abs(delta) > 10:
                pw += int(delta * 0.3)
            else:
                pw += random.randint(-5, 5)
            pw = max(0, min(5000, pw))
            block.set_reg(2, pw)

            v = 2300 + random.randint(-15, 15)
            block.set_reg(3, v)

            current_a = pw / max(1, v/10)
            ia = int(max(0, min(2000, current_a * 100)))
            block.set_reg(4, ia)

            # 20 saniyelik döngü: ilk 10 sn yüksek, sonraki 10 sn düşük sıcaklık
            cycle = int((t // 10) % 2)
            if cycle == 0:
                temp_target = 65 + random.uniform(-0.5, 0.5)
            else:
                temp_target = 40 + random.uniform(-0.5, 0.5)

            temp = block.get_reg(5) / 10.0
            temp = temp * 0.8 + temp_target * 0.2
            block.set_reg(5, int(temp * 10))

            soc = block.get_reg(6) / 10.0
            soc += random.uniform(-0.2, 0.2)
            soc = min(100.0, max(0.0, soc))
            block.set_reg(6, int(soc * 10))

            status = 0b00000001
            block.set_reg(1, status)

            t += interval
            time.sleep(interval)
        except Exception as e:
            print(f"[{datetime.now()}] updater error: {e}")
            time.sleep(interval)


async def run_server():
    context, block = make_context()

    identity = ModbusDeviceIdentification()
    identity.VendorName = "DemoCorp"
    identity.ProductCode = "DEMO"
    identity.VendorUrl = "https://example.com"
    identity.ProductName = "ModbusTCP Inverter/BMS Simulator"
    identity.ModelName = "SIM-INV-01"
    identity.MajorMinorRevision = "1.0"

    th = threading.Thread(target=updater, args=(block,), daemon=True)
    th.start()

    print(f"Starting Modbus TCP simulator at {HOST}:{PORT}")
    server = ModbusTcpServer(context, identity=identity, address=(HOST, PORT))
    await server.serve_forever()

def main():
    asyncio.run(run_server())

if __name__ == "__main__":
    main()
