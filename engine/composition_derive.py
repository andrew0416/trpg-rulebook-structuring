"""Pure, data-declared numeric composition; source admission belongs to callers."""
from copy import deepcopy
from fractions import Fraction
import math
if __package__:
    from . import root_resolution as R
else:
    import root_resolution as R

class CompositionPending(ValueError): pass

LAWS={'add','multiply','maximum','minimum','replace','nonstacking','percent_add','percent_product'}

def derive(base,contributions,steps,*,rounding='floor'):
    """Steps give explicit application order. Percent values are exact ratios."""
    initial=R._number(base)
    if rounding not in ('floor','ceil','trunc','exact'):raise ValueError('explicit rounding law required')
    if type(contributions) is not list or type(steps) is not list:raise ValueError('contribution and step lists required')
    rows={};numbers={}
    for row in contributions:
        if type(row) is not dict or not {'id','source','value'}<=set(row) or set(row)-{'id','source','value','active','priority'}:
            raise ValueError('exact contribution fields required')
        for key in ('id','source'):
            if type(row[key]) is not str or not row[key]:raise ValueError('contribution and source identities required')
        if row['id'] in rows:raise ValueError('duplicate contribution identity')
        active=row.get('active',True)
        if active is not None and type(active) is not bool:raise ValueError('boolean or pending contribution condition required')
        if 'priority' in row and type(row['priority']) is not int:raise ValueError('integer priority required')
        rows[row['id']]=row;numbers[row['id']]=R._number(row['value'])
    used=[]
    for step in steps:
        if type(step) is not dict or set(step)!={'law','contributors'} or type(step['law']) is not str or step['law'] not in LAWS:
            raise ValueError('known composition law and contributor list required')
        ids=step['contributors']
        if type(ids) is not list or not ids or any(type(i) is not str or i not in rows for i in ids):raise ValueError('actual contribution identities required')
        used.extend(ids)
        if step['law'] in ('replace','nonstacking') and any('priority' not in rows[i] for i in ids):raise ValueError('explicit replacement/nonstacking priorities required')
    if len(set(used))!=len(used) or set(used)!=set(rows):raise ValueError('each contribution must belong to exactly one step')
    if any(row.get('active',True) is None for row in rows.values()):raise CompositionPending('contribution condition unresolved')
    value=initial;trace=[]
    for step in steps:
        ids=[i for i in step['contributors'] if rows[i].get('active',True)]
        if not ids:continue
        before=value;law=step['law'];selected=ids
        if law in ('replace','nonstacking'):
            priority=max(rows[i]['priority'] for i in ids)
            selected=[i for i in ids if rows[i]['priority']==priority]
            if len({numbers[i] for i in selected})!=1:raise CompositionPending('conflicting contributions at equal priority')
            amount=numbers[selected[0]]
            value=amount if law=='replace' else value+amount
        elif law=='add':value+=sum((numbers[i] for i in ids),Fraction())
        elif law=='maximum':value=max([value]+[numbers[i] for i in ids])
        elif law=='minimum':value=min([value]+[numbers[i] for i in ids])
        elif law=='percent_add':value*=1+sum((numbers[i] for i in ids),Fraction())
        else:
            for i in ids:value*=numbers[i]+(1 if law=='percent_product' else 0)
        trace.append({'law':law,'contributors':list(ids),'selected':list(selected),
                      'before':R.plain(R._numeric_value(before)),'after':R.plain(R._numeric_value(value))})
    result=R.plain(R._numeric_value(value)) if rounding=='exact' else {'floor':math.floor,'ceil':math.ceil,'trunc':math.trunc}[rounding](value)
    return {'base':deepcopy(base),'contributions':deepcopy(contributions),'steps':trace,
            'exact':R.plain(R._numeric_value(value)),'rounding':rounding,'value':result,'consumed':False}


def policy(engine,actor,target,document,*,context=None,decisions=None):
    """Preview selected-source arithmetic against live, read-only state inputs."""
    import source_policy as P
    import source_policy_state as S
    import world_entities as W
    import acquisition_qualification as Q
    W.require_actors(engine,actor,target)
    prepared=P.resolve(engine.r,document,context=context,decisions=decisions,
        _state_reader=lambda specs:S.read(engine,actor,target,specs))
    if prepared['status']!='PolicyValuesReady':return prepared
    values=prepared['values']
    if set(values)!={'composition'} or type(values['composition']) is not dict:
        raise ValueError('exact composition declaration required')
    declaration=deepcopy(values['composition'])
    if set(declaration)!={'base','contributions','steps','rounding'}:
        raise ValueError('explicit base, contributions, steps and rounding required')
    rows=declaration['contributions']
    if type(rows) is not list:raise ValueError('contribution list required')
    for row in rows:
        if type(row) is not dict or row.get('source')!=prepared['selected_id']:
            raise ValueError('contribution must belong to selected policy source')
        if 'active' in row:row['active']=Q.predicate(row['active'])
    try:result=derive(**declaration)
    except CompositionPending as exc:
        return dict(prepared,status='PolicyCompositionPending',composition={'status':'pending','reason':str(exc)},consumed=False)
    return dict(prepared,status='PolicyCompositionEvaluated',composition=result,consumed=False)


