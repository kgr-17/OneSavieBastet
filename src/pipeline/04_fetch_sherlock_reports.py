"""Fetch README.md from each sherlock-audit/{name}-judging repo. The README is the
full audit report — section headers like '# Issue H-1: title' / '# Issue M-1: title'."""
import json
import os
import sys
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Tuple

REPOS_JSON = "artifacts/sherlock_repos.json"
OUT_DIR = "artifacts/sherlock_reports"
BRANCHES = ["main", "master"]


def fetch(full_name, default_branch) -> Tuple[str, Optional[bytes], str]:
    contest = full_name.split("/")[-1].removesuffix("-judging")
    branches = [default_branch] + [b for b in BRANCHES if b != default_branch]
    for branch in branches:
        url = f"https://raw.githubusercontent.com/{full_name}/{branch}/README.md"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sherlock-fetcher"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
                if data and len(data) > 200:
                    return contest, data, f"{branch}/README.md"
        except Exception:
            continue
    return contest, None, ""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(REPOS_JSON, encoding="utf-8") as f:
        repos = json.load(f)
    judging = [r for r in repos if r["name"].endswith("-judging")]
    print(f"Fetching {len(judging)} sherlock judging repos\n", flush=True)

    done, missing, skipped = 0, 0, 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {}
        for r in judging:
            contest = r["name"].removesuffix("-judging")
            out = os.path.join(OUT_DIR, f"{contest}.md")
            if os.path.exists(out):
                skipped += 1
                continue
            futures[pool.submit(fetch, r["full_name"], r["default_branch"])] = contest
        for fut in as_completed(futures):
            contest, content, src = fut.result()
            if content:
                with open(os.path.join(OUT_DIR, f"{contest}.md"), "wb") as f:
                    f.write(content)
                done += 1
                if done % 25 == 0:
                    print(f"  fetched {done} ...", flush=True)
            else:
                missing += 1
    print(f"\nfetched={done}, missing={missing}, skipped={skipped}")


if __name__ == "__main__":
    main()
