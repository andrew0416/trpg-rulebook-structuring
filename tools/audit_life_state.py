"""Life-state source and evidence integrity. This is not whole-rule closure."""
import ast,hashlib,json
from pathlib import Path
from audit_world_state_semantics import validate_reviews
ROOT=Path(__file__).resolve().parents[1]
SPEC='data/verification/life-state-semantics.json'

def validate(spec,root):
    errors=[]
    if any(spec.get('certification',{}).values()):errors.append('unsupported_life_certification')
    clauses=spec.get('clauses',[])
    if len(clauses)!=len({c['id'] for c in clauses}) or not clauses:errors.append('invalid_life_clauses')
    reviews=[dict(id=c['id'],finding=c['formal'],evidence=[a for a in c['sources'] if a['kind']=='markdown']) for c in clauses]
    errors += validate_reviews({'interpretation_reviews':reviews},root)
    readers={}
    for c in clauses:
        for anchor in c['sources']:
            if anchor['kind']=='markdown':continue
            path=root/anchor['file']
            if anchor['kind']!='pdf_text' or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
                errors.append('invalid_life_pdf:'+c['id']);continue
            from pypdf import PdfReader
            if path not in readers:readers[path]=PdfReader(path)
            page=readers[path].pages[anchor['page_index']].extract_text()
            excerpt=anchor['excerpt']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=anchor['file_sha256'] or excerpt not in page or hashlib.sha256(excerpt.encode()).hexdigest()!=anchor['excerpt_sha256']:
                errors.append('stale_life_pdf:'+c['id'])
    tree=ast.parse((root/'tools/test_life_state.py').read_text(encoding='utf-8-sig'))
    ids={'LIFE-'+n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)}
    for c in clauses:
        if not c.get('independent_proof_obligations'):errors.append('missing_obligations:'+c['id'])
        if not c.get('partial_tests') or not set(c['partial_tests'])<=ids:errors.append('missing_life_tests:'+c['id'])
    if not spec.get('runtime_contract',{}).get('remaining'):errors.append('unsupported_runtime_closure')
    return errors

if __name__=='__main__':
    spec=json.loads((ROOT/SPEC).read_text(encoding='utf-8'));errors=validate(spec,ROOT)
    paths=[SPEC,'tools/audit_life_state.py','tools/test_life_state.py','tools/audit_world_state_semantics.py']+spec['runtime_contract']['implementation']+sorted({s['file'] for c in spec['clauses'] for s in c['sources']})
    result=dict(status='integrity_pass_runtime_partial' if not errors else 'invalid',errors=errors,clauses=len(spec['clauses']),proof_obligations=sum(len(c['independent_proof_obligations']) for c in spec['clauses']),whole_rule_certified=False,remaining=spec['runtime_contract']['remaining'],input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/whole-rulebook-audit/life-state-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('remaining','input_hashes')},ensure_ascii=False));raise SystemExit(bool(errors))
