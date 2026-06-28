"""Team B static-detector stage (mirrors OneSavie's regex/AST static engine).
Deterministic, high-precision detectors run over each TEST repo's Solidity code.
For each detected pattern we get a CERTAIN tag for that repo; we then map it to the
guessed rows in that repo whose description matches, as a high-confidence
confirmation signal for the relabel. Pure code, no LLM.
"""
import csv, re, os, glob, json
from collections import defaultdict

ROOT = '/Users/yixuliu/OneSavieBastet'
TEST = f'{ROOT}/data/test'

# (tag, subtag, regex, requires-absence-of regex within window) — OneSavie's static patterns
DETECTORS = [
    ('Chainlink', 'Deprecated Library', re.compile(r'\.\s*latestAnswer\s*\(\s*\)'), None),
    ('Chainlink', 'Stale Value', re.compile(r'\.\s*latestRoundData\s*\('), re.compile(r'updatedAt|updated_at|block\.timestamp\s*-')),
    ('Slippage', 'Missing minOut / maxAmount', re.compile(r'swapExactTokensForTokens\s*\([^;]*?,\s*0\s*,'), None),
    ('Slippage', 'Missing deadline', re.compile(r'block\.timestamp\s*\)') , None),  # weak; only as hint
    ('Reentrancy', 'Violating CEI / Missing nonReentrant', re.compile(r'\.call\s*\{\s*value:'), re.compile(r'nonReentrant')),
    ('DoS', 'Unbounded loop', re.compile(r'for\s*\([^;]*;[^;]*\.length\s*;'), None),
]

ee = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v50_v49_plus216.csv', encoding='utf-8-sig'))}


def scan_repo(repo_hash):
    d = os.path.join(TEST, repo_hash)
    if not os.path.isdir(d):
        return {}
    sols = [s for s in glob.glob(d + '/**/*.sol', recursive=True)
            if not re.search(r'(mock|test|/lib/|node_modules|interface)', s, re.I)] or glob.glob(d + '/**/*.sol', recursive=True)
    hits = defaultdict(int)
    for s in sols:
        try:
            txt = open(s, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        for tag, sub, rgx, absent in DETECTORS:
            for m in rgx.finditer(txt):
                if absent is not None:
                    window = txt[max(0, m.start() - 400): m.end() + 400]
                    if absent.search(window):
                        continue
                hits[(tag, sub)] += 1
    return dict(hits)


# scan each repo present in the submission
repos = sorted(set(r['repo_path'] for r in ee.values()))
repo_hits = {}
for h in repos:
    hh = scan_repo(h)
    if hh:
        repo_hits[h] = hh

# summary: which detectors fire, and in how many repos
allhits = defaultdict(int)
for h, hh in repo_hits.items():
    for k, c in hh.items():
        allhits[k] += 1
print(f"static detectors fired across {len(repo_hits)}/{len(repos)} repos:")
for (tag, sub), nrep in sorted(allhits.items(), key=lambda x: -x[1]):
    print(f"  {tag}/{sub}: present in {nrep} repos")

# strong signal: Chainlink latestAnswer (deprecated) is near-certain. List guessed rows in those repos.
json.dump({f"{h}": {f"{t}|{s}": c for (t, s), c in hh.items()} for h, hh in repo_hits.items()},
          open(f'{ROOT}/finetune/teacher/static_hits.json', 'w'), indent=1)
print("\nsaved finetune/teacher/static_hits.json")

# show chainlink-deprecated repos and their guessed rows
print("\nChainlink/Deprecated (latestAnswer) repos + their current guessed-row tags:")
for h, hh in repo_hits.items():
    if ('Chainlink', 'Deprecated Library') in hh:
        rows = [P for P, r in ee.items() if r['repo_path'] == h]
        cur = [(P, ee[P]['tag']) for P in rows if ee[P]['tag'].lower() != 'chainlink']
        if cur:
            print(f"  repo {h}: {len(rows)} rows, non-Chainlink-tagged: {cur[:6]}")
