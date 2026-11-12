"""Download the UI fonts (Cabinet Grotesk, Satoshi from Fontshare) into frontend/src/fonts so the app works offline.

The font files are not committed: Fontshare's licence allows using them in a web app but not redistributing the
files, so each machine fetches them once. Run before `npm run build`:

    python scripts/get_fonts.py
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

CSS = "https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@700,800&f[]=satoshi@400,500,700&display=swap"
OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "fonts"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    css = urllib.request.urlopen(CSS, timeout=30).read().decode()
    faces = re.findall(r"font-family: '([^']+)';\s*src: url\('([^']+\.woff2)'\).*?font-weight: (\d+);", css, re.S)
    if not faces:
        raise SystemExit("No fonts found in the Fontshare CSS; check your internet connection.")
    for family, url, weight in faces:
        name = f"{family.lower().replace(' ', '-')}-{weight}.woff2"
        data = urllib.request.urlopen("https:" + url if url.startswith("//") else url, timeout=30).read()
        if data[:4] != b"wOF2":
            raise SystemExit(f"{name}: not a woff2 file")
        (OUT / name).write_bytes(data)
        print(f"{name}  {len(data) // 1024} KB")


if __name__ == "__main__":
    main()
