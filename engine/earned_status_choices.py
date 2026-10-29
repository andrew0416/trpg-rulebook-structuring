"""Earned choices from the actual three-roll native Move accuracy occurrence.

Choice admission precedes damage. The existing passive event owns suspension,
the effect dispatcher owns application receipts, and combat_timing owns expiry.
Repeated numeric debuffs need an explicit GM composition ruling.
"""
from copy import deepcopy
import csv
import io
import common_checks as C
import root_resolution as R
import world_entities as W
import combat_timing as TIME

KEY='earned_status_choice'
MARKER='_earned_status_event'
FICKLE='move/변덕레이저'
POPULATION='move/찍찍베기'
OPTIONS={
    FICKLE:('둔화 (1라운드)','억압'),
    POPULATION:('취약 (다음 턴 끝까지)','대상의 기술 1단계 더 저항 (다음 턴 끝까지)','이 피해는 저항 불가'),
}
ENGLISH={FICKLE:'Fickle Beam',POPULATION:'Population Bomb'}
PER='each success after the first'


def native(move,mechanics=None):
    return move.get('id') in OPTIONS and (mechanics is None or any(
        x.get('type')=='apply_status_choice' for x in mechanics.get('effects_exec',())))


def declaration(source):
    return {'type':'apply_status_choice','options':list(OPTIONS[source]),'target':'target','per':PER}


def definition(rules,source):
    if source not in OPTIONS or rules._selected_rule(source)!=source:
        raise ValueError('selected native three-roll choice source required')
    from source_context import verified_source
    from hp_setting_moves import MOVE_REF
    rows=list(csv.reader(io.StringIO(verified_source(rules,MOVE_REF,label='earned multi-roll choices').decode('utf-8-sig'))))
    matched=[row for row in rows if row and row[-1]==ENGLISH[source]]
    move=rules.move(source)
    if len(matched)!=1 or str(move.get('effect')).replace('\r\n','\n')!=matched[0][7].replace('\r\n','\n') or move.get('name')!=matched[0][0]:
        raise ValueError('earned choice source text changed')
    mm=rules.move_mech(source)[0]
    choices=[x for x in mm.get('effects_exec',()) if x.get('type')=='apply_status_choice']
    rolls=[x for x in mm.get('effects_exec',()) if x.get('type')=='multi_roll']
    if len(choices)!=1 or {k:v for k,v in choices[0].items() if not k.startswith('_')}!=declaration(source):
        raise ValueError('exact reviewed native choice declaration required')
    expected={'type':'multi_roll','rolls':3,'hit_if_any':True,'crit_if_any_crit':True}
    if source==POPULATION:expected['bonus_per_extra_success']='choose one'
    if len(rolls)!=1 or {k:v for k,v in rolls[0].items() if not k.startswith('_')}!=expected:
        raise ValueError('exact three native accuracy results required')
    return declaration(source)


def preflight(engine,actor,target,effect,source):
    expected=definition(engine.r,source)
    if {k:v for k,v in effect.items() if not k.startswith('_')}!=expected:
        raise ValueError('unsupported earned choice payload')
    W.require_actors(engine,actor,target)
    if not engine.encounter_active:
        raise ValueError('earned timed choices require an actual encounter')
    if source==FICKLE:TIME.current(engine)
    C.integer(target.custom_conditions.get('combat_turn_serial',0),'target turn serial',0)



def preflight_move(engine,actor,target,move,mechanics):
    if not native(move,mechanics):return
    effects=mechanics.get('effects_exec',[])
    choice=[x for x in effects if x.get('type')=='apply_status_choice']
    rolls=[x for x in effects if x.get('type')=='multi_roll']
    if len(choice)!=1:raise ValueError('one native earned-choice declaration required')
    preflight(engine,actor,target,choice[0],move['id'])
    expected={'type':'multi_roll','rolls':3,'hit_if_any':True,'crit_if_any_crit':True}
    if move['id']==POPULATION:expected['bonus_per_extra_success']='choose one'
    if len(rolls)!=1 or {k:v for k,v in rolls[0].items() if not k.startswith('_')}!=expected:
        raise ValueError('earned choices require the actual three-roll producer')


