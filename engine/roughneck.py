"""Book Roughneck adapters; ownership, damage, conditions and lifetimes remain shared."""
from copy import deepcopy
from pathlib import Path
import json
import acquired_features as A
import skill_modifiers as S
import combat_timing as CLOCK
import effect_lifetimes as LIFE

_data=json.loads((Path(__file__).resolve().parents[1]/'data/roughneck-definitions.json').read_text(encoding='utf8'))
DEFINITIONS=_data['features'];FEATURES=tuple(DEFINITIONS)
CLASS,MENACE,METTLE,MALICE,DISPLAY,GAZE,NAILS=FEATURES
SOURCE_SHA256=_data['source_sha256']
PRESENCE='edge/협박하는-존재'
MOVES=('move/째려보기','move/야금야금','move/박치기','move/뱀눈초리','move/검은눈빛','move/버티기','move/게으름피우기')
KEY='roughneck'


def owns(actor,feature):
    return actor.kind=='trainer' and bool(A.owned_rule_count(actor,feature))


def records(actor,feature,active=True):
    import trainer_feature_acquisition as T
    return [record for _, record in T.static_acquisitions(actor, feature, active=active)]


def acquisition_snapshot(e,actor,feature):
    parents={}
    for parent in DEFINITIONS[feature]['parents']:
        qualify(e,actor,parent);parents[parent]=records(actor,parent)[-1]['request_id']
    members={f:records(actor,f)[-1]['request_id'] for f in FEATURES if records(actor,f)} if feature==NAILS else {}
    return {'parents':parents,'members':members,'presence':A.owned_rule_count(actor,PRESENCE),
            'ranks':{s:S.rank(e.r,actor,s)[2] for s in ('육상','협박')}}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot)!={'parents','members','presence','ranks'}:
        raise ValueError('exact Roughneck acquisition observations required')
    d=DEFINITIONS[feature]
    if set(snapshot['parents'])!=set(d['parents']) or set(snapshot['ranks'])!={'육상','협박'}:
        raise ValueError('printed Roughneck prerequisites required')
    for parent,request in {**snapshot['parents'],**snapshot['members']}.items():
        if parent not in FEATURES or not any(r['request_id']==request for r in records(actor,parent,False)):
            raise ValueError('actual historical Roughneck prerequisite receipt required')
    for value in snapshot['ranks'].values():
        S.validate_rank_value(actor.r,value,label='actual Roughneck skill rank')
    if type(snapshot['presence']) is not int:
        raise ValueError('actual Roughneck skill and Edge observations required')
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('athletics','prerequisite',feature!=CLASS or snapshot['ranks']['육상']>=3,'Novice Athletics required'),
        Q.check('presence','prerequisite',feature!=CLASS or snapshot['presence']==1,'acquired Intimidating Presence required'),
        Q.check('intimidate','prerequisite',snapshot['ranks']['협박']>=d['intimidate'],'printed Intimidate skill rank required'),
        Q.check('features','prerequisite',feature!=NAILS or len(snapshot['members'])>=3,'three acquired Roughneck Features required')])


def qualify(e,actor,feature):
    import trainer_feature_acquisition as T
    if not owns(actor,feature) or len(records(actor,feature))!=1:
        raise ValueError('actual acquired Roughneck source required: '+feature)
    T.validate_actor(actor);T._static_source(e.r,feature)
    if feature==DISPLAY:
        __import__('source_context').verified_source(e.r,_data['english_supplement'],label='Fearsome Display English supplement',source_root='source-audit')
    return DEFINITIONS[feature]


def after_acquire(e,actor,feature,source):
    import state_grants as G
    if feature in (MALICE,GAZE,NAILS):
        import items
        items.register_feats(e,actor)
    else:G.stat(actor,'def',1,source,operation_id='acquisition_stat_tag')


def _swift(e,actor,source,cost):
    import action_points as AP,turn as TURN
    if AP.available(actor)<cost:raise ValueError(source+' requires '+str(cost)+' AP')
    if not TURN.spend(e,actor,'swift',source):raise ValueError(source+' requires available Swift Action')
    if cost:actor.ap_account.charge(cost,mode='spend')


def _choice(e,actor,source,kind,**facts):
    qualify(e,actor,source)
    return e.rulings.decide(dict(type=kind,unit=source,actor=actor.name,actor_id=actor.entity_id,**facts))



