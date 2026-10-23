"""Exhaustive obligation inventory, not semantic certification.
Every RuleUnit and nested typed effect is retained; textual candidates require review.
"""
import ast,collections,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FACETS={
 'condition':{'if','if_weather','if_hp_below_third','while','while_status','condition','on','on_ko','on_miss','on_natural_roll','on_natural_roll_min','on_roll','except','unless','fails_if','requires','only','vs','vs_type'},
 'target':{'target','targets','species','range','shape','origin','radius','allies','enemies'},
 'cost':{'ap','cost','consume','consumable','action','action_cost'},
 'duration':{'duration','until','rounds','turns','when','at','delay'},
 'frequency':{'frequency','limit','once_per_scene','once_per_scene_per_target','once','max','repeatable'},
 'choice':{'choice','choose','options','chosen','mode'},
}
TEXT_MARKERS={
 'condition':r'경우|라면|이면|때|동안|unless|except|if ',
 'cost':r'AP|지불|소비|소모|행동',
 'frequency':r'장면|하루|매일|한 번|한번|[0-9]+회|라운드|턴',
 'target':r'대상|아군|적|자신|사용자|미터|범위',
 'duration':r'동안|까지|종료|해제|지속',
 'choice':r'선택|중 하나|중에서',
 'numeric':r'\d',
}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def emit(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    from audit_rulebook_all import walk_effects
    units=[json.loads(s) for s in (ROOT/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines()]
    catalog={r['rule_id']:r for r in [json.loads(s) for s in (ROOT/'data/verification/rule-coverage-catalog.jsonl').read_text(encoding='utf-8').splitlines()]}
    contracts=json.loads((ROOT/'data/verification/rule-contracts.json').read_text(encoding='utf-8'))['contracts']
    contract_map=collections.defaultdict(list)
    for c in contracts:
        for uid in c['source_unit_ids']:contract_map[uid].append(c['id'])
    # Candidate string-key consumers only: occurrence is explicitly not evidence of enforcement.
    mentions=collections.defaultdict(set)
    for p in (ROOT/'engine').glob('*.py'):
        if p.name.startswith('test_'):continue
        for node in ast.walk(ast.parse(p.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):
                mentions[node.value].add(p.relative_to(ROOT).as_posix()+':'+str(node.lineno))
    rows=[];fields=collections.Counter();effect_types=collections.Counter();facets=collections.Counter()
    risk_units=collections.defaultdict(set);effect_count=0
    for u in units:
        uid=u['id'];data=(u.get('mech') or {}).get('data',{});effects=[]
        for path,e in walk_effects(data.get('effects',[])):
            effect_count+=1;effect_types[e['type']]+=1
            keys=[]
            for k,v in e.items():
                fields[k]+=1
                fs=[name for name,members in FACETS.items() if k in members or (name=='condition' and k.startswith('if_'))]
                if fs:facets.update(fs)
                keys.append(dict(key=k,value=v,facets=fs,consumer_candidates=sorted(mentions[k]),enforcement_review='pending'))
            effects.append(dict(path=path,type=e['type'],fields=keys,semantic_review='pending'))
            if 'ap' in e:risk_units['ap_effect_cost'].add(uid)
            if 'if_weather' in e:risk_units['weather_effect'].add(uid)
            if isinstance(e.get('if'),str):risk_units['text_condition'].add(uid)
            if e.get('type') in ('gm','rule'):risk_units['gm_or_narrative_effect'].add(uid)
        text=u.get('text',{});body='\n'.join(v for v in text.values() if isinstance(v,str))
        # Keep complete lines; never present heuristic fragments as a reviewed clause count.
        candidates=[dict(index=i+1,text=line,facets=[k for k,v in TEXT_MARKERS.items() if re.search(v,line,re.I)],review='pending')
                    for i,line in enumerate(body.splitlines()) if line.strip()]
        header=data.get('header',{});header_freq=header.get('frequency',{}) if isinstance(header,dict) else {}
        if isinstance(header_freq,dict) and header_freq.get('ap'):risk_units['ap_header_cost'].add(uid)
        rec=catalog.get(uid,{})
        tests={name:value for name,value in rec.get('tested_components',{}).items()}
        required=['original source fidelity including omissions and order','source clause decomposition and exceptions','implementation path review including side effects','independent positive/negative/boundary tests','combined lifecycle and interaction tests']
        if not effects:required.append('classify data/reference/implicit rule before any test exemption')
        rows.append(dict(rule_id=uid,kind=u['kind'],source=u.get('source'),source_text_candidates=candidates,header=header,effects=effects,
            linked_contracts=contract_map[uid],tested_components=tests,full_rule_status='not_certified',required_reviews=required))
    assert len(rows)==len({r['rule_id'] for r in rows})==len(units)
    assert {r['rule_id'] for r in rows}==set(catalog),'coverage catalog drift'
    out=ROOT/'output/whole-rulebook-audit'
    (out/'rule-obligations.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    summary=dict(total_rules=len(rows),nested_effects=effect_count,rules_with_effects=sum(bool(r['effects']) for r in rows),
        rules_without_effects=sum(not r['effects'] for r in rows),rules_with_contracts=sum(bool(r['linked_contracts']) for r in rows),
        rules_with_component_tests=sum(bool(r['tested_components']) for r in rows),full_rule_certified=0,
        effect_types=dict(effect_types.most_common()),field_occurrences=dict(fields.most_common()),facet_field_occurrences=dict(facets),
        review_groups={k:dict(count=len(v),rule_ids=sorted(v)) for k,v in risk_units.items()},
        limitations=['This inventories existing representation; missing source clauses still need source-to-data review.',
                    'A field name found in code does not prove its condition is enforced.',
                    'Text candidate counts are not rule or clause counts.',
                    'No effects or no linked test does not imply a rule is inapplicable.',
                    'Passing a component does not verify its parent rule.'],
        input_hashes={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in [ROOT/'output/ruleunits.jsonl',ROOT/'data/verification/rule-contracts.json',ROOT/'data/verification/rule-coverage-catalog.jsonl',Path(__file__),*sorted((ROOT/'engine').glob('*.py'))]})
    emit(out/'obligation-summary.json',summary)
    print(json.dumps({k:summary[k] for k in ('total_rules','nested_effects','rules_with_effects','rules_without_effects','rules_with_contracts','rules_with_component_tests','full_rule_certified')},ensure_ascii=False))
    return 0
if __name__=='__main__':raise SystemExit(main())
