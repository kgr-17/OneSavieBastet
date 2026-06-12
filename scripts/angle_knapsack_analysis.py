import pandas as pd, json, os

ROOT = r'c:/OneSavieBastet'
m = json.load(open(os.path.join(ROOT,'artifacts/test_hash_to_contest_v3.json')))
h2c = {k: (v.get('contest') or v.get('title_hint') or ('UNKNOWN_'+k)) for k,v in m.items()}

t = pd.read_csv(os.path.join(ROOT,'outputs/submission_teammate442.csv'))
d = pd.read_csv(os.path.join(ROOT,'data/dataset_0831.csv'), encoding='utf-8-sig')

def audit_of(p):
    if not isinstance(p,str): return None
    parts = p.replace('\\','/').split('/')
    for seg in parts:
        if len(seg)>=7 and seg[0:2]=='20' and '-' in seg:
            return seg
    return parts[-1] if parts else None

d['audit'] = d['repo_path'].map(audit_of)
ds_counts = d['audit'].value_counts()

t['audit'] = t['repo_path'].map(lambda h: h2c.get(h,'NOHASH_'+str(h)))
tm_counts = t['audit'].value_counts()

print('n distinct audits in 0831:', d['audit'].nunique())
print('n distinct test hashes mapped:', len(h2c))
print()
print('=== PER-AUDIT COUNT PROXY: teammate_pred vs 0831 rows ===')
print('NOTE: surplus here is not automatically a scorer penalty. The scorer keys on test hash,')
print('      and predictions for hashes absent from hidden truth are ignored rather than penalized.')
allaud = sorted(set(tm_counts.index)|set(ds_counts.index))
rows=[]
for a in allaud:
    tp = tm_counts.get(a,0); tr = ds_counts.get(a,0)
    if tp>0:
        rows.append((a,int(tp),int(tr),int(tp-tr)))
rows.sort(key=lambda r:-(r[3]))
print(f'{"audit":32s} {"tm":>4s} {"truth":>5s} {"diff":>5s}')
for a,tp,tr,diff in rows:
    if tr == 0:
        flag = '  (uncovered in 0831; probe needed, no automatic penalty)'
    elif diff > 0:
        flag = '  <<SURPLUS on covered audit (possible per-hash penalty)'
    else:
        flag = ''
    print(f'{a:32s} {tp:4d} {tr:5d}  {diff:+4d}{flag}')

covered_surplus = sum(max(0,df) for _,_,tr,df in rows if tr>0)
deficit = sum(-(df) for _,_,tr,df in rows if tr>0 and df<0)
covered_pred = sum(tp for _,tp,tr,_ in rows if tr>0)
uncovered_pred = sum(tp for _,tp,tr,_ in rows if tr==0)
print()
print('total teammate rows         :', int(tm_counts.sum()))
print('teammate rows on COVERED     :', covered_pred)
print('teammate rows on UNCOVERED   :', uncovered_pred)
print('covered-audit surplus proxy  :', covered_surplus)
print('total covered DEFICIT (addable headroom):', deficit)
