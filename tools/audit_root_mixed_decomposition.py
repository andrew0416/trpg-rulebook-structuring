"""52 mixed-candidate integrity checks. A pass is NOT semantic entailment."""
from __future__ import annotations
import argparse,collections,functools,hashlib,json
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
NAMES=('base','core','supplement')
SPECS=tuple('data/verification/root-mixed-'+n+'-decomposition.json' for n in NAMES)
SCOPES=('data/verification/root-authority-scope-review.json','data/verification/root-authority-scope-core-followup.json','data/verification/root-authority-scope-supplement-followup.json')
REVIEWS='data/verification/common-source-reviews'
GRAPH='data/verification/rule-symbol-graph.json'
ATOMS='data/verification/root-authority-atoms.json'
HIERARCHIES={'root_authority_contract','common_extension_interface','scoped_domain_rule','content_instance','guidance_or_explanation','source_context','unresolved_conflict'}
MODALITIES={'normative','permission','prohibition','recommendation','example','source_note','unresolved'}
CONTEXT_ONLY={'RMB-C11-053-04':('input/ch11-running-the-game.md',1530,1530),'RMB-C11-068-04':('input/ch11-running-the-game.md',1634,1635)}
BASE_CONTEXT={'C11-007':('01','09'),'C11-030':('01',),'C11-053':('01',),'C11-062':('01',),'C11-128':('01',)}
SUPPLEMENT_GUARDS={'CHB-FINANCE':'해당 홈브류 재정을 캠페인에 채택','CHB-TERASTAL':'선택형 테라스탈 모듈을 채택','CHB-ZMOVES':'해당 홈브류 Z기술 모듈을 채택','SB':'해당 축복/기프트 하위 모듈과 항목을 캠페인에 채택','ERRATA':'해당 플레이테스트 패킷 변경을 선택 프로필에 채택; PTK 수용 및 판본 관계는 별도','FAN':'해당 판타지 하위 모형을 캠페인에서 채택','SPOL':'해당 SF 하위 모형을 캠페인에서 채택'}
CORE_GUARDS={'RMC-C05-002-01':'일반적인 여행 동행 제한을 채택한 설정','RMC-C05-160-01':'d20 개정 포획 모델이 선택된 프로필','RMC-C07-185-01':'부상 페널티 옵션을 캠페인이 선택','RMC-C07-185-02':'추가 부상 페널티 옵션 채택','RMC-C07-185-03':'추가 부상 옵션의 위치 설명','RMC-C07-185-04':'추가 부상 옵션으로 생긴 단계 손실','RMC-C07-185-05':'추가 부상 페널티 옵션 채택'}
FALSE_KEYS={'semantic_closure','whole_rulebook_semantics_complete','whole_atomic_semantics_complete','all_atomic_rule_semantics_complete','meaning_coverage_proved','meaning_atomic_complete','atomic_semantics_complete','semantic_proof_complete','semantic_coverage_proved','source_condition_denominator_complete','runtime_implemented','runtime_tests_executed','new_root_axiom','whole_rule_certified','implementation_conformance_proved'}
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def text_hash(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
@functools.lru_cache(maxsize=512)
def _digest(p,size,mtime):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(p):
 p=Path(p).resolve();s=p.stat();return _digest(str(p),s.st_size,s.st_mtime_ns)
def safe(root,rel):
 if not isinstance(rel,str) or not rel or Path(rel).is_absolute():raise ValueError('unsafe_path')
 p=(root/rel).resolve()
 if not p.is_relative_to(root):raise ValueError('unsafe_path')
 return p
def nonempty(s):return isinstance(s,str) and bool(s.strip())
def strings(x):return isinstance(x,list) and all(nonempty(s) for s in x)
def anchor(root,file,start,end):
 ls=safe(root,file).read_text(encoding='utf-8-sig').splitlines()
 if type(start)is not int or type(end)is not int or not 1<=start<=end<=len(ls):raise ValueError('anchor_range')
 ex='\n'.join(ls[start-1:end]);return dict(file=file,start=start,end=end,excerpt=ex,excerpt_sha256=text_hash(ex))
def from_block(root,b):
 f,ran=b.rsplit(':',1);s,e=map(int,ran.split('-'));return anchor(root,f,s,e)
def overlap(a,b):return a['file']==b['file'] and max(a['start'],b['start'])<=min(a['end'],b['end'])
@functools.lru_cache(maxsize=8)
def pdf_page(path,size,mtime,page):
 from pypdf import PdfReader
 return PdfReader(path).pages[page].extract_text()
def normalize_specs(specs):
 if isinstance(specs,dict) and set(specs)==set(NAMES):return [specs[n] for n in NAMES]
 if isinstance(specs,(list,tuple)) and len(specs)==3:return list(specs)
 raise ValueError('exactly_three_specs_required')
def validate(specs,root)->list[str]:
 try:return _validate(normalize_specs(specs),Path(root).resolve())
 except (KeyError,TypeError,ValueError,IndexError,OSError,AttributeError) as e:return ['mixed_schema_error:'+type(e).__name__+':'+str(e)[:160]]
def _validate(specs,root):
 errors=[]
 def fail(x):errors.append(x)
 reviews={p.relative_to(root).as_posix():load(p) for p in sorted((root/REVIEWS).glob('*.json'))}
 live={}
 for f,r in reviews.items():
  for c in r['clauses']:
   if c['id'] in live:fail('mixed_live_duplicate:'+c['id'])
   live[c['id']]=(f,r['file'],c)
 if len(reviews)!=20:fail('mixed_review_inventory')
 symbols={x['id'] for x in load(root/GRAPH)['nodes']};atoms={x['id'] for x in load(root/ATOMS)['atoms']}
 expected=[]
 for f in SCOPES:
  ids=[x['candidate_id'] for x in load(root/f)['candidate_dispositions'] if x['category']=='mixed']
  if len(ids)!=len(set(ids)):fail('mixed_scope_duplicate:'+f)
  expected.append(set(ids))
 if [len(x) for x in expected]!=[9,16,27] or len(set.union(*expected))!=52:fail('mixed_scope_denominator')
 components={};allids=[]
 for spec in specs:
  for x in spec['components']:
   if x['id'] in components:fail('mixed_component_duplicate:'+x['id'])
   components[x['id']]=x
  allids.extend(x['candidate_id'] for x in spec['candidates'])
 if len(allids)!=52 or len(set(allids))!=52:fail('mixed_candidate_set')
 def check_hash(f,h,label):
  if digest(safe(root,f))!=h:fail('mixed_file_hash:'+label)
 def check_anchor(a,label):
  a2=anchor(root,a['file'],a['start'],a['end'])
  if any(a.get(k)!=v for k,v in a2.items()):fail('mixed_anchor:'+label)
 def false_claims(x,label):
  if isinstance(x,dict):
   for k,v in x.items():
    if k in FALSE_KEYS and v is not False:fail('mixed_false_closure:'+label+':'+k)
    if k in {'new_root_atoms','root_axioms_added'} and (type(v)is not int or v!=0):fail('mixed_new_root_claim:'+label)
    if k=='coverage_percent' and v is not None:fail('mixed_coverage_claim:'+label)
    false_claims(v,label)
  elif isinstance(x,list):
   for y in x:false_claims(y,label)
 for idx,spec in enumerate(specs):
  name=NAMES[idx];false_claims(spec,name)
  if spec.get('semantic_closure') is not False:fail('mixed_false_closure:'+name)
  cs={x['candidate_id']:x for x in spec['candidates']}
  if set(cs)!=expected[idx] or len(cs)!=len(spec['candidates']):fail('mixed_candidate_set:'+name)
  if 'component_count' in spec.get('scope',{}) and spec['scope']['component_count']!=len(spec['components']):fail('mixed_component_count:'+name)
  scope=spec['scope'];sf=scope.get('source_scope_report',scope.get('parent_scope_file',scope.get('selection_file')))
  if sf!=SCOPES[idx]:fail('mixed_scope_reference:'+name)
  declared=scope.get('candidate_ids',scope.get('selected_candidate_ids',scope.get('selection',{}).get('candidate_ids')))
  if not isinstance(declared,list) or set(declared)!=expected[idx] or len(declared)!=len(expected[idx]):fail('mixed_declared_candidate_set:'+name)
  snaps={}
  for sn in spec['source_snapshots']:
   f=sn.get('file',sn.get('source_file'));h=sn.get('sha256',sn.get('source_sha256'))
   if f in snaps:fail('mixed_snapshot_duplicate:'+name)
   snaps[f]=sn;check_hash(f,h,name+':'+f)
   if f.startswith('input/'):
    ls=safe(root,f).read_text(encoding='utf-8-sig').splitlines()
    if 'source_line_count' in sn and sn['source_line_count']!=len(ls):fail('mixed_line_count:'+f)
    for rng in sn.get('direct_source_read_ranges',[]):
     if len(rng)!=2 or not 1<=rng[0]<=rng[1]<=len(ls):fail('mixed_read_range:'+f)
  for f,h in spec.get('input_hashes',{}).items():check_hash(f,h,name+':'+f)
  sh=scope.get('parent_scope_sha256',scope.get('selection_sha256',spec.get('input_hashes',{}).get(sf)))
  if sh is None and sf in snaps:sh=snaps[sf].get('sha256')
  check_hash(sf,sh,name+':scope')
  for c in spec['candidates']:
   cid=c['candidate_id'];rf,src,current=live[cid]
   if c['review_file']!=rf or c['source_file']!=src:fail('mixed_candidate_source:'+cid)
   check_hash(rf,c['review_sha256'],cid+':review');check_hash(src,c['source_sha256'],cid+':source')
   if c['current_candidate']!=current:fail('mixed_candidate_snapshot:'+cid)
   aa=[from_block(root,b) for b in current['block_ids']]
   for a in c['anchors']:check_anchor(a,cid)
   if c['anchors']!=aa:fail('mixed_candidate_anchor_relation:'+cid)
   if src not in snaps:fail('mixed_source_snapshot_missing:'+cid)
   ids=c['component_ids'];actual={x['id'] for x in spec['components'] if x['candidate_id']==cid}
   if not ids or len(ids)!=len(set(ids)) or set(ids)!=actual:fail('mixed_component_crosslink:'+cid)
   lines={(a['file'],n) for a in aa for n in range(a['start'],a['end']+1)}
   ac=c.get('source_line_accounting',[]);got=[(x.get('file',src),x['line']) for x in ac]
   if set(got)!=lines or len(got)!=len(set(got)):fail('mixed_line_accounting:'+cid)
   for x in ac:
    f=x.get('file',src);n=x['line'];t=anchor(root,f,n,n)['excerpt']
    if 'source_text'in x and x['source_text']!=t:fail('mixed_line_text:'+cid)
    if not x['component_ids'] and t.strip() not in {'','<table>','</table>'}:fail('mixed_line_unaccounted:'+cid)
    for ref in x['component_ids']:
     if ref not in actual:fail('mixed_line_reference:'+cid)
     elif not any(a['file']==f and a['start']<=n<=a['end'] for a in components[ref]['source_anchors']):fail('mixed_line_reference_range:'+cid)
  for x in spec['components']:
   ident=x['id'];cid=x['candidate_id']
   if cid not in cs:fail('mixed_component_owner:'+ident);continue
   if x.get('status')!='draft' or x.get('semantic_closure') is not False:fail('mixed_component_status:'+ident)
   if x.get('hierarchy') not in HIERARCHIES or x.get('modality') not in MODALITIES:fail('mixed_modality:'+ident)
   if not nonempty(x.get('statement')):fail('mixed_statement:'+ident)
   if not strings(x.get('conditions')) or not x['conditions']:fail('mixed_conditions:'+ident)
   for k in ['exceptions','unresolved','parent_symbols']:
    if not strings(x.get(k)):fail('mixed_component_list:'+ident+':'+k)
   if not x['parent_symbols'] or not set(x['parent_symbols'])<=symbols:fail('mixed_symbol:'+ident)
   if not (strings(x.get('delegation')) or nonempty(x.get('delegation'))):fail('mixed_delegation:'+ident)
   form=x.get('formal_relation',{})
   if not isinstance(form.get('variables'),dict) or not form['variables'] or not nonempty(form.get('relation')) or not nonempty(form.get('interpretation_limit')):fail('mixed_formal_relation:'+ident)
   for k in ['positive_case','boundary_case']:
    if not all(x.get(k,{}).get(z) for z in ['given','expected','not_inferred']):fail('mixed_case:'+ident)
   aa=x['source_anchors']
   if not aa:fail('mixed_component_anchor_missing:'+ident)
   for a in aa:check_anchor(a,ident)
   if not any(overlap(a,b) for a in aa for b in cs[cid]['anchors']):
    allowed=CONTEXT_ONLY.get(ident)
    if not allowed or not any((a['file'],a['start'],a['end'])==allowed for a in aa):fail('mixed_component_parent_range:'+ident)
   spans=x.get('source_spans',x.get('source_span'))
   if not isinstance(spans,list) or not spans:fail('mixed_source_span_missing:'+ident)
   else:
    for s in spans:
     if isinstance(s,str):
      if not s or not any(s in a['excerpt'] for a in aa):fail('mixed_source_span:'+ident)
     elif isinstance(s,dict):
      a=aa[s['anchor_index']];t=s.get('text',s.get('excerpt'))
      if not nonempty(t) or t not in a['excerpt']:fail('mixed_source_span:'+ident)
      if 'start_offset'in s or 'end_offset'in s:
       i,j=s['start_offset'],s['end_offset']
       if type(i)is not int or type(j)is not int or not 0<=i<j<=len(a['excerpt']) or a['excerpt'][i:j]!=t:fail('mixed_source_span_offset:'+ident)
      if 'excerpt_sha256'in s and s['excerpt_sha256']!=text_hash(t):fail('mixed_source_span_hash:'+ident)
     else:fail('mixed_source_span:'+ident)
   focus_anchors=[]
   if isinstance(spans,list):
    for sp in spans:
     if isinstance(sp,str):focus_anchors.extend(a for a in aa if sp and sp in a['excerpt'])
     elif isinstance(sp,dict):focus_anchors.append(aa[sp['anchor_index']])
   if not any(overlap(a,b) for a in focus_anchors for b in cs[cid]['anchors']):
    declared_context=CONTEXT_ONLY.get(ident)
    if not declared_context or not any((a['file'],a['start'],a['end'])==declared_context for a in focus_anchors):fail('mixed_focused_parent_range:'+ident)
   atom_reuse={r.get('id') for r in x.get('reuse_refs',[]) if r.get('type') in {'existing_atom','existing_authority_atom','root_authority_atom'}}
   if atom_reuse!=set(x.get('existing_atom_refs',[])):fail('mixed_atom_crosslink:'+ident)
   for r in x.get('reuse_refs',[]):
    typ=r.get('type');rid=r.get('id')
    allowed=atoms if typ in {'existing_atom','existing_authority_atom','root_authority_atom'} else live if typ in {'candidate','source_review_candidate'} else set()
    if rid not in allowed or not nonempty(r.get('relationship')):fail('mixed_reuse_reference:'+ident)
   if not strings(x.get('existing_atom_refs')) or not set(x['existing_atom_refs'])<=atoms:fail('mixed_atom_reference:'+ident)
   for ref in x.get('context_component_refs',[]):
    if ref==ident or ref not in components or (components[ref]['candidate_id']!=cid and not (ident=='MSUP-SPOL-077-01' and ref in {'MSUP-SPOL-068-01','MSUP-SPOL-068-02'})):fail('mixed_context_reference:'+ident)
   if x['hierarchy']=='root_authority_contract' and not x.get('existing_atom_refs'):fail('mixed_unbacked_root_contract:'+ident)
   if idx==0 and cid in BASE_CONTEXT and not ident.endswith('-01'):
    required={f'RMB-{cid}-{n}' for n in BASE_CONTEXT[cid]}
    if cid=='C11-007' and ident.rsplit('-',1)[1] in {'09','10'}:required=set()
    if not required<=set(x.get('context_component_refs',[])):fail('mixed_optional_guard:'+ident)
   if idx==1 and ident in CORE_GUARDS and CORE_GUARDS[ident] not in x['conditions']:fail('mixed_optional_guard:'+ident)
   if idx==2:
    prefix=next((p for p in SUPPLEMENT_GUARDS if cid.startswith(p+'-')),None)
    if prefix is None or SUPPLEMENT_GUARDS[prefix] not in x['conditions']:fail('mixed_optional_guard:'+ident)
    given=x['positive_case']['given']
    if not isinstance(given,dict) or given.get('selected_module_and_conditions')!=x['conditions']:fail('mixed_guard_case_binding:'+ident)
  for pa in spec.get('supporting_pdf_anchors',[]):
   check_hash(pa['file'],pa['file_sha256'],name+':pdf');p=safe(root,pa['file']);st=p.stat()
   page=pdf_page(str(p),st.st_size,st.st_mtime_ns,pa['page_index'])
   if pa['excerpt'] not in page or text_hash(pa['excerpt'])!=pa['excerpt_sha256']:fail('mixed_pdf_excerpt:'+pa['id'])
  for c in spec['candidates']:
   for ac in c.get('source_text_accounting',[]):
    check_anchor(ac['anchor'],c['candidate_id']+':accounting');t=ac['anchor']['excerpt']
    for r in ac['residual_segments']:
     piece=t[r['start_offset']:r['end_offset']]
     if piece!=r['excerpt'] or text_hash(piece)!=r['excerpt_sha256']:fail('mixed_residual_excerpt:'+c['candidate_id'])
    for s in ac['focused_component_spans']:
     if s['component_id'] not in c['component_ids']:fail('mixed_text_accounting_reference:'+c['candidate_id'])
 return sorted(set(errors))
def input_files(specs,root):
 root=Path(root).resolve();files=set(SCOPES)|{GRAPH,ATOMS}
 files.update(p.relative_to(root).as_posix() for p in (root/REVIEWS).glob('*.json'))
 for s in normalize_specs(specs):
  files.update(s.get('input_hashes',{}))
  files.update(x.get('file',x.get('source_file')) for x in s['source_snapshots'])
  for c in s['candidates']:files.update((c['review_file'],c['source_file']))
  for x in s['components']:files.update(a['file'] for a in x['source_anchors'])
  files.update(a['file'] for a in s.get('supporting_pdf_anchors',[]))
 return sorted(files)
def input_hashes(specs,root,spec_paths=()):
 root=Path(root).resolve();out={f:digest(safe(root,f)) for f in input_files(specs,root)}
 for p in spec_paths:
  p=Path(p).resolve();out[p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p)]=digest(p)
 out['tools/audit_root_mixed_decomposition.py']=digest(__file__);return out
