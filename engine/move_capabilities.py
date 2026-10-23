"""Read-only learned-capability contributions from reviewed known Moves."""
from pathlib import Path
import hashlib,json


def policy(rules):
    result=getattr(rules,'_move_capability_policy',None)
    if result is None:
        result=json.loads((Path(rules.root)/'data/move-capability-policy.json').read_text(encoding='utf-8'))
        for file,digest in result['source_files'].items():
            if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('learned capability source changed: '+file)
        rules._move_capability_policy=result
    return result


def learned_ids(actor):
    """Owned learning, excluding use permissions and display-only overlays."""
    import move_state as MOVES
    return frozenset(actor.r.move_id(mid) or mid for mid in MOVES.owned_list(actor.spec,"moves",actor.moves))


def contributions(actor):
    result=[]
    learned=learned_ids(actor)
    for source,row in policy(actor.r)['sources'].items():
        if source not in learned:continue
        if actor.r._selected_rule(source)!=source:raise ValueError('learned capability needs selected source review')
        mechanics,_=actor.r.move_mech(source)
        effects=[{k:v for k,v in e.items() if not k.startswith('_')} for e in mechanics.get('effects_exec',[]) if e.get('type')=='grant_capability']
        if effects!=row['expected_extracted_grants']:raise ValueError('learned capability extraction differs from reviewed source')
        result.extend({'source':source,'capability':name,'lifetime':row['lifetime'],'source_record':row['source_record']} for name in row['capabilities'])
    # The exact CSV capability expands the printed learned-Move grant list.
    # Learning ownership excludes temporary permission and display overlays.
    import csv_item_capability_contracts as CSV
    for source in sorted(learned):
        move=actor.r.moves.get(source)
        if not move:continue
        custom=move.get('source')=='custom' or move.get('homebrew') is True
        if not CSV.poison_glands_eligible(move,homebrew=custom):continue
        import csv_item_contract_policy as CSV_POLICY
        CSV_POLICY.definition(actor.r,clause_id='C2CSV/item-data:87:5')
        if actor.r._selected_rule(source)!=source:raise ValueError('learned Poison Glands needs its actual selected Move')
        if not any(row['source']==source and row['capability']=='독샘' for row in result):
            result.append({'source':source,'capability':'독샘','lifetime':'while_move_known',
                           'source_record':'C2CSV/item-data:87:5'})
    return tuple(result)


CHOICES_KEY='learned_capability_policies'

def validate_choices(actor):
    choices=actor.spec.get(CHOICES_KEY,{})
    if not isinstance(choices,dict):raise ValueError('learned capability policies must be records')
    definitions=policy(actor.r).get('numeric_sources',{})
    for source,record in choices.items():
        options=definitions.get(source,{}).get('choices',{})
        if not isinstance(record,dict) or not isinstance(record.get('choice'),str) or record.get('choice') not in options or not isinstance(record.get('reason'),str) or not record['reason'].strip():
            raise ValueError('learned capability source choice and reason required')
        if record.get('authority')!=options[record['choice']]['authority']:
            raise ValueError('learned capability choice authority does not match source')
    return choices


def choose(engine,actor,source,choice,*,reason):
    from copy import copy,deepcopy
    options=policy(actor.r).get('numeric_sources',{}).get(source,{}).get('choices',{})
    if not isinstance(choice,str) or choice not in options or not isinstance(reason,str) or not reason.strip():
        raise ValueError('reviewed learned capability source choice and reason required')
    before=deepcopy(actor.spec.get(CHOICES_KEY,{}));after=deepcopy(before)
    after[source]={'choice':choice,'authority':options[choice]['authority'],'reason':reason}
    probe=copy(actor);probe.spec=dict(actor.spec,**{CHOICES_KEY:after});validate_choices(probe)
    records=deepcopy(validate_totals(actor))
    if source in before and before[source]['choice']!=choice and source in learned_ids(actor):
        for field in options[choice]['bonuses']:
            if _current(actor,field) and field not in records:records[field]=_record(actor,field)
    probe.spec[TOTALS_KEY]=records
    current_values(probe,actor.spec.get('movement') or {},records)
    actor.spec[TOTALS_KEY]=records
    actor.spec[CHOICES_KEY]=after
    engine.gm._rec('습득 재능 원문 선택',before,after,reason,actor)
    return deepcopy(after[source])


def numeric_contributions(actor,fields,*,learned=None):
    choices=validate_choices(actor);learned=learned_ids(actor) if learned is None else frozenset(learned);fields=set(fields);result=[]
    for source,row in policy(actor.r).get('numeric_sources',{}).items():
        if source not in learned:continue
        options=row.get('choices')
        keys=set().union(*(set(r['bonuses']) for r in options.values())) if options else set(row['bonuses'])
        if not keys.intersection(fields):continue
        if actor.r._selected_rule(source)!=source:raise ValueError('learned capability needs selected source review')
        mechanics,_=actor.r.move_mech(source)
        effects=[{k:v for k,v in e.items() if not k.startswith('_')} for e in mechanics.get('effects_exec',[]) if e.get('type')=='grant_capability']
        if effects!=row['expected_extracted_grants']:raise ValueError('numeric learned capability extraction differs from reviewed source')
        if options and source not in choices:raise ValueError('learned capability source choice required: '+source)
        selected=options[choices[source]['choice']] if options else row
        for field,amount in selected['bonuses'].items():
            if field in fields:result.append({'source':source,'field':field,'amount':amount,'source_record':row['source_record'],'lifetime':row['lifetime'],'choice':choices[source]['choice'] if options else None})
    return tuple(result)


