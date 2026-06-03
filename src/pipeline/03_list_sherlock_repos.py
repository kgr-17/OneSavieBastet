"""List all sherlock-audit org repos. Counterpart to c4_01 for the Sherlock platform."""
import json
import os
import sys
import time
import urllib.request
import urllib.error

OUT = "artifacts/sherlock_repos.json"
API = "https://api.github.com/orgs/sherlock-audit/repos?per_page=100&page={page}"
TOKEN = os.environ.get("GITHUB_TOKEN")


def fetch_page(page):
    req = urllib.request.Request(API.format(page=page))
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")), r.headers


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs("artifacts", exist_ok=True)
    all_repos = []
    for page in range(1, 30):
        try:
            data, headers = fetch_page(page)
        except urllib.error.HTTPError as e:
            print(f"page {page}: HTTP {e.code}", flush=True)
            break
        if not data:
            break
        all_repos.extend(data)
        remaining = headers.get("X-RateLimit-Remaining", "?")
        print(f"page {page}: {len(data)} repos (rate-remaining={remaining})", flush=True)
        if len(data) < 100:
            break
        time.sleep(0.4)

    slim = [
        {"name": r["name"], "full_name": r["full_name"], "default_branch": r.get("default_branch", "main")}
        for r in all_repos
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2)
    print(f"\nSaved {len(slim)} sherlock repos to {OUT}")
    judging = [r for r in slim if r["name"].endswith("-judging")]
    print(f"  -judging repos: {len(judging)}")


if __name__ == "__main__":
    main()