class OverlapPending(ValueError):
    def __init__(self,binding):
        import common_checks as C
        self.decision=C.PendingDecision('No printed law for overlapping identical Roughneck effects. An exact GM source ruling is required.',
            basis={'binding':deepcopy(binding),'operators':['add','maximum'],
                   'new_origin_is':'uncommitted Move intent' if binding['new_origin']['kind']=='move' else 'completed actual maneuver hit',
                   'resume':'Provide roughneck_overlap answer with binding, operator and reason; no new Feature cost or effect is committed.'})
        super().__init__(self.decision.required)


def _origin_binding(origin):
    return {k:origin[k] for k in (('kind','completion_id') if origin['kind']=='move' else ('kind','event_id','source'))}


def _overlap_binding(e,actor,target,source,origin):
    field='incoming_critical_bonus' if source==DISPLAY else 'incoming_status_range'
    overlaps=[r for r in CLOCK.records(target) if r['source']==source and field in r]
    if not overlaps:return None
    for record in overlaps:
        producer=getattr(e,'_effect_dispatch_receipts',{}).get(record.get('effect_receipt'))
        if not producer or producer['status']!='completed' or producer['target'] is not target or producer['source_id']!=source:
            raise ValueError('actual completed overlapping effect occurrences required')
    return {'source':source,'source_sha256':SOURCE_SHA256,'actor_id':actor.entity_id,'target_id':target.entity_id,
            'new_origin':_origin_binding(origin),'field':field,'overlap_occurrences':[r['effect_occurrence'] for r in overlaps]}


def _stacking_plan(e,actor,target,source,origin):
    binding=_overlap_binding(e,actor,target,source,origin)
    if binding is None:return None
    answer=e.rulings.decide({'type':'roughneck_overlap','unit':source,'binding':deepcopy(binding),
                             'text':'Choose add or maximum for these exact overlapping occurrences; this is a GM ruling, not a published edition.'})
    if answer is None:raise OverlapPending(binding)
    if type(answer) is not dict or set(answer)!={'binding','operator','reason'}:
        raise ValueError('exact source-bound Roughneck GM composition ruling required')
    if answer['binding']!=binding:raise OverlapPending(binding)
    if answer['operator'] not in ('add','maximum') or type(answer['reason']) is not str or not answer['reason'].strip():
        raise ValueError('explicit GM composition operator and reason required')
    index=len(e.rulings.log)
    e.rulings.record('source_composition',source,deepcopy(binding),{'operator':answer['operator']},answer['reason'],'scene')
    return {'binding':binding,'operator':answer['operator'],'reason':answer['reason'],'ruling_log_index':index}


def _validate_plan(e,plan,binding):
    if plan is None or plan.get('binding')!=binding:raise OverlapPending(binding)
    index=plan.get('ruling_log_index')
    if type(index) is not int or not 0<=index<len(e.rulings.log):raise ValueError('actual Rulings evidence required for composition')
    expected={'kind':'source_composition','what':binding['source'],'before':binding,'after':{'operator':plan['operator']},'reason':plan['reason'],'scope':'scene'}
    if e.rulings.log[index]!=expected or plan['operator'] not in ('add','maximum'):
        raise ValueError('actual source-bound GM composition evidence changed')


def _timed(e,actor,target,source,effect,*,_stacking=None,**extra):
    import effects as FX
    if any(key in extra for key in ('incoming_critical_bonus','incoming_status_range')):
        binding=_overlap_binding(e,actor,target,source,extra['roughneck_origin'])
        if binding is not None:_validate_plan(e,_stacking,binding)
        extra['roughneck_stacking']=deepcopy(_stacking) if binding is not None else None
    result=FX.run_effects(e,actor,target,[effect],{'hit':True,'nat':None,'dealt':0},source)
    if result[1]:raise ValueError('Roughneck timed effect requires completed shared dispatch')
    receipts={outcome.receipt for outcome in result.outcomes}
    row=next((record for record in CLOCK.records(target) if record.get('effect_receipt') in receipts),None)
    if row is not None:
        row.update(extra)
        e._effect_dispatch_receipts[row['effect_receipt']]['roughneck_timed']=deepcopy(extra)
    return row


