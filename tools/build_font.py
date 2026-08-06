"""PicoType 字型建置工具 —— 單一資料模型、雙輸出、1 bit/pixel。

取代 full_hardcode_converter.py 的字型部分。相對舊版的四項改動：

1. **不再挑常用字**：直接取整份 TTF 的 cmap。舊流程需要 charsets/*.txt 人工字表，
   結果是 3,119 個字型根本沒有的字被存成 .notdef 佔位圖（同一張 2x2 點圖存了
   3,119 次）。改用 cmap 後，收錄的每一個字都保證有真字形，notdef 歸零。
2. **1 bit/pixel，row-aligned**：原始資料雖是 1 byte/pixel，但只有 0x00/0xFF
   兩種值，轉 1bpp 無損。row-aligned（每列補滿位元組）比 tight bitstream 多
   約 33 KB，換得解碼只需 `base + row * stride`，不必跨位元組位移。
3. **雙輸出**：同一次建置同時產生韌體用的 .h 與模擬器用的 .font/.map，
   兩者從此不可能不同步。
4. **PUA 與零寬控制字元排除**：見 EXCLUDE_RANGES / EXCLUDE_CHARS。

位元順序：**bit 0 = 該位元組最左邊的 pixel（LSB-first）**，與
rp2040-ili9341-infones/software/tools/make_cjk_font.py 的慣例一致。

IME 資料不由本工具產生。產生它的 ime_data/BPMF*.txt 目前不在 repo 內，而既有
產出已穩定（多份 header 與 output_data 之間位元組完全相同），因此改為從既有
header 原樣沿用，見 --ime-from。

用法:
    python -X utf8 tools/build_font.py
    python -X utf8 tools/build_font.py --font fonts/Cubic_11.ttf --size 12
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

# ==============================================================================
# --- 配置 ---
# ==============================================================================
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_FONT = "fonts/Cubic_11.ttf"
DEFAULT_SIZE = 12

# 輸出。名稱刻意不含 "Cubic" —— 那是 OFL 保留名稱，衍生物不應沿用。
OUT_HEADER = "output_data/picotype_data_optimized.h"
OUT_FONT = "output_data/picotype_12.font"
OUT_MAP = "output_data/picotype_12.map"

# IME 資料的來源 header（原樣沿用其 zhuyin_* 陣列）
DEFAULT_IME_FROM = "../pico_keyboard_ime_terminal_usb_host/picotype_data_optimized.h"

# 排除範圍。PUA 各字型有自己的私用圖形，收進來是無意義的亂碼。
EXCLUDE_RANGES = [(0xE000, 0xF8FF)]          # Private Use Area
EXCLUDE_CHARS = {0xFE0F, 0x20E3}             # VS-16、keycap 組字元：本就不該有字形

FONT_MAP_FORMAT = "<IIBBbbbB"                # 14 bytes，見 FontMapRecord_Opt
REC_SIZE = struct.calcsize(FONT_MAP_FORMAT)
assert REC_SIZE == 14

MAP_FORMAT_TAG = "1-bit"                     # 模擬器據此判斷解碼方式


def excluded(cp: int) -> bool:
    if cp in EXCLUDE_CHARS:
        return True
    return any(lo <= cp <= hi for lo, hi in EXCLUDE_RANGES)


# ==============================================================================
# --- 1bpp 打包 ---
# ==============================================================================
def pack_1bpp(pixels: bytes, w: int, h: int) -> bytes:
    """1 B/px 的 L-mode 資料 → 1bpp row-aligned，LSB-first。

    每列佔 stride = (w + 7) // 8 個位元組；第 i 個 pixel 落在
    byte i // 8 的 bit i % 8。
    """
    stride = (w + 7) // 8
    out = bytearray(stride * h)
    for y in range(h):
        row = y * w
        base = y * stride
        for x in range(w):
            if pixels[row + x] > 128:
                out[base + (x >> 3)] |= 1 << (x & 7)
    return bytes(out)


def unpack_1bpp(data: bytes, w: int, h: int) -> bytes:
    """pack_1bpp 的逆運算，還原成 1 B/px（0x00 / 0xFF）。驗證用。"""
    stride = (w + 7) // 8
    out = bytearray(w * h)
    for y in range(h):
        base = y * stride
        row = y * w
        for x in range(w):
            if data[base + (x >> 3)] >> (x & 7) & 1:
                out[row + x] = 0xFF
    return bytes(out)


# ==============================================================================
# --- 建置 ---
# ==============================================================================
def build(font_path: str, size: int):
    """回傳 (records, bitmap, stats)。records 為 dict list，已依 unicode 排序。"""
    cmap = set(TTFont(font_path, lazy=True).getBestCmap())
    pil = ImageFont.truetype(font_path, size, index=0)

    records, bitmap = [], bytearray()
    n_excluded = n_empty = 0

    for cp in sorted(cmap):
        if excluded(cp):
            n_excluded += 1
            continue
        ch = chr(cp)
        try:
            left, top, right, bottom = pil.getbbox(ch)
            x_advance = pil.getlength(ch)
        except Exception:
            n_empty += 1
            continue
        w, h = right - left, bottom - top
        if w == 0 or h == 0:
            # 空白字元保留可見的前進量，其餘無墨字形直接略過
            if ch == " ":
                w = int(x_advance) if x_advance > 0 else size // 3
                h, left, top = size, 0, 0
            else:
                n_empty += 1
                continue

        img = Image.new("L", (w, h), 0)
        ImageDraw.Draw(img).text((-left, -top), ch, font=pil, fill=255)
        raw = img.tobytes()

        packed = pack_1bpp(raw, w, h)
        # round-trip：確認 1bpp 轉換對這個字形是無損的
        assert unpack_1bpp(packed, w, h) == bytes(
            0xFF if b > 128 else 0x00 for b in raw
        ), f"round-trip 失敗 U+{cp:04X}"

        records.append({
            "unicode": cp, "offset": len(bitmap), "width": w, "height": h,
            "x_advance": int(x_advance), "x_offset": left, "y_offset": top,
        })
        bitmap.extend(packed)

    stats = {
        "cmap": len(cmap), "kept": len(records),
        "excluded": n_excluded, "empty": n_empty,
        "max_glyph_bytes": max(
            ((r["width"] + 7) // 8) * r["height"] for r in records),
    }
    return records, bytes(bitmap), stats


def pack_map(records) -> bytes:
    out = bytearray()
    for r in records:
        out.extend(struct.pack(
            FONT_MAP_FORMAT, r["unicode"], r["offset"], r["width"], r["height"],
            r["x_advance"], r["x_offset"], r["y_offset"], 0))
    return bytes(out)


# ==============================================================================
# --- 輸出：韌體 .h ---
# ==============================================================================
def extract_array(src: str, name: str) -> bytes:
    m = re.search(r"const uint8_t " + name + r"\[(\d+)\] PROGMEM = \{(.*?)\n\};",
                  src, re.S)
    if not m:
        raise SystemExit(f"錯誤: 在來源 header 找不到 {name}")
    data = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(2)))
    if len(data) != int(m.group(1)):
        raise SystemExit(f"錯誤: {name} 長度不符")
    return data


def c_array(name: str, data: bytes) -> str:
    lines = [f"const uint8_t {name}[{len(data)}] PROGMEM = {{"]
    for i in range(0, len(data), 16):
        lines.append("    " + ", ".join(f"0x{b:02x}" for b in data[i:i + 16]) + ",")
    lines.append("};")
    return "\n".join(lines)


def write_header(path, font_map, bitmap, n_records, ime_idx, ime_pool,
                 font_path, font_version, max_glyph_bytes):
    ime_rec = struct.calcsize("<HBxHH")
    content = f"""// Auto-generated by tools/build_font.py. DO NOT EDIT.
