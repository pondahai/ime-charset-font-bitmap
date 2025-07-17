import os
import struct
from collections import defaultdict
from PIL import Image, ImageDraw, ImageFont

# ==============================================================================
# --- 全局配置 ---
# ==============================================================================
# --- 輸入檔案 ---
IME_SOURCE_FILES = [
    "../ime_data/BPMFBase.txt",
    "../ime_data/BPMFPunctuations.txt"
]
# FONT_SOURCE_PATH = "../fonts/BoutiqueBitmap9x9_1.92.ttf"
FONT_SOURCE_PATH = "../fonts/Cubic_11.ttf"
FONT_INDEX = 0
FONT_SIZE = 12

# --- 輸出檔案 ---
OUTPUT_H_FILE_PATH = "../output_data/picotype_data_optimized.h"

# --- 字元集生成模式 ---
# 'AUTO': 自動從輸入法碼表提取 (預設)
# 'FILE': 從指定的檔案讀取
CHARSET_MODE = 'FILE'  # <<< 修改這裡來切換模式

# 當 CHARSET_MODE 為 'FILE' 時，此路徑生效
# CHARSET_FILE_PATH = "../charsets/common_chinese.txt" # <<< 您可以指向任何字元集檔案
# CHARSET_FILE_PATH = "../charsets/chars_from_ime_tcsc.txt" # <<< 您可以指向任何字元集檔案
CHARSET_FILE_PATH = "../charsets/chars_from_tcfreq_sc.txt" # 繁體來自字頻表另加上簡體字

# --- 二進位格式定義 ---
IME_INDEX_FORMAT_OPTIMIZED = "<HBxHH"
FONT_MAP_FORMAT_OPTIMIZED = "<IIBBbbbB"

# ==============================================================================
# --- 主函式 ---
# ==============================================================================
def main():
    print("--- PicoType 全功能硬編碼轉換工具 (可選字元集版) ---")

    # --- 1. 根據模式獲取字元集 ---
    print(f"\n[步驟 1/4] 獲取字元集 (模式: {CHARSET_MODE})...")
    
    base_charset = set()
    if CHARSET_MODE == 'AUTO':
        print("從輸入法碼表中自動提取...")
        base_charset = extract_charset_from_ime()
    elif CHARSET_MODE == 'FILE':
        print(f"從檔案 '{CHARSET_FILE_PATH}' 讀取...")
        base_charset = extract_charset_from_file()
    else:
        print(f"錯誤: 無效的 CHARSET_MODE '{CHARSET_MODE}'。")
        return

    if not base_charset:
        print("錯誤: 未能獲取到任何字元。")
        return

    # 加入 ASCII 基礎字元
    ascii_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.?!:;()[]{}<>@#$%^&*-=_+`~'“\"\\|/"
    final_charset = "".join(sorted(list(base_charset | set(ascii_chars))))
    print(f"獲取完成，共計 {len(final_charset)} 個獨立字元將被包含。")

    # ... (後續步驟 main, convert_font, convert_ime, generate_header 都保持不變) ...
    print("\n[步驟 2/4] 轉換字型為優化的二進位格式...")
    font_map_data, font_bitmap_data = convert_font_optimized(final_charset)
    if font_map_data is None: return
    print("字型轉換完成。")
    print("\n[步驟 3/4] 轉換輸入法碼表為優化的二進位格式...")
    ime_idx_data, ime_pool_data = convert_ime_optimized()
    if ime_idx_data is None: return
    print("輸入法碼表轉換完成。")
    print("\n[步驟 4/4] 生成 C++ 硬編碼標頭檔...")
    generate_header_file_optimized(ime_idx_data, ime_pool_data, font_map_data, font_bitmap_data)
    print("\n--- 所有任務完成！ ---")
    print(f"輸出檔案: {OUTPUT_H_FILE_PATH}")

# ==============================================================================
# --- 輔助函式 ---
# ==============================================================================

# --- 新增和修改的字元集提取函式 ---
def extract_charset_from_ime():
    """從輸入法碼表檔案中提取字元集。"""
    char_set = set()
    for filepath in IME_SOURCE_FILES:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if "BPMFBase.txt" in filepath:
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) >= 1 and len(parts[0]) == 1:
                        char_set.add(parts[0])
            elif "BPMFPunctuations.txt" in filepath:
                for line in lines:
                    parts = line.strip().split(" ", 1)
                    if parts:
                        char_set.add(parts[0])
        except FileNotFoundError:
            print(f"警告: 找不到檔案 '{filepath}'，已跳過。")
    return char_set

