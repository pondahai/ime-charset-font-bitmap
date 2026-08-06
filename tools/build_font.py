"""PicoType 字型建置工具 —— 多字型 fallback 鏈、1 bit/pixel、雙輸出。

取代 full_hardcode_converter.py 的字型部分。相對舊版的五項改動：

1. **不再挑常用字**：收錄範圍由字型的 cmap 決定，不需要人工整理的字元集。
   舊流程有 3,119 個字型根本沒有的字被存成 .notdef 佔位圖（同一張 2x2 點圖
   存了 3,119 次），因為唯一的過濾條件是 `width == 0 or height == 0`，
   而 .notdef 的 bbox 是 13x5，通過了檢查。
2. **多字型 fallback 鏈**：主字型畫不出來的字，依序往後面的字型找。
   **一律以 cmap 查表決定，不靠 bitmap 特徵猜測** —— 若用特徵比對，
   `'` 和 `;` 剛好也是 4 個亮點會被誤刪，`。︷＝～` 這 4 個真字也是 13x5。
3. **1 bit/pixel，row-aligned**：原始資料雖是 1 B/px，但只有 0x00/0xFF
   兩種值，轉 1bpp 無損。row-aligned 比 tight bitstream 多約 33 KB，
   換得解碼只需 `base + row * stride`，不必跨位元組位移。
4. **雙輸出**：同一次建置同時產生韌體用的 .h 與模擬器用的 .font/.map。
5. **PUA 與零寬控制字元排除**：見 EXCLUDE_RANGES / EXCLUDE_CHARS。

位元順序：**bit 0 = 該位元組最左邊的 pixel（LSB-first）**。

**每一層都必須跑在自己的設計字級**。點陣字型離開設計字級就會被反鋸齒破壞
（實測 Fusion @13 筆畫結構跑掉、Unifont @12 有 99.9% 灰階）。對齊只能用
位移校正，不能縮放。判定工具見 tools/check_pixel_font.py。

IME 資料不由本工具產生，改為從既有 header 原樣沿用，見 --ime-from。

用法:
    python -X utf8 tools/build_font.py
    python -X utf8 tools/build_font.py --primary-only    # 只用主字型
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

# ==============================================================================
# --- 配置 ---
# ==============================================================================
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# fallback 鏈：(路徑, 設計字級, 校正)
#   dx / dy   繪製位移，用來對齊主字型的字身位置
#   advance   覆寫 x_advance，讓混排時的前進量一致
# 校正值的求法：拿兩套字型對共有字逐 pixel 比對字身位置差，見 §7.7。
FONT_CHAIN = [
    ("fonts/Cubic_11.ttf", 12, {}),
    ("fonts/fusion-pixel-12px-proportional-zh_hant.ttf", 12,
     dict(dx=+1, dy=-2, advance=13)),
]

# 收錄範圍 = 主字型 cmap ∪ 這些字表。
# 後者是「想要但主字型沒有」的字，由 charsets/missing_from_cubic.txt 提供。
TARGET_CHARSETS = ["charsets/missing_from_cubic.txt"]

OUT_HEADER = "output_data/picotype_data_optimized.h"
OUT_FONT = "output_data/picotype_12.font"
OUT_MAP = "output_data/picotype_12.map"
OUT_SOURCES = "output_data/picotype_12.sources.json"

DEFAULT_IME_FROM = "../pico_keyboard_ime_terminal_usb_host/picotype_data_optimized.h"

EXCLUDE_RANGES = [
    (0x0000, 0x001F),                        # C0 控制字元
    (0x007F, 0x009F),                        # DEL 與 C1 控制字元
    (0xE000, 0xF8FF),                        # PUA：各字型的私用圖形，無意義
]
EXCLUDE_CHARS = {0xFE0F, 0x20E3}             # VS-16、keycap：本就不該有字形

FONT_MAP_FORMAT = "<IIBBbbbB"                # 14 bytes
REC_SIZE = struct.calcsize(FONT_MAP_FORMAT)
assert REC_SIZE == 14

MAP_FORMAT_TAG = "1-bit"


def excluded(cp: int) -> bool:
    return cp in EXCLUDE_CHARS or any(lo <= cp <= hi for lo, hi in EXCLUDE_RANGES)


# ==============================================================================
# --- 1bpp 打包 ---
# ==============================================================================
def pack_1bpp(pixels: bytes, w: int, h: int) -> bytes:
    """1 B/px 的 L-mode 資料 → 1bpp row-aligned，LSB-first。"""
    stride = (w + 7) // 8
    out = bytearray(stride * h)
    for y in range(h):
        row, base = y * w, y * stride
        for x in range(w):
            if pixels[row + x] > 128:
                out[base + (x >> 3)] |= 1 << (x & 7)
    return bytes(out)


def unpack_1bpp(data: bytes, w: int, h: int) -> bytes:
    """pack_1bpp 的逆運算，還原成 1 B/px（0x00 / 0xFF）。"""
    stride = (w + 7) // 8
    out = bytearray(w * h)
    for y in range(h):
        base, row = y * stride, y * w
        for x in range(w):
            if data[base + (x >> 3)] >> (x & 7) & 1:
                out[row + x] = 0xFF
    return bytes(out)


# ==============================================================================
# --- 字型層 ---
# ==============================================================================
class Layer:
    def __init__(self, rel_path, size, correction):
        path = os.path.join(REPO_ROOT, rel_path)
        if not os.path.exists(path):
            raise SystemExit(f"錯誤: 找不到字型 {path}")
        tt = TTFont(path, lazy=True)
        self.rel = rel_path
        self.name = tt["name"].getDebugName(1) or os.path.basename(rel_path)
        self.version = tt["name"].getDebugName(5) or "?"
        self.cmap = set(tt.getBestCmap())
        self.size = size
        self.dx = correction.get("dx", 0)
        self.dy = correction.get("dy", 0)
        self.advance = correction.get("advance")
        self.pil = ImageFont.truetype(path, size, index=0)
        self.count = 0

    def render(self, ch):
        """回傳 (raw 1B/px, w, h, x_advance, x_offset, y_offset)，無墨則 None。"""
        try:
            left, top, right, bottom = self.pil.getbbox(ch)
            adv = self.pil.getlength(ch)
        except Exception:
            return None
        w, h = right - left, bottom - top
        if w == 0 or h == 0:
            return None
        img = Image.new("L", (w, h), 0)
        ImageDraw.Draw(img).text((-left, -top), ch, font=self.pil, fill=255)
        return (img.tobytes(), w, h,
                self.advance if self.advance is not None else int(adv),
                left + self.dx, top + self.dy)


def load_targets(layers):
    """收錄範圍 = 主字型 cmap ∪ TARGET_CHARSETS。"""
    targets = set(layers[0].cmap)
    for rel in TARGET_CHARSETS:
        p = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(p):
            print(f"  警告: 找不到 {rel}，略過")
            continue
        txt = open(p, encoding="utf-8").read()
        body = "".join(l for l in txt.splitlines() if not l.startswith("#"))
        targets |= {ord(c) for c in body if not c.isspace()}
    return targets


# ==============================================================================
# --- 建置 ---
# ==============================================================================
def build(layers):
    targets = load_targets(layers)
    records, bitmap, sources = [], bytearray(), {}
    n_excluded = n_missing = 0
    missing_cps = []

    for cp in sorted(targets):
        if excluded(cp):
            n_excluded += 1
            continue
        ch = chr(cp)
        got = None
        for idx, layer in enumerate(layers):
            if cp not in layer.cmap:
                continue            # cmap 查表 —— 治本，不猜 bitmap 特徵
            r = layer.render(ch)
            if r is None:
                continue            # 有 cmap 記錄但無墨（如空白），往下一層
            got = (idx, layer, r)
            break

        if got is None:
            # 空白字元例外：保留可見的前進量
            if ch == " ":
                w, h = layers[0].size // 3, layers[0].size
                raw = bytes(w * h)
                got = (0, layers[0], (raw, w, h, w, 0, 0))
            else:
                n_missing += 1
                missing_cps.append(cp)
                continue

        idx, layer, (raw, w, h, adv, xo, yo) = got
        packed = pack_1bpp(raw, w, h)
        assert unpack_1bpp(packed, w, h) == bytes(
            0xFF if b > 128 else 0 for b in raw), f"round-trip 失敗 U+{cp:04X}"

        records.append({"unicode": cp, "offset": len(bitmap), "width": w,
                        "height": h, "x_advance": adv,
                        "x_offset": xo, "y_offset": yo})
        bitmap.extend(packed)
        sources[cp] = idx
        layer.count += 1

    stats = {
        "targets": len(targets), "kept": len(records),
        "excluded": n_excluded, "missing": n_missing,
        "missing_cps": missing_cps,
        "max_glyph_bytes": max(((r["width"] + 7) // 8) * r["height"]
                               for r in records),
    }
    return records, bytes(bitmap), sources, stats


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
                 layers, max_glyph_bytes):
    ime_rec = struct.calcsize("<HBxHH")
    attrib = "\n".join(
        f"//   [{i}] {l.name} v{l.version} @{l.size}px — {l.count} 字"
        for i, l in enumerate(layers))
    content = f"""// Auto-generated by tools/build_font.py. DO NOT EDIT.
