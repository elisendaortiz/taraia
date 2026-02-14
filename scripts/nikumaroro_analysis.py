#!/usr/bin/env python3
"""
Nikumaroro Taraia Object Satellite Image Analysis
Retrieves and processes satellite imagery to track the Taraia Object over time

Installation:
    pip install earthengine-api geemap pillow numpy matplotlib requests

First-time setup:
    earthengine authenticate

Usage:
    python nikumaroro_analysis.py
"""

import ee
import geemap
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import requests
from PIL import Image
import io

# ============================================================================
# CONFIGURATION
# ============================================================================

# Taraia Object location (northwest lagoon, Nikumaroro Island)
# Coordinates: 4°41'10.2"S 174°29'53.1"W
# Converted from DMS (Degrees Minutes Seconds) to decimal degrees
TARAIA_LAT = -4.686167  # 4°41'10.2"S (negative for South)
TARAIA_LON = -174.498083  # 174°29'53.1"W (negative for West)
BUFFER_KM = 0.3  # Area around the point to capture (300m radius)

# Output directory
OUTPUT_DIR = Path("nikumaroro_imagery")
OUTPUT_DIR.mkdir(exist_ok=True)

# Date range for analysis
START_YEAR = 2013
END_YEAR = 2024

# ============================================================================
# METHOD 1: Google Earth Engine (Sentinel-2)
# ============================================================================

def initialize_earth_engine():
    """Initialize Google Earth Engine - requires authentication"""
    try:
        ee.Initialize()
        print("✓ Earth Engine initialized")
    except:
        print("! Authenticating Earth Engine (first time only)...")
        ee.Authenticate()
        ee.Initialize()
        print("✓ Earth Engine authenticated and initialized")

def get_bbox(lat, lon, buffer_km):
    """Create bounding box around point"""
    # Rough conversion: 1 degree ≈ 111 km
    buffer_deg = buffer_km / 111.0
    return [
        lon - buffer_deg,  # west
        lat - buffer_deg,  # south
        lon + buffer_deg,  # east
        lat + buffer_deg   # north
    ]

def download_sentinel2_images():
    """Download Sentinel-2 imagery using Google Earth Engine"""
    
    initialize_earth_engine()
    
    bbox = get_bbox(TARAIA_LAT, TARAIA_LON, BUFFER_KM)
    roi = ee.Geometry.Rectangle(bbox)
    
    # Get available Sentinel-2 images
    collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                  .filterBounds(roi)
                  .filterDate(f'{START_YEAR}-01-01', f'{END_YEAR}-12-31')
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))
    
    # Get image dates
    dates = collection.aggregate_array('system:time_start').getInfo()
    
    print(f"Found {len(dates)} Sentinel-2 images")
    
    images_info = []
    
    for i, date_ms in enumerate(dates[:50]):  # Limit to 50 most recent
        date = datetime.fromtimestamp(date_ms / 1000)
        date_str = date.strftime('%Y-%m-%d')
        
        img = (collection.filterDate(date_str, (date + timedelta(days=1)).strftime('%Y-%m-%d'))
               .first())
        
        # RGB visualization
        vis_params = {
            'min': 0,
            'max': 3000,
            'bands': ['B4', 'B3', 'B2'],  # RGB
            'region': roi,
            'dimensions': 1024,
            'format': 'png'
        }
        
        try:
            url = img.getThumbURL(vis_params)
            
            # Download image
            response = requests.get(url)
            if response.status_code == 200:
                filepath = OUTPUT_DIR / f"sentinel2_{date_str.replace('-', '')}.png"
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                images_info.append({
                    'date': date_str,
                    'timestamp': date_ms,
                    'filename': filepath.name,
                    'source': 'Sentinel-2'
                })
                
                print(f"  Downloaded: {date_str}")
        except Exception as e:
            print(f"  Failed {date_str}: {e}")
    
    return images_info