def extract_charset_from_file():
    """從指定的文字檔中讀取字元集。"""
    char_set = set()
    try:
        with open(CHARSET_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            # 將檔案內容中的每個字元都加入 set
            for char in content:
                if char.strip(): # 忽略空白字元
                    char_set.add(char)
    except FileNotFoundError:
        print(f"錯誤: 找不到字元集檔案 '{CHARSET_FILE_PATH}'。")
    return char_set

def convert_font_optimized(charset):
    try:
        font = ImageFont.truetype(FONT_SOURCE_PATH, FONT_SIZE, index=FONT_INDEX)
    except IOError: return None, None
    font_map_records, font_bitmap_data = [], bytearray()
    for char in charset:
        try:
            bbox, x_advance = font.getbbox(char), font.getlength(char)
            left, top, right, bottom = bbox
            glyph_width, glyph_height = right - left, bottom - top
        except AttributeError:
             (glyph_width, glyph_height) = font.getsize(char)
             left, top, x_advance = 0, 0, glyph_width
        if glyph_width == 0 or glyph_height == 0:
            if char == ' ':
                glyph_width, glyph_height, left, top = int(x_advance) if x_advance > 0 else FONT_SIZE // 3, FONT_SIZE, 0, 0
            else: continue
        char_image = Image.new("L", (glyph_width, glyph_height), 0)
        ImageDraw.Draw(char_image).text((-left, -top), char, font=font, fill=255)
        offset = len(font_bitmap_data)
        font_bitmap_data.extend(char_image.tobytes())
        font_map_records.append({
            "unicode": ord(char), "offset": offset, "width": glyph_width, "height": glyph_height,
            "x_advance": int(x_advance), "x_offset": left, "y_offset": top, "padding": 0
        })
    font_map_records.sort(key=lambda r: r["unicode"])
    packed_font_map_data = bytearray()
    for record in font_map_records:
        packed_font_map_data.extend(struct.pack(
            FONT_MAP_FORMAT_OPTIMIZED, record["unicode"], record["offset"], record["width"],
            record["height"], record["x_advance"], record["x_offset"], record["y_offset"], record["padding"]
        ))
    return packed_font_map_data, font_bitmap_data

def convert_ime_optimized():
    ime_map = defaultdict(list)
    try:
        with open(IME_SOURCE_FILES[0], "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError: return None, None
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 2 and len(parts[0]) == 1:
            char, bopomofo = parts[0], parts[1]
            bopomofo_key = bopomofo.replace("ˊ", "2").replace("ˇ", "3").replace("ˋ", "4").replace("˙", "5")
            if not any(c.isdigit() for c in bopomofo_key): bopomofo_key += "1"
            if char not in ime_map[bopomofo_key]: ime_map[bopomofo_key].append(char)
    
    ime_pool_data, idx_records, temp_list = bytearray(), [], []
    for key, candidates in ime_map.items():
        temp_list.append({"key_bytes": key.encode('utf-8'), "candidates": candidates})
    temp_list.sort(key=lambda item: item["key_bytes"])

    for item in temp_list:
        key_bytes, data_bytes = item["key_bytes"], "".join(item["candidates"]).encode('utf-8')
        key_offset, key_len = len(ime_pool_data), len(key_bytes)
        ime_pool_data.extend(key_bytes)
        data_offset, data_len = len(ime_pool_data), len(data_bytes)
        ime_pool_data.extend(data_bytes)
        idx_records.append({ "key_offset": key_offset, "key_len": key_len, "data_offset": data_offset, "data_len": data_len })

    packed_ime_idx_data = bytearray()
    for record in idx_records:
        packed_ime_idx_data.extend(struct.pack(
            IME_INDEX_FORMAT_OPTIMIZED,
            record["key_offset"], record["key_len"],
            record["data_offset"], record["data_len"]
        ))
    return packed_ime_idx_data, ime_pool_data

def generate_header_file_optimized(ime_idx_data, ime_pool_data, font_map_data, font_bitmap_data):
    
    # --- 這是修正後的內部函式 ---
    def format_byte_array_to_c(name, data):
        c_code = [f"const uint8_t {name}[{len(data)}] PROGMEM = {{"]
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            c_code.append("    " + ", ".join(f"0x{b:02x}" for b in chunk) + ",")
        c_code.append("};")
        return "\n".join(c_code)

    h_content = [
        "// Auto-generated by full_hardcode_converter.py (Optimized v4). DO NOT EDIT.\n",
        "#pragma once", "#include <Arduino.h>",
        "\n// FONT DATA (Optimized v2)\n",
        "struct __attribute__((packed)) FontMapRecord_Opt {",
        "    uint32_t unicode;   // 4 bytes", "    uint32_t offset;    // 4 bytes",
        "    uint8_t  width;     // 1 byte", "    uint8_t  height;    // 1 byte",
        "    uint8_t  x_advance; // 1 byte", "    int8_t   x_offset;  // 1 byte",
        "    int8_t   y_offset;  // 1 byte", "    uint8_t  padding;   // 1 byte to make it 16 bytes",
        "};", "",
        format_byte_array_to_c("font_map_raw_opt", font_map_data), "",
        format_byte_array_to_c("font_bitmap_data_opt", font_bitmap_data), "",
        "const FontMapRecord_Opt* const font_map_opt = reinterpret_cast<const FontMapRecord_Opt*>(font_map_raw_opt);",
        f"const size_t font_map_count_opt = {len(font_map_data) // struct.calcsize(FONT_MAP_FORMAT_OPTIMIZED)};",
        
        "\n\n// IME DATA (Optimized v4)\n",
        "struct __attribute__((packed)) ImeIndexRecord_Opt {",
        "    uint16_t key_offset;    // 2 bytes", "    uint8_t  key_len;       // 1 byte",
        "    uint8_t  padding;       // 1 byte for alignment",
        "    uint16_t data_offset;   // 2 bytes", "    uint16_t data_len;      // 2 bytes",
        "};", "",
        format_byte_array_to_c("zhuyin_idx_raw_opt", ime_idx_data), "",
        format_byte_array_to_c("zhuyin_pool_opt", ime_pool_data), "",
        "const ImeIndexRecord_Opt* const zhuyin_idx_opt = reinterpret_cast<const ImeIndexRecord_Opt*>(zhuyin_idx_raw_opt);",
        f"const size_t zhuyin_idx_count_opt = {len(ime_idx_data) // struct.calcsize(IME_INDEX_FORMAT_OPTIMIZED)};",
    ]
    
    output_dir = os.path.dirname(OUTPUT_H_FILE_PATH)
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    with open(OUTPUT_H_FILE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(h_content))

# ==============================================================================
# --- 執行入口 ---
# ==============================================================================
if __name__ == "__main__":
    main()