//
// 字型資料為 1 bit/pixel、row-aligned、LSB-first
//   （bit 0 = 該位元組最左邊的 pixel）。
// 每列佔 stride = (width + 7) / 8 個位元組，第 j 列起點為 offset + j * stride。
//
// 字型來源（fallback 鏈，依序查找）:
{attrib}
//
//   全部以 SIL Open Font License 1.1 授權散布。
//   保留字型名稱不適用於本衍生資料；完整授權與 attribution 見 fonts/LICENSES/。

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
# --- 輸出：模擬器 .font / .map / .sources.json ---
# ==============================================================================
def write_simulator(font_out, map_out, src_out, bitmap, records, sources,
                    layers, size, missing_cps):
    with open(font_out, "wb") as f:
        f.write(bitmap)

    doc = {
        "metadata": {
            "font_name": f"picotype_{size}",
            "font_size": size,
            "format": MAP_FORMAT_TAG,
            "chain": [f"{l.name} v{l.version} @{l.size}px" for l in layers],
        },
        "characters": {str(r["unicode"]): [r["offset"], r["width"], r["height"]]
                       for r in records},
    }
    with open(map_out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    # 每個字由哪一層提供。供 font_viewer.py 標示來源，不進韌體。
    with open(src_out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({
            "layers": [{"name": l.name, "version": l.version, "size": l.size,
                        "path": l.rel, "count": l.count} for l in layers],
            "chars": {str(cp): idx for cp, idx in sorted(sources.items())},
            "unavailable": [f"{cp:04X}" for cp in missing_cps],
        }, f, ensure_ascii=False, indent=1)


# ==============================================================================
def main():
    ap = argparse.ArgumentParser(description="PicoType 字型建置（1bpp、fallback 鏈）")
    ap.add_argument("--ime-from", default=DEFAULT_IME_FROM)
    ap.add_argument("--primary-only", action="store_true",
                    help="只用鏈的第一層（第一階段的行為）")
    args = ap.parse_args()

    chain = FONT_CHAIN[:1] if args.primary_only else FONT_CHAIN
    layers = [Layer(*c) for c in chain]

    print("fallback 鏈:")
    for i, l in enumerate(layers):
        corr = []
        if l.dx or l.dy:
            corr.append(f"dx={l.dx:+d} dy={l.dy:+d}")
        if l.advance is not None:
            corr.append(f"advance={l.advance}")
        print(f"  [{i}] {l.name} v{l.version} @{l.size}px"
              f"  cmap {len(l.cmap):,}"
              f"{'  (' + ', '.join(corr) + ')' if corr else ''}")

    records, bitmap, sources, stats = build(layers)
    font_map = pack_map(records)

    print(f"\n收錄範圍 {stats['targets']:,} 字"
          f" → 收錄 {stats['kept']:,}"
          f"（排除 PUA/控制字元 {stats['excluded']}，"
          f"全鏈皆無字形 {stats['missing']}）")
    print("\n各層貢獻:")
    for i, l in enumerate(layers):
        print(f"  [{i}] {l.name:<34} {l.count:>6} 字")
    print(f"\nbitmap {len(bitmap):,} B ({len(bitmap)/1024:.1f} KB)"
          f"   map {len(font_map):,} B ({len(font_map)/1024:.1f} KB)"
          f"   合計 {(len(bitmap)+len(font_map))/1024:.1f} KB")
    print(f"最大字形 {stats['max_glyph_bytes']} B")

    ime_path = os.path.join(REPO_ROOT, args.ime_from)
    if not os.path.exists(ime_path):
        raise SystemExit(f"錯誤: 找不到 IME 來源 header {ime_path}")
    ime_src = open(ime_path, encoding="utf-8").read()
    ime_idx = extract_array(ime_src, "zhuyin_idx_raw_opt")
    ime_pool = extract_array(ime_src, "zhuyin_pool_opt")
    print(f"IME 沿用: idx {len(ime_idx):,} B  pool {len(ime_pool):,} B")

    write_header(os.path.join(REPO_ROOT, OUT_HEADER), font_map, bitmap,
                 len(records), ime_idx, ime_pool, layers,
                 stats["max_glyph_bytes"])
    write_simulator(os.path.join(REPO_ROOT, OUT_FONT),
                    os.path.join(REPO_ROOT, OUT_MAP),
                    os.path.join(REPO_ROOT, OUT_SOURCES),
                    bitmap, records, sources, layers,
                    layers[0].size, stats["missing_cps"])

    hdr = os.path.getsize(os.path.join(REPO_ROOT, OUT_HEADER))
    print(f"\n輸出:")
    print(f"  {OUT_HEADER}  ({hdr/1024/1024:.2f} MB)")
    print(f"  {OUT_FONT}")
    print(f"  {OUT_MAP}")
    print(f"  {OUT_SOURCES}")


if __name__ == "__main__":
    main()
