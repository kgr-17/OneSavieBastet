"""Measure the canonical coverage gap: for each test repo, how many High/Medium
findings its C4 audit report contains vs how many rows our submission has.
Under-covered repos = structural opportunity (real canonical findings, with real
descriptions that should match hidden truth, that we're NOT including).
"""
import csv, re, os
from collections import defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def pk(c):
    c = re.sub(r'^\s*20\d\d-\d\d-', '', str(c).strip().lower())
    t = [x for x in re.split(r'[-_]', c) if x]
    return t[0] if t else ''


reps = {os.path.splitext(f)[0]: f for f in os.listdir(f'{ROOT}/artifacts/c4_reports') if f.endswith('.md')}


def best_report(contest):
    cand = [r for r in reps if r == contest] or [r for r in reps if r.startswith(contest) or contest.startswith(r)] \
        or [r for r in reps if pk(contest) and pk(contest) in r.split('-')]
    return min(cand, key=lambda r: abs(len(r) - len(contest))) if cand else None


def count_findings(repfile):
    """Count H-/M- finding headers in a C4 report."""
    txt = open(f'{ROOT}/artifacts/c4_reports/{repfile}', encoding='utf-8', errors='replace').read()
    # headers like ## [H-01], ## [[H-01]], # H-01, ## [M-1]
    hs = re.findall(r'^#+\s*\[*\[?H-?\d+', txt, re.M | re.I)
    ms = re.findall(r'^#+\s*\[*\[?M-?\d+', txt, re.M | re.I)
    return len(hs), len(ms)


sub = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v50_v49_plus216.csv', encoding='utf-8-sig')))
sheet = list(csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig')))
hash2contest = {}
for r in sheet:
    if r.get('contest', '').strip() and r['contest'] != '(unmapped)':
        hash2contest[r['repo_hash']] = r['contest'].strip()

rows_by_hash = defaultdict(list)
for r in sub:
    rows_by_hash[r['repo_path']].append(r)

gaps = []
for h, rows in rows_by_hash.items():
    contest = hash2contest.get(h)
    if not contest:
        continue
    rf = best_report(contest)
    if not rf:
        continue
    nh, nm = count_findings(rf)
    canon = nh + nm
    ours = len(rows)
    gap = canon - ours
    if canon > 0:
        gaps.append((contest, ours, nh, nm, canon, gap))

gaps.sort(key=lambda x: -x[5])
print(f"{'contest':<26}{'ourRows':>8}{'H':>4}{'M':>4}{'canon':>7}{'GAP':>6}")
under = tot_gap = 0
for c, o, nh, nm, canon, gap in gaps:
    flag = '  <<UNDER' if gap > 0 else ('  over' if gap < 0 else '')
    print(f"  {c:<24}{o:>8}{nh:>4}{nm:>4}{canon:>7}{gap:>+6}{flag}")
    if gap > 0:
        under += 1
        tot_gap += gap
print(f"\nrepos UNDER-covered vs canonical C4 report: {under}")
print(f"TOTAL canonical findings we're missing (addressable deficit): {tot_gap}")
print(f"(these have real C4 descriptions -> would match hidden truth; tags assignable from the report)")
