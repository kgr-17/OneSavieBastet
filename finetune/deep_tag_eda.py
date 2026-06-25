"""Deep tag/subtag dive across the score ladder + gold, to find systematic
mis-labeling and what we're missing. Answers: which tags we over/under-use vs
gold, which corrections bought the retag-era points, which rows never stabilized
(ambiguous), and whether we under-use multi-labels (partial-credit left on table).
"""
import csv, re, json
from collections import Counter, defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'


def n1(s):
    return re.sub(r'\s+', ' ', str(s).split(',')[0]).strip().lower()


def labs(s):
    return [n1(x) for x in str(s).split(',') if x.strip()]


LADDER = [
    ('data_history/submission_c4_v5_312.09.csv', 312.09),
    ('data_history/submission_442.38.csv', 442.38),
    ('data_history/0d40f2c3_447.63.csv', 447.63),
    ('outputs/submission_c4_v13_retag.csv', 464.75),
    ('outputs/submission_c4_v14_fulltag.csv', 468.56),
    ('outputs/submission_c4_v15_canonical.csv', 471.18),
    ('outputs/submission_c4_v16_maxcontext.csv', 474.21),
    ('data_history/submission_c4_v16_ee25fix_475.07.csv', 475.07),
    ('data_history/submission_c4_v34_teacher_all_479.27.csv', 479.27),
]


def load(f):
    return {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/{f}', encoding='utf-8-sig'))}


loaded = [(sc, load(f)) for f, sc in LADDER]
gold = list(csv.DictReader(open(f'{ROOT}/train.csv', encoding='utf-8-sig')))

# ---- Part 1: distribution vs gold (primary-tag share) ----
gold_tags = Counter(n1(r['tag']) for r in gold)
best = loaded[-1][1]  # v34
best_tags = Counter(n1(r['tag']) for r in best.values() if r['tag'].strip())
gt = sum(gold_tags.values()); bt = sum(best_tags.values())
print("=== Part 1: primary-TAG distribution — v34 vs gold (train.csv) ===")
print(f"{'tag':<22}{'gold%':>7}{'v34%':>7}{'diff':>7}")
alltags = sorted(set(gold_tags) | set(best_tags), key=lambda t: -(best_tags.get(t, 0)))
for t in alltags[:18]:
    g = 100 * gold_tags.get(t, 0) / gt
    b = 100 * best_tags.get(t, 0) / bt
    flag = '  <<OVER' if b - g > 3 else ('  <<UNDER' if g - b > 3 else '')
    print(f"{t:<22}{g:>6.1f}{b:>6.1f}{b-g:>+7.1f}{flag}")

# ---- Part 2: corrections during the retag era (442 -> 479) ----
print("\n=== Part 2: most common TAG corrections across retag jumps (442->479) ===")
tagmoves = Counter(); submoves = Counter()
retag = [d for sc, d in loaded if sc >= 442]
for i in range(1, len(retag)):
    a, b = retag[i - 1], retag[i]
    for p in set(a) & set(b):
        if n1(a[p]['tag']) != n1(b[p]['tag']):
            tagmoves[(n1(a[p]['tag']), n1(b[p]['tag']))] += 1
        if n1(a[p]['subtag']) != n1(b[p]['subtag']):
            submoves[(n1(a[p]['subtag']), n1(b[p]['subtag']))] += 1
for (o, nw), c in tagmoves.most_common(12):
    print(f"  {o:<20} -> {nw:<20} x{c}")
print("\n  most common SUBTAG corrections:")
for (o, nw), c in submoves.most_common(10):
    print(f"  {o:<28} -> {nw:<28} x{c}")

# ---- Part 3: instability — rows that never stabilized ----
print("\n=== Part 3: most UNSTABLE rows (distinct tags across the ladder = ambiguous) ===")
churn = {}
for p in loaded[0][1]:
    tags = set(n1(d[p]['tag']) for sc, d in loaded if p in d and d[p]['tag'].strip())
    subs = set(n1(d[p]['subtag']) for sc, d in loaded if p in d and d[p]['subtag'].strip())
    churn[p] = (len(tags), len(subs))
unstable = sorted(churn.items(), key=lambda x: -(x[1][0] + x[1][1]))
print(f"  rows with >=4 distinct tags across versions: {sum(1 for p,(t,s) in churn.items() if t>=4)}")
for p, (t, s) in unstable[:8]:
    print(f"  pid {p}: {t} distinct tags, {s} distinct subtags | v34={best[p]['tag']!r}/{best[p]['subtag']!r}")

# ---- Part 4: multi-label usage vs gold ----
print("\n=== Part 4: multi-label usage (partial-credit lever) ===")
gold_mt = sum(len(labs(r['tag'])) for r in gold) / len(gold)
gold_ms = sum(len(labs(r['subtag'])) for r in gold) / len(gold)
print(f"  gold: {gold_mt:.2f} tags/row, {gold_ms:.2f} subtags/row | multi-tag rows {100*sum(1 for r in gold if len(labs(r['tag']))>1)/len(gold):.0f}%")
for sc, d in loaded:
    nz = [r for r in d.values() if r['tag'].strip()]
    mt = sum(len(labs(r['tag'])) for r in nz) / len(nz)
    ms = sum(len(labs(r['subtag'])) for r in nz) / len(nz)
    print(f"  {sc}: {mt:.2f} tags/row, {ms:.2f} subtags/row | multi-tag {100*sum(1 for r in nz if len(labs(r['tag']))>1)/len(nz):.0f}%")
