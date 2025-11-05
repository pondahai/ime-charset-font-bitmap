# (這裡貼上包含所有翻頁功能修改的完整 main.py 程式碼)
import pygame
import json
import os
import random

# --- 配置 ---
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240
FPS = 30

# 資源檔案路徑
FONT_MAP_PATH = "output_data/Cubic_11.ttf_12.map"
FONT_DATA_PATH = "output_data/Cubic_11.ttf_12.font"
IME_IDX_PATH = "output_data/zhuyin.idx"
IME_DAT_PATH = "output_data/zhuyin.dat"

# UI 顏色和佈局
COLOR_BACKGROUND = (20, 30, 40)
COLOR_TEXT = (220, 220, 220)
COLOR_INPUT = (255, 255, 0) # 黃色
COLOR_CANDIDATE = (0, 255, 255) # 青色
COLOR_BORDER = (80, 80, 80)
INPUT_AREA_RECT = pygame.Rect(10, 10, SCREEN_WIDTH - 20, 40)
CANDIDATE_AREA_RECT = pygame.Rect(10, 60, SCREEN_WIDTH - 20, 40)
EDITOR_AREA_RECT = pygame.Rect(10, 110, SCREEN_WIDTH - 20, SCREEN_HEIGHT - 120)

# --- 核心類別：字型渲染器 (與上一版相同) ---
class FontRenderer:
    def __init__(self, map_path, font_path):
        self.char_map = {}
        self.font_file = None
        self.metadata = {}
        if not self._load_map(map_path) or not self._open_font_data(font_path):
            raise RuntimeError("字型渲染器初始化失敗！")
        print("字型渲染器初始化成功！")

    def _load_map(self, map_path):
        try:
            with open(map_path, 'r', encoding='utf-8') as f:
                map_data = json.load(f)
                self.metadata = map_data.get('metadata', {})
                self.char_map = map_data.get('characters', {})
                print(f"成功載入 {len(self.char_map)} 個字元的查找表。")
                return True
        except Exception as e:
            print(f"錯誤: 無法載入或解析 .map 檔案: {e}")
            return False

    def _open_font_data(self, font_path):
        try:
            self.font_file = open(font_path, 'rb')
            return True
        except Exception as e:
            print(f"錯誤: 找不到 .font 檔案: {e}")
            return False

    def get_char_surface(self, char_to_render, color=(255, 255, 255)):
        unicode_str = str(ord(char_to_render))
        font_size = self.metadata.get('font_size', 24)
        if unicode_str not in self.char_map:
            not_found_surface = pygame.Surface((font_size, font_size), pygame.SRCALPHA)
            pygame.draw.rect(not_found_surface, (255, 0, 255, 200), (0, 0, font_size-2, font_size-2), 1)
            return not_found_surface
        offset, width, height = self.char_map[unicode_str]
        self.font_file.seek(offset)
        pixel_data = self.font_file.read(width * height)
        char_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        for y in range(height):
            for x in range(width):
                alpha = pixel_data[y * width + x]
                if alpha > 0:
                    char_surface.set_at((x, y), (*color, alpha))
        return char_surface

    def draw_string(self, target_surface, text, x, y, color=(255, 255, 255)):
        current_x = x
        for char in text:
            char_surf = self.get_char_surface(char, color)
            if char_surf:
                target_surface.blit(char_surf, (current_x, y))
                current_x += char_surf.get_width() + 1
        return current_x
    def measure_string(self, text):
        """測量一個字串被渲染後的總寬度，但不實際繪製。"""
        width = 0
        for char in text:
            unicode_str = str(ord(char))
            if unicode_str in self.char_map:
                # 從 map 中獲取字元寬度
                _, char_width, _ = self.char_map[unicode_str]
                width += char_width + 1 # 加上 1px 的字元間距
            else:
                # 如果字元不存在，給一個預設寬度
                width += self.metadata.get('font_size', 24) + 1
        return width    
    def close(self):
        if self.font_file:
            self.font_file.close()

# --- 核心類別：輸入法引擎 (與上一版相同) ---
class ImeEngine:
    def __init__(self, idx_path, dat_path):
        self.idx_data = {}
        self.dat_file = None
        if not self._load_idx(idx_path) or not self._open_dat(dat_path):
            raise RuntimeError("輸入法引擎初始化失敗！")
        print("輸入法引擎初始化成功！")

    def _load_idx(self, idx_path):
        try:
            with open(idx_path, 'r', encoding='utf-8') as f:
                self.idx_data = json.load(f)
                print(f"成功載入 {len(self.idx_data)} 條輸入法索引。")
                return True
        except Exception as e:
            print(f"錯誤: 無法載入或解析 .idx 檔案: {e}")
            return False

    def _open_dat(self, dat_path):
        try:
            self.dat_file = open(dat_path, 'rb')
            return True
        except Exception as e:
            print(f"錯誤: 找不到 .dat 檔案: {e}")
            return False

    def query(self, input_code):
        if input_code not in self.idx_data:
            return ""
        offset, length = self.idx_data[input_code]
        self.dat_file.seek(offset)
        encoded_bytes = self.dat_file.read(length)
        return encoded_bytes.decode('utf-8')

    def close(self):
        if self.dat_file:
            self.dat_file.close()

