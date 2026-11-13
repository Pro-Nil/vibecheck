# Known issues and improvements

Honest status as of 13 Nov 2026. Everything below was found by running the app on real data:
74 posts from one fest's Instagram page (Mar–Nov 2026) and 9 drafts of one talk poster that the design
team rejected, plus 2 posters the team accepted.

**Short version:** the pipeline, API, plugins and dashboards work end to end. Model v8 (v7 with cleaner approval-model training; v7 added layout, typeface and clutter features) ranks the team's real
new posts above its rejected drafts (AUC 0.90 on posts it had not seen) and both accepted one-offs above all 9
rejects (was AUC 0.53 in v2). It is still tested on very little: all rejected drafts come from one brief and only
2 accepted designs are on record.
More decided designs (see "Improvements") are what would move it further.

## 0000000. Model v8 (13 Nov 2026): cleaner approval-model training

Where v7 still lost points, measured on the synthetic team rather than guessed. If the approval model were handed the
exact rules each design broke, the same 120 decisions would give **0.89** held-out AUC (v7: 0.81). So the gap was the
inputs, not too few decisions. The detectors were not the problem: each broken rule is spotted at AUC 0.96-1.00, except
cramped (0.71) and no-accent (0.84). Three changes, each small, kept only because they held up on two independent sets
of 60 new briefs (seeds 999 and 2024, paired bootstrap over briefs):

- **Leave the whole brief out.** When the approval model learns from a rejected version, its on-brand inputs compared
  it with the team's posts *including its accepted sibling* from the same brief. A brand-new design never has such a
  sibling, so training inputs looked more on-brand than real ones. Now every design from the same brief is left out.
- **Saturate off-range inputs at 1 range width.** "Clearly outside the team's range" now counts the same however far
  out, so one extreme value (a team with very uniform headlines has a narrow range) cannot swamp the rest.
- **Edge margin** (closest text to the image edge) as an input: it spots cramped layouts at AUC 0.99.

| Held-out, both sets pooled (360 versions) | AUC change vs v7 | 90 % interval |
|---|---|---|
| leave brief out | +0.003 | -0.000 to +0.006 |
| saturate | +0.005 | -0.002 to +0.012 |
| **all three (shipped)** | **+0.013** | **+0.005 to +0.021** (better in 100 % of resamples) |

End to end (retrained app, `eval_demo_team.py 60`): final AUC **0.81 → 0.83**, seniors' pick ranked first **77 % →
82 %**; median score wrong typeface 46 → 36, cramped 46 → 41, clean designs unchanged at 84. Real data (Techkriti,
approval model off): time-forward AUC 0.90, unchanged.

**Tried and not kept** (same harness, test AUC; v7 0.81): binary "outside range" flags 0.77; boosted stumps 0.73-0.79
and depth-2 trees 0.76 (overfit 120 decisions); L1 logistic 0.73-0.80; other regularisation strengths 0.79-0.81;
a weight cap above 0.6 (no change); largest-accent-shape input (spots no-accent at 1.00, but test AUC 0.80: the
seniors barely care about that rule, weight 0.4). The remaining gap to 0.89 is mostly how continuous measurements
turn into "this rule is broken"; more decided briefs would close more of it than another model.

Models trained before v8 keep scoring exactly as they were trained until the team retrains.

## 000000. Model v7 (13 Nov 2026): layout, typeface and clutter features; a better confidence rule

The held-out test above showed what the model could not see: the seniors' wrong-typeface, clutter and centred-layout
rules (no feature described type or layout). v7 measures them from the image and the text boxes the detector already
finds (`finish.layout`, stored with the typography summary; older posts are measured on the next retrain without
running text detection again):

- **Typeface**: stroke weight, stroke unevenness and letter-outline complexity of the headline (distance transform on
  the letter pixels). **Layout**: title alignment. **Clutter**: small text fragments and small separate shapes away
  from text.
- Probe on generated posters (25 per rule, AUC vs clean; 0.5 = no signal): wrong typeface by stroke weight 0.00 and
  outline 0.96; clutter by small text / small shapes 1.00 / 1.00; centred by title alignment 0.00.
- They enter the approval model as "how far outside the team's usual range" (capped at 4 range widths).

