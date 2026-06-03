"""v3 identifier — fixes:
  - blacklist 'dev-test-repo' false-positive
  - support legacy C4 URL: code423n4.com/{date}-{slug}-contest
  - support code4rena.com/contests/{date}-{slug}-contest
  - flag Sherlock audits (sherlock.xyz / 'Sherlock Discord') separately
  - drop generic stop-tokens (test, src, lib, out, script, contracts) from subfolder voting
"""
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict

DATA_DIR = "data"
ARTIFACTS = "artifacts"
C4_REPOS_JSON = "artifacts/c4_repos.json"

# URL patterns covering legacy/new C4 forms.
URL_PATTERNS = [
    re.compile(r"github\.com/code-423n4/([0-9]{4}-[0-9]{2}-[A-Za-z0-9_.-]+?)(?:[/#?\s\"')\]]|$)"),
    re.compile(r"code4rena\.com/audits/([0-9]{4}-[0-9]{2}-[A-Za-z0-9_-]+)"),
    re.compile(r"code4rena\.com/contests/([0-9]{4}-[0-9]{2}-[A-Za-z0-9_-]+)"),
    re.compile(r"code423n4\.com/([0-9]{4}-[0-9]{2}-[A-Za-z0-9_-]+)"),
]

SHERLOCK_RE = re.compile(r"sherlock\.xyz|Sherlock Discord", re.IGNORECASE)

BLACKLIST_SLUGS = {
    "2022-01-dev-test-repo",
}
STOP_SUBDIRS = {
    "test", "tests", "src", "lib", "libs", "out", "script", "scripts",
    "contracts", "audits", "audit", ".github", ".git", "node_modules",
    "build", "dist", "deploy", "deployments", "cache", "config", "configs",
    "spec", "specs", "doc", "docs", "documentation", "release", "releases",
    "package", "packages", "vendor", "third-party", "thirdparty",
}


def normalize_slug(s):
    s = s.rstrip("./")
    s = re.sub(r"-(findings|mitigation|mitigation-contest|mitigation-review|invitational|contest)$", "", s)
    return s


def load_c4_contests():
    with open(C4_REPOS_JSON, encoding="utf-8") as f:
        repos = json.load(f)
    slugs = set()
    tail_to_slugs = defaultdict(list)
    for r in repos:
        name = r["name"]
        if name.endswith("-findings") or name.endswith("-mitigation"):
            continue
        if not re.match(r"^\d{4}-\d{2}-", name):
            continue
        if name in BLACKLIST_SLUGS:
            continue
        slugs.add(name)
        tail = name[8:]
        tail_to_slugs[tail.lower()].append(name)
        for tok in tail.lower().split("-"):
            if len(tok) >= 3 and tok not in STOP_SUBDIRS:
                tail_to_slugs[tok].append(name)
    return slugs, dict(tail_to_slugs)


def find_url_slug(text, c4_slugs):
    for pat in URL_PATTERNS:
        for raw in pat.findall(text):
            slug = normalize_slug(raw)
            if slug in c4_slugs:
                return slug, "exact"
            # Try fuzzy: tail prefix
            for canonical in c4_slugs:
                if canonical.startswith(slug + "-") or slug.startswith(canonical + "-"):
                    return canonical, "prefix"
                if canonical[8:] == slug[8:] if (len(slug) >= 8 and slug[4] == "-") else False:
                    return canonical, "tail"
            # No match in C4 — return raw so caller knows the slug exists but no C4 repo.
            return slug, "raw_only"
    return None, None


def folder_signals(z, split, folder):
    prefix = f"{split}/{folder}/"
    names = [n for n in z.namelist() if n.startswith(prefix) and not n.endswith("/")]
    subdirs = set()
    for n in names:
        rel = n[len(prefix):]
        parts = rel.split("/")
        if len(parts) > 1 and parts[0]:
            subdirs.add(parts[0].lower())
    subdirs = {s for s in subdirs if s not in STOP_SUBDIRS and not s.startswith(".")}

    keyword = ("readme", "scope.txt", "package.json", "license", "audit", "4naly3er")
    text_candidates = [n for n in names if any(k in n.lower() for k in keyword)]
    text_candidates.sort(key=lambda n: n.count("/"))
    texts = []
    for n in text_candidates[:8]:
        try:
            with z.open(n) as f:
                texts.append(f.read().decode("utf-8", errors="replace"))
        except Exception:
            continue
    return subdirs, " ".join(texts)