# ============================================================================
# METHOD 2: Sentinel Hub (Alternative - requires API key)
# ============================================================================

def download_sentinel_hub_images(api_key=None):
    """
    Alternative method using Sentinel Hub API
    Sign up at: https://www.sentinel-hub.com/
    """
    if not api_key:
        print("! Sentinel Hub requires API key - skipping")
        return []
    
    # Implementation for Sentinel Hub API would go here
    # More reliable than Earth Engine for automated downloads
    pass

# ============================================================================
# METHOD 3: Static Satellite Imagery Providers
# ============================================================================

def download_static_satellite_tiles():
    """
    Download tiles from public satellite imagery providers
    Using XYZ tile servers (OpenStreetMap style)
    """
    
    # Convert lat/lon to tile coordinates at zoom level 18
    def lat_lon_to_tile(lat, lon, zoom):
        n = 2.0 ** zoom
        x = int((lon + 180.0) / 360.0 * n)
        y = int((1.0 - np.log(np.tan(np.radians(lat)) + 1.0 / np.cos(np.radians(lat))) / np.pi) / 2.0 * n)
        return x, y
    
    zoom = 18  # High detail
    x, y = lat_lon_to_tile(TARAIA_LAT, TARAIA_LON, zoom)
    
    # Try multiple tile servers
    tile_servers = {
        'esri_world': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        'google_satellite': 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
    }
    
    images_info = []
    
    for name, url_template in tile_servers.items():
        url = url_template.format(z=zoom, x=x, y=y)
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                filepath = OUTPUT_DIR / f"{name}_z{zoom}.png"
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                images_info.append({
                    'date': 'current',
                    'filename': filepath.name,
                    'source': name,
                    'zoom': zoom
                })
                
                print(f"✓ Downloaded: {name}")
        except Exception as e:
            print(f"✗ Failed {name}: {e}")
    
    return images_info

# ============================================================================
# IMAGE ALIGNMENT AND REGISTRATION
# ============================================================================

def align_images(images_info):
    """
    Align all images to the same coordinate system
    Uses feature matching or simple resize/crop
    """
    
    if not images_info:
        print("! No images to align")
        return []
    
    # Load all images
    images = []
    for info in images_info:
        filepath = OUTPUT_DIR / info['filename']
        if filepath.exists():
            img = Image.open(filepath)
            images.append(np.array(img))
    
    if not images:
        return []
    
    # Get reference size (first image)
    ref_height, ref_width = images[0].shape[:2]
    
    # Resize all to match reference
    aligned_images = []
    for i, img in enumerate(images):
        if img.shape[:2] != (ref_height, ref_width):
            pil_img = Image.fromarray(img)
            pil_img = pil_img.resize((ref_width, ref_height), Image.Resampling.LANCZOS)
            img = np.array(pil_img)
        
        # Save aligned version
        aligned_path = OUTPUT_DIR / f"aligned_{images_info[i]['filename']}"
        Image.fromarray(img).save(aligned_path)
        
        aligned_images.append({
            **images_info[i],
            'aligned_filename': aligned_path.name,
            'width': ref_width,
            'height': ref_height
        })
    
    print(f"✓ Aligned {len(aligned_images)} images to {ref_width}x{ref_height}")
    
    return aligned_images

# ============================================================================
# OUTPUT FOR INTERACTIVE VIEWER
# ============================================================================