# --- 主應用程式 ---
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("PicoType Simulator - Full Demo with Paging")
    clock = pygame.time.Clock()

    try:
        renderer = FontRenderer(FONT_MAP_PATH, FONT_DATA_PATH)
        ime = ImeEngine(IME_IDX_PATH, IME_DAT_PATH)
    except RuntimeError as e:
        print(e)
        return

    # 狀態變數
    input_buffer = "" 
    candidate_string = ""
    editor_content = ""
    candidate_page = 0
    CANDIDATES_PER_PAGE = 9

    key_map = {
        '1': 'ㄅ', 'q': 'ㄆ', 'a': 'ㄇ', 'z': 'ㄈ', '2': 'ㄉ', 'w': 'ㄊ', 's': 'ㄋ', 'x': 'ㄌ',
        'e': 'ㄍ', 'd': 'ㄎ', 'c': 'ㄏ', 'r': 'ㄐ', 'f': 'ㄑ', 'v': 'ㄒ', 't': 'ㄓ', 'g': 'ㄔ',
        'b': 'ㄕ', 'y': 'ㄖ', 'h': 'ㄗ', 'n': 'ㄘ', 'm': 'ㄙ', 'u': 'ㄧ', 'j': 'ㄨ', 'k': 'ㄩ',
        '8': 'ㄚ', 'i': 'ㄛ', 'l': 'ㄜ', ',': 'ㄝ', '9': 'ㄞ', 'o': 'ㄟ', ';': 'ㄠ', '.': 'ㄡ',
        '0': 'ㄢ', 'p': 'ㄣ', "'": 'ㄤ', '/': 'ㄥ', '6': 'ㄦ',
        '3': 'ˇ', '4': 'ˋ', '5': '˙', '7': 'ˊ'
    }

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                
                elif event.unicode in key_map:
                    input_buffer += key_map[event.unicode]
                    query_code = input_buffer.replace("ˊ", "2").replace("ˇ", "3").replace("ˋ", "4").replace("˙", "5")
                    if not any(c in "2345" for c in query_code):
                        query_code += "1"
                    candidate_string = ime.query(query_code)
                    candidate_page = 0

                elif event.key == pygame.K_BACKSPACE:
                    if input_buffer:
                        input_buffer = input_buffer[:-1]
                        if input_buffer:
                            query_code = input_buffer.replace("ˊ", "2").replace("ˇ", "3").replace("ˋ", "4").replace("˙", "5")
                            if not any(c in "2345" for c in query_code):
                                query_code += "1"
                            candidate_string = ime.query(query_code)
                        else:
                            candidate_string = ""
                        candidate_page = 0
                    elif editor_content:
                        editor_content = editor_content[:-1]
                
                elif event.key == pygame.K_SPACE:
                    if candidate_string:
                        actual_choice_index = candidate_page * CANDIDATES_PER_PAGE
                        if actual_choice_index < len(candidate_string):
                            editor_content += candidate_string[actual_choice_index]
                            input_buffer = ""
                            candidate_string = ""
                            candidate_page = 0

                elif pygame.K_1 <= event.key <= pygame.K_9:
                    choice_on_page = event.key - pygame.K_1
                    actual_choice_index = candidate_page * CANDIDATES_PER_PAGE + choice_on_page
                    if actual_choice_index < len(candidate_string):
                        editor_content += candidate_string[actual_choice_index]
                        input_buffer = ""
                        candidate_string = ""
                        candidate_page = 0
                
                elif event.key == pygame.K_RIGHT or event.key == pygame.K_EQUALS:
                    if len(candidate_string) > (candidate_page + 1) * CANDIDATES_PER_PAGE:
                        candidate_page += 1
                
                elif event.key == pygame.K_LEFT or event.key == pygame.K_MINUS:
                    if candidate_page > 0:
                        candidate_page -= 1

        screen.fill(COLOR_BACKGROUND)
        
        pygame.draw.rect(screen, COLOR_BORDER, INPUT_AREA_RECT, 1)
        renderer.draw_string(screen, f"輸入: {input_buffer}", INPUT_AREA_RECT.x + 5, INPUT_AREA_RECT.y + 5, COLOR_INPUT)

        pygame.draw.rect(screen, COLOR_BORDER, CANDIDATE_AREA_RECT, 1)
        start_index = candidate_page * CANDIDATES_PER_PAGE
        end_index = start_index + CANDIDATES_PER_PAGE
        page_candidates = candidate_string[start_index:end_index]
        candidate_display = " ".join([f"{i+1}{c}" for i, c in enumerate(page_candidates)])
        if len(candidate_string) > CANDIDATES_PER_PAGE:
            page_info = f"[{candidate_page + 1}/{ (len(candidate_string) - 1) // CANDIDATES_PER_PAGE + 1}]"
            candidate_display += f"  {page_info} (-/=)"
        renderer.draw_string(screen, f"{candidate_display}", CANDIDATE_AREA_RECT.x + 5, CANDIDATE_AREA_RECT.y + 5, COLOR_CANDIDATE)

        # 繪製編輯區
        pygame.draw.rect(screen, COLOR_BORDER, EDITOR_AREA_RECT, 1)
        line_y = EDITOR_AREA_RECT.y + 5
        current_line = ""
        for char in editor_content:
            # 測試如果加上新字元是否會超出一行
            test_line = current_line + char
            line_width = renderer.measure_string(test_line)
            
            if line_width > EDITOR_AREA_RECT.width - 10: # 減去左右邊距
                # 當前行已滿，繪製它並開始新行
                renderer.draw_string(screen, current_line, EDITOR_AREA_RECT.x + 5, line_y, COLOR_TEXT)
                line_y += renderer.metadata.get('font_size', 24) + 4 # 換行
                current_line = char # 新行以當前字元開始
            else:
                # 尚未滿行，繼續添加字元
                current_line = test_line

        # 繪製剩餘的最後一行
        renderer.draw_string(screen, current_line, EDITOR_AREA_RECT.x + 5, line_y, COLOR_TEXT)
        
        pygame.display.flip()
        clock.tick(FPS)

    renderer.close()
    ime.close()
    pygame.quit()

if __name__ == "__main__":
    main()