
import asyncio
from bleak import BleakScanner

TARGET = "FF:FF:92:82:68:97"

async def main():
    print("SCANNING BLE DEVICES...")

    devices = await BleakScanner.discover(
        timeout=40,
        return_adv=True
    )

    print(f"FOUND: {len(devices)} DEVICES\n")

    for device, adv in devices.values():
        name = adv.local_name or device.name or "Unknown"

        print("NAME:", name)
        print("MAC:", device.address)
        print("RSSI:", adv.rssi)

        for mid, data in adv.manufacturer_data.items():
            print(f"MANUFACTURER ID: 0x{mid:04X}")
            print("DATA:", data.hex(" "))

            if mid == 0x5053 and len(data) >= 5:
                model = (
                    (data[4] << 8) | data[0]
                ) & 0x3FFF

                firmware = (data[2] << 8) | data[3]

                print(f"MODEL ID: 0x{model:04X}")
                print(f"FIRMWARE: 0x{firmware:04X}")

        if (
            device.address.upper() == TARGET
            or name == "NEMR92826897"
        ):
            print(">>> THIS IS OUR TAG <<<")

        print("-" * 45)

asyncio.run(main())
