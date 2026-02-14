# Taraia Object — Nikumaroro Island Satellite Time-Series

Satellite imagery analysis of the **Taraia Object**, a submerged feature in the northwest lagoon of Nikumaroro Island (Republic of Kiribati) at coordinates **4°41'10.2"S, 174°29'53.1"W** — suspected location of Amelia Earhart's Lockheed Electra 10E.

The project tracks changes in the object's visibility between 2013 and 2024 using multi-source satellite imagery, with evidence suggesting progressive sediment obscuration over time.

---

## Project Structure

```
taraia/
├── index.html                  # Interactive time-slider viewer (open via local server)
├── scripts/
│   ├── getdata_nikumaroro.py   # Pulls historical GEE imagery (2013–2024) ← run this
│   └── nikumaroro_analysis.py  # Original prototype script
├── nikumaroro_imagery/
│   ├── viewer_config.json      # Image metadata consumed by the viewer
│   ├── landsat8_YYYY.png       # Landsat 8 imagery (2013–2021)
│   └── sentinel2_YYYY.png      # Sentinel-2 imagery (2022–2024)
└── .env                        # GCP credentials (not committed)
```

---

## Setup

**1. Install dependencies**
```bash
pip install earthengine-api requests pillow python-dotenv
```

**2. Authenticate Google Earth Engine** (one-time)
```bash
earthengine authenticate
```

**3. Configure credentials**

Create a `.env` file in the project root:
```
GOOGLE_PROJECT_ID=your-gcp-project-id
GOOGLE_PROJECT_NUMBER=your-project-number
```

You need a Google Cloud Project with the [Earth Engine API enabled](https://console.cloud.google.com/apis/library/earthengine.googleapis.com) and an account registered at [signup.earthengine.google.com](https://signup.earthengine.google.com).

---

## Usage

**Pull imagery (2013–2024)**
```bash
python scripts/getdata_nikumaroro.py
```

This fetches one best-available (least cloudy) image per year and writes `nikumaroro_imagery/viewer_config.json`. Expected output: ~12 images.

**View the time-series**
```bash
python -m http.server 8000
```
Then open `http://localhost:8000` in your browser. Use the slider or arrow buttons to move through years.

---

## Data Sources

| Years     | Satellite  | Collection                          | Native Resolution |
|-----------|------------|-------------------------------------|-------------------|
| 2013–2021 | Landsat 8  | `LANDSAT/LC08/C02/T1_L2`            | 30 m/px           |
| 2022–2024 | Sentinel-2 | `COPERNICUS/S2_SR_HARMONIZED`       | 10 m/px           |

Images are selected by lowest cloud cover percentage for each calendar year. ROI is a 1500m radius (~3×3 km) around the target coordinates.

---

## Research Context

- [Purdue Exponent — Earhart Expedition Article](https://www.purdueexponent.org/city_state/general_news/earhart-purdue-plane-expedition/article_14c4486a-51f6-4c72-83b4-9c9544350df5.html)
- The Taraia Object appears in satellite imagery as a distinct feature on the lagoon floor
- Sediment deposition between 2013–2024 has progressively reduced its visibility
- Detection techniques used in comparable searches: LiDAR (bathymetric), GPR, magnetometry, electrical resistivity

---

## Future Improvements

- **Extend the timeline back further** — the time-series currently starts at 2013 (Landsat 8 launch). Landsat 7 (1999–) and Landsat 5 (1984–2013) data should be incorporated to capture the object's state decades earlier, before any sediment accumulation began. This would significantly strengthen the change-detection analysis.

- **Reduce the ROI buffer** — `BUFFER_M` is currently set to 1500m to improve image readability, but the ideal value for close inspection of the Taraia Object is closer to 300m. A tighter crop would make the object more prominent in each frame. A solution would be to offer both views: a wide-context image at 1500m and a zoomed-in crop at 300m per year.

- **Host images on external storage** — storing PNGs in the git repository is not ideal at scale. Hosting on S3, Cloudflare R2, or similar object storage would be preferable: the Python script would upload images directly after download, and `viewer_config.json` would reference the remote URLs instead of local paths. This removes the Git LFS dependency entirely and makes the GitHub Pages deployment lightweight.

---

## Deployment (GitHub Pages)

```bash
git add .
git commit -m "add imagery"
git push
```

Enable Pages in repo settings → set source to `main` branch root. The viewer runs entirely client-side with no build step required.

> **Note:** PNG files can be large. Use Git LFS (`git lfs track "*.png"`) or host images on external storage (Cloudflare R2, AWS S3) and update paths in `viewer_config.json` if the repo exceeds GitHub's 100MB limit.
