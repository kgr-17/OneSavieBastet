"""For each folder inside train.zip and test.zip, identify its C4 contest by parsing
README.md (which always contains a github.com/code-423n4/{contest} link).

Outputs:
- artifacts/test_hash_to_contest.json
- artifacts/train_hash_to_contest_verified.json

Also cross-validates against the TF-IDF-based train mapping in
artifacts/hash_to_contest.json.
"""
import json
import os
import re
import sys
import zipfile
from collections import Counter

DATA_DIR = "data"
ARTIFACTS = "artifacts"

# Match github.com/code-423n4/{contest} URLs in README text. Strip trailing
# punctuation/path that GitHub URLs in markdown can pick up.
GH_PAT = re.compile(
    r"github\.com/code-423n4/([0-9]{4}-[0-9]{2}-[A-Za-z0-9_.-]+?)(?:[/#?\s\"')\]]|$)"
)

# Backup: extract contest title from README "# X audit details" heading.
TITLE_PAT = re.compile(r"^#\s+(.+?)\s+(audit|contest|details)", re.MULTILINE | re.IGNORECASE)


def identify_contest_from_text(text: str):
    """Return (contest_slug, evidence_count, title_hint). Picks the slug that
    appears most often in github.com/code-423n4/ links."""
    matches = GH_PAT.findall(text)
    # Strip "-findings" / "-mitigation" / common variants so the canonical contest slug wins.
    norm = []
    for m in matches:
        m = m.rstrip(".")
        m = re.sub(r"-(findings|mitigation|mitigation-contest)$", "", m)
        norm.append(m)
    if not norm:
        title = TITLE_PAT.search(text)
        return None, 0, title.group(1) if title else None
    top = Counter(norm).most_common(1)[0]
    title = TITLE_PAT.search(text)
    return top[0], top[1], title.group(1) if title else None


def scan_zip(zip_path: str, split_name: str):
    """Walk the zip; for each top-level folder under {split_name}/, read its README.md."""
    results = {}
    with zipfile.ZipFile(zip_path) as z:
        all_names = z.namelist()
        # Map hash folder -> list of candidate readme paths inside it
        readme_paths = {}
        for n in all_names:
            if n.startswith("__MACOSX") or not n.startswith(f"{split_name}/"):
                continue
            parts = n.split("/")
            if len(parts) < 3:
                continue
            folder = parts[1]
            tail = "/".join(parts[2:])
            if tail.lower() == "readme.md":
                readme_paths.setdefault(folder, []).append(n)

        for folder, paths in readme_paths.items():
            # Prefer the shortest path (root README) over nested ones.
            paths.sort(key=lambda p: (p.count("/"), len(p)))
            for p in paths:
                with z.open(p) as f:
                    try:
                        text = f.read().decode("utf-8", errors="replace")
                    except Exception:
                        continue
                slug, count, title = identify_contest_from_text(text)
                if slug:
                    results[folder] = {
                        "contest": slug,
                        "evidence_count": count,
                        "readme_path": p,
                        "title_hint": title,
                    }
                    break

    return results


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(ARTIFACTS, exist_ok=True)

    test_map = scan_zip(os.path.join(DATA_DIR, "test.zip"), "test")
    train_map = scan_zip(os.path.join(DATA_DIR, "train.zip"), "train")
    print(f"test:  identified {len(test_map)}/53 folders")
    print(f"train: identified {len(train_map)}/54 folders")

    with open(os.path.join(ARTIFACTS, "test_hash_to_contest.json"), "w", encoding="utf-8") as f:
        json.dump(test_map, f, indent=2)
    with open(os.path.join(ARTIFACTS, "train_hash_to_contest_verified.json"), "w", encoding="utf-8") as f:
        json.dump(train_map, f, indent=2)

    print("\n--- Test mappings (first 15) ---")
    for h, info in list(test_map.items())[:15]:
        print(f"  {h} -> {info['contest']:50s}  (evidence={info['evidence_count']})")

    # Cross-validate train mappings against TF-IDF-based file.
    tfidf_path = os.path.join(ARTIFACTS, "hash_to_contest.json")
    if os.path.exists(tfidf_path):
        with open(tfidf_path, encoding="utf-8") as f:
            tfidf = json.load(f)
        agree, disagree, missing = 0, [], 0
        for h, info in train_map.items():
            if h not in tfidf:
                missing += 1
                continue
            tf_pick = tfidf[h]["contest"]
            readme_pick = info["contest"]
            if tf_pick == readme_pick:
                agree += 1
            else:
                disagree.append((h, tf_pick, readme_pick, tfidf[h]["vote_share"]))
        print(f"\n--- Train cross-check (README vs TF-IDF) ---")
        print(f"  agree:    {agree}")
        print(f"  disagree: {len(disagree)}")
        print(f"  missing:  {missing}")
        if disagree:
            print("\n  Disagreements (README is ground truth):")
            for h, tf, rd, vs in disagree[:20]:
                print(f"    {h}  README={rd:35s}  TFIDF={tf:35s}  (vote_share={vs:.2f})")


if __name__ == "__main__":
    main()
