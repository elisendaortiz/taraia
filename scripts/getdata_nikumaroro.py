#!/usr/bin/env python3
"""
Nikumaroro Taraia Object — Historical GEE Time-Series Downloader
Pulls the best available satellite image per year (2013–2024) and
writes viewer_config.json for the index.html time-slider viewer.

Sources:
  2013–2014  Landsat 8 C02 T1 L2  (LANDSAT/LC08/C02/T1_L2)
  2015–2024  Sentinel-2 SR Harmonized (COPERNICUS/S2_SR_HARMONIZED)

Installation:
    pip install earthengine-api requests pillow

Authentication (one-time):
    earthengine authenticate

Usage:
    python getdata_nikumaroro.py
"""

import ee
import json
import os
import requests
from datetime import datetime
from pathlib import Path
from PIL import Image
import io
from dotenv import load_dotenv

# Load .env from the project root (one level up from scripts/)
load_dotenv(Path(__file__).parent.parent / ".env")

# ============================================================================
# CONFIGURATION
# ============================================================================

TARAIA_LAT  = -4.686167    # 4°41'10.2"S
TARAIA_LON  = -174.498083  # 174°29'53.1"W
BUFFER_M    = 1500         # 1500 m radius → ~3×3 km ROI (~100×100 px at Landsat 30m native)
IMAGE_PX    = 1024         # Output image size in pixels

START_YEAR  = 2013
END_YEAR    = 2024

OUTPUT_DIR  = Path(__file__).parent.parent / "nikumaroro_imagery"
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================================================
# EARTH ENGINE INIT
# ============================================================================

def initialize_ee():
    project = os.environ.get("GOOGLE_PROJECT_ID")
    if not project:
        raise RuntimeError("GOOGLE_PROJECT_ID not set — add it to your .env file.")
    try:
        ee.Initialize(project=project)
        print(f"✓ Earth Engine initialized (project: {project})")
    except ee.EEException:
        print("  Authenticating Earth Engine...")
        ee.Authenticate()
        ee.Initialize(project=project)
        print(f"✓ Earth Engine authenticated and initialized (project: {project})")


def get_roi():
    point = ee.Geometry.Point([TARAIA_LON, TARAIA_LAT])
    return point.buffer(BUFFER_M).bounds()

# ============================================================================
# IMAGE SELECTION
# ============================================================================

def get_best_sentinel2(year, roi):
    """
    Return (ee.Image, date_str) for the least-cloudy Sentinel-2 image in
    that calendar year, or (None, None) if none found.
    """
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(roi)
        .filterDate(f"{year}-01-01", f"{year}-12-31")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )

    count = collection.size().getInfo()
    if count == 0:
        return None, None

    image = collection.first()
    date_str = image.date().format("YYYY-MM-dd").getInfo()
    cloud_pct = image.get("CLOUDY_PIXEL_PERCENTAGE").getInfo()
    print(f"    S2  {year}: {date_str}  cloud={cloud_pct:.1f}%")
    return image, date_str


def get_best_landsat8(year, roi):
    """
    Return (ee.Image, date_str) for the least-cloudy Landsat 8 C02 T1 L2
    image in that calendar year, or (None, None) if none found.
    """
    collection = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(roi)
        .filterDate(f"{year}-01-01", f"{year}-12-31")
        .filter(ee.Filter.lt("CLOUD_COVER", 30))
        .sort("CLOUD_COVER")
    )

    count = collection.size().getInfo()
    if count == 0:
        return None, None

    image = collection.first()
    date_str = image.date().format("YYYY-MM-dd").getInfo()
    cloud_pct = image.get("CLOUD_COVER").getInfo()
    print(f"    L8  {year}: {date_str}  cloud={cloud_pct:.1f}%")
    return image, date_str

# ============================================================================
# DOWNLOAD
# ============================================================================

S2_VIS = {
    "bands": ["B4", "B3", "B2"],
    "min": 0,
    "max": 3000,
    "gamma": 1.4,
}

L8_VIS = {
    # Landsat 8 C02 L2 SR bands — raw DN; reflectance = DN * 0.0000275 - 0.2
    # DN ~7000 → reflectance 0.0   DN ~30000 → reflectance 0.6
    "bands": ["SR_B4", "SR_B3", "SR_B2"],
    "min": 7000,
    "max": 30000,
    "gamma": 1.4,
}


