"""Actual Move-use exchanges; acquisition, actions and quotas keep native owners."""
from copy import deepcopy

import frequency as F
import state_grants as G
import world_entities as W

FIGHTER='feat/싸움꾼의-유능함'
COMMAND='feat/융통-명령'
FEATURES={FIGHTER:(844,849),COMMAND:(637,641)}
BOOK_SHA='b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
CORE_SHA='e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'
SKILLS=('명령','교활','포켓몬학')
STATS=('hp','atk','def','spa','spd','spe')
WINDOW='versatility_turn_window'
SCENE={'kind':'scene','uses':1}
DEFINITIONS={uid:{'clause_id':'C2-ENTRY-input/ch03-skills-edges-feats.md:'+str(span[0])+'-'+str(span[1]),
    'span':list(span),'catalog_span':list(span),'minimum_level':0,'skill':None,
    'source':{'file':'input/ch03-skills-edges-feats.md','sha256':BOOK_SHA},
    'stat_tags':['any'] if uid==FIGHTER else []} for uid,span in FEATURES.items()}


def source(rules,feature,edition='core'):
    import source_context as S
    if feature not in FEATURES or edition not in ('core','local_csv'):
        raise ValueError('reviewed Versatility source required')
    record=39 if feature==FIGHTER else 4
    source_id='input/ch03-skills-edges-feats.md:'+str(FEATURES[feature][0])+'-'+str(FEATURES[feature][1])
    versions={feature,source_id,'C2-ENTRY-'+source_id,'C2CSV/input/db/feats.csv:R'+str(record)+':main'}
    if rules._selected_rule(feature)!=feature or versions.intersection(rules.ruleset.unit_versions):
        raise ValueError('selected Versatility version requires its own adapter')
    S.verified_source(rules,{'file':'input/ch03-skills-edges-feats.md','sha256':BOOK_SHA},label='Versatility')
    if edition=='local_csv':
        S.verified_source(rules,{'file':'input/db/feats.csv','sha256':CSV_SHA},label='Versatility CSV')
        rules.ruleset.require({'id':'C2CSV/input/db/feats.csv:R'+str(record)+':main',
            'source':{'file':'db/feats.csv','record_span':[record,record]}})
        return {'edition':edition,'file':'input/db/feats.csv','sha256':CSV_SHA,'record':record}
    original={'file':'source-audit/ptu-core-1.05.pdf','sha256':CORE_SHA,'pages':[63,63] if feature==FIGHTER else [59,59]}
    S.verified_source(rules,original,label='original Core Versatility',source_root='source-audit')
    return {'edition':edition,'file':'input/ch03-skills-edges-feats.md','sha256':BOOK_SHA,
            'span':list(FEATURES[feature]),'interpretation':original}


def _selection(feature,selection):
    if type(selection)is not dict or set(selection)!=({'edition','stat'} if feature==FIGHTER else {'edition'}):
        raise ValueError('exact Versatility source and acquisition stat selection required')
    if selection['edition'] not in ('core','local_csv') or feature==FIGHTER and selection['stat'] not in STATS:
        raise ValueError('reviewed Versatility edition and one actual stat required')


