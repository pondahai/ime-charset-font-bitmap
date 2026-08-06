# 字型管線分析與改造交接文件

這份文件是一次遠端分析 session 的完整結論，供後續（特別是本機）接手時直接使用。
所有數字都是實測，不是估算——每一項都註明了測法。

分析基準：

- `ime-charset-font-bitmap` @ `cc11909`
- `pico_keyboard_ime_terminal_usb_host` @ 預設分支
- `pico_keyboard_ime_terminal` @ 預設分支

---

## 1. 一句話結論

現有字型資料是 1 byte/pixel，但整份資料只有 `0x00` 和 `0xFF` 兩種值；改成 1 bit/pixel
是無損的，可把 1,420 KB 壓到 345 KB。同時，資料裡有 3,119 個字其實是字型的
`.notdef` 佔位圖，可以用「多字型 fallback 鏈」補成真字形，代價只有 39 KB。

兩件事都應該在源頭（本 repo 的轉換器）修，而不是在下游 repack。

---

## 2. 源頭 repo 現在跑不起來（最高優先）

`git ls-files` 只有 10 個檔案：

```
README.md
main.py
output_data/Cubic_11.ttf_12.font
output_data/Cubic_11.ttf_12.map
output_data/readme.md
output_data/zhuyin.dat
output_data/zhuyin.idx
tools/README.md
tools/charset_extractor.py
tools/full_hardcode_converter.py
```

`tools/full_hardcode_converter.py` 需要 `../fonts/`、`../charsets/`、`../ime_data/`，
**三個目錄都不在 repo 裡**，也沒有 `.gitignore`——單純沒有 commit 進去。

因此任何「重跑光柵化」的工作都被這件事擋住。第一步一定是把這三個目錄補進 repo
（或改成下載腳本 + `.gitignore`）。

需要補的檔案，由 `tools/charset_extractor.py` 和 `tools/full_hardcode_converter.py`
的設定反推：

| 路徑 | 用途 |
|---|---|
| `fonts/Cubic_11.ttf` | 主字型 |
| `ime_data/BPMFBase.txt` | 注音碼表（字→注音） |
| `ime_data/BPMFPunctuations.txt` | 標點碼表 |
| `ime_data/通用规范汉字表(2013)全部(8105字).txt` | 字元集來源 |
| `ime_data/字頻表.txt` | 字元集來源 |
| `charsets/chars_from_tcfreq_sc.txt` | extractor 的產出，converter 的輸入 |

> **Cubic 11 版本警告**：官方目前 release 是 v1.500。若用新版重跑，現有 7,430 個
> 字的字形會跟著改變。要維持輸出穩定，必須使用當初產生現有資料的那一份 TTF。

---

## 3. 現有資料的實測數據

兩個 pico repo 的 `picotype_data_optimized.h` **md5 完全相同**
（`5cb3a48ee3e5665f284d39e92012ab43`），路徑分別是根目錄與 `software/`。

| 符號 | 大小 |
|---|---|
| `font_map_raw_opt` | 152,810 B（10,915 筆 × 14 B） |
| `font_bitmap_data_opt` | 1,301,582 B |
| `zhuyin_idx_raw_opt` | 10,880 B |
| `zhuyin_pool_opt` | 53,983 B |

字型部分關鍵事實：

- bitmap 內**只有兩種位元組值**：`0x00`、`0xFF` → 轉 1bpp 無損
- 最大字框 13×13；字框分佈：13×11 有 7,430 個、13×5 有 3,123 個、13×10 有 134 個
- 每列所需位元組：2 bytes 的有 10,811 個字，1 byte 的有 104 個
- Cubic 11 的 13×11 字：`x_offset=0`、`y_offset=1`（7,426 個），另有 4 個 `y_offset=0`
- codepoint > 0xFFFF 的有 247 個 → **`unicode` 欄位不能縮成 uint16**
- `FontMapRecord_Opt` 實際是 **14 bytes**，但結構註解寫「to make it 16 bytes」，註解是錯的

轉 1bpp 後的大小（實算，非估算）：

