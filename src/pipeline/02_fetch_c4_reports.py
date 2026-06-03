"""For each *-findings repo, try to fetch report.md / README.md from raw.githubusercontent.com.
Saves to artifacts/c4_reports/{contest}.md. Skips contests already downloaded."""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

REPOS_JSON = "artifacts/c4_repos.json"
OUT_DIR = "artifacts/c4_reports"

# Try these files in order. Most C4 audits use report.md; some use README.md.
CANDIDATE_FILES = ["report.md", "README.md", "data/report.md"]
BRANCHES = ["main", "master"]


def fetch(full_name: str, default_branch: str) -> Tuple[str, Optional[bytes], str]:
    """Returns (contest_name, content_bytes_or_None, source_path)."""
    contest = full_name.split("/")[-1].removesuffix("-findings")
    branches = [default_branch] + [b for b in BRANCHES if b != default_branch]
    for branch in branches:
        for filename in CANDIDATE_FILES:
            url = f"https://raw.githubusercontent.com/{full_name}/{branch}/{filename}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "c4-phase1"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = r.read()
                    if data and len(data) > 200:
                        return contest, data, f"{branch}/{filename}"
            except urllib.error.HTTPError:
                continue
            except Exception:
                continue
    return contest, None, ""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(REPOS_JSON, encoding="utf-8") as f:
        repos = json.load(f)
    findings_repos = [r for r in repos if r["name"].endswith("-findings")]
    print(f"Processing {len(findings_repos)} -findings repos\n", flush=True)

    done, missing = 0, 0
    skipped = 0

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {}
        for r in findings_repos:
            contest = r["name"].removesuffix("-findings")
            out_path = os.path.join(OUT_DIR, f"{contest}.md")
            if os.path.exists(out_path):
                skipped += 1
                continue
            futures[pool.submit(fetch, r["full_name"], r["default_branch"])] = contest

        for fut in as_completed(futures):
            contest, content, src = fut.result()
            if content:
                out_path = os.path.join(OUT_DIR, f"{contest}.md")
                with open(out_path, "wb") as f:
                    f.write(content)
                done += 1
                if done % 25 == 0:
                    print(f"  fetched {done} ...", flush=True)
            else:
                missing += 1

    print(f"\nDone. fetched={done}, missing={missing}, skipped(existing)={skipped}")
    print(f"Output: {OUT_DIR}/")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
