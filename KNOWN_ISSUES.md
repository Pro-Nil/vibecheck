# Known issues and improvements

Honest status as of 11 Nov 2026. Everything below was found by running the app on real data:
74 posts from one fest's Instagram page (Mar–Nov 2026) and 9 drafts of one talk poster that the design
team rejected, plus 2 posters the team accepted.

**Short version:** the pipeline, API, plugins and dashboards work end to end. The model does **not** yet do
the one thing the product promises: it cannot tell a poster the team will accept from one it will reject.
The cause is data, not code, and the fix is listed under "Improvements".

---

## 1. What fails

### F1. Accepted and rejected posters get the same score (the big one)

| Poster | Truth | "Looks like the team" (classifier, 0–1) | Mean similarity to 5 nearest team posts |
|---|---|---|---|
| Event poster (dance night) | accepted | 0.99 | 0.48 |
| Talk poster, final | accepted | 0.95 | 0.58 (inflated: this poster is in the training set) |
| 9 drafts of the same talk poster | rejected | 0.86 – 1.00 | 0.43 – 0.53 |

Neither signal separates the two groups. A designer would get "Borderline" for both a winner and a reject.

### F2. The classifier learned "is this a clean, finished poster?", not "is this our style?"

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

### F4. Similarity percentile is unfair to genuinely new posters

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

### F6. The "likely approved" line is not calibrated to approval

The line comes from Youden's J on team posts vs near-misses, then is clipped to 30–85. It currently sits at the
85 cap. It says nothing about what the seniors actually approve.

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

### F8. Two "style features" are guesses

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
