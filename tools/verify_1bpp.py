"""驗證 build_font.py 的 1bpp 產出。

三項檢查，任何一項失敗即以非零碼結束：

1. **round-trip** —— 把 .h 內的 1bpp 資料解碼回 1 B/px，與字型重新光柵化的
   結果逐 byte 比對。這證明位元打包與解碼互為逆運算，且解碼端對 stride、
   位元順序的認知與產生端一致。

2. **與舊資料一致** —— 對新舊資料都收錄的字，比對字形與 metric。
   舊資料是 1 B/px，只有 0x00/0xFF，可直接二值化後比較。
   這證明改造沒有動到任何既有字形。

3. **無 notdef 殘留** —— 新資料不應含有任何 .notdef 字形。以 cmap 為準
   （不靠 bitmap 特徵猜測，見 HANDOFF §4）。

用法:
    python -X utf8 tools/verify_1bpp.py
    python -X utf8 tools/verify_1bpp.py --old <舊的 picotype_data_optimized.h>
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import sys

import json

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_font import (unpack_1bpp, REC_SIZE, FONT_MAP_FORMAT,  # noqa: E402
                        FONT_CHAIN, Layer)

NEW_HEADER = "output_data/picotype_data_optimized.h"
NEW_SOURCES = "output_data/picotype_12.sources.json"
DEFAULT_OLD = "../pico_keyboard_ime_terminal_usb_host/picotype_data_optimized.h"
PRIMARY = FONT_CHAIN[0][0]
SIZE = FONT_CHAIN[0][1]


def read_array(src: str, name: str) -> bytes:
    m = re.search(r"const uint8_t " + name + r"\[(\d+)\] PROGMEM = \{(.*?)\n\};",
                  src, re.S)
    if not m:
        return b""
    return bytes(int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", m.group(2)))


def read_records(data: bytes):
    return [dict(zip(("unicode", "offset", "width", "height",
                      "x_advance", "x_offset", "y_offset", "pad"),
                     struct.unpack(FONT_MAP_FORMAT, data[i:i + REC_SIZE])))
            for i in range(0, len(data), REC_SIZE)]


def fail(msg):
    print(f"  FAIL  {msg}")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default=DEFAULT_OLD)
    args = ap.parse_args()

    new_path = os.path.join(REPO_ROOT, NEW_HEADER)
    if not os.path.exists(new_path):
        raise SystemExit(f"錯誤: 找不到 {new_path}，請先執行 tools/build_font.py")
    new_src = open(new_path, encoding="utf-8").read()

    new_map = read_records(read_array(new_src, "font_map_raw_opt"))
    new_bmp = read_array(new_src, "font_bitmap_data_1bpp")
    if not new_bmp:
        raise SystemExit("錯誤: 新 header 內找不到 font_bitmap_data_1bpp")

    layers = [Layer(*c) for c in FONT_CHAIN]
    primary_cmap = layers[0].cmap
    all_cmap = set().union(*(l.cmap for l in layers))

    src_path = os.path.join(REPO_ROOT, NEW_SOURCES)
    if not os.path.exists(src_path):
        raise SystemExit(f"錯誤: 找不到 {src_path}，請先執行 tools/build_font.py")
    src_doc = json.load(open(src_path, encoding="utf-8"))
    src_of = {int(k): v for k, v in src_doc["chars"].items()}

    print(f"新資料: {len(new_map)} 字, bitmap {len(new_bmp):,} B")
    print("鏈: " + " → ".join(f"{l.name} @{l.size}px" for l in layers) + "\n")
    errors = 0

    # --- 1. round-trip -----------------------------------------------------
    print("[1/3] round-trip：1bpp 解碼 vs 產生它的那一層重新光柵化")
    checked = 0
    for r in new_map:
        cp = r["unicode"]
        ch = chr(cp)
        w, h = r["width"], r["height"]
        stride = (w + 7) // 8
        packed = new_bmp[r["offset"]:r["offset"] + stride * h]
        if len(packed) != stride * h:
            errors += fail(f"U+{cp:04X} bitmap 長度不足")
            continue
        decoded = unpack_1bpp(packed, w, h)

        if ch == " ":
            expect = bytes(w * h)          # 空白字元無墨
        else:
            if cp not in src_of:
                errors += fail(f"U+{cp:04X} 缺少來源標記")
                continue
            layer = layers[src_of[cp]]
            out = layer.render(ch)
            if out is None:
                errors += fail(f"U+{cp:04X} 標記的來源層畫不出此字")
                continue
            raw, rw, rh, adv, xo, yo = out
            if (rw, rh) != (w, h):
                errors += fail(f"U+{cp:04X} 字框不符 "
                               f"header=({w},{h}) 重繪=({rw},{rh})")
                continue
            if (adv, xo, yo) != (r["x_advance"], r["x_offset"], r["y_offset"]):
                errors += fail(f"U+{cp:04X} metric 不符（校正值未正確套用？）")
                continue
            expect = bytes(0xFF if b > 128 else 0x00 for b in raw)
        if decoded != expect:
            errors += fail(f"U+{cp:04X} {ch!r} 字形不符")
            continue
        checked += 1
    print(f"      {checked}/{len(new_map)} 通過")

    # --- 2. 與舊資料一致 ---------------------------------------------------
    old_path = os.path.join(REPO_ROOT, args.old)
    print(f"\n[2/3] 與舊資料比對：{os.path.basename(old_path)}")
    if not os.path.exists(old_path):
        print(f"      SKIP  找不到 {old_path}")
    else:
        old_src = open(old_path, encoding="utf-8").read()
        old_map = read_records(read_array(old_src, "font_map_raw_opt"))
        # 基準檔可能是舊的 1 B/px 版，也可能是先前的 1bpp 版 —— 自動判斷。
        old_bmp = read_array(old_src, "font_bitmap_data_opt")
        old_is_1bpp = False
        if not old_bmp:
            old_bmp = read_array(old_src, "font_bitmap_data_1bpp")
            old_is_1bpp = True
        if not old_bmp:
            raise SystemExit(f"錯誤: 基準檔 {old_path} 內找不到字型 bitmap 陣列")
        print(f"      基準格式: {'1bpp' if old_is_1bpp else '1 B/px'}"
              f"，{len(old_map)} 字")
        old_by_cp = {r["unicode"]: r for r in old_map}
        new_by_cp = {r["unicode"]: r for r in new_map}

        # 只比對「由主字型提供」的字。由 fallback 層提供的字在舊資料中是
        # .notdef 佔位圖，本來就應該不同 —— 那正是這次改造的目的。
        shared = sorted(cp for cp in set(old_by_cp) & set(new_by_cp)
                        if src_of.get(cp) == 0)
        replaced = sorted(cp for cp in set(old_by_cp) & set(new_by_cp)
                          if src_of.get(cp, 0) != 0)
        same = 0
        for cp in shared:
            o, n = old_by_cp[cp], new_by_cp[cp]
            if (o["width"], o["height"], o["x_advance"], o["x_offset"],
                    o["y_offset"]) != (n["width"], n["height"], n["x_advance"],
                                       n["x_offset"], n["y_offset"]):
                errors += fail(f"U+{cp:04X} metric 改變了")
                continue
            w, h = n["width"], n["height"]
            if old_is_1bpp:
                ostride = (w + 7) // 8
                old_bin = unpack_1bpp(
                    old_bmp[o["offset"]:o["offset"] + ostride * h], w, h)
            else:
                old_pixels = old_bmp[o["offset"]:o["offset"] + w * h]
                old_bin = bytes(0xFF if b > 128 else 0x00 for b in old_pixels)
            stride = (w + 7) // 8
            new_bin = unpack_1bpp(
                new_bmp[n["offset"]:n["offset"] + stride * h], w, h)
            if old_bin != new_bin:
                errors += fail(f"U+{cp:04X} 字形改變了")
                continue
            same += 1
        dropped = sorted(set(old_by_cp) - set(new_by_cp))
        added = sorted(set(new_by_cp) - set(old_by_cp))
        print(f"      主字型提供的共有字 {len(shared)}，{same} 字完全相同")
        print(f"      由 fallback 取代的 {len(replaced)} 字"
              f"（舊資料為 notdef，現為真字形）")
        print(f"      新資料移除 {len(dropped)} 字（全鏈皆無字形）")
        print(f"      新資料新增 {len(added)} 字")
        leaked = [cp for cp in dropped if cp in primary_cmap]
        if leaked:
            errors += fail(f"移除了 {len(leaked)} 個主字型實際有字形的字："
                           f"{[hex(c) for c in leaked[:10]]}")

    # --- 3. 無 notdef 殘留 -------------------------------------------------
    print("\n[3/3] notdef 殘留檢查（以各層 cmap 為準）")
    notdef = [r["unicode"] for r in new_map
              if r["unicode"] not in all_cmap and chr(r["unicode"]) != " "]
    if notdef:
        errors += fail(f"{len(notdef)} 個字不在任何一層的 cmap 內: "
                       f"{[hex(c) for c in notdef[:10]]}")
    else:
        print(f"      0 個 —— 收錄的 {len(new_map)} 字都由宣告的來源層提供")
    wrong = [cp for cp, idx in src_of.items() if cp not in layers[idx].cmap]
    if wrong:
        errors += fail(f"{len(wrong)} 個字的來源標記與該層 cmap 不符")

    print()
    if errors:
        print(f"驗證失敗：{errors} 項錯誤")
        return 1
    print("驗證全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