| 打包方式 | 大小 |
|---|---|
| row-aligned（每列補滿位元組） | 200,267 B = 195.6 KB |
| tight bitstream（不對齊） | 166,534 B = 162.6 KB |

**建議採 row-aligned**：只多 33 KB，但解碼變成單純的 `base + row*stride`，
不需要跨位元組的位移運算。

去重無效：7,796 個非 notdef 字裡有 7,790 個 bitmap 互異，只有 6 個重複。

---

## 4. notdef 的成因（3,119 個）

### 是什麼

FreeType 的 glyph 0（`.notdef`）。當 Cubic 11 沒有某個字時，PIL 回傳 `.notdef`，
而 Cubic 11 的 `.notdef` 是一個 2×2 的點：

```
U+20E3  w=13 h=5 x_advance=13 x_offset=0 y_offset=5
 |.....##......|
 |.....##......|
 |.............|
 |.............|
 |.............|
```

3,119 筆的 **bitmap 完全相同（unique = 1）**，metrics 也完全相同。
等於同一張圖被存了 3,119 次，加上各自 14 B 的索引，約 80 KB 用來表達「這個字沒有」。

### 為什麼會混進來

`convert_font_optimized()` 唯一的過濾條件是：

```python
if glyph_width == 0 or glyph_height == 0:
```

`.notdef` 的 bbox 是 13×5，寬高都不為 0，**所以通過檢查被當成正常字存起來**。
整條管線沒有任何「字型到底有沒有這個字」的判斷。

### 正確的修法

在源頭用 cmap 查表，而不是事後靠 bitmap 特徵猜：

```python
from fontTools.ttLib import TTFont
cmap = set(TTFont(path, lazy=True).getBestCmap())
if ord(ch) not in cmap:
    ...  # 換下一套字型
```

> **若不得不在下游用特徵比對**（例如 repack 現有 header 而拿不到 TTF），
> 判斷條件必須是完整簽章：`size == (13,5) and ink == 4 and bbox == (2,2) and origin == (5,0)`。
> **不可以只看亮點數量**——`'` 和 `;` 也剛好是 4 個亮點，會被誤刪。
> 另外有 4 個真字也是 13×5：`。`、`︷`、`＝`、`～`，同樣會被亮點數誤傷。

### 這 3,119 個字是誰

| 區塊 | 數量 |
|---|---|
| CJK 基本區 (U+4E00–U+9FFF) | 2,583 |
| Ext C–F | 160 |
| Ext A | 74 |
| Ext B | 36 |
| 符號類（羅馬數字、圈圈數字、框線、✓✗、℉ 等） | 266 |

---

## 5. 字型 fallback 鏈（實測覆蓋率）

### 候選字型單獨表現

對那 3,119 個字做 cmap 比對的結果：

| 字型 | cmap 大小 | 補到 | 備註 |
|---|---|---|---|
| Zpix 最像素 @12 | 22,235 | 2,673 (85.7%) | **授權有限制，不可用** |
| Fusion Pixel 12px @12 | 36,518 | 2,598 (83.3%) | OFL 1.1（release zip 內附 OFL.txt） |
| Ark Pixel 12px @12 | 24,433 | 2,594 (83.2%) | OFL 1.1，大致是 Fusion 的子集 |
| UnifontEX @16 | 65,436 | 2,894 (92.8%) | Ext A 全中、基本區全中、Ext B/C-F 全無 |
| Plangothic P1 @16 | 65,440 | 233 (7.5%) | **Ext B 36/36、Ext C-F 160/160 全中** |
| Plangothic P2 @16 | 42,152 | 3 (0.1%) | 不值得納入 |

### 建議的鏈（已排除 Zpix）

```
1. Cubic_11.ttf                                   @12  （主字型，維持現有外觀）
2. fusion-pixel-12px-proportional-zh_hant.ttf     @12  （dx=+1, dy=-2, advance=13）
3. UnifontExMono.ttf                              @16
4. PlangothicP1-Regular.ttf                       @16
```

**實測結果：3,090 / 3,119（99.1%）**，放棄的 29 個全部是 PUA 私用區碼位。

