import os

# --- 配置 (採用資料驅動設計) ---
# 我們將設定資訊全部整合到這個列表中
# 每個字典代表一個來源檔案的處理規則
SOURCE_FILES_CONFIG = [
#     {
#         "path": "../ime_data/BPMFBase.txt",
#         "method": "first_char"  # 特殊規則：直接取第一個字元
#     },
    {
        "path": "../ime_data/BPMFPunctuations.txt",
        "method": "split",      # 通用規則：分割字串
        "delimiter": " ",       # 分隔符號是「空格」
        "column_index": 0       # 取第 0 個欄位 (第一個)
    },
    {
        "path": "../ime_data/通用规范汉字表(2013)全部(8105字).txt",
        "method": "split",      # 通用規則：分割字串
        "delimiter": "\t",      # 分隔符號是「Tab」
        "column_index": 1       # 取第 1 個欄位 (第二個)
    },
    {
        "path": "../ime_data/字頻表.txt",
        "method": "split",      # 通用規則：分割字串
        "delimiter": " ",      # 分隔符號是「Tab」
        "column_index": 0       # 取第 1 個欄位 (第二個)
    },
]

# 輸出的字元集檔案
OUTPUT_CHARSET_PATH = "../charsets/chars_from_tcfreq_sc.txt"

# --- 主程式 ---
def extract_chars_from_tables():
    """
    從多個輸入法碼表中提取所有字元和符號，去重後儲存為一個字元集檔案。
    (此版本採用資料驅動設計，更具擴充性)
    """
    print("開始從多個來源提取字元集...")

    char_set = set()

    # 直接遍歷設定列表，不再需要判斷檔名
    for config in SOURCE_FILES_CONFIG:
        filepath = config["path"]
        print(f"正在處理檔案: {filepath} (使用方法: {config['method']})")
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"警告: 找不到檔案 '{filepath}'，將跳過。")
            continue

        for line in lines:
            line = line.strip()
            if not line:
                continue

            char_to_add = None
            
            # 根據設定中的 method 決定解析方式
            if config["method"] == "first_char":
                char_to_add = line[0]
            
            elif config["method"] == "split":
                delimiter = config["delimiter"]
                col_index = config["column_index"]
                
                parts = line.split(delimiter)
                if len(parts) > col_index and parts[col_index]:
                    char_to_add = parts[col_index]

            if char_to_add:
                # 確保只添加一個字元，避免 "的" 和 "的 " 被視為不同
                char_set.add(char_to_add.strip())

    if not char_set:
        print("錯誤: 未能從任何來源檔案中提取到字元。")
        return

    output_dir = os.path.dirname(OUTPUT_CHARSET_PATH)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    sorted_chars = sorted(list(char_set))
    with open(OUTPUT_CHARSET_PATH, "w", encoding="utf-8") as f:
        f.write("".join(sorted_chars))

    print("-" * 30)
    print("字元集提取完成！")
    print(f"總共提取了 {len(sorted_chars)} 個獨立字元(包括符號)。")
    print(f"字元集已儲存至: {OUTPUT_CHARSET_PATH}")


if __name__ == "__main__":
    extract_chars_from_tables()