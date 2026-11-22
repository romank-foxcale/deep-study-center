"""Make the app icon source (desktop/app-icon.png, 1024x1024): the blue diamond of the sidebar logo on a dark tile.
Plain Python (zlib), no image library. Then: npx tauri icon app-icon.png (from desktop/)."""

import struct
import zlib
from pathlib import Path

N = 1024
BG = (29, 28, 26, 255)          # dark tile
FG = (142, 166, 255, 255)       # accent blue (dark theme)
R = 180                          # tile corner radius
rows = []
for y in range(N):
    row = bytearray([0])  # filter: none
    for x in range(N):
        # rounded square tile
        cx, cy = min(max(x, R), N - 1 - R), min(max(y, R), N - 1 - R)
        inside = (x - cx) ** 2 + (y - cy) ** 2 <= R * R
        if not inside:
            row += bytes((0, 0, 0, 0))
            continue
        # diamond: |x - c| + |y - c| <= size
        d = abs(x - N / 2) + abs(y - N / 2)
        row += bytes(FG if d <= 300 else BG)
    rows.append(bytes(row))
raw = zlib.compress(b"".join(rows), 9)


def chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0)) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")
out = Path(__file__).parent / "app-icon.png"
out.write_bytes(png)
print(out, len(png))