來源分佈：

| 區塊 | Fusion | UnifontEX | Plangothic | 放棄 |
|---|---|---|---|---|
| CJK 基本區 2,583 | 2,308 | 275 | — | 0 |
| 符號類 266 | 189 | 48 | — | 29 (PUA) |
| Ext A 74 | 23 | 51 | — | 0 |
| Ext B 36 | 11 | — | 25 | 0 |
| Ext C-F 160 | 60 | — | 100 | 0 |
| **合計** | **2,591** | **374** | **125** | **29** |

### 兩個必須遵守的實作規則

**(1) PUA 必須排除在 fallback 鏈之外。**
Fusion Pixel 在 U+E110 有自己的私用區字形（28 px 寬）。若不排除，那些 PUA 碼位
會被畫成某套字型自己的圖示，是無意義的亂碼。過濾範圍 `U+E000–U+F8FF`。

**(2) 點陣字型絕不可離開設計字級。**
實測 Fusion @13：高度從 11 變 12，筆畫被拉扯到結構跑掉（「言」的橫劃數量都變了）。
實測 UnifontEX @12：整條筆畫消失（`㙘` 缺一半）。
對齊只能用「原生字級 + 位移校正」，不能用縮放。

### Fusion 的 metric 校正參數怎麼來的

拿現有 header 裡真正的 Cubic 資料，跟 Fusion 光柵化結果逐 pixel 比對：

```
Cubic 11「國」(現有資料)        Fusion Pixel @12
   .###########.                 ###########.
   .#.....#.#.#.                 #.....#.#.#.
   .###########.                 ###########.
   .#.....#...#.                 #.....#...#.
   w=13 h=11 x_off=0 y_off=1     w=12 h=11 x_off=0 y_off=3  adv=12
```

字身完全一致，只差位置。故校正值為 **`dx=+1, dy=-2, advance=13`**。

UnifontEX / Plangothic 用 16×16，不需校正（見下節）。

---

## 6. 為什麼 16×16 的字放得進現有版面

兩個 pico repo 的排版常數（`.ino` 內，兩邊相同）：

```c
const int FONT_HEIGHT  = 16;   // 字格高度
const int PADDING      = 4;
const int LINE_SPACING = 4;    // → 每行 20 px
```

字格本來就是 16 px 高，現有字只是 11 px 高、靠 `y_offset` 定位。所以 UnifontEX /
Plangothic 的 16×16 字形剛好填滿字格，**不需要改任何佈局常數**。

`FontMapRecord_Opt` 本來就逐字儲存 `width/height/x_advance/x_offset/y_offset`，
所以混用不同尺寸的來源**不需要改資料格式**。

fallback 鏈的最大字框實測 **17×16**（7 個 Plangothic 的 Ext B/C-F 字），
1bpp 需要 48 B，現有 `MAX_CHAR_BUFFER_SIZE = 256` 綽綽有餘。

---

## 7. 各方案的 flash 用量（實算）

| 方案 | bitmap | map | 合計 |
|---|---|---|---|
| 現況（1 B/px） | 1,271.1 KB | 149.2 KB | **1,420.3 KB** |
| A：純 1bpp，字元集不變 | 195.6 KB | 149.2 KB | **344.8 KB** |
| D2：1bpp + 三層 fallback 補字 | 235.1 KB | 148.8 KB | **383.9 KB** |

D2 相對 A 多 **39.1 KB**，換到 3,090 個真字形。相對現況省下 1,036 KB。

IME 資料（idx 10,880 + pool 53,983 = 63.3 KB）不受影響。

附帶效益：`picotype_data_optimized.h` 原始碼從 9.5 MB 降到約 1.6 MB，編譯時間明顯縮短。

### 延伸選項：把 CJK 基本區補滿

現在 charset 只收了 CJK 基本區 20,992 字中的 9,975 個，**剩 11,017 個收到訊息就是
空框**——這與 notdef 無關，是 charset 涵蓋範圍的問題。