def build_report(specs,root,spec_paths=()):
 specs=normalize_specs(specs);errs=validate(specs,root);cc=[x for s in specs for x in s['components']]
 return {'generated_at':datetime.now(timezone.utc).isoformat(),'kind':'mixed_decomposition_integrity_not_semantic_proof','candidate_count':sum(len(s['candidates']) for s in specs),'component_count':len(cc),'hierarchy_counts':dict(collections.Counter(x['hierarchy'] for x in cc)),'input_hashes':input_hashes(specs,root,spec_paths),'errors':errs,'results':{'passed':not errs,'error_count':len(errs),'errors':errs},'semantic_closure':False,'all_atomic_rule_semantics_complete':False,'limitations':['Components are not proved atoms.','Guard checks protect declared adoption/context contracts, not inferred source semantics.','Exact quotes are verified; free-form interpretation entailment and omitted conditions still require independent review.']}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);ap.add_argument('--spec',action='append',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
 paths=a.spec or [a.root/p for p in SPECS];report=build_report([load(p) for p in paths],a.root,paths)
 out=a.output or a.root/'output/whole-rulebook-audit/root-mixed-decomposition-audit.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report['results'],ensure_ascii=False));return 0 if report['results']['passed'] else 1
if __name__=='__main__':raise SystemExit(main())

