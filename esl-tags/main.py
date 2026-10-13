
import asyncio
import math
import time

import qrcode
from PIL import Image, ImageDraw, ImageFont
from bleak import BleakClient, BleakScanner


NAME = "NEMR92826897"
MAC = "FF:FF:92:82:68:97"

FEF1 = "0000fef1-0000-1000-8000-00805f9b34fb"
FEF2 = "0000fef2-0000-1000-8000-00805f9b34fb"

CELL = "A-102"
URL = "https://wms.scada25.ru/s/c/A-102"

STATUS = "FREE"
# EXPIRED, NORMAL, FREE

WAREHOUSE = "Цех №2"
ZONE = "RECV"
PRODUCT = "Монастырские · лайм-мята"
QUANTITY = "10 001 шт. · 0,5л ×12"
EXPIRY = "21.07.2026"

RED = (215, 0, 0)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def font(size):
    for path in (
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/seguisb.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass

    raise RuntimeError("Cyrillic font not found")


def make_image():
    img = Image.new("RGB", (250, 122), WHITE)
    d = ImageDraw.Draw(img)

    danger = STATUS == "EXPIRED"
    free = STATUS == "FREE"

    accent = RED if danger else BLACK

    def text(value, x, y, size, color=BLACK):
        d.text(
            (x, y),
            value,
            font=font(size),
            fill=color
        )

    def fitted(value, max_width, size):
        f = font(size)

        if d.textbbox(
            (0, 0), value, font=f
        )[2] <= max_width:
            return value

        while value:
            value = value[:-1]

            result = value.rstrip() + "…"

            width = d.textbbox(
                (0, 0), result, font=f
            )[2]

            if width <= max_width:
                return result

        return ""

    # 1. Верхняя шапка
    d.rectangle((0, 0, 249, 25), fill=accent)

    if danger:
        # Знак предупреждения
        d.polygon(
            [(7, 21), (17, 3), (27, 21)],
            fill=WHITE
        )

        d.line(
            [(17, 10), (17, 15)],
            fill=RED,
            width=2
        )

        d.ellipse(
            (16, 18, 18, 20),
            fill=RED
        )

        heading = "ПРОСРОЧЕНО"
    elif free:
        heading = "СВОБОДНА"
    else:
        heading = "ЯЧЕЙКА ЗАНЯТА"

    text(
        heading,
        33 if danger else 8,
        2,
        18 if danger else 15,
        WHITE
    )

    # 2. Разделитель QR
    d.line(
        (175, 27, 175, 121),
        fill=BLACK,
        width=1
    )

    # 3. Настоящий QR
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=2,
        border=4
    )

    qr.add_data(URL)
    qr.make(fit=True)

    qr_img = qr.make_image(
        fill_color="black",
        back_color="white"
    ).convert("RGB")

    if qr_img.size != (74, 74):
        raise RuntimeError(
            f"QR size does not fit: {qr_img.size}"
        )

    img.paste(qr_img, (176, 27))

    text("СКАН QR", 181, 108, 8)

    # 4. Номер ячейки
    text(CELL, 5, 27, 29)

    # 5. Предупреждение
    d.rectangle(
        (99, 38, 172, 58),
        outline=accent,
        width=2
    )

    badge = (
        "НЕ БРАТЬ"
        if danger else
        "СВОБОДНО"
        if free else
        "ЗАНЯТО"
    )

    text(
        badge,
        104,
        41,
        10,
        accent
    )

    # 6. Разделительная линия
    d.line(
        (5, 62, 172, 62),
        fill=BLACK,
        width=1
    )

    # 7. Информация о ячейке
    text(
        fitted(f"{WAREHOUSE} · {ZONE}", 165, 10),
        6,
        64,
        10
    )

    if free:
        text("Нет продукции", 6, 80, 11)
        text("Ожидает размещения", 6, 93, 9)

    else:
        text(
            fitted(PRODUCT, 166, 9),
            6,
            78,
            9
        )

        text(
            fitted(QUANTITY, 166, 9),
            6,
            91,
            9
        )

    # 8. Нижняя статусная полоса
    d.rectangle(
        (0, 104, 174, 121),
        fill=accent
    )

    bottom_text = (
        f"СРОК {EXPIRY}"
        if not free
        else "ЯЧЕЙКА ПУСТА"
    )

    text(
        fitted(bottom_text, 165, 11),
        7,
        104,
        11,
        WHITE
    )

    return img