實測：Fusion 可提供其中 9,512 個，UnifontEX 可提供全部 11,017 個，
用 Fusion→UnifontEX 的順序全補需要 **+401.1 KB**（bitmap 250.5 + map 150.6），
總計約 785 KB。相對現況 1,420 KB 仍然是省的。

這是獨立決策，不影響 A 或 D2。

---

## 8. 下游需要配合的改動

### 8.1 兩個 pico repo

`class FontRenderer` 在兩個 repo **逐字元完全相同**（96 行），一份 patch 兩邊都能套：

| repo | 檔案 | `drawChar` 行號 |
|---|---|---|
| `pico_keyboard_ime_terminal_usb_host` | `pico_keyboard_ime_terminal_usb_host.ino` | 285 |
| `pico_keyboard_ime_terminal` | `software/pico_keyboard_ime_terminal.ino` | 213 |

bitmap 的唯一消費點就是 `drawChar()`（已 grep 確認全檔無其他引用）：

```c
size_t buffer_size = (size_t)w * h;                       // → ((w + 7) / 8) * h
memcpy_P(bitmap_buffer, font_bitmap_data_opt + offset, buffer_size);
...
if (bitmap_buffer[j * w + i] > 128) _tft.writePixel(...); // → 改成位元測試
```

建議的位元順序：**bit 0 = 該位元組最左邊的 pixel（LSB-first）**，
與 `rp2040-ili9341-infones/software/tools/make_cjk_font.py` 的慣例一致。

**防呆**：符號改名（例如 `font_bitmap_data_1bpp`）並加 `#define PICOTYPE_FONT_BPP 1`。
這樣舊 header 配新 renderer 會編譯失敗，而不是畫出一片雪花。

**缺字前進量**：`findChar()` 回傳 nullptr 時目前前進 `FONT_HEIGHT / 2` = 8，
但全形字應該是 13。`drawString()` 和 `getStringWidth()` 兩處都要改，
否則兩者算出的寬度會不一致。（只要有字最終落到「無字形」路徑就會遇到。）

`MAX_CHAR_BUFFER_SIZE` 可從 256 降到 64（實測最大需求 48 B）。

### 8.2 模擬器 `main.py`

`FontRenderer.get_char_surface()` 目前逐位元組讀 alpha，需改為位元解碼。
`.map` 的 `metadata.format` 目前是 `"1-byte-grayscale"`，應一併更新為 `"1-bit"`
並讓解碼端據此判斷。

---

## 9. output_data 不同步的根因

**repo 裡根本沒有 `output_data/*.font` / `*.map` 的生成器。** 只有產 `.h` 的
`full_hardcode_converter.py`。那兩個檔是某個沒進版控的舊腳本產的。

實測差異（`output_data/Cubic_11.ttf_12.map` vs header）：

| | 字數 |
|---|---|
| `output_data` 收錄 | 13,798 |
| header 收錄 | 10,915 |
| header 有、`output_data` 沒有 | 2,963 |
| `output_data` 有、header 沒有 | 5,846 |

兩邊是用**不同 charset** 建的，不是單純版本落後。

**修法**：改成單一資料模型、雙輸出——同一次建置同時產生 `.h`（韌體）與
`.font`/`.map`（模擬器），不同步的問題從結構上消失。

---

## 10. PUA 污染的來源

`tools/charset_extractor.py` 的三個輸入：

```python
"../ime_data/BPMFPunctuations.txt"
"../ime_data/通用规范汉字表(2013)全部(8105字).txt"
"../ime_data/字頻表.txt"
```

那 29 個 PUA 碼位（U+E07F、U+E1D6、U+E69B、U+E80C、U+E837、U+E83C、U+E918、
U+E988、U+EA52、U+EACB、U+F6DE 等）幾乎確定來自「字頻表」——那類表常含有從
特定字型剪貼的私用碼位。

**應在 extractor 就過濾掉**，而不是等到轉換階段。順便也該過濾
`U+FE0F`（VS-16）與 `U+20E3`（keycap 組字元）這類零寬控制字元——它們本來就不該有字形。

---

## 11. 目標架構

