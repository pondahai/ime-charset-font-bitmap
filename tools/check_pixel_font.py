"""判定字型是否真為某個字級設計的點陣字型。

判準：真正的點陣字型在其設計字級光柵化後，筆畫對齊 pixel grid，
      **只會出現 0 與 255 兩種灰階值**。出現中間值代表反鋸齒介入，
      即該字型並非為此字級設計。

這個判準對本專案是決定性的：資料格式是 1 bit/pixel，若光柵化結果帶灰階，
轉 1bpp 就必須做二值化門檻 —— 那是有損的，且細筆畫會斷裂或消失。

用法:
    python -X utf8 tools/check_pixel_font.py <ttf> <size> [<size> ...]
    python -X utf8 tools/check_pixel_font.py fonts/Cubic_11.ttf 11 12 13
"""
from __future__ import annotations

import sys
from collections import Counter

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

# 取樣用的字：混合筆畫繁簡、標點、拉丁，避免只測到簡單字形
SAMPLE = ("國字體言語漢文永東中一二三十日月山水火木金土"
          "的是不了在有人這上們地大來個到說時要就出會"
          "ABCDEFGHIJKLMNopqrstuvwxyz0123456789,.?!:;()")


def check(path: str, size: int):
    cmap = set(TTFont(path, lazy=True).getBestCmap())
    font = ImageFont.truetype(path, size, index=0)

    hist = Counter()
    heights, widths = Counter(), Counter()
    tested = 0

    for ch in SAMPLE:
        if ord(ch) not in cmap:
            continue
        left, top, right, bottom = font.getbbox(ch)
        w, h = right - left, bottom - top
        if w == 0 or h == 0:
            continue
        img = Image.new("L", (w, h), 0)
        ImageDraw.Draw(img).text((-left, -top), ch, font=font, fill=255)
        hist.update(img.tobytes())
        widths[w] += 1
        heights[h] += 1
        tested += 1

    if not tested:
        print(f"  @{size:<3} 取樣字全部不在 cmap 內，無法判定")
        return

    total = sum(hist.values())
    pure = hist.get(0, 0) + hist.get(255, 0)
    gray = total - pure
    n_values = len(hist)
    ink = total - hist.get(0, 0)

    verdict = "點陣字型（無損可轉 1bpp）" if gray == 0 else \
              f"非此字級設計（{100.0*gray/max(ink,1):.1f}% 的墨水像素是灰階）"

    common_h = heights.most_common(1)[0]
    common_w = widths.most_common(1)[0]
    print(f"  @{size:<3} 灰階值 {n_values:>3} 種   "
          f"典型字框 {common_w[0]}x{common_h[0]}   {verdict}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(1)
    path = sys.argv[1]
    sizes = [int(s) for s in sys.argv[2:]]
    tt = TTFont(path, lazy=True)
    name = tt["name"].getDebugName(1) or "?"
    ver = tt["name"].getDebugName(5) or "?"
    has_bitmap = [t for t in ("EBDT", "EBLC", "CBDT", "CBLC", "bdat", "bloc")
                  if t in tt]
    print(f"{path}")
    print(f"  {name}  v{ver}   cmap {len(tt.getBestCmap())} 字"
          f"   內嵌點陣表: {has_bitmap or '無（outline 字型）'}")
    for s in sizes:
        check(path, s)
    print()


if __name__ == "__main__":
    main()
