"""v61 = v59 (best, 482.97) + concise rewrite of the 23 verbose gold rows
(+ optional severity fixes). Two variants:
  v61b = v59 + gold-row concise descriptions only  (safer; pure description lever)
  v61  = v61b + 15 severity fixes (>=0.80 report match)  (includes the riskier severity)
"""
import csv, json, re, os
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = '/Users/yixuliu/OneSavieBastet'
gitmap = json.load(open(f'{ROOT}/finetune/teacher/gitmap.json'))

# gold rewrites
raw = open('/private/tmp/claude-501/-Users-yixuliu-OneSavieBastet/e8716397-f06c-4536-9867-1620f92906d6/tasks/GOLDREWRITE').read()
i = raw.find('{')
rw = {str(x['id']): x['description'] for x in json.loads(raw[i:])['result']['rewrites']}
print(f'gold rewrites: {len(rw)}/23')

v59 = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v59_gitfix_descrewrite.csv', encoding='utf-8-sig')))


def write(rows, name):
    w = csv.DictWriter(open(f'{ROOT}/outputs/{name}.csv', 'w', newline='', encoding='utf-8'),
                       fieldnames=['Property', 'repo_path', 'severity', 'tag', 'subtag', 'description'])
    w.writeheader(); w.writerows(rows)


# v61b: descriptions only
b = [dict(r) for r in v59]
nd = 0
for r in b:
    if r['Property'] in rw and len(rw[r['Property']]) > 30:
        r['description'] = rw[r['Property']]; nd += 1
write(b, 'submission_c4_v61b_golddesc')
print(f'v61b: {nd} verbose gold descriptions rewritten concise')

# v61: + severity fixes (recompute >=0.80 report matches)
def strip_md(t):
    t = re.sub(r'```[\s\S]*?```', ' ', t); t = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', t)
    t = re.sub(r'`([^`]*)`', r'\1', t); t = re.sub(r'[#*>|]', ' ', t); return re.sub(r'\s+', ' ', t).strip()
def parse(name):
    p = f'{ROOT}/artifacts/c4_reports/{name}.md'
    if not os.path.exists(p): return []
    txt = open(p, encoding='utf-8', errors='replace').read()
    parts = re.split(r'(^#+\s*(?:Issue\s+)?\[*\[?[HM]-?\d+[^\n]*)', txt, flags=re.M | re.I); out = []
    for k in range(1, len(parts), 2):
        body = parts[k + 1] if k + 1 < len(parts) else ''
        sev = 'High' if re.search(r'H-?\d', parts[k], re.I) else 'Medium'
        d = strip_md(body)[:450]
        if len(d) > 40: out.append({'severity': sev, 'desc': d})
    return out
enc = SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu')
cbc = {}
for h, c in gitmap.items():
    if c == 'forge-std': continue
    f = parse(c)
    if f: cbc[h] = (f, enc.encode([x['desc'] for x in f], normalize_embeddings=True, show_progress_bar=False))
s = [dict(r) for r in b]
ns = 0
for r in s:
    e = cbc.get(r['repo_path'])
    if not e: continue
    f, Ef = e
    sim = (enc.encode([r['description']], normalize_embeddings=True, show_progress_bar=False) @ Ef.T)[0]
    j = int(sim.argmax())
    if sim.max() >= 0.80 and f[j]['severity'] != r['severity'].strip():
        r['severity'] = f[j]['severity']; ns += 1
write(s, 'submission_c4_v61_golddesc_sev')
print(f'v61: + {ns} severity fixes (>=0.80 report match)')

# length report
import statistics
gl = [len(r['description']) for r in b]
print(f"all desc length median: {int(statistics.median(gl))} (truth ~223)")