//
// 字型資料為 1 bit/pixel、row-aligned、LSB-first
//   （bit 0 = 該位元組最左邊的 pixel）。
// 每列佔 stride = (width + 7) / 8 個位元組，第 j 列起點為 offset + j * stride。
//
// 字型來源: {os.path.basename(font_path)} v{font_version}
//   SIL Open Font License 1.1 — https://github.com/ACh-K/Cubic-11
//   保留名稱「Cubic」「俐方體」不適用於本衍生資料。
//   完整授權與 attribution 見 fonts/LICENSES/。

#pragma once
#include <Arduino.h>

// 資料格式版本。renderer 必須以位元方式解碼 font_bitmap_data_1bpp；
// 舊的 1 B/px renderer 會因為找不到 font_bitmap_data_opt 而編譯失敗，
// 這是刻意的防呆 —— 錯誤組合應該編不過，而不是畫出一片雪花。
#define PICOTYPE_FONT_BPP 1

// 實測最大字形需求 {max_glyph_bytes} bytes。
#define PICOTYPE_MAX_GLYPH_BYTES {max_glyph_bytes}

// FONT DATA (1bpp)

struct __attribute__((packed)) FontMapRecord_Opt {{
    uint32_t unicode;   // 4 bytes
    uint32_t offset;    // 4 bytes
    uint8_t  width;     // 1 byte
    uint8_t  height;    // 1 byte
    uint8_t  x_advance; // 1 byte
    int8_t   x_offset;  // 1 byte
    int8_t   y_offset;  // 1 byte
    uint8_t  padding;   // 1 byte — 結構共 14 bytes
}};

