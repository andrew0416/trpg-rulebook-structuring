"""Source-reviewed TM prose reconciliation; never infer completion from duplicates."""
import json, re
from pathlib import Path
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[1]
# Each nonliteral equivalence below was compared with the complete original span.
MANUAL={
3: [('supp-polygon.md',325,327)],
9: [('supp-polygon.md',583,583)],
17:[('ch09-equipment.md',117,128)],
20:[('supp-fantasy.md',235,238)],
22:[('supp-fantasy.md',244,245)],
23:[('supp-fantasy.md',248,253)],
24:[('supp-fantasy.md',256,257)],
26:[('supp-fantasy.md',263,265)],
27:[('supp-fantasy.md',268,269)],
31:[('ch09-equipment.md',439,449)],
32:[('ch09-equipment.md',452,456),('ch09-equipment.md',472,472)],
34:[('ch10-index-reference.md',178,178)],
69:[('ch10-index-reference.md',381,383)],
74:[('supp-errata.md',859,861)],
87:[('ch07-combat.md',615,615)],
101:[('supp-errata.md',873,873)],
102:[('ch04-trainer-classes.md',523,531)],
108:[('ch11-running-the-game.md',1536,1554)],
111:[('ch05-pokemon.md',758,767)],
112:[('ch05-pokemon.md',787,794)],
}
NOTES={
3:'Same casing count/ownership/removal conditions; CSV collects common and restricted availability paragraphs and supplies names of the latter.',
9:'Same preparation state and technology requirement; appended list names the following catalog items.',
17:'Same herbal counter/extended-rest reset and first/second/third consumption states; CSV omits only the introductory advice paragraph.',
20:'Same catalyst grants; appended class tier reference is explanatory acquisition guidance, not a different state contract.',
23:'Same fossil ability and Spirit Surge contributions. CSV additionally makes 3 extras a minimum while MD192 calls 3 a baseline and MD194 permits none: preserve category6 recipe variant separately.',
24:'Same item/move tier and bonus; appended tier reference does not change state.',
32:'CSV concatenates nonadjacent original clauses; preserve all original parents rather than treating the prose block as one new rule.',
34:'Same innate move connection with different Korean word order.',
69:'Same single effective weather, replacement, five-round duration and GM-only natural-weather equivalence; added reference sentence only.',
74:'Same errata initiative and failed-save action choices; preserve selected errata context, do not merge with CSV73 legacy mechanics.',
101:'Prone implies Vulnerable is already explicit in errata Vulnerable parent; core prone action procedure remains separately linked by that source.',
102:'Same generated move template state; below replaced by tooltip is a presentation reference.',
108:'Same permanent type/grant/learnset changes and GM exceptions; 포이즌 translated as 독 in the example.',
111:'Same fishing rod categories, hooked target and bait/lure state; English parentheticals and table formatting omitted.',
112:'Same mounted actor relation and movement state; final chapter reference changed to skill reference only.',
}
def parents():
 out=[]
 for filename,key,kind in [('category2-core-clause-status.json','clause_mappings','core'),('category2-class-clause-status.json','entries','class'),('category2-optional-clause-status.json','rows','optional'),('category2-optional-additional-clause-status.json','rows','optional')]:
  d=json.loads((ROOT/'data/verification'/filename).read_text(encoding='utf-8'))
  for r in d[key]:
   uid=r.get('clause_id') or r.get('source_clause_id') or r['id']
   if kind=='core':
    spans=[]
    for b in r['block_ids']:
     m=re.fullmatch(r'(.+):(\d+)-(\d+)',b)
     if m:spans.append((m[1],int(m[2]),int(m[3])))
   else:spans=[(a['file'],a['start'],a['end']) for a in r.get('anchors',r.get('source',[]))]
   out.append((uid,spans))
 return out

def reconcile():
 path=ROOT/'data/verification/category2-tabular-core-status.json'
 d=json.loads(path.read_text(encoding='utf-8')); ps=parents(); unresolved=[]
 for r in d['entries']:
  if r['source_file']!='input/db/tm.csv' or not r['include_category2']:continue
  number=r['row']; refs=[]
  if number in MANUAL:
   refs=[dict(file='input/'+f,start=a,end=b) for f,a,b in MANUAL[number]]
  elif r['exact_text_matches']:
   refs=r['exact_text_matches']
   if '[에라타]' in r['name']: refs=[a for a in refs if a['file']=='input/supp-errata.md'] or refs
   else:refs=refs[:1]
  if not refs:
   unresolved.append(number);continue
  links=[]
  for ref in refs:
   file=ROOT/ref['file'];lines=file.read_text(encoding='utf-8').splitlines()
   ref=dict(ref,file_sha256=sha256(file.read_bytes()).hexdigest(),excerpt_sha256=sha256('\n'.join(lines[ref['start']-1:ref['end']]).encode()).hexdigest())
   ref['parent_clause_ids']=sorted({uid for uid,spans in ps if any(f==ref['file'] and a<=ref['end'] and b>=ref['start'] for f,a,b in spans)})
   links.append(ref)
  missing=any(not a['parent_clause_ids'] for a in links)
  r['semantic_source_links']=links
  if number==3:r['other_category_reference']={'file':'input/supp-polygon.md','start':367,'end':367,'disposition':'setting availability guidance; no universal state invariant'}
  r['semantic_review_note']=NOTES.get(number,'Full effect/body and source context agree; retain original source parents and their conditions/exceptions.')
  r['deduplication_status']='parent-link-unresolved' if missing else 'same-state-contract-existing-source-parents'
  r['denominator_contribution']=None if missing else 0
  r['completion_credit']=False
  if missing:unresolved.append(number)
  if number==23:r['other_category_variant']={'category':6,'csv':'Extras minimum three','md':'Three is suggested baseline; extras may be omitted','source':'input/supp-fantasy.md:192-194','status':'unresolved-selection'}
 d['counts']['tm_reconciled_to_original_parents']=sum(r.get('denominator_contribution')==0 for r in d['entries'] if r['source_file'].endswith('tm.csv') and r['include_category2'])
 d['counts']['tm_remaining_variant_review_rows']=unresolved
 path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(d['counts'],ensure_ascii=False,indent=2))
if __name__=='__main__':reconcile()
