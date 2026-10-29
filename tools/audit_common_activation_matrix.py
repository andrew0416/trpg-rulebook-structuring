from pathlib import Path
import json,hashlib,csv,ast
ROOT=Path(__file__).resolve().parents[1]
REL='data/verification/common-activation-transition-contract.json'
CATEGORIES={'bounded_verified','implementation_missing','source_ambiguity','gm_defined_input','verification_missing','higher_scope_grouping'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate(spec,root=ROOT):
 root=Path(root);errors=[]
 def bad(s):errors.append(s)
 if any(spec.get(k) is not False for k in ['whole_root_complete','whole_rulebook_complete','source_denominator_complete']):bad('unsupported_global_closure')
 expected={f'ROOT-{i:02}' for i in range(1,27)}|{f'AE-C{i:02}' for i in range(1,33)}|{f'ACT-H{i:02}' for i in range(1,11)}
 cs=spec.get('conditions',[]);ids=[c.get('id') for c in cs]
 if set(ids)!=expected or len(ids)!=len(expected):bad('condition_set_mismatch')
 syms=json.loads((root/'data/verification/top-level-milestone.json').read_text(encoding='utf8'))['symbols'];ss=spec.get('interfaces',[])
 if {s.get('id') for s in ss}!={s['id'] for s in syms} or len(ss)!=len(syms):bad('interface_set_mismatch')
 sources={};cache={}
 for a in spec.get('source_anchors',[]):
  if a['id'] in sources:bad('duplicate_anchor:'+a['id'])
  sources[a['id']]=a;p=root/a['file']
  if not p.is_file() or digest(p)!=a['file_sha256']:bad('source_file_drift:'+a['id']);continue
  if 'record_1based' in a:
   if str(p) not in cache:
    with p.open(encoding='utf-8-sig',newline='') as f:cache[str(p)]=list(csv.reader(f))
   excerpt=cache[str(p)][a['record_1based']-1][a['column_1based']-1]
  else:excerpt='\n'.join(p.read_text(encoding='utf-8-sig').splitlines()[a['start']-1:a['end']])
  if excerpt!=a['excerpt'] or hashlib.sha256(excerpt.encode()).hexdigest()!=a['excerpt_sha256']:bad('source_excerpt_drift:'+a['id'])
 evidence=spec.get('evidence_catalog',{})
 for c in cs:
  id=c['id']
  if c.get('exit_category') not in CATEGORIES:bad('bad_exit_category:'+id)
  if not c.get('condition_and_transition') or not c.get('exit_evidence'):bad('missing_semantics_or_exit:'+id)
  if not c.get('source_anchor_ids') or not set(c['source_anchor_ids'])<=sources.keys():bad('missing_source:'+id)
  if not set(c.get('evidence_refs',[]))<=evidence.keys():bad('unknown_evidence:'+id)
  for p in c.get('runtime_paths',[]):
   f=root/p['file']
   if not f.is_file() or digest(f)!=p['file_sha256']:bad('runtime_file_drift:'+id);continue
   lines=f.read_text(encoding='utf8').splitlines();ex='\n'.join(lines[p['start']-1:p['end']])
   if hashlib.sha256(ex.encode()).hexdigest()!=p['excerpt_sha256']:bad('runtime_excerpt_drift:'+id)
  if c.get('bounded_subcontract_complete'):
   if c['exit_category']!='bounded_verified' or c.get('runtime_status')!='implemented_bounded' or not c.get('runtime_paths') or not c.get('evidence_refs'):bad('unsupported_bounded_closure:'+id)
   if not any(evidence[e].get('fully_current') and evidence[e].get('passing_test_ids') for e in c.get('evidence_refs',[]) if e in evidence):bad('no_current_conformance:'+id)
  if c.get('runtime_status') in ['missing','pending_only','held_only'] and c.get('semantic_support_counted'):bad('pending_counted_as_implementation:'+id)
 packets={w['id']:w for w in spec.get('known_remaining_work_packets',[])}
 for c in cs:
  linked=c.get('work_packet_ids',[])
  if c.get('remaining') and not linked:bad('orphan_remaining:'+c['id'])
  for w in linked:
   if w not in packets or c['id'] not in packets[w].get('condition_ids',[]):bad('work_link_mismatch:'+c['id'])
  if c.get('bounded_subcontract_complete'):
   if not c.get('bounded_domain'):bad('missing_bounded_domain:'+c['id'])
   available={t for e in c.get('evidence_refs',[]) if e in evidence for t in evidence[e].get('passing_test_ids',[])}
   if not c.get('independent_test_ids') or not set(c['independent_test_ids'])<=available:bad('missing_independent_case:'+c['id'])
 for w in packets.values():
  for cid in w.get('condition_ids',[]):
   target=next((c for c in cs if c['id']==cid),None)
   if target is None or w['id'] not in target.get('work_packet_ids',[]):bad('reverse_work_link_mismatch:'+w['id'])
 ts=spec.get('transitions',[])
 if {t.get('id') for t in ts}!={f'ACT-T{i:02}' for i in range(1,9)} or len(ts)!=8:bad('transition_set_mismatch')
 for t in ts:
  expected_links=spec.get('required_connectivity',{}).get(t['id'])
  if not expected_links or set(t.get('condition_ids',[]))!=set(expected_links) or not set(t.get('condition_ids',[]))<=expected:bad('transition_link_mismatch:'+t['id'])
  if not t.get('guard') or not t.get('effect'):bad('missing_transition_contract:'+t['id'])
 for key,e in evidence.items():
  p=root/e['file']
  if not p.is_file() or digest(p)!=e['sha256']:bad('evidence_report_drift:'+key);continue
  data=json.loads(p.read_text(encoding='utf8'));passing={z['id'] for z in data.get('results',[]) if z.get('status')=='pass'}
  if set(e.get('passing_test_ids',[]))!=passing:bad('evidence_test_mismatch:'+key)
  if e.get('fully_current'):
   for rel,h in data.get('input_hashes',{}).items():
    f=root/rel
    if not f.is_file() or digest(f)!=h:bad('stale_conformance_input:'+key+':'+rel)
 return sorted(set(errors))
def audit(root=ROOT):
 root=Path(root);spec=json.loads((root/REL).read_text(encoding='utf8'));errors=validate(spec,root)
 return {'status':'checks_passed' if not errors else 'not_passed','errors':errors,'results':[{'id':'ACTIVATION-MATRIX-INTEGRITY','status':'pass' if not errors else 'fail'}],'input_hashes':{REL:digest(root/REL),'tools/audit_common_activation_matrix.py':digest(Path(__file__))},'counts':spec['summary'],'semantic_complete':False,'meaning':'Exact finite review inventory and source/code/evidence links; not source universe coverage or new runtime conformance proof.'}
if __name__=='__main__':
 report=audit();(ROOT/'output/common-activation-matrix-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({'status':report['status'],'errors':report['errors']},ensure_ascii=False));raise SystemExit(bool(report['errors']))
