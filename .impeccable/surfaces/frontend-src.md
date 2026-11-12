---
version: 1
slug: "frontend-src"
primary_target: "frontend/src"
related_targets: []
---

# VibeCheck app (frontend/src)

Scope: the whole web app (Check my idea, Check my design, Result, History, Team style, Team setup, Plugins).
Mode: Operate. Build path: code-led. Users: junior designers checking work; seniors recording decisions and reading
team style; demo audience at CS698B (26 Nov 2026).

## Direction contract

THESIS: A design team's work lives on a notice board; VibeCheck pins your design on the team's board beside the posts
it learned from and stamps the verdict. Refuses the grey SaaS dashboard with a gauge and a card grid.

OWN-WORLD: Felt-green soft-board (#1F4A3D shell, #2A5A4B board panel with a fine felt dot texture), white notice paper
cards on a pale green-grey ground (#F4F6F2), ink black text, violet stamp ink (#5B3E96) reserved for verdict stamps and
decisions, Okabe-Ito verdict colours (on-brand #009E73, borderline #E69F00, off-brand #D55E00) used only for verdict and
check state. Barlow Condensed for display and numerals, Atkinson Hyperlegible for UI text. Push-pins and a slight tilt
only on pinned posters in board panels. Dark mode: night board (deeper felt, charcoal paper).

STORY: The designer sees their poster pinned among the team's closest posts, reads the stamp and the score, then
the reasons in words, then acts (check another version / record the seniors' decision).

FIRST VIEWPORT: Felt-green top bar with standard tabs, team select and theme toggle. Result: title row with actions
right; a full-width board panel: pinned poster left (stamp over its corner), score numeral 160px+ with verdict line and
sub-scores centre, closest team posts pinned right in a 3x2 grid with nameplates (match %, date, likes). Why and Finish
checklist cards below.

FORM: The Notice Board, position 6 of 7 on the grounded list; seed:4545c93345b24c8a. Raises: scale-contrast score
(variable-font specimen); strict categorical verdict colours (transit); fixed nameplates on post tiles (character
catalog); stamped states, nothing disappears (ticket wallet); dot size = likes on the style map (star atlas).
Signature move: the verdict stamp pressing onto the pinned poster once on load (reduced motion: no press).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
