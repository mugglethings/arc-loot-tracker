import FreeSimpleGUI as sg
import json
import os
from PIL import ImageGrab, Image
import keyboard
import numpy as np
import logging

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('loot_tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = 'data'
ITEMS_DIR = os.path.join(DATA_DIR, 'items')
LOOT_FILE = 'loot.txt'

# ────────────────────────────────────────────────────────────────
# GLOBAL HELPERS
# ────────────────────────────────────────────────────────────────
def text_input(prompt, default=""):
    """Reusable text input with validation"""
    while True:
        out = sg.popup_get_text(prompt, default_text=default, keep_on_top=True)
        if out and out.strip():
            return out.strip()
        sg.popup_error("Input cannot be empty!")

def single_choice(title, label, options, allow_restart=False, allow_text=False):
    """Reusable dropdown or text input modal"""
    layout = []
    if allow_restart:
        layout.append([sg.Button('Restart')])
    layout.extend([
        [sg.Text(label)],
        [sg.Combo(options, key='-VAL-', size=(25, 1), readonly=True) if not allow_text
         else sg.Input(key='-VAL-', size=(27, 1))],
        [sg.Button('OK')]
    ])
    window = sg.Window(title, layout, size=(380, 150), keep_on_top=True, finalize=True)
    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, None):
            window.close()
            return None, 'close'
        if event == 'Restart':
            window.close()
            return None, 'restart'
        if event == 'OK':
            value = values.get('-VAL-', '').strip()
            if not value:
                sg.popup_error("Field cannot be empty!")
                continue
            if not allow_text and value not in options:
                sg.popup_error("Invalid selection")
                continue
            window.close()
            return value, 'success'

