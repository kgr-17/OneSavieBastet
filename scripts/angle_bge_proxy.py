"""Offline BGE proxy for the minimal-risk add-deficit angle.

Question: if we add a deficit finding using an md-extracted sentence as its
description, what fraction clear the BGE>0.7 bar against the COMPETITION TRUTH
description? We cannot see test truth, but train.csv truth descriptions exist
for contests whose .md reports we also have. We match md-extracted sentences to
train truth via greedy cosine and report matched-pair BGE.
"""
import csv, json, os, re, sys
from pathlib import Path

ROOT = Path(r"c:/OneSavieBastet")
REPORTS = ROOT / "data/dataset_v0/reports"

def norm(rp):
    rp = rp.strip()
    return rp[6:] if rp.startswith("repos/") else rp

def load_train_map():
    h2c = {}
    for f in ["artifacts/train_hash_to_contest_v3.json",
              "artifacts/train_hash_to_contest_verified.json"]:
        m = json.load(open(ROOT / f, encoding="utf-8"))
        for h, v in m.items():
            c = v.get("contest") if isinstance(v, dict) else v
            if c:
                h2c.setdefault(h, c)
    return h2c

TITLE_RE = re.compile(r"^##\s*\[?\[?[HML]-?\d*\]?\s*(.*?)\]?\(http", re.IGNORECASE)

def extract_sentence(md_path):
    """Title + first paragraph of Impact/body, cleaned. The 'no-LLM' extractor."""
    txt = open(md_path, encoding="utf-8", errors="replace").read()
    lines = txt.splitlines()
    title = ""
    if lines:
        m = re.match(r"^##\s*\[+\s*(?:[HML]-?\d+\]?\s*)?(.*?)\]\(http", lines[0])
        if m:
            title = m.group(1)
        else:
            title = re.sub(r"^#+\s*", "", lines[0])
        title = re.sub(r"\]\(http.*$", "", title)
        title = title.replace("\\", "").replace("`", "").strip(" []")
    # find Impact section or first substantive paragraph (skip links/submitted-by)
    body = ""
    capture = False
    for ln in lines[1:]:
        s = ln.strip()
        if s.lower().startswith("### impact") or s.lower() == "impact":
            capture = True
            continue
        if capture and s and not s.startswith("###"):
            body = s
            break
    if not body:
        for ln in lines[1:]:
            s = ln.strip()
            if (s and not s.startswith("*Submitted") and not s.startswith("<http")
                    and not s.startswith("#") and len(s) > 40):
                body = s
                break
    body = body.replace("\\", "").replace("`", "")
    sent = (title + ". " + body).strip()
    return sent[:400]

def main():
    h2c = load_train_map()
    reportdirs = set(os.listdir(REPORTS))
    tr = list(csv.DictReader(open(ROOT / "train.csv", encoding="utf-8-sig")))
    # group train findings by contest (via hash)
    by_contest = {}
    for r in tr:
        c = h2c.get(norm(r["repo_path"]))
        d = (r.get("description") or "").replace("\xa0", " ").strip()
        if c in reportdirs and d:
            by_contest.setdefault(c, []).append(d)

    # pick contests with decent overlap and md files
    targets = sorted(by_contest, key=lambda c: -len(by_contest[c]))[:6]
    print("Loading BGE model (BAAI/bge-large-en-v1.5)...", flush=True)
    from sentence_transformers import SentenceTransformer
    import numpy as np
    model = SentenceTransformer("BAAI/bge-large-en-v1.5")

    def emb(texts):
        v = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(v)

    all_hits = 0
    all_pairs = 0
    for c in targets:
        truths = by_contest[c]
        d = REPORTS / c
        mds = sorted(d.glob("*.md"))
        sents = [extract_sentence(p) for p in mds]
        sents = [s for s in sents if len(s) > 15]
        if not sents or not truths:
            continue
        T = emb(truths)
        S = emb(sents)
        sim = T @ S.T  # truths x sents cosine
        # greedy one-to-one: each truth takes best available sentence
        used = set()
        scores = []
        order = list(range(len(truths)))
        # match in order of best-available
        flat = [(sim[i, j], i, j) for i in range(len(truths)) for j in range(len(sents))]
        flat.sort(reverse=True)
        matched_t = set()
        for sc, i, j in flat:
            if i in matched_t or j in used:
                continue
            matched_t.add(i); used.add(j)
            scores.append(sc)
        scores.sort(reverse=True)
        hits = sum(1 for s in scores if s > 0.7)
        print(f"{c:28s} truths={len(truths):3d} mds={len(sents):3d} "
              f"matched={len(scores):3d} BGE>0.7={hits:3d} "
              f"({hits/max(1,len(scores))*100:4.0f}%) "
              f"mean_top_sim={sum(scores[:len(truths)])/max(1,len(scores[:len(truths)])):.3f}")
        all_hits += hits
        all_pairs += len(scores)
    print()
    print(f"OVERALL matched pairs={all_pairs} BGE>0.7={all_hits} "
          f"({all_hits/max(1,all_pairs)*100:.1f}%)")

if __name__ == "__main__":
    main()
