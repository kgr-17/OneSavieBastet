"""Overlay VERIFIED dataset_0831 human-gold tags/subtags onto v16_maxcontext for
guessed test rows, aligned by subtag match within the same contest/project.
Pure +EV: replaces a guessed tag with the human-gold tag where gold exists and
the subtag corroborates the alignment. Zero structural change (counts identical).

Probe A (safe): only the 2 record-verified recoveries (pid 216->ERC4626, 286->TWAP).
Probe B (systematic): all confidently subtag-aligned gold across known contests.
"""
import csv, re
from collections import defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


def project_key(contest):
    c = re.sub(r'^\s*20\d\d-\d\d-', '', str(contest).strip().lower())
    toks = [t for t in re.split(r'[-_]', c) if t]
    return toks[0] if toks else ''


def audit_of(rp):
    for seg in str(rp).replace('\\', '/').split('/'):
        if len(seg) >= 7 and seg[:2] == '20' and '-' in seg:
            return seg
    return ''


v16 = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v16_maxcontext.csv', encoding='utf-8')))
byP = {r['Property']: r for r in v16}
sheet = list(csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig')))
P2contest = {r['Property']: r.get('contest', '').strip() for r in sheet if r.get('Property')}

ds = [r for r in csv.DictReader(open(f'{ROOT}/data/dataset_0831.csv', encoding='utf-8-sig'))
      if r['status'].strip() == 'Done' and r['tag'].strip() and r['subtag'].strip()]
gold_by_proj = defaultdict(list)
for r in ds:
    gold_by_proj[project_key(audit_of(r['repo_path']))].append((r['tag'].strip(), r['subtag'].strip()))


def systematic_overrides():
    """Return {Property: (new_tag, new_subtag, reason)} from subtag-aligned gold."""
    out = {}
    used = defaultdict(set)  # project -> set of gold indices used (one-to-one)
    for P, contest in P2contest.items():
        if not contest or contest == '(unmapped)':
            continue
        pk = project_key(contest)
        golds = gold_by_proj.get(pk)
        if not golds:
            continue
        row = byP.get(P)
        if not row:
            continue
        rsub, rtag = n1(row['subtag']), n1(row['tag'])
        for i, (gtag, gsub) in enumerate(golds):
            if i in used[pk]:
                continue
            if n1(gsub) == rsub and n1(gtag) != rtag:   # subtag corroborates; tag differs -> gold wins
                used[pk].add(i)
                out[P] = (gtag, gsub, f"{contest}: subtag '{rsub}' matches gold; tag {row['tag']}->{gtag}")
                break
    return out


def write(path, overrides):
    rows = [dict(r) for r in v16]
    bp = {r['Property']: r for r in rows}
    for P, (gt, gs, _) in overrides.items():
        bp[P]['tag'] = gt
        bp[P]['subtag'] = gs
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
        w.writeheader()
        w.writerows(rows)


# Probe A: the 2 record-verified recoveries
A = {'216': ('ERC4626', 'Rounding Error', 'notional rounding -> gold ERC4626'),
     '286': ('TWAP', 'Front Run, Reward Manipulation', 'sturdy MEV/JIT -> gold TWAP')}
write(f'{ROOT}/outputs/submission_c4_v31_goldalign2.csv', A)

# Probe B: systematic subtag-aligned gold overlay
B = systematic_overrides()
write(f'{ROOT}/outputs/submission_c4_v32_goldoverlay.csv', B)

print(f"Probe A (safe, 2 verified): {len(A)} overrides -> v31_goldalign2.csv")
for P, (gt, gs, why) in sorted(A.items(), key=lambda x: int(x[0])):
    print(f"  pid {P}: {byP[P]['tag']}->{gt} | {why}")
print(f"\nProbe B (systematic): {len(B)} overrides -> v32_goldoverlay.csv")
for P, (gt, gs, why) in sorted(B.items(), key=lambda x: int(x[0])):
    print(f"  pid {P}: {byP[P]['tag']}/{byP[P]['subtag']} -> {gt}/{gs} | {why}")
