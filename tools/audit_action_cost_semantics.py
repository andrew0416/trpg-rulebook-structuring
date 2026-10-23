"""Validate source provenance and bounded action-model links, not semantic closure."""
import ast,hashlib,json
from pathlib import Path
from functools import lru_cache
ROOT=Path(__file__).resolve().parents[1]
SPEC='data/verification/action-cost-semantics.json'
def sha(data):return hashlib.sha256(data).hexdigest()
@lru_cache(maxsize=8)
def pdf_page(path,digest,index):
    from pypdf import PdfReader
    return PdfReader(path).pages[index].extract_text()
def validate(spec,root):
    errors=[]
    if spec.get('whole_rule_certified') is not False or spec.get('semantic_completeness_proved') is not False:errors.append('unsupported_action_closure')
    anchors=spec.get('source_anchors',{})
    expected={'MD-DEFAULT','MD-DOWNGRADE','MD-POKEMON','MD-FULL','MD-HELD-DROP','MD-DROP-SPECIFIC','PDF-DOWNGRADE','PDF-POKEMON','PDF-HELD-DROP'}
    if set(anchors)!=expected:errors.append('action_anchor_set_mismatch')
    for key,a in anchors.items():
        try:
            p=root/a['file']
            if not p.resolve().is_relative_to(root.resolve()) or not p.is_file():raise ValueError('path')
            digest=sha(p.read_bytes())
            if digest!=a['file_sha256']:raise ValueError('file_hash')
            excerpt=a['excerpt']
            if not excerpt or sha(excerpt.encode())!=a['excerpt_sha256']:raise ValueError('excerpt_hash')
            if a['kind']=='markdown':
                lines=p.read_text(encoding='utf-8').splitlines();start,end=a['start'],a['end']
                if type(start) is not int or type(end) is not int or not 1<=start<=end<=len(lines) or '\n'.join(lines[start-1:end])!=excerpt:raise ValueError('range')
            elif a['kind']=='pdf':
                index=a['page_index']
                if type(index) is not int or index<0:raise ValueError('page')
                text=pdf_page(str(p),digest,index)
                if sha(text.encode())!=a['page_text_sha256'] or excerpt not in text:raise ValueError('page_excerpt')
            else:raise ValueError('kind')
        except (KeyError,ValueError,TypeError,IndexError,OSError):errors.append('stale_action_anchor:'+key)
    clauses=spec.get('clauses',[])
    if [c.get('id') for c in clauses]!=['ACTION-COST-%02d'%i for i in range(1,6)]:errors.append('action_clause_set_mismatch')
    tree=ast.parse((root/'tools/test_movement_action_budget.py').read_text(encoding='utf-8-sig'))
    tests={n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
    for c in clauses:
        if not c.get('formal') or not c.get('anchors') or not set(c['anchors'])<=set(anchors):errors.append('invalid_action_clause_sources:'+str(c.get('id')))
        if not c.get('tests') or not set(c['tests'])<=tests:errors.append('invalid_action_test_links:'+str(c.get('id')))
    conflicts=spec.get('unresolved_source_conflicts',[])
    if len(conflicts)!=1 or conflicts[0].get('id')!='ACTION-DROP-01' or conflicts[0].get('status')!='unresolved' or set(conflicts[0].get('anchors',[]))!={'MD-POKEMON','MD-HELD-DROP','MD-DROP-SPECIFIC','PDF-POKEMON','PDF-HELD-DROP'}:errors.append('lost_action_drop_conflict')
    if not spec.get('runtime_contract',{}).get('remaining'):errors.append('unsupported_action_runtime_closure')
    return errors
if __name__=='__main__':
    spec=json.loads((ROOT/SPEC).read_text(encoding='utf-8'));errors=validate(spec,ROOT)
    paths=[SPEC,'tools/audit_action_cost_semantics.py','tools/test_movement_action_budget.py']+spec['runtime_contract']['implementation']+sorted({a['file'] for a in spec['source_anchors'].values()})
    report=dict(status='integrity_pass_runtime_partial' if not errors else 'invalid',errors=errors,clauses=len(spec['clauses']),source_anchors=len(spec['source_anchors']),whole_rule_certified=False,remaining=spec['runtime_contract']['remaining'],input_hashes={p:sha((ROOT/p).read_bytes()) for p in paths})
    (ROOT/'output/whole-rulebook-audit/action-cost-semantics-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('remaining','input_hashes')},ensure_ascii=False));raise SystemExit(bool(errors))