# ────────────────────────────────────────────────────────────────
# MAIN CLASS
# ────────────────────────────────────────────────────────────────
class LootTracker:
    def __init__(self):
        self.template_cache = {}
        self.initialize_directories()
        self.load_all_data()
    
    def initialize_directories(self):
        try:
            os.makedirs(ITEMS_DIR, exist_ok=True)
            if not os.path.exists(LOOT_FILE):
                open(LOOT_FILE, 'a').close()
            logger.info("Directories initialized")
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            sg.popup_error(f"Failed to initialize: {e}")
            exit(1)
    
    def load_json(self, filename):
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Required file not found: {path}")
        with open(path, 'r') as f:
            data = json.load(f)
        if filename == 'containers.json':
            return data.get('containers', [])
        if filename == 'condition.json':
            return data.get('condition', [])
        return data
    
    def load_all_data(self):
        try:
            self.maps_data = self.load_json('maps.json')
            self.maps_list = list(self.maps_data.keys())
            self.containers_list = self.load_json('containers.json')
            self.conditions_list = self.load_json('condition.json')
            self.grid_data = self.load_json('grid.json')
            self.items_list = self.load_items()
            logger.info(f"Loaded {len(self.maps_list)} maps, {len(self.items_list)} item templates")
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            sg.popup_error(f"Failed to load data: {e}")
            exit(1)
    
    def load_items(self):
        items = {}
        for filename in os.listdir(ITEMS_DIR):  # ← FIXED: was "ITEM items_dir"
            if filename.endswith('.png'):
                name = os.path.splitext(filename)[0]
                path = os.path.join(ITEMS_DIR, filename)
                try:
                    img = np.array(Image.open(path).convert('RGB'), dtype=np.float32) / 255.0
                    items[name] = img
                except Exception as e:
                    logger.warning(f"Failed to load PNG {filename}: {e}")
        return items
    
    def get_template(self, name):
        if name in self.template_cache:
            return self.template_cache[name]
        if name in self.items_list:
            template = self.items_list[name]
            self.template_cache[name] = template
            return template
        return None
    
    def match_template(self, cell, template):
        if cell.shape != template.shape:
            return float('inf')
        return np.mean((cell - template) ** 2)
    
    def find_matching_name(self, cell_img):
        if cell_img.size == 0:
            return None
        best_mse = float('inf')
        best_name = None
        for name in self.items_list:
            template = self.get_template(name)
            if template is None:
                continue
            mse = self.match_template(cell_img, template)
            if mse < best_mse and mse < 0.002:
                best_mse = mse
                best_name = name
        if best_name:
            logger.info(f"Recognized: {best_name} (MSE={best_mse:.6f})")
            return best_name
        return None
    
    def save_template(self, name, cell_img):
        path = os.path.join(ITEMS_DIR, f"{name}.png")
        if os.path.exists(path):
            try:
                existing = np.array(Image.open(path).convert('RGB'), dtype=np.float32) / 255.0
                if existing.shape == cell_img.shape and np.allclose(existing, cell_img, atol=1e-5):
                    logger.info(f"Reusing: {name}.png")
                    self.items_list[name] = cell_img
                    return
            except Exception as e:
                logger.warning(f"Failed to compare: {e}")
        try:
            img = Image.fromarray((cell_img * 255).astype(np.uint8))
            img.save(path)
            self.items_list[name] = cell_img
            logger.info(f"Saved: {name}.png")
            self.template_cache.pop(name, None)
        except Exception as e:
            logger.error(f"Save failed: {e}")
            sg.popup_error(f"Save failed: {e}")
    
    def get_quantity_input(self, idx, name=None):
        prompt = f"Grid {idx + 1}: Quantity for '{name}' (e.g. 5):" if name else f"Grid {idx + 1}: Quantity:"
        while True:
            qty_str = text_input(prompt, default="1")
            try:
                qty = int(qty_str)
                if qty >= 1:
                    return qty
                raise ValueError
            except ValueError:
                sg.popup_error("Enter a valid number (1 or more)!")

    def process_grid(self, img, map_name, condition, location, container, grid_count):
        try:
            if img.dtype == np.uint8:
                img = img.astype(np.float32) / 255.0
            if len(img.shape) == 3 and img.shape[2] == 4:
                img = img[:, :, :3]
            
            cells = self.grid_data.get('cells', [])
            if not cells:
                logger.error("No grid cells defined")
                return None
            
            loot = {}
            cell_data = []
            for idx in range(min(grid_count, len(cells))):
                x1, y1, x2, y2 = cells[idx]
                cell_img = img[y1:y2, x1:x2]
                recognized_name = self.find_matching_name(cell_img)
                cell_data.append((idx, cell_img, recognized_name))
            
            for idx, cell_img, recognized_name in cell_data:
                name = recognized_name
                if not name:
                    name = text_input(f"Grid {idx + 1}: Enter item name (e.g. Wires):")
                self.save_template(name, cell_img)
                qty = self.get_quantity_input(idx, name)
                loot[name] = loot.get(name, 0) + qty
                logger.info(f"Added: {name} × {qty}")
            
            if not loot:
                return None
            
            line_parts = [map_name, condition, location, container]
            for item in sorted(loot.keys()):
                line_parts.extend([item, str(loot[item])])
            
            with open(LOOT_FILE, 'a', encoding='utf-8') as f:
                f.write(','.join(line_parts) + '\n')
            
            logger.info(f"Loot saved: {loot}")
            return True
        
        except Exception as e:
            logger.error(f"Error: {e}")
            sg.popup_error(f"Error: {e}")
            return None

    def scan_window(self, map_name, condition, location, container, grid_count):
        layout = [
            [sg.Text("Press F8 to scan loot grid")],
            [sg.Text(f"Scanning first {grid_count} cells...", key='-STATUS-')],
            [sg.Button('Cancel')]
        ]
        window = sg.Window("Loot Scanner", layout)
        try:
            while True:
                event, _ = window.read(timeout=100)
                if event in (sg.WIN_CLOSED, 'Cancel'):
                    window.close()
                    return False
                if keyboard.is_pressed('f8'):
                    window['-STATUS-'].update("Scanning...")
                    screenshot = ImageGrab.grab()
                    img_array = np.array(screenshot.convert('RGB'))
                    window.hide()
                    result = self.process_grid(img_array, map_name, condition, location, container, grid_count)
                    window.un_hide()
                    if result:
                        window.close()
                        sg.popup("Loot saved!", keep_on_top=True)
                        return True
                    window['-STATUS-'].update("Press F8 to retry")
        finally:
            window.close()

    def run(self):
        while True:
            # Map
            map_name, status = single_choice("Loot Tracker", "Select Map", self.maps_list)
            if status != 'success': return

            # Condition
            condition, status = single_choice("Loot Tracker", "Select Condition", self.conditions_list, allow_restart=True)
            if status == 'close': return
            if status == 'restart': continue

            # Location
            locations = list(self.maps_data.get(map_name, {}).get('locations', {}).keys())
            if not locations:
                sg.popup_error(f"No locations for map: {map_name}")
                continue

            location_loop = True
            while location_loop:
                location, status = single_choice("Loot Tracker", "Select Location", locations, allow_restart=True)
                if status == 'close': return
                if status == 'restart': break

                container_loop = True
                while container_loop:
                    # Container + Grid Count
                    layout = [
                        [sg.Button('Restart')],
                        [sg.Text("Select Container")],
                        [sg.Combo(self.containers_list, key='-CONT-', size=(25, 1), readonly=True)],
                        [sg.Text("Grid cells (1-12):"), sg.Input(key='-GRID-', size=(5, 1), default_text='12')],
                        [sg.Button('Start Scan')]
                    ]
                    window = sg.Window("Loot Tracker", layout, size=(380, 180), keep_on_top=True)
                    restart_flag = False
                    while True:
                        event, values = window.read()
                        if event == sg.WIN_CLOSED:
                            window.close()
                            return
                        if event == 'Restart':
                            window.close()
                            restart_flag = True
                            container_loop = False
                            break
                        if event == 'Start Scan':
                            container = values.get('-CONT-', '').strip()
                            grid_input = values.get('-GRID-', '12').strip()
                            if not container or container not in self.containers_list:
                                sg.popup_error("Please select a container")
                                continue
                            if not grid_input.isdigit():
                                sg.popup_error("Grid cells must be 1-12")
                                continue
                            grid_count = max(1, min(int(grid_input), 12))
                            window.close()
                            scan_result = self.scan_window(map_name, condition, location, container, grid_count)
                            if scan_result:
                                choice = sg.popup_yes_no("Scan another container?")
                                if choice != 'Yes':
                                    container_loop = False
                                    break
                            break
                    if restart_flag:
                        location_loop = False
                        break

if __name__ == "__main__":
    try:
        tracker = LootTracker()
        tracker.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sg.popup_error(f"Fatal error: {e}")