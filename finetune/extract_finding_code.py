"""Exp2 core: for each finding (repo_hash + description), locate the Solidity code
it references and extract relevant snippets to feed an LLM classifier.
Strategy: parse Contract / Contract.function() identifiers from the description,
grep the repo's .sol files for them, extract the matching function bodies (capped).
"""
import os, re, glob, json, sys

ROOT = '/Users/yixuliu/OneSavieBastet'


def repo_dir(base, h):
    d = os.path.join(base, h)
    return d if os.path.isdir(d) else None


def clean_desc(desc):
    """Drop the auditor-credits / source boilerplate that pollutes identifier parsing."""
    return re.split(r'Source:|##\s*Found by|\*Submitted|\*\*Found', str(desc))[0].strip()


def idents(desc):
    """Extract likely Solidity identifiers from a finding description."""
    d = clean_desc(desc)
    out = []
    # Contract.function() and Contract.function patterns
    out += re.findall(r'\b([A-Z][A-Za-z0-9_]+)\.([A-Za-z_][A-Za-z0-9_]+)\s*\(', d)
    # bare function() calls
    funcs = re.findall(r'\b([a-z_][A-Za-z0-9_]{2,})\s*\(', d)
    # CamelCase contract names
    contracts = re.findall(r'\b([A-Z][A-Za-z0-9]{2,})\b', d)
    flat = set()
    for c, f in out:
        flat.add(c); flat.add(f)
    flat.update(funcs[:8]); flat.update(contracts[:8])
    # drop common english CamelCase noise
    noise = {'The', 'This', 'When', 'Source', 'Found', 'Summary', 'Impact', 'Cause',
             'However', 'Since', 'If', 'In', 'As', 'But', 'And', 'For', 'ERC', 'DoS'}
    return [x for x in flat if x not in noise and len(x) >= 3]


def extract(base, h, desc, budget=6000):
    rd = repo_dir(base, h)
    if not rd:
        return ''
    sols = glob.glob(rd + '/**/*.sol', recursive=True)
    # skip mocks/tests/interfaces for signal
    sols = [s for s in sols if not re.search(r'(mock|test|/lib/|node_modules|interface)', s, re.I)] or sols
    names = idents(desc)
    if not names:
        return ''
    # score files by how many identifiers they contain; grab top funcs
    scored = []
    for s in sols:
        try:
            txt = open(s, encoding='utf-8', errors='replace').read()
        except Exception:
            continue
        hits = sum(txt.count(n) for n in names)
        if hits:
            scored.append((hits, s, txt))
    scored.sort(reverse=True, key=lambda x: x[0])
    out, used = [], 0
    for hits, s, txt in scored[:3]:
        # try to pull function bodies mentioning the identifiers
        snippet = ''
        for n in names:
            m = re.search(r'(function\s+' + re.escape(n) + r'\b[\s\S]{0,1200}?\n\})', txt)
            if m:
                snippet += m.group(1) + '\n\n'
        if not snippet:
            snippet = txt[:1500]
        chunk = f"// FILE: {os.path.relpath(s, rd)}\n{snippet}"
        if used + len(chunk) > budget:
            chunk = chunk[:budget - used]
        out.append(chunk); used += len(chunk)
        if used >= budget:
            break
    return '\n'.join(out)


if __name__ == '__main__':
    # self-test on a few test findings
    import csv
    base = f'{ROOT}/data/test'
    ee = list(csv.DictReader(open(f'{ROOT}/outputs/submission_c4_v16_ee25fix.csv', encoding='utf-8-sig')))
    sheet = {r['Property']: r for r in csv.DictReader(open(f'{ROOT}/artifacts/teammate_labeling_sheet.csv', encoding='utf-8-sig'))}
    n_ok = 0
    for r in ee[:0] or [x for x in ee if x['Property'] in sheet][:8]:
        h = r['repo_path']; desc = sheet[r['Property']]['description']
        code = extract(base, h, desc)
        ids = idents(desc)
        print(f"pid {r['Property']} repo {h}: idents={ids[:5]} -> code {len(code)} chars {'OK' if code else 'MISS'}")
        if code:
            n_ok += 1
    print(f"\ncode found for {n_ok}/8 sampled findings")
