"""Local evidence-validator (the train-holdout is unreliable, so we validate
against the sources that DID predict live):
  PRIMARY  = dataset_0831 human GOLD (independent of our models), subtag-aligned.
  SECONDARY= report-grounded >=0.8 labels (evidence-backed; v49 proved they work).
Scores candidates with the real competition field_score = (TP-0.5*FP)/|truth| per
row, on the evidence-covered rows. Also breaks down each candidate's changes vs the
current best by whether they AGREE or CONTRADICT independent gold.
"""
import csv, json, re, sys
from collections import defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def norm(s):
    return re.sub(r'\s+', ' ', str(s)).strip().lower()


def labs(s):
    return frozenset(norm(x) for x in str(s).split(',') if x.strip())


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


def field_score(pred_set, truth_set):
    if not truth_set:
        return None
    tp = len(pred_set & truth_set)
    fp = len(pred_set - truth_set)
    return max(0.0, (tp - 0.5 * fp) / len(truth_set))


# --- build the GOLD proxy: per test Property, the subtag-aligned gold (tag,subtag) ---
sheet = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig'))}
ds = [r for r in csv.DictReader(open(f'{ROOT}/data/dataset_0831.csv', encoding='utf-8-sig'))
      if r['status'].strip() == 'Done' and r['tag'].strip() and r['subtag'].strip()]
gold = defaultdict(list)
for r in ds:
    gold[pk(audit_of(r['repo_path']))].append((r['tag'].strip(), r['subtag'].strip()))

cur = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v50_v49_plus216.csv', encoding='utf-8-sig'))}
gold_truth = {}   # Property -> (tag_str, subtag_str) from subtag-aligned gold
for P, srow in sheet.items():
    if P not in cur:
        continue
    golds = gold.get(pk(srow.get('contest', '')))
    if not golds:
        continue
    cs = n1(cur[P]['subtag'])
    for gt, gs in golds:
        if n1(gs) == cs:
            gold_truth[P] = (gt, gs)
            break

# report >=0.8 proxy (from both passes)
rep = {}
for f in ['report_grounded_preds.json', 'report_grounded_preds2.json']:
    for p in json.load(open(f'{ROOT}/finetune/teacher/{f}')):
        try:
            c = float(p.get('confidence', 0))
        except Exception:
            c = 0
        if c >= 0.8:
            rep[str(p['Property'])] = (p['tag'], p['subtag'])

print(f"evidence coverage: GOLD-aligned rows = {len(gold_truth)} | report>=0.8 rows = {len(rep)}")


def score(path):
    rows = {r['Property']: r for r in csv.DictReader(open(path, encoding='utf-8-sig'))}
    gt_tag = gt_sub = rp_tag = 0.0
    for P, (t, s) in gold_truth.items():
        gt_tag += field_score(labs(rows[P]['tag']), labs(t)) or 0
        gt_sub += field_score(labs(rows[P]['subtag']), labs(s)) or 0
    for P, (t, s) in rep.items():
        if P in rows:
            rp_tag += field_score(labs(rows[P]['tag']), labs(t)) or 0
    return gt_tag, gt_sub, rp_tag


def gold_diff(path):
    """changes vs v50 that AGREE vs CONTRADICT independent gold."""
    rows = {r['Property']: r for r in csv.DictReader(open(path, encoding='utf-8-sig'))}
    agree = contra = 0
    for P, (gtag, _) in gold_truth.items():
        if n1(rows[P]['tag']) != n1(cur[P]['tag']):  # candidate changed this gold-covered row
            if n1(rows[P]['tag']) == n1(gtag):
                agree += 1
            elif n1(cur[P]['tag']) == n1(gtag):
                contra += 1
    return agree, contra


cands = sys.argv[1:] or [
    'outputs/submission_c4_v50_v49_plus216.csv',
    'outputs/submission_c4_v51_report_wider.csv',
]
print(f"\n{'candidate':<46}{'GOLDtag':>9}{'GOLDsub':>9}{'REP>=.8':>9}  changes-vs-v50(gold: +agree/-contra)")
print('-' * 100)
for c in cands:
    gt, gs, rp = score(f'{ROOT}/{c}' if not c.startswith('/') else c)
    a, x = gold_diff(f'{ROOT}/{c}' if not c.startswith('/') else c)
    name = c.split('/')[-1]
    print(f"{name:<46}{gt:>9.2f}{gs:>9.2f}{rp:>9.2f}  +{a}/-{x}")
print(f"\nGOLD = independent human truth (higher = better-aligned). v50 = current best (481.21).")