def _budget(source,results,hit):
    if type(results)is not list or len(results)!=3:
        raise ValueError('three actual native accuracy results required')
    for result in results:
        if type(result) not in (tuple,list) or len(result)!=3:
            raise ValueError('actual accuracy triple required')
        success,face,critical=result
        if type(success)is not bool or type(critical)is not bool or critical and not success:
            raise ValueError('actual accuracy success and critical required')
        if face is not None:C.integer(face,'actual accuracy d20',1,20)
    if type(hit)is not bool or hit and not any(x[0] for x in results):raise ValueError('actual final hit required')
    return (max(0,sum(x[0] for x in results)-1)+int(source==POPULATION and any(x[2] for x in results))) if hit else 0


def _selection(row):
    return {'choices':row['choices'],'overlaps':row['overlaps'],'stacking':row['stacking'],'unresisted':row['unresisted']}


def _seal_selection(row):
    row['selection_fingerprint']=R.fingerprint(_selection(row))


def observe(engine,actor,target,move,results,event_id,completion_id,*,hit,critical,natural):
    if not native(move):return move
    expected=definition(engine.r,move['id'])
    event=engine._passive_events.get(event_id)
    if event is None or event['actor'] is not actor or event['target'] is not target or event['completion_id']!=completion_id or KEY in event:
        raise ValueError('actual native choice accuracy producer required')
    import passive_events as P,effect_contracts as CONTRACTS
    accuracy=next((x['facts'] for x in P.observations(engine,event_id) if x['stage']=='accuracy'),None)
    if accuracy!={'hit':hit,'natural_roll':natural,'critical':critical}:
        raise ValueError('earned choices require the actual observed accuracy')
    results=[list(x) for x in results]
    if critical!=any(x[2] for x in results) or natural!=max((x[1] for x in results if x[1] is not None),default=None):
        raise ValueError('aggregate accuracy differs from the three actual rolls')
    budget=_budget(move['id'],results,hit)
    facts={'event_id':event_id,'actor_id':actor.entity_id,'target_id':target.entity_id,
           'completion_id':completion_id,'move_id':move['id'],'results':results,
           'hit':hit,'critical':critical,'natural':natural,'budget':budget,
           'round':engine.round_no,'at':engine.elapsed_seconds,'profile':CONTRACTS.source_profile(engine,move['id'])}
    row={'facts':facts,'fingerprint':R.fingerprint(facts),'choices':None if budget else [],
         'overlaps':None if budget else [],'stacking':None,'unresisted':None,'ready':not bool(budget),'applications':{}}
    _seal_selection(row);event[KEY]=row
    return dict(move,**{MARKER:event_id})