def encode_bwr(image):
    canvas = Image.new(
        "RGB",
        (250, 128),
        WHITE
    )

    canvas.paste(image, (0, 3))

    rotated = canvas.rotate(
        270,
        expand=True
    )

    pixels = rotated.load()

    white_plane = bytearray()
    red_plane = bytearray()

    wb = 0
    rb = 0
    bit = 7

    for y in range(rotated.height):
        for x in range(rotated.width - 1, -1, -1):
            r, g, b = pixels[x, y]

            is_white = (
                r > 128
                and g > 128
                and b > 128
            )

            is_red = (
                r > 128
                and g <= 128
                and b <= 128
            )

            if is_white:
                wb |= 1 << bit

            if is_red:
                rb |= 1 << bit

            bit -= 1

            if bit < 0:
                white_plane.append(wb)
                red_plane.append(rb)

                wb = 0
                rb = 0
                bit = 7

    data = bytes(
        white_plane + red_plane
    )

    if len(data) != 8000:
        raise RuntimeError(
            f"Invalid image size: {len(data)}"
        )

    return data


async def upload_image(image):
    data = encode_bwr(image)

    device = await BleakScanner.find_device_by_name(
        NAME,
        timeout=40
    )

    if device is None:
        raise RuntimeError("Tag not found")

    if device.address.upper() != MAC:
        raise RuntimeError("MAC mismatch")

    responses = asyncio.Queue()

    def notify(sender, value):
        responses.put_nowait(bytes(value))

    async with BleakClient(
        device,
        timeout=20
    ) as client:

        print("CONNECTED:", client.is_connected)
        print("MTU:", client.mtu_size)

        await client.start_notify(FEF1, notify)
        await asyncio.sleep(0.5)

        async def receive():
            return await asyncio.wait_for(
                responses.get(),
                timeout=25
            )

        async def command(payload):
            await asyncio.wait_for(
                client.write_gatt_char(
                    FEF1,
                    payload,
                    response=True
                ),
                timeout=15
            )

            return await receive()

        try:
            # Размер блока
            reply = await command(b"\x01")

            if len(reply) != 3 or reply[0] != 1:
                raise RuntimeError("Block size error")

            block_size = int.from_bytes(
                reply[1:3],
                "little"
            )

            if not (
                5 <= block_size <= client.mtu_size - 3
            ):
                raise RuntimeError("Invalid block size")

            chunk_size = block_size - 4
            total = math.ceil(
                len(data) / chunk_size
            )

            print("TOTAL BLOCKS:", total)

            # Подготовка
            prepare = (
                b"\x02"
                + len(data).to_bytes(4, "little")
                + b"\x00\x00\x00"
            )

            reply = await command(prepare)

            if (
                len(reply) < 2
                or reply[:2] != b"\x02\x00"
            ):
                raise RuntimeError("Prepare failed")

            # Старт
            reply = await command(b"\x03")

            sent = set()
            attempts = 0

            # Передача изображения
            while True:
                if len(reply) < 2 or reply[0] != 5:
                    raise RuntimeError(
                        f"Unexpected response: {reply.hex()}"
                    )

                if reply[1] == 8:
                    if len(sent) != total:
                        raise RuntimeError(
                            f"Incomplete: {len(sent)}/{total}"
                        )

                    print("TRANSFER COMPLETE")
                    break

                if len(reply) != 6 or reply[1] != 0:
                    raise RuntimeError(
                        f"Transfer error: {reply.hex()}"
                    )

                index = int.from_bytes(
                    reply[2:6],
                    "little"
                )

                if index >= total:
                    raise RuntimeError("Invalid block index")

                start = index * chunk_size

                packet = (
                    index.to_bytes(4, "little")
                    + data[start:start + chunk_size]
                )

                await asyncio.wait_for(
                    client.write_gatt_char(
                        FEF2,
                        packet,
                        response=True
                    ),
                    timeout=15
                )

                sent.add(index)
                attempts += 1

                print(
                    f"BLOCK {len(sent)}/{total}",
                    flush=True
                )

                if attempts > total * 4:
                    raise RuntimeError("Too many retries")

                reply = await receive()

        finally:
            if client.is_connected:
                await client.stop_notify(FEF1)


async def main():
    started = time.perf_counter()

    image = make_image()

    # Сохраняем PNG для проверки макета
    image.save("preview_a102.png")

    print("SCADA ESL")
    print("CELL:", CELL)
    print("STATUS:", STATUS)

    await upload_image(image)

    print(
        f"DONE: {time.perf_counter() - started:.1f} sec"
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("STOPPED")
    except Exception as e:
        print(
            f"ERROR: {type(e).__name__}: {e}"
        )
