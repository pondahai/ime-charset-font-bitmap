# 字型來源與授權

本 repo 收錄的字型檔，以及由其產生的點陣資料，皆依下列授權散布。
產出的韌體標頭檔（`picotype_data_optimized.h`）檔頭會自動帶上對應的
attribution 註解 —— 那是唯一實際對外散布的成品。

## 目前使用中

### Cubic 11（俐方體十一）

| | |
|---|---|
| 檔案 | `fonts/Cubic_11.ttf` |
| 版本 | **1.430**（`name` ID 5） |
| cmap | 10,250 字 |
| 授權 | SIL Open Font License 1.1 — 見 `Cubic_11-OFL.txt` |
| 來源 | https://github.com/ACh-K/Cubic-11 |

**版本固定的理由**：此版本經逐 pixel 驗證，與現有 `picotype_data_optimized.h`
的 10,914 個字形 100% 相同，確認為當初產生現有資料的那一份。官方目前釋出的是
v1.500，字形已有變動 —— **不要用新版覆蓋**，否則輸出會無聲改變。

**保留名稱（Reserved Font Name）**：「Cubic」「俐方體」。本專案的產出不得以這些
名稱對外呈現為字型名，故輸出檔名採中性命名（`picotype_12.*`）而非 `Cubic_11.*`。

### Fusion Pixel 12px Proportional zh_hant

| | |
|---|---|
| 檔案 | `fonts/fusion-pixel-12px-proportional-zh_hant.ttf` |
| 版本 | **2026.07.20** |
| cmap | 36,518 字 |
| 授權 | SIL Open Font License 1.1 — 見 `Fusion_Pixel-OFL.txt` |
| 來源 | https://github.com/TakWolf/fusion-pixel-font |

fallback 鏈第二層，補 Cubic 11 沒有的字。上游由多套點陣字型混合而成
（Ark Pixel、Misaki、MisekiBitmap、BoutiqueBitmap、**Cubic 11**、Galmuri），
各家皆為 OFL 1.1 或相容授權；其建置程式另為 MIT。

**字級固定為 12**：實測 @11 有 92.9%、@13 有 72.0% 的墨水像素是灰階，
只有 @12 是乾淨的點陣輸出。點陣字型不可離開設計字級縮放，
判定方法見 `tools/check_pixel_font.py`。

選 `zh_hant` 變體：與 `zh_hans` 的 cmap 完全相同（皆 36,518 字），
只差共用碼位的地區字形，取繁體以與 Cubic 11 一致。

## 評估過但未採用

| 字型 | 授權 | 未採用的原因 |
|---|---|---|
| Ark Pixel 12px | OFL 1.1 | 覆蓋率僅差 4 個字，實質是 Fusion 的子集 |
| UnifontEX | GPL2 + 字型嵌入例外 **及** OFL 1.1 | **字級不符** —— 設計字級為 16，@12 有 99.9% 的墨水像素是灰階 |
| Plangothic P1 | OFL 1.1 | **非點陣字型** —— outline 設計，任何字級都無法產生乾淨的 1bpp 輸出 |

授權都沒有問題，是設計字級這一關過不了。剔除這兩套的代價是約 499 個
Ext A/B/C-F 罕用字永久缺字 —— 那些字在 12×12 內本來也畫不清楚。

## 明確排除

**Zpix（最像素）** —— 專有商業授權，非 OFL。其條款明文禁止
「修改、反編譯、轉換、拆分等反向操作」，而本專案的建置流程（TTF → 點陣圖 →
打包進韌體）正屬於此類操作。商用另需 USD $1,000／單一產品。**不得使用。**
