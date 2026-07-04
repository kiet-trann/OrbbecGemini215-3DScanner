# Setup Notes

## Environment

Recommended development machine:

- Windows 10/11 64-bit or Ubuntu 22.04.
- Intel Core i5/i7 or AMD Ryzen 5/7 or better.
- 16 GB RAM minimum.
- USB 3.0 port.
- At least 10 GB free disk space.

## Python Setup

```powershell
cd C:\Users\TD-998\OrbbecGemini215-3DScanner
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Camera Setup Checklist

- Install Orbbec SDK/runtime required by `pyorbbecsdk2`.
- Connect Gemini 215 through USB 3.0.
- Confirm Windows Device Manager or Linux `lsusb` can see the camera.
- Start with `scripts/01_rgbd_viewer.py`.

## Marker Setup

- Print ArUco markers on flat paper or mica.
- Put 4 to 6 markers around the object.
- Keep at least 1 marker visible during scan; 2 or more is better.
- Store marker size and world coordinates in `data/calibration/marker_layout.example.json`.
