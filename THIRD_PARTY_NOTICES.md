# Third-Party Notices

本工具鏈自身的程式碼採 MIT（見 `LICENSE`）。

`fonts/` 與 `ime_data/` 內的來源資料、以及 `output_data/` 內由它們產生的
衍生資料，各自遵守其原授權。詳細說明分列於兩份 attribution 文件：

| 文件 | 涵蓋範圍 |
| :--- | :--- |
| [`fonts/LICENSES/ATTRIBUTION.md`](fonts/LICENSES/ATTRIBUTION.md) | 字型的出處、授權、版本固定理由、保留字型名稱 |
| [`ime_data/LICENSES/ATTRIBUTION.md`](ime_data/LICENSES/ATTRIBUTION.md) | 注音碼表與字表的出處與授權 |

## 摘要

| 成分 | 上游 | 授權 |
| :--- | :--- | :--- |
| 注音碼表 | [McBopomofo](https://github.com/openvanilla/McBopomofo) | MIT，Copyright (c) 2011-2026 Mengjuei Hsieh et al. |
| 主字型 | [Cubic 11](https://github.com/ACh-K/Cubic-11) v1.430 | SIL OFL 1.1 |
| fallback 字型 | [Fusion Pixel 12px zh_hant](https://github.com/TakWolf/fusion-pixel-font) | SIL OFL 1.1 |

## 給下游專案

任何收錄 `output_data/picotype_data_optimized.h`（或其衍生的
`.font` / `.map` / `ime_tables.h`）的專案，都必須隨附：

1. **McBopomofo 的 MIT 著作權聲明與授權條文** ——
   全文見 [`ime_data/LICENSES/McBopomofo-MIT.txt`](ime_data/LICENSES/McBopomofo-MIT.txt)
2. **字型的 SIL OFL 1.1 聲明** —— 產出的標頭檔檔頭會自動帶上 attribution 註解

> 需要注意的是 McBopomofo 資料目錄內各檔案的授權並不一致：
> 多字詞庫 `BPMFMappings.txt` 帶有 libtabe（BSD）血統，
> 而本專案**只使用** `BPMFBase.txt` 與 `BPMFPunctuations.txt`（皆為純 MIT）。
> 詳見 `ime_data/LICENSES/ATTRIBUTION.md`。
