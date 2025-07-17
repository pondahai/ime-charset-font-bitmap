# PicoType 資料轉換工具鏈說明 (README)

## 1. 總覽 (Overview)

本工具鏈包含兩個核心的 Python 腳本：`charset_extractor.py` 和 `full_hardcode_converter.py`。它們的主要目標是將文字形式的字型檔 (TTF)、輸入法碼表、以及各種字元來源，轉換為適用於嵌入式系統 (如 Arduino、ESP32 等) 的高度優化、可直接硬編碼 (hard-code) 的 C++ 標頭檔 (`.h`)。

這樣做的主要優點是：

*   **節省資源**：在 RAM 和 Flash 有限的微控制器上，無需在執行時期解析文字檔案或字型檔。
*   **提升效能**：直接讀取預先處理好的二進位資料，遠比動態渲染字元或搜尋文字碼表來得快。
*   **客製化字庫**：可以根據專案需求，精準地打包需要的字元，大幅縮小最終韌體的體積。

## 2. 工具鏈運作流程
![charset_ime_font_bitmap](https://github.com/user-attachments/assets/ab65f373-229e-492a-9f29-aa424256df67)

整個資料處理流程如下：

1.  **準備來源資料**: 將原始的輸入法碼表 (`.txt`)、字頻表 (`.txt`)、字型檔 (`.ttf`) 等放入對應的資料夾。
2.  **(可選) 產生字元集**:
    *   執行 `tools/charset_extractor.py`。
    *   此腳本會讀取 `ime_data/` 和其他來源的檔案，提取所有不重複的字元。
    *   產生一個精簡的字元集檔案 (例如 `charsets/chars_from_tcfreq_sc.txt`)。
3.  **轉換為硬編碼**:
    *   執行 `tools/full_hardcode_converter.py`。
    *   此腳本會：
        a. 根據設定，讀取上一步產生的**字元集檔案**。
        b. 讀取指定的**字型檔**，並只渲染字元集中包含的字元，將其轉換為點陣圖資料。
        c. 讀取**注音輸入法碼表**，將其轉換為高效查詢的二進位格式。
        d. 將上述所有二進位資料打包成一個 C++ 標頭檔 (`output_data/picotype_data_optimized.h`)。
4.  **整合至專案**: 在您的 Arduino/C++ 專案中直接 `#include "picotype_data_optimized.h"` 即可使用這些預先處理好的資料。

## 3. 目錄結構

為了讓工具鏈正常運作，建議採用以下目錄結構：

```
PicoType_Project/
│
├── arduino_project/          # 你的主要 Arduino 或 C++ 專案程式碼
│   └── ...
│
├── tools/                    # 存放本工具鏈的 Python 腳本
│   ├── charset_extractor.py
│   └── full_hardcode_converter.py
│
├── fonts/                    # 存放來源字型檔
│   └── Cubic_11.ttf
│
├── ime_data/                 # 存放來源輸入法碼表、字頻表等
│   ├── BPMFBase.txt
│   ├── BPMFPunctuations.txt
│   ├── 字頻表.txt
│   └── 通用规范汉字表(2013)全部(8105字).txt
│
├── charsets/                 # 存放由 charset_extractor.py 產生的字元集
│   └── chars_from_tcfreq_sc.txt
│
└── output_data/              # 存放最終產出的 C++ 標頭檔
    └── picotype_data_optimized.h
```

## 4. 各工具詳解

### 4.1. `charset_extractor.py` (字元集提取工具)

*   **功能**:
    此工具的核心功能是從一個或多個不同格式的文字檔中，提取出所有字元，並生成一個不重複、已排序的字元集合檔案。

*   **設計理念**:
    採用「資料驅動」設計。所有的檔案來源和解析規則都定義在 `SOURCE_FILES_CONFIG` 列表中。這使得新增或修改來源檔案時，只需修改設定檔，無需更動主程式邏輯，擴充性極佳。

*   **如何使用**:
    1.  將您的來源檔案（例如碼表、文章、字頻表）放入 `ime_data/`。
    2.  編輯 `charset_extractor.py` 中的 `SOURCE_FILES_CONFIG` 列表，為每個檔案設定：
        *   `path`: 檔案路徑。
        *   `method`: 解析方法，例如 `'split'` (分割字串) 或 `'first_char'` (取第一個字元)。
        *   `delimiter`: 分隔符號 (當 `method` 為 `'split'` 時使用)。
        *   `column_index`: 要提取的欄位索引 (當 `method` 為 `'split'` 時使用)。
    3.  執行 `python tools/charset_extractor.py`。
    4.  腳本會在 `charsets/` 目錄下產生一個合併後的字元集檔案。

### 4.2. `full_hardcode_converter.py` (全功能硬編碼轉換工具)

*   **功能**:
    此為核心轉換工具，負責將文字資源轉換成最終的 C++ 硬編碼資料。

*   **核心概念**:
    *   **可選字元集 (`CHARSET_MODE`)**:
        *   `'FILE'`: (推薦) 使用 `charset_extractor.py` 產生的檔案作為字元集基礎。這能最大程度地客製化字庫大小。
        *   `'AUTO'`: 直接從輸入法檔案 (`IME_SOURCE_FILES`) 中提取字元，適合快速測試。
    *   **二進位優化**: 所有資料都被 `struct.pack` 轉換為緊湊的二進位格式，並使用「索引(Index) + 資料池(Pool)」的模式來節省空間和加速查詢。

*   **如何使用**:
    1.  確保 `charset_extractor.py` 已產生所需的字元集檔案 (如果使用 `'FILE'` 模式)。
    2.  編輯 `full_hardcode_converter.py` 頂部的全局配置區塊：
        *   `IME_SOURCE_FILES`: 設定注音輸入法的碼表來源。
        *   `FONT_SOURCE_PATH`: 指定要使用的 TTF 字型檔。
        *   `FONT_SIZE`: 設定要渲染的字體大小。
        *   `OUTPUT_H_FILE_PATH`: 設定最終產出的 `.h` 檔案路徑。
        *   `CHARSET_MODE` 和 `CHARSET_FILE_PATH`: 根據需求設定字元集模式及路徑。
    3.  執行 `python tools/full_hardcode_converter.py`。
    4.  腳本會在 `output_data/` 目錄下產生 `picotype_data_optimized.h`。

## 5. 產出檔案格式詳解

### 5.1. 字元集檔案 (`chars_from_tcfreq_sc.txt`)

*   **格式**: 純文字檔 (UTF-8)。
*   **內容**: 一個沒有任何分隔符號的長字串，包含了所有從來源檔案中提取出的、不重複且排序過的字元。
    例如: `!"#$%&'()*+,-./0123...一丁七...龥`

### 5.2. C++ 標頭檔 (`picotype_data_optimized.h`)

這是最核心的產出檔案，其內部資料結構經過精心設計。

#### A. 字型資料 (Font Data)

字型資料被分為兩部分：一個「對應表 (Map)」和一個「點陣圖資料池 (Bitmap Pool)」。

*   `font_map_raw_opt`: 字元對應表 (Index)。它是一個 `FontMapRecord_Opt` 結構的陣列。
*   `font_bitmap_data_opt`: 包含了所有字元實際的、連續存放的點陣圖資料 (Pool)。

**`struct FontMapRecord_Opt` 結構 (共 16 Bytes):**

| 欄位        | 型別     | 大小 (Bytes) | 說明                                                              |
| :---------- | :------- | :----------- | :---------------------------------------------------------------- |
| `unicode`   | `uint32_t` | 4            | 字元的 Unicode 編碼。                                               |
| `offset`    | `uint32_t` | 4            | 該字元的點陣圖資料在 `font_bitmap_data_opt` 中的起始位移(offset)。 |
| `width`     | `uint8_t`  | 1            | 字元點陣圖的寬度 (pixels)。                                       |
| `height`    | `uint8_t`  | 1            | 字元點陣圖的高度 (pixels)。                                       |
| `x_advance` | `uint8_t`  | 1            | 字元在水平方向上的總繪製寬度，用於計算下一個字元的起始位置。       |
| `x_offset`  | `int8_t`   | 1            | 字元點陣圖相對於繪製原點的水平偏移。                               |
| `y_offset`  | `int8_t`   | 1            | 字元點陣圖相對於繪製原點的垂直偏移（基線之上）。                   |
| `padding`   | `uint8_t`  | 1            | 填充位元組，使結構體大小對齊到 16 bytes，提高存取效率。           |

**運作方式**:
要繪製一個字元時，先透過二分搜尋法在 `font_map_opt` 中找到對應的 Unicode 紀錄，從中取得 `offset`, `width`, `height` 等資訊，然後再去 `font_bitmap_data_opt` 中讀取點陣圖資料來繪製。

#### B. 輸入法資料 (IME Data)

輸入法資料同樣採用「索引 + 資料池」的設計，以實現高效的注音查詢。

*   `zhuyin_idx_raw_opt`: 注音索引表。它是一個 `ImeIndexRecord_Opt` 結構的陣列。
*   `zhuyin_pool_opt`: 資料池，連續存放了所有注音按鍵組合 (key) 和其對應的候選字 (candidates)。

**`struct ImeIndexRecord_Opt` 結構 (共 8 Bytes):**

| 欄位          | 型別       | 大小 (Bytes) | 說明                                                        |
| :------------ | :--------- | :----------- | :---------------------------------------------------------- |
| `key_offset`  | `uint16_t` | 2            | 注音按鍵組合在 `zhuyin_pool_opt` 中的起始位移。             |
| `key_len`     | `uint8_t`  | 1            | 注音按鍵組合的長度 (bytes)。                                |
| `padding`     | `uint8_t`  | 1            | 填充位元組，用於對齊。                                        |
| `data_offset` | `uint16_t` | 2            | 該注音對應的候選字字串在 `zhuyin_pool_opt` 中的起始位移。 |
| `data_len`    | `uint16_t` | 2            | 候選字字串的總長度 (bytes)。                                |

**運作方式**:
當使用者輸入一組注音（例如 `ㄍㄨㄤ`）時：
1.  程式將輸入的注音組合（`guang`）在 `zhuyin_idx_opt` 索引表中進行搜尋（因為索引表已排序，可使用二分搜尋）。
2.  在 `zhuyin_pool_opt` 中，根據 `key_offset` 和 `key_len` 比對，確認找到完全匹配的按鍵組合。
3.  一旦找到，就使用對應的 `data_offset` 和 `data_len` 從 `zhuyin_pool_opt` 中讀取出候選字字串（例如 "光廣逛"）。

---
