"""Berserker receipts compose native acquisition, injury, hit and turn owners."""
from copy import deepcopy
from functools import wraps
from hashlib import sha256
from pathlib import Path
import csv
import json

import common_checks as C
import state_grants as G

CLASS='supp-fantasy/버서커'
POWER='feat/분노의-힘'; LESSONS='feat/분노와-고통의-교훈'; FRENZY='feat/광란'
FIGHT='feat/전투지속'; CRASH='feat/충격과-박살'; LIMIT='feat/극한'
BOOK_SHA='a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
FEATURES={CLASS:(542,544),POWER:(546,550),LESSONS:(552,556),FRENZY:(558,563),
          FIGHT:(565,570),CRASH:(572,576),LIMIT:(578,583)}
CSV_ROWS={u:544+n for n,u in enumerate(FEATURES)}
PARENTS={CLASS:(),POWER:(CLASS,),LESSONS:(CLASS,),FRENZY:(CLASS,),FIGHT:(LESSONS,),CRASH:(FRENZY,),LIMIT:(LESSONS,)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[533,584] if u==CLASS else list(s),
    'clause_id':'FAN-'+str(66+n).zfill(3),'class_template':CLASS,'minimum_level':0,'skill':None,
    'source':{'file':'input/supp-fantasy.md','sha256':BOOK_SHA}} for n,(u,s) in enumerate(FEATURES.items())}
MOVE_NAMES={CLASS:('바둥바둥','분노'),CRASH:('이판사판태클','난동부리기')}
FRENZY_STATE='berserker_frenzy'
FIGHT_STATE='berserker_fight_on'


def records(actor,feature=None,active=False):
    import trainer_feature_acquisition as T
    return [r for _,r in T.static_family_acquisitions(actor,FEATURES,feature,active=active)]


def acquired(actor,feature=CLASS):
    rows=records(actor,feature,True)
    return rows[-1] if rows else None


