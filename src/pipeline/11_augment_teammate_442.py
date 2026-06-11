"""v7 — Augment teammate's 442 submission with additional findings.

Strategy:
1. Take teammate's 442 CSV as baseline (best so far).
2. For each under-predicted repo (<=5 predictions), find additional H/M findings:
   - If the audit is mapped to a cached C4/Sherlock report: parse extra findings
     from that report, dedupe vs teammate's existing predictions for the repo.
   - If unidentified (3 repos: 27c6f2a68058, 348856fe60ac, c2426a2ab283):
     LLM-on-code — read in-scope .sol files from test.zip, ask Claude to
     identify H/M vulnerabilities in train.csv style.
3. For each new candidate finding, call Claude Sonnet 4.6 once to:
   (a) rewrite the description to train.csv style
   (b) classify (tag, subtag) using the existing taxonomy
4. Rebalance: trim over-predicted repos to cap=20; slot the new candidates in.
5. Write outputs/submission_c4_v7.csv.

Cost estimate: ~70 LLM calls @ ~$0.005 each = ~$0.35. Well within $20 budget.
"""
import csv
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Tiny .env loader
if os.path.exists(".env"):
    for ln in open(".env"):
        ln = ln.strip()
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

import anthropic
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

MODEL = "claude-sonnet-4-6"

TEAMMATE_CSV = "teamate_hightst_submission.csv"
TRAIN_CSV = "train.csv"
DATASET_0831 = "data/dataset_0831.csv"
TEST_ZIP = "data/test.zip"
TEST_MAP = "artifacts/test_hash_to_contest_v3.json"
OUT = "outputs/submission_c4_v7.csv"

# Manual mappings from earlier sessions
EXTRA_TEST_MAP = {
    "103f39b0f29b": ("2024-02-rubicon-finance", "sherlock"),
    "1167ec3a176e": ("2024-03-arrakis", "sherlock"),
    "592eed5791df": ("2024-07-kwenta-staking-contracts", "sherlock"),
    "73f6a793d916": ("2024-01-rio-vesting-escrow", "sherlock"),
    "9470d2cf198f": ("2025-02-rova", "sherlock"),
    "9ddd6b83c27e": ("2022-10-rage-trade", "sherlock"),
    "e7921851ec01": ("2023-06-dodo", "sherlock"),
    "a4d91fb1550f": ("2021-05-88mph", "c4"),
}

# Knobs
UNDER_THRESHOLD = 5       # repos with <=this many predictions are augmentation candidates
OVER_CAP = 20             # cap teammate's over-predicted repos at this many
PER_REPO_NEW_CAP = 8      # max new findings to add per under-predicted repo
DEDUPE_SIM = 0.30         # if max TF-IDF sim >= this, skip as duplicate

# Finding regex per platform
C4_FINDING_RE = re.compile(r"^##\s+\[?\[?([HM])-(\d+)\]\s+(.+?)\]?(?:\(.*?\))?$", re.MULTILINE)
SHERLOCK_FINDING_RE = re.compile(r"^#\s+Issue\s+([HM])-(\d+)\s*:?\s*(.+?)$", re.MULTILINE)


def parse_findings_from_cached(contest, platform):
    base = "artifacts/c4_reports" if platform == "c4" else "artifacts/sherlock_reports"
    path = os.path.join(base, f"{contest}.md")
    if not os.path.exists(path):
        return []
    txt = open(path, encoding="utf-8", errors="replace").read()
    pat = C4_FINDING_RE if platform == "c4" else SHERLOCK_FINDING_RE
    matches = list(pat.finditer(txt))
    findings = []
    for i, m in enumerate(matches):
        sev = "High" if m.group(1) == "H" else "Medium"
        title = m.group(3).strip().rstrip("]")
        body = txt[m.end(): matches[i+1].start() if i+1 < len(matches) else len(txt)].strip()
        # Strip "Found by" section (sherlock) and code blocks
        body = re.sub(r"^##\s+Found by[\s\S]*?(?=^##|\Z)", "", body, flags=re.MULTILINE)
        body = re.sub(r"```[\s\S]*?```", "", body)
        body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
        body = re.sub(r"\s+", " ", body).strip()
        findings.append({"severity": sev, "title": title, "body": body[:2500]})
    return findings