def _row(engine,event):
    row=event.get(KEY)
    if type(row)is not dict or set(row)!={'facts','fingerprint','choices','overlaps','stacking','unresisted','ready','applications','selection_fingerprint'}:
        raise ValueError('actual earned-choice record required')
    facts=row['facts']
    expected={'event_id','actor_id','target_id','completion_id','move_id','results','hit','critical','natural','budget','round','at','profile'}
    if type(facts)is not dict or set(facts)!=expected or row['fingerprint']!=R.fingerprint(facts):
        raise ValueError('earned choice accuracy evidence changed')
    if (event['producer']!='Engine.use_move' or facts['event_id']!=event['id'] or
            facts['actor_id']!=event['actor'].entity_id or facts['target_id']!=event['target'].entity_id or
            facts['completion_id']!=event['completion_id'] or facts['move_id']!=event['move_id'] or
            facts['round']!=event['round'] or facts['at']!=event['elapsed_seconds']):
        raise ValueError('earned choice producer identity changed')
    definition(engine.r,facts['move_id'])
    C.integer(facts['budget'],'earned choice budget',0)
    C.integer(facts['round'],'earned choice round',1);C.integer(facts['at'],'earned choice time',0)
    if type(facts['critical'])is not bool or type(facts['profile'])is not str or not facts['profile']:
        raise ValueError('typed earned choice source observation required')
    if facts['budget']!=_budget(facts['move_id'],facts['results'],facts['hit']):
        raise ValueError('earned choice budget changed')
    if facts['critical']!=any(x[2] for x in facts['results']) or facts['natural']!=max((x[1] for x in facts['results'] if x[1] is not None),default=None):
        raise ValueError('earned choice aggregate changed')
    import passive_events as P
    accuracy=next((x['facts'] for x in P.observations(engine,event['id']) if x['stage']=='accuracy'),None)
    if accuracy!={'hit':facts['hit'],'natural_roll':facts['natural'],'critical':facts['critical']}:
        raise ValueError('earned choices lost actual accuracy observation')
    completion=engine._move_completions.get(facts['completion_id'])
    if completion is None or completion['actor'] is not event['actor'] or completion['move_id']!=facts['move_id']:
        raise ValueError('earned choices lost paid move completion')
    stored=completion.get('target_moves',{}).get(facts['target_id'])
    if stored is None or stored.get(MARKER)!=event['id']:
        raise ValueError('earned choice target lost its native Move observation')
    choices=row['choices']
    if choices is not None:
        if type(choices)is not list or len(choices)!=facts['budget'] or any(type(x)is not int or not 1<=x<=len(OPTIONS[facts['move_id']]) for x in choices):
            raise ValueError('exact earned selection count and option indices required')
    elif facts['budget']==0:raise ValueError('zero budget cannot request a choice')
    if row['selection_fingerprint']!=R.fingerprint(_selection(row)):
        raise ValueError('earned choice selection changed')
    if type(row['ready'])is not bool or type(row['applications'])is not dict:
        raise ValueError('earned choice lifecycle changed')
    overlaps=row['overlaps']
    if overlaps is not None and (type(overlaps)is not list or any(type(x)is not dict or set(x)!={'recipient_id','event_id','choice_index'} for x in overlaps)):
        raise ValueError('actual overlapping numeric choice observations required')
    policy=row['stacking']
    if policy is not None and (type(policy)is not dict or set(policy)!={'mode','reason'} or policy['mode'] not in ('replace','add') or type(policy['reason'])is not str or not policy['reason'].strip()):
        raise ValueError('explicit GM repeat composition required')
    unresisted=row['unresisted']
    if unresisted is not None and (type(unresisted)is not dict or set(unresisted)!={'mode','reason'} or unresisted['mode']!='positive_type_multiplier_floor_one' or type(unresisted['reason'])is not str or not unresisted['reason'].strip()):
        raise ValueError('explicit GM unresisted-damage interpretation required')
    if row['ready']:
        if bool(facts['move_id']==POPULATION and choices is not None and 3 in choices)!=(unresisted is not None):
            raise ValueError('selected unresisted damage requires its explicit GM interpretation')
        if choices is None or overlaps is None:raise ValueError('ready choices need their actual selection')
        repeated=facts['move_id']==POPULATION and (choices.count(2)>1 or bool(overlaps))
        if repeated!=(policy is not None):raise ValueError('repeated numeric choice needs its explicit GM policy')
    elif row['applications']:raise ValueError('unselected choices cannot have applications')
    return row


def evidence(engine,event):
    row=_row(engine,event)
    return {'accuracy':row['fingerprint'],'selection':row['selection_fingerprint'],
            'applications':{uid:{k:v for k,v in application.items() if k!='receipt'}
                            for uid,application in row['applications'].items()}}


