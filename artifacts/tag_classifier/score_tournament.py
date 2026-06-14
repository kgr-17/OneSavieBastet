import json, io, re
from collections import Counter, defaultdict
def norm(s): return re.sub(r'\s+',' ',str(s).split(',')[0]).strip().lower()
hold=json.load(io.open('artifacts/tag_classifier/holdout.json',encoding='utf-8'))
res=json.load(io.open('artifacts/tag_classifier/tournament.json',encoding='utf-8'))
def evalsrc(byPid):
    te=se=0;n=len(hold); hard=defaultdict(lambda:[0,0])
    for h in hold:
        p=byPid.get(str(h['id'])) or byPid.get(h['id'])
        pt=norm(p['tag']) if p else None; ps=norm(p['subtag']) if p else None
        tt=norm(h['truth_tag'][0]) if h['truth_tag'] else None
        if tt:
            if tt in ('dos','access control','input validation','logic error'): hard[tt][1]+=1
            if pt==tt:
                te+=1
                if tt in hard: hard[tt][0]+=1
        if h['truth_subtag'] and ps==norm(h['truth_subtag'][0]): se+=1
    return 100*te/n,100*se/n,hard
print('=== TOURNAMENT (single-pass holdout) — baselines: canonical 3p=61/51, generic 1p=55/44 ===')
rows=[]
for key,byPid in res.items():
    t,s,hard=evalsrc(byPid); rows.append((t+s,key,t,s,hard))
rows.sort(reverse=True)
print(f'{"strategy":12} {"TAG":>5} {"SUB":>5}  | DoS  AC   IV   Logic')
for tot,key,t,s,hard in rows:
    h=' '.join(f'{(100*hard[x][0]//hard[x][1]) if hard[x][1] else 0:3d}' for x in ['dos','access control','input validation','logic error'])
    print(f'{key:12} {t:4.0f}% {s:4.0f}%  | {h}')
print(f'\nWINNER: {rows[0][1]} (tag+sub={rows[0][0]:.0f})')
