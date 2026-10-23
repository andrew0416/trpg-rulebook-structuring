"""Integrity of a manual scope review. A pass does not prove rule semantics or coverage."""
from __future__ import annotations
import argparse, collections, hashlib, json
from pathlib import Path
from datetime import datetime, timezone

CHAPTERS=('ch00','ch01','ch06','ch10','ch11')
TARGETS={'source.authority','rules.applicability','rules.precedence'}
REVIEWS='data/verification/common-source-reviews'
SPEC='data/verification/root-authority-scope-review.json'
GRAPH='data/verification/rule-symbol-graph.json'
ATOMS='data/verification/root-authority-atoms.json'
CATEGORIES={'root_authority_contract','common_extension_interface','scoped_domain_rule','content_instance','guidance_or_explanation','source_context','mixed'}
ROOT=Path(__file__).resolve().parents[1]
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def _list(v): return v if isinstance(v,list) else []
def _dict(v): return v if isinstance(v,dict) else {}
def _nonempty(v): return isinstance(v,str) and bool(v.strip())
def _safe(root, value):
    if not isinstance(value,str): return None
    p=(root/value).resolve()
    return p if p.is_relative_to(root) else None
def _anchor(root,block):
    f,r=block.rsplit(':',1);a,b=map(int,r.split('-'))
    lines=(root/f).read_text(encoding='utf-8-sig').splitlines()
    text='\n'.join(lines[a-1:b])
    return dict(file=f,start=a,end=b,excerpt=text,excerpt_sha256=hashlib.sha256(text.encode()).hexdigest())
def _live(root):
    reviews={p.relative_to(root).as_posix():load(p) for p in sorted((root/REVIEWS).glob('*.json'))}
    selected={ch:reviews[f'{REVIEWS}/{ch}.json'] for ch in CHAPTERS}
    index={c['id']:(ch,c) for ch,r in selected.items() for c in r['clauses'] if TARGETS&set(c.get('symbol_refs',[]))}
    full=[c['id'] for r in reviews.values() for c in r['clauses'] if TARGETS&set(c.get('symbol_refs',[]))]
    return reviews,selected,index,full