def attack_hit(e,actor,target,*,origin):
    import effects as FX
    if not owns(actor,CLASS) or actor.side is None or actor.side==target.side:return None
    kind=origin.get('kind') if type(origin) is dict else None
    if kind=='move':
        import move_completion as COMPLETE
        receipt=COMPLETE.require_hit_return(e,origin.get('event_id'),target)
        if receipt['attacker_id']!=actor.entity_id or receipt['completion_id']!=origin.get('completion_id'):
            raise ValueError('actual Roughneck native Move hit required')
        previous=e._passive_events[origin['event_id']].get('outcomes',{}).get(KEY)
        if previous is not None:return deepcopy(previous)
    elif kind in ('maneuver','grapple'):
        event=next((row for row in e._precision_events if row['id']==origin.get('event_id')),None)
        expected='accuracy_hit' if kind=='maneuver' else 'damaging_hit'
        if (event is None or event.get('actor') is not actor or event['target'] is not target
                or event['round']!=e.round_no or event['producer']!='combat_maneuver' or event['result']!=expected):
            raise ValueError('actual Roughneck native maneuver hit required')
        if kind=='maneuver':
            if event.get(KEY,{}).get('phase')!='pending' or event['source']!=origin.get('source'):
                raise ValueError('actual retained Roughneck maneuver decision required')
        else:
            import grapple_state as GRAPPLE
            row=GRAPPLE._state(e)['relations'].get(origin.get('relation_id'))
            if (row is None or event['source']!='struggle' or row['status']!='active'
                    or not {actor.entity_id,target.entity_id}<=set(row['participants'])
                    or origin.get('history_index')!=len(row['history'])):
                raise ValueError('actual current grapple Attack producer required')
    else:raise ValueError('actual native Roughneck Attack origin required')
    stat=_choice(e,actor,CLASS,'roughneck_hit',target_id=target.entity_id,origin=origin,stats=['atk','def','spa','spd','spe'])
    if stat is not None and stat is not False and stat not in ('atk','def','spa','spd','spe'):
        raise ValueError('one printed Combat Stat required')
    if stat:
        _swift(e,actor,CLASS,1);FX.apply_stage_changes(e,actor,target,{stat:-1},source_id=CLASS)
    return {'status':'applied' if stat else 'inapplicable','stat':stat}


def after_maneuver(e,actor,attack):
    if not owns(actor,CLASS):return
    # The native maneuver runner owns accuracy and its completed opposed effect.
    # Calling Manipulate's effect helper (e.g. Enchanting Gaze) is not an Attack.
    event=__import__('skill_maneuver_actions').completed_attack_event(e,actor,attack)
    if event is None or KEY in event:return
    import root_resolution as ROOT
    facts={key:event[key] for key in ('id','round','source','result')}
    facts.update(actor_id=actor.entity_id,target_id=event['target'].entity_id,manipulation=event.get('manipulation'),turn_serial=actor.custom_conditions.get('combat_turn_serial',0))
    event[KEY]={'phase':'pending','facts':facts,'fingerprint':ROOT.fingerprint(facts)}
    return resolve_maneuver(e,actor,event['id'])