def source(rules,feature,edition):
    from source_context import verified_source
    if feature not in FEATURES or edition not in ('supplement','local_csv'):
        raise ValueError('exact Berserker Feature and source edition required')
    if rules._selected_rule(feature)!=feature or feature in rules.ruleset.unit_versions:
        raise ValueError('selected Berserker source needs its explicit adapter')
    verified_source(rules,{'file':'input/supp-fantasy.md','sha256':BOOK_SHA},label='Berserker supplement')
    result={'edition':edition,'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'span':list(FEATURES[feature])}
    if edition=='local_csv':
        verified_source(rules,{'file':'input/db/feats.csv','sha256':CSV_SHA},label='Berserker CSV')
        with (Path(rules.root)/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as stream:
            cells=list(csv.reader(stream))[CSV_ROWS[feature]-1]
        rules.ruleset.require({'id':'C2CSV/input/db/feats.csv:R'+str(CSV_ROWS[feature])+':main',
            'source':{'file':'db/feats.csv','record_span':[CSV_ROWS[feature]]*2}})
        result.update(file='input/db/feats.csv',sha256=CSV_SHA,row=CSV_ROWS[feature],
            cells_sha256=sha256(json.dumps(cells,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    return result


def static_source(rules,feature):
    source(rules,feature,'supplement')
    actual=rules.selection.units[feature].get('source',{})
    if actual.get('file')!='supp-fantasy.md' or actual.get('lines')!=DEFINITIONS[feature]['catalog_span'] or actual.get('sha256')!=BOOK_SHA:
        raise ValueError('exact original Berserker catalog source required')
    return dict(DEFINITIONS[feature]['source'],clause_id=DEFINITIONS[feature]['clause_id'],span=list(FEATURES[feature]))


def acquisition_snapshot(e,actor,feature,rank,selection):
    import skill_modifiers as SK
    keys={'edition','ability'} if feature==POWER else {'edition'}
    if rank is not None or type(selection)is not dict or set(selection)!=keys:
        raise ValueError('explicit Berserker edition and printed Power of Rage choice required')
    if feature==POWER:
        __import__('feature_ability_grants')._ability(e.r,POWER,selection['ability'])
    return {'selection':deepcopy(selection),'source':source(e.r,feature,selection['edition']),
        'skills':{s:SK.rank(e.r,actor,s)[2] for s in ('전투','협박')},
        'parents':[r['request_id'] for r in records(actor,active=True) if r['feature_id'] in PARENTS[feature]]}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot)is not dict or set(snapshot)!={'selection','source','skills','parents'}:
        raise ValueError('exact Berserker acquisition observations required')
    chosen=snapshot['selection'];keys={'edition','ability'} if feature==POWER else {'edition'}
    if type(chosen)is not dict or set(chosen)!=keys or snapshot['source']!=source(actor.r,feature,chosen['edition']):
        raise ValueError('Berserker acquisition selection/source changed')
    if feature==POWER:__import__('feature_ability_grants')._ability(actor.r,POWER,chosen['ability'])
    skills=snapshot['skills']
    if type(skills)is not dict or set(skills)!={'전투','협박'}:raise ValueError('actual acquired Combat and Intimidate ranks required')
    for value in skills.values():C.integer(value,'acquired Berserker skill rank',1)
    history={r['request_id']:r['feature_id'] for r in records(actor)}
    parents=snapshot['parents']
    if type(parents)is not list or len(set(parents))!=len(parents) or not set(parents)<=set(history):
        raise ValueError('actual Berserker parent receipts required')
    combat=3 if feature==CLASS else 4 if feature in (FRENZY,FIGHT) else (4 if chosen['edition']=='local_csv' else 5) if feature==CRASH else 0
    intimidate=3 if feature==CLASS else 4 if feature==LESSONS else 5 if feature==LIMIT else 0
    return Q.require(feature,'native','acquire',[
        Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),
        Q.check('parents','prerequisite',set(PARENTS[feature])<={history[r] for r in parents},'printed Berserker parents required'),
        Q.check('combat','prerequisite',skills['전투']>=combat,'printed Combat rank required'),
        Q.check('intimidate','prerequisite',skills['협박']>=intimidate,'printed Intimidate rank required')])


def prepare_acquire(e,actor,selection):
    # The existing projection creates its own authoritative feature source.
    # TFA then attaches the actual acquisition receipt to that same source.
    actor.spec.setdefault('feature_choices',{})[POWER]=[selection['ability']]
    __import__('feature_ability_grants').register_all(e,actor)


def after_acquire(e,actor,feature,sid):
    G.stat(actor,'hp',1,sid,operation_id='acquisition_stat_tag')
    if feature in MOVE_NAMES:
        G.grant_moves(actor,[e.r.move_id(name) for name in MOVE_NAMES[feature]],sid,'feature',
            owner_id=actor.entity_id,lifetime='while_owned',rule_id=feature)


def validate_acquisition(actor,record,sid,active):
    if not active:return
    state=actor.spec.get(G.KEY,{})
    if state.get('stat_sources',{}).get('hp',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:
        raise ValueError('actual Berserker HP stat tag required')
    feature=record['feature_id']
    if feature in MOVE_NAMES:
        expected=[actor.r.move_id(name) for name in MOVE_NAMES[feature]]
        if state.get('sources',{}).get(sid,{}).get('grants',{}).get('moves')!=expected:
            raise ValueError('actual learned Berserker Moves required')
    if feature==POWER and actor.spec.get('feature_choices',{}).get(POWER)!=[record['snapshot']['selection']['ability']]:
        raise ValueError('immutable actual Power of Rage ability choice required')


def lessons(actor):return acquired(actor,LESSONS) is not None


def move_interested(e,actor,target):
    return bool(acquired(actor,LIMIT) or any(acquired(c,FIGHT) for c in e.everyone))


def frenzy_bonus(actor):
    row=actor.custom_conditions.get(FRENZY_STATE)
    receipt=acquired(actor,FRENZY) if row else None
    return 2 if receipt and row=={'request_id':receipt['request_id'],'serial':actor.custom_conditions.get('combat_turn_serial',0)} else 0


def end_turn(actor):actor.custom_conditions.pop(FRENZY_STATE,None)


def frenzy(e,actor,*,request_id):
    import initiative_interrupts as I,action_lifecycle as A,frequency as F,turn as TURN
    __import__('world_entities').require_actors(e,actor)
    receipt=acquired(actor,FRENZY)
    if receipt is None:raise ValueError('actual Frenzy acquisition required')
    if type(request_id)is not str or not request_id.strip():raise ValueError('actual Frenzy request identity required')
    quota={'kind':'scene','uses':2}
    def apply(se,a):
        if '난동' not in a.conditions:raise ValueError('Frenzy requires actual Enraged condition')
        if not TURN.can_act(se,a) or not A.status_permission(se,a,'free'):raise ValueError('Frenzy Free Action unavailable')
        if __import__('effect_lifetimes').forbids(a,'priority'):raise ValueError('current effect prohibits Priority actions')
        trigger=I.between_trigger(se)
        if I._loan_location(se,a)[2]!=se.round_no:raise ValueError('plain Priority requires this-round unacted turn right')
        if not F.activation_allowed(a,FRENZY,quota,engine=se):raise ValueError('Frenzy scene frequency exhausted')
        row={'id':request_id,'actor_id':a.entity_id,'source':FRENZY,'priority':0,
            'mode':'borrow_turn','payment':'future_turn','budget':None,'clock':'owner_turn','settlement_clock':'none'}
        queued=I.queue(se,[row],trigger=trigger)
        A.triggered_free_action(se,a,FRENZY)
        F.consume_activation(a,FRENZY,quota,engine=se)
        se.cure_status(a,'둔화');se.cure_status(a,'구속')
        I.begin(se,queued['window_id'],request_id)
        a.custom_conditions[FRENZY_STATE]={'request_id':receipt['request_id'],'serial':a.custom_conditions['combat_turn_serial']}
        return {'source':FRENZY,'window_id':queued['window_id'],'request_id':request_id}
    return G.transition(e,actor,apply,include_rulings=True,include_grid=e.grid is not None)


def conscious(actor):
    row=actor.custom_conditions.get(FIGHT_STATE)
    receipt=acquired(actor,FIGHT) if row else None
    return bool(not actor.dead and '기절' not in actor.conditions and receipt and row.get('request_id')==receipt['request_id']
        and row.get('active')is True and actor.hp<=0 and 2*actor.hp>-actor.base_max_hp)


def faint_boundary(e,actor):
    import frequency as F,action_lifecycle as A
    if actor.hp>0:
        actor.custom_conditions.pop(FIGHT_STATE,None);return False
    if conscious(actor):return True
    receipt=acquired(actor,FIGHT)
    if (receipt is None or actor.dead or '기절' in actor.conditions or 2*actor.hp<=-actor.base_max_hp
            or '난동' not in actor.conditions or not actor.on_field or actor.captured):return False
    quota={'kind':'daily','uses':1};bypass=actor.injuries>=5
    if not bypass and not F.activation_allowed(actor,FIGHT,quota,engine=e):return False
    if not A.status_permission(e,actor,'free'):return False
    answer=e.rulings.decide({'type':'berserker_fight_on','unit':FIGHT,'actor':actor.name,
        'actor_id':actor.entity_id,'hp':actor.hp,'maximum_hp':actor.base_max_hp,'injuries':actor.injuries,
        'text':'Use Fight On and On before fainting? Five injuries ignores its daily frequency.'})
    if answer is None or answer is False:return False
    if answer is not True:raise ValueError('explicit Fight On use or decline required')
    actor.custom_conditions[FIGHT_STATE]={'request_id':receipt['request_id'],'active':True}
    A.triggered_free_action(e,actor,FIGHT)
    if not bypass:F.consume_activation(actor,FIGHT,quota,engine=e)
    return True


def weapon_move(e,actor,move,weapon_id):
    learned={actor.r.move_id(name):feature for feature,names in MOVE_NAMES.items() for name in names}
    feature=learned.get(move['id'])
    explicit=weapon_id is not None or '_berserker_weapon' in move
    if not feature or not explicit:return None
    if acquired(actor,feature)is None:raise ValueError('actual learned Berserker weapon Move acquisition required')
    import turn as TURN,weapon_actions as WA,wielder_capability as W,living_weapon as L
    ledger=actor.custom_conditions.get('equipped_weapons',{})
    selected=weapon_id if weapon_id is not None else move['_berserker_weapon']
    choices=[(k,r['weapon']) for k,r in ledger.items() if selected in (k,r.get('instance_id'),r['weapon']['name'])]
    if len(choices)!=1:raise ValueError('one actually equipped melee weapon required')
    key,weapon=choices[0]
    if '근접' not in TURN.WEAPON_KIND[weapon['kind']]['range']:raise ValueError('Berserker Moves require a melee weapon')
    if not L.require_weapon(e,actor,weapon):W.require_weapon(e,actor,weapon)
    if move['id'] not in __import__('move_capabilities').learned_ids(actor):raise ValueError('actually learned Berserker Move required')
    raw=deepcopy(e.r.move(move['id']));raw['range']='WR, 대상 1'
    out=WA.adapt_weapon_move(e,actor,raw,key,weapon);out['_berserker_weapon']=key
    return out


def damage_bonus(e,actor,target,move):
    if not lessons(actor) or actor.injuries<1:return 0
    import skill_modifiers as SK
    if move['id'] not in {actor.r.move_id(n) for n in ('분노','바둥바둥','마구할퀴기','난동부리기')} and not move.get('_weapon_attack'):
        return 0
    value=SK.rank(e.r,actor,'협박')[2]+actor.injuries
    live=getattr(e,'_berserker_hit',None)
    if live and live['actor']is actor and live['target']is target and live['move_id']==move['id'] and live['push']:
        value*=2
    return value


def native_hit(fn):
    @wraps(fn)
    def run(e,actor,target,move_id,move,*args,**kwargs):
        previous=getattr(e,'_berserker_hit',None)
        scope={'actor':actor,'target':target,'move_id':move_id,'push':False}
        e._berserker_hit=scope
        try:
            row=e._move_completions[kwargs['completion_id']]
            eligible=move_id in {actor.r.move_id(n) for names in MOVE_NAMES.values() for n in names} or bool(move.get('_weapon_attack'))
            if acquired(actor,LIMIT) and eligible and move['class'] in ('물리','특수') and not row.get('berserker_push_offered'):
                row['berserker_push_offered']=True
                answer=e.rulings.decide({'type':'berserker_push_limit','unit':LIMIT,'actor':actor.name,
                    'actor_id':actor.entity_id,'target_id':target.entity_id,'move_id':move_id,
                    'text':'Gain one Injury before resolving this hit, one Tick temporary HP, and double Lessons bonus? Select one actual Persistent Affliction to cure, or None.'})
                if answer is not None and answer is not False:
                    import status_sets as S
                    if (type(answer)is not dict or set(answer)!={'cure_persistent'}
                            or (answer['cure_persistent'] is not None and answer['cure_persistent'] not in S.afflictions(actor,'persistent'))):
                        raise ValueError('explicit Push Limit use and one actual optional persistent cure required')
                    import action_lifecycle as A,precise_actions as P,temporary_hp as H,status_sets as S
                    A.triggered_free_action(e,actor,LIMIT)
                    before=actor.injuries;P.gain_injury(e,actor,1,LIMIT)
                    H.grant(e,actor,e.tick(actor),provenance={'source':LIMIT,'completion':row['id']})
                    if answer['cure_persistent'] is not None:e.cure_status(actor,answer['cure_persistent'])
                    row['berserker_push']={'before':before,'after':actor.injuries,'target_id':target.entity_id}
                    e.check_fainted(actor)
            e._berserker_hit['push']='berserker_push' in row
            return fn(e,actor,target,move_id,move,*args,**kwargs)
        finally:
            if previous is None:vars(e).pop('_berserker_hit',None)
            else:e._berserker_hit=previous
    return run
