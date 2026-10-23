"""Finite scope-review integrity; not source-rule coverage or semantic proof."""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
REVIEWS='data/verification/common-source-reviews'
GRAPH='data/verification/rule-symbol-graph.json'
TARGETS={'source.authority','rules.applicability','rules.precedence'}
DOCUMENTS={f'ch{i:02}' for i in range(12)}|{'chHB-FINANCE','chHB-TERASTAL','chHB-WEATHER','chHB-ZMOVES','supp-blessings','supp-errata','supp-fantasy','supp-polygon'}
CATEGORIES={'root_authority_contract','common_extension_interface','scoped_domain_rule','content_instance','guidance_or_explanation','source_context','mixed'}
SPEC_NAMES=('root-authority-scope-review.json','root-authority-scope-core-followup.json','root-authority-scope-supplement-followup.json')
FALSE_FIELDS={'completion','whole_rule_certified','semantic_completeness_proved','whole_source_complete','whole_rulebook_semantics_complete','source_condition_denominator_complete','atomic_coverage_complete','atomic_semantic_completion','semantic_validation_complete','semantic_proof','whole_semantic_proof','whole_semantics_complete','visuals_complete'}
def load(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text_digest(t): return hashlib.sha256(t.encode()).hexdigest()
def _dict(v): return v if isinstance(v,dict) else {}
def _list(v): return v if isinstance(v,list) else []
def _text(v): return isinstance(v,str) and bool(v.strip())
def safe_file(root,value):
    if not isinstance(value,str): raise ValueError('non-string path')
    p=(root/value).resolve()
    if not p.is_relative_to(root) or not p.is_file(): raise ValueError('outside root or missing')
    return p

def validate(reports,root):
    """Return (errors, derived_inventory); never mutate reports or project."""
    root=Path(root).resolve();errors=[]
    summary=dict(document_count=0,selected_candidate_count=0,candidate_scope_records=0,
        declared_full_text_reread_documents=[],declared_targeted_context_documents=[],
        classification_counts={},read_declarations_independently_proven=False,
        source_condition_denominator_complete=False,whole_rulebook_semantics_complete=False,coverage_percent=None)
    def fail(code):errors.append(code)
    if not isinstance(reports,list) or not reports:return ['invalid_report_list'],summary
    try:
        paths=sorted((root/REVIEWS).glob('*.json'))
        if {p.stem for p in paths}!=DOCUMENTS:fail('live_document_inventory')
        reviews={p.relative_to(root).as_posix():load(p) for p in paths}
        symbols={n['id'] for n in load(root/GRAPH)['nodes']}
        source_lines={};selected={};by_review={}
        for rp,r in reviews.items():
            source=r['file'];source_lines[source]=safe_file(root,source).read_text(encoding='utf-8-sig').splitlines()
            if r.get('source_sha256')!=digest(root/source):fail('live_review_source_hash:'+rp)
            by_review[rp]=[]
            for c in r['clauses']:
                if TARGETS&set(c.get('symbol_refs',[])):
                    cid=c['id']
                    if cid in selected:fail('live_candidate_duplicate:'+cid)
                    selected[cid]=(rp,c);by_review[rp].append(cid)
    except (OSError,KeyError,TypeError,ValueError) as e:return errors+['invalid_live_inputs:'+type(e).__name__],summary
    summary.update(document_count=len(reviews),selected_candidate_count=len(selected))
    all_docs=[];all_ids=[];counts=Counter();anchor_checks=0
    def expected_anchor(block):
        f,span=block.rsplit(':',1);a,b=map(int,span.split('-'))
        if f not in source_lines or not 1<=a<=b<=len(source_lines[f]):raise ValueError('invalid block')
        text='\n'.join(source_lines[f][a-1:b])
        return dict(file=f,start=a,end=b,excerpt=text,excerpt_sha256=text_digest(text))
    def check_anchor(a,label,sources):
        nonlocal anchor_checks
        a=_dict(a);f=a.get('file');start=a.get('start');end=a.get('end')
        if not isinstance(f,str) or f not in sources or type(start)!=int or type(end)!=int:fail('invalid_anchor:'+label);return
        if not 1<=start<=end<=len(source_lines[f]):fail('anchor_range:'+label);return
        text='\n'.join(source_lines[f][start-1:end])
        if a.get('excerpt')!=text or a.get('excerpt_sha256')!=text_digest(text):fail('anchor_content:'+label)
        anchor_checks+=1
    def walk(v,label,sources):
        if isinstance(v,dict):
            if ('excerpt' in v or 'excerpt_sha256' in v) and ('file' in v or 'start' in v):check_anchor(v,label,sources)
            for k,t in v.items():
                if k in FALSE_FIELDS and t is not False:fail('unsupported_semantic_completion:'+label+'.'+k)
                if k=='coverage_percent' and t is not None:fail('unsupported_coverage_percent:'+label)
                if k=='root_axioms_added' and (type(t)!=int or t!=0):fail('unsupported_new_root_axioms:'+label)
                walk(t,label+'.'+k,sources)
        elif isinstance(v,list):
            for i,t in enumerate(v):walk(t,label+f'[{i}]',sources)
    for num,report in enumerate(reports):
        label=f'report{num}'
        if not isinstance(report,dict):fail('invalid_report:'+label);continue
        scope=_dict(report.get('scope'));docs=_list(scope.get('documents'))
        if not docs or any(not isinstance(d,str) or d not in DOCUMENTS for d in docs) or len(docs)!=len(set(map(str,docs))):fail('scope_documents:'+label)
        rps={f'{REVIEWS}/{d}.json' for d in docs if isinstance(d,str)}&reviews.keys()
        sources={reviews[p]['file'] for p in rps};expected_ids=[c for p in rps for c in by_review[p]]
        if scope.get('selection_symbols',scope.get('target_symbols'))!=sorted(TARGETS):fail('scope_selection_symbols:'+label)
        for k in ('source_condition_denominator_complete','whole_rulebook_semantics_complete'):
            if scope.get(k) is not False:fail('scope_required_incomplete:'+label+'.'+k)
        if set(_dict(report.get('classification_criteria')))!=CATEGORIES:fail('classification_enum:'+label)
        walk(report,label,sources)
        snaps=_list(report.get('source_and_review_snapshots'))
        if Counter(str(_dict(d).get('review_file')) for d in snaps)!=Counter(rps):fail('document_snapshot_partition:'+label)
        read_lines={};full_flags=[]
        for d in snaps:
            d=_dict(d);rp=d.get('review_file')
            if not isinstance(rp,str) or rp not in rps:continue
            f=reviews[rp]['file'];n=len(source_lines[f]);ch=Path(rp).stem;all_docs.append(ch)
            if d.get('source_file')!=f or d.get('source_line_count')!=n:fail('source_snapshot_identity:'+rp)
            for field,path in (('source_sha256',f),('review_sha256',rp)):
                if d.get(field)!=digest(root/path):fail('snapshot_hash:'+rp+':'+field)
            if 'candidate_ids' in d and Counter(map(str,_list(d['candidate_ids'])))!=Counter(by_review[rp]):fail('snapshot_candidate_set:'+rp)
            if 'indexed_candidate_count' in d and d['indexed_candidate_count']!=len(by_review[rp]):fail('snapshot_candidate_count:'+rp)
            seen=set()
            for span in _list(d.get('direct_source_read_ranges')):
                if not isinstance(span,list) or len(span)!=2 or any(type(x)!=int for x in span) or not 1<=span[0]<=span[1]<=n:fail('read_range:'+rp);continue
                seen.update(range(span[0],span[1]+1))
            read_lines[f]=seen
            full=d.get('whole_source_text_reread_this_turn',d.get('direct_source_text_read_complete'))
            if type(full)!=bool:fail('missing_read_scope_declaration:'+rp)
            if full is True and len(seen)!=n:fail('unsupported_full_text_read:'+rp)
            full_flags.append(full is True)
            summary['declared_full_text_reread_documents' if full is True else 'declared_targeted_context_documents'].append(ch)
        for k in ('all_source_text_reread','direct_text_read_complete'):
            if k in scope and scope[k] is not all(full_flags):fail('aggregate_read_scope:'+label+':'+k)
        ds=_list(report.get('candidate_dispositions'));ids=[str(_dict(d).get('candidate_id')) for d in ds]
        if Counter(ids)!=Counter(expected_ids):fail('candidate_partition:'+label)
        all_ids.extend(ids)
        if 'candidate_count' in scope and scope['candidate_count']!=len(expected_ids):fail('declared_candidate_count:'+label)
        local_counts=Counter()
        for d in ds:
            d=_dict(d);cid=d.get('candidate_id')
            if not isinstance(cid,str) or cid not in selected:fail('unknown_candidate:'+str(cid));continue
            rp,c=selected[cid]
            if d.get('review_file')!=rp or rp not in rps:fail('candidate_document:'+cid)
            if d.get('current_candidate',d.get('original_candidate'))!=c:fail('candidate_snapshot_content:'+cid)
            if _dict(d.get('original_candidate')).get('id')!=cid:fail('missing_original_candidate_history:'+cid)
            try:anchors=[expected_anchor(b) for b in c['block_ids']]
            except (ValueError,KeyError,TypeError):fail('invalid_live_block:'+cid);continue
            if d.get('anchors')!=anchors:fail('candidate_anchor_relation:'+cid)
            for a in anchors:
                if not set(range(a['start'],a['end']+1))<=read_lines.get(a['file'],set()):fail('candidate_outside_declared_read_scope:'+cid)
            cat=d.get('category')
            if not isinstance(cat,str) or cat not in CATEGORIES:fail('candidate_category:'+cid)
            else:counts[cat]+=1;local_counts[cat]+=1
            if not _text(d.get('reason')) or not _text(d.get('review_method')):fail('candidate_review_evidence:'+cid)
            if d.get('atomic_coverage_complete') is not False:fail('candidate_completion:'+cid)
            parent=_dict(d.get('parent_relation'));refs=d.get('parent_symbols',[parent.get('symbol')])
            if not isinstance(refs,list) or not refs or any(not isinstance(x,str) or x not in symbols for x in refs):fail('candidate_parent_symbol:'+cid)
            guards=d.get('scope_guard',parent.get('scope_guard'));exceptions=d.get('exceptions_preserved',parent.get('exceptions_preserved'))
            if not isinstance(guards,list) or any(x not in guards for x in c.get('conditions',[])):fail('candidate_condition_loss:'+cid)
            if not isinstance(exceptions,list) or any(x not in exceptions for x in c.get('exceptions',[])):fail('candidate_exception_loss:'+cid)
        v=_dict(report.get('validation'))
        for k,expected in (('candidate_count',len(expected_ids)),('classification_counts',dict(local_counts))):
            if k in v and v[k]!=expected:fail('validation_summary:'+label+':'+k)
        den=_dict(scope.get('denominator'))
        for k,expected in (('all_review_index_candidates',len(selected)),('this_review_candidates',len(expected_ids)),('outside_this_review_not_dispositioned',len(selected)-len(expected_ids)),('by_category',dict(local_counts))):
            if k in den and den[k]!=expected:fail('denominator_summary:'+label+':'+k)
        if 'by_chapter' in den and den['by_chapter']!={d:len(by_review.get(f'{REVIEWS}/{d}.json',[])) for d in docs}:fail('denominator_by_chapter:'+label)
        # Current ledgers are never silently accepted as historical snapshots.
        hashed=list(_dict(report.get('input_hashes')).items())
        index=_dict(report.get('authority_index_snapshot'))
        if 'authority_index_snapshot' in report and not {'reviews','review_hashes'} & index.keys():
            fail('index_snapshot_schema:'+label)
        if 'reviews' in index:
            entries=_list(index['reviews'])
            if not isinstance(index['reviews'],list) or Counter(str(_dict(x).get('file')) for x in entries)!=Counter(reviews.keys()):
                fail('index_review_partition:'+label)
            hashed += [(x.get('file'),x.get('sha256')) for x in entries if isinstance(x,dict)]
        if 'review_hashes' in index:
            ledger=index['review_hashes']
            if not isinstance(ledger,dict) or set(ledger)!=set(reviews):
                fail('index_review_partition:'+label)
            hashed += list(_dict(ledger).items())
        for key,expected in (('review_count',len(reviews)),('indexed_candidate_count',len(selected))):
            if key in index and (type(index[key])!=int or index[key]!=expected):
                fail('index_snapshot_count:'+label+':'+key)
        hashed += [(x.get('file'),x.get('sha256')) for x in _list(report.get('supporting_snapshots')) if isinstance(x,dict)]
        for path,expected in hashed:
            try:actual=digest(safe_file(root,path))
            except (ValueError,OSError):fail('hash_ledger_path:'+str(path));continue
            if actual!=expected:fail('hash_ledger_stale:'+path)
        index=_dict(report.get('authority_index_snapshot'))
        if 'candidate_ids' in index and index['candidate_ids']!=sorted(selected):fail('global_candidate_index_snapshot:'+label)
    if Counter(all_docs)!=Counter(DOCUMENTS):fail('combined_document_partition')
    if Counter(all_ids)!=Counter(selected.keys()):fail('combined_candidate_partition')
    summary.update(candidate_scope_records=len(all_ids),classification_counts=dict(sorted(counts.items())),source_anchor_checks=anchor_checks)
    for k in ('declared_full_text_reread_documents','declared_targeted_context_documents'):summary[k]=sorted(summary[k])
    return errors,summary

def build_report(reports,root,paths=()):
    errors,summary=validate(reports,root);root=Path(root).resolve()
    inputs={GRAPH:digest(root/GRAPH),'tools/audit_root_authority_scope_inventory.py':digest(__file__)}
    for p in sorted((root/REVIEWS).glob('*.json')):
        inputs[p.relative_to(root).as_posix()]=digest(p)
        source=load(p)['file'];inputs[source]=digest(safe_file(root,source))
    for report in reports:
        declared=list(_dict(report.get('input_hashes')))
        declared += [d.get('file') for d in _list(report.get('supporting_snapshots')) if isinstance(d,dict)]
        for key in declared:
            try: inputs[key]=digest(safe_file(root,key))
            except (ValueError,OSError): pass  # validate already reports missing/unsafe dependencies
    for p in paths:
        p=Path(p);inputs['data/verification/'+p.name]=digest(p)
    return dict(generated_at=datetime.now(timezone.utc).isoformat(),status='fail' if errors else 'draft_integrity_pass',
        errors=errors,results=[dict(id='combined_scope_inventory_integrity',status='fail' if errors else 'pass')],
        inventory=summary,input_hashes=inputs,whole_rule_certified=False,semantic_completeness_proved=False,coverage_percent=None,
        limitation='Finite three-symbol candidate partition and provenance only. Read ranges are reviewer declarations, not independent reading evidence. No source-clause denominator, meaning proof, or full rulebook coverage is established.')
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--spec-dir',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();directory=a.spec_dir or a.root/'data/verification';paths=[directory/n for n in SPEC_NAMES]
    report=build_report([load(x) for x in paths],a.root,paths)
    output=a.output or a.root/'output/whole-rulebook-audit/root-authority-scope-inventory-audit.json'
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['status'],errors=report['errors'],inventory=report['inventory']),ensure_ascii=False))
    return bool(report['errors'])
if __name__=='__main__':raise SystemExit(main())