def resolve_maneuver(e,actor,event_id):
    """Retry only choices on the native maneuver's retained completed hit; never repay its Standard or reroll."""
    import root_resolution as ROOT,state_grants as G
    event=next((row for row in e._precision_events if row['id']==event_id),None)
    if not event or KEY not in event or event['actor'] is not actor or event['producer']!='combat_maneuver':
        raise ValueError('actual retained Roughneck maneuver hit required')
    record=event[KEY];facts=record['facts']
    if (record['fingerprint']!=ROOT.fingerprint(facts) or facts!={**{key:event[key] for key in ('id','round','source','result')},
        'actor_id':actor.entity_id,'target_id':event['target'].entity_id,'manipulation':event.get('manipulation'),'turn_serial':facts['turn_serial']}):
        raise ValueError('native Roughneck maneuver hit facts changed')
    if record['phase']=='completed':return deepcopy(record)
    if record['phase']!='pending' or event['round']!=e.round_no or facts['turn_serial']!=actor.custom_conditions.get('combat_turn_serial',0):raise ValueError('same-turn Roughneck hit reaction required')
    def apply(staged,user,target):
        actual=next(row for row in staged._precision_events if row['id']==event_id)
        state=actual[KEY];origin={'kind':'maneuver','event_id':event_id,'source':facts['source']}
        selected=None;stacking=None
        eligible=(facts['source']=='maneuver/술수' and facts['manipulation']=='terrorize' and owns(user,MENACE)
                  and user.side is not None and user.side!=target.side)
        if eligible:
            selected=_choice(staged,user,MENACE,'roughneck_menace',target_id=target.entity_id,origin=origin)
            if selected is not None and type(selected) is not bool:raise ValueError('explicit Menace use or decline required')
            if selected is True:stacking=_stacking_plan(staged,user,target,MENACE,origin)
        state['hit']=attack_hit(staged,user,target,origin=origin)
        if eligible:
            state['menace']=selected is True
            if selected is True:
                _swift(staged,user,MENACE,0)
                _timed(staged,user,target,MENACE,{'type':'initiative','set_to':0,'until':"start of target's next turn"},roughneck_origin=origin)
                _timed(staged,user,target,MENACE,{'type':'accuracy_mod','value':0,'duration':'1라운드'},_stacking=stacking,
                       incoming_status_range={'status':'풀죽음','base':17,'bonus':4},roughneck_origin=origin)
        state['phase']='completed'
        return deepcopy(state)
    try:return G.transition(e,actor,apply,participants=(event['target'],),include_rulings=True)
    except OverlapPending as pending:return pending.decision


def begin_display(e,actor,target,move,completion_id):
    import move_completion as COMPLETE
    if move['id'] not in (*MOVES,'move/버티기-홈브류') or not owns(actor,DISPLAY):return
    row=e._move_completions[completion_id]
    if row['actor'] is not actor or target.entity_id not in row['started'] or row['phase']!='targets':
        raise ValueError('actual native Move activation required for Fearsome Display')
    if 'fearsome_display' not in row:
        answer=_choice(e,actor,DISPLAY,'roughneck_display',move_id=move['id'],completion_id=completion_id)
        status=None
        if type(answer) is dict and set(answer)=={'status'} and move['id']=='move/게으름피우기':
            import status_sets
            status=answer['status']
            if status not in status_sets.afflictions(actor):raise ValueError('one current Status Affliction required')
            answer=True
        if answer is not None and type(answer) is not bool:raise ValueError('explicit Fearsome Display use or decline required')
        if answer is True and move['id']=='move/게으름피우기' and status is None:
            import status_sets
            afflictions=status_sets.afflictions(actor)
            if len(afflictions)!=1:raise ValueError('explicit one Status Affliction selection required')
            status=afflictions[0]
        stackings={}
        if answer is True:
            if move['id']=='move/째려보기':
                origin={'kind':'move','completion_id':completion_id}
                for recipient in row['targets']:
                    if actor.side is not None and recipient.side!=actor.side:
                        stackings[recipient.entity_id]=_stacking_plan(e,actor,recipient,DISPLAY,origin)
            _swift(e,actor,DISPLAY,2)
        row['fearsome_display']={'used':answer is True,'status':status,'ap':2 if answer is True else 0,'completed':[],'stackings':stackings}
    if row['fearsome_display']['used']:
        move['_fearsome_completion']=completion_id
        # The prepared Move already owns actor references; change only our marker.
        row['target_moves'][target.entity_id]['_fearsome_completion']=completion_id


def vulnerable(e,actor,target,move):
    token=move.get('_fearsome_completion')
    if token is None or move['id']!='move/야금야금':return False
    row=getattr(e,'_move_completions',{}).get(token)
    return bool(row and row['actor'] is actor and row['phase']=='targets' and row.get('fearsome_display',{}).get('used')
                and target.entity_id in row['started'] and target.entity_id not in row['results'])


