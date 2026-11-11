"""Paths and settings. Everything can be overridden with environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("VIBE_DATA_DIR", ROOT / "data"))
IMAGES_DIR = DATA_DIR / "images"
RAW_DIR = DATA_DIR / "raw"          # instaloader downloads land here before import
MODELS_DIR = DATA_DIR / "models"
UPLOADS_DIR = DATA_DIR / "uploads"  # inspo images sent to /checks
DB_URL = os.environ.get("VIBE_DB_URL", f"sqlite:///{(DATA_DIR / 'vibecheck.db').as_posix()}")

# Set VIBE_FAKE_CLIP=1 to use a tiny deterministic stand-in for CLIP (tests, no downloads).
FAKE_CLIP = os.environ.get("VIBE_FAKE_CLIP") == "1"
CLIP_MODEL = os.environ.get("VIBE_CLIP_MODEL", "ViT-B-32")
CLIP_PRETRAINED = os.environ.get("VIBE_CLIP_PRETRAINED", "openai")
# "pad": show CLIP the whole poster (padded to a square with its own edge colour). "center": CLIP's default
# centre crop, which cuts ~10 % off the top and bottom of a 4:5 poster, where titles and logos usually are.
CLIP_FRAMING = os.environ.get("VIBE_CLIP_FRAMING", "pad")

# Daily refresh (fetch new posts + retrain). Hour in local time; set VIBE_SCHEDULER=0 to turn off.
SCHEDULER_ON = os.environ.get("VIBE_SCHEDULER", "1") == "1"
REFRESH_HOUR = int(os.environ.get("VIBE_REFRESH_HOUR", "3"))

# Optional Instagram session made with `instaloader --login <user>` (the person logs in themselves).
INSTAGRAM_SESSION_USER = os.environ.get("VIBE_IG_SESSION_USER")

for d in (DATA_DIR, IMAGES_DIR, RAW_DIR, MODELS_DIR, UPLOADS_DIR):
    d.mkdir(parents=True, exist_ok=True)
