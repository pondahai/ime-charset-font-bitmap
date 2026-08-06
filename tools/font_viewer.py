"""字形檢閱器 —— 直接檢視轉換後的點陣字形。

讀取 build_font.py 產出的 .font/.map，也就是**韌體實際會燒進去的同一份資料**，
所以看到的字形就是裝置上會顯示的字形。

四種檢視:

  字表  (Grid)     捲動瀏覽全部字形，可跳至指定碼位或搜尋
  單字  (Detail)   放大檢視單一字形，顯示完整 metric 與位元組
  對照  (Compare)  資料字形 vs 即時以 TTF 光柵化的字形，差異處標紅
  缺字  (Missing)  charsets/missing_from_cubic.txt 內目前畫不出來的字

對照模式是驗證器的視覺化版本：verify_1bpp.py 只告訴你過或不過，
這裡讓你看出**哪一個 pixel** 不一樣。

用法:
    python -X utf8 tools/font_viewer.py
    python -X utf8 tools/font_viewer.py --map output_data/picotype_12.map
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import pygame

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_MAP = "output_data/picotype_12.map"
DEFAULT_FONT_DATA = "output_data/picotype_12.font"
DEFAULT_SOURCES = "output_data/picotype_12.sources.json"
DEFAULT_TTF = "fonts/Cubic_11.ttf"
DEFAULT_MISSING = "charsets/missing_from_cubic.txt"

W, H = 1100, 720
BG = (18, 20, 26)
FG = (226, 228, 232)
DIM = (120, 126, 138)
ACCENT = (96, 196, 255)
INK = (240, 242, 245)
DIFF = (255, 78, 96)
GRID_LINE = (44, 48, 58)
SEL = (60, 120, 190)

# fallback 鏈各層的顏色。第 0 層（主字型）用純白，後續層用可辨識的色調，
# 讓「哪些字是補上來的」在字表裡一眼看得出來。
LAYER_COLORS = [INK, (128, 222, 168), (246, 200, 108), (200, 160, 246)]

CELL = 44          # 字表每格像素
GLYPH_SCALE = 3    # 字表內字形放大倍率
DETAIL_SCALE = 18  # 單字模式放大倍率


# ==============================================================================
# --- 資料存取 ---
# ==============================================================================
class FontData:
    def __init__(self, map_path, font_path, sources_path=None):
        with open(map_path, encoding="utf-8") as f:
            doc = json.load(f)
        self.meta = doc.get("metadata", {})
        self.chars = {int(k): v for k, v in doc.get("characters", {}).items()}
        self.is_1bpp = self.meta.get("format") == "1-bit"
        self.blob = open(font_path, "rb").read()
        self.codepoints = sorted(self.chars)
        # fallback 鏈的來源標記（若有）。純檢閱用，不進韌體。
        self.layers, self.source_of, self.unavailable = [], {}, []
        if sources_path and os.path.exists(sources_path):
            with open(sources_path, encoding="utf-8") as f:
                s = json.load(f)
            self.layers = s.get("layers", [])
            self.source_of = {int(k): v for k, v in s.get("chars", {}).items()}
            self.unavailable = sorted(int(x, 16) for x in s.get("unavailable", []))

    def raw_bytes(self, cp):
        off, w, h = self.chars[cp]
        n = ((w + 7) // 8) * h if self.is_1bpp else w * h
        return self.blob[off:off + n]

    def pixels(self, cp):
        """回傳 (bool matrix [h][w], w, h)。"""
        off, w, h = self.chars[cp]
        if self.is_1bpp:
            stride = (w + 7) // 8
            d = self.blob[off:off + stride * h]
            return ([[bool(d[y * stride + (x >> 3)] >> (x & 7) & 1)
                      for x in range(w)] for y in range(h)], w, h)
        d = self.blob[off:off + w * h]
        return ([[d[y * w + x] > 128 for x in range(w)] for y in range(h)], w, h)


def ttf_pixels(pil_font, ch):
    """即時以 TTF 光柵化，回傳與 FontData.pixels 相同的結構。"""
    from PIL import Image, ImageDraw
    left, top, right, bottom = pil_font.getbbox(ch)
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return None, 0, 0
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).text((-left, -top), ch, font=pil_font, fill=255)
    d = img.tobytes()
    return ([[d[y * w + x] > 128 for x in range(w)] for y in range(h)], w, h)


# ==============================================================================
# --- 繪製 ---
# ==============================================================================
def draw_glyph(surf, mat, w, h, x, y, scale, color=INK):
    if not mat:
        return
    for gy in range(h):
        row = mat[gy]
        for gx in range(w):
            if row[gx]:
                surf.fill(color, (x + gx * scale, y + gy * scale, scale, scale))


def draw_glyph_diff(surf, a, b, w, h, x, y, scale):
    """a = 資料字形, b = TTF 字形。相同畫白，只在其中之一畫紅。"""
    for gy in range(h):
        for gx in range(w):
            va = a[gy][gx] if a and gy < len(a) and gx < len(a[gy]) else False
            vb = b[gy][gx] if b and gy < len(b) and gx < len(b[gy]) else False
            if va and vb:
                surf.fill(INK, (x + gx * scale, y + gy * scale, scale, scale))
            elif va or vb:
                surf.fill(DIFF, (x + gx * scale, y + gy * scale, scale, scale))


class Viewer:
    def __init__(self, data: FontData, pil_font, missing):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("PicoType 字形檢閱器")
        self.data = data
        self.pil = pil_font
        self.missing = missing
        self.mode = "grid"          # grid | detail | compare | missing
        self.layer_filter = None    # None = 全部；否則只看該層提供的字
        self.top_row = 0
        self.sel = 0                # index into current list
        self.search = ""
        self.searching = False
        self.font = self._ui_font(15)
        self.small = self._ui_font(13)
        self.big = self._ui_font(20)
        # 參考字型：只用來顯示「缺字實際長什麼樣」，不參與任何資料產生。
        self.ref = self._ui_font(26)
        self.cols = (W - 320) // CELL

    @staticmethod
    def _ui_font(size):
        for name in ("microsoftjhenghei", "msjh", "notosanstc",
                     "microsoftyahei", "segoeui", None):
            try:
                f = pygame.font.SysFont(name, size) if name else \
                    pygame.font.Font(None, size)
                if f:
                    return f
            except Exception:
                continue
        return pygame.font.Font(None, size)

    def layer_color(self, cp):
        idx = self.data.source_of.get(cp, 0)
        return LAYER_COLORS[idx % len(LAYER_COLORS)]

    def layer_label(self, cp):
        idx = self.data.source_of.get(cp)
        if idx is None or not self.data.layers:
            return None
        l = self.data.layers[idx]
        return f"[{idx}] {l['name']} @{l['size']}px"

    # --- 目前檢視的碼位清單 ---
    def cur_list(self):
        if self.mode == "missing":
            return self.missing
        if self.layer_filter is not None:
            return [cp for cp in self.data.codepoints
                    if self.data.source_of.get(cp, 0) == self.layer_filter]
        return self.data.codepoints

    def text(self, s, x, y, color=FG, font=None):
        self.screen.blit((font or self.font).render(s, True, color), (x, y))

    # ------------------------------------------------------------------ 繪製
    def draw(self):
        self.screen.fill(BG)
        if self.mode in ("grid", "missing"):
            self.draw_grid()
        else:
            self.draw_detail()
        self.draw_status()
        pygame.display.flip()

    def draw_grid(self):
        lst = self.cur_list()
        rows = (H - 90) // CELL
        start = self.top_row * self.cols
        end = min(len(lst), start + rows * self.cols)
        for i in range(start, end):
            cp = lst[i]
            gi = i - start
            cx = 20 + (gi % self.cols) * CELL
            cy = 60 + (gi // self.cols) * CELL
            if i == self.sel:
                self.screen.fill(SEL, (cx - 2, cy - 2, CELL, CELL))
            pygame.draw.rect(self.screen, GRID_LINE,
                             (cx - 2, cy - 2, CELL, CELL), 1)
            if cp in self.data.chars:
                mat, w, h = self.data.pixels(cp)
                draw_glyph(self.screen, mat, w, h, cx, cy, GLYPH_SCALE,
                           self.layer_color(cp))
            else:
                # 缺字：畫韌體會顯示的洋紅方框，並用系統字型把該字淡淡疊上去，
                # 讓人看得出缺的到底是哪個字（韌體上當然沒有這一層）。
                pygame.draw.rect(self.screen, DIFF, (cx + 4, cy + 4,
                                                     CELL - 12, CELL - 12), 1)
                ch = chr(cp)
                if ch.isprintable():   # 控制字元交給 SysFont 會直接拋錯
                    gl = self.ref.render(ch, True, DIM)
                    self.screen.blit(gl, (cx + (CELL - 4 - gl.get_width()) // 2,
                                          cy + (CELL - 4 - gl.get_height()) // 2))
        self.draw_sidebar()

    def draw_sidebar(self):
        lst = self.cur_list()
        if not lst:
            return
        cp = lst[self.sel]
        x = W - 285
        pygame.draw.line(self.screen, GRID_LINE, (x - 20, 50), (x - 20, H - 40))
        self.text(f"U+{cp:04X}", x, 60, ACCENT, self.big)
        if chr(cp).isprintable():
            self.text(chr(cp), x + 130, 56, FG, self.big)
        y = 95
        if cp in self.data.chars:
            off, w, h = self.data.chars[cp]
            mat, _, _ = self.data.pixels(cp)
            draw_glyph(self.screen, mat, w, h, x, y, 10, self.layer_color(cp))
            y += h * 10 + 16
            lab = self.layer_label(cp)
            if lab:
                self.text(lab, x, y, self.layer_color(cp), self.small)
                y += 22
            nbytes = len(self.data.raw_bytes(cp))
            for line in (f"w={w}  h={h}",
                         f"offset=0x{off:X}",
                         f"{nbytes} bytes"
                         f"  (stride {(w+7)//8})" if self.data.is_1bpp
                         else f"{nbytes} bytes"):
                self.text(line, x, y, DIM, self.small)
                y += 18
        else:
            self.text("此字型無此字形", x, y, DIFF, self.small)
            y += 24
            self.text("（第二階段 fallback", x, y, DIM, self.small); y += 18
            self.text("  鏈的目標）", x, y, DIM, self.small)

    def draw_detail(self):
        lst = self.cur_list()
        cp = lst[self.sel]
        ch = chr(cp)
        self.text(f"U+{cp:04X}   {ch}", 30, 55, ACCENT, self.big)

        has = cp in self.data.chars
        if not has:
            self.text("此字型無此字形", 30, 100, DIFF)
            return
        mat, w, h = self.data.pixels(cp)
        off, _, _ = self.data.chars[cp]

        if self.mode == "detail":
            draw_glyph(self.screen, mat, w, h, 30, 100, DETAIL_SCALE)
            # 格線
            for gx in range(w + 1):
                pygame.draw.line(self.screen, GRID_LINE,
                                 (30 + gx * DETAIL_SCALE, 100),
                                 (30 + gx * DETAIL_SCALE, 100 + h * DETAIL_SCALE))
            for gy in range(h + 1):
                pygame.draw.line(self.screen, GRID_LINE,
                                 (30, 100 + gy * DETAIL_SCALE),
                                 (30 + w * DETAIL_SCALE, 100 + gy * DETAIL_SCALE))
            x = 30 + w * DETAIL_SCALE + 40
            y = 100
            raw = self.data.raw_bytes(cp)
            for line in (f"width      {w}",
                         f"height     {h}",
                         f"offset     0x{off:X}  ({off})",
                         f"stride     {(w+7)//8} bytes/列" if self.data.is_1bpp else "",
                         f"資料量      {len(raw)} bytes",
                         f"格式        {self.data.meta.get('format','?')}"):
                if line:
                    self.text(line, x, y, FG, self.small)
                    y += 22
            y += 10
            self.text("原始位元組", x, y, DIM, self.small); y += 20
            stride = (w + 7) // 8 if self.data.is_1bpp else w
            for i in range(0, min(len(raw), stride * 20), stride):
                self.text(" ".join(f"{b:02x}" for b in raw[i:i + stride]),
                          x, y, DIM, self.small)
                y += 16
        else:  # compare
            if self.pil is None:
                self.text("找不到 TTF，無法對照", 30, 100, DIFF)
                return
            tmat, tw, th = ttf_pixels(self.pil, ch)
            self.text("資料", 30, 92, DIM, self.small)
            draw_glyph(self.screen, mat, w, h, 30, 112, 12)
            x2 = 30 + max(w, 14) * 12 + 50
            self.text("TTF 即時光柵化", x2, 92, DIM, self.small)
            draw_glyph(self.screen, tmat, tw, th, x2, 112, 12)
            x3 = x2 + max(tw, 14) * 12 + 50
            same = (w, h) == (tw, th) and mat == tmat
            self.text("差異" if not same else "差異（無）", x3, 92,
                      DIFF if not same else DIM, self.small)
            draw_glyph_diff(self.screen, mat, tmat,
                            max(w, tw), max(h, th), x3, 112, 12)
            y = 112 + max(h, th) * 12 + 30
            if same:
                self.text("逐 pixel 完全相同", 30, y, (120, 220, 140))
            else:
                self.text(f"不一致  資料=({w},{h})  TTF=({tw},{th})", 30, y, DIFF)

    def draw_status(self):
        lst = self.cur_list()
        meta = self.data.meta
        head = (f"{meta.get('font_name','?')} @{meta.get('font_size','?')}px"
                f"   格式 {meta.get('format','?')}"
                f"   {len(self.data.codepoints)} 字")
        self.text(head, 20, 18, DIM, self.small)
        mode_label = {"grid": "字表", "detail": "單字",
                      "compare": "對照", "missing": "缺字"}[self.mode]
        if self.layer_filter is not None and self.mode == "grid":
            mode_label += f" · 僅第 {self.layer_filter} 層"
        pos = f"{self.sel+1}/{len(lst)}" if lst else "0/0"
        self.text(f"[{mode_label}]  {pos}", W - 320, 18,
                  self.layer_color(lst[self.sel]) if lst else ACCENT, self.small)
        # 鏈的組成與各層字數，色塊與字表內的字形同色
        if self.data.layers:
            lx = 20
            for i, l in enumerate(self.data.layers):
                c = LAYER_COLORS[i % len(LAYER_COLORS)]
                self.screen.fill(c, (lx, 40, 8, 8))
                s = f"{l['name']} {l['count']:,}"
                self.text(s, lx + 13, 34, c, self.small)
                lx += 13 + self.small.size(s)[0] + 22
        if self.searching:
            bar = f"跳至: {self.search}_"
            self.text(bar, 20, H - 30, ACCENT, self.small)
        else:
            self.text("方向鍵/PgUp/PgDn 移動   Enter 單字   c 對照   "
                      "m 缺字   f 分層   / 跳至碼位或字   Esc 返回",
                      20, H - 30, DIM, self.small)

    # ------------------------------------------------------------------ 輸入
    def jump(self, q):
        q = q.strip()
        if not q:
            return
        cp = None
        try:
            cp = int(q, 16) if all(c in "0123456789abcdefABCDEF" for c in q) \
                else ord(q[0])
        except ValueError:
            cp = ord(q[0])
        lst = self.cur_list()
        # 找最接近的
        for i, c in enumerate(lst):
            if c >= cp:
                self.sel = i
                break
        else:
            self.sel = max(0, len(lst) - 1)
        self.ensure_visible()

    def ensure_visible(self):
        rows = (H - 90) // CELL
        row = self.sel // self.cols
        if row < self.top_row:
            self.top_row = row
        elif row >= self.top_row + rows:
            self.top_row = row - rows + 1

    def handle(self, e):
        lst = self.cur_list()
        if e.type == pygame.QUIT:
            return False
        if e.type != pygame.KEYDOWN:
            if e.type == pygame.MOUSEWHEEL and self.mode in ("grid", "missing"):
                self.top_row = max(0, self.top_row - e.y)
            return True

        if self.searching:
            if e.key == pygame.K_RETURN:
                self.jump(self.search)
                self.search, self.searching = "", False
            elif e.key == pygame.K_ESCAPE:
                self.search, self.searching = "", False
            elif e.key == pygame.K_BACKSPACE:
                self.search = self.search[:-1]
            elif e.unicode and e.unicode.isprintable():
                self.search += e.unicode
            return True

        k = e.key
        if k == pygame.K_ESCAPE:
            if self.mode in ("detail", "compare"):
                self.mode = "grid" if self.mode == "detail" else "detail"
            else:
                return False
        elif k == pygame.K_SLASH:
            self.searching, self.search = True, ""
        elif k == pygame.K_RETURN:
            self.mode = "detail" if self.mode in ("grid", "missing") else "grid"
        elif k == pygame.K_c:
            self.mode = "compare" if self.mode != "compare" else "grid"
        elif k == pygame.K_m:
            self.mode = "missing" if self.mode != "missing" else "grid"
            self.sel, self.top_row = 0, 0
        elif k == pygame.K_f and self.data.layers:
            # 循環：全部 → 第 0 層 → 第 1 層 → ... → 全部
            n = len(self.data.layers)
            self.layer_filter = 0 if self.layer_filter is None else \
                (None if self.layer_filter + 1 >= n else self.layer_filter + 1)
            self.mode = "grid"
            self.sel, self.top_row = 0, 0
        elif lst:
            step = {pygame.K_LEFT: -1, pygame.K_RIGHT: 1,
                    pygame.K_UP: -self.cols, pygame.K_DOWN: self.cols,
                    pygame.K_PAGEUP: -self.cols * 8,
                    pygame.K_PAGEDOWN: self.cols * 8,
                    pygame.K_HOME: -len(lst), pygame.K_END: len(lst)}.get(k)
            if step:
                self.sel = max(0, min(len(lst) - 1, self.sel + step))
                self.ensure_visible()
        return True

    def run(self):
        clock = pygame.time.Clock()
        while True:
            for e in pygame.event.get():
                if not self.handle(e):
                    pygame.quit()
                    return
            self.draw()
            clock.tick(60)


# ==============================================================================
def main():
    ap = argparse.ArgumentParser(description="PicoType 字形檢閱器")
    ap.add_argument("--map", default=DEFAULT_MAP)
    ap.add_argument("--font-data", default=DEFAULT_FONT_DATA)
    ap.add_argument("--ttf", default=DEFAULT_TTF)
    ap.add_argument("--missing", default=DEFAULT_MISSING)
    args = ap.parse_args()

    p = lambda rel: os.path.join(REPO_ROOT, rel)
    for rel in (args.map, args.font_data):
        if not os.path.exists(p(rel)):
            raise SystemExit(f"錯誤: 找不到 {p(rel)}\n"
                             f"      請先執行 tools/build_font.py")
    data = FontData(p(args.map), p(args.font_data), p(DEFAULT_SOURCES))

    pil = None
    if os.path.exists(p(args.ttf)):
        try:
            from PIL import ImageFont
            pil = ImageFont.truetype(p(args.ttf),
                                     int(data.meta.get("font_size", 12)), index=0)
        except Exception as ex:
            print(f"警告: 無法載入 TTF，對照模式停用（{ex}）")

    # 缺字清單優先取建置結果（實際跑完 fallback 鏈後仍無字形的字），
    # 沒有的話才退回讀 charsets/ 的目標清單。
    missing = data.unavailable
    if not missing and os.path.exists(p(args.missing)):
        txt = open(p(args.missing), encoding="utf-8").read()
        body = "".join(l for l in txt.splitlines() if not l.startswith("#"))
        missing = sorted({ord(c) for c in body if not c.isspace()})

    print(f"載入 {len(data.codepoints)} 字，格式 {data.meta.get('format')}")
    for i, l in enumerate(data.layers):
        print(f"  [{i}] {l['name']} v{l['version']} @{l['size']}px — {l['count']:,} 字")
    print(f"缺字清單 {len(missing)} 字")
    Viewer(data, pil, missing).run()


if __name__ == "__main__":
    main()