{c_array("font_map_raw_opt", font_map)}

{c_array("font_bitmap_data_1bpp", bitmap)}

const FontMapRecord_Opt* const font_map_opt = reinterpret_cast<const FontMapRecord_Opt*>(font_map_raw_opt);
const size_t font_map_count_opt = {n_records};


// IME DATA (Optimized v4) —— 原樣沿用，本工具不重建

struct __attribute__((packed)) ImeIndexRecord_Opt {{
    uint16_t key_offset;    // 2 bytes
    uint8_t  key_len;       // 1 byte
    uint8_t  padding;       // 1 byte for alignment
    uint16_t data_offset;   // 2 bytes
    uint16_t data_len;      // 2 bytes
}};

{c_array("zhuyin_idx_raw_opt", ime_idx)}

{c_array("zhuyin_pool_opt", ime_pool)}

const ImeIndexRecord_Opt* const zhuyin_idx_opt = reinterpret_cast<const ImeIndexRecord_Opt*>(zhuyin_idx_raw_opt);
const size_t zhuyin_idx_count_opt = {len(ime_idx) // ime_rec};
"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


# ==============================================================================
# --- 輸出：模擬器 .font / .map ---
# ==============================================================================
def write_simulator(font_path_out, map_path_out, bitmap, records, font_name, size):
    with open(font_path_out, "wb") as f:
        f.write(bitmap)
    doc = {
        "metadata": {
            "font_name": font_name,
            "font_size": size,
            "format": MAP_FORMAT_TAG,
        },
        "characters": {
            str(r["unicode"]): [r["offset"], r["width"], r["height"]]
            for r in records
        },
    }
    with open(map_path_out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


# ==============================================================================
def main():
    ap = argparse.ArgumentParser(description="PicoType 字型建置（1bpp、整份 cmap）")
    ap.add_argument("--font", default=DEFAULT_FONT)
    ap.add_argument("--size", type=int, default=DEFAULT_SIZE)
    ap.add_argument("--ime-from", default=DEFAULT_IME_FROM,
                    help="沿用 IME 陣列的既有 header")
    args = ap.parse_args()

    font_path = os.path.join(REPO_ROOT, args.font)
    if not os.path.exists(font_path):
        raise SystemExit(f"錯誤: 找不到字型 {font_path}")

    tt = TTFont(font_path, lazy=True)
    version = tt["name"].getDebugName(5) or "?"
    print(f"字型: {os.path.basename(font_path)}  version {version}  @{args.size}px")

    records, bitmap, stats = build(font_path, args.size)
    font_map = pack_map(records)

    print(f"  cmap {stats['cmap']} 字 → 收錄 {stats['kept']}"
          f"（排除 PUA/控制字元 {stats['excluded']}，無墨字形 {stats['empty']}）")
    print(f"  bitmap {len(bitmap):,} B ({len(bitmap)/1024:.1f} KB)"
          f"   map {len(font_map):,} B ({len(font_map)/1024:.1f} KB)"
          f"   合計 {(len(bitmap)+len(font_map))/1024:.1f} KB")
    print(f"  最大字形 {stats['max_glyph_bytes']} B")

    ime_src_path = os.path.join(REPO_ROOT, args.ime_from)
    if not os.path.exists(ime_src_path):
        raise SystemExit(f"錯誤: 找不到 IME 來源 header {ime_src_path}\n"
                         f"      請以 --ime-from 指定既有的 picotype_data_optimized.h")
    ime_src = open(ime_src_path, encoding="utf-8").read()
    ime_idx = extract_array(ime_src, "zhuyin_idx_raw_opt")
    ime_pool = extract_array(ime_src, "zhuyin_pool_opt")
    print(f"  IME 沿用: idx {len(ime_idx):,} B  pool {len(ime_pool):,} B")

    write_header(os.path.join(REPO_ROOT, OUT_HEADER), font_map, bitmap,
                 len(records), ime_idx, ime_pool, font_path, version,
                 stats["max_glyph_bytes"])
    write_simulator(os.path.join(REPO_ROOT, OUT_FONT),
                    os.path.join(REPO_ROOT, OUT_MAP),
                    bitmap, records,
                    f"picotype_{args.size}", args.size)

    hdr_size = os.path.getsize(os.path.join(REPO_ROOT, OUT_HEADER))
    print(f"\n輸出:")
    print(f"  {OUT_HEADER}  ({hdr_size/1024/1024:.2f} MB)")
    print(f"  {OUT_FONT}")
    print(f"  {OUT_MAP}")


if __name__ == "__main__":
    main()
