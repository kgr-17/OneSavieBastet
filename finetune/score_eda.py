"""Serious EDA over the score-tagged submission ladder (145 -> 479).
All files share Property 1..400, so we diff row-by-row and attribute each score
jump to the fields that changed. Answers: what changed, and which change bought
the points, at each step of the climb.
"""
import csv, re, os, json, statistics
from collections import Counter

ROOT = '/Users/yixuliu/OneSavieBastet'

# file -> public score (data_history has it in the name; outputs known from record/today)
LADDER = [
    ('data_history/submission (19)_145.86.csv', 145.86, 'early statistical/prior'),
    ('data_history/submission_c4_v1_218.66.csv', 218.66, 'first C4-lookup'),
    ('data_history/submission_c4_v5_312.09.csv', 312.09, 'dataset_0831 direct lookup'),
    ('data_history/submission_409.98.csv', 409.98, '?'),
    ('data_history/submission_437.32.csv', 437.32, '?'),
    ('data_history/submission_439.32.csv', 439.32, '?'),
    ('data_history/submission_442.38.csv', 442.38, 'teammate 442 baseline'),
    ('data_history/0d40f2c3_447.63.csv', 447.63, 'teammate filled-desc'),
    ('outputs/submission_c4_v13_retag.csv', 464.75, 'LLM retag'),
    ('outputs/submission_c4_v14_fulltag.csv', 468.56, 'fulltag'),
    ('outputs/submission_c4_v15_canonical.csv', 471.18, 'canonical retag'),
    ('outputs/submission_c4_v16_maxcontext.csv', 474.21, 'maxcontext'),
    ('data_history/submission.candidate_474_aggressive_cleanup_pass2_474.93.csv', 474.93, 'aggressive cleanup'),
    ('data_history/submission_c4_v16_ee25fix_475.07.csv', 475.07, 'ee25 optimism fix'),
    ('outputs/submission_c4_v34_teacher_all.csv', 479.28, 'Opus teacher relabel (today)'),
]


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


def load(f):
    return {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/{f}', encoding='utf-8-sig'))}


def is_empty(r):
    return not r.get('tag', '').strip() and (not r.get('description', '').strip() or r.get('description', '').strip().lower() == 'empty')


def stats(d):
    rows = list(d.values())
    nonpad = [r for r in rows if not is_empty(r)]
    repos = Counter(r['repo_path'] for r in nonpad)
    descs = [r.get('description', '') for r in nonpad]
    dlens = [len(x) for x in descs]
    tags = [n1(r.get('tag', '')) for r in nonpad if r.get('tag', '').strip()]
    subs = [n1(r.get('subtag', '')) for r in nonpad if r.get('subtag', '').strip()]
    sev = Counter(r.get('severity', '').strip() for r in nonpad)
    return {
        'nonpad_rows': len(nonpad),
        'repos_covered': len(repos),
        'median_desc_len': int(statistics.median(dlens)) if dlens else 0,
        'rich_desc_pct': round(100 * sum(1 for x in dlens if x > 200) / max(1, len(dlens)), 1),
        'distinct_tags': len(set(tags)),
        'distinct_subtags': len(set(subs)),
        'empty_tag_pct': round(100 * sum(1 for r in nonpad if not r.get('tag', '').strip()) / max(1, len(nonpad)), 1),
        'high_sev_pct': round(100 * sev.get('High', 0) / max(1, len(nonpad)), 1),
    }


def diff(a, b):
    """changes from a to b, keyed by Property."""
    keys = set(a) & set(b)
    out = {'repo': 0, 'severity': 0, 'tag': 0, 'subtag': 0, 'desc': 0, 'desc_lenup': 0}
    for k in keys:
        ra, rb = a[k], b[k]
        if ra['repo_path'] != rb['repo_path']:
            out['repo'] += 1
        if ra.get('severity', '').strip().lower() != rb.get('severity', '').strip().lower():
            out['severity'] += 1
        if n1(ra.get('tag', '')) != n1(rb.get('tag', '')):
            out['tag'] += 1
        if n1(ra.get('subtag', '')) != n1(rb.get('subtag', '')):
            out['subtag'] += 1
        da, db = ra.get('description', '').strip(), rb.get('description', '').strip()
        if da != db:
            out['desc'] += 1
            if len(db) > len(da) + 20:
                out['desc_lenup'] += 1
    return out


loaded = [(f, sc, note, load(f)) for f, sc, note in LADDER]

print("=" * 100)
print("PER-FILE STATS (score ladder)")
print(f"{'score':>8} {'nonpad':>7} {'repos':>6} {'medDesc':>8} {'rich%':>6} {'#tags':>6} {'#subs':>6} {'emptyTag%':>9} {'High%':>6}  note")
for f, sc, note, d in loaded:
    s = stats(d)
    print(f"{sc:>8} {s['nonpad_rows']:>7} {s['repos_covered']:>6} {s['median_desc_len']:>8} {s['rich_desc_pct']:>6} "
          f"{s['distinct_tags']:>6} {s['distinct_subtags']:>6} {s['empty_tag_pct']:>9} {s['high_sev_pct']:>6}  {note}")

print("\n" + "=" * 100)
print("PAIRWISE CHANGES (consecutive by score) -> what changed to buy the jump")
print(f"{'from':>8}->{'to':<8} {'dScore':>7} | {'repo':>5} {'sev':>5} {'tag':>5} {'subtag':>6} {'desc':>5} {'descLenUp':>9}  attribution")
for i in range(1, len(loaded)):
    fa, sca, na, da = loaded[i - 1]
    fb, scb, nb, db = loaded[i]
    dd = diff(da, db)
    ds = round(scb - sca, 2)
    # crude attribution: dominant changed field
    fields = {'repo/coverage': dd['repo'], 'severity': dd['severity'], 'tag': dd['tag'],
              'subtag': dd['subtag'], 'description': dd['desc']}
    dom = max(fields, key=fields.get)
    print(f"{sca:>8}->{scb:<8} {ds:>+7} | {dd['repo']:>5} {dd['severity']:>5} {dd['tag']:>5} {dd['subtag']:>6} "
          f"{dd['desc']:>5} {dd['desc_lenup']:>9}  DOMINANT: {dom} ({nb})")

json.dump([{'file': f, 'score': sc, 'note': note, **stats(d)} for f, sc, note, d in loaded],
          open(f'{ROOT}/artifacts/score_eda_stats.json', 'w'), indent=2)
print("\nsaved artifacts/score_eda_stats.json")
