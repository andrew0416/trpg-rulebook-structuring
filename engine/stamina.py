"""Stamina observes native triggers; only the enclosing action can finish them.

The damage primitive alone is not proof that a triggering action has resolved.
Different Athletics/Combat ranks require an actual choice, never an invented max.
"""
from pathlib import Path
import json
import acquisition_qualification as Q,acquired_features as A,skill_modifiers as S
from source_context import verified_source

SOURCE='edge/스테미너'
NAMES=(SOURCE,'스테미너','Stamina')

def interested(actor):
    return any(value in NAMES for value in actor.spec.get('edges',[]))

def policy(rules):
    value=json.loads((Path(rules.root)/'data/stamina-policy.json').read_text(encoding='utf-8'))
    if value['rule_id']!=SOURCE or rules._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected native Stamina source required')
    verified_source(rules,value['source'],label='Stamina')
    source=rules.selection.units[SOURCE]['source']
    if source.get('file')!=value['source']['file'].removeprefix('input/') or source.get('lines')!=value['lines']:raise ValueError('Stamina literal source identity changed')
    return value

def validate(actor):
    if not interested(actor):return False
    document=policy(actor.r)
    Q.require(SOURCE,'native','owned',[
        Q.check('trainer','prerequisite',actor.kind==document['owner_kind'],'Stamina requires an actual Trainer'),
        Q.rank_limit('copies',A.owned_rule_count(actor,SOURCE),1,document['maximum_copies'],'Stamina requires one actual acquired Edge'),
        Q.check('skill','prerequisite',any(S.rank(actor.r,actor,key)[2]>=document['minimum_rank'] for key in document['skills']),
                'Stamina requires ordinary Expert Athletics or Combat')])
    return True

def observe(engine,actor,event,**facts):
    if not interested(actor):return
    validate(actor)
    if event not in ('massive_damage','critical_hit','take_a_breather'):raise ValueError('unreviewed Stamina trigger')
    import action_lifecycle as ACTION
    ACTION.observe_resolution(engine,actor,SOURCE,dict(event=event,**facts))

def finish(engine,row,*,actor=None,skill=None):
    import effects as FX,action_lifecycle as ACTION,common_checks as C
    if row['phase']!='producer_returned':raise ValueError('actual complete triggering action required before Stamina')
    if ACTION.pending_resolution_effects(engine,row):return C.PendingDecision('actual triggering action effects remain unresolved')
    for trigger in row['triggers']:
        if trigger['source']!=SOURCE or trigger['status']=='completed':continue
        owner=trigger['actor']
        if actor is not None and owner is not actor:continue
        if trigger.get('effect_receipts'):
            rows=getattr(engine,'_effect_dispatch_receipts',{})
            if all(rows[token]['status']=='completed' for token in trigger['effect_receipts']):trigger['status']='completed'
            continue
        if not validate(owner):raise ValueError('actual acquired Stamina required at action completion')
        ranks={key:S.effective_rank(engine.r,owner,key) for key in policy(engine.r)['skills']}
        selected=skill if actor is owner else None
        if selected is None:
            if len(set(ranks.values()))!=1:
                trigger['status']='awaiting_skill'
                continue
            selected=next(iter(ranks))
        if selected not in ranks:raise ValueError('Stamina requires an actual Athletics or Combat choice')
        result=FX.run_effects(engine,owner,owner,[{'type':'temp_hp','target':'self','value':ranks[selected]}],
            {'native_action':row['id'],'stamina_skill':selected},SOURCE)
        trigger['skill']=selected;trigger['rank']=ranks[selected]
        trigger['effect_receipts']=[outcome.receipt for outcome in result.outcomes]
        trigger['status']='awaiting_effect' if result.pending else 'completed'
    return row

def resolve(engine,actor,action_id,*,skill=None):
    import action_lifecycle as ACTION,world_entities as W
    W.require_actors(engine,actor)
    row=getattr(engine,'_native_action_resolutions',{}).get(action_id)
    if row is None or not any(t['actor'] is actor and t['source']==SOURCE for t in row['triggers']):raise ValueError('actual Stamina triggering action receipt required')
    matching=[t for t in row['triggers'] if t['actor'] is actor and t['source']==SOURCE]
    if all(t['status']=='completed' for t in matching):raise ValueError('Stamina triggering action already resolved')
    return finish(engine,row,actor=actor,skill=skill)