def create_viewer_config(aligned_images):
    """
    Create JSON configuration for interactive slider viewer
    """
    
    # Sort by date
    aligned_images.sort(key=lambda x: x.get('timestamp', 0) or x.get('date', ''))
    
    config = {
        'location': {
            'name': 'Taraia Object, Nikumaroro Island',
            'lat': TARAIA_LAT,
            'lon': TARAIA_LON,
            'description': 'Suspected location of Amelia Earhart\'s Lockheed Electra 10E'
        },
        'images': aligned_images,
        'metadata': {
            'generated': datetime.now().isoformat(),
            'total_images': len(aligned_images),
            'date_range': {
                'start': aligned_images[0].get('date', 'unknown'),
                'end': aligned_images[-1].get('date', 'unknown')
            }
        }
    }
    
    config_path = OUTPUT_DIR / 'viewer_config.json'
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"✓ Saved viewer config to {config_path}")
    
    return config

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """
    Main execution pipeline
    """
    
    print("="*70)
    print("NIKUMARORO TARAIA OBJECT - SATELLITE IMAGE ANALYSIS")
    print("="*70)
    print(f"\nTarget: {TARAIA_LAT}, {TARAIA_LON}")
    print(f"Output: {OUTPUT_DIR}\n")
    
    all_images = []
    
    # Method 1: Try Google Earth Engine (Sentinel-2)
    print("\n[1/3] Attempting Google Earth Engine download...")
    try:
        gee_images = download_sentinel2_images()
        all_images.extend(gee_images)
    except Exception as e:
        print(f"! Earth Engine failed: {e}")
        print("  → Install: pip install earthengine-api")
        print("  → Authenticate: earthengine authenticate")
    
    # Method 2: Static satellite tiles (always works)
    print("\n[2/3] Downloading static satellite imagery...")
    static_images = download_static_satellite_tiles()
    all_images.extend(static_images)
    
    # Method 3: Align all images
    print("\n[3/3] Aligning images...")
    aligned_images = align_images(all_images)
    
    # Create viewer configuration
    if aligned_images:
        config = create_viewer_config(aligned_images)
        
        print("\n" + "="*70)
        print("✓ ANALYSIS COMPLETE")
        print("="*70)
        print(f"Total images: {len(aligned_images)}")
        print(f"Output directory: {OUTPUT_DIR}")
        print(f"Config file: {OUTPUT_DIR / 'viewer_config.json'}")
        print("\nNext step: Upload viewer_config.json to Claude for interactive viewer")
    else:
        print("\n✗ No images downloaded. Check authentication and internet connection.")
    
    return config if aligned_images else None

# ============================================================================
# JUPYTER NOTEBOOK FRIENDLY
# ============================================================================

if __name__ == "__main__":
    # Run the pipeline
    config = main()
    
    # Display sample if available
    if config and config['images']:
        print("\n" + "="*70)
        print("PREVIEW")
        print("="*70)
        
        # Show first and last image
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        for idx, (ax, img_info) in enumerate(zip(axes, [config['images'][0], config['images'][-1]])):
            if 'aligned_filename' in img_info:
                img_path = OUTPUT_DIR / img_info['aligned_filename']
            else:
                img_path = OUTPUT_DIR / img_info['filename']
            
            if img_path.exists():
                img = Image.open(img_path)
                ax.imshow(img)
                ax.set_title(f"{img_info['date']} ({img_info['source']})")
                ax.axis('off')
        
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / 'preview.png', dpi=150, bbox_inches='tight')
        print(f"\n✓ Preview saved to {OUTPUT_DIR / 'preview.png'}")
        plt.show()

"""
USAGE INSTRUCTIONS:
===================

1. Install dependencies:
   pip install earthengine-api geemap pillow numpy matplotlib requests

2. Authenticate Earth Engine (first time only):
   earthengine authenticate

3. Run this script:
   python nikumaroro_analysis.py

4. Find outputs in ./nikumaroro_imagery/
   - Individual satellite images
   - aligned_*.png (registered images)
   - viewer_config.json (for interactive viewer)
   - preview.png (comparison of first/last images)

5. Upload viewer_config.json to Claude and request an interactive slider artifact

NOTES:
------
- Sentinel-2 data available from 2015+
- Earlier data requires alternative sources (Landsat, commercial)
- Cloud cover may limit available imagery
- Script will work even if Earth Engine authentication fails
- At minimum, will download current high-resolution satellite tiles
"""