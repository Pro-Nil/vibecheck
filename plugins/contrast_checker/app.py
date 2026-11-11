"""Example plugin: readability / contrast checker.

Shows other teams how to build a VibeCheck plugin. It is its own tiny service:
    uvicorn app:app --app-dir plugins/contrast_checker --port 8100
then register it once:
    curl -X POST http://localhost:8000/plugins -H "Content-Type: application/json" \
         -d '{"name":"Contrast checker","url":"http://localhost:8100/hook","slot":"result"}'

VibeCheck POSTs {"event": "check.completed", "check": {...}, "team": {...}, "api_base": "..."}
and draws the Panel we return.
"""
from fastapi import FastAPI

app = FastAPI(title="Contrast checker plugin")


def _lum(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@app.post("/hook")
def hook(event: dict):
    check = event.get("check", {})
    pal = check.get("plan_palette") or []
    if len(pal) < 2:
        return {"title": "Readability", "summary": "Upload an inspiration image to check colour contrast."}
    bg = pal[0]["hex"]  # biggest colour = likely background
    pairs = [(c["hex"], round(ratio(bg, c["hex"]), 2)) for c in pal[1:5]]
    best = max(r for _, r in pairs)
    items = [{"ok": best >= 4.5, "text": f"Best text colour on {bg} reaches {best}:1 "
                                        f"({'passes' if best >= 4.5 else 'fails'} the 4.5:1 rule for small text)."},
             {"ok": best >= 3.0, "text": f"Large headlines need 3:1 — {'met' if best >= 3 else 'not met'}."}]
    return {
        "title": "Readability (contrast checker)",
        "summary": f"Background colour {bg} against the other main colours of your inspiration.",
        "metrics": [{"label": "Best contrast", "value": best, "unit": ":1"}],
        "items": items,
        "chart": {"type": "bar", "title": "Contrast with the background", "y_label": "ratio : 1",
                  "points": [{"label": h, "value": r} for h, r in pairs]},
    }
