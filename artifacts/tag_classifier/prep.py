import csv, json, random
from collections import Counter, defaultdict

tr=list(csv.DictReader(open('train.csv',encoding='utf-8-sig')))
# exact label vocab from competition truth
def labs(v,key): return [p.strip() for p in str(v.get(key,'')).split(',') if p.strip()]
tag_vocab=sorted(set(t for r in tr for t in labs(r,'tag')))
sub_vocab=sorted(set(s for r in tr for s in labs(r,'subtag')))
print('distinct tags:',len(tag_vocab),'| distinct subtags:',len(sub_vocab))

# repo-level split (SAME as diagnostic: seed 1337, 30% holdout)
repos=sorted(set(r['repo_path'] for r in tr))
random.Random(1337).shuffle(repos)
k=int(len(repos)*0.3); hold=set(repos[:k]); train=set(repos[k:])
trn=[r for r in tr if r['repo_path'] in train]
hld=[r for r in tr if r['repo_path'] in hold]

holdout=[{'id':i,'repo':r['repo_path'],'severity':r['severity'],
          'description':r['description'],
          'truth_tag':labs(r,'tag'),'truth_subtag':labs(r,'subtag')} for i,r in enumerate(hld)]

# few-shot: diverse examples from TRAIN split (no leakage), cover many tags
by_tag=defaultdict(list)
for r in trn:
    t=labs(r,'tag'); 
    if t: by_tag[t[0]].append(r)
fewshot=[]
for t in [x for x,_ in Counter(labs(r,'tag')[0] for r in trn if labs(r,'tag')).most_common()]:
    if by_tag[t]:
        r=by_tag[t][0]
        fewshot.append({'description':r['description'][:300],'tag':labs(r,'tag'),'subtag':labs(r,'subtag')})
    if len(fewshot)>=30: break

json.dump(holdout, open('artifacts/tag_classifier/holdout.json','w',encoding='utf-8'), ensure_ascii=False)
json.dump(fewshot, open('artifacts/tag_classifier/fewshot.json','w',encoding='utf-8'), ensure_ascii=False)
json.dump({'tags':tag_vocab,'subtags':sub_vocab}, open('artifacts/tag_classifier/vocab.json','w',encoding='utf-8'), ensure_ascii=False)
print('holdout findings:',len(holdout),'| fewshot examples:',len(fewshot))
print('tags:',tag_vocab)