```
tools/
  charset_extractor.py   →  charsets/*.txt              (+ PUA / 控制字元過濾)
  build_font.py          →  單一 glyph 資料模型
                              ├→ picotype_data_optimized.h   (韌體，1bpp)
                              └→ output_data/*.font + *.map  (模擬器，1bpp)
```

`build_font.py` 相對現有 `full_hardcode_converter.py` 的四項改動：

1. cmap 查表決定用哪套字型（治本解決 notdef）
2. fallback 鏈，每層帶自己的光柵尺寸與 metric 校正
3. 1bpp row-aligned 輸出
4. PUA / 控制字元排除

設定大致長這樣：

```python
FONT_CHAIN = [
    ("fonts/Cubic_11.ttf",                               12, {}),
    ("fonts/fusion-pixel-12px-proportional-zh_hant.ttf", 12, dict(dx=+1, dy=-2, advance=13)),
    ("fonts/UnifontExMono.ttf",                          16, {}),
    ("fonts/PlangothicP1-Regular.ttf",                   16, {}),
]
EXCLUDE_RANGES = [(0xE000, 0xF8FF)]      # PUA
EXCLUDE_CHARS  = {0xFE0F, 0x20E3}        # 零寬控制字元
```

---

## 12. 字型取得網址（實測可用）

這些是在遠端容器裡實際下載成功的網址。GitHub release 的資產檔名不好猜，
以下是驗證過的完整路徑：

```
Fusion Pixel 12px（OFL 1.1，zip 內附 OFL.txt）
https://github.com/TakWolf/fusion-pixel-font/releases/download/2026.07.20/fusion-pixel-font-12px-proportional-ttf-v2026.07.20.zip
  → fusion-pixel-12px-proportional-zh_hant.ttf

Ark Pixel 12px（OFL 1.1，備案）
https://github.com/TakWolf/ark-pixel-font/releases/download/2026.07.20/ark-pixel-font-12px-proportional-ttf-v2026.07.20.zip

UnifontEX（授權待確認，衍生自 GNU Unifont）
https://github.com/stgiga/UnifontEX/releases/download/16/UnifontExMono.ttf

Plangothic（授權待確認，專案宣稱 OFL）
https://github.com/Fitzgerald-Porthmouth-Koenigsegg/Plangothic-Project/releases/download/V2.9.5795/Plangothic-Static-V2.9.5795.zip
  → PlangothicP1-Regular.ttf
```

在該容器中 `unifoundry.com` 與 `cdn.jsdelivr.net` 被 proxy 擋（403），本機應該沒這問題。

---

## 13. 待辦與待決事項

### 前置（擋住所有後續工作）

- [ ] 把 `fonts/`、`ime_data/`、`charsets/` commit 進 repo
- [ ] 確認並固定 `Cubic_11.ttf` 的版本（不要用 v1.500 覆蓋舊版）

### 待你決定

- [ ] **UnifontEX 與 Plangothic 的授權**要先確認過再納入。
      若兩者都不能用，Fusion 單獨仍補 2,591 個（83%），Ext B/C-F 放棄、畫洋紅方框。
- [ ] 要不要順便把 CJK 基本區補滿（+401 KB）
- [ ] notdef 補字要不要跟 1bpp 一起做，還是分兩階段

### 實作

- [ ] `charset_extractor.py`：加 PUA / 控制字元過濾
- [ ] `build_font.py`：cmap 判斷 + fallback 鏈 + 1bpp + 雙輸出
- [ ] `main.py`：1bpp 解碼、`metadata.format` 更新
- [ ] 兩個 pico repo：`drawChar()` 位元解碼、符號改名防呆、缺字前進量 8→13、
      `MAX_CHAR_BUFFER_SIZE` 256→64
- [ ] 上機驗證：中英混排、注音候選列、節點列表、缺字方框

### 已知不可解

- 29 個 PUA 碼位無法補（依定義沒有標準字形，應從 charset 移除）
- 極高筆畫的 Ext B 字（如 `𪚥`，龍×4，64 劃）在 16×16 內必然糊成一團。
  這是像素預算的物理限制，不是字型選擇問題。
