"""Tighten the gold sheet to the highest-impact, minimal-effort rows:
  keep a guessed row ONLY if (a) the models disagree with the current-best (479.96)
  label -> it's probably wrong, AND (b) it's VERIFIABLE -- the contest has
  dataset_0831 human gold and/or a fetched C4 report -> a human can resolve it fast.
Inlines the gold reference so each pick is a quick lookup, not research.
"""
import csv, json, re, os
from collections import Counter, defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


def pk(c):
    c = re.sub(r'^\s*20\d\d-\d\d-', '', str(c).strip().lower())
    t = [x for x in re.split(r'[-_]', c) if x]
    return t[0] if t else ''


def audit_of(rp):
    for seg in str(rp).replace('\\', '/').split('/'):
        if len(seg) >= 7 and seg[:2] == '20' and '-' in seg:
            return seg
    return ''


base = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/outputs/base_479.96.csv', encoding='utf-8-sig'))}
sheet = list(csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig')))
sc = {str(p['id']): p for p in json.load(open(f'{ROOT}/finetune/teacher/srccode_test_preds.json'))}
preds = json.load(open(f'{ROOT}/finetune/teacher/5pass_preds.json'))
tv, sv = defaultdict(list), defaultdict(list)
for p in preds:
    tv[str(p['id'])].append(p['tag'])
    sv[str(p['id'])].append(p['subtag'])

# dataset_0831 gold by project key
ds = [r for r in csv.DictReader(open(f'{ROOT}/data/dataset_0831.csv', encoding='utf-8-sig'))
      if r['status'].strip() == 'Done' and r['tag'].strip()]
gold = defaultdict(list)
for r in ds:
    gold[pk(audit_of(r['repo_path']))].append((r['tag'].strip(), r['subtag'].strip()))

# fetched C4 reports available?
reports = set(os.path.splitext(f)[0] for f in os.listdir(f'{ROOT}/artifacts/c4_reports')) if os.path.isdir(f'{ROOT}/artifacts/c4_reports') else set()


def maj(xs):
    c = Counter(n1(x) for x in xs)
    t, nn = c.most_common(1)[0]
    return t, round(nn / len(xs), 2) if xs else (None, 0)


rows = []
for r in sheet:
    P = r['Property']
    contest = r.get('contest', '').strip()
    if not contest or contest == '(unmapped)':
        continue
    cur_t, cur_s = n1(base.get(P, {}).get('tag', '')), n1(base.get(P, {}).get('subtag', ''))
    tt, tconf = maj(tv.get(P, []))
    st = n1(sc.get(P, {}).get('tag', ''))
    disagree = (tt and tt != cur_t) or (st and st != cur_t)
    if not disagree:
        continue
    proj = pk(contest)
    gold_opts = sorted(set(f"{t}/{s}" for t, s in gold.get(proj, [])))
    has_report = any(contest.startswith(rep) or rep.startswith(contest) or proj in rep for rep in reports)
    if not gold_opts and not has_report:
        continue  # not verifiable -> skip (keep effort minimal)
    rows.append({
        'Property': P, 'contest': contest, 'severity': r.get('severity', ''),
        'current_tag(479.96)': base.get(P, {}).get('tag', ''),
        'teacher_tag': tt or '', 'teacher_conf': tconf, 'srccode_tag': sc.get(P, {}).get('tag', ''),
        'current_subtag': base.get(P, {}).get('subtag', ''),
        'gold_options(dataset_0831)': ' | '.join(gold_opts) if gold_opts else '(none)',
        'c4_report': 'yes' if has_report else 'no',
        'FINAL_tag': '', 'FINAL_subtag': '',
        'description': ' '.join(str(r.get('description', '')).split())[:350],
    })

# impact rank: gold-available first, then strongest model disagreement
rows.sort(key=lambda x: (x['gold_options(dataset_0831)'] == '(none)', -x['teacher_conf']))
cols = ['Property', 'contest', 'severity', 'current_tag(479.96)', 'teacher_tag', 'teacher_conf', 'srccode_tag',
        'current_subtag', 'gold_options(dataset_0831)', 'c4_report', 'FINAL_tag', 'FINAL_subtag', 'description']
out = f'{ROOT}/labeling_handoff/GOLD_SHEET_TIGHT.csv'
w = csv.DictWriter(open(out, 'w', newline='', encoding='utf-8'), fieldnames=cols)
w.writeheader(); w.writerows(rows)
with_gold = sum(1 for r in rows if r['gold_options(dataset_0831)'] != '(none)')
print(f"WROTE {out}")
print(f"  TIGHT high-impact rows: {len(rows)} (of 289)  | {with_gold} have dataset_0831 gold reference, {len(rows)-with_gold} have C4 report only")
print(f"  -> minimal targeted human effort: ~{len(rows)} picks, each with a verifiable reference inline")
print("\n  top 12 (gold-reference rows first):")
for r in rows[:12]:
    print(f"  pid {r['Property']:>3} [{r['contest']}] cur={r['current_tag(479.96)']!r} teacher={r['teacher_tag']!r}({r['teacher_conf']}) src={r['srccode_tag']!r} | gold: {r['gold_options(dataset_0831)'][:50]}")