def numeric_values(actor,base,fields):
    result=dict(base)
    for row in numeric_contributions(actor,fields):
        value=result.get(row['field'],0)
        if type(value)is not int or value<0:raise ValueError('base numeric capability must be a nonnegative integer')
        result[row['field']]=value+row['amount']
    return result


TOTALS_KEY='learned_capability_totals'
NUMERIC_FIELDS=('land','sky','swim','burrow','teleport','high_jump','long_jump','power')

def _current(actor,field):
    return actor.spec.get('power_basis','current')=='current' if field=='power' else actor.spec.get('movement_basis','current')=='current'


def validate_totals(actor):
    rows=actor.spec.get(TOTALS_KEY,{})
    if not isinstance(rows,dict):raise ValueError('learned capability totals must be field records')
    definitions=policy(actor.r)['numeric_sources']
    for field,record in rows.items():
        if field not in NUMERIC_FIELDS or not isinstance(record,dict) or type(record.get('present'))is not bool or not isinstance(record.get('included'),list):
            raise ValueError('invalid learned capability total observation')
        seen=set()
        for item in record['included']:
            if not isinstance(item,dict):raise ValueError('invalid included learned capability contribution')
            source=item.get('source');row=definitions.get(source,{})
            options=row.get('choices');choice=item.get('choice')
            if options and (not isinstance(choice,str) or choice not in options):raise ValueError('invalid observed source choice')
            selected=options[choice] if options else row
            if source in seen or item.get('field')!=field or item.get('amount')!=selected.get('bonuses',{}).get(field) or type(item.get('amount'))is not int or item.get('source_record')!=row.get('source_record') or item.get('lifetime')!='while_move_known' or (not options and choice is not None):
                raise ValueError('observed learned capability contribution differs from source')
            seen.add(source)
    return rows


def current_values(actor,base,fields):
    records=validate_totals(actor);result=dict(base)
    for field in fields:
        if field not in records or not _current(actor,field):continue
        record=records[field];value=result.get(field,0)
        if type(value)is not int or value<0:raise ValueError('current capability total must be a nonnegative integer')
        amount=sum(row['amount'] for row in numeric_contributions(actor,(field,)))
        value+=amount-sum(row['amount'] for row in record['included'])
        if value<0:raise ValueError('current capability total cannot contain its claimed learned bonus')
        if not value and not record['present']:result.pop(field,None)
        else:result[field]=value
    return result


def _record(actor,field):
    values=actor.spec.get('movement') or {}
    if field in ('power','high_jump','long_jump') and field not in values:
        raise ValueError('actual current capability total required before learning change: '+field)
    included=list(numeric_contributions(actor,(field,)))
    value=actor.movement if field=='land' else values.get(field,0)
    if type(value)is not int or value<sum(row['amount'] for row in included):
        raise ValueError('current capability total cannot contain its claimed learned bonus')
    return {'present':field in values or field=='land','included':included}


def plan_change(actor,*,baseline=None,granted=(),revoked=()):
    """Read-only plan before a learned ownership mutation; permissions do not enter it."""
    from copy import copy,deepcopy
    import state_grants as G,move_state as MOVES
    probe=copy(actor);probe.spec=deepcopy(actor.spec);st=G.state(probe)
    if baseline is not None:
        old=probe.spec.get('moves',[])
        st['legacy']['moves']=[v for v in st['legacy'].get('moves',[]) if v not in baseline and v not in old]
        probe.spec['moves']=list(baseline)
    for source in revoked:st['sources'].pop(source,None);st['overlays'].pop(source,None)
    probe.moves=MOVES.effective_list(probe.spec,'moves')
    before=learned_ids(actor);after=learned_ids(probe)|set(granted)
    changed=before^after;fields=set()
    for source in changed:
        row=policy(actor.r)['numeric_sources'].get(source,{})
        fields.update(row.get('bonuses',{}))
        for option in row.get('choices',{}).values():fields.update(option['bonuses'])
    records=validate_totals(actor);result={}
    for field in fields:
        if not _current(actor,field):continue
        # Validate the future projection before source ownership changes.
        numeric_contributions(actor,(field,),learned=after)
        if field not in records:result[field]=_record(actor,field)
    return result


def commit_change(actor,plan):
    if plan:actor.spec.setdefault(TOTALS_KEY,{}).update(plan)


def observe_totals(actor):
    """Rebase an explicit new current-total observation, preserving source receipts."""
    result={}
    for field in NUMERIC_FIELDS:
        if _current(actor,field) and field in (actor.spec.get('movement') or {}):
            included=numeric_contributions(actor,(field,))
            if included:result[field]=_record(actor,field)
    return result