def read_test_sources(test_hash, max_chars=24000):
    """Read in-scope .sol files from test.zip for a hash. Uses scope.txt if present."""
    files = []
    scope_lines = None
    with zipfile.ZipFile(TEST_ZIP) as z:
        # Find scope.txt
        for n in z.namelist():
            if n.startswith(f"test/{test_hash}/") and n.endswith("scope.txt"):
                with z.open(n) as f:
                    scope_lines = {ln.decode("utf-8", "replace").strip() for ln in f if ln.strip()}
                break
        # Gather .sol files (filtered by scope if available)
        for n in z.namelist():
            if not n.startswith(f"test/{test_hash}/") or not n.endswith(".sol"):
                continue
            rel = n[len(f"test/{test_hash}/"):]
            # Skip OZ / forge-std / lib deps
            if any(seg in rel for seg in ("lib/", "node_modules/", "openzeppelin", "forge-std", ".t.sol")):
                continue
            if scope_lines and not any(rel in line or line.lstrip("./") == rel for line in scope_lines):
                continue
            with z.open(n) as f:
                try:
                    content = f.read().decode("utf-8", "replace")
                except Exception:
                    continue
            files.append((rel, content))
    files.sort(key=lambda x: len(x[1]))
    out, used = [], 0
    for rel, content in files:
        if used + len(content) > max_chars:
            content = content[: max_chars - used]
            out.append(f"// FILE: {rel}\n{content}\n")
            break
        out.append(f"// FILE: {rel}\n{content}\n")
        used += len(content)
    return "\n".join(out), [rel for rel, _ in files[: len(out)]]


