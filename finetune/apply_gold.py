"""Apply the 3 verified dataset_0831 human-gold tag corrections to ANY base
submission (keyed by Property). Usage:
    python finetune/apply_gold.py <base.csv> <out.csv>
Gold (subtag-corroborated against dataset_0831 Done rows):
  pid 216 (notional, subtag Rounding Error): tag -> ERC4626
  pid 286 (sturdy, subtag Front Run):        tag -> TWAP, subtag -> 'Front Run, Reward Manipulation'
  pid 309 (sturdy, subtag Hardcoded Param):  tag -> Slippage
Only changes tag/subtag; per-repo counts unchanged -> structurally safe, pure-label.
"""
import csv, sys

GOLD = {
    '216': {'tag': 'ERC4626'},
    '286': {'tag': 'TWAP', 'subtag': 'Front Run, Reward Manipulation'},
    '309': {'tag': 'Slippage'},
}

base, out = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(base, encoding='utf-8-sig')))
changed = []
for r in rows:
    g = GOLD.get(r['Property'])
    if not g:
        continue
    for k, v in g.items():
        if r[k].strip().lower() != v.strip().lower():
            changed.append(f"pid {r['Property']}: {k} {r[k]!r}->{v!r}")
            r[k] = v
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
    w.writeheader()
    w.writerows(rows)
print(f"base={base} rows={len(rows)} -> {out}")
for c in changed:
    print(" ", c)
print(f"{len(changed)} field changes applied")