def identify(z, split, folder, c4_slugs, tail_to_slugs):
    subdirs, all_text = folder_signals(z, split, folder)

    # Signal 1: URL slug.
    slug, kind = find_url_slug(all_text, c4_slugs)
    if slug and kind in ("exact", "prefix", "tail"):
        return {"contest": slug, "method": f"url_{kind}", "confidence": "high"}

    is_sherlock = bool(SHERLOCK_RE.search(all_text))

    # Signal 2: subfolder tail-tokens (excluding stop-tokens).
    candidates = Counter()
    for sub in subdirs:
        sub_norm = re.sub(r"-(contracts|contracts-internal|core|periphery|modular|v[0-9]+|protocol)$", "", sub)
        for key in (sub, sub_norm):
            if key in tail_to_slugs:
                for s in tail_to_slugs[key]:
                    candidates[s] += 1

    if candidates:
        top = candidates.most_common(2)
        if len(top) == 1 or top[0][1] > top[1][1]:
            best, count = top[0]
            return {
                "contest": best,
                "method": "subfolder",
                "confidence": "high" if count >= 2 else "medium",
                "evidence_subdirs": list(subdirs),
                "is_sherlock": is_sherlock,
            }

    # Signal 3: text substring scan for any C4 slug.
    text_lower = all_text.lower()
    text_hits = Counter()
    for s in c4_slugs:
        if s.lower() in text_lower:
            text_hits[s] += 1
    if text_hits:
        best = text_hits.most_common(1)[0][0]
        return {"contest": best, "method": "text_substr", "confidence": "medium", "is_sherlock": is_sherlock}

    # If we found a slug from URL but it didn't match C4 list, surface it (possibly Sherlock).
    if slug and kind == "raw_only":
        return {"contest": slug, "method": "url_raw", "confidence": "medium", "is_sherlock": is_sherlock}

    if is_sherlock:
        # Try to extract any clue from contest title (e.g. "# Rubicon Finance contest details").
        m = re.search(r"^#\s+(.+?)\s+contest", all_text, re.MULTILINE | re.IGNORECASE)
        title = m.group(1).strip() if m else None
        return {"contest": None, "method": "sherlock_unknown", "confidence": "low", "title_hint": title, "is_sherlock": True}

    return None


def scan_split(zip_path, split, c4_slugs, tail_to_slugs):
    out = {}
    with zipfile.ZipFile(zip_path) as z:
        all_names = z.namelist()
        folders = set()
        for n in all_names:
            if n.startswith("__MACOSX") or not n.startswith(f"{split}/"):
                continue
            parts = n.split("/")
            if len(parts) >= 2 and parts[1]:
                folders.add(parts[1])
        for i, folder in enumerate(sorted(folders), 1):
            res = identify(z, split, folder, c4_slugs, tail_to_slugs)
            if res:
                out[folder] = res
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    c4_slugs, tail_to_slugs = load_c4_contests()
    print(f"Loaded {len(c4_slugs)} dated C4 code-repo slugs (after blacklist)")

    test_map = scan_split(os.path.join(DATA_DIR, "test.zip"), "test", c4_slugs, tail_to_slugs)
    train_map = scan_split(os.path.join(DATA_DIR, "train.zip"), "train", c4_slugs, tail_to_slugs)

    with open(os.path.join(ARTIFACTS, "test_hash_to_contest_v3.json"), "w", encoding="utf-8") as f:
        json.dump(test_map, f, indent=2)
    with open(os.path.join(ARTIFACTS, "train_hash_to_contest_v3.json"), "w", encoding="utf-8") as f:
        json.dump(train_map, f, indent=2)

    confirmed_test = {h: v for h, v in test_map.items() if v.get("contest") and v["confidence"] in ("high", "medium")}
    confirmed_train = {h: v for h, v in train_map.items() if v.get("contest") and v["confidence"] in ("high", "medium")}

    print(f"\ntest:  {len(confirmed_test)}/53 confirmed ({Counter(v['method'] for v in confirmed_test.values())})")
    print(f"train: {len(confirmed_train)}/54 confirmed ({Counter(v['method'] for v in confirmed_train.values())})")

    sherlock_test = [h for h, v in test_map.items() if v.get("is_sherlock")]
    print(f"\nSherlock-flagged test folders: {len(sherlock_test)}")

    print("\n--- All test mappings ---")
    for h, info in sorted(test_map.items()):
        sl = " [Sherlock]" if info.get("is_sherlock") else ""
        contest = info.get("contest") or "?"
        print(f"  {h} -> {contest:50s}  [{info['method']:20s} {info['confidence']}]{sl}")

    import csv
    with open("test.csv", encoding="utf-8") as f:
        r = csv.reader(f); next(r)
        all_test = [row[0] for row in r if row]
    missing = [h for h in all_test if h not in test_map or not test_map[h].get("contest")]
    print(f"\n--- Still unidentified ({len(missing)}) ---")
    for h in missing:
        info = test_map.get(h, {})
        title = info.get("title_hint", "?")
        print(f"  {h}  title_hint={title}")


if __name__ == "__main__":
    main()
