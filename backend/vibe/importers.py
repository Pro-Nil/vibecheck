"""Extract step: get post images (+ likes, dates, captions) into the database.

Three ways in:
  * import_folder:    any folder of images. Optional meta.csv (filename,caption,posted_at,likes,comments)
                      and Instaloader's *.json.xz sidecars are read if present.
  * fetch_instagram:  downloads a public page with Instaloader into data/raw/<handle>, then import_folder.
  * add_upload:       one image sent through the API (e.g. a rejected draft).
"""
from __future__ import annotations

import csv
import json
import lzma
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select

from . import config
from .db import Post, SessionLocal, Team

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
_CAROUSEL = re.compile(r"^(?P<base>.+_UTC)_(?P<n>\d+)$")
_IG_STAMP = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})_UTC")


def _read_meta_csv(folder: Path) -> dict[str, dict]:
    f = folder / "meta.csv"
    if not f.exists():
        return {}
    with f.open(newline="", encoding="utf-8") as fh:
        return {row["filename"]: row for row in csv.DictReader(fh)}


def _read_ig_json(img: Path, base: str) -> dict:
    """Read Instaloader metadata next to an image, if any."""
    for cand in (img.with_name(base + ".json.xz"), img.with_name(base + ".json")):
        if cand.exists():
            try:
                raw = lzma.open(cand).read() if cand.suffix == ".xz" else cand.read_bytes()
                node = json.loads(raw).get("node", {})
            except Exception:
                return {}
            likes = (node.get("edge_media_preview_like") or node.get("edge_liked_by") or {}).get("count")
            if likes is None:
                likes = (node.get("iphone_struct") or {}).get("like_count")
            com = (node.get("edge_media_to_comment") or node.get("edge_media_to_parent_comment") or {}).get("count")
            edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
            caption = edges[0]["node"]["text"] if edges else ""
            ts = node.get("taken_at_timestamp")
            return {"likes": likes, "comments": com, "caption": caption,
                    "posted_at": datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None) if ts else None,
                    "external_id": node.get("shortcode") or base}
    return {}


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip()[:19], fmt)
        except ValueError:
            pass
    return None


def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def import_folder(team_id: int, folder: str | Path, label: str, source_page: str = "",
                  carousel_first_only: bool = True,
                  progress: Callable[[float, str], None] | None = None) -> int:
    """Copy every image in `folder` into data/images and add a Post row. Returns rows added."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")
    source_page = source_page or folder.name
    meta = _read_meta_csv(folder)
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    dest_dir = config.IMAGES_DIR / f"team_{team_id}" / label / _safe(source_page)
    dest_dir.mkdir(parents=True, exist_ok=True)
    added = 0
    with SessionLocal() as s:
        existing = set(s.scalars(select(Post.external_id).where(
            Post.team_id == team_id, Post.source_page == source_page)))
        for i, img in enumerate(files):
            stem = img.stem
            m = _CAROUSEL.match(stem)
            base = m.group("base") if m else stem
            if m and carousel_first_only and m.group("n") != "1":
                continue
            info = _read_ig_json(img, base)
            row = meta.get(img.name, {})
            ext_id = str(info.get("external_id") or row.get("id") or img.relative_to(folder).as_posix())
            if ext_id in existing:
                continue
            posted = info.get("posted_at") or _parse_date(row.get("posted_at"))
            if posted is None and (st := _IG_STAMP.search(stem)):
                posted = datetime.strptime(" ".join(st.groups()), "%Y-%m-%d %H %M %S")
            dest = dest_dir / f"{_safe(ext_id)}{img.suffix.lower()}"
            shutil.copy2(img, dest)
            s.add(Post(team_id=team_id, label=label, source_page=source_page, external_id=ext_id,
                       image_path=dest.relative_to(config.DATA_DIR).as_posix(),
                       caption=info.get("caption") or row.get("caption") or "",
                       posted_at=posted,
                       likes=_int(info.get("likes") if info.get("likes") is not None else row.get("likes")),
                       comments=_int(info.get("comments") if info.get("comments") is not None else row.get("comments"))))
            existing.add(ext_id)
            added += 1
            if progress and i % 20 == 0:
                progress(i / max(1, len(files)), f"Imported {added} images from {source_page}")
        s.commit()
    return added


def add_upload(team_id: int, data: bytes, filename: str, label: str, caption: str = "",
               likes: int | None = None, posted_at: datetime | None = None) -> Post:
    import hashlib
    digest = hashlib.sha1(data).hexdigest()[:16]
    ext = Path(filename).suffix.lower() if Path(filename).suffix.lower() in IMAGE_EXTS else ".png"
    dest_dir = config.IMAGES_DIR / f"team_{team_id}" / label / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{digest}{ext}"
    dest.write_bytes(data)
    with SessionLocal() as s:
        existing = s.scalar(select(Post).where(Post.team_id == team_id, Post.source_page == "uploads",
                                               Post.external_id == digest))
        if existing:
            return existing
        p = Post(team_id=team_id, label=label, source_page="uploads", external_id=digest,
                 image_path=dest.relative_to(config.DATA_DIR).as_posix(), caption=caption,
                 likes=likes, posted_at=posted_at)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p


def fetch_instagram(team_id: int, handle: str, label: str, max_posts: int = 300,
                    since: datetime | None = None,
                    progress: Callable[[float, str], None] | None = None) -> int:
    """Download a public Instagram page with Instaloader, then import it.

    Instagram often blocks anonymous downloads. If that happens, log in once yourself with
    `instaloader --login YOUR_USERNAME` and set VIBE_IG_SESSION_USER=YOUR_USERNAME, or download
    the images by hand and use import_folder instead.
    """
    import instaloader

    handle = handle.strip().lstrip("@")
    target_dir = config.RAW_DIR / _safe(handle)
    L = instaloader.Instaloader(
        dirname_pattern=str(target_dir), download_videos=False, download_video_thumbnails=True,
        download_geotags=False, download_comments=False, save_metadata=True, compress_json=True,
        post_metadata_txt_pattern="", quiet=True, max_connection_attempts=2)
    if config.INSTAGRAM_SESSION_USER:
        L.load_session_from_file(config.INSTAGRAM_SESSION_USER)
    profile = instaloader.Profile.from_username(L.context, handle)
    n = old_seen = 0
    for post in profile.get_posts():
        if n >= max_posts:
            break
        if since and post.date_utc < since:
            # newest first, but up to 3 pinned posts can be old: stop after the 4th old one
            old_seen += 1
            if old_seen > 3:
                break
            continue
        L.download_post(post, target=handle)
        n += 1
        if progress and n % 5 == 0:
            progress(min(0.99, n / max_posts), f"Downloaded {n} posts from @{handle}")
    return import_folder(team_id, target_dir, label, source_page=handle)


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:80] or "x"


def team_or_404(s, team_id: int) -> Team:
    t = s.get(Team, team_id)
    if t is None:
        raise KeyError(f"team {team_id} not found")
    return t