def validate(spec,root)->list[str]:
    root=Path(root).resolve(); errors=[]
    def fail(code): errors.append(code)
    if not isinstance(spec,dict): return ['invalid_scope_spec']
    try:
        reviews,selected,index,full=_live(root)
        symbols={n['id'] for n in load(root/GRAPH)['nodes']}
        atomids={a['id'] for a in load(root/ATOMS)['atoms']}
    except (OSError,ValueError,KeyError,TypeError) as e: return ['invalid_scope_inputs:'+type(e).__name__]
    if len(reviews)!=20: fail('scope_review_inventory_count')
    if len(full)!=len(set(full)): fail('scope_live_candidate_duplicate')
    scope=_dict(spec.get('scope'))
    if scope.get('documents')!=list(CHAPTERS): fail('scope_documents')
    if scope.get('target_symbols')!=sorted(TARGETS): fail('scope_target_symbols')
    if spec.get('completion') is not False: fail('unsupported_scope_completion')
    for key in ('source_condition_denominator_complete','whole_rulebook_semantics_complete'):
        if scope.get(key) is not False: fail('unsupported_scope_completion:'+key)
    if scope.get('direct_text_read_complete') is not True or scope.get('all_indexed_candidates_individually_reviewed') is not True: fail('scope_read_status')
    # These are prohibited certification fields even if added outside the schema.
    prohibited={'whole_rule_certified','semantic_completeness_proved','whole_source_complete','whole_rulebook_semantics_complete',
                'source_condition_denominator_complete','atomic_coverage_complete','atomic_semantic_completion',
                'semantic_validation_complete','semantic_proof','visuals_complete'}
    def visit(v,path='spec'):
        if isinstance(v,dict):
            for k,t in v.items():
                if k in prohibited and t is not False: fail('unsupported_scope_certification:'+path+'.'+k)
                visit(t,path+'.'+k)
        elif isinstance(v,list):
            for i,t in enumerate(v): visit(t,path+f'[{i}]')
    visit(spec)
    sourcefiles={v['file'] for v in selected.values()}
    source_lines={f:(root/f).read_text(encoding='utf-8-sig').splitlines() for f in sourcefiles}
    anchor_cache={}
    def parent_anchor(block):
        if block not in anchor_cache:
            f,span=block.rsplit(':',1);a,b=map(int,span.split('-'))
            text='\n'.join(source_lines[f][a-1:b])
            anchor_cache[block]=dict(file=f,start=a,end=b,excerpt=text,excerpt_sha256=hashlib.sha256(text.encode()).hexdigest())
        return anchor_cache[block]
    def check_anchor(a,label):
        if not isinstance(a,dict): fail('invalid_scope_anchor:'+label);return
        f=a.get('file');start=a.get('start');end=a.get('end')
        if not isinstance(f,str) or f not in sourcefiles or type(start)!=int or type(end)!=int:
            fail('invalid_scope_anchor:'+label);return
        lines=source_lines[f]
        if not 1<=start<=end<=len(lines): fail('invalid_scope_anchor_range:'+label);return
        text='\n'.join(lines[start-1:end])
        if a.get('excerpt')!=text or a.get('excerpt_sha256')!=hashlib.sha256(text.encode()).hexdigest(): fail('scope_anchor_mismatch:'+label)
    def walk_anchors(v,path='spec'):
        if isinstance(v,dict):
            if {'excerpt','start','end'}&v.keys() and ('file' in v or 'excerpt_sha256' in v):check_anchor(v,path)
            for k,t in v.items():walk_anchors(t,path+'.'+k)
        elif isinstance(v,list):
            for i,t in enumerate(v):walk_anchors(t,path+f'[{i}]')
    walk_anchors(spec)
    docs=_list(spec.get('source_and_review_snapshots'))
    docnames=[_dict(d).get('chapter') for d in docs]
    if collections.Counter(str(x) for x in docnames)!=collections.Counter(CHAPTERS):fail('scope_source_snapshot_set')
    for d in docs:
        d=_dict(d);ch=d.get('chapter')
        if not isinstance(ch,str) or ch not in selected:continue
        f=selected[ch]['file'];rp=f'{REVIEWS}/{ch}.json'
        if d.get('source_file')!=f or d.get('review_file')!=rp:fail('scope_snapshot_identity:'+ch)
        if d.get('source_sha256')!=digest(root/f):fail('scope_source_hash:'+ch)
        if d.get('review_sha256')!=digest(root/rp):fail('scope_review_hash:'+ch)
        count=len((root/f).read_text(encoding='utf-8-sig').splitlines())
        if d.get('source_line_count')!=count or d.get('direct_source_read_ranges')!=[[1,count]]:fail('scope_read_range:'+ch)
        if d.get('direct_source_text_read_complete') is not True:fail('scope_read_incomplete:'+ch)
        if d.get('visuals_complete') is not False or d.get('atomic_semantic_completion') is not False:fail('unsupported_scope_source_completion:'+ch)
        if d.get('indexed_candidate_count')!=sum(c[0]==ch for c in index.values()):fail('scope_document_count:'+ch)
    snap=_dict(spec.get('authority_index_snapshot'))
    rs=_list(snap.get('reviews'))
    paths=[_dict(v).get('file') for v in rs]
    if collections.Counter(str(x) for x in paths)!=collections.Counter(list(reviews)):fail('scope_review_snapshot_set')
    for v in rs:
        v=_dict(v);p=v.get('file')
        if isinstance(p,str) and p in reviews and v.get('sha256')!=digest(root/p):fail('scope_review_snapshot_hash:'+p)
    if snap.get('candidate_ids')!=sorted(full):fail('scope_full_index_snapshot')
    ss=_list(spec.get('supporting_snapshots'))
    if collections.Counter(str(_dict(v).get('file')) for v in ss)!=collections.Counter([GRAPH,ATOMS]):fail('scope_support_snapshot_set')
    for v in ss:
        v=_dict(v);p=v.get('file')
        if isinstance(p,str) and p in (GRAPH,ATOMS) and v.get('sha256')!=digest(root/p):fail('scope_support_hash:'+p)
    ds=_list(spec.get('candidate_dispositions'))
    ids=[_dict(d).get('candidate_id') for d in ds]
    if collections.Counter(str(i) for i in ids)!=collections.Counter(list(index)):fail('scope_candidate_set')
    for d in ds:
        d=_dict(d);cid=d.get('candidate_id')
        if not isinstance(cid,str) or cid not in index:continue
        ch,c=index[cid]
        if d.get('original_candidate')!=c:fail('scope_original_candidate_mismatch:'+cid)
        if d.get('review_file')!=f'{REVIEWS}/{ch}.json':fail('scope_candidate_review:'+cid)
        # Exact parent blocks protect against unrelated but valid excerpts from the same file.
        expected=[parent_anchor(b) for b in c['block_ids']]
        if d.get('anchors')!=expected:fail('scope_candidate_anchor_relation:'+cid)
        if not isinstance(d.get('category'),str) or d.get('category') not in CATEGORIES:fail('scope_category:'+cid)
        if d.get('reviewed') is not True or not _nonempty(d.get('review_method')) or not _nonempty(d.get('reason')):fail('scope_unreviewed_candidate:'+cid)
        parent=_dict(d.get('parent_relation'))
        if not isinstance(parent.get('symbol'),str) or parent.get('symbol') not in symbols:fail('scope_parent_symbol:'+cid)
        if not _nonempty(parent.get('concept')) or not _nonempty(parent.get('kind')):fail('scope_parent_relation:'+cid)
        if parent.get('scope_guard')!=c.get('conditions',[]) or parent.get('exceptions_preserved')!=c.get('exceptions',[]):fail('scope_parent_conditions:'+cid)
        refs=d.get('related_existing_atom_ids')
        if not isinstance(refs,list) or any(not isinstance(a,str) or a not in atomids for a in refs):fail('scope_atom_reference:'+cid)
        if not isinstance(d.get('root_denominator_disposition'),str) or d.get('root_denominator_disposition') not in ('root_clause_split_required','root_contract_candidate','retain_under_parent_not_an_additional_root_axiom'):fail('scope_root_disposition:'+cid)
        if d.get('atomic_coverage_complete') is not False:fail('unsupported_scope_candidate_completion:'+cid)
    counts=dict(collections.Counter(d['category'] for d in ds if isinstance(d,dict) and isinstance(d.get('category'),str)))
    den=_dict(scope.get('denominator'))
    expectedden=dict(all_review_index_candidates=len(full),this_review_candidates=len(index),outside_this_review_not_dispositioned=len(full)-len(index),
        by_chapter={ch:sum(v[0]==ch for v in index.values()) for ch in CHAPTERS},by_category=counts)
    if den!=expectedden:fail('scope_denominator_mismatch')


    gaps=_list(spec.get('newly_found_gaps')); gapmap={}
    for g in gaps:
        g=_dict(g);gid=g.get('id')
        if not _nonempty(gid) or gid in gapmap:fail('scope_gap_id');continue
        gapmap[gid]=g
        if not isinstance(g.get('symbol'),str) or g.get('symbol') not in symbols:fail('scope_gap_symbol:'+gid)
        if g.get('status')!='draft' or g.get('atomic_coverage_complete') is not False:fail('scope_gap_status:'+gid)
        if not _nonempty(g.get('statement')) or not _nonempty(g.get('reason')):fail('scope_gap_meaning:'+gid)
        a=_dict(g.get('anchor'));check_anchor(a,gid)
        f=a.get('file');start=a.get('start');end=a.get('end')
        if isinstance(f,str) and f in sourcefiles and type(start)==int and type(end)==int:
            expected=[]
            for r in selected.values():
                if r['file']!=f:continue
                for c in r['clauses']:
                    overlaps=[]
                    for b in c['block_ids']:
                        ba=parent_anchor(b)
                        if ba['file']==f and max(start,ba['start'])<=min(end,ba['end']):overlaps.append(b)
                    if overlaps:expected.append(dict(candidate_id=c['id'],symbol_refs=c.get('symbol_refs',[]),overlapping_blocks=overlaps,in_three_symbol_index=bool(TARGETS&set(c.get('symbol_refs',[])))))
            if g.get('existing_review_candidates')!=expected:fail('scope_gap_candidate_relation:'+gid)
    proposals=_list(spec.get('suggested_atomic_clause_splits'));pids=set()
    for p in proposals:
        p=_dict(p);pid=p.get('id')
        if not _nonempty(pid) or pid in pids:fail('scope_proposal_id');continue
        pids.add(pid)
        if p.get('status')!='draft' or p.get('semantic_validation_complete') is not False:fail('scope_proposal_status:'+pid)
        if not _nonempty(p.get('title')) or not _nonempty(p.get('boundary')):fail('scope_proposal_boundary:'+pid)
        statements=p.get('suggested_atomic_statements')
        if not isinstance(statements,list) or not statements or any(not _nonempty(s) for s in statements):fail('scope_proposal_statements:'+pid)
        ars=p.get('existing_atom_ids')
        if not isinstance(ars,list) or any(not isinstance(a,str) or a not in atomids for a in ars):fail('scope_proposal_atom_reference:'+pid)
        gs=p.get('source_gap_ids');cs=p.get('source_candidate_ids')
        if not isinstance(gs,list) or any(not isinstance(g,str) or g not in gapmap for g in gs):fail('scope_proposal_gap_reference:'+pid);continue
        if not isinstance(cs,list) or any(not isinstance(c,str) or c not in index for c in cs):fail('scope_proposal_candidate_reference:'+pid);continue
        expected=[gapmap[g]['anchor'] for g in gs]
        expected.extend(parent_anchor(b) for c in cs for b in index[c][1]['block_ids'])
        if any(not isinstance(a,dict) or not {'file','start','end'}<=set(a) for a in expected):fail('scope_proposal_bad_anchor:'+pid);continue
        expected=list({(a['file'],a['start'],a['end']):a for a in expected}.values())
        if not expected or p.get('anchors')!=expected:fail('scope_proposal_anchor_relation:'+pid)
    for c in _list(spec.get('candidate_clarifications')):
        c=_dict(c)
        if not isinstance(c.get('candidate_id'),str) or c.get('candidate_id') not in index:fail('scope_clarification_candidate')
        if not _list(c.get('anchors')) or not _nonempty(c.get('suggestion')) or not _nonempty(c.get('reason')):fail('scope_clarification_required_fields')
    validation=_dict(spec.get('validation'))
    if validation.get('semantic_proof') is not False:fail('unsupported_scope_validation_proof')
    if not _list(spec.get('uncertainties')):fail('scope_missing_uncertainties')
    return errors

