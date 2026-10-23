"""Audit top-level profile selection without certifying source-specific precedence."""
import hashlib,itertools,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from ruleset import RuleFilter,classify

def audit(root):
    units=list(map(json.loads,(root/'output/ruleunits.jsonl').read_text(encoding='utf-8').splitlines()))
    profiles=json.loads((root/'data/rulesets.json').read_text(encoding='utf-8'))['rulesets']
    errors=[];rows=[]
    for name,declared in profiles.items():
        rf=RuleFilter.load(str(root),name);kept,excluded,aliases=rf.split(units);conflicts=dict(rf.alias_conflicts)
        # split excludes unresolved identities from runtime admission, but that is
        # not a resolved policy exclusion. Keep each actual reason in the audit.
        unresolved_units=sorted((dict(id=u['id'],reason=why.removeprefix('unresolved:')) for u,why in excluded if why.startswith(('unresolved:', 'unresolved_variant:'))),key=lambda item:(item['id'],item['reason']))
        reverse=RuleFilter.load(str(root),name);rk,re,ra=reverse.split(list(reversed(units)))
        order_independent=(aliases==ra and conflicts==reverse.alias_conflicts and {u['id'] for u in kept}=={u['id'] for u in rk} and {(u['id'],why) for u,why in excluded}=={(u['id'],why) for u,why in re})
        if not order_independent:errors.append('order_dependent_selection:'+name)
        partition_ok=len(kept)+len(excluded)==len(units) and not ({u['id'] for u in kept}&{u['id'] for u,why in excluded})
        if not partition_ok:errors.append('selection_partition_error:'+name)
        drift={key:dict(declared=declared.get(key),effective=rf.profile.get(key)) for key in ['sources','variants','variant_replaces_core','variant_choices','unit_versions','rulings_files','exclude_units','exclude_tags'] if declared.get(key)!=rf.profile.get(key)}
        rows.append(dict(profile=name,kept=len(kept),excluded=len(excluded),alias_count=len(aliases),unresolved_variant_families=conflicts,unresolved_units=unresolved_units,declared_effective_differences=drift,order_independent=order_independent,partition_ok=partition_ok))
    witnesses=[]
    for source,variant,identity,tag in itertools.product([False,True],repeat=4):
        profile=dict(sources=['core'] if source else [],variants=['playtest'] if variant else [],exclude_units=[] if identity else ['rule/example'],exclude_tags=[] if tag else ['excluded-tag'])
        candidate=dict(id='rule/example',title='Example [Playtest]',source=dict(file='db/moves.csv'),tags=['excluded-tag'])
        actual=RuleFilter(profile).allows(candidate)[0];expected=source and variant and identity and tag
        witnesses.append(dict(inputs=dict(source_enabled=source,variant_enabled=variant,identity_allowed=identity,tags_allowed=tag),expected=expected,actual=actual,status='pass' if actual==expected else 'fail'))
    if any(w['status']!='pass' for w in witnesses):errors.append('profile_predicate_counterexample')
    unknown=[u['id'] for u in units if classify(u)[0]=='unknown']
    unresolved=bool(unknown or any(x['unresolved_units'] or x['unresolved_variant_families'] or x['declared_effective_differences'] for x in rows))
    paths=['tools/audit_rule_selection.py','engine/ruleset.py','engine/engine.py','data/rulesets.json','output/ruleunits.jsonl']
    return dict(status='fail' if errors else 'incomplete' if unresolved else 'checks_passed',errors=errors,unknown_source_rules=unknown,profiles=rows,boolean_model=dict(formula='source_enabled AND variant_enabled AND identity_allowed AND tags_allowed',domain='Known source, tagged variant, valid typed profile; each variable is Boolean.',witnesses=witnesses,covered=len(witnesses),total=16,whole_rule_certified=False),remaining=['Source provenance/classification fidelity','Source authority for all declared profile selections','Duplicate candidate equivalence or explicit selection','Source-specific partial order and effect composition','Runtime enforcement for all rule kinds and direct access paths','Name-keyed entity duplicates and generic name resolution'],input_hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths})
if __name__=='__main__':
    report=audit(ROOT)
    (ROOT/'output/whole-rulebook-audit/rule-selection-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['status'],errors=report['errors'],unknown_sources=len(report['unknown_source_rules']),predicate_cases=report['boolean_model']['covered'],profiles=[dict(name=p['profile'],unresolved_families=len(p['unresolved_variant_families']),unresolved_units=p['unresolved_units'],configuration_differences=list(p['declared_effective_differences'])) for p in report['profiles']]),ensure_ascii=False))
    raise SystemExit(0 if report['status']=='checks_passed' else 1)
