"""
ARC Raiders Loot Tracker - PyQt6 Version
Modern loot tracking application with database and advanced analysis
"""

import sys
import os
import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageGrab
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QMessageBox, QDialog, QLineEdit,
    QTextEdit, QGroupBox, QGridLayout, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('loot_tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
DATA_DIR = 'data'
ITEMS_DIR = os.path.join(DATA_DIR, 'items')
DB_FILE = 'loot_tracker.db'
MSE_THRESHOLD = 0.002


# ═══════════════════════════════════════════════════════════════
# GRID CALCULATOR
# ═══════════════════════════════════════════════════════════════
class GridCalculator:
    """Static grid calculator with precise column positions"""
    
    COL_X = [215, 353, 492, 631]  # X-coordinates for each column
    ROW_Y_START = 398
    CELL_WIDTH = 119
    CELL_HEIGHT = 91
    ROW_GAP = 48
    
    def __init__(self, resolution=(2560, 1440)):
        self.resolution = resolution
        available_height = resolution[1] - self.ROW_Y_START
        self.max_rows = available_height // (self.CELL_HEIGHT + self.ROW_GAP)
        logger.info(f"Grid Calculator initialized for {resolution[0]}x{resolution[1]}")
    
    def get_cell_coords(self, cell_index):
        """Get (x1, y1, x2, y2) coordinates for a cell by index"""
        row = cell_index // 4
        col = cell_index % 4
        
        x1 = self.COL_X[col]
        y1 = self.ROW_Y_START + row * (self.CELL_HEIGHT + self.ROW_GAP)
        x2 = x1 + self.CELL_WIDTH
        y2 = y1 + self.CELL_HEIGHT
        
        return (x1, y1, x2, y2)
    
    def validate_samples(self):
        """Validate calculations match expected coordinates"""
        samples = {
            0: (215, 398, 334, 489),
            1: (353, 398, 472, 489),
            2: (492, 398, 611, 489),
            3: (631, 398, 750, 489),
            4: (215, 537, 334, 628),
        }
        
        for idx, expected in samples.items():
            calculated = self.get_cell_coords(idx)
            assert calculated == expected, f"Grid {idx+1} mismatch"
        
        logger.info("Grid validation passed")
        return True


# ═══════════════════════════════════════════════════════════════
# DATABASE MANAGER
# ═══════════════════════════════════════════════════════════════
class DatabaseManager:
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check for old schema and migrate
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(sessions)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'tier' not in columns:
                logger.info("Migrating database schema...")
                cursor.execute("ALTER TABLE sessions ADD COLUMN tier TEXT DEFAULT 'None'")
                cursor.execute("ALTER TABLE sessions ADD COLUMN categories TEXT DEFAULT '[]'")
                conn.commit()
                logger.info("Migration completed")
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                map TEXT NOT NULL,
                condition TEXT NOT NULL,
                location TEXT NOT NULL,
                container TEXT NOT NULL,
                tier TEXT NOT NULL,
                categories TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Loot items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS loot_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    
    def add_session(self, map_name, condition, location, container, tier, categories, items):
        """Add a new loot session with items"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                'INSERT INTO sessions (map, condition, location, container, tier, categories) VALUES (?, ?, ?, ?, ?, ?)',
                (map_name, condition, location, container, tier, json.dumps(categories))
            )
            session_id = cursor.lastrowid
            
            for item_name, quantity in items.items():
                cursor.execute(
                    'INSERT INTO loot_items (session_id, item_name, quantity) VALUES (?, ?, ?)',
                    (session_id, item_name, quantity)
                )
            
            conn.commit()
            logger.info(f"Session {session_id} saved with {len(items)} items")
            return session_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save session: {e}")
            raise
        finally:
            conn.close()
    
    def get_today_sessions(self):
        """Get all sessions from today"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT s.id, s.map, s.condition, s.location, s.container, s.tier, s.timestamp,
                   GROUP_CONCAT(l.item_name || ' x' || l.quantity, ', ') as items
            FROM sessions s
            LEFT JOIN loot_items l ON s.id = l.session_id
            WHERE DATE(s.timestamp) = DATE('now')
            GROUP BY s.id
            ORDER BY s.timestamp DESC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_container_loot_for_comparison(self, container, map_filter=None, location_filter=None, condition_filter=None):
        """Get loot data for a container with optional map, location and condition filters for comparison"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = '''
            SELECT 
                l.item_name,
                MIN(l.quantity) as min_qty,
                MAX(l.quantity) as max_qty,
                COUNT(*) as times_found
            FROM loot_items l
            JOIN sessions s ON l.session_id = s.id
            WHERE s.container = ?
        '''
        params = [container]
        
        if map_filter and map_filter != "All":
            query += ' AND s.map = ?'
            params.append(map_filter)
        
        if location_filter and location_filter != "All":
            query += ' AND s.location = ?'
            params.append(location_filter)
        
        if condition_filter and condition_filter != "All":
            query += ' AND s.condition = ?'
            params.append(condition_filter)
        
        query += ' GROUP BY l.item_name'
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Get total scans for percentage
        total_query = 'SELECT COUNT(*) FROM sessions WHERE container = ?'
        total_params = [container]
        
        if map_filter and map_filter != "All":
            total_query += ' AND map = ?'
            total_params.append(map_filter)
        
        if location_filter and location_filter != "All":
            total_query += ' AND location = ?'
            total_params.append(location_filter)
        
        if condition_filter and condition_filter != "All":
            total_query += ' AND condition = ?'
            total_params.append(condition_filter)
        
        cursor.execute(total_query, total_params)
        total_scans = cursor.fetchone()[0]
        
        conn.close()
        
        # Build result dict
        loot_dict = {}
        for item_name, min_qty, max_qty, times_found in results:
            percentage = (times_found / total_scans * 100) if total_scans > 0 else 0
            loot_dict[item_name] = {
                'min_qty': min_qty,
                'max_qty': max_qty,
                'percentage': percentage,
                'times_found': times_found
            }
        
        return loot_dict, total_scans
    
    def delete_session(self, session_id):
        """Delete a session and its items"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        conn.commit()
        conn.close()
        logger.info(f"Session {session_id} deleted")
    
    def get_statistics(self, days=7):
        """Get loot statistics for the last N days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                l.item_name,
                SUM(l.quantity) as total_quantity,
                COUNT(DISTINCT s.id) as found_in_sessions,
                s.map
            FROM loot_items l
            JOIN sessions s ON l.session_id = s.id
            WHERE s.timestamp >= DATE('now', '-' || ? || ' days')
            GROUP BY l.item_name, s.map
            ORDER BY total_quantity DESC
        ''', (days,))
        
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_loot_table_data(self, container, map_filter=None, location_filter=None, tier_filter=None):
        """Get advanced loot table data for a specific container"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Build query with filters
        query = '''
            SELECT 
                l.item_name,
                MIN(l.quantity) as min_qty,
                MAX(l.quantity) as max_qty,
                COUNT(*) as times_found,
                GROUP_CONCAT(s.categories, '|||') as all_categories
            FROM loot_items l
            JOIN sessions s ON l.session_id = s.id
            WHERE s.container = ?
        '''
        params = [container]
        
        if map_filter and map_filter != "All":
            query += ' AND s.map = ?'
            params.append(map_filter)
        
        if location_filter and location_filter != "All":
            query += ' AND s.location = ?'
            params.append(location_filter)
        
        if tier_filter and tier_filter != "All":
            query += ' AND s.tier = ?'
            params.append(tier_filter)
        
        query += ' GROUP BY l.item_name'
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Get total scans for percentage calculation
        total_query = 'SELECT COUNT(*) FROM sessions WHERE container = ?'
        total_params = [container]
        
        if map_filter and map_filter != "All":
            total_query += ' AND map = ?'
            total_params.append(map_filter)
        
        if location_filter and location_filter != "All":
            total_query += ' AND location = ?'
            total_params.append(location_filter)
        
        if tier_filter and tier_filter != "All":
            total_query += ' AND tier = ?'
            total_params.append(tier_filter)
        
        cursor.execute(total_query, total_params)
        total_scans = cursor.fetchone()[0]
        
        conn.close()
        
        # Process results with percentage and categories
        processed = []
        for item_name, min_qty, max_qty, times_found, all_categories_str in results:
            # Parse all categories from all sessions
            all_categories = set()
            if all_categories_str:
                for cats_json in all_categories_str.split('|||'):
                    try:
                        cats = json.loads(cats_json) if cats_json else []
                        all_categories.update(cats)
                    except:
                        pass
            
            percentage = (times_found / total_scans * 100) if total_scans > 0 else 0
            
            processed.append({
                'item': item_name,
                'min_qty': min_qty,
                'max_qty': max_qty,
                'categories': sorted(all_categories),
                'percentage': percentage
            })
        
        # Sort by percentage descending
        processed.sort(key=lambda x: x['percentage'], reverse=True)
        
        return processed
    
    def get_container_locations(self, container):
        """Get all locations where a container was found"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                s.map,
                s.location,
                s.tier,
                s.categories,
                COUNT(*) as times_found
            FROM sessions s
            WHERE s.container = ?
            GROUP BY s.map, s.location
            ORDER BY times_found DESC
        ''', (container,))
        
        results = cursor.fetchall()
        conn.close()
        
        # Parse categories
        processed = []
        for map_name, location, tier, categories_json, times_found in results:
            try:
                categories = json.loads(categories_json) if categories_json else []
            except:
                categories = []
            
            processed.append({
                'map': map_name,
                'location': location,
                'tier': tier,
                'categories': categories,
                'times_found': times_found
            })
        
        return processed
    
    def get_all_containers_stats(self):
        """Get statistics for all containers"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                container,
                COUNT(*) as times_scanned
            FROM sessions
            GROUP BY container
            ORDER BY times_scanned DESC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def get_all_items(self):
        """Get list of all unique items found"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT item_name
            FROM loot_items
            ORDER BY item_name
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return [item[0] for item in results]
    
    def get_item_container_stats(self, item_name):
        """Get container statistics for a specific item"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                s.container,
                MIN(l.quantity) as min_qty,
                MAX(l.quantity) as max_qty,
                COUNT(*) as times_found,
                COUNT(DISTINCT s.id) as different_sessions
            FROM loot_items l
            JOIN sessions s ON l.session_id = s.id
            WHERE l.item_name = ?
            GROUP BY s.container
            ORDER BY times_found DESC
        ''', (item_name,))
        
        results = cursor.fetchall()
        
        # Get total scans across all containers
        cursor.execute('''
            SELECT COUNT(DISTINCT s.id)
            FROM sessions s
            WHERE EXISTS (
                SELECT 1 FROM loot_items l 
                WHERE l.session_id = s.id AND l.item_name = ?
            )
        ''', (item_name,))
        
        total_sessions = cursor.fetchone()[0]
        
        conn.close()
        
        # Build result with percentages
        processed = []
        for container, min_qty, max_qty, times_found, different_sessions in results:
            percentage = (different_sessions / total_sessions * 100) if total_sessions > 0 else 0
            
            processed.append({
                'container': container,
                'min_qty': min_qty,
                'max_qty': max_qty,
                'times_found': times_found,
                'percentage': percentage
            })
        
        return processed, total_sessions
    
    def get_sessions_by_container(self, container, days=None):
        """Get sessions for a specific container with optional time filter"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = '''
            SELECT s.id, s.map, s.condition, s.location, s.container, s.tier, s.timestamp,
                   GROUP_CONCAT(l.item_name || ' x' || l.quantity, ', ') as items
            FROM sessions s
            LEFT JOIN loot_items l ON s.id = l.session_id
            WHERE s.container = ?
        '''
        params = [container]
        
        if days is not None:
            if days == 0:
                # Today only
                query += ' AND DATE(s.timestamp) = DATE("now")'
            else:
                # Last N days
                query += f' AND s.timestamp >= DATE("now", "-{days} days")'
        
        query += ' GROUP BY s.id ORDER BY s.timestamp DESC'
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def get_base_and_rare_loot(self, container):
        """
        Get common loot (appears on all map/location combos) and unique loot
        Returns dicts with item info and location data for unique items
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get total unique map/location combinations for this container
        cursor.execute('''
            SELECT COUNT(DISTINCT map || '|' || location)
            FROM sessions
            WHERE container = ?
        ''', (container,))
        
        total_locations = cursor.fetchone()[0]
        
        if total_locations == 0:
            conn.close()
            return {}, {}, {}
        
        # Get all items with their map/location distribution
        cursor.execute('''
            SELECT 
                l.item_name,
                MIN(l.quantity) as min_qty,
                MAX(l.quantity) as max_qty,
                COUNT(DISTINCT s.map || '|' || s.location) as location_count
            FROM loot_items l
            JOIN sessions s ON l.session_id = s.id
            WHERE s.container = ?
            GROUP BY l.item_name
            ORDER BY location_count DESC
        ''', (container,))
        
        items = cursor.fetchall()
        
        common_loot = {}
        unique_loot = {}
        
        for item_name, min_qty, max_qty, location_count in items:
            item_data = {
                'min_qty': min_qty,
                'max_qty': max_qty,
                'locations_count': location_count
            }
            
            # Common = appears on all map/location combos
            if location_count == total_locations:
                common_loot[item_name] = item_data
            else:
                unique_loot[item_name] = item_data
        
        # Get location data for unique loot
        unique_locations = {}
        if unique_loot:
            for item_name in unique_loot.keys():
                cursor.execute('''
                    SELECT DISTINCT s.map, s.location
                    FROM sessions s
                    JOIN loot_items l ON s.id = l.session_id
                    WHERE s.container = ? AND l.item_name = ?
                ''', (container, item_name))
                
                locations = [f"{row[0]} - {row[1]}" for row in cursor.fetchall()]
                unique_locations[item_name] = locations
        
        conn.close()
        
        return common_loot, unique_loot, unique_locations


# ═══════════════════════════════════════════════════════════════
# TEMPLATE MATCHER
# ═══════════════════════════════════════════════════════════════
class TemplateMatcher:
    def __init__(self, items_dir=ITEMS_DIR):
        self.items_dir = Path(items_dir)
        self.items_dir.mkdir(parents=True, exist_ok=True)
        self.templates = {}
        self.load_templates()
    
    def load_templates(self):
        """Load all template images from disk"""
        for img_file in self.items_dir.glob('*.png'):
            name = img_file.stem
            try:
                img = np.array(Image.open(img_file).convert('RGB'), dtype=np.float32) / 255.0
                self.templates[name] = img
            except Exception as e:
                logger.warning(f"Failed to load template {name}: {e}")
        
        logger.info(f"Loaded {len(self.templates)} templates")
    
    def match_template(self, cell_img, template):
        """Calculate MSE between cell and template"""
        if cell_img.shape != template.shape:
            return float('inf')
        return np.mean((cell_img - template) ** 2)
    
    def recognize_item(self, cell_img):
        """Find best matching template for cell image"""
        if cell_img.size == 0:
            return None, 1.0
        
        best_mse = float('inf')
        best_name = None
        
        for name, template in self.templates.items():
            mse = self.match_template(cell_img, template)
            if mse < best_mse:
                best_mse = mse
                best_name = name
        
        if best_mse < MSE_THRESHOLD:
            logger.info(f"Recognized: {best_name} (MSE={best_mse:.6f})")
            return best_name, best_mse
        
        return None, best_mse
    
    def save_template(self, name, cell_img):
        """Save a new template or update existing"""
        path = self.items_dir / f"{name}.png"
        
        # Check if identical template exists
        if path.exists():
            try:
                existing = np.array(Image.open(path).convert('RGB'), dtype=np.float32) / 255.0
                if existing.shape == cell_img.shape and np.allclose(existing, cell_img, atol=1e-5):
                    logger.info(f"Template {name} already exists (identical)")
                    self.templates[name] = cell_img
                    return
            except Exception as e:
                logger.warning(f"Failed to compare with existing: {e}")
        
        # Save new template
        img = Image.fromarray((cell_img * 255).astype(np.uint8))
        img.save(path)
        self.templates[name] = cell_img
        logger.info(f"Saved template: {name}")
    
    def get_template_names(self):
        """Get list of all template names"""
        return sorted(self.templates.keys())


# ═══════════════════════════════════════════════════════════════
# SCAN DIALOG
# ═══════════════════════════════════════════════════════════════
class ScanDialog(QDialog):
    scan_complete = pyqtSignal(dict)
    
    def __init__(self, grid_calculator, grid_count, matcher, parent=None):
        super().__init__(parent)
        self.grid_calculator = grid_calculator
        self.grid_count = grid_count
        self.matcher = matcher
        self.loot_data = {}
        self.current_cell = 0
        self.cell_images = []
        
        self.setWindowTitle("Scan Loot Grid")
        self.setModal(True)
        self.resize(600, 500)
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Instructions
        info = QLabel(f"Scanning {self.grid_count} cells (4 columns × {self.grid_count // 4 + (1 if self.grid_count % 4 else 0)} rows)")
        info.setStyleSheet("font-size: 14px; padding: 10px; background: #e3f2fd;")
        layout.addWidget(info)
        
        # Status
        self.status_label = QLabel("Initializing...")
        self.status_label.setStyleSheet("font-size: 13px; padding: 8px;")
        layout.addWidget(self.status_label)
        
        # Preview area
        preview_group = QGroupBox("Cell Preview")
        preview_layout = QVBoxLayout()
        self.preview_label = QLabel("No image captured yet")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(150)
        self.preview_label.setStyleSheet("border: 2px dashed #ccc; background: #f5f5f5;")
        preview_layout.addWidget(self.preview_label)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        # Current cell info
        self.cell_info_group = QGroupBox("Current Cell")
        cell_layout = QVBoxLayout()
        
        self.recognized_label = QLabel("Recognized: None")
        cell_layout.addWidget(self.recognized_label)
        
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Item Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter item name...")
        name_layout.addWidget(self.name_input)
        cell_layout.addLayout(name_layout)
        
        qty_layout = QHBoxLayout()
        qty_layout.addWidget(QLabel("Quantity:"))
        self.qty_input = QSpinBox()
        self.qty_input.setMinimum(1)
        self.qty_input.setMaximum(999)
        self.qty_input.setValue(1)
        qty_layout.addWidget(self.qty_input)
        qty_layout.addStretch()
        cell_layout.addLayout(qty_layout)
        
        self.cell_info_group.setLayout(cell_layout)
        self.cell_info_group.setEnabled(False)
        layout.addWidget(self.cell_info_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.confirm_btn = QPushButton("Confirm Item")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self.confirm_item)
        button_layout.addWidget(self.confirm_btn)
        
        self.skip_btn = QPushButton("Skip Cell")
        self.skip_btn.setEnabled(False)
        self.skip_btn.clicked.connect(self.skip_cell)
        button_layout.addWidget(self.skip_btn)
        
        self.finish_btn = QPushButton("Finish Scan")
        self.finish_btn.setEnabled(False)
        self.finish_btn.clicked.connect(self.finish_scan)
        button_layout.addWidget(self.finish_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def showEvent(self, event):
        """Capture screenshot automatically when dialog is shown"""
        super().showEvent(event)
        QTimer.singleShot(100, self.capture_screen)
    
    def capture_screen(self):
        """Capture screenshot and extract grid cells"""
        self.status_label.setText("Capturing...")
        QApplication.processEvents()
        
        try:
            screenshot = ImageGrab.grab()
            img_array = np.array(screenshot.convert('RGB'), dtype=np.float32) / 255.0
            
            self.cell_images = []
            for idx in range(self.grid_count):
                x1, y1, x2, y2 = self.grid_calculator.get_cell_coords(idx)
                cell = img_array[y1:y2, x1:x2]
                self.cell_images.append(cell)
            
            self.status_label.setText(f"Captured {len(self.cell_images)} cells")
            self.current_cell = 0
            self.process_current_cell()
            
        except Exception as e:
            logger.error(f"Capture failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to capture: {e}")
            self.status_label.setText("Capture failed")
    
    def process_current_cell(self):
        """Process the current cell"""
        if self.current_cell >= len(self.cell_images):
            self.finish_scan()
            return
        
        cell_img = self.cell_images[self.current_cell]
        row = self.current_cell // 4
        col = self.current_cell % 4
        
        # Show preview
        h, w = cell_img.shape[:2]
        qimg = QImage((cell_img * 255).astype(np.uint8).data, w, h, w * 3, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio)
        self.preview_label.setPixmap(pixmap)
        
        # Try to recognize
        name, mse = self.matcher.recognize_item(cell_img)
        
        if name:
            self.recognized_label.setText(f"Recognized: {name} (confidence: {1-mse:.1%})")
            self.name_input.setText(name)
        else:
            self.recognized_label.setText("Recognized: Unknown")
            self.name_input.clear()
        
        self.status_label.setText(f"Cell {self.current_cell + 1}/{len(self.cell_images)} (Row {row + 1}, Col {col + 1})")
        self.cell_info_group.setEnabled(True)
        self.confirm_btn.setEnabled(True)
        self.skip_btn.setEnabled(True)
        self.finish_btn.setEnabled(True)
        self.name_input.setFocus()
    
    def confirm_item(self):
        """Confirm current item and move to next"""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Input", "Please enter an item name")
            return
        
        qty = self.qty_input.value()
        cell_img = self.cell_images[self.current_cell]
        
        self.matcher.save_template(name, cell_img)
        self.loot_data[name] = self.loot_data.get(name, 0) + qty
        logger.info(f"Added: {name} x{qty}")
        
        self.current_cell += 1
        self.name_input.clear()
        self.qty_input.setValue(1)
        
        self.process_current_cell()
    
    def skip_cell(self):
        """Skip current cell"""
        self.current_cell += 1
        self.name_input.clear()
        self.qty_input.setValue(1)
        self.process_current_cell()
    
    def finish_scan(self):
        """Finish scanning and emit results"""
        if not self.loot_data:
            reply = QMessageBox.question(
                self, "No Items",
                "No items were recorded. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
        
        self.scan_complete.emit(self.loot_data)
        self.accept()
    
    def closeEvent(self, event):
        """Cleanup on close"""
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════
class LootTrackerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ARC Raiders Loot Tracker")
        self.resize(900, 700)
        
        # Initialize components
        self.db = DatabaseManager()
        self.matcher = TemplateMatcher()
        self.grid_calculator = GridCalculator(resolution=(2560, 1440))
        
        # Validate grid calculations
        try:
            self.grid_calculator.validate_samples()
        except AssertionError as e:
            logger.error(f"Grid validation failed: {e}")
            QMessageBox.critical(self, "Grid Error", f"Grid calculation validation failed:\n{e}")
        
        self.load_config_data()
        
        self.setup_ui()
        self.refresh_today_sessions()
        
        logger.info("Application started")
    
    def load_config_data(self):
        """Load configuration files"""
        try:
            with open(os.path.join(DATA_DIR, 'maps.json'), 'r') as f:
                self.maps_data = json.load(f)
            
            with open(os.path.join(DATA_DIR, 'containers.json'), 'r') as f:
                data = json.load(f)
                self.containers = data.get('containers', [])
            
            with open(os.path.join(DATA_DIR, 'condition.json'), 'r') as f:
                data = json.load(f)
                self.conditions = data.get('condition', [])
            
            logger.info("Configuration loaded")
            
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load configuration: {e}")
            sys.exit(1)
    
    def setup_ui(self):
        """Setup the main UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Title
        title = QLabel("🎮 ARC Raiders Loot Tracker")
        title.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        main_layout.addWidget(title)
        
        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self.create_scan_tab(), "📸 Quick Scan")
        tabs.addTab(self.create_history_tab(), "📋 Today's Loot")
        tabs.addTab(self.create_container_history_tab(), "📜 Container History")
        tabs.addTab(self.create_base_loot_tab(), "🎯 Base vs Rare Loot")
        tabs.addTab(self.create_stats_tab(), "📊 Statistics")
        tabs.addTab(self.create_loot_table_tab(), "🔍 Advanced Loot Table")
        tabs.addTab(self.create_item_containers_tab(), "🔎 Item to Containers")
        tabs.addTab(self.create_container_locations_tab(), "📍 Container Locations")
        tabs.addTab(self.create_total_containers_tab(), "📦 Total Containers")
        tabs.addTab(self.create_compare_tab(), "⚖️ Compare Containers")
        main_layout.addWidget(tabs)
    
    def create_scan_tab(self):
        """Create the scanning tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Scan form
        form_group = QGroupBox("New Scan")
        form_layout = QGridLayout()
        
        # Map
        form_layout.addWidget(QLabel("Map:"), 0, 0)
        self.map_combo = QComboBox()
        self.map_combo.addItems(list(self.maps_data.keys()))
        self.map_combo.currentTextChanged.connect(self.on_map_changed)
        form_layout.addWidget(self.map_combo, 0, 1)
        
        # Condition
        form_layout.addWidget(QLabel("Condition:"), 1, 0)
        self.condition_combo = QComboBox()
        self.condition_combo.addItems(self.conditions)
        form_layout.addWidget(self.condition_combo, 1, 1)
        
        # Location
        form_layout.addWidget(QLabel("Location:"), 2, 0)
        self.location_combo = QComboBox()
        form_layout.addWidget(self.location_combo, 2, 1)
        
        # Container
        form_layout.addWidget(QLabel("Container:"), 3, 0)
        self.container_combo = QComboBox()
        self.container_combo.addItems(self.containers)
        form_layout.addWidget(self.container_combo, 3, 1)
        
        # Grid count
        form_layout.addWidget(QLabel("Grid Cells:"), 4, 0)
        grid_layout = QHBoxLayout()
        self.grid_spin = QSpinBox()
        self.grid_spin.setMinimum(1)
        self.grid_spin.setMaximum(48)  # 12 rows × 4 cols
        self.grid_spin.setValue(12)
        self.grid_spin.valueChanged.connect(self.update_grid_info)
        grid_layout.addWidget(self.grid_spin)
        self.grid_info_label = QLabel("(3 rows × 4 cols)")
        grid_layout.addWidget(self.grid_info_label)
        grid_layout.addStretch()
        form_layout.addLayout(grid_layout, 4, 1)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Scan button
        scan_btn = QPushButton("🔍 Start Scan")
        scan_btn.setStyleSheet("font-size: 16px; padding: 12px; background: #4CAF50; color: white;")
        scan_btn.clicked.connect(self.start_scan)
        layout.addWidget(scan_btn)
        
        # Quick actions
        quick_group = QGroupBox("Quick Actions")
        quick_layout = QVBoxLayout()
        
        repeat_btn = QPushButton("🔄 Repeat Last Scan")
        repeat_btn.clicked.connect(self.repeat_last_scan)
        quick_layout.addWidget(repeat_btn)
        
        quick_group.setLayout(quick_layout)
        layout.addWidget(quick_group)
        
        layout.addStretch()
        
        widget.setLayout(layout)
        
        # Initialize locations
        self.on_map_changed(self.map_combo.currentText())
        self.update_grid_info(12)
        
        return widget
    
    def update_grid_info(self, value):
        """Update grid info label"""
        rows = value // 4 + (1 if value % 4 else 0)
        cols = min(value, 4)
        self.grid_info_label.setText(f"({rows} rows × {cols} cols)")
    
    def create_history_tab(self):
        """Create the history tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Sessions from today:"))
        header_layout.addStretch()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_today_sessions)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Table
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(8)
        self.history_table.setHorizontalHeaderLabels([
            "ID", "Map", "Condition", "Location", "Container", "Tier", "Items", "Actions"
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.history_table)
        
        widget.setLayout(layout)
        return widget
    
    def create_container_history_tab(self):
        """Create the container history tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Header with filters
        header_layout = QHBoxLayout()
        
        # Container selection
        header_layout.addWidget(QLabel("Container:"))
        self.container_history_combo = QComboBox()
        self.container_history_combo.addItems(self.containers)
        header_layout.addWidget(self.container_history_combo)
        
        # Period selection
        header_layout.addWidget(QLabel("Period:"))
        self.container_history_period = QComboBox()
        self.container_history_period.addItems(["Today", "Last 7 Days", "Last 14 Days", "All Time"])
        header_layout.addWidget(self.container_history_period)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_container_history)
        header_layout.addWidget(refresh_btn)
        
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Table
        self.container_history_table = QTableWidget()
        self.container_history_table.setColumnCount(8)
        self.container_history_table.setHorizontalHeaderLabels([
            "ID", "Map", "Condition", "Location", "Container", "Tier", "Items", "Actions"
        ])
        self.container_history_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.container_history_table)
        
        widget.setLayout(layout)
        return widget
    
    def create_base_loot_tab(self):
        """Create the common vs unique loot tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Container selection
        container_layout = QHBoxLayout()
        container_layout.addWidget(QLabel("Container:"))
        self.base_loot_container = QComboBox()
        self.base_loot_container.addItems(self.containers)
        container_layout.addWidget(self.base_loot_container)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_base_loot)
        container_layout.addWidget(refresh_btn)
        
        container_layout.addStretch()
        layout.addLayout(container_layout)
        
        # Common loot section
        common_group = QGroupBox("Common Loot (All Locations)")
        common_layout = QVBoxLayout()
        
        self.base_loot_table = QTableWidget()
        self.base_loot_table.setColumnCount(4)
        self.base_loot_table.setHorizontalHeaderLabels([
            "Item", "Min Qty", "Max Qty", "Locations Found"
        ])
        self.base_loot_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        common_layout.addWidget(self.base_loot_table)
        
        common_group.setLayout(common_layout)
        layout.addWidget(common_group)
        
        # Rare loot
        rare_group = QGroupBox("Rare Loot (Location Specific)")
        rare_layout = QVBoxLayout()
        
        self.rare_loot_table = QTableWidget()
        self.rare_loot_table.setColumnCount(5)
        self.rare_loot_table.setHorizontalHeaderLabels([
            "Item", "Min Qty", "Max Qty", "Locations Count", "Found At"
        ])
        self.rare_loot_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.rare_loot_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        rare_layout.addWidget(self.rare_loot_table)
        
        rare_group.setLayout(rare_layout)
        layout.addWidget(rare_group)
        
        widget.setLayout(layout)
        return widget
    
    def create_total_containers_tab(self):
        """Create the total containers statistics tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Container Statistics:"))
        header_layout.addStretch()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_total_containers)
        header_layout.addWidget(refresh_btn)
        
        layout.addLayout(header_layout)
        
        # Table
        self.total_containers_table = QTableWidget()
        self.total_containers_table.setColumnCount(2)
        self.total_containers_table.setHorizontalHeaderLabels([
            "Container", "Times Scanned"
        ])
        self.total_containers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.total_containers_table)
        
        widget.setLayout(layout)
        
        # Load initial data
        self.refresh_total_containers()
        
        return widget
    
    def refresh_total_containers(self):
        """Refresh the total containers statistics"""
        data = self.db.get_all_containers_stats()
        
        self.total_containers_table.setRowCount(len(data))
        
        for row, (container, times_scanned) in enumerate(data):
            self.total_containers_table.setItem(row, 0, QTableWidgetItem(container))
            self.total_containers_table.setItem(row, 1, QTableWidgetItem(str(times_scanned)))
    
    def create_compare_tab(self):
        """Create the container comparison tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Selection area
        selection_group = QGroupBox("Container Selection")
        selection_layout = QGridLayout()
        
        # Container 1
        selection_layout.addWidget(QLabel("Container 1:"), 0, 0)
        self.compare_container1 = QComboBox()
        self.compare_container1.addItems(self.containers)
        selection_layout.addWidget(self.compare_container1, 0, 1)
        
        selection_layout.addWidget(QLabel("Condition:"), 0, 2)
        self.compare_condition1 = QComboBox()
        self.compare_condition1.addItem("All")
        self.compare_condition1.addItems(self.conditions)
        selection_layout.addWidget(self.compare_condition1, 0, 3)
        
        selection_layout.addWidget(QLabel("Map:"), 0, 4)
        self.compare_map1 = QComboBox()
        self.compare_map1.addItem("All")
        self.compare_map1.addItems(list(self.maps_data.keys()))
        self.compare_map1.currentTextChanged.connect(self.update_compare_locations1)
        selection_layout.addWidget(self.compare_map1, 0, 5)
        
        selection_layout.addWidget(QLabel("Location:"), 0, 6)
        self.compare_location1 = QComboBox()
        self.compare_location1.addItem("All")
        selection_layout.addWidget(self.compare_location1, 0, 7)
        
        # Container 2
        selection_layout.addWidget(QLabel("Container 2:"), 1, 0)
        self.compare_container2 = QComboBox()
        self.compare_container2.addItems(self.containers)
        if len(self.containers) > 1:
            self.compare_container2.setCurrentIndex(1)
        selection_layout.addWidget(self.compare_container2, 1, 1)
        
        selection_layout.addWidget(QLabel("Condition:"), 1, 2)
        self.compare_condition2 = QComboBox()
        self.compare_condition2.addItem("All")
        self.compare_condition2.addItems(self.conditions)
        selection_layout.addWidget(self.compare_condition2, 1, 3)
        
        selection_layout.addWidget(QLabel("Map:"), 1, 4)
        self.compare_map2 = QComboBox()
        self.compare_map2.addItem("All")
        self.compare_map2.addItems(list(self.maps_data.keys()))
        self.compare_map2.currentTextChanged.connect(self.update_compare_locations2)
        selection_layout.addWidget(self.compare_map2, 1, 5)
        
        selection_layout.addWidget(QLabel("Location:"), 1, 6)
        self.compare_location2 = QComboBox()
        self.compare_location2.addItem("All")
        selection_layout.addWidget(self.compare_location2, 1, 7)
        
        # Compare button
        compare_btn = QPushButton("⚖️ Compare")
        compare_btn.setStyleSheet("font-size: 14px; padding: 8px; background: #2196F3; color: white;")
        compare_btn.clicked.connect(self.refresh_comparison)
        selection_layout.addWidget(compare_btn, 2, 0, 1, 8)
        
        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)
        
        # Common items table
        common_group = QGroupBox("Common Items (Found in Both)")
        common_layout = QVBoxLayout()
        
        self.compare_common_table = QTableWidget()
        self.compare_common_table.setColumnCount(5)
        self.compare_common_table.setHorizontalHeaderLabels([
            "Item", 
            f"Container 1 Qty", 
            f"Container 1 %",
            f"Container 2 Qty",
            f"Container 2 %"
        ])
        self.compare_common_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        common_layout.addWidget(self.compare_common_table)
        
        common_group.setLayout(common_layout)
        layout.addWidget(common_group)
        
        # Unique items table
        unique_group = QGroupBox("Unique Items (Found in Only One)")
        unique_layout = QVBoxLayout()
        
        self.compare_unique_table = QTableWidget()
        self.compare_unique_table.setColumnCount(4)
        self.compare_unique_table.setHorizontalHeaderLabels([
            "Item", "Found In", "Quantity", "% Chance"
        ])
        self.compare_unique_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        unique_layout.addWidget(self.compare_unique_table)
        
        unique_group.setLayout(unique_layout)
        layout.addWidget(unique_group)
        
        widget.setLayout(layout)
        return widget
    
    def update_compare_locations1(self, map_name):
        """Update location dropdown 1 based on selected map"""
        self.compare_location1.clear()
        self.compare_location1.addItem("All")
        
        if map_name != "All" and map_name in self.maps_data:
            locations = list(self.maps_data[map_name].get('locations', {}).keys())
            self.compare_location1.addItems(locations)
    
    def update_compare_locations2(self, map_name):
        """Update location dropdown 2 based on selected map"""
        self.compare_location2.clear()
        self.compare_location2.addItem("All")
        
        if map_name != "All" and map_name in self.maps_data:
            locations = list(self.maps_data[map_name].get('locations', {}).keys())
            self.compare_location2.addItems(locations)
    
    def refresh_comparison(self):
        """Refresh the container comparison"""
        container1 = self.compare_container1.currentText()
        condition1 = self.compare_condition1.currentText()
        map1 = self.compare_map1.currentText()
        location1 = self.compare_location1.currentText()
        container2 = self.compare_container2.currentText()
        condition2 = self.compare_condition2.currentText()
        map2 = self.compare_map2.currentText()
        location2 = self.compare_location2.currentText()
        
        if container1 == container2 and condition1 == condition2 and map1 == map2 and location1 == location2:
            QMessageBox.warning(self, "Same Selection", "Please select different containers, conditions, maps, or locations to compare")
            return
        
        # Get loot data for both containers
        loot1, total1 = self.db.get_container_loot_for_comparison(container1, map1, location1, condition1)
        loot2, total2 = self.db.get_container_loot_for_comparison(container2, map2, location2, condition2)
        
        if not loot1 and not loot2:
            QMessageBox.information(self, "No Data", "No loot data found for selected containers")
            return
        
        # Build descriptive names
        name1 = container1
        if condition1 != "All":
            name1 += f" ({condition1}"
            if map1 != "All":
                name1 += f", {map1}"
                if location1 != "All":
                    name1 += f", {location1}"
            elif location1 != "All":
                name1 += f", {location1}"
            name1 += ")"
        elif map1 != "All":
            name1 += f" ({map1}"
            if location1 != "All":
                name1 += f", {location1}"
            name1 += ")"
        elif location1 != "All":
            name1 += f" ({location1})"
        
        name2 = container2
        if condition2 != "All":
            name2 += f" ({condition2}"
            if map2 != "All":
                name2 += f", {map2}"
                if location2 != "All":
                    name2 += f", {location2}"
            elif location2 != "All":
                name2 += f", {location2}"
            name2 += ")"
        elif map2 != "All":
            name2 += f" ({map2}"
            if location2 != "All":
                name2 += f", {location2}"
            name2 += ")"
        elif location2 != "All":
            name2 += f" ({location2})"
        
        # Update table headers with container names
        self.compare_common_table.setHorizontalHeaderLabels([
            "Item",
            f"{name1} Qty",
            f"{name1} %",
            f"{name2} Qty",
            f"{name2} %"
        ])
        
        # Find common and unique items
        all_items = set(loot1.keys()) | set(loot2.keys())
        common_items = set(loot1.keys()) & set(loot2.keys())
        unique_items = all_items - common_items
        
        # Populate common items table
        self.compare_common_table.setRowCount(len(common_items))
        for row, item in enumerate(sorted(common_items)):
            data1 = loot1[item]
            data2 = loot2[item]
            
            self.compare_common_table.setItem(row, 0, QTableWidgetItem(item))
            
            # Container 1 quantity
            if data1['min_qty'] == data1['max_qty']:
                qty1_text = str(data1['min_qty'])
            else:
                qty1_text = f"{data1['min_qty']}-{data1['max_qty']}"
            self.compare_common_table.setItem(row, 1, QTableWidgetItem(qty1_text))
            
            # Container 1 percentage
            self.compare_common_table.setItem(row, 2, QTableWidgetItem(f"{data1['percentage']:.1f}%"))
            
            # Container 2 quantity
            if data2['min_qty'] == data2['max_qty']:
                qty2_text = str(data2['min_qty'])
            else:
                qty2_text = f"{data2['min_qty']}-{data2['max_qty']}"
            self.compare_common_table.setItem(row, 3, QTableWidgetItem(qty2_text))
            
            # Container 2 percentage
            self.compare_common_table.setItem(row, 4, QTableWidgetItem(f"{data2['percentage']:.1f}%"))
        
        # Populate unique items table
        self.compare_unique_table.setRowCount(len(unique_items))
        unique_list = []
        
        for item in unique_items:
            if item in loot1:
                data = loot1[item]
                found_in = name1
            else:
                data = loot2[item]
                found_in = name2
            
            unique_list.append((item, found_in, data))
        
        # Sort by item name
        unique_list.sort(key=lambda x: x[0])
        
        for row, (item, found_in, data) in enumerate(unique_list):
            self.compare_unique_table.setItem(row, 0, QTableWidgetItem(item))
            self.compare_unique_table.setItem(row, 1, QTableWidgetItem(found_in))
            
            # Quantity
            if data['min_qty'] == data['max_qty']:
                qty_text = str(data['min_qty'])
            else:
                qty_text = f"{data['min_qty']}-{data['max_qty']}"
            self.compare_unique_table.setItem(row, 2, QTableWidgetItem(qty_text))
            
            # Percentage
            self.compare_unique_table.setItem(row, 3, QTableWidgetItem(f"{data['percentage']:.1f}%"))
    
    def create_stats_tab(self):
        """Create the statistics tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Period selector
        period_layout = QHBoxLayout()
        period_layout.addWidget(QLabel("Show stats for last:"))
        self.period_combo = QComboBox()
        self.period_combo.addItems(["7 days", "14 days", "30 days", "All time"])
        self.period_combo.currentTextChanged.connect(self.refresh_statistics)
        period_layout.addWidget(self.period_combo)
        period_layout.addStretch()
        layout.addLayout(period_layout)
        
        # Stats display
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        layout.addWidget(self.stats_text)
        
        widget.setLayout(layout)
        
        self.refresh_statistics()
        
        return widget
    
    def create_loot_table_tab(self):
        """Create the advanced loot table tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Container selection
        container_group = QGroupBox("Select Container")
        container_layout = QHBoxLayout()
        
        container_layout.addWidget(QLabel("Container:"))
        self.loot_table_container = QComboBox()
        self.loot_table_container.addItems(self.containers)
        container_layout.addWidget(self.loot_table_container)
        
        container_layout.addStretch()
        container_group.setLayout(container_layout)
        layout.addWidget(container_group)
        
        # Filters
        filter_group = QGroupBox("Filters")
        filter_layout = QGridLayout()
        
        filter_layout.addWidget(QLabel("Map:"), 0, 0)
        self.loot_table_map = QComboBox()
        self.loot_table_map.addItem("All")
        self.loot_table_map.addItems(list(self.maps_data.keys()))
        filter_layout.addWidget(self.loot_table_map, 0, 1)
        
        filter_layout.addWidget(QLabel("Location:"), 0, 2)
        self.loot_table_location = QComboBox()
        self.loot_table_location.addItem("All")
        filter_layout.addWidget(self.loot_table_location, 0, 3)
        
        filter_layout.addWidget(QLabel("Tier:"), 1, 0)
        self.loot_table_tier = QComboBox()
        self.loot_table_tier.addItems(["All", "None", "Yellow", "Red"])
        filter_layout.addWidget(self.loot_table_tier, 1, 1)
        
        # Update button
        update_btn = QPushButton("🔄 Update Table")
        update_btn.clicked.connect(self.refresh_loot_table)
        filter_layout.addWidget(update_btn, 1, 2, 1, 2)
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # Table
        self.loot_table = QTableWidget()
        self.loot_table.setColumnCount(4)
        self.loot_table.setHorizontalHeaderLabels(["Item", "Quantity", "Categories", "% Chance"])
        self.loot_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.loot_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.loot_table)
        
        # Connect map change to update locations
        self.loot_table_map.currentTextChanged.connect(self.update_loot_table_locations)
        
        widget.setLayout(layout)
        return widget
    
    def create_container_locations_tab(self):
        """Create the container locations tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Container selection
        container_layout = QHBoxLayout()
        container_layout.addWidget(QLabel("Select Container:"))
        self.container_locations_combo = QComboBox()
        self.container_locations_combo.addItems(self.containers)
        self.container_locations_combo.currentTextChanged.connect(self.refresh_container_locations)
        container_layout.addWidget(self.container_locations_combo)
        
        show_btn = QPushButton("🔍 Show Locations")
        show_btn.clicked.connect(self.refresh_container_locations)
        container_layout.addWidget(show_btn)
        
        container_layout.addStretch()
        layout.addLayout(container_layout)
        
        # Table
        self.container_locations_table = QTableWidget()
        self.container_locations_table.setColumnCount(5)
        self.container_locations_table.setHorizontalHeaderLabels([
            "Map", "Location", "Tier", "Categories", "Times Found"
        ])
        self.container_locations_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.container_locations_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.container_locations_table)
        
        widget.setLayout(layout)
        return widget
    
    def create_item_containers_tab(self):
        """Create the item to containers tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Item selection
        item_layout = QHBoxLayout()
        item_layout.addWidget(QLabel("Select Item:"))
        self.item_combo = QComboBox()
        self.item_combo.currentTextChanged.connect(self.refresh_item_containers)
        item_layout.addWidget(self.item_combo)
        
        show_btn = QPushButton("🔍 Show Containers")
        show_btn.clicked.connect(self.refresh_item_containers)
        item_layout.addWidget(show_btn)
        
        item_layout.addStretch()
        layout.addLayout(item_layout)
        
        # Info label
        self.item_info_label = QLabel()
        self.item_info_label.setStyleSheet("font-size: 12px; padding: 8px; background: #e3f2fd;")
        layout.addWidget(self.item_info_label)
        
        # Table
        self.item_containers_table = QTableWidget()
        self.item_containers_table.setColumnCount(5)
        self.item_containers_table.setHorizontalHeaderLabels([
            "Container", "Min Qty", "Max Qty", "Times Found", "% Chance"
        ])
        self.item_containers_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.item_containers_table)
        
        widget.setLayout(layout)
        
        # Load initial items
        self.load_items_combo()
        
        return widget
    
    def update_loot_table_locations(self, map_name):
        """Update location dropdown based on selected map"""
        self.loot_table_location.clear()
        self.loot_table_location.addItem("All")
        
        if map_name != "All" and map_name in self.maps_data:
            locations = list(self.maps_data[map_name].get('locations', {}).keys())
            self.loot_table_location.addItems(locations)
    
    def refresh_loot_table(self):
        """Refresh the advanced loot table"""
        container = self.loot_table_container.currentText()
        map_filter = self.loot_table_map.currentText()
        location_filter = self.loot_table_location.currentText()
        tier_filter = self.loot_table_tier.currentText()
        
        data = self.db.get_loot_table_data(container, map_filter, location_filter, tier_filter)
        
        self.loot_table.setRowCount(len(data))
        
        for row, item in enumerate(data):
            # Item name
            self.loot_table.setItem(row, 0, QTableWidgetItem(item['item']))
            
            # Quantity range
            if item['min_qty'] == item['max_qty']:
                qty_text = str(item['min_qty'])
            else:
                qty_text = f"{item['min_qty']} - {item['max_qty']}"
            self.loot_table.setItem(row, 1, QTableWidgetItem(qty_text))
            
            # Categories
            categories_text = ", ".join(item['categories']) if item['categories'] else "None"
            self.loot_table.setItem(row, 2, QTableWidgetItem(categories_text))
            
            # Percentage
            self.loot_table.setItem(row, 3, QTableWidgetItem(f"{item['percentage']:.1f}%"))
    
    def refresh_container_locations(self):
        """Refresh the container locations table"""
        container = self.container_locations_combo.currentText()
        
        data = self.db.get_container_locations(container)
        
        self.container_locations_table.setRowCount(len(data))
        
        for row, item in enumerate(data):
            self.container_locations_table.setItem(row, 0, QTableWidgetItem(item['map']))
            self.container_locations_table.setItem(row, 1, QTableWidgetItem(item['location']))
            self.container_locations_table.setItem(row, 2, QTableWidgetItem(item['tier']))
            
            categories_text = ", ".join(item['categories']) if item['categories'] else "None"
            self.container_locations_table.setItem(row, 3, QTableWidgetItem(categories_text))
            
            self.container_locations_table.setItem(row, 4, QTableWidgetItem(str(item['times_found'])))
    
    def load_items_combo(self):
        """Load all items into the items combo box"""
        items = self.db.get_all_items()
        self.item_combo.clear()
        if items:
            self.item_combo.addItems(items)
        else:
            self.item_combo.addItem("No items found yet")
    
    def refresh_item_containers(self):
        """Refresh the item containers table"""
        item_name = self.item_combo.currentText()
        
        if item_name == "No items found yet":
            self.item_containers_table.setRowCount(0)
            self.item_info_label.setText("No data available")
            return
        
        data, total_sessions = self.db.get_item_container_stats(item_name)
        
        self.item_containers_table.setRowCount(len(data))
        
        # Update info label
        self.item_info_label.setText(f"Item: <b>{item_name}</b> | Found in <b>{total_sessions}</b> sessions")
        
        for row, item in enumerate(data):
            self.item_containers_table.setItem(row, 0, QTableWidgetItem(item['container']))
            
            # Quantity range
            if item['min_qty'] == item['max_qty']:
                qty_text = str(item['min_qty'])
            else:
                qty_text = f"{item['min_qty']} - {item['max_qty']}"
            self.item_containers_table.setItem(row, 1, QTableWidgetItem(str(item['min_qty'])))
            self.item_containers_table.setItem(row, 2, QTableWidgetItem(str(item['max_qty'])))
            
            self.item_containers_table.setItem(row, 3, QTableWidgetItem(str(item['times_found'])))
            
            self.item_containers_table.setItem(row, 4, QTableWidgetItem(f"{item['percentage']:.1f}%"))
    
    def on_map_changed(self, map_name):
        """Update locations when map changes"""
        if map_name in self.maps_data:
            locations = list(self.maps_data[map_name].get('locations', {}).keys())
            self.location_combo.clear()
            self.location_combo.addItems(locations)
    
    def start_scan(self):
        """Start the scanning process"""
        map_name = self.map_combo.currentText()
        condition = self.condition_combo.currentText()
        location = self.location_combo.currentText()
        container = self.container_combo.currentText()
        grid_count = self.grid_spin.value()
        
        if not all([map_name, condition, location, container]):
            QMessageBox.warning(self, "Incomplete", "Please fill all fields")
            return
        
        # Open scan dialog
        dialog = ScanDialog(self.grid_calculator, grid_count, self.matcher, self)
        dialog.scan_complete.connect(
            lambda loot: self.save_scan(map_name, condition, location, container, loot)
        )
        dialog.exec()
    
    def save_scan(self, map_name, condition, location, container, loot_data):
        """Save scan results to database"""
        if not loot_data:
            return
        
        try:
            # Get tier and categories from maps.json
            tier = "None"
            categories = []
            
            if map_name in self.maps_data:
                locations = self.maps_data[map_name].get('locations', {})
                if location in locations:
                    tier = locations[location].get('tier', 'None')
                    categories = locations[location].get('category', [])
            
            session_id = self.db.add_session(map_name, condition, location, container, tier, categories, loot_data)
            
            # Log success without popup
            items_str = ', '.join([f"{name} x{qty}" for name, qty in loot_data.items()])
            logger.info(f"Scan saved - Session {session_id}: {items_str}")
            
            # Refresh all relevant tabs
            self.refresh_today_sessions()
            self.refresh_statistics()
            self.refresh_total_containers()
            self.load_items_combo()
            self.refresh_base_loot()
            
        except Exception as e:
            logger.error(f"Failed to save scan: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
    
    def repeat_last_scan(self):
        """Repeat the last scan with same settings"""
        sessions = self.db.get_today_sessions()
        if not sessions:
            QMessageBox.information(self, "No History", "No previous scans today")
            return
        
        last = sessions[0]
        self.map_combo.setCurrentText(last[1])
        self.condition_combo.setCurrentText(last[2])
        self.location_combo.setCurrentText(last[3])
        self.container_combo.setCurrentText(last[4])
        
        QMessageBox.information(self, "Settings Loaded", "Previous scan settings loaded. Click 'Start Scan' to begin.")
    
    def refresh_today_sessions(self):
        """Refresh the today's sessions table"""
        sessions = self.db.get_today_sessions()
        
        self.history_table.setRowCount(len(sessions))
        
        for row, session in enumerate(sessions):
            session_id, map_name, condition, location, container, tier, timestamp, items = session
            
            self.history_table.setItem(row, 0, QTableWidgetItem(str(session_id)))
            self.history_table.setItem(row, 1, QTableWidgetItem(map_name))
            self.history_table.setItem(row, 2, QTableWidgetItem(condition))
            self.history_table.setItem(row, 3, QTableWidgetItem(location))
            self.history_table.setItem(row, 4, QTableWidgetItem(container))
            self.history_table.setItem(row, 5, QTableWidgetItem(tier))
            self.history_table.setItem(row, 6, QTableWidgetItem(items or "No items"))
            
            # Delete button
            delete_btn = QPushButton("🗑️ Delete")
            delete_btn.clicked.connect(lambda checked, sid=session_id: self.delete_session(sid))
            self.history_table.setCellWidget(row, 7, delete_btn)
    
    def refresh_container_history(self):
        """Refresh the container history table"""
        container = self.container_history_combo.currentText()
        period_text = self.container_history_period.currentText()
        
        # Map period to days
        days_map = {
            "Today": 0,
            "Last 7 Days": 7,
            "Last 14 Days": 14,
            "All Time": None
        }
        days = days_map.get(period_text)
        
        sessions = self.db.get_sessions_by_container(container, days)
        
        self.container_history_table.setRowCount(len(sessions))
        
        for row, session in enumerate(sessions):
            session_id, map_name, condition, location, container_name, tier, timestamp, items = session
            
            self.container_history_table.setItem(row, 0, QTableWidgetItem(str(session_id)))
            self.container_history_table.setItem(row, 1, QTableWidgetItem(map_name))
            self.container_history_table.setItem(row, 2, QTableWidgetItem(condition))
            self.container_history_table.setItem(row, 3, QTableWidgetItem(location))
            self.container_history_table.setItem(row, 4, QTableWidgetItem(container_name))
            self.container_history_table.setItem(row, 5, QTableWidgetItem(tier))
            self.container_history_table.setItem(row, 6, QTableWidgetItem(items or "No items"))
            
            # Delete button
            delete_btn = QPushButton("🗑️ Delete")
            delete_btn.clicked.connect(lambda checked, sid=session_id: self.delete_session(sid))
            self.container_history_table.setCellWidget(row, 7, delete_btn)
    
    def refresh_base_loot(self):
        """Refresh the common vs rare loot tables"""
        container = self.base_loot_container.currentText()
        
        common_loot, rare_loot, rare_locations = self.db.get_base_and_rare_loot(container)
        
        # Populate common loot table
        self.base_loot_table.setRowCount(len(common_loot))
        for row, (item_name, data) in enumerate(sorted(common_loot.items())):
            self.base_loot_table.setItem(row, 0, QTableWidgetItem(item_name))
            self.base_loot_table.setItem(row, 1, QTableWidgetItem(str(data['min_qty'])))
            self.base_loot_table.setItem(row, 2, QTableWidgetItem(str(data['max_qty'])))
            self.base_loot_table.setItem(row, 3, QTableWidgetItem(str(data['locations_count'])))
        
        # Populate rare loot table
        self.rare_loot_table.setRowCount(len(rare_loot))
        for row, (item_name, data) in enumerate(sorted(rare_loot.items())):
            self.rare_loot_table.setItem(row, 0, QTableWidgetItem(item_name))
            self.rare_loot_table.setItem(row, 1, QTableWidgetItem(str(data['min_qty'])))
            self.rare_loot_table.setItem(row, 2, QTableWidgetItem(str(data['max_qty'])))
            self.rare_loot_table.setItem(row, 3, QTableWidgetItem(str(data['locations_count'])))
            
            # Build location string
            locations = rare_locations.get(item_name, [])
            location_text = ", ".join(locations)
            self.rare_loot_table.setItem(row, 4, QTableWidgetItem(location_text))
            self.rare_loot_table.setItem(row, 5, QTableWidgetItem(location_text))
    
    def delete_session(self, session_id):
        """Delete a session"""
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete session {session_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_session(session_id)
                self.refresh_today_sessions()
                self.refresh_statistics()
                self.refresh_total_containers()
                self.load_items_combo()
                self.refresh_base_loot()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")
    
    def refresh_statistics(self):
        """Refresh statistics display"""
        period_text = self.period_combo.currentText()
        days = {'7 days': 7, '14 days': 14, '30 days': 30, 'All time': 3650}[period_text]
        
        stats = self.db.get_statistics(days)
        
        text = f"<h2>Statistics - Last {period_text}</h2>"
        text += "<table border='1' cellpadding='5' style='border-collapse: collapse;'>"
        text += "<tr><th>Item</th><th>Total Quantity</th><th>Found In Sessions</th><th>Map</th></tr>"
        
        for item_name, total_qty, sessions_count, map_name in stats:
            text += f"<tr><td>{item_name}</td><td>{total_qty}</td><td>{sessions_count}</td><td>{map_name}</td></tr>"
        
        text += "</table>"
        
        if not stats:
            text += "<p>No data for this period.</p>"
        
        self.stats_text.setHtml(text)


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    
    # Set modern style
    app.setStyle('Fusion')
    
    window = LootTrackerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()