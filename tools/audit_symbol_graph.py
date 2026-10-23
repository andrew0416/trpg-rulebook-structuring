"""Validate and traverse the top-down rule symbol graph. Structure is not semantic certification."""
import argparse,hashlib,json
from pathlib import Path

def closure(graph, symbol):
    nodes={n['id']:n for n in graph['nodes']};seen=set();todo=[symbol]
    while todo:
        cur=todo.pop()
        if cur in seen:continue
        seen.add(cur);todo.extend(nodes.get(cur,{}).get('requires',[]))
    return seen

def validate(graph, units, contracts):
    errors=[];nodes={n['id']:n for n in graph['nodes']}
    if len(nodes)!=len(graph['nodes']):errors.append('duplicate_symbols')
    if graph.get('root') not in nodes:errors.append('missing_root')
    for node in graph['nodes']:
        if node.get('parent') and node['parent'] not in nodes:errors.append('unknown_parent:'+node['id'])
        for dep in node.get('requires',[]):
            if dep not in nodes:errors.append('unknown_dependency:'+node['id']+':'+dep)
        for uid in node.get('source_unit_ids',[]):
            if uid not in units:errors.append('unknown_source_rule:'+uid);continue
            current=hashlib.sha256(json.dumps(units[uid]['text'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            if node.get('source_hashes',{}).get(uid)!=current:errors.append('stale_symbol_source:'+node['id']+':'+uid)
        if node.get('status')=='reviewed' and (not node.get('source_unit_ids') or node.get('dependency_review')!='complete'):
            errors.append('unsupported_review_claim:'+node['id'])
    for edge in ['requires','parent']:
        visiting=set();done=set()
        def visit(uid):
            if uid in visiting:errors.append('cycle:'+edge+':'+uid);return
            if uid in done or uid not in nodes:return
            visiting.add(uid);raw=nodes[uid].get(edge,[])
            for target in ([raw] if isinstance(raw,str) else raw or []):visit(target)
            visiting.remove(uid);done.add(uid)
        for uid in nodes:visit(uid)
    binds=graph['rule_bindings'];ids=[b['rule_id'] for b in binds]
    if len(set(ids))!=len(ids):errors.append('duplicate_rule_bindings')
    if set(ids)!=set(units):errors.append('rule_binding_set_mismatch')
    for b in binds:
        if not b.get('symbol_refs'):errors.append('empty_rule_binding:'+b['rule_id'])
        for symbol in b.get('symbol_refs',[]):
            if symbol not in nodes:errors.append('unknown_rule_symbol:'+b['rule_id']+':'+symbol)
        if b.get('relation')=='classification_candidate' and b.get('dependency_review')=='complete':errors.append('candidate_marked_reviewed:'+b['rule_id'])
    rows=graph.get('contracts',[]);ids=[c['contract_id'] for c in rows]
    if len(set(ids))!=len(ids):errors.append('duplicate_contract_bindings')
    if set(ids)!={c['id'] for c in contracts}:errors.append('contract_binding_set_mismatch')
    for row in rows:
        for symbol in row['symbol_refs']:
            if symbol not in nodes:errors.append('unknown_contract_symbol:'+symbol)
    return errors

def rule_blockers(graph,rule_id):
    row=next((b for b in graph['rule_bindings'] if b['rule_id']==rule_id),None)
    if row is None:return ['symbol_binding_missing']
    blocks=[]
    if row.get('dependency_review')!='complete':blocks.append('symbol_dependencies_not_reviewed')
    nodes={n['id']:n for n in graph['nodes']}
    needed=set().union(*(closure(graph,s) for s in row['symbol_refs']))
    incomplete=sorted(s for s in needed if nodes.get(s,{}).get('status')!='reviewed' or nodes.get(s,{}).get('dependency_review')!='complete')
    if incomplete:blocks.append('unverified_parent_symbols:'+','.join(incomplete))
    return blocks

def impact(graph,symbol):
    if symbol not in {n['id'] for n in graph['nodes']}:raise ValueError('Unknown symbol: '+symbol)
    dependent={n['id'] for n in graph['nodes'] if symbol in closure(graph,n['id'])}
    return dict(symbol=symbol,affected_symbols=sorted(dependent),rule_ids=sorted(b['rule_id'] for b in graph['rule_bindings'] if set(b['symbol_refs'])&dependent),contract_ids=sorted(c['contract_id'] for c in graph['contracts'] if set(c['symbol_refs'])&dependent),meaning='Potential impact includes unreviewed dependency proposals. Membership is not a coverage claim.')

def main(root,symbol=None):
    graph=json.loads((root/'data/verification/rule-symbol-graph.json').read_text(encoding='utf-8'))
    units={u['id']:u for u in map(json.loads,(root/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines())}
    contracts=json.loads((root/'data/verification/rule-contracts.json').read_text(encoding='utf-8'))['contracts']
    errors=validate(graph,units,contracts)
    from audit_root_semantics import validate_root,closure_blockers
    root_spec=json.loads((root/'data/verification/root-semantics.json').read_text(encoding='utf-8'))
    errors += validate_root(root_spec,graph,root)
    selected=impact(graph,symbol) if symbol else None
    if selected:
        selected['test_ids']=sorted({t['id'] for c in contracts if c['id'] in selected['contract_ids'] for clause in c['clauses'] for t in clause.get('tests',[])})
    report=dict(root_semantics_closed=not closure_blockers(root_spec),root_semantics_blockers=closure_blockers(root_spec),structure_status='pass' if not errors else 'fail',errors=errors,symbols=sum(n['kind']=='symbol' for n in graph['nodes']),rule_bindings=len(graph['rule_bindings']),reviewed_symbols=sum(n['kind']=='symbol' and n['status']=='reviewed' for n in graph['nodes']),fully_reviewed_rule_dependencies=sum(not rule_blockers(graph,uid) for uid in units),impact=selected,meaning='A connected hierarchy does not establish complete source symbolization or correct runtime behavior.')
    (root/'output/whole-rulebook-audit/symbol-graph-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='impact'},ensure_ascii=False))
    if selected:print(json.dumps(dict(impact=symbol,rules=len(selected['rule_ids']),contracts=len(selected['contract_ids']),tests=len(selected['test_ids'])),ensure_ascii=False))
    return 1 if errors else 0
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--impact');args=parser.parse_args()
    raise SystemExit(main(Path(__file__).resolve().parents[1],args.impact))