def acquisition_snapshot(engine,actor,feature,selection):
    import move_state as M,skill_modifiers as S
    _selection(feature,selection)
    known=M.known(engine.r,{'moves':M.owned_list(actor.spec,'moves')}) if feature==FIGHTER else []
    return {'selection':deepcopy(selection),'source':source(engine.r,feature,selection['edition']),
        'skills':{skill:S.rank(engine.r,actor,skill)[2] for skill in SKILLS} if feature==COMMAND else {},
        'known_moves':known,'frequencies':{mid:list(F.move_frequency(engine,mid,actor)) for mid in known}}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q,common_checks as C,move_state as M
    if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'selection','source','skills','known_moves','frequencies'}:
        raise ValueError('exact historical Versatility acquisition observations required')
    _selection(feature,snapshot['selection'])
    if snapshot['source']!=source(actor.r,feature,snapshot['selection']['edition']):
        raise ValueError('actual immutable Versatility acquisition source required')
    checks=[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required')]
    if feature==FIGHTER:
        known=snapshot['known_moves'];freq=snapshot['frequencies']
        if type(known)is not list or M.known(actor.r,{'moves':known})!=known or type(freq)is not dict or set(freq)!=set(known) or snapshot['skills']!={}:
            raise ValueError('actual learned Versatility Move List required')
        for pair in freq.values():
            if type(pair)is not list or len(pair)!=2:raise ValueError('native observed Versatility Move frequency required')
            kind,cap=pair
            if kind not in ('scene','daily','turn','at_will','every_other_turn','unknown','static','one_time'):
                raise ValueError('native observed Versatility Move frequency required')
            C.integer(cap,'Versatility observed Move frequency cap',1)
        checks.append(Q.check('two_moves','prerequisite',sum(pair[0] in ('scene','daily') for pair in freq.values())>=2,
                              'Fighter Versatility requires two actually learned Scene or Daily Moves'))
    else:
        skills=snapshot['skills']
        if type(skills)is not dict or set(skills)!=set(SKILLS) or snapshot['known_moves']!=[] or snapshot['frequencies']!={}:
            raise ValueError('exact Command Versatility named skill observations required')
        for value in skills.values():C.integer(value,'Command Versatility observed skill rank',0)
        checks.append(Q.check('adept','prerequisite',max(skills.values())>=4,'Adept Command, Guile or Pokemon Education required'))
    return Q.require(feature,'native','acquire',checks)


def records(actor,feature=None,*,active=True):
    import trainer_feature_acquisition as T
    return T.static_family_acquisitions(actor, FEATURES, feature, active=active)


def after_acquire(engine,actor,feature,source_id):
    if feature==FIGHTER:
        row=actor.spec[G.KEY]['sources'][source_id]['static_acquisition']
        G.stat(actor,row['snapshot']['selection']['stat'],1,source_id,operation_id='acquisition_stat_tag')


def _seal(row):
    return __import__('resolution_transaction').request_fingerprint({key:value for key,value in row.items() if key!='sha256'})


def begin_turn(engine,actor):
    """Called only by the actual native turn-start producer, after its automatic hooks."""
    if engine._active_turn_actor is not actor or not engine.encounter_active:return
    row={'actor_id':actor.entity_id,'encounter':engine._party_encounter_epoch,'round':engine.round_no,
         'turn':actor.custom_conditions['combat_turn_serial'],'scene':actor.spec['frequency_state']['scene'],
         'history_index':len(actor._action_history),
         'move_ids':[uid for uid,row in getattr(engine,'_move_completions',{}).items() if row['actor'] is actor]}
    row['sha256']=_seal(row);actor.spec[WINDOW]=row


def validate_actor(actor):
    rows=records(actor)
    for feature in FEATURES:
        unit=actor.r.selection.units.get(feature,{})
        aliases={feature,unit.get('title'),unit.get('eng')}
        owned=aliases.intersection(actor.spec.get('feats',[]))
        if bool(owned)!=bool([r for _,r in rows if r['feature_id']==feature]) or owned and owned!={feature}:
            raise ValueError('Versatility needs its actual acquired Feature receipt')
    for sid,row in rows:
        if row['feature_id']==FIGHTER:
            stat=row['snapshot']['selection']['stat']
            operation=actor.spec[G.KEY].get('stat_sources',{}).get(stat,{}).get('sources',{}).get(sid,{})
            if operation.get('acquisition_stat_tag')!={'delta':1,'minimum':None}:
                raise ValueError('actual source-owned Fighter Versatility stat tag required')
    row=actor.spec.get(WINDOW)
    if row is not None:
        import common_checks as C
        if type(row)is not dict or set(row)!={'actor_id','encounter','round','turn','scene','history_index','move_ids','sha256'} or row['sha256']!=_seal(row) or row['actor_id']!=actor.entity_id:
            raise ValueError('Versatility actual native turn-start evidence changed')
        for field in ('encounter','round','turn','scene','history_index'):C.integer(row[field],'Versatility native '+field,0)
        if type(row['move_ids'])is not list or len(set(row['move_ids']))!=len(row['move_ids']) or any(type(uid)is not str for uid in row['move_ids']):
            raise ValueError('Versatility actual Move completion observations changed')


def _trigger(engine,subject):
    validate_actor(subject)
    row=subject.spec.get(WINDOW)
    if (not engine.encounter_active or engine.round_start_seconds is None or engine._active_turn_actor is not subject
            or engine._ordinary_turn_rounds.get(subject)!=engine.round_no or row is None
            or row.get('sha256')!=_seal(row) or row['actor_id']!=subject.entity_id
            or [row['encounter'],row['round'],row['turn'],row['scene']]!=[engine._party_encounter_epoch,engine.round_no,
                subject.custom_conditions.get('combat_turn_serial',0),subject.spec.get('frequency_state',{}).get('scene',0)]
            or subject._turn_start_decisions_pending):
        raise ValueError('Versatility requires the actual native Initiative or Pokemon turn-start trigger')
    # Simultaneous passive/Free start effects do not consume this trigger. An
    # ordinary action or a real (even Free) Move activation advances past it.
    if (any(action!='free' for action in subject._action_history[row['history_index']:])
            or any(uid not in row['move_ids'] and completion['actor'] is subject
                   for uid,completion in getattr(engine,'_move_completions',{}).items())):
        raise ValueError('Versatility turn-start trigger has already passed')


def use(engine,actor,give_move,restore_move,*,pokemon=None,edition='core'):
    import trainer_feature_acquisition as T,action_points as AP,action_lifecycle as ACTION,pokemon_activities as P
    feature=COMMAND if pokemon is not None else FIGHTER
    W.require_actors(engine,actor,*(() if pokemon is None else (pokemon,)))
    T.validate_actor(actor)
    if not records(actor,feature):raise ValueError('actual acquired Versatility Feature required')
    source(engine.r,feature,edition)
    subject=actor if pokemon is None else pokemon
    if pokemon is not None:P._pokemon(subject);P._owner(actor,subject)
    give_move=engine.r.move_id(give_move);restore_move=engine.r.move_id(restore_move)
    def apply(e,trainer,*others):
        target=others[0] if others else trainer
        _trigger(e,target)
        if give_move==restore_move:raise ValueError('Versatility requires two different Moves')
        _,give_kind=F.preflight_forfeit_move(e,target,give_move,source=feature)
        _,restore_kind=F.preflight_restore_move_use(e,target,restore_move)
        if give_kind=='scene' and restore_kind=='daily':raise ValueError('Scene to Daily exchange is forbidden')
        if not F.activation_allowed(target,feature,SCENE,engine=e,action_actor=trainer):
            raise ValueError('Versatility is once per Scene for its actual subject')
        if pokemon is not None and AP.available(trainer)<1:raise ValueError('Command Versatility requires 1 AP')
        ACTION.triggered_free_action(e,trainer,feature)
        if pokemon is not None:AP.spend(trainer,1)
        forfeiture=F.forfeit_move(e,target,give_move,source=feature)
        if restore_kind=='scene':F.restore_scene_use(e,target,restore_move)
        else:F.restore_daily_use(e,target,restore_move)
        F.consume_activation(target,feature,SCENE,engine=e,action_actor=trainer)
        return {'source':feature,'actor_id':trainer.entity_id,'subject_id':target.entity_id,
                'give_move':give_move,'restore_move':restore_move,'forfeiture':forfeiture}
    return G.transition(engine,actor,apply,participants=() if pokemon is None else (pokemon,))
