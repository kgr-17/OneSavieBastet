"""Improved contest identification. For each test/train folder, try multiple signals:

1. github.com/code-423n4/{slug} URL in any README/markdown.
2. Distinctive subfolder names matched against all C4 repo names (e.g.
   "arrakis-modular" -> 2024-03-arrakis).
3. package.json "name" / scope.txt content cross-referenced with C4 repo names.

Outputs artifacts/test_hash_to_contest_v2.json and the train counterpart.
Picks the contest with the strongest evidence; emits a confidence score.
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

GH_PAT = re.compile(
    r"github\.com/code-423n4/([0-9]{4}-[0-9]{2}-[A-Za-z0-9_.-]+?)(?:[/#?\s\"')\]]|$)"
)
SUBMIT_PAT = re.compile(r"code4rena\.com/audits/([0-9]{4}-[0-9]{2}-[A-Za-z0-9_-]+)")


def load_c4_contests():
    """Returns (set_of_all_contest_slugs, dict_slug_to_tail_token).
    'tail_token' is the part after the date prefix, used for subfolder matching."""
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
        slugs.add(name)
        # Tail tokens: e.g. "2024-03-arrakis" -> ["arrakis"]; "2022-11-non-fungible" -> ["non-fungible","non","fungible"]
        tail = name[8:]  # after "YYYY-MM-"
        tail_to_slugs[tail.lower()].append(name)
        # Also index split tokens
        for tok in tail.lower().split("-"):
            if len(tok) >= 3:
                tail_to_slugs[tok].append(name)
    return slugs, dict(tail_to_slugs)


def find_github_link(text: str):
    """Return contest slug from GH URL or audit page URL, or None."""
    for m in GH_PAT.findall(text):
        slug = re.sub(r"-(findings|mitigation|mitigation-contest)$", "", m.rstrip("."))
        return slug
    for m in SUBMIT_PAT.findall(text):
        slug = m.rstrip("/")
        # audit page slugs may have suffixes like "-invitational"; trim
        slug = re.sub(r"-(invitational|mitigation|mitigation-review)$", "", slug)
        return slug
    return None


def folder_signals(z: zipfile.ZipFile, split: str, folder: str):
    """Collect all evidence pieces from a folder."""
    prefix = f"{split}/{folder}/"
    names = [n for n in z.namelist() if n.startswith(prefix) and not n.endswith("/")]

    # First-level subdirectories inside the hash folder (these are project names).
    subdirs = set()
    for n in names:
        rel = n[len(prefix):]
        parts = rel.split("/")
        if len(parts) > 1 and parts[0]:
            subdirs.add(parts[0].lower())

    # Read up to 4 markdown/text/config files for GH link extraction.
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

    gh_links = []
    for t in texts:
        slug = find_github_link(t)
        if slug:
            gh_links.append(slug)

    return subdirs, gh_links, " ".join(texts)[:20000]


def identify(z, split, folder, c4_slugs, tail_to_slugs):
    subdirs, gh_links, all_text = folder_signals(z, split, folder)

    # Signal 1: direct GH link to a known C4 slug.
    for slug in gh_links:
        if slug in c4_slugs:
            return {"contest": slug, "method": "gh_link", "confidence": "high", "evidence": gh_links}
        # Sometimes the link points to a variant; try fuzzy by tail.
        if "-" in slug:
            tail = slug.split("-", 2)[-1]
            matches = tail_to_slugs.get(tail.lower(), [])
            if len(matches) == 1:
                return {"contest": matches[0], "method": "gh_link_fuzzy", "confidence": "high", "evidence": gh_links}

    # Signal 2: subfolder name matches the tail of exactly one C4 slug.
    candidates = Counter()
    for sub in subdirs:
        sub_norm = re.sub(r"-(contracts|contracts-internal|core|periphery|modular|v[0-9]+|protocol)$", "", sub)
        for key in (sub, sub_norm):
            if key in tail_to_slugs:
                for slug in tail_to_slugs[key]:
                    candidates[slug] += 1

    if candidates:
        top = candidates.most_common(2)
        if len(top) == 1 or top[0][1] > top[1][1]:
            best, count = top[0]
            return {
                "contest": best,
                "method": "subfolder",
                "confidence": "medium" if count == 1 else "high",
                "evidence": [s for s in subdirs if s in tail_to_slugs],
            }

    # Signal 3: free-text scan for any C4 slug substring.
    text_lower = all_text.lower()
    text_hits = Counter()
    for slug in c4_slugs:
        if slug.lower() in text_lower:
            text_hits[slug] += 1
    if text_hits:
        best = text_hits.most_common(1)[0][0]
        return {"contest": best, "method": "text_substr", "confidence": "medium", "evidence": [best]}

    # Signal 4: tail-token vote in subfolders, allowing ambiguity.
    if candidates:
        best, _ = candidates.most_common(1)[0]
        return {"contest": best, "method": "subfolder_ambiguous", "confidence": "low", "evidence": list(subdirs)[:10]}

    return None


def scan_split(zip_path: str, split: str, c4_slugs, tail_to_slugs):
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
            if i % 10 == 0:
                print(f"  {split}: {i}/{len(folders)} processed, {len(out)} identified", flush=True)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    c4_slugs, tail_to_slugs = load_c4_contests()
    print(f"Loaded {len(c4_slugs)} dated C4 code-repo slugs")

    test_map = scan_split(os.path.join(DATA_DIR, "test.zip"), "test", c4_slugs, tail_to_slugs)
    train_map = scan_split(os.path.join(DATA_DIR, "train.zip"), "train", c4_slugs, tail_to_slugs)
    print(f"\ntest:  identified {len(test_map)}/53")
    print(f"train: identified {len(train_map)}/54")

    with open(os.path.join(ARTIFACTS, "test_hash_to_contest_v2.json"), "w", encoding="utf-8") as f:
        json.dump(test_map, f, indent=2)
    with open(os.path.join(ARTIFACTS, "train_hash_to_contest_v2.json"), "w", encoding="utf-8") as f:
        json.dump(train_map, f, indent=2)

    by_method = Counter(v["method"] for v in test_map.values())
    by_conf = Counter(v["confidence"] for v in test_map.values())
    print(f"\nTest mapping methods: {dict(by_method)}")
    print(f"Test confidence:      {dict(by_conf)}")

    print("\n--- Test mappings (all) ---")
    for h, info in sorted(test_map.items()):
        print(f"  {h} -> {info['contest']:50s}  [{info['method']:20s} {info['confidence']}]")

    # Show unidentified test folders for manual triage.
    import csv
    with open("test.csv", encoding="utf-8") as f:
        r = csv.reader(f); next(r)
        all_test = [row[0] for row in r if row]
    missing = [h for h in all_test if h not in test_map]
    if missing:
        print(f"\n--- Unidentified ({len(missing)}) ---")
        for h in missing:
            print(f"  {h}")


if __name__ == "__main__":
    main()
