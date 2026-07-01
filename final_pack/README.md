# final_pack — OneSavie Bastet C4 Foundation

A clean, self-contained extract of the **foundational Code4rena (C4) lookup framework,
workflow, dataset, and containerized runtime** for the Kaggle *OneSavie Bastet* smart-contract
vulnerability competition. Experiment variants, daily logs, and dead-ends are excluded — only the
reusable structure is here.

**→ Start with [`REPORT.md`](REPORT.md)** — the full explanation of the framework, workflow,
dataset, scoring, and how to run it.

**→ Then [`experiments.md`](experiments.md)** — **kgr's** (`yixuliu`) significant submissions only,
each written as a **submission recipe** (the exact optimization method, inputs→steps→output) with
real public + private LB scores (Kaggle API, post-deadline). Methods that generalized (private
70.9→193.6) vs ones that overfit public (the concise-description rewrite: +1.76 public, −1.02
private). Raw kgr-only ledger in [`kgr_kaggle_submissions.csv`](kgr_kaggle_submissions.csv).

## The idea in one sentence

The 12-char hex repo IDs are **folder names inside two public Azure-blob zips**, each folder is a
public C4/Sherlock audit, so the task is *identify the audit → transcribe its real findings*
(Era 1, coverage), then *model the competition's `(tag, subtag)` labeling function with an LLM and
fix the guessed labels in place* (Era 2, labels).

## Layout

| Folder | What's in it |
|---|---|
| [`pipeline/`](pipeline/) | Era-1 C4 + Sherlock lookup workflow (download → identify → generate) |
| [`classifier/`](classifier/) | Era-2 LLM labeling-function classifier (the `tag`/`subtag` fixer) |
| [`common/`](common/) | Submission validation + the local scoring standard + taxonomy loader |
| [`references/`](references/) | The competition tag/subtag label space |
| [`dataset/`](dataset/) | `train.csv`, `test.csv`, submission schema, and the hash→contest map |
| [`docker/`](docker/) | Containerized runtime (`Dockerfile`, compose, requirements) |

Score ladder: statistical priors ~117 → C4 lookup 218 → +`dataset_0831` 312 → coverage-maxed 442
→ LLM classifier **474**. (Full ladder and per-experiment reasoning: see `REPORT.md` §8.)
</content>
