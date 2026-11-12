# Design: Dark Studio

VibeCheck's interface is a dark product studio: a near-black ground, framed showcase panels, hairline borders and
one glossy red accent. The team's own work is shown on dark "stages" so posters glow; everything around them stays
quiet. The look follows the user's reference (a premium dark component-library site); only the style is borrowed, no
branding. Navigation, forms and tables stay standard web controls.

Source of truth: `frontend/src/styles.css` (tokens on `:root`), `frontend/src/components/ui.jsx`, fonts in
`frontend/index.html`.

## Colour

| Token | Dark (default) | Light | Job |
|---|---|---|---|
| `--ground` | #0A0A0B | #FAFAFA | page background, with a soft red glow at the top |
| `--paper` / `--paper-2` / `--panel` | #111113 / #18181B / #0D0D0F | #FFF / #F4F4F5 / #F7F7F8 | cards, fills, inputs |
| `--ink` / `--ink-2` / `--ink-3` | #F5F5F6 / #A1A1AA / #71717A | #0A0A0B / #52525B / #71717A | text levels |
| `--rule` / `--rule-2` | white 8% / 14% | black 8% / 14% | hairlines |
| `--accent` + `--accent-grad` | #E5372A, #F2493B to #D42C1F | same | primary buttons, verdict seal, selected decision, accent words in titles |
| `--ok` / `--warn` / `--bad` | #2DD4A3 / #F5B83D / #FF7A3D | darker inks in light | verdict and check states only, always with an icon and words |

Stages (`.board`) are dark in both themes. Chart series: team #0072B2 on paper, white on stages; other pages pink
#E7A6CB; rejected drafts orange #FFB27A / #D55E00.

## Type

- Display: **Cabinet Grotesk** 700/800, tight tracking (-0.035em on h1, -0.06em on the score numeral). One word of a
  page title can be set in the accent (`<em>` or `.num` inside `h1`).
- Text: **Satoshi** 400–700, 15.5px/1.6.
- Both load from Fontshare (`index.html`); without internet the stack falls back to the system UI font.
- Numbers in data use tabular figures (`.num`).

## Components

- **Top bar**: sticky, translucent with backdrop blur and a bottom hairline; red rounded-square brand mark; tabs as
  quiet text, the active one in a bordered pill; bordered square icon button for the theme.
- **Paper** (`.paper`): #111113 card, 20px radius, hairline border, soft deep shadow.
- **Stage** (`.board`): double frame (outer border + inner hairline panel at 10px inset) with a red radial glow
  top-left. Used for the Result hero, the Check drop zone, Team style and Team setup counts.
- **Framed tile** (`.pinned`): dark tile, 16px radius, image inset with 11px radius, nameplate below (match %, date,
  likes); lifts on hover.
- **Verdict seal** (`.stamp`): glossy red badge rotated -7deg on your design, with "VibeCheck · date"; presses in once
  on load. `.stamp.sm` is a small pill for table rows.
- **Readout** (Result): huge white score numeral, verdict + tinted chip, one-line summary, confidence note; threshold
  scale (zones, score marker, caption) and score parts with thin bars. Closest posts as a strip along the stage bottom.
- **Feedback**: "What to change" and the finish checklist first, with a glowing top line (orange when something is
  off, green when clear); passed checks as green pills; "What already fits" as a compact multi-column list.
- **Buttons**: primary glossy red with an inner highlight and red glow; secondary dark with a hairline; 12px radius.
- **Inputs**: dark panel fill, hairline border, red focus ring.
- **Marks / chips**: tinted backgrounds with coloured icons (lucide), never colour alone.
- **Ledger**, **summary rows**, **meta chips**, **paint chips** (dark tiles with mono hex).

## Motion

One authored moment: the verdict seal presses in (0.6s, ease-out, from a visible blurred state). Tiles lift on hover.
Reduced motion turns both off.

## Accessibility

Dark default with a light theme toggle; visible red focus rings; verdicts always in words and icons; chart groups
differ by shape; text contrast ≥ 4.5:1 on cards and stages.
