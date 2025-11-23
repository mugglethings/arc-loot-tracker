# ARC LOOT TABLE INPUT ENGINE (ARCLTIE)

A Python application for logging game loot from containers using automated screenshot recognition.

## TODO

Make the program be able to recognize numbers for numbering quantity

refine script?

eventually make it web based... maybe?

## Requirements

- Windows 11
- [Python 3.8+](https://www.python.org/downloads/)
- Screen resolution: 1920x1080

## Installation

1. Install Python dependencies:
```bashd
pip install -r requirements.txt
```

2. Create the required data structure:
```
project/
├── data/
│   ├── maps.json
│   ├── containers.json
│   ├── condition.json
│   ├── grid.json
│   └── items.json (created automatically if missing)
├── loot_tracker.py
└── requirements.txt
```

## How to Use

### First Time Setup

1. Ensure your `data/` folder contains:
   - `maps.json` - Map names and their locations
   - `containers.json` - List of container types
   - `condition.json` - List of conditions (e.g., day/night)
   - `grid.json` - Grid cell coordinates for screenshot analysis

2. Run the application:
```bash
python loot_tracker.py
```

### Recording Loot

1. **Select Map**: Choose from dropdown menu (e.g., dam, buried, space)
   - Click `Next` to continue

2. **Select Condition**: Choose game condition (e.g., night, day)
   - Click `Restart` to go back to map selection
   - Click `Next` to continue

3. **Select Location**: Choose location within the selected map
   - Click `Restart` to go back to map selection
   - Click `Next` to continue

4. **Select Container**: Choose container type and grid size
   - Enter number of grid cells to scan (1-12)
   - Click `Start Scan`

5. **Capture Screenshot**:
   - Position your game window to show the loot grid
   - Press `F8` to capture screenshot
   - Application automatically analyzes the grid

6. **Handle Unknown Items**:
   - If an item is not recognized, you'll be prompted to name it
   - Enter item name (e.g., `metal` for metal)
   - The item template is saved for future recognition

7. **Continue or Finish**:
   - Choose "Yes" to scan another container in the same location
   - Choose "No" to finish and start over

### Output Format

Loot data is saved to `loot.txt` as comma-separated values:

```
map,condition,location,container,item1,quantity1,item2,quantity2,...
```

Example:
```
dam,night,control tower,server rack,metal,5,medical bandage,1,circuit board,2
dam,night,water treatment,metal crate,key,1,bandage,1,grenade,1
```

## File Structure After First Run

```
project/
├── data/
│   ├── maps.json
│   ├── containers.json
│   ├── condition.json
│   ├── grid.json
│   └── items.json
├── templates/
│   └── items/
│       ├── metal.png
│       ├── bandage.png
│       └── ... (auto-generated)
├── loot.txt (output file)
├── loot_tracker.log (application log)
├── loot_tracker.py
└── requirements.txt
```

## Tips

- **Item Recognition**: The first time you encounter an item, you'll need to name it. Subsequent encounters will be automatic.
- **Screenshot Timing**: Ensure the loot grid is fully visible and not obscured when pressing F8.

## Troubleshooting

- **No items recognized**: Check that `grid.json` coordinates match your screen resolution
- **Wrong items detected**: Delete incorrect templates from `templates/items/` folder
- **Application crashes**: Check `loot_tracker.log` for error details
- **F8 not working**: Prob just spam it. Sometimes works after 3 clicks

## Todo

Script a table generation script using the data gathered