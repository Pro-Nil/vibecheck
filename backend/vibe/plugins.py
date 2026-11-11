"""Plugin system: other teams' services add panels inside our app.

A plugin registers a URL. When an event happens (a check finishes, a style profile is opened)
we POST the event to that URL; the plugin answers with a Panel (see schemas.Panel) and the
frontend draws it with our own components, so it looks native.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx
from pydantic import ValidationError
from sqlalchemy import or_, select

from .db import Plugin, SessionLocal
from .schemas import Panel

TIMEOUT_S = 5.0


def plugins_for(team_id: int, slot: str) -> list[Plugin]:
    with SessionLocal() as s:
        return list(s.scalars(select(Plugin).where(
            Plugin.enabled == 1, Plugin.slot == slot,
            or_(Plugin.team_id == team_id, Plugin.team_id.is_(None)))))


def _call(p: Plugin, event: dict) -> dict:
    base = {"plugin_id": p.id, "plugin": p.name, "author_team": p.author_team}
    try:
        r = httpx.post(p.url, json=event, timeout=TIMEOUT_S)
        r.raise_for_status()
        panel = Panel.model_validate(r.json())
        return {**base, "ok": True, "panel": panel.model_dump(exclude_none=True)}
    except ValidationError as e:
        return {**base, "ok": False, "error": f"Plugin answered with a bad panel: {e.errors()[0]['msg']}"}
    except Exception as e:
        return {**base, "ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def run_plugins(team_id: int, slot: str, event: dict) -> list[dict]:
    ps = plugins_for(team_id, slot)
    if not ps:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(ps))) as ex:
        return list(ex.map(lambda p: _call(p, event), ps))