def download_image(image, roi, vis_params, filename):
    """
    Download an EE image as a PNG thumbnail.
    Returns True on success, False on failure.
    """
    try:
        url = image.visualize(**vis_params).getThumbURL({
            "region": roi,
            "dimensions": IMAGE_PX,
            "format": "png",
        })

        response = requests.get(url, timeout=120)

        # Validate we actually got an image, not an error page
        content_type = response.headers.get("Content-Type", "")
        if response.status_code != 200 or "image" not in content_type:
            print(f"    ✗ Bad response ({response.status_code}, {content_type})")
            return False

        # Verify it opens as a valid image
        img = Image.open(io.BytesIO(response.content))
        img.verify()

        filepath = OUTPUT_DIR / filename
        with open(filepath, "wb") as f:
            f.write(response.content)

        return True

    except Exception as e:
        print(f"    ✗ Download failed: {e}")
        return False

# ============================================================================
# VIEWER CONFIG
# ============================================================================

def write_viewer_config(images_info):
    images_info.sort(key=lambda x: x["date"])

    config = {
        "location": {
            "name": "Taraia Object, Nikumaroro Island",
            "lat": TARAIA_LAT,
            "lon": TARAIA_LON,
            "description": "Suspected location of Amelia Earhart's Lockheed Electra 10E",
        },
        "images": images_info,
        "metadata": {
            "generated": datetime.now().isoformat(),
            "total_images": len(images_info),
            "date_range": {
                "start": images_info[0]["date"] if images_info else "unknown",
                "end":   images_info[-1]["date"] if images_info else "unknown",
            },
        },
    }

    config_path = OUTPUT_DIR / "viewer_config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n✓ Saved viewer_config.json  ({len(images_info)} images)")
    return config

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 68)
    print("NIKUMARORO TARAIA OBJECT — HISTORICAL TIME-SERIES DOWNLOADER")
    print("=" * 68)
    print(f"Coordinates : {TARAIA_LAT}, {TARAIA_LON}")
    print(f"Years       : {START_YEAR}–{END_YEAR}")
    print(f"Output      : {OUTPUT_DIR}\n")

    initialize_ee()
    roi = get_roi()

    images_info = []
    failed_years = []

    for year in range(START_YEAR, END_YEAR + 1):
        print(f"\n[{year}]")

        image, date_str, source_label, vis_params, filename = None, None, None, None, None

        # Sentinel-2 preferred from 2015 onward
        if year >= 2015:
            image, date_str = get_best_sentinel2(year, roi)
            if image:
                source_label = "Sentinel-2"
                vis_params   = S2_VIS
                filename     = f"sentinel2_{year}.png"

        # Landsat 8 for 2013-2014, or as fallback if S2 has no coverage
        if image is None:
            image, date_str = get_best_landsat8(year, roi)
            if image:
                source_label = "Landsat 8"
                vis_params   = L8_VIS
                filename     = f"landsat8_{year}.png"

        if image is None:
            print(f"    ✗ No imagery found for {year} — skipping")
            failed_years.append(year)
            continue

        print(f"    Downloading {filename} …")
        ok = download_image(image, roi, vis_params, filename)

        if ok:
            print(f"    ✓ Saved {filename}")
            images_info.append({
                "date":             date_str,
                "filename":         filename,
                "aligned_filename": filename,   # no alignment needed — same projection
                "source":           source_label,
                "width":            IMAGE_PX,
                "height":           IMAGE_PX,
            })
        else:
            failed_years.append(year)

    # Summary
    print("\n" + "=" * 68)
    if images_info:
        config = write_viewer_config(images_info)
        print(f"✓ DONE  —  {len(images_info)} images, "
              f"{config['metadata']['date_range']['start']} → "
              f"{config['metadata']['date_range']['end']}")
    else:
        print("✗ No images downloaded. Check GEE authentication.")

    if failed_years:
        print(f"  Skipped years: {failed_years}")

    print("\nNext: open index.html in a browser (served via local HTTP) to use the slider.")


if __name__ == "__main__":
    main()