def after_move(e,row):
    import effects as FX
    import move_completion as COMPLETE
    if row['phase']!='complete':return
    actor=row['actor'];display=row.get('fearsome_display',{})
    for event_id in row.get('native_returns',{}):
        event=e._passive_events[event_id];target=event['target']
        result=COMPLETE.recipient_result(row,target)
        if result is None or result.get('cancelled') or result.get('hit_prevented') or row['native_returns'][event_id]['facts']['hit_prevented']:continue
        COMPLETE.require_returned_event(e,event_id)
        if display.get('used') and event_id not in display['completed']:
            mid=row['move_id'];origin={'kind':'move','completion_id':row['id'],'event_id':event_id}
            if result['hit'] or mid=='move/뱀눈초리':
                if mid=='move/째려보기' and actor.side is not None and target.side!=actor.side:
                    _timed(e,actor,target,DISPLAY,{'type':'accuracy_mod','value':0,'duration':'1라운드'},_stacking=display['stackings'].get(target.entity_id),incoming_critical_bonus=2,roughneck_origin=origin)
                elif mid=='move/박치기':
                    _timed(e,actor,target,DISPLAY,{'type':'initiative','set_to':0,'until':"end of target's next turn"},roughneck_origin=origin)
                elif mid=='move/뱀눈초리':FX.apply_stage_changes(e,actor,target,{'spe':-2},source_id=DISPLAY)
                elif mid=='move/검은눈빛':e.apply_status(target,'억압',source=DISPLAY,applied_by=actor)
                elif mid in ('move/버티기','move/버티기-홈브류'):
                    import temporary_hp
                    temporary_hp.grant(e,actor,e.tick(actor)*2,provenance={'source':DISPLAY,'completion_id':row['id']})
                elif mid=='move/게으름피우기':e.cure_status(actor,display['status'])
            display['completed'].append(event_id)
        if (not result['hit'] or not owns(actor,CLASS) or actor.side is None or target.side==actor.side
                or 'roughneck' in event.get('outcomes',{})):continue
        COMPLETE.require_hit_return(e,event_id,target)
        event.setdefault('outcomes',{})['roughneck']=attack_hit(e,actor,target,origin={'kind':'move','event_id':event_id,'completion_id':row['id']})


def validate_world(e,index):
    import root_resolution as ROOT,move_completion as COMPLETE
    for event in getattr(e,'_precision_events',[]):
        record=event.get(KEY)
        if record is None:continue
        facts=record['facts']
        if (record['fingerprint']!=ROOT.fingerprint(facts) or event['result']!='accuracy_hit'
                or event['producer']!='combat_maneuver' or facts['id']!=event['id']
                or facts['actor_id']!=event['actor'].entity_id or facts['target_id']!=event['target'].entity_id
                or record['phase'] not in ('pending','completed')):
            raise ValueError('Roughneck actual native maneuver receipt changed')
    for target in index.values():
        for timed in CLOCK.records(target):
            if timed['source'] not in (MENACE,DISPLAY):continue
            # Flinch's Vulnerable child belongs to condition_instances, which
            # validates its exact envelope and canonical parent in WORLD.
            if 'flinch_parent_id' in timed:continue
            origin=timed.get('roughneck_origin',{})
            producer=e._effect_dispatch_receipts.get(timed.get('effect_receipt'))
            if not producer or producer.get('roughneck_timed')!={k:timed[k] for k in producer.get('roughneck_timed',{})}:
                raise ValueError('Roughneck timed contribution lost its native dispatch metadata')
            plan=timed.get('roughneck_stacking')
            if plan is not None:
                binding=plan['binding'];_validate_plan(e,plan,binding)
                if binding['target_id']!=target.entity_id or binding['source']!=timed['source'] or binding['new_origin']!=_origin_binding(origin):
                    raise ValueError('composition ruling belongs to other native occurrences')
                for occurrence in binding['overlap_occurrences']:
                    old=[r for r in e._effect_dispatch_receipts.values() if r['occurrence']==occurrence]
                    if len(old)!=1 or old[0]['source_id']!=timed['source'] or old[0]['target'] is not target or 'roughneck_timed' not in old[0]:
                        raise ValueError('composition ruling lost its actual overlapping occurrences')
            if timed['source']==MENACE:
                event=next((x for x in e._precision_events if x['id']==origin.get('event_id')),None)
                if (event is None or event['target'] is not target or event.get('manipulation')!='terrorize'
                        or not event.get(KEY,{}).get('menace')):raise ValueError('Menace requires its actual paid Terrorize hit')
            else:
                row=e._move_completions.get(origin.get('completion_id'))
                event=e._passive_events.get(origin.get('event_id'))
                if (row is None or event is None or event['target'] is not target or event['completion_id']!=row['id']
                        or not row.get('fearsome_display',{}).get('used')):raise ValueError('Fearsome Display requires its actual paid Move')
                COMPLETE.require_hit_return(e,event['id'],target)
    return True
