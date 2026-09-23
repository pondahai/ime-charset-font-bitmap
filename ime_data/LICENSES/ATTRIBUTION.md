# 輸入法與字元來源資料的出處與授權

與 `fonts/LICENSES/ATTRIBUTION.md` 對應 —— 那份管字形,這份管碼表與字表。

`ime_data/` 內的來源檔決定了兩件事:**能打出什麼**(注音碼表)與
**想顯示什麼**(字表)。兩者都會進入最終產出 `picotype_data_optimized.h`,
因此其授權必須隨著衍生資料一路散布到下游韌體。

---

## 1. 注音碼表 — McBopomofo(小麥注音輸入法)

| | |
|---|---|
| 上游 | https://github.com/openvanilla/McBopomofo |
| 授權 | MIT License(全文見 `McBopomofo-MIT.txt`) |
| 著作權 | Copyright (c) 2011-2026 Mengjuei Hsieh et al. |

### 使用的檔案

| 檔案 | 內容 | 上游是否另有出處 |
|---|---|---|
| `BPMFBase.txt` | 單字注音對應 | **無** —— 適用 McBopomofo 的 MIT |
| `BPMFPunctuations.txt` | 標點符號對應 | **無** —— 適用 McBopomofo 的 MIT |

### 未使用的檔案,以及為什麼要寫明

`BPMFMappings.txt`(2–6 字的多字詞庫)**未被使用**。

這點必須寫明,因為它的授權狀況與上面兩個不同。McBopomofo 的
`Source/Data/README.md` 對該檔案註明:

> Originally simplified from tsi.src of libtabe (BSD Licensed) with modifications

也就是說,**McBopomofo 的資料目錄內,只有多字詞庫帶著 libtabe 的 BSD 血統**。

本專案的輸入法是單字候選(注音 → 候選字),不是詞庫(注音 → 候選詞),
所以從未取用 `BPMFMappings.txt`。因此:

- 不涉及 libtabe
- 無 BSD 條款需要額外遵循
- 碼表側的授權義務僅為 **MIT 的姓名標示**

若將來要加入「詞」的候選功能,這個結論就會改變 —— 屆時必須重新檢視
`BPMFMappings.txt` 的 BSD 條款。

### 資料在產出中的形式

原始碼表為文字格式,經 `full_hardcode_converter.py` 轉換為
「索引 + 資料池」的二進位結構,在 `picotype_data_optimized.h` 內成為:

| 陣列 | 內容 |
|---|---|
| `zhuyin_idx_raw_opt[]` | 注音查詢鍵索引(8 B/筆,已排序) |
| `zhuyin_pool_opt[]` | 查詢鍵與候選字字串的資料池 |

這是格式轉換,內容仍為 McBopomofo 的衍生著作。

> ⚠️ 依 §4.3,目前的 `build_font.py` **不重建** IME 資料,
> 而是以 `--ime-from` 從既有標頭檔原樣沿用這兩個陣列。
> 所以即使建置流程改版,這份出處聲明依然適用。

---

## 2. 字表來源

這些檔案構成「收錄範圍」三方聯集中的「字表」那一支(見 README §8)。
它們是**字元清單**,不是程式碼。

| 檔案 | 性質 | 出處 |
|---|---|---|
| `通用规范汉字表(2013)全部(8105字).txt` | 中國大陸 2013 年公布的國家規範字表 | 政府公布的規範性文件,內容為事實性字表 |
| `字頻表.txt` | 依字頻排序的繁體字清單 | **出處未確認** —— 見下方 |

### 關於 `字頻表.txt`

這份檔案是一列以換行分隔的繁體漢字,依使用頻率排序,無檔頭、無出處註記。
從內容判斷(收錄「臺」「灣」且為繁體)應為臺灣來源的字頻統計,
常見的候選是中研院平衡語料庫或教育部相關字頻報告,但**無法從檔案本身確認**。

現況評估:

- 它在管線中的角色是「排序過的字元清單」,屬於事實性彙編
- 最終產出**不含**這份檔案本身,只用它決定哪些 Unicode 碼位要收錄
- 因此散布風險低,但**出處仍應補上**

若您知道原始出處,請更新本節。

---

## 3. 下游應該怎麼標示

任何收錄 `picotype_data_optimized.h`(或其衍生的 `.font` / `.map` /
`ime_tables.h`)的專案,都必須隨附:

1. McBopomofo 的 MIT 著作權聲明與授權條文(本目錄的 `McBopomofo-MIT.txt`)
2. 字型的 SIL OFL 1.1 聲明(見 `fonts/LICENSES/ATTRIBUTION.md`)

產出的標頭檔檔頭會自動帶上字型的 attribution 註解;
碼表的部分請在專案的 `THIRD_PARTY_NOTICES.md` 中標示。