def _recipients(engine,event):
    import move_defense_reactions as DEFENSE
    state=DEFENSE._defense(engine,event)
    if state is None:return [event['target']]
    index=W.actor_index(engine)
    return [index[x['actor_id']] for x in state['recipients'] if x['hit']]


def _resistance_records(actor):
    return [r for r in TIME.records(actor) if r.get(KEY,{}).get('kind')=='outgoing_resistance']


def ensure_choice(engine,event):
    if KEY not in event:return
    row=_row(engine,event)
    import passive_events as P,effect_contracts as CONTRACTS
    facts=row['facts']
    if facts['profile']!=CONTRACTS.source_profile(engine,facts['move_id']):
        raise ValueError('earned choice source changed before resume')
    if row['choices'] is None:return P._pending(engine,event,'earned_status_choice')
    if row['ready']:return
    if row['overlaps'] is None:
        row['overlaps']=[]
        if facts['move_id']==POPULATION and 2 in row['choices']:
            for target in _recipients(engine,event):
                for record in _resistance_records(target):
                    origin=record[KEY]
                    row['overlaps'].append({key:origin[key] for key in ('recipient_id','event_id','choice_index')})
        _seal_selection(row)
    repeated=facts['move_id']==POPULATION and (row['choices'].count(2)>1 or bool(row['overlaps']))
    if repeated and row['stacking'] is None:
        answer=engine.rulings.decide({'type':'earned_status_choice_stacking','unit':facts['move_id'],
            'actor':event['actor'].name,'event_id':event['id'],'choices':list(row['choices']),
            'overlaps':deepcopy(row['overlaps']),
            'text':'Repeated numeric resistance has no selected stacking law. GM: choose replace (one new step, new deadline) or add (each selected step), with a reason.'})
        if answer is None:return P._pending(engine,event,'earned_status_choice_stacking')
        if type(answer)is not dict or set(answer)!={'mode','reason'} or answer['mode'] not in ('replace','add') or type(answer['reason'])is not str or not answer['reason'].strip():
            raise ValueError('explicit GM repeat composition required')
        row['stacking']=deepcopy(answer)
    if facts['move_id']==POPULATION and 3 in row['choices'] and row['unresisted'] is None:
        answer=engine.rulings.decide({'type':'earned_status_choice_unresisted','unit':POPULATION,
            'actor':event['actor'].name,'event_id':event['id'],
            'text':'Source says this damage cannot be resisted, but its general boundary is unresolved. GM may explicitly select positive_type_multiplier_floor_one for this occurrence: final positive type multipliers below1 become1; immunity0, multipliers>=1 and flat Damage Reduction stay unchanged. Supply mode and reason; other interpretations remain unsupported/pending.'})
        if answer is None:
            _seal_selection(row)
            return P._pending(engine,event,'earned_status_choice_unresisted_interpretation')
        if type(answer)is not dict or set(answer)!={'mode','reason'} or type(answer['mode'])is not str or type(answer['reason'])is not str or not answer['reason'].strip():
            raise ValueError('explicit GM unresisted mode and reason required')
        if answer['mode']!='positive_type_multiplier_floor_one':
            _seal_selection(row)
            return P._pending(engine,event,'earned_status_choice_unresisted_unsupported')
        row['unresisted']=deepcopy(answer)
    row['ready']=True;_seal_selection(row)


