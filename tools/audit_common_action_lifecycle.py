"""Provenance/link gate for a PARTIAL common action specification, not entailment proof."""
import ast,hashlib,json
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC='data/verification/common-action-lifecycle-semantics.json'
BINDINGS='data/verification/common-action-lifecycle-runtime-bindings.json'

def sha(data):return hashlib.sha256(data).hexdigest()
@lru_cache(maxsize=4)
def reader(path,digest):
    from pypdf import PdfReader
    return PdfReader(path)
@lru_cache(maxsize=64)
def pdf_page(path,digest,index):return reader(path,digest).pages[index].extract_text()
def safe_file(root,name):
    p=(root/name).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():raise ValueError('path')
    return p

def validate(spec,root,bindings=None):
    errors=[]
    for flag in ('whole_rulebook_complete','whole_rule_certified','semantic_completeness_proved','runtime_conformance_proved','atomic_decomposition_complete'):
        if spec.get(flag) is not False:errors.append('unsupported_action_lifecycle_closure:'+flag)
    anchors=spec.get('source_anchors',{})
    if len(anchors)!=111:errors.append('action_lifecycle_anchor_count')
    files={}
    for key,a in anchors.items():
        try:
            p=safe_file(root,a['file'])
            if a['file'] not in files:files[a['file']]=sha(p.read_bytes())
            digest=files[a['file']]
            if digest!=a['file_sha256']:raise ValueError('file_hash')
            excerpt=a['excerpt']
            if not excerpt or sha(excerpt.encode())!=a['excerpt_sha256']:raise ValueError('excerpt_hash')
            if a['kind']=='markdown':
                lines=p.read_text(encoding='utf8').splitlines();start,end=a['start'],a['end']
                if type(start) is not int or type(end) is not int or not 1<=start<=end<=len(lines) or '\n'.join(lines[start-1:end])!=excerpt:raise ValueError('range')
            elif a['kind']=='pdf':
                index=a['page_index']
                if type(index) is not int or index<0:raise ValueError('page')
                text=pdf_page(str(p),digest,index)
                if sha(text.encode())!=a['page_text_sha256'] or excerpt not in text:raise ValueError('page_excerpt')
            else:raise ValueError('kind')
        except (KeyError,ValueError,TypeError,IndexError,OSError):errors.append('stale_action_lifecycle_anchor:'+key)
    for row in spec.get('supporting_artifacts',[]):
        name=row.get('project_file',row.get('suggested_project_file',''))
        try:
            if sha(safe_file(root,name).read_bytes())!=row['sha256']:raise ValueError('hash')
        except (ValueError,OSError,KeyError):errors.append('stale_action_lifecycle_support:'+name)
    clauses=spec.get('clauses',[])
    expected=[f'COMMON-ACTION-{i:03d}' for i in range(1,24)]
    if [c.get('id') for c in clauses]!=expected:errors.append('action_lifecycle_clause_set')
    graph=json.loads((root/'data/verification/rule-symbol-graph.json').read_text(encoding='utf8'))
    symbols={s['id'] for s in graph['nodes']}
    for c in clauses:
        if c.get('semantic_closure') is not False or c.get('implementation_verified') is not False:errors.append('unsupported_action_clause_closure:'+str(c.get('id')))
        if not c.get('formal') or not c.get('source_anchor_ids') or not set(c['source_anchor_ids'])<=set(anchors):errors.append('invalid_action_lifecycle_sources:'+str(c.get('id')))
        if not c.get('symbol_refs') or not set(c['symbol_refs'])<=symbols:errors.append('invalid_action_lifecycle_symbols:'+str(c.get('id')))
    quotas=spec.get('quotas',{})
    if any(quotas.get('ordinary',{}).get(k)!=1 for k in ('standard','shift','swift')) or quotas.get('aoo',{}).get('max_per_round')!=1 or quotas.get('triggered_activation',{}).get('max_per_trigger_instance')!=1:errors.append('changed_source_action_quota')
    for k,row in quotas.items():
        if isinstance(row,dict) and (not row.get('source_anchor_ids') or not set(row['source_anchor_ids'])<=set(anchors)):errors.append('unlinked_action_quota:'+k)
    if not spec.get('unresolved') or not spec.get('remaining'):errors.append('lost_action_lifecycle_remaining')
    if bindings is None:bindings=json.loads((root/BINDINGS).read_text(encoding='utf8'))
    if bindings.get('whole_rule_certified') is not False or bindings.get('semantic_completeness_proved') is not False or not bindings.get('remaining'):errors.append('unsupported_action_bindings_closure')
    tree=ast.parse((root/bindings['test_script']).read_text(encoding='utf8'))
    tests={n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
    if [b.get('clause_id') for b in bindings.get('bindings',[])]!=expected:errors.append('action_lifecycle_binding_set')
    for b in bindings.get('bindings',[]):
        if b.get('whole_clause_verified') is not False:errors.append('unsupported_action_binding_closure:'+str(b.get('clause_id')))
        if not set(b.get('tests',[]))<=tests:errors.append('unknown_action_lifecycle_test:'+str(b.get('clause_id')))
        if b.get('status')=='partial_component_test_links' and not b.get('tests'):errors.append('missing_action_lifecycle_tests:'+str(b.get('clause_id')))
    for name in bindings.get('implementation',[]):
        try:safe_file(root,name)
        except (ValueError,OSError):errors.append('missing_action_implementation:'+name)
    return errors

def input_files(spec,bindings):
    return sorted(set([SPEC,BINDINGS,'tools/audit_common_action_lifecycle.py',bindings['test_script']]+bindings['implementation']+[a['file'] for a in spec['source_anchors'].values()]+[a.get('project_file',a.get('suggested_project_file')) for a in spec['supporting_artifacts']]))
if __name__=='__main__':
    spec=json.loads((ROOT/SPEC).read_text(encoding='utf8'));bindings=json.loads((ROOT/BINDINGS).read_text(encoding='utf8'));errors=validate(spec,ROOT,bindings)
    report=dict(status='integrity_pass_runtime_partial' if not errors else 'invalid',errors=errors,source_anchor_count=len(spec['source_anchors']),draft_clause_count=len(spec['clauses']),fully_verified_clauses=0,whole_rule_certified=False,remaining=bindings['remaining'],input_hashes={f:sha((ROOT/f).read_bytes()) for f in input_files(spec,bindings)})
    (ROOT/'output/whole-rulebook-audit/common-action-lifecycle-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('remaining','input_hashes')},ensure_ascii=False));raise SystemExit(bool(errors))