| Held-out test, 60 new briefs | v6 | **v7** |
|---|---|---|
| Final score AUC, accepted vs rejected | 0.74 | **0.81** |
| Seniors' pick ranked first | 68 % | **77 %** |
| Median score: clean / wrong typeface / clutter / cramped | 80 / 63 / 51 / 58 | **84 / 46 / 44 / 46** |

Ceiling stays 0.92 (the seniors' 10 % flipped decisions). Centred layouts still score high (75 → 73): the seniors
care least about that rule (weight 0.5). Real data (Techkriti, approval model off): time-forward AUC **0.90**, unchanged,
since the on-brand part did not change.

**Tried and not kept:** a within-brief (pairwise) approval model. Leave-one-brief-out AUC 0.818 (current) vs 0.791
(pairwise) vs 0.811 (both); same-brief pairs right 0.843 / 0.843 / 0.871. Within noise on 40 briefs, so not shipped.

**Confidence rule.** "Low confidence: the team has posted little like this" used to fire when the look-alike
percentile was below 10 %. On the synthetic team it flagged 23 % of clean on-style designs but only 10 % of other
clubs' posters, the wrong way round; learning the 10 % from the team's newer posts changed nothing. v7 uses the
similarity to the single closest team post, flagged below the level only 5 % of the team's own posts fall under
(leave one out), so it adapts to how varied a team is. Flagged now: clean on-style 7 %, off-palette 40 %, other
clubs' posters 57 %.

Models trained before v7 keep working (without the new inputs and with the old confidence rule) until the team retrains.

## 00000. Synthetic demo team (12 Nov 2026): the approval model, end to end

The real team has 2 accepted designs, so the approval model can never switch on there. `scripts/make_demo_team.py`
builds an imaginary team (generated posters, house style, other clubs, 40 briefs x 3 versions) whose simulated seniors
decide with hidden weights per broken rule, plus noise and 10 % flipped decisions. `scripts/eval_demo_team.py`
then tests on NEW briefs the model never saw.

- Approval model switches on by itself: leave-one-brief-out AUC 0.81 (low end 0.76), on-brand alone 0.72.
- On 60 unseen briefs: AUC accepted vs rejected **0.61 → 0.74** with the learned approval model; it picks the seniors'
  favourite version in **55 % → 68 %** of briefs. Ceiling (the seniors' own score, given their inconsistency) 0.92.
- Blind spots: font choice and small clutter (no feature describes them). Giving the approval model 8 or 16 CLIP
  directions did not help (AUC 0.74 either way, lower leave-one-out), so `APPROVAL_CLIP_PCS = 0`.
- Read it as "the machinery learns a consistent taste from about 120 decided designs", not as accuracy on a real team:
  the seniors here follow rules we wrote.

 (12 Nov 2026): synthetic data used to test, not to train

Made-up data cannot teach the seniors' taste (train and test on my own fakes and the score means nothing), so it
was used two ways, each guarded by the real time-forward evaluation:

**1. Mistake benchmark (`scripts/synth_benchmark.py`).** Each of the 75 real team posts is held out with its series
and scored as-is, after 10 realistic mistakes and after 5 harmless edits. Finding: v5 hardly noticed most mistakes.
A wrong colour scheme changed the verdict in only 29 % of posts, while harmless edits (mirror, 4 % crop) changed it
in 13-15 %. Clutter lowered the score in 41 % of posts, *less* often than mirroring did (57 %).

**Fix (v6): style match.** A third on-brand signal compares the six measured style features (brightness, saturation,
warmth, busyness, empty space, contrast; standardised by the team's spread) with the same-topic past posts.

| Verdict changed by the edit (higher is better for mistakes, lower for harmless) | v5 | v6 |
|---|---|---|
| wrong colour scheme | 29 % | **57 %** (median score 30 → 14) |
| busy texture / low contrast (scored lower) | 63 % / 67 % | **75 % / 73 %** |
| clutter, washed out | 16 %, 16 % | 12 %, 13 % (within this team's normal range: Techkriti posts run from plain to very busy) |
| harmless: JPEG / 4 % crop / brighter | 11 % / 13 % / 7 % | **7 % / 7 % / 5 %** |

Real-data guardrail: time-forward AUC 0.90 (0.79-0.94), series-out 0.93 (v5: 0.95), both within noise. On the
labelled designs both accepted posters are now On-brand (Pandiya 51, WEALTH CODE 25) and above all 9 rejects
(highest 21); 5 of 9 rejects Off-brand, 1 On-brand.

**2. Simulated seniors (`scripts/simulate_seniors.py`).** Each simulated brief = 1 accepted real post + 2 rejected
versions with a mistake; 15 % of decisions flipped (inconsistent seniors). The approval model, validated leaving one
brief out:

| Briefs (designs) | Approval model AUC | On-brand AUC | Same-brief pairs right (approval / on-brand) |
|---|---|---|---|
| 5 (15) | 0.69 ± 0.14 | 0.61 | 0.74 / 0.67 |
| 12 (36) | 0.62 ± 0.08 | 0.58 | 0.71 / 0.66 |
| 30 (90) | 0.63 ± 0.08 | 0.56 | 0.71 / 0.68 |
| 50 (150) | 0.67 ± 0.03 | 0.57 | 0.73 / 0.70 |

So **expect to need roughly 30-50 decided briefs** before a learned approval model reliably beats the on-brand score,
and even then the gain is modest. Richer inputs (signed style z-scores) and centring within each brief did not help.
The old switch-on rule (AUC >= 0.60 at 8+8 designs, 3 briefs) would often switch on a model that was just lucky (its
estimate swings +/-0.15 at that size), so it now also requires the low end of a bootstrap 90 % interval to be above
0.5 and no loss against the on-brand score. In simulation it then switches on 0-33 % of the time below 20 briefs,
67 % at 30, 100 % at 50. The simulated seniors reject exactly the mistakes we invented, so real numbers will be worse.

 (12 Nov 2026): CLIP now sees the whole poster

CLIP's standard preprocessing resizes the short side to 224 px and **centre-crops**, so a 4:5 poster lost ~10 %
at the top and bottom, where titles, dates and logos usually are. v5 pads each image to a square with its own edge
colour first (`features.pad_square`, `VIBE_CLIP_FRAMING=pad`). Stored vectors carry `clip_ver` and are
re-embedded automatically on the next retrain.

Tested with `scripts/embed_variants.py` + `scripts/evaluate.py` (v4 scorer, only the image embedding changed):

| Embedding | A: time-forward AUC (95 % CI) | B: series-out AUC | Rejects caught at 10 % false alarms (A / B) |
|---|---|---|---|
| ViT-B-32, centre crop (v4) | 0.90 (0.76-0.93) | 0.96 | 42 % / 78 % |
| **ViT-B-32, padded (v5)** | **0.90 (0.82-0.95)** | **0.95** | **64 % / 78 %** |
| ViT-B-32, mean of 3 square crops | 0.94 (0.83-0.96) | 0.97 | 67 % / 100 % (3x slower, accepted posters lower) |
| ViT-B-16, padded | 0.86 | 0.93 | 43 % / 78 % |
| ViT-L-14, padded (3x the size) | 0.79 | 0.90 | 50 % / 56 % |

**Bigger models are worse** here, like DINOv2: they focus on *what* is in a poster, not its style. Recency
weighting (compare only with the last 30/50 posts) and k = 5-15 were within noise.

**Labelled designs, v4 → v5:** accepted Pandiya 20 → **46 (On-brand)**, accepted WEALTH CODE 11 → **23** (Borderline,
just under the 25 line); the highest-scoring reject is 15.5, so **both accepted designs now score above all 9 rejects**
(AUC 0.83 → 1.0; same-brief pairs 6/9 → 9/9). 5 of 9 rejects are now Off-brand (v4: 0), none On-brand. Only 11
labelled designs from 2 briefs, and padding was chosen after seeing them, so treat this as encouraging, not proven.

 (12 Nov 2026): a better test, then a better scorer

**New evaluation, `scripts/evaluate.py`.** Two accepted designs are too few to judge anything, but every post the
team published later *is* an approved new design. So:
- **A. time-forward:** for each month, the model knows only older posts and scores that month's posts (33 real
  new posts) and the 9 rejected drafts.
- **B. series held out:** each series of near-identical posts is scored by a model built from the other series (75 posts).

It exposed two real bugs in v2/v3:
1. **Novelty penalty:** 33 % of genuinely approved new posts would have been called "Off-brand".
2. **Floor effect:** a design less similar than *every* past post got percentile 0, however far off it was, so new
   one-offs (WEALTH CODE: 0) tied with bad drafts (0, 0, 0, 0, 0).

| Scorer | A: AUC new posts vs rejects (95 % CI) | B: AUC | FinLit final beats own drafts | Pandiya |
|---|---|---|---|---|
| v2/v3: look (k=5) + colour, plain percentiles | 0.76 (0.65-0.84) | 0.92 | 0 / 9 | 22 |
| colour vs topic only | 0.66 | 0.80 | 6 / 9 | 42 |
| DINOv2 look | 0.17 | 0.45 | 8 / 9 | 8 |
| typography vs topic | 0.34 | 0.56 | 3 / 9 | 30 |
| **v4: smooth percentiles, look (k=10) x2 + colour on the z scale** | **0.90 (0.76-0.93)** | **0.96** | **9 / 9** | 19 |

Variants k = 8-10 and look weight 1.5-3 all score within 0.02, so v4 is not a lucky setting. About 20 variants
were tried against the same 9 rejects, so expect the true gain to be somewhat smaller than shown.

**Verdict lines are now calibrated on new posts:** "Off-brand" = below the 10th percentile of the real new posts'
scores (12 % of them land there, was 33-42 %), "On-brand" = above the median new post. Every result also says
"fits better than X % of the posts this team actually published next".

**Result on the labelled designs:** all 9 rejects below the on-brand line, none called Off-brand; Pandiya (accepted)
scores above all 9 rejects, WEALTH CODE (accepted) above 6 of 9 → accepted-vs-rejected AUC **0.83** (v2: 0.53).
Same-brief pairs ranked right: 67 % (6 of 9). Every real design currently lands "Borderline": the model ranks
better, but the gap between accepted and rejected is small compared with the spread of normal new posts.

## 0. Model v2 (12 Nov 2026): what changed and what it achieved

Rejected drafts are scarce (a real constraint), so v2 stops trying to learn "accepted vs rejected" and
measures **on-brand against the team's own posts**, which needs only approved posts:

- **On-brand score = percentile among the team's own posts**, from two signals: overall look (CLIP, ignoring each
  post's near-twins so series posts don't inflate the reference) and **colour match against the 8 past posts on the
  most similar topic** (Lab histogram). The classifier is only used once ≥ 20 other-page posts exist (F2).
- **Verdict wording** changed from "Likely approved / sent back" to **On-brand / Borderline / Off-brand**.
- **Audience appeal** (LAION aesthetic predictor) added as a separate number. Tested first, see below.
- **Likes model** now picks between two candidate models by cross-validation.

Experiments behind these choices (team: 74 posts; labelled: 2 accepted one-off posters, 9 rejected drafts):

| Idea tested | Result | Used? |
|---|---|---|
| LAION aesthetic score separates accepted from rejected | **No.** Rejected drafts scored 4.9–6.3, accepted 4.0 and 5.5 (it likes ornate "artsy" drafts the seniors turned down) | not for the verdict |
| LAION aesthetic score vs likes (relative to the month) | Spearman **0.25, p = 0.03** (weak but real) | shown as "audience appeal"; the likes model may use it, but cross-validation kept the CLIP model (error 1.30 vs 1.56) |
| CLIP similarity, colour layout, light/dark layout, colour histogram vs team | Team-vs-rejected AUC 0.68–0.89, **but both accepted posters ranked as low as the rejects**: these separate routine series posts from one-off posters, not accepted from rejected | no |
| Colour histogram vs the same-topic past posts | Accepted at 43rd and 15th percentile, rejects mostly ≤ 14th | yes |

**Result of v2 on the labelled posters:** all 9 rejected drafts fall below the on-brand line (scores 0–30, 6 below
"borderline"). One accepted poster scores 23 (Borderline, above 7 of 9 rejects); the other scores **0**, the same as
the five lowest rejects. Accepted-vs-rejected AUC ≈ **0.53**: **still a coin flip**. With 2 accepted examples nothing
here is statistically meaningful, and the colour-match idea was picked after looking at these same 11 posters, so its
apparent edge is likely optimistic.

What v2 does fix: scores now mean something ("more on-brand than X % of the team's posts") instead of the old
classifier giving every real poster ~0.95, and a new poster is no longer punished for having no twin in a series.

## 0b. Model v3 (12 Nov 2026): bigger models tested, finished designs, learned approval

**Bigger image models did not help.** Each candidate "view" was scored the same way as v2 (percentile among the
team's own posts, near-twins excluded) and tested on the real labelled designs: does the accepted FinLit final beat
each of its 9 rejected drafts (same brief, the real use case)?

| View | FinLit final beats drafts | Accepted vs rejected AUC (2 vs 9) | Used? |
|---|---|---|---|
| CLIP ViT-B/32 look (v1) | 2 / 9 | 0.33 | inside v2 |
| Colour vs same-topic posts (v2) | 6 / 9 | 0.72 | yes |
| v2 combined (CLIP look + colour) | 5 / 9 | 0.67 | yes (current) |
| DINOv2-small / base look (stronger self-supervised model) | 5 / 9 | 0.28 | no |
| DINOv2-base vs same-topic posts | 8 / 9 | 0.44 (Pandiya at 15th pct) | no |
| Typography from OCR text boxes, vs same-topic posts | 4 / 9 | 0.22 | no (used for finish checks) |
| Colour layout 6x8 vs same-topic posts | 2 / 9 | 0.33 | no |
| DINOv2 + colour + typography (averaged) | 4-6 / 9 | 0.31-0.47 | no |

None beats v2 on accepted-vs-rejected, and 11 labelled designs (2 accepted) cannot tell real gains from noise.
**The limit is labels, not model size**, so v3 builds the path for labels instead:

- **Finished designs can be checked** (`kind=final`, one image): on-brand score of the design itself, plus a
  **finish checklist** from text detection (EasyOCR's CRAFT detector): headline legibility (WCAG contrast),
  share of low-contrast text, amount of text, headline size, resolution, shape. Optional link to the plan check
  ("plan vs final": score change and how close the final stayed to the inspiration).
- **Every check is calibrated on the team's own posts.** With fixed rules, the first version flagged most of the
  team's approved posts: low contrast on 72 %, small text on 54 %, text near the edge on 58 %. Small-text and edge
  checks were dropped (fine print at the edges is this team's style; the detector can't see text below ~1 % of the
  height). Now each check fires on 10-17 % of approved team posts. They fire on 0-22 % of the rejected drafts, so
  **they are a readiness checklist, not an approval predictor**, and they do not change the score.
- **Approval model**: logistic regression on 15 readable inputs (on-brand parts, distance from the team's usual style
  and typography, appeal), trained only on designs with a known decision (`decision` = accepted/rejected, grouped by
  `project`). Validated leaving out one whole project at a time; used only with >= 8 accepted, >= 8 rejected, >= 3
  projects and AUC >= 0.60, then blended into final-design scores by its AUC (at most 60 %). Instagram posts alone
  never train it (they caused the series-vs-one-off problem, F1/F4).
  **Status on the real data: off** (2 accepted, 9 rejected, 2 projects; needs 6 more accepted and 1 more project).
  Tested on synthetic data, where it switches on and gets AUC >= 0.8.
- **Decisions are now data**: marking a final check approved/rejected stores that exact image with its decision and
  project; Team setup can upload "designs the seniors accepted" and rejected drafts with a project name.
- **Confidence** on every result: low when the team has posted little like the design (looks-like < 10th pct)
  or the model knows < 30 posts; the final-design result says when the approval model is not trained yet.
- **Honest metric on the Team style page**: of the 9 same-project accepted-vs-rejected pairs, the on-brand score
  ranks the accepted design higher in **56 %** (50 % = guessing).

---

## 1. What fails

### F1. Accepted and rejected posters get the same score (the big one)

| Poster | Truth | "Looks like the team" (classifier, 0–1) | Mean similarity to 5 nearest team posts |
|---|---|---|---|
| Event poster (dance night) | accepted | 0.99 | 0.48 |
| Talk poster, final | accepted | 0.95 | 0.58 (inflated: this poster is in the training set) |
| 9 drafts of the same talk poster | rejected | 0.86 – 1.00 | 0.43 – 0.53 |

Neither signal separates the two groups. A designer would get "Borderline" for both a winner and a reject.

### F2. The classifier learned "is this a clean, finished poster?", not "is this our style?" (mitigated in v2: not used without ≥ 20 other-page posts)

With no posts from other pages, the only negatives are near-misses (deliberately broken copies of team posts).
So the classifier learns to spot breakage. Every real poster, accepted or rejected, passes.

### F3. Most near-misses were contradictory labels (fixed, but leaves few negatives)

CLIP barely notices colour edits. Average CLIP similarity of a near-miss to its own original:

| Transform | Similarity to original |
|---|---|
| oversaturate | 0.93 |
| channel swap | 0.93 |
| wash out | 0.90 |
| hue shift | 0.90 |
| invert | 0.86 |
| clutter | 0.82 |
| bad crop | 0.67 |
| blur + flatten | 0.41 |

A real team post's nearest *other* team post is only 0.68 similar. So the broken copy sat closer to each post
than any real sibling did, and the model was taught "this exact poster is both us and not us". One accepted
poster that was in the training set scored 57 ("Likely sent back") because of its own oversaturated copy.

**Fix applied:** near-misses with similarity > 0.85 to their original are dropped (`NEAR_MISS_MAX_SIM`).
That removed 47 of 74, leaving 27 negatives, which is too few.

### F4. Similarity percentile is unfair to genuinely new posters (mitigated in v2: near-twins are ignored)

Team posts come in series (same template, same event, carousel-like sets). Each past post has a near-twin,
so "how close is a team post to the rest" is high. A new poster never has a twin, so it lands at the 10th
percentile even when it fits. Held-out AUC of similarity alone: **0.58** (0.5 = guessing).

**Mitigation applied:** the score mix is now weighted by each signal's held-out AUC (`_weights` in `model.py`)
instead of a fixed 50/50. It helps but cannot fix a weak signal.

### F5. Earlier accuracy numbers were misleading

The first versions reported hold-out AUC 0.87–0.91 and "8 of 8 rejected drafts caught". Those numbers measured
"real post vs broken copy" (easy, see F2/F3), not "accepted vs rejected". After removing contradictory
near-misses the honest hold-out AUC is **0.71**, and the rejected drafts score 66–73 against 71–78 for accepted posters.
The test split is also tiny (≈14 team posts), so any single number has a wide error bar.

### F6. The verdict line is not calibrated to approval (partly fixed in v4)

v4 sets the lines from how the team's real new posts scored (10 % Off-brand, median = On-brand line), which fixes
the novelty penalty. They are still calibrated on what got *posted*, not on what the seniors approved; with
decided designs the approval model should take over.

### F6b. Some accepted one-off posters score Off-brand

A poster that breaks the team's colour habits on purpose (the accepted talk poster's bright blue/purple block) gets
a low on-brand score even when the seniors liked it. "On-brand" measures sameness, and good design sometimes isn't.
The UI tells designers this ("normal for a new kind of poster, check the closest posts"), but the score itself can't.

### F7. ~~Bug: the description has no effect when there are no other pages~~ (fixed)

**Was:** with no other pages the text score fell back to a constant `sigmoid(0.6) ≈ 0.65`, whatever the designer
wrote, and the `×60` scale was hand-picked.

**Now:** the description is ranked against 40 typical poster descriptions (`REFERENCE_DESCRIPTIONS` in `model.py`):
the text score is the share of them it beats at matching the team's posts (minus other pages' posts, when there
are any). No hand-tuned scale, and it works with or without other pages. Covered by
`test_description_matters_without_other_pages`. On the real team model:

| Description | Text score |
|---|---|
| off-white paper, bold navy fest-name header, dancer photo inside large type | 0.95 |
| dark navy, bold white title, speaker cut-out, sponsor logos | 0.58 |
| neon cyberpunk city | 0.30 |
| meme with Impact font | 0.28 |
| pastel watercolour flowers | 0.10 |
| cute cartoon animals | 0.03 |

**Still open:** CLIP reads text inside images, so naming the fest in the description probably inflates the score.
The 40 reference descriptions were written by hand; a better reference set would come from real briefs.

### F8. Two "style features" are guesses (text detection now exists, see 0b, but `text_amount` still uses CLIP)

`text_amount` and `illustration` come from CLIP zero-shot prompts, not OCR or a trained detector. They are
uncalibrated, and the reasons that quote them ("yours 30, usual 30–41") can be wrong. `busyness` and `whitespace`
use hand-picked thresholds (Canny 80/160, tile std < 6).

### F9. Instagram download is slow and fragile

- Anonymous Instaloader runs at about **7 posts per minute**, and Instagram can block it at any time.
- Only the first slide of a carousel is kept. Reels become their cover frame. Video style is ignored.
- Downloading Instagram is against Instagram's terms. Fine at course scale; not for a product.
- The daily refresh only pulls the team page's last 7 days. Other pages are never refreshed.

### F10. Engagement prediction is thin

Ridge regression on 74 posts. Cross-validated error 1.30 vs 1.95 for "always usual" (log of likes ÷ the page's
monthly mean). Images and reels are mixed. The ±0.2 band edges are arbitrary. It has not been checked on posts
published after training.

### F11. Smaller product gaps

- Stored checks keep the score from the model version that made them. There is no "re-score with the latest model".
- The style map (UMAP) is fitted at training time; new points are placed with `transform`, which is approximate.
- No delete endpoints for posts, checks or teams. Uploaded inspiration images are kept forever.
- Plugin charts are drawn in one colour; plugins cannot set colours.
- Frontend bundle is 580 KB (Recharts, no code splitting). The team list loads once per page load.
- Style-map tooltips fetch the post on every hover.

### F12. Security (matters before other teams' plugins connect)

- No authentication. "Your name" is free text. CORS is `*`.
- **SSRF:** anyone can register a plugin URL, and the server will POST to it, including internal addresses.
- `POST /teams/{id}/import` with `folders` reads **any folder path on the server machine**.
- Uploads are capped at 15 MB each but not rate-limited.

### F13. Operations

- Import and retrain jobs run in threads inside the API process. A restart kills them (they are marked failed).
- SQLite, single writer. Each model version is a new joblib file; nothing cleans old ones.
- CLIP (~350 MB) loads in every process; CPU-only feature extraction is ~5–10 images per second.

### F14. Testing gaps

- Tests use a fake CLIP and synthetic posters. Nothing tests the real CLIP pipeline or real-data accuracy.
- No frontend tests. No CI.
- The evaluation steps promised in the proposal, "plan vs final" (score the plan a designer *would* have given)
  and a user test with 3–5 people, have not been done.

---

## 2. Improvements, most important first

### Data (fixes F1–F6)
1. **Get the team's draft archive**: past drafts with what happened to them (accepted / sent back), ideally 50+
   rejected. This is exactly the question the product asks. Then train accepted-vs-rejected directly.
2. **Use History outcomes**: every check marked approved/rejected (with the final image) already becomes a labelled
   example. Make this the main data source over time.
3. **Recent posts from similar pages** (other college fests, `since` = this year): real "not our style" negatives.
   They teach style vs other pages; they will not fully separate a dull draft from a good one.
4. **Group-aware evaluation**: split train/test by event or month, so series siblings never sit on both sides.
   Report a bootstrap confidence interval, not a single AUC.

### Model
5. Replace colour-only near-misses with ones CLIP actually sees: layout swaps, font swaps, other-page backgrounds
   behind team elements. Keep a near-miss only if its similarity to the original is below ~0.85.
6. With enough labelled drafts: a pairwise/ranking model ("which of these two would the seniors pick?") or a
   linear probe on CLIP features, calibrated with Platt scaling so 0.8 really means ~80 %.
7. Set the approval line from real accepted vs rejected outcomes, not from near-misses.
8. Text score (F7, fixed): strip the fest's own name from descriptions before scoring, and replace the hand-written
   reference descriptions with real briefs from past projects.
9. Replace zero-shot `text_amount` with OCR (EasyOCR's detector, already a dependency) and validate every style
   feature on 20 hand-labelled posters.
10. Similarity: compare against one representative per series (cluster first), or drop it once a real classifier exists.

### Product
11. Until F1 is fixed, present results as **"how your plan compares to past posts"** (nearest posts, feature strips,
    palette), not "will be approved".
12. "Re-score with latest model" button on old checks; show the model version on every result.
13. Plugins may set chart colours; add a plugin test button on the Plugins page.

### Engineering
14. Auth (even a shared team code), restrict CORS, and an allow-list or private-IP block for plugin URLs.
15. Restrict `folders` imports to one configured directory.
16. Job queue (RQ/Celery or a simple worker process) so restarts don't lose work.
17. Delete endpoints and a retention rule for uploads.
18. CI (GitHub Actions) running the pytest suite and the frontend build; one slow test with real CLIP.
19. Code-split the frontend charts.