def bundle(engine,actor,target,plan,contributors):
    """Each submission is a document plus its own scoped context/decisions.

    The selected plan owns order and rounding. Its member manifest binds each
    contribution identity to an independently resolved policy and source.
    """
    import source_policy as P
    import source_policy_state as S
    import world_entities as W
    import acquisition_qualification as Q
    W.require_actors(engine,actor,target)
    def resolve(submission):
        if type(submission) is not dict or 'document' not in submission or set(submission)-{'document','context','decisions'}:
            raise ValueError('exact policy submission required')
        return P.resolve(engine.r,**submission,_state_reader=lambda specs:S.read(engine,actor,target,specs))
    if type(contributors) is not list:raise ValueError('contributor submissions required')
    owner=resolve(plan)
    if owner['status']!='PolicyValuesReady':return owner
    values=owner['values']
    if set(values)!={'composition_plan'} or type(values['composition_plan']) is not dict:raise ValueError('exact composition plan required')
    declaration=values['composition_plan']
    if set(declaration)!={'base','members','steps','rounding'}:raise ValueError('exact composition plan fields required')
    members=declaration['members']
    if type(members) is not dict:raise ValueError('explicit member manifest required')
    for key,member in members.items():
        if type(key) is not str or not key or type(member) is not dict or set(member)!={'policy_id','source'}:
            raise ValueError('exact contributor policy/source binding required')
        if any(type(v) is not str or not v for v in member.values()):raise ValueError('nonempty contributor bindings required')
    evidence={}
    for submission in contributors:
        item=resolve(submission);identity=item['policy_id']
        if identity in evidence:raise ValueError('duplicate contributor policy')
        evidence[identity]=item
    if set(evidence)!={member['policy_id'] for member in members.values()}:raise ValueError('exact declared contributor policies required')
    for member in members.values():
        if evidence[member['policy_id']]['selected_id']!=member['source']:raise ValueError('selected contributor source differs from plan')
    result={'plan':owner,'contributors':evidence,'effects_executed':False,'consumed':False}
    unresolved=[key for key,item in evidence.items() if item['status'] not in ('PolicyValuesReady','PolicyNotApplicable')]
    if unresolved:return dict(result,status='PolicyCompositionPending',pending_policies=unresolved)
    rows=[];excluded=[]
    for identity,item in evidence.items():
        expected={key for key,member in members.items() if member['policy_id']==identity}
        if item['status']=='PolicyNotApplicable':excluded.extend(sorted(expected));continue
        values=item['values']
        if set(values)!={'composition_contributions'} or type(values['composition_contributions']) is not list:raise ValueError('exact contributor declaration required')
        actual=deepcopy(values['composition_contributions'])
        if any(type(row) is not dict or type(row.get('id')) is not str for row in actual):raise ValueError('identified contribution rows required')
        if len(actual)!=len(expected) or {row['id'] for row in actual}!=expected:raise ValueError('contributions differ from declared manifest')
        for row in actual:
            if row.get('source')!=item['selected_id']:raise ValueError('contribution must belong to independently selected source')
            if 'active' in row:row['active']=Q.predicate(row['active'])
        rows.extend(actual)
    # Validate the complete plan even when an inapplicable member is omitted.
    steps=deepcopy(declaration['steps']);seen=[];filtered=[]
    if type(steps) is not list:raise ValueError('explicit composition steps required')
    for step in steps:
        if type(step) is not dict or set(step)!={'law','contributors'} or type(step['law']) is not str or step['law'] not in LAWS or type(step['contributors']) is not list or not step['contributors']:
            raise ValueError('known composition step required')
        if any(type(key) is not str or key not in members for key in step['contributors']):raise ValueError('step references undeclared member')
        seen.extend(step['contributors']);step['contributors']=[key for key in step['contributors'] if key not in excluded]
        if step['contributors']:filtered.append(step)
    if len(seen)!=len(set(seen)) or set(seen)!=set(members):raise ValueError('each member must belong to exactly one step')
    try:calculated=derive(declaration['base'],rows,filtered,rounding=declaration['rounding'])
    except CompositionPending as exc:return dict(result,status='PolicyCompositionPending',reason=str(exc),excluded=excluded)
    return dict(result,status='PolicyCompositionEvaluated',composition=calculated,excluded=excluded)
