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

## 第二階段規劃納入（尚未下載）

以下為 fallback 鏈候選，授權皆已確認可用。取得網址見 `HANDOFF.md` §12。

| 字型 | 授權 | 備註 |
|---|---|---|
| Fusion Pixel 12px | OFL 1.1 | 上游多套字型混合，各家皆 OFL 1.1 或相容 |
| UnifontEX | GPL2 + 字型嵌入例外 **及** OFL 1.1（雙授權） | **本專案採 OFL 1.1 那一支**，以維持單一授權模型；作者要求署名 "stgiga" |
| Plangothic P1 | OFL 1.1 | 保留名稱「Plangothic」「遍黑」 |
| Ark Pixel 12px | OFL 1.1 | 備案，大致為 Fusion 的子集 |

## 明確排除

**Zpix（最像素）** —— 專有商業授權，非 OFL。其條款明文禁止
「修改、反編譯、轉換、拆分等反向操作」，而本專案的建置流程（TTF → 點陣圖 →
打包進韌體）正屬於此類操作。商用另需 USD $1,000／單一產品。**不得使用。**
