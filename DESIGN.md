# Design: The Notice Board

VibeCheck's interface is a club's notice board. Your design is pinned on the team's board next to the posts the
model learned from, and the verdict lands on it as a rubber stamp. The world lends four things only: type, palette,
density and one signature move. Navigation, forms and tables stay standard web controls.

Source of truth: `frontend/src/styles.css` (tokens on `:root`), `frontend/src/components/ui.jsx` (shared pieces).

## Colour

| Token | Light | Dark | Job |
|---|---|---|---|
| `--felt` | #1F4A3D | #0E2A21 | top bar, primary buttons |
| `--felt-2` / `--felt-edge` | #2A5A4B / #234F42 | #153A2F / #112F26 | board panels and their inset frame |
| `--ground` | #EEF1EC | #0F1513 | page background (green-grey, never cream) |
| `--paper` / `--paper-2` | #FFFFFF / #E6EBE4 | #172019 / #1F2A24 | cards ("paper"), quiet fills |
| `--ink` / `--ink-2` | #14171A / #4B5650 | #E8EFEA / #A9B8B0 | text, secondary text (tinted, not grey) |
| `--stamp` | #5B3E96 | #B8A2F0 | stamps and the selected seniors' decision only |
| `--ok` / `--warn` / `--bad` | #009E73 / #E69F00 / #D55E00 | same | verdict and check states only (Okabe-Ito); `*-ink` variants for text |

Rules: verdict colours never decorate; every verdict also carries an icon and words. Chart series: team #0072B2,
other pages #CC79A7, rejected #D55E00; on the felt board the map uses white / pink / peach. Pins are #E8B04A (yours)
or neutral grey (the team's).

## Type

- Display and numerals: **Barlow Condensed** 600/800 (self-hosted via @fontsource). h1 clamp(2rem..2.6rem), h2 1.55rem,
  the score numeral clamp(6.5rem..10rem) with a 0.3em "/ 100".
- UI and body: **Atkinson Hyperlegible** 400/700, 15.5px/1.55.
- Hierarchy comes from scale contrast (huge numeral, small labels), not from colour or extra chrome. Figures in data use
  tabular numerals (`.num`).

## Components

- **Top bar**: felt green, wordmark VIBECHECK with the stamped-tick mark, icon + label tabs (lucide-react), team select,
  theme toggle. Active tab is a ground-coloured pill.
- **Board** (`.board`): felt panel with a fine dot texture and a 9px inset frame. Used where the team's own work is
  shown: Result hero, Check drop zone, Team style map, Team setup counts.
- **Pinned** (`.pinned`): white paper with a push-pin, slight tilt (±0.5 to 1.6deg), lifts on hover. Team posts carry a
  fixed nameplate: match %, short date, likes.
- **Stamp** (`.stamp`): violet double-ruled rubber stamp, rotated -11deg, verdict or decision text plus "VibeCheck ·
  date". `.stamp.sm` for table rows. Decided work keeps its stamp; nothing disappears.
- **Paper** (`.paper`): white card with a hairline rule and soft shadow; never nested.
- **Mark**: 26px rounded square with a lucide icon (check / x / alert) for reasons, finish checks, job states.
- **VerdictChip**: filled chip, icon + words.
- **Ledger**: number + explanation rows for model statistics (instead of same-size stat tiles).
- **Paint chips** for palettes: swatch, hex in monospace, share of area.
- **Seg** control for the seniors' decision; the pressed option takes stamp violet.

## Motion

One authored moment: the stamp presses onto the poster on load (0.5s, ease-out, from a visible scaled state so it never
hides content). Reduced motion: no press, no tilt transition.

## Accessibility

Light/dark with a toggle (plus system preference), skip link, visible focus (violet on paper, amber on felt),
verdicts in words and icons, chart lines differ by dash, map groups by shape. Text contrast ≥ 4.5:1 on paper and felt.