def choose(engine,actor,event_id,choices):
    import passive_events as P,state_grants as G
    W.require_actors(engine,actor)
    event=engine._passive_events.get(event_id)
    if event is None or event['actor'] is not actor or engine._passive_pending!=event_id or event.get('phase')!='accuracy_boundary':
        raise ValueError('actual pending earned-choice owner required')
    row=_row(engine,event)
    if row['ready'] or row['applications']:raise ValueError('earned choice already accepted')
    if type(choices)is not list or len(choices)!=row['facts']['budget'] or any(type(x)is not int or not 1<=x<=len(OPTIONS[event['move_id']]) for x in choices):
        raise ValueError('select exactly the earned number of legal options')
    if row['choices'] is not None and row['choices']!=choices:
        raise ValueError('cannot change the retained earned selection')
    # Commit only registered native waits; Heavy retains its explicit external remainder.
    pending=[]
    def apply(staged,owner):
        current=staged._passive_events[event_id][KEY]
        current['choices']=list(choices);_seal_selection(current)
        try:return P.deliver(staged,event_id)
        except Exception as error:
            if G.record_native_pending(staged,error,pending):return None
            raise
    result=G.transition(engine,actor,apply,include_grid=engine.grid is not None,include_rulings=True)
    if pending:
        exception,pending_id=pending[0]
        raise exception(pending_id)
    if engine._passive_pending is not None:raise P.PassiveEventPending(engine._passive_pending)
    return result


def _actual(engine,actor,target,move,completion_id=None):
    event=engine._passive_events.get(move.get(MARKER))
    if event is None or event['actor'] is not actor or event['move_id']!=move['id']:
        raise ValueError('actual earned-choice Move occurrence required')
    row=_row(engine,event)
    if not row['ready']:raise ValueError('earned choice must resolve before damage or effects')
    if completion_id is not None and completion_id!=event['completion_id']:
        raise ValueError('earned choice completion changed')
    if target is not event['target']:
        import move_defense_reactions as DEFENSE
        DEFENSE.require_recipient(engine,getattr(engine,'_defense_recipient_scope',None),
                                  actor,target,move,event['completion_id'])
    return event,row


def current_multiplier(engine,actor,target,move,multiplier):
    if MARKER not in move:return multiplier
    event,row=_actual(engine,actor,target,move)
    if event['move_id']==POPULATION and 3 in row['choices'] and multiplier>0:
        return max(1.0,multiplier)
    return multiplier


def outgoing_steps(engine,actor):
    # Every simultaneous record after the first has an explicit additive ruling.
    return sum(record[KEY]['steps'] for record in _resistance_records(actor))


def _timed_facts(record):
    value={k:deepcopy(record[k]) for k in ('source','timing_text','count_deadline','turn_deadline','encounter_end','statuses',KEY) if k in record}
    if 'turn_owner' in record:value['turn_owner_id']=record['turn_owner'].entity_id
    return value


def apply(engine,actor,target,effect,ctx):
    import effect_contracts as CONTRACTS,effect_lifetimes as LIFE
    source=ctx.get('source_id')
    preflight(engine,actor,target,effect,source)
    event,row=_actual(engine,actor,target,ctx.get('move',{}),ctx.get('move_completion'))
    token=ctx.get('effect_receipt');occurrence=ctx.get('effect_occurrence')
    CONTRACTS.validate_receipt(engine,token,source,occurrence,actor,target,effect)
    if engine._effect_dispatch_receipts[token]['status']!='dispatching':
        raise ValueError('live original choice dispatcher required')
    uid=target.entity_id
    if uid in row['applications']:raise ValueError('earned choices already applied to this recipient')
    application={'receipt':token,'occurrence':occurrence,'recipient_id':uid,'timed':[],'conditions':[],
                 'clock':{'round':engine.round_no,'at':engine.elapsed_seconds,
                          'count':TIME.current(engine) if source==FICKLE else None,
                          'target_turn':target.custom_conditions.get('combat_turn_serial',0)}}
    row['applications'][uid]=application
    numeric_done=False
    for index,choice in enumerate(row['choices']):
        if source==POPULATION and choice==3:continue
        if source==FICKLE and choice==2:
            import condition_instances as CONDITIONS
            before={x['id'] for x in CONDITIONS.records(target,'억압')}
            engine.apply_status(target,'억압',source=source,applied_by=actor)
            current=engine._passive_events[event['id']][KEY]['applications'][uid]
            current['conditions'].extend(x['id'] for x in CONDITIONS.records(target,'억압') if x['id'] not in before)
            continue
        if source==POPULATION and choice==2:
            if numeric_done:continue
            numeric_done=True
            prior=_resistance_records(target)
            policy=row['stacking']
            if prior and policy is None:
                raise ValueError('numeric overlap changed after choice; explicit GM composition required')
            if policy and policy['mode']=='replace':
                for old in list(prior):TIME.expire(engine,target,old,ending='replaced')
            steps=row['choices'].count(2) if policy and policy['mode']=='add' else 1
            record={'source':source,'effect_contract':True,'timing_text':"end of target's next turn",
                    'turn_owner':target,'turn_deadline':target.custom_conditions.get('combat_turn_serial',0)+1,
                    'encounter_end':True}
            kind='outgoing_resistance'
        else:
            status='둔화' if source==FICKLE else '취약'
            raw={'type':'apply_status','status':status,'target':'target'}
            raw.update({'duration':'1 round'} if source==FICKLE else {'until':"end of target's next turn"})
            record=LIFE.prepare(engine,actor,target,raw,source)
            kind=status;steps=0
        record[KEY]={'event_id':event['id'],'recipient_id':uid,'choice_index':index,'kind':kind,'steps':steps}
        record.update(effect_receipt=token,effect_occurrence=occurrence)
        TIME.install(engine,target,record)
        current=engine._passive_events[event['id']][KEY]['applications'][uid]
        actual=next(r for r in TIME.records(target) if r.get(KEY)==record[KEY])
        current['timed'].append(_timed_facts(actual))
    return None


