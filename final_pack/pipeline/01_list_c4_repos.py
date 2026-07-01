"""List all repos in the code-423n4 GitHub org. Outputs JSON to artifacts/c4_repos.json."""
import json
import os
import sys
import time
import urllib.request
import urllib.error

OUT = "artifacts/c4_repos.json"
API = "https://api.github.com/orgs/code-423n4/repos?per_page=100&page={page}"
TOKEN = os.environ.get("GITHUB_TOKEN")


def fetch_page(page: int):
    req = urllib.request.Request(API.format(page=page))
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")), r.headers


def main():
    os.makedirs("artifacts", exist_ok=True)
    all_repos = []
    for page in range(1, 20):
        try:
            data, headers = fetch_page(page)
        except urllib.error.HTTPError as e:
            print(f"page {page}: HTTP {e.code} -- {e.read().decode('utf-8', 'replace')[:200]}", flush=True)
            if e.code == 403:
                print("Rate limited. Set GITHUB_TOKEN env var.", flush=True)
            break
        if not data:
            break
        all_repos.extend(data)
        remaining = headers.get("X-RateLimit-Remaining", "?")
        print(f"page {page}: {len(data)} repos (rate-remaining={remaining})", flush=True)
        if len(data) < 100:
            break
        time.sleep(0.5)

    slim = [
        {
            "name": r["name"],
            "full_name": r["full_name"],
            "default_branch": r.get("default_branch", "main"),
            "created_at": r.get("created_at"),
            "size": r.get("size"),
            "description": (r.get("description") or "")[:200],
        }
        for r in all_repos
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2)
    print(f"\nSaved {len(slim)} repos to {OUT}")
    findings = [r for r in slim if r["name"].endswith("-findings")]
    print(f"  -findings repos: {len(findings)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
