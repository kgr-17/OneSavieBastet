# OneSavie Bastet — kgr's Submissions & Optimization Methods

> The significant submissions **kgr (`yixuliu`)** ran on top of the C4 foundation framework
> (see [`REPORT.md`](REPORT.md)), each documented as a **submission recipe** — the exact
> optimization method that produced it (inputs → steps → output), with its real public *and*
> private leaderboard scores.

> **Scope — kgr only.** "Everything Is CTF" had four members on the shared Kaggle account:
> `yixuliu` (kgr, 40 submissions), `hash548`, `matseoizau`, and `wliilamsam`. This doc covers
> **only kgr's** entries. Other members' submissions — e.g. the `capped_*` row-count series
> (`wliilamsam`) and `report_recovery_v60_novel40_balanced` (the team's 519.81/215.21 top score,
> not kgr's) — are deliberately excluded. kgr's full authored ledger is saved as
> [`kgr_kaggle_submissions.csv`](kgr_kaggle_submissions.csv) (pulled from the Kaggle API after the
> 2026-06-30 reveal, filtered on `submitted_by == yixuliu`).

---

## 1. Reading the scores: public ≈ 2.5 × private

Public and private are different repo splits on different scales; across kgr's healthy submissions
**public ≈ 2.5 × private**. That ratio is normal — *not* overfit. Overfit shows up when a change
**raises public without raising private** (or lowers it). Every recipe below reports both numbers
so the transfer is visible.

**kgr's private climb (the main success line):**

| Date | Submission | Public | Private | Method (§) |
|---|---|---:|---:|---|
| 06-04 | `v6` | 309.09 | 70.89 | early C4 lookup |
| 06-11 | `v8` (teammate-442 base) | 442.88 | 145.85 | coverage maxed |
| 06-13 | **`v13_retag`** | 464.75 | **180.67** | LLM classifier (A1) |
| 06-14 | `v16_maxcontext` | 474.21 | 191.31 | maxcontext prompt (A2) |
| 06-24 | `v33_ee25fix_gold` | 475.07 | **192.31** | gold tag fixes (A3) |
| 06-28 | `v46_5pass_srccode` | 479.21 | 192.69 | 5-pass consensus (A4) |
| 06-28 | **`v55_swing_safe`** | 481.21 | **193.59** | safe coverage swing (A5) — **kgr's best private** |
| 06-29 | `v59_gitfix_descrewrite` | **482.97** | 190.57 | concise descriptions (B1) — **best public, overfit** |

Private went **70.9 → 193.6**. The label/gold/coverage work generalized; the final-day description
push (B1) took public to its peak but **did not** move private.

---

## 2. Category A — methods that won on public *and* private

### A1. `v13_retag` — LLM labeling-function classifier  ·  464.75 / 180.67  *(+22 public, the breakpoint)*
**Base:** teammate-442 coverage file (`v11`). **Method:**
1. Flag the ~145 **guessed** rows — audits with no gold `tag` in `dataset_0831`. Leave gold rows untouched.
2. For each, prompt an LLM with the **OneSavie taxonomy + few-shot examples**, 3-pass.
3. **Override `tag`/`subtag`** where ≥⅔ of passes agree. Row counts, severity, descriptions unchanged (pure-label).

**Why it generalized:** the labeling function (taxonomy + annotator conventions) is a property of the
finding, not the split, so both public (+22) and private (145.85→180.67) moved. This is the single
largest private lever in kgr's ladder.

### A2. `v16_maxcontext` — pinpoint-the-defect prompt  ·  474.21 / 191.31
**Base:** `v15`. **Method:** same override pipeline as A1, but the classification prompt is the
**tournament-winning `maxcontext` strategy** — feed the aligned **canonical audit text + extracted
code**, instruct the model to *first state the exact code-level defect, then* emit the label.
3-pass, ≥⅔ override.

**Why it generalized:** reading the real code before labeling fixed confusable tags. Private rose to
191.31 and held there across the whole mid-ladder — the classifier's true ceiling.

### A3. `v33_ee25fix_gold` — verified gold tag corrections  ·  475.07 / 192.31
**Base:** `v16_ee25fix`. **Method:** apply **3 hand-verified `dataset_0831` gold corrections**
where the classifier was wrong — `pid216` notional→**ERC4626/Rounding**, `pid286` sturdy→**TWAP**,
`pid309` sturdy→**Slippage** — each corroborated by the subtag. Pure-label, counts unchanged.

**Why it generalized:** gold is ~100% truth. Tied public, but private 191.31→192.31. The same single
ERC4626 correction later carried `v49`→`v50` (+1.0 private), confirming **gold beats guesses on the
hidden split.**

### A4. `v46_5pass_srccode` — 5-pass × source-code consensus  ·  479.21 / 192.69
**Base:** 479.96 (`correction_hp`). **Method:**
1. Run the relabel **5 independent Opus passes**.
2. Independently classify from **extracted Solidity source** (`extract_finding_code.py`, see B1 step 2).
3. **Override only the 18 tag / 15 subtag rows where the 5 passes are UNANIMOUS *and* the source-code
   model agrees.** Protect the 13 human-corrected rows.

**Why it generalized:** the unanimous∩source-agree gate keeps only high-confidence flips → private 192.69.

### A5. `v55_swing_safe` — the safe coverage swing  ·  481.21 / 193.59  *(kgr's best private)*
**Method** (`build_swing.py`, small N):
1. **Drop the 6 lowest-canonical-match rows** (weak/version-drift), while **PROTECTING** git-fixed,
   gold, and strong report-grounded rows, and **never** leaving a repo with <2 rows.
2. **Add 6 dedup-verified canonical findings** (real C4 report text, report-grounded tags) to the
   **deepest-deficit repos** (popcorn/frax), preferring **High** severity, diversified across contests.
3. Re-sort by `Property`, write CSV.

**Why it generalized — and the irony:** kgr's daily record dismissed this as "tied public, no
signal." The private reveal says otherwise: **193.59, the highest private of kgr's entire ladder.**
The 6 swapped-in real findings happened to land in private-split repos. *A change can be invisible on
public yet be your single best private move.*

---

## 3. Category B — overfit: public up, private flat or down

(Less significant as wins — included because they show which **optimization methods over-fit** here.)

### B1. `v59_gitfix_descrewrite` — concise description rewrite  ·  482.97 / 190.57  *(best public, −1.02 private)*
This is the method kgr asked to detail. **Base:** `v58_gitfix` (481.21 / 191.59).

**Step 1 — find the matching code** (`extract_finding_code.py`): for each of the 289 guessed rows,
- parse Solidity identifiers from the description — `Contract.function()`, bare `func()`, CamelCase
  contract names — after stripping auditor-credit boilerplate;
- `grep` the repo's `.sol` files (skipping `mock`/`test`/`interface`/`lib`) for those identifiers;
- score files by identifier-hit count, and **extract the matching `function …{ }` bodies** (≤6000
  chars) as the grounding snippet.

**Step 2 — rewrite the description:** feed the matched code + the aligned canonical finding to the
LLM and regenerate the description in a **concise "Cause: … / Impact: …"** form (~291 chars, terse
like the hidden truth), grounded in the real code.

**Step 3 — keep everything else fixed:** `tag`/`subtag`/`severity`/row-count unchanged (pure-label),
write CSV.

**Result & why it overfit:** crossing the BGE-0.7 cliff on more pairs gained **+1.76 public**
(481.21→482.97, kgr's best public, the locked final). But **private fell −1.02** (191.59→190.57).
The whole follow-on description line confirms it — every variant raised/held public while private
stayed pinned:

| Submission | Public | Private | desc change |
|---|---:|---:|---|
| `v58_gitfix` (base) | 481.21 | **191.59** | — |
| `v59_gitfix_descrewrite` | **482.97** | 190.57 | 289 rows → concise Cause/Impact |
| `v61b_golddesc` | 482.66 | 190.57 | + compress 23 gold rows |
| `v62b_tight289` | 481.93 | 190.43 | tighten 289 → 223 chars |
| `v64_exactds` | 477.27 | 190.57 | 37 rows → exact dataset_0831 text |

**Lesson:** description-style tuning is a **public lever, not a private one** — it fits the public
split's semantic-similarity scoring without adding real signal the private split rewards. Selecting
`v59` because it topped *public* cost ~3 private points versus `v55` (193.59).

### B2. `v15_canonical` vs `v15_subtag` — aggressive retag overfit  ·  471.18 / 180.32  vs  464.62 / 183.23
Two builds off `v13`: a **safe** one refining only 51 subtags where the tag agrees, and an
**aggressive** full canonical re-tag (79 tag + 109 subtag diffs). kgr selected the aggressive one as
"NEW BEST" on its **+6.56 public** (464.62→471.18). The private reveal flips it: aggressive
**180.32** vs safe **183.23** — the broad retag **lost −2.91 private**. Over-relabeling fit the
public split and damaged the hidden one; the conservative, agree-gated edit was the better
generalizer.

> **Honest note on the git-fix.** kgr's record predicted `v58_gitfix` would be a private win.
> The data says it **tied `v50` on both splits** (481.21 / 191.59) — the 7 corrected wrong-contest
> rows scored ~0 before *and* after on the hidden split. A documented method whose predicted private
> gain did not materialize; the real private gains came from A3/A4/A5.

---

## 4. Appendix — kgr's full ledger

[`kgr_kaggle_submissions.csv`](kgr_kaggle_submissions.csv) — all 40 `yixuliu` submissions with
`file, date, public, private, description`. Sort by `private` for the generalizing ranking; flag any
row where `public/private ≫ 2.5` as overfit-suspect.
</content>