def validate(engine):
    import effect_contracts as CONTRACTS,condition_instances as CONDITIONS
    index=W.actor_index(engine);applications={}
    for event in engine._passive_events.values():
        if KEY not in event:continue
        row=_row(engine,event)
        for uid,application in row['applications'].items():
            if uid not in index or type(application)is not dict or set(application)!={'receipt','occurrence','recipient_id','timed','conditions','clock'} or application['recipient_id']!=uid:
                raise ValueError('earned choice application identity changed')
            target=index[uid]
            if target is not event['target']:
                import passive_events as P
                children=[child for child in engine._passive_events.values()
                          if child.get('defense_parent')==event['id'] and child['target'] is target
                          and child['actor'] is event['actor'] and child['move_id']==event['move_id']
                          and any(x['stage']=='accuracy' and x['facts']['hit'] is True for x in P.observations(engine,child['id']))]
                if not children:raise ValueError('earned choice recipient lost native defense producer')
            token=application['receipt']
            actual=engine._effect_dispatch_receipts.get(token,{})
            effect=actual.get('effect',{})
            if {k:v for k,v in effect.items() if not k.startswith('_')}!=declaration(event['move_id']):
                raise ValueError('earned choice effect declaration changed')
            CONTRACTS.validate_receipt(engine,token,event['move_id'],application['occurrence'],
                                       event['actor'],target,effect)
            if actual['status'] not in ('dispatching','completed'):
                raise ValueError('earned choice lost its actual effect application')
            if type(application['timed'])is not list or type(application['conditions'])is not list:
                raise ValueError('earned choice materialization evidence required')
            clock=application['clock']
            if type(clock)is not dict or set(clock)!={'round','at','count','target_turn'} or clock['round']!=row['facts']['round'] or clock['at']!=row['facts']['at']:
                raise ValueError('earned choice application clock changed')
            C.integer(clock['target_turn'],'choice recipient turn serial',0)
            if event['move_id']==FICKLE:C.integer(clock['count'],'choice initiative count')
            elif clock['count'] is not None:raise ValueError('unexpected Population Bomb count clock')
            expected_indices={i for i,choice in enumerate(row['choices']) if choice==1}
            if event['move_id']==POPULATION and 2 in row['choices']:
                expected_indices.add(row['choices'].index(2))
            if {x.get(KEY,{}).get('choice_index') for x in application['timed']}!=expected_indices:
                raise ValueError('timed materialization differs from the selected choices')
            if (len(application['conditions'])!=len(set(application['conditions'])) or
                    len(application['conditions'])>(row['choices'].count(2) if event['move_id']==FICKLE else 0)):
                raise ValueError('Suppressed count exceeds actual selected occurrences')
            for expected in application['timed']:
                origin=expected[KEY];choice_index=origin['choice_index']
                C.integer(origin['steps'],'earned resistance steps',0)
                C.integer(choice_index,'earned choice index',0,len(row['choices'])-1)
                choice=row['choices'][choice_index]
                kind='둔화' if event['move_id']==FICKLE else '취약' if choice==1 else 'outgoing_resistance'
                steps=row['choices'].count(2) if row['stacking'] and row['stacking']['mode']=='add' else 1
                if origin!={'event_id':event['id'],'recipient_id':uid,'choice_index':choice_index,'kind':kind,'steps':steps if kind=='outgoing_resistance' else 0}:
                    raise ValueError('earned choice timed contribution changed')
                if expected.get('source')!=event['move_id'] or expected.get('encounter_end') is not True:
                    raise ValueError('earned timed choice source or encounter lifetime changed')
                if kind=='둔화':
                    if (choice!=1 or expected.get('statuses')!=['둔화'] or expected.get('timing_text')!='1 round'
                            or expected.get('count_deadline')!=(clock['round']+1,clock['count'])
                            or set(expected)!={'source','timing_text','count_deadline','encounter_end','statuses',KEY}):
                        raise ValueError('Fickle Beam Slowed lifetime changed')
                else:
                    if (choice not in (1,2) or expected.get('turn_owner_id')!=uid
                            or expected.get('timing_text')!="end of target's next turn"
                            or expected.get('turn_deadline')!=clock['target_turn']+1
                            or set(expected)!=({'source','timing_text','turn_deadline','turn_owner_id','encounter_end',KEY}|({'statuses'} if choice==1 else set()))):
                        raise ValueError('Population Bomb target-turn lifetime changed')
                    if kind=='취약' and expected.get('statuses')!=['취약']:
                        raise ValueError('Population Bomb chosen status changed')
                key=(event['id'],uid,choice_index)
                if key in applications:raise ValueError('duplicate earned choice application')
                applications[key]=(expected,token,application['occurrence'])
            for condition_id in application['conditions']:
                candidates=[*CONDITIONS.records(target,'억압'),*target.spec.get('effect_instance_history',[])]
                found=[x for x in candidates if x.get('id')==condition_id]
                if not found or any(x.get('source')!=FICKLE or x.get('effect',{}).get('condition')!='억압' for x in found):
                    raise ValueError('selected Suppressed lost its native source')
    for target in index.values():
        seen=set()
        for record in TIME.records(target):
            origin=record.get(KEY)
            if origin is None:continue
            key=(origin.get('event_id'),target.entity_id,origin.get('choice_index'))
            if key in seen or key not in applications:raise ValueError('timed choice lacks its original occurrence')
            seen.add(key);expected,token,occurrence=applications[key]
            if _timed_facts(record)!=expected or record.get('effect_receipt') is not token or record.get('effect_occurrence')!=occurrence:
                raise ValueError('timed choice differs from earned source receipt')
            fields=(set(expected)-{'turn_owner_id'})|{'effect_contract','effect_receipt','effect_occurrence','owned_statuses','installing'}
            if 'turn_owner_id' in expected:fields.add('turn_owner')
            if set(record)!=fields or record.get('effect_contract') is not True:
                raise ValueError('earned timed choice has unsupported derived fields')
            if record.get('installing') is not False or type(record.get('owned_statuses'))is not set or not record['owned_statuses']<=set(record.get('statuses',())):
                raise ValueError('earned timed status ownership changed')
    return True