def input_hashes(spec,root,spec_path=None,extra_tools=()):
    root=Path(root).resolve(); result={}
    files=[GRAPH,ATOMS]+[p.relative_to(root).as_posix() for p in sorted((root/REVIEWS).glob('*.json'))]
    for ch in CHAPTERS:
        p=root/REVIEWS/f'{ch}.json'
        if p.exists():files.append(load(p)['file'])
    for f in files:
        path=_safe(root,f)
        if path and path.is_file():result[f]=digest(path)
    if spec_path:
        path=Path(spec_path).resolve()
        if path.exists():result[SPEC]=digest(path)
    elif (root/SPEC).exists():result[SPEC]=digest(root/SPEC)
    result['tools/audit_root_authority_scope.py']=digest(Path(__file__))
    for key,path in extra_tools:
        if Path(path).is_file():result[key]=digest(path)
    return result

def build_report(spec,root,spec_path=None):
    errors=validate(spec,root)
    return dict(generated_at=datetime.now(timezone.utc).isoformat(),status='fail' if errors else 'draft_integrity_pass',errors=errors,
        whole_rule_certified=False,semantic_completeness_proved=False,coverage_percent=None,
        limitation='Integrity of manual scope annotations and provenance only; not semantic proof or rulebook coverage.',
        candidate_records=len(_list(_dict(spec).get('candidate_dispositions'))),
        input_hashes=input_hashes(spec,root,spec_path))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--spec',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    root=a.root.resolve();sp=a.spec.resolve() if a.spec else root/SPEC
    spec=load(sp);report=build_report(spec,root,sp)
    output=a.output or root/'output/whole-rulebook-audit/root-authority-scope-audit.json'
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['status'],errors=report['errors'],candidate_records=report['candidate_records']),ensure_ascii=False))
    return bool(report['errors'])
if __name__=='__main__':raise SystemExit(main())