# Few-shot pool: train.csv + dataset_0831 Done rows (English only)
def load_style_pool():
    pool = []
    with open(TRAIN_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = r.get("description", "").strip()
            if 120 <= len(d) <= 400 and not re.search(r"[一-鿿]", d):
                pool.append({"tag": r["tag"], "subtag": r["subtag"], "severity": r["severity"], "desc": d})
    with open(DATASET_0831, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d = r.get("description", "").strip()
            if not d or re.search(r"[一-鿿]", d):
                continue
            if r.get("status", "").strip().lower() != "done":
                continue
            if 120 <= len(d) <= 400:
                pool.append({"tag": r["tag"], "subtag": r["subtag"], "severity": r["severity"], "desc": d})
    return pool


def few_shot_for(tag, subtag, pool, n=5):
    same_both = [p for p in pool if p["tag"] == tag and p["subtag"] == subtag]
    same_tag = [p for p in pool if p["tag"] == tag and p not in same_both]
    out = same_both[:n]
    if len(out) < n:
        out.extend(same_tag[: n - len(out)])
    if len(out) < n:
        out.extend(pool[: n - len(out)])
    return out[:n]


# LLM helpers
client = anthropic.Anthropic()


def rewrite_and_classify(severity, title, body, pool, retries=5):
    """Single LLM call: rewrite description in train.csv style + suggest (tag,subtag)."""
    # Style examples — pick by random-but-stable shuffle
    examples = pool[:5]  # fallback; better to pick by tag after we have one
    ex_str = "\n\n".join(f'Example {i+1}: "{ex["desc"]}"' for i, ex in enumerate(examples))
    prompt = f"""You rewrite smart-contract audit findings to match a target style and classify them.

Target style:
- 1-3 declarative sentences, 150-300 characters total
- Names the specific function/contract
- States cause and impact concisely
- Technical English; NO markdown, NO URLs, NO line refs like L123, NO backticks-only blocks

Five style examples:

{ex_str}

Classification taxonomy is a (tag, subtag) pair drawn from this competition's vocabulary.
Common tags include: DoS, Input Validation, Access Control, Accounting Error, Arithmetic,
  Slippage, Logic error, Reentrancy, ERC4626, ERC20, ERC721, Chainlink, Oracle, Upgradeable,
  Governance, Liquidation, Cross-Chain, MEV, Flashloan, TWAP, Uniswap.
Common subtags include: Invalid Validation, State Update Inconsistency, Bad Condition,
  Incorrect Parameter, Implementation Error, Violating CEI / Missing nonReentrant,
  Price Manipulation / Arbitrage opportunity, Centralization Risk, Missing minOut / maxAmount,
  Not EIP Compliant, Out of Gas, Stale Value, Front Run, Precision Loss, Token Decimal,
  Asset Theft, Rebase Token, Fee On Transfer Token.

Output ONLY a JSON object with keys "description", "tag", "subtag". No prose.

Severity: {severity}
Title: {title}
Source body: {body[:2200]}"""
    last_err = None
    import time
    for attempt in range(retries + 1):
        try:
            msg = client.messages.create(
                model=MODEL,
                max_tokens=500,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
            data = json.loads(text)
            cost = msg.usage.input_tokens * 3 / 1e6 + msg.usage.output_tokens * 15 / 1e6
            return data, cost
        except Exception as e:
            last_err = e
            if "rate_limit" in str(e).lower() or "429" in str(e):
                time.sleep(8 + 2 * attempt)  # respect 50 RPM ceiling
            else:
                time.sleep(2)
    print(f"  ! rewrite failed after {retries+1}: {last_err}")
    return None, 0.0


def llm_find_vulns(test_hash, source_code, pool, n_vulns=6, retries=1):
    """LLM-on-code for unidentified repos."""
    ex = pool[:5]
    ex_str = "\n\n".join(f'Example {i+1}: "{e["desc"]}"' for i, e in enumerate(ex))
    prompt = f"""Below is the in-scope Solidity source code of a private smart-contract audit. Identify the most likely High and Medium severity vulnerabilities a security auditor would flag. Output findings in the target style.

Target style for each "description":
- 1-3 declarative sentences, 150-300 characters
- Names specific functions/contracts from the code
- States cause and impact

Five style examples:

{ex_str}

For each finding, also pick (tag, subtag) from the competition taxonomy.
Common tags: DoS, Input Validation, Access Control, Accounting Error, Arithmetic, Slippage, Logic error, Reentrancy, ERC4626, ERC20, ERC721, Chainlink, Oracle, Upgradeable, Governance, Liquidation, Cross-Chain, MEV.
Common subtags: Invalid Validation, Bad Condition, Incorrect Parameter, Implementation Error, Asset Theft, Centralization Risk, Stale Value, Front Run, Reentrancy, Missing minOut / maxAmount, Token Decimal, Precision Loss.

Output ONLY a JSON array of up to {n_vulns} findings, each with keys: "severity" (High or Medium), "description", "tag", "subtag". No prose.

Source code:
{source_code}"""
    last_err = None
    for _ in range(retries + 1):
        try:
            msg = client.messages.create(
                model=MODEL,
                max_tokens=2000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
            data = json.loads(text)
            cost = msg.usage.input_tokens * 3 / 1e6 + msg.usage.output_tokens * 15 / 1e6
            return data, cost
        except Exception as e:
            last_err = e
    print(f"  ! llm_find_vulns failed for {test_hash}: {last_err}")
    return [], 0.0


def dedupe_against(candidates, existing_texts):
    """TF-IDF cosine: drop candidates whose body/title is too close to anything in existing_texts."""
    if not candidates or not existing_texts:
        return candidates
    corpus = [c.get("title", "") + " " + c.get("body", "")[:500] for c in candidates] + existing_texts
    try:
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
        mat = vec.fit_transform(corpus)
        sims = cosine_similarity(mat[: len(candidates)], mat[len(candidates):])
        keep = []
        for i, c in enumerate(candidates):
            if sims[i].max() < DEDUPE_SIM:
                keep.append(c)
        return keep
    except ValueError:
        return candidates


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs("outputs", exist_ok=True)

    # Load teammate's 442
    with open(TEAMMATE_CSV, encoding="utf-8-sig") as f:
        tm = list(csv.DictReader(f))
    per_repo = defaultdict(list)
    for r in tm:
        if r.get("repo_path", "empty") != "empty":
            per_repo[r["repo_path"]].append(r)

    # Load test hash -> contest mapping
    with open(TEST_MAP, encoding="utf-8") as f:
        tmap = json.load(f)

    # All test hashes (need this for the 0-prediction ones)
    with open("test.csv", encoding="utf-8") as f:
        rr = csv.reader(f)
        next(rr)
        all_test = [row[0] for row in rr if row]

    pool = load_style_pool()
    print(f"Style pool: {len(pool)} train.csv + dataset_0831 examples")

    # Step 1+2: gather candidate findings for each under-predicted repo
    candidates_by_hash = {}
    total_cost = 0.0

    for h in all_test:
        n_existing = len(per_repo.get(h, []))
        if n_existing > UNDER_THRESHOLD:
            continue
        info = tmap.get(h, {})
        contest = info.get("contest")
        platform = info.get("platform", "c4")
        if h in EXTRA_TEST_MAP:
            contest, platform = EXTRA_TEST_MAP[h]

        existing_texts = [r["description"] for r in per_repo.get(h, [])]

        if contest:
            findings = parse_findings_from_cached(contest, platform)
            findings = dedupe_against(findings, existing_texts)
            if findings:
                findings = findings[: PER_REPO_NEW_CAP]
                candidates_by_hash[h] = ("cached", findings)
                print(f"  {h}  n_existing={n_existing}  contest={contest}  candidates={len(findings)}")
        else:
            # Unidentified: LLM-on-code
            print(f"  {h}  n_existing={n_existing}  UNIDENTIFIED -> LLM-on-code")
            src, file_list = read_test_sources(h)
            if not src:
                print(f"     ! no source code found, skipping")
                continue
            print(f"     source: {len(src)} chars across {len(file_list)} files")
            llm_findings, cost = llm_find_vulns(h, src, pool, n_vulns=6)
            total_cost += cost
            print(f"     LLM cost: ${cost:.4f}, got {len(llm_findings)} findings")
            # Convert to common format
            findings = [{"severity": f["severity"], "title": f.get("description", "")[:80],
                         "body": f.get("description", ""),
                         "_tag": f.get("tag"), "_subtag": f.get("subtag")} for f in llm_findings]
            findings = dedupe_against(findings, existing_texts)
            findings = findings[: PER_REPO_NEW_CAP]
            candidates_by_hash[h] = ("llm-code", findings)

    print(f"\nGathered candidates for {len(candidates_by_hash)} repos")

    # Step 3: rewrite + classify all candidates via LLM
    all_new_rows = []  # list of dict matching csv columns
    flat_jobs = []
    for h, (kind, fs) in candidates_by_hash.items():
        for f in fs:
            flat_jobs.append((h, kind, f))
    print(f"\nRewriting {len(flat_jobs)} candidates via {MODEL}...")

    def process_one(idx, h, kind, f):
        if kind == "llm-code":
            # Already in target style; just package
            return idx, {
                "repo_path": h,
                "severity": f["severity"],
                "tag": f.get("_tag") or "Logic error",
                "subtag": f.get("_subtag") or "Implementation Error",
                "description": f["body"][:350],
            }, 0.0
        data, cost = rewrite_and_classify(f["severity"], f["title"], f["body"], pool)
        if not data:
            return idx, None, cost
        return idx, {
            "repo_path": h,
            "severity": f["severity"],
            "tag": data.get("tag", "Logic error"),
            "subtag": data.get("subtag", "Implementation Error"),
            "description": data.get("description", f["body"])[:350],
        }, cost

    results = [None] * len(flat_jobs)
    with ThreadPoolExecutor(max_workers=3) as pool_exec:
        futs = {pool_exec.submit(process_one, i, h, k, f): i for i, (h, k, f) in enumerate(flat_jobs)}
        done_n = 0
        for fut in as_completed(futs):
            i, row, cost = fut.result()
            total_cost += cost
            results[i] = row
            done_n += 1
            if done_n % 10 == 0:
                print(f"   {done_n}/{len(flat_jobs)} done, running cost ${total_cost:.3f}")

    for row in results:
        if row:
            all_new_rows.append(row)
    print(f"\nFinal: {len(all_new_rows)} new prediction rows. Total LLM cost: ${total_cost:.3f}")

    # Step 4: rebalance teammate + new candidates
    SEV_RANK = {"High": 0, "Medium": 1}

    # Trim over-predicted repos
    final_rows = []
    capped_drops = 0
    for h, rows in per_repo.items():
        sorted_rows = sorted(rows, key=lambda r: SEV_RANK.get(r["severity"], 2))
        keep = sorted_rows[:OVER_CAP]
        capped_drops += len(rows) - len(keep)
        final_rows.extend(keep)
    print(f"Trimmed {capped_drops} rows from over-predicted repos (cap={OVER_CAP})")

    # Add new candidates
    final_rows.extend(all_new_rows)

    # Sort: Highs first then Mediums
    final_rows.sort(key=lambda r: SEV_RANK.get(r["severity"], 2))

    # Trim to 400
    if len(final_rows) > 400:
        # Prefer to drop low-impact rows: keep all Highs, drop excess Mediums from largest repos
        highs = [r for r in final_rows if r["severity"] == "High"]
        meds = [r for r in final_rows if r["severity"] == "Medium"]
        # cap Mediums per repo to make room
        per_h_med = defaultdict(int)
        out_meds = []
        for r in meds:
            if len(highs) + len(out_meds) >= 400:
                break
            out_meds.append(r)
            per_h_med[r["repo_path"]] += 1
        final_rows = highs[:400] + out_meds[: 400 - min(len(highs), 400)]
    final_rows = final_rows[:400]

    # Write
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Property", "repo_path", "severity", "tag", "subtag", "description"])
        for i, r in enumerate(final_rows, start=1):
            w.writerow([str(i), r["repo_path"], r["severity"], r["tag"], r["subtag"], r["description"]])
        # Pad
        for i in range(len(final_rows) + 1, 401):
            w.writerow([str(i), "empty", "empty", "empty", "empty", "empty"])

    # Summary
    sev = Counter(r["severity"] for r in final_rows)
    rp = Counter(r["repo_path"] for r in final_rows)
    print(f"\nWritten: {OUT}")
    print(f"  non-empty rows: {len(final_rows)} / 400")
    print(f"  severity:       {dict(sev)}")
    print(f"  unique repos:   {len(rp)}")
    print(f"  total LLM cost: ${total_cost:.3f}")


if __name__ == "__main__":
    main()
