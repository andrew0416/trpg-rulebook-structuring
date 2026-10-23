"""Integrity of partial recovery contracts and their independent test links."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC='data/verification/recovery-semantics.json'

def validate(spec,root):
    errors=[]
    if any(spec.get('certification',{}).values()):errors.append('unsupported_recovery_certification')
    clauses=spec.get('clauses',[])
    if not clauses or len({c['id'] for c in clauses})!=len(clauses):errors.append('invalid_recovery_clauses')
    for c in clauses:
        if not c.get('formal') or not c.get('proof_obligations') or not c.get('sources'):errors.append('incomplete_recovery_clause:'+c['id'])
        for a in c.get('sources',[]):
            path=root/a.get('file','');start,end=a.get('start',0),a.get('end',0)
            if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):errors.append('invalid_recovery_source:'+c['id']);continue
            lines=path.read_text(encoding='utf-8').splitlines();excerpt='\n'.join(lines[start-1:end])
            if start<1 or end<start or end>len(lines) or excerpt!=a.get('excerpt') or hashlib.sha256(excerpt.encode()).hexdigest()!=a.get('excerpt_sha256'):errors.append('stale_recovery_source:'+c['id'])
    runtime=spec.get('runtime_contract',{})
    if not runtime.get('remaining'):errors.append('unsupported_recovery_runtime_closure')
    tests=runtime.get('partial_tests',[])
    if not tests:errors.append('missing_recovery_test_links')
    for t in tests:
        path=root/t['file']
        if not path.is_file():errors.append('missing_recovery_test_file');continue
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        names={n.name for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
        if t['method'] not in names:errors.append('unknown_recovery_test:'+t['method'])
    for review in spec.get('interpretation_reviews',[]):
        for a in review.get('evidence',[]):
            if a.get('kind')!='pdf_text':continue
            path=root/a['file']
            if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):errors.append('missing_recovery_pdf');continue
            from pypdf import PdfReader
            page=PdfReader(path).pages[a['page_index']].extract_text();excerpt=a['excerpt']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=a['file_sha256'] or excerpt not in page or hashlib.sha256(excerpt.encode()).hexdigest()!=a['excerpt_sha256']:errors.append('stale_recovery_pdf')
    return errors

if __name__=='__main__':
    spec=json.loads((ROOT/SPEC).read_text(encoding='utf-8'));errors=validate(spec,ROOT)
    paths=[SPEC,'tools/audit_recovery_semantics.py']+spec['runtime_contract']['implementation']+sorted({t['file'] for t in spec['runtime_contract']['partial_tests']})+sorted({a['file'] for c in spec['clauses'] for a in c['sources']})
    paths+=sorted({a['file'] for r in spec.get('interpretation_reviews',[]) for a in r.get('evidence',[])})
    result=dict(status='integrity_pass_runtime_partial' if not errors else 'invalid',errors=errors,clauses=len(spec['clauses']),proof_obligations=sum(len(c['proof_obligations']) for c in spec['clauses']),whole_rule_certified=False,remaining=spec['runtime_contract']['remaining'],input_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/whole-rulebook-audit/recovery-semantics-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('input_hashes','remaining')},ensure_ascii=False));raise SystemExit(bool(errors))
