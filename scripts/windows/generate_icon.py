#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-dependency generator for the multi-resolution Windows .ico desktop icon.

Writes a valid PNG-in-ICO file (16x16, 32x32, 48x48, 256x256) matching the DSA
emerald/cyan quant emblem without requiring Pillow or ImageMagick.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)


def _render_emblem_rgba(size: int) -> bytes:
    rows = bytearray()
    radius = size * 0.22
    for y in range(size):
        rows.append(0)  # PNG filter type 0 (None)
        ny = (y + 0.5) / size
        for x in range(size):
            nx = (x + 0.5) / size

            # Rounded-square mask
            dx = max(0.0, max(radius - x - 0.5, x + 0.5 - (size - radius)))
            dy = max(0.0, max(radius - y - 0.5, y + 0.5 - (size - radius)))
            dist = (dx * dx + dy * dy) ** 0.5
            if dist > radius:
                rows.extend((0, 0, 0, 0))
                continue

            # Dark navy gradient background
            r = int(11 + 6 * nx)
            g = int(18 + 16 * ny)
            b = int(32 + 26 * (nx + ny) * 0.5)
            a = 255

            # Subtle cyan border ring
            if radius - dist < max(1.2, size * 0.035):
                r, g, b = 34, 211, 238

            # 4 ascending quant bars
            bars = (
                (0.18, 0.30, 0.54, (14, 165, 233)),
                (0.35, 0.47, 0.43, (34, 211, 238)),
                (0.52, 0.64, 0.33, (45, 212, 191)),
                (0.69, 0.81, 0.22, (52, 211, 153)),
            )
            for bx0, bx1, by_top, color in bars:
                if bx0 <= nx <= bx1 and by_top <= ny <= 0.78:
                    r, g, b = color
                    break

            rows.extend((r, g, b, a))
    return bytes(rows)


def _encode_png(size: int) -> bytes:
    raw = _render_emblem_rgba(size)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )


def generate_ico(output_path: Path) -> Path:
    sizes = (16, 32, 48, 256)
    images = [_encode_png(s) for s in sizes]
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries = bytearray()
    for size, img in zip(sizes, images):
        w_byte = 0 if size >= 256 else size
        h_byte = 0 if size >= 256 else size
        entries.extend(struct.pack("<BBBBHHII", w_byte, h_byte, 0, 0, 1, 32, len(img), offset))
        offset += len(img)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(header + bytes(entries) + b"".join(images))
    return output_path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else (repo_root / "assets" / "dsa-desktop.ico")
    out = generate_ico(target)
    print(f"Generated Windows desktop icon: {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
