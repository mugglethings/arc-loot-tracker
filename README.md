# ARC LOOT TRACKER - PyQt6 Version

A modern PyQt6-based application for tracking loot from game containers with comprehensive analytics. Features automatic screenshot capture, item recognition, and advanced data analysis across 10 different views.

## Requirements

- Windows 10/11
- [Python 3.8+](https://www.python.org/downloads/)
- Screen resolution: 2560x1440 (configured for this resolution)

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## How to Use

### First Time Setup

1. Ensure your `data/` folder contains:
   - `maps.json` - Map definitions with location lists
   - `containers.json` - Container types available in the game
   - `condition.json` - Game conditions (e.g., night, day)
   - `room.json` - Room/location definitions

2. Run the application:
```bash
python loot_tracker.py
```

The database (`loot_tracker.db`) and item templates folder will be created automatically.

## Main Features

The application has 10 analysis tabs:

1. **📸 Quick Scan** - Start new loot scanning sessions
   - Select map, condition, location, and container
   - Configure grid size (1-48 cells)
   - Automatically captures screenshot when dialog opens

2. **📋 Today's Loot** - View all sessions from today
   - Shows items found with quantities
   - Delete sessions you want to remove

3. **📜 Container History** - Filter sessions by container and time period
   - Today, Last 7/14 days, or All time

4. **🎯 Common vs Unique Loot** - Analyze container drops
   - Common loot: appears in all map/location combinations
   - Unique loot: appears only in specific locations
   - Shows where unique items are found

5. **📊 Statistics** - Item frequency analytics
   - Configurable time periods (7/14/30 days or all time)
   - Grouped by item and map

6. **🔍 Advanced Loot Table** - Detailed container analysis
   - Filter by map, location, and tier
   - Shows min/max quantities and categories

7. **🔎 Item to Containers** - Reverse lookup
   - See which containers have a specific item
   - Shows drop percentages

8. **📍 Container Locations** - Geographic analysis
   - Where containers are found on maps
   - Location, tier, and category information

9. **📦 Total Containers** - Global statistics
   - How many times each container has been scanned

10. **⚖️ Compare Containers** - Side-by-side analysis
    - Compare two containers with optional map/location filters
    - See common and unique items

## Recording Loot Workflow

1. Go to the **📸 Quick Scan** tab
2. Fill in:
   - Map (auto-populated from maps.json)
   - Condition (day/night/etc)
   - Location (auto-populated based on selected map)
   - Container type
   - Grid cells to scan (number of cells visible)

3. Click **"🔍 Start Scan"**
   - Dialog opens and automatically captures a screenshot
   - Shows preview of each cell
   - Uses template matching to recognize items

4. For each cell:
   - Review recognized item (or type new name)
   - Enter quantity
   - Click **Confirm Item** to save and move to next
   - Or click **Skip Cell** to skip empty/unknown cells

5. When done with all cells, click **Finish Scan**
   - Session is saved to database with timestamp
   - Item templates are updated for future recognition

## Item Recognition

- Uses template-based matching (MSE algorithm)
- Saves recognized items as PNG templates in `data/items/`
- Improves with more scanning - more templates = better recognition
- Falls back to manual entry if item not recognized

## Database

Data is stored in SQLite database (`loot_tracker.db`) with two main tables:
- `sessions` - Scan sessions with metadata (map, location, container, timestamp, etc)
- `loot_items` - Individual items from each session

All queries support filters and time ranges for flexible analysis.

## Tips

- **Improving Recognition**: The more you scan, the more item templates are saved, so recognition gets better over time
- **Screenshot Quality**: Ensure your game window is properly positioned so the inventory grid is fully visible
- **Database Backup**: Consider backing up `loot_tracker.db` regularly to preserve your data

## Troubleshooting

- **Items not recognized**: This is normal at first. Type the item name and continue - the template is saved for next time
- **Wrong coordinates in screenshots**: Grid coordinates are fixed for 2560x1440 resolution. Adjust if using different resolution
- **Application crashes**: Check `loot_tracker.log` for error details

## File Structure After First Run

```
project/
├── data/
│   ├── maps.json
│   ├── containers.json
│   ├── condition.json
│   ├── room.json
│   └── items/
│       ├── metal.png
│       ├── bandage.png
│       └── ... (auto-generated from scans)
├── loot_tracker.py       - Main application
├── loot_tracker.db        - SQLite database with sessions and items
├── loot_tracker.log       - Application log
├── requirements.txt
└── README.md
```
