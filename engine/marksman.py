"""Marksman acquisitions and native weapon attacks; shared owners keep costs and state."""
from copy import deepcopy
from contextlib import contextmanager
from functools import wraps
from hashlib import sha256
from pathlib import Path
import csv
import json

import state_grants as G
import world_entities as W

CLASS='supp-fantasy/명사수'
AIM='feat/시야-아래-조준'; DOUBLE='feat/더블-샷'; WATCH='feat/감시'
CLEAR='feat/클리어-샷'; CRIPPLE='feat/크리플링-샷'; DEAD='feat/데드아이-샷'
BOOK_SHA='a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266'
CSV_SHA='4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'
FEATURES={CLASS:(797,799),AIM:(801,805),DOUBLE:(807,811),WATCH:(813,817),CLEAR:(819,824),CRIPPLE:(826,830),DEAD:(832,836)}
CSV_ROWS={u:573+i for i,u in enumerate(FEATURES)}
CLAUSES={u:'FAN-'+str(103+i) for i,u in enumerate(FEATURES)}
DEFINITIONS={u:{'span':list(s),'catalog_span':[788,837] if u==CLASS else list(s),
    'clause_id':CLAUSES[u],'class_template':CLASS,'minimum_level':0,'skill':None,
    'source':{'file':'input/supp-fantasy.md','sha256':BOOK_SHA}} for u,s in FEATURES.items()}
ARM='marksman_attack_choice'; WATCH_STATE='marksman_overwatch'; DEAD_STATE='marksman_deadeye'
WEAPON_ACTION='marksman_weapon_action'
CORE_SNIPER='ability/스나이퍼-core105'; CORE_SNIPER_NAME='스나이퍼 (Core 1.05)'
PLAYTEST_SNIPER='ability/스나이퍼-playtest'
SNIPER_TEXT='Static Effect: When the Pokémon gets a Critical Hit, add the value of the Damage Dice Roll an additional time to the total damage.'


def install(rules):
    """Derive the missing core identity from the printed class; never alias Playtest."""
    from ruleset import ExcludedRuleSelection
    try:rules.selection.resolve(CLASS)
    except ExcludedRuleSelection:return
    source(rules,CLASS,'supplement')
    body=(Path(rules.root)/'source-audit/core-marksman-sniper.txt').read_text(encoding='utf-8')
    if body.splitlines()!=['Ability: Sniper',SNIPER_TEXT]:raise ValueError('exact primary core Sniper body required')
    unit={'id':CORE_SNIPER,'title':CORE_SNIPER_NAME,'eng':'Sniper (Core 1.05)','kind':'entity:ability',
          'source':{'file':'supp-fantasy.md','lines':[797,799],'sha256':BOOK_SHA,
                    'official_body':{'file':'source-audit/core-marksman-sniper.txt','sha256':sha256(body.encode()).hexdigest()}},'tags':['source-scoped','core-105-body']}
    if CORE_SNIPER not in rules.selection.units:rules.selection.register_derived(unit,(CLASS,))
    if rules.selection.units[CORE_SNIPER]['source']!=unit['source']:raise ValueError('core Sniper derived identity changed')
    definition={'id':CORE_SNIPER,'name':CORE_SNIPER_NAME,'eng':'Sniper (Core 1.05)','frequency':'항상',
                'effect':SNIPER_TEXT,'effects':[],'source':unit['source'],
                'official_source':{'extract':'source-audit/core-marksman-sniper.txt','sha256':sha256(body.encode()).hexdigest(),'lines':[1,2]},
                'native_contract':{'type':'marksman_core','critical_extra_dice_rolls':1}}
    old=rules.core_abilities.get(CORE_SNIPER)
    if old is not None and old!=definition:raise ValueError('core Sniper body cannot overwrite another source')
    rules.core_abilities[CORE_SNIPER]=definition
    rules.ability_freq[CORE_SNIPER_NAME]='항상';rules.ability_effects[CORE_SNIPER_NAME]=[]


def sniper_policy(actor):
    import ability_transitions as A
    core=any(x in (CORE_SNIPER_NAME,CORE_SNIPER) for x in actor.abilities)
    playtest=any(x in ('스나이퍼 [Playtest]',PLAYTEST_SNIPER) for x in actor.abilities)
    core=core and A.active(actor,CORE_SNIPER_NAME);playtest=playtest and A.active(actor,'스나이퍼 [Playtest]')
    if core and playtest:raise ValueError('choose one actual Sniper edition, not stacked core and Playtest')
    return 'core_105' if core else 'feb2016_playtest' if playtest else None


def records(actor,feature=None,active=False):
    return [r for _,r in __import__('trainer_feature_acquisition').static_family_acquisitions(actor,FEATURES,feature,active=active)]


def acquired(actor,feature):
    rows=records(actor,feature,True)
    return rows[-1] if rows else None


def source(rules,feature,edition):
    from source_context import verified_source
    if feature not in FEATURES or edition not in ('supplement','local_csv'):raise ValueError('exact Marksman source edition required')
    if rules._selected_rule(feature)!=feature or feature in rules.ruleset.unit_versions:raise ValueError('selected Marksman source needs its own adapter')
    verified_source(rules,{'file':'input/supp-fantasy.md','sha256':BOOK_SHA},label='Marksman supplement')
    result={'edition':edition,'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'span':list(FEATURES[feature])}
    if edition=='local_csv':
        verified_source(rules,{'file':'input/db/feats.csv','sha256':CSV_SHA},label='Marksman CSV')
        row=CSV_ROWS[feature]
        with (Path(rules.root)/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as stream:cells=list(csv.reader(stream))[row-1]
        rules.ruleset.require({'id':'C2CSV/input/db/feats.csv:R'+str(row)+':main','source':{'file':'db/feats.csv','record_span':[row,row]}})
        result.update(file='input/db/feats.csv',sha256=CSV_SHA,row=row,cells_sha256=sha256(json.dumps(cells,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    return result


def static_source(rules,feature):
    source(rules,feature,'supplement')
    unit=rules.selection.units[feature]['source']
    if unit.get('file')!='supp-fantasy.md' or unit.get('lines')!=DEFINITIONS[feature]['catalog_span']:raise ValueError('exact Marksman catalog span required')
    return {'file':'input/supp-fantasy.md','sha256':BOOK_SHA,'clause_id':CLAUSES[feature],'span':list(FEATURES[feature])}


def validate_selection(feature,rank,selection):
    extra={CLASS:'sniper',AIM:'weapon_scope',CRIPPLE:'trip_policy',DEAD:'release_policy'}.get(feature)
    if rank is not None or type(selection)is not dict or set(selection)!=({'edition',extra} if extra else {'edition'}):raise ValueError('explicit Marksman edition and printed source choice required')
    if feature==CLASS and selection['sniper'] not in ('core_105','feb2016_playtest'):raise ValueError('select the actual Sniper source')
    if feature==AIM and selection['weapon_scope'] not in ('korean_ranged','english_long_range'):raise ValueError('select the S-001 Aiming weapon scope')
    if feature==CRIPPLE and selection['trip_policy'] not in ('korean_optional_trip','english_required_trip'):raise ValueError('select the S-001 Crippling Trip policy')
    if feature==DEAD and selection['release_policy'] not in ('korean_shift_attack','english_optional_shift'):raise ValueError('select the S-001 Dead-Eye Shift policy')


def acquisition_snapshot(e,actor,feature,rank,selection):
    import skill_modifiers as S,acquired_features as A
    validate_selection(feature,rank,selection)
    return {'selection':deepcopy(selection),'source':source(e.r,feature,selection['edition']),
        'combat':S.rank(e.r,actor,'전투')[2],'perception':S.rank(e.r,actor,'통찰')[2],
        'parent_owned':feature==CLASS or bool(A.owned_rule_count(actor,CLASS))}


def qualification(actor,feature,snapshot,prerequisite_source):
    import acquisition_qualification as Q,common_checks as C
    s=snapshot
    if prerequisite_source is not None or type(s)is not dict or set(s)!={'selection','source','combat','perception','parent_owned'}:raise ValueError('exact Marksman acquisition observations required')
    validate_selection(feature,None,s['selection'])
    if s['source']!=source(actor.r,feature,s['selection']['edition']):raise ValueError('Marksman acquisition source changed')
    for key in ('combat','perception'):C.integer(s[key],'actual acquired '+key,1)
    if type(s['parent_owned'])is not bool:raise ValueError('actual Marksman parent observation required')
    skill=(s['combat']>=3 and s['perception']>=3) if feature==CLASS else s['combat']>=4 if feature==DOUBLE else max(s['combat'],s['perception'])>={AIM:0,WATCH:4,CLEAR:5,CRIPPLE:5,DEAD:6}[feature]
    return Q.require(feature,'native','acquire',[Q.check('trainer','prerequisite',actor.kind=='trainer','actual Trainer required'),Q.check('parent','prerequisite',s['parent_owned'],'actual Marksman prerequisite required'),Q.check('skills','prerequisite',skill,'printed Marksman skill ranks required')])


def after_acquire(e,actor,feature,sid):
    G.stat(actor,'atk',1,sid,operation_id='acquisition_stat_tag')
    if feature==CLASS:
        sniper=acquired(actor,CLASS)['snapshot']['selection']['sniper']
        G.grant(actor,'abilities',CORE_SNIPER_NAME if sniper=='core_105' else '스나이퍼 [Playtest]',sid,'feature',owner_id=actor.entity_id,lifetime='while_owned',rule_id=feature)


def validate_acquisition(actor,record,sid,active):
    if active and actor.spec.get(G.KEY,{}).get('stat_sources',{}).get('atk',{}).get('sources',{}).get(sid,{}).get('acquisition_stat_tag')!={'delta':1,'minimum':None}:raise ValueError('actual Marksman Attack tag required')


def require(e,actor,feature):
    W.require_actors(e,actor)
    row=acquired(actor,feature)
    if row is None or not __import__('acquired_features').owned_rule_count(actor,feature):raise ValueError('actual acquired Marksman Feature required: '+feature)
    source(e.r,feature,row['snapshot']['selection']['edition'])
    __import__('trainer_feature_acquisition').validate_actor(actor)
    if actor.fainted or actor.dead or actor.captured or not actor.on_field:raise ValueError('available actual Marksman required')
    return row


def aim_applies(actor,move):
    row=acquired(actor,AIM)
    if row is None or row['snapshot']['selection']['weapon_scope']=='korean_ranged':return True
    key=move.get('_weapon_attack',{}).get('key')
    entry=actor.custom_conditions.get('equipped_weapons',{}).get(key)
    return bool(entry and entry['weapon']['kind']=='장거리 사격무기')


def aim(e,actor):
    require(e,actor,AIM)
    return e.activate_optional_state_effect(actor,'FAN-104')


def atomic_move(fn):
    @wraps(fn)
    def run(e,actor,*args,**kwargs):
        if not actor.spec.get(ARM) or getattr(e,'_marksman_atomic',False):return fn(e,actor,*args,**kwargs)
        pending=[]
        def apply(se,a):
            copied_args,copied_kwargs=G._stage_transition_payload(e,se,(args,kwargs))
            se._marksman_atomic=True
            try:
                if getattr(se,'_marksman_attack',None):return fn(se,a,*copied_args,**copied_kwargs)
                with attack_scope(se,a,copied_args[0],se.r.move_id(copied_args[1]),CLEAR):
                    return fn(se,a,*copied_args,**copied_kwargs)
            except Exception as error:
                if G.record_native_pending(se,error,pending):return None
                raise
            finally:del se._marksman_atomic
        result=G.transition(e,actor,apply,include_grid=e.grid is not None,include_rulings=True)
        if pending:
            exception,event_id=pending[0];raise exception(event_id)
        return result
    return run


def weapon(e,actor,weapon_id,move_id=None,*,struggle=False):
    import weapon_actions as WA
    ledger=actor.custom_conditions.get('equipped_weapons',{})
    choices=[(k,r) for k,r in ledger.items() if weapon_id in (k,r.get('instance_id'),r['weapon']['name'])]
    if len(choices)!=1:raise ValueError('one actually equipped ranged weapon required')
    key,row=choices[0];mid=row['struggle_id'] if struggle or move_id is None else e.r.move_id(move_id)
    move=WA.prepare(e,actor,e.r.move(mid),key)
    rng=WA.range_spec(e,move,actor)
    if type(rng.get('origin'))is not int or rng['origin']<=0 or not move.get('_weapon_attack'):raise ValueError('actual ranged Weapon Attack required')
    if rng.get('targets')!=1 or rng.get('shape'):raise ValueError('Marksman selected attack needs one actual target')
    return key,mid,move,rng


def arm_clear(e,actor,move_id,weapon_id):
    require(e,actor,CLEAR);key,mid,_,_=weapon(e,actor,weapon_id,move_id)
    return G.transition(e,actor,lambda se,a:a.spec.update({ARM:{'move_id':mid,'weapon_id':key}}))


def clear_eligible(e,actor,target):
    import body_state as B
    from grid import cheb
    if e.grid is None:raise ValueError('Clear Shot requires actual mapped terrain and combatants')
    cells=B.cells(target,require_complete=True)
    for other in W.actor_index(e).values():
        if other is target or not other.on_field or other.captured:continue
        if min(cheb(a,b) for a in cells for b in B.cells(other,require_complete=True))<=2:return False
    return not any(min(cheb(a,b) for a in cells)<=2 for b in e.grid.blocking|e.grid.rough)


def clear_begin(e,actor,target,move):
    selected=actor.spec.get(ARM)
    if not selected:return False
    if selected!={'move_id':move['id'],'weapon_id':move.get('_weapon_attack',{}).get('key')}:return False
    require(e,actor,CLEAR)
    if not clear_eligible(e,actor,target):raise ValueError('Clear Shot target must have no combatants or Rough or Blocking Terrain within two metres')
    import frequency as F,turn as T
    quota={'kind':'scene','uses':2}
    if not F.activation_allowed(actor,CLEAR,quota,engine=e):raise ValueError('Clear Shot Scene frequency exhausted')
    if not T.spend(e,actor,'swift',CLEAR):raise ValueError('Clear Shot requires its Swift Action')
    F.consume_activation(actor,CLEAR,quota,engine=e);actor.spec.pop(ARM)
    return True


@contextmanager
def attack_scope(e,actor,target,mid,feature,**values):
    previous=getattr(e,'_marksman_attack',None)
    scope={'actor':actor,'target':target,'move_id':mid,'feature':feature,**values}
    e._marksman_attack=scope
    try:yield scope
    finally:
        current=getattr(e,'_marksman_attack',None)
        completion=getattr(e,'_move_completions',{}).get((current or {}).get('completion_id'))
        if completion is not None and completion['phase']!='complete':
            current['suspended']=True
        elif previous is None:vars(e).pop('_marksman_attack',None)
        else:e._marksman_attack=previous


def scope(e,actor,target,move):
    row=getattr(e,'_marksman_attack',None)
    return row if row and row['actor']is actor and row['target']is target and row['move_id']==move['id'] else None


def authority(e,actor,target,mid,source):
    row=scope(e,actor,target,{'id':mid})
    return bool(row and row['feature']==source and source in (DOUBLE,CRIPPLE,WATCH,DEAD) and not row.get('grant_used'))


def begin_move(e,completion):
    current=scope(e,completion['actor'],completion['targets'][0],completion['move'])
    if current is None:return
    current['completion_id']=completion['id']
    completion['marksman_attack']={k:deepcopy(v) for k,v in current.items() if k not in ('actor','target')}
    if current['feature']==WATCH:
        watched=watch_state(e,completion['actor']);target=completion['targets'][0]
        if watched is None or target.entity_id not in watched['targets']:raise ValueError('actual Overwatch moving-foe activation required')
        owner=e._active_turn_actor
        proof={'source':WATCH,'actor_id':completion['actor'].entity_id,'target_id':target.entity_id,
            'owner_id':None if owner is None else owner.entity_id,'completion_id':completion['id'],'round':e.round_no}
        completion['marksman_attack']['watch_reaction']={'facts':proof,'fingerprint':__import__('root_resolution').fingerprint(proof)}
    actor=completion['actor'];operation=actor.spec.get(WEAPON_ACTION)
    if operation and operation['feature']==current['feature']:
        operation['completions'][str(operation['stage'])]=completion['id']
    if current['feature']==DEAD:actor.spec[DEAD_STATE]['completion_id']=completion['id']


def after_complete(e,completion):
    current=getattr(e,'_marksman_attack',None)
    if current and current.get('completion_id')==completion['id'] and current.get('suspended'):
        vars(e).pop('_marksman_attack',None)


def observed_attack(completion,target):
    import move_completion as MC
    data=deepcopy(completion['marksman_attack'])
    data['hit_recipients']=[recipient.entity_id for recipient in MC.actual_recipients(completion)
        if (actual:=MC.recipient_result(completion,recipient)) and actual['hit']
        and not actual.get('cancelled') and not actual.get('hit_prevented')]
    return bool(data['hit_recipients']),data


def native_attack(e,actor,target,key,mid,feature,**values):
    import action_lifecycle as A
    from common_checks import PendingDecision
    operation=actor.spec.get(WEAPON_ACTION)
    token=operation['completions'].get(str(operation['stage'])) if operation and operation['feature']==feature else actor.spec.get(DEAD_STATE,{}).get('completion_id') if feature==DEAD else None
    if token is not None:
        completion=getattr(e,'_move_completions',{}).get(token)
        if completion is None or completion['actor']is not actor or completion['move_id']!=mid or completion['targets']!=[target] or completion.get('marksman_attack',{}).get('feature')!=feature:raise ValueError('actual saved Marksman attack completion required')
        if completion['phase']!='complete':return PendingDecision('resume the actual native Marksman attack'),None
        return observed_attack(completion,target)
    with attack_scope(e,actor,target,mid,feature,**values) as row:
        try:
            with A.move_grant(e,actor,target,mid,source=feature,kind='free') as grant:
                e.use_move(actor,target,mid,weapon_id=key,free_action=True,count_use=True,_action_grant=grant)
        except Exception as error:
            if not G.record_native_pending(e,error,[]):raise
            return PendingDecision('resume the actual native Marksman attack'),None
        current=e._marksman_attack
        completion=getattr(e,'_move_completions',{}).get(current.get('completion_id'))
        if completion is None:raise ValueError('actual Marksman attack completion required')
        if completion['phase']!='complete':return PendingDecision('resume the actual native Marksman attack'),None
        return observed_attack(completion,target)


def weapon_operation(e,actor,target,key,mid,feature,options,cost,ap):
    """Only an unfinished native action is retained; its costs are never replayed."""
    intent={'feature':feature,'target_id':target.entity_id,'weapon_id':key,'move_id':mid,'options':deepcopy(options)}
    old=actor.spec.get(WEAPON_ACTION)
    if old is not None:
        if old['intent']!=intent or old['round']!=e.round_no:raise ValueError('resume the existing actual Marksman weapon action first')
        return old
    import turn as T,action_points as AP
    if AP.available(actor)<ap:raise ValueError(feature+' requires '+str(ap)+' AP')
    if not T.spend(e,actor,cost,feature):raise ValueError(feature+' requires its '+cost+' Action')
    AP.charge(actor,ap,mode='spend')
    row={'intent':intent,'feature':feature,'round':e.round_no,'stage':0,'completions':{},'results':[]}
    actor.spec[WEAPON_ACTION]=row
    return row


def double_shot(e,actor,target,weapon_id):
    require(e,actor,DOUBLE);W.require_actors(e,actor,target)
    key,mid,_,_=weapon(e,actor,weapon_id,struggle=True)
    def apply(se,a,t):
        from common_checks import PendingDecision
        op=weapon_operation(se,a,t,key,mid,DOUBLE,{},'standard',1)
        while op['stage']<2:
            data=op.get('first',{})
            values={} if op['stage']==0 else {'repeated_aim':data.get('aim',(0,0)),'clear':data.get('clear',False)}
            hit,data=native_attack(se,a,t,key,mid,DOUBLE,penalty=-2,**values)
            if isinstance(hit,PendingDecision):return hit
            op=a.spec[WEAPON_ACTION]
            if op['stage']==0:op['first']=data
            op['results'].append(hit);op['stage']+=1
        result=op['results'];a.spec.pop(WEAPON_ACTION)
        return result
    return G.transition(e,actor,apply,participants=(target,),include_rulings=True)


def crippling_shot(e,actor,target,weapon_id,*,use_trip,challenger_skill='전투',defender_skill='전투',fixed_accuracy=None,challenger_options=None,defender_options=None):
    acquisition=require(e,actor,CRIPPLE);W.require_actors(e,actor,target)
    if type(use_trip)is not bool:raise ValueError('explicit optional Crippling Shot Trip use or decline required')
    if acquisition['snapshot']['selection']['trip_policy']=='english_required_trip' and not use_trip:raise ValueError('English Crippling Shot requires its Trip on a hit')
    key,mid,_,rng=weapon(e,actor,weapon_id,struggle=True)
    def apply(se,a,t):
        from common_checks import PendingDecision
        options={'use_trip':use_trip,'challenger_skill':challenger_skill,'defender_skill':defender_skill,'fixed_accuracy':fixed_accuracy,'challenger_options':challenger_options,'defender_options':defender_options}
        weapon_operation(se,a,t,key,mid,CRIPPLE,options,'full',2)
        hit,data=native_attack(se,a,t,key,mid,CRIPPLE,penalty=-2)
        if isinstance(hit,PendingDecision):return hit
        if not hit:
            a.spec.pop(WEAPON_ACTION);return {'hit':False,'trip':None}
        if len(data['hit_recipients'])!=1:raise ValueError('single-target Crippling Shot requires one actual hit recipient')
        recipient=W.actor_index(se)[data['hit_recipients'][0]]
        operation=a.spec[WEAPON_ACTION]
        if not operation.get('hit_effects_applied'):
            se.apply_status(recipient,'둔화');se.change_stage(recipient,'spe',-1)
            operation['hit_effects_applied']=True
        if not use_trip:
            a.spec.pop(WEAPON_ACTION);return {'hit':True,'trip':None}
        import maneuver_opposed as M
        config={'geometry':{'range':rng['origin'],'remote':True,'vertical':False},'action_cost':'included','accuracy':'ordinary',
            'opposed':'required','success':'check','requirements':[],'challenger_skills':['전투','곡예','통찰'],
            'defender_skills':['전투','곡예'],'resistance_purpose':'resist_trip','challenger_purpose':None,
            'accuracy_class':'변화','opportunity':'none'}
        plans,prepared=M._prepare(se,a,recipient,'maneuver/걸기',(),challenger_skill,defender_skill,fixed_accuracy,challenger_options,defender_options,{'source':CRIPPLE},config=config)
        def outcome(won):
            if won:se.apply_status(recipient,'넘어짐')
            return won
        result=M._run(se,a,recipient,'maneuver/걸기',6,plans,prepared,outcome,fixed_accuracy,config=config)
        if isinstance(result,PendingDecision):return result
        a.spec.pop(WEAPON_ACTION)
        return {'hit':True,'trip':result}
    return G.transition(e,actor,apply,participants=(target,),include_rulings=True)


def accuracy_modifiers(e,actor,target,move,optional):
    row=scope(e,actor,target,move)
    clear=row.get('clear',False) if row else False
    clear=clear or clear_begin(e,actor,target,move)
    if row is not None:
        row['clear']=clear;row['aim']=optional
        completion=getattr(e,'_move_completions',{}).get(row.get('completion_id'))
        if completion is not None:completion['marksman_attack'].update(clear=clear,aim=optional)
        if row.get('repeated_aim'):optional=tuple(row['repeated_aim'])
    accuracy,critical=optional
    if row:accuracy+=row.get('penalty',0)
    if clear:critical+=4
    return accuracy,critical,clear


def resistance(e,actor,target,move):
    row=scope(e,actor,target,move)
    if row is None:
        row=getattr(e,'_marksman_attack',None)
        token=getattr(e,'_defense_recipient_scope',None)
        if not row or row['actor']is not actor or row['move_id']!=move['id'] or token is None:return 0
        # Damage precedes the stored receipt; use its actual native producer.
        __import__('move_defense_reactions').require_recipient(e,token,actor,target,move,row['completion_id'])
    return int(bool(row and row['feature']==CRIPPLE))


def sniper_dice(e,actor,move,crit,set_damage):
    if not crit or sniper_policy(actor)!='feb2016_playtest':return 0
    from source_context import verified_source
    verified_source(e.r,{'file':'input/db/abilities.csv','sha256':'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},label='actual February2016 Sniper')
    # The saved LLM string-dice declaration is not consumed by the generic
    # integer-only bonus_damage branch (effects.py and Engine.roll_damage).
    declaration=[{'type':'bonus_damage','value':'3d10','if':'crit'}]
    if e.r.ability_effects.get('스나이퍼 [Playtest]') not in ([],declaration):raise ValueError('Playtest Sniper has another damage consumer; review before combining')
    return 16 if set_damage else e.roll_expr('3d10',actor=actor,purpose='damage')[0]


def sniper_times(actor,crit):
    return int(bool(crit and sniper_policy(actor)=='core_105'))


def watch(e,actor,weapon_id,*,direction,blast_center):
    require(e,actor,WATCH)
    key,mid,_,rng=weapon(e,actor,weapon_id)
    if e.grid is None:raise ValueError('Overwatch requires mapped geometry')
    if type(direction) not in (tuple,list) or len(direction)!=2 or any(type(x)is not int or x not in (-1,0,1) for x in direction) or tuple(direction)==(0,0):raise ValueError('Overwatch needs one actual Line direction')
    if type(blast_center) not in (tuple,list) or len(blast_center)!=2 or any(type(x)is not int for x in blast_center) or not e.grid.inside(blast_center):raise ValueError('Overwatch needs one actual Blast center')
    line=e.grid.line(actor.pos,tuple(direction),rng['origin']);blast=e.grid.ranged_blast(tuple(blast_center),3)
    if len(line&blast)<3:raise ValueError('Overwatch Blast must overlap at least three Line metres')
    def apply(se,a):
        import turn as T,combat_timing as CLOCK
        if not T.spend(se,a,'standard',WATCH):raise ValueError('Overwatch requires its Standard Action')
        a.spec[WATCH_STATE]={'weapon_id':key,'origin':list(a.pos),'cells':[list(c) for c in sorted(line|blast)],
            'positions':{x.entity_id:list(x.pos) for x in W.actor_index(se).values() if x.location['kind']=='grid'},'used_round':se.round_no,'targets':[],
            'deadline':[se.round_no+1,CLOCK.current(se)]}
        return deepcopy(a.spec[WATCH_STATE])
    return G.transition(e,actor,apply)


def watch_state(e,actor):
    row=actor.spec.get(WATCH_STATE)
    if row is None:return None
    import combat_timing as CLOCK
    cursor=getattr(e,'_initiative_cursor',None);deadline=row['deadline']
    expired=e.round_no>deadline[0] or e.round_no==deadline[0] and cursor and cursor['round']==e.round_no and cursor['count']<=deadline[1]
    if acquired(actor,WATCH) is None or not __import__('acquired_features').owned_rule_count(actor,WATCH) or not e.encounter_active or not actor.on_field or actor.fainted or actor.dead or actor.captured or actor.location['kind']!='grid' or list(actor.pos)!=row['origin'] or expired:
        actor.spec.pop(WATCH_STATE,None);return None
    return row


def moved(e,mover):
    """Called by native paid/forced entry, including an exit from the watched area."""
    if mover.location['kind']!='grid':return
    for actor in W.actor_index(e).values():
        row=watch_state(e,actor)
        if row is None:continue
        origin=row['positions'].get(mover.entity_id);position=list(mover.pos)
        row['positions'][mover.entity_id]=position
        if origin is None or origin==position or mover is actor or mover.side==actor.side:continue
        cells={tuple(c) for c in row['cells']}
        if tuple(origin) not in cells and tuple(position) not in cells:continue
        if row['used_round']!=e.round_no:row.update(used_round=e.round_no,targets=[])
        if mover.entity_id in row['targets']:continue
        answer=e.rulings.decide({'type':'marksman_overwatch','unit':WATCH,'actor_id':actor.entity_id,'target_id':mover.entity_id,'text':'Choose one currently equipped ranged Weapon Move, or decline.'})
        if answer is None or answer is False:continue
        if type(answer)is not dict or set(answer)!={'weapon_id','move_id'}:raise ValueError('Overwatch needs an actual ranged Weapon Attack choice')
        require(e,actor,WATCH);key,mid,move,_=weapon(e,actor,answer['weapon_id'],answer['move_id'])
        import frequency as F,weapon_actions as WA
        if not F.move_allowed(e,actor,mid)[0]:continue
        WA.validate_target(e,actor,mover,move)
        row['targets'].append(mover.entity_id)
        result,_=native_attack(e,actor,mover,key,mid,WATCH)
        if isinstance(result,__import__('common_checks').PendingDecision):return result


def declare_deadeye(e,actor,*,request_id):
    require(e,actor,DEAD)
    import initiative_interrupts as I,frequency as F,turn as T
    old=actor.spec.get(DEAD_STATE)
    if old and old['request_id']==request_id:return deepcopy(old)
    if type(request_id)is not str or not request_id.strip():raise ValueError('actual Dead-Eye request identity required')
    trigger=I.between_trigger(e)
    if trigger['schedule_cursor']!=0 or any(r['round']==e.round_no for r in e._turn_closures) or old and old['round']==e.round_no:raise ValueError('Dead-Eye is declared once at actual round start')
    quota={'kind':'scene','uses':2}
    if not F.activation_allowed(actor,DEAD,quota,engine=e):raise ValueError('Dead-Eye Scene frequency exhausted')
    def apply(se,a):
        request={'id':request_id,'actor_id':a.entity_id,'source':DEAD,'priority':0,'mode':'reaction','payment':'next','budget':{'standard':1},'clock':'none'}
        queued=I.queue(se,[request],trigger=I.between_trigger(se));I.begin(se,queued['window_id'],request_id)
        if not T.spend(se,a,'standard',DEAD):raise ValueError('Dead-Eye declaration requires its Standard Action')
        I.finish(se);F.consume_activation(a,DEAD,quota,engine=se)
        a.spec[DEAD_STATE]={'request_id':request_id,'round':se.round_no,'phase':'declared','window_id':queued['window_id'],'completion_id':None}
        a.spec[DEAD_STATE]['declaration_fingerprint']=__import__('root_resolution').fingerprint({k:a.spec[DEAD_STATE][k] for k in ('request_id','round','window_id')})
        return deepcopy(a.spec[DEAD_STATE])
    return G.transition(e,actor,apply)


@contextmanager
def round_end_shift(e,actor):
    import initiative_interrupts as I
    request={'id':actor.spec[DEAD_STATE]['request_id']+'/shift','actor_id':actor.entity_id,'source':DEAD,
        'priority':0,'mode':'reaction','payment':'current','budget':{'shift':1},'clock':'none'}
    queued=I.queue(e,[request],trigger=I.between_trigger(e));I.begin(e,queued['window_id'],request['id'])
    try:yield
    finally:I.finish(e)


def deadeye_choice(e,actor,*,use,target=None,weapon_id=None,move_id=None,path=(),mode='land'):
    require(e,actor,DEAD)
    import initiative_schedule as S,focus_punch as P
    S.preflight_end_round(e)
    row=actor.spec.get(DEAD_STATE)
    if not row or row['round']!=e.round_no or row['phase']!='declared' or 'choice' in row or e._active_turn_actor is not None:raise ValueError('actual undecided round-end Dead-Eye declaration required')
    if type(use)is not bool:raise ValueError('explicit Dead-Eye use or decline required')
    if not use:
        if target is not None or weapon_id is not None or move_id is not None or path:raise ValueError('declined Dead-Eye cannot attack or Shift')
        row['choice']={'use':False};return deepcopy(row)
    W.require_actors(e,actor,target);key,mid,_,_=weapon(e,actor,weapon_id,move_id)
    row['choice']={'use':True,'target_id':target.entity_id,'weapon_id':key,'move_id':mid,'path':P.path_choice(path,mode),'mode':mode}
    return deepcopy(row)


def finish_round(e):
    for actor in W.actor_index(e).values():
        row=actor.spec.get(DEAD_STATE)
        if not row or row['round']!=e.round_no or row['phase'] not in ('declared','resolving'):continue
        if row['phase']=='resolving':
            completion=getattr(e,'_move_completions',{}).get(row['completion_id'])
            if completion is None or completion['phase']!='complete':return __import__('common_checks').PendingDecision('resume the actual native Dead-Eye attack')
            row['phase']='complete';continue
        if acquired(actor,DEAD) is None or actor.fainted or actor.dead or not actor.on_field:row['phase']='cancelled';continue
        choice=row.get('choice')
        if choice is None:raise ValueError('choose actual Dead-Eye round-end use or decline first')
        if not choice['use']:row['phase']='declined';continue
        import movement_actions as M,turn as T
        policy=acquired(actor,DEAD)['snapshot']['selection']['release_policy']
        # The Korean attack spends Shift; English may Shift before its free attack.
        if policy=='korean_shift_attack' or choice['path']:
            with round_end_shift(e,actor):
                if not T.spend(e,actor,'shift',DEAD):raise ValueError('Dead-Eye requires an available Shift Action')
                if choice['path']:M.follow_paid_path(e,actor,choice['path'],mode=choice['mode'],maximum_distance=M.capabilities(e,actor).get(choice['mode'],0))
        target=W.actor_index(e)[choice['target_id']]
        key,mid,_,_=weapon(e,actor,choice['weapon_id'],choice['move_id'])
        row['phase']='resolving'
        result,_=native_attack(e,actor,target,key,mid,DEAD,deadeye=True)
        if isinstance(result,__import__('common_checks').PendingDecision):return result
        actor.spec[DEAD_STATE]['phase']='complete'


def pending(e):
    return [(a,a.spec[DEAD_STATE]) for a in W.actor_index(e).values() if a.spec.get(DEAD_STATE,{}).get('round')==e.round_no and a.spec[DEAD_STATE]['phase'] in ('declared','resolving')]


def end_round(e):
    actor,row=pending(e)[0];target=W.actor_index(e).get(row.get('choice',{}).get('target_id'),actor)
    return __import__('reactive_ability_events').atomic_move(e,actor,target,lambda se,a,t:se._end_round())


def reaction_origin(e,event_id,*,live):
    event=getattr(e,'_passive_events',{}).get(event_id)
    if event is None or event.get('producer')!='Engine.use_move':return None
    actor=event['actor'];row=actor.spec.get(DEAD_STATE)
    if not row or row.get('completion_id')!=event.get('completion_id') or row['round']!=event['round']:return None
    move=getattr(e,'_move_completions',{}).get(row['completion_id'])
    window=getattr(e,'_initiative_interrupts',{}).get('windows',{}).get(row['window_id'])
    request=next((r for r in window['requests'] if r['id']==row['request_id']),None) if window else None
    fingerprint=__import__('root_resolution').fingerprint({k:row[k] for k in ('request_id','round','window_id')})
    if fingerprint!=row['declaration_fingerprint'] or request is None or request['source']!=DEAD or request['actor']is not actor or request['status']!='completed' or request['receipt']['actions']!=['standard'] or request['receipt']['round']!=row['round']:raise ValueError('actual paid Dead-Eye Priority declaration required')
    if move is None or move['actor']is not actor or move.get('marksman_attack',{}).get('feature')!=DEAD:return None
    if live and (row['phase']!='resolving' or event['phase']!='accuracy_boundary' or e._active_turn_actor is not None):return None
    return {'source':DEAD,'actor_id':actor.entity_id,'request_id':row['request_id'],'completion_id':row['completion_id'],'declaration_fingerprint':fingerprint}


def watch_reaction_origin(e,event_id,*,live):
    event=getattr(e,'_passive_events',{}).get(event_id)
    if event is None or event.get('producer')!='Engine.use_move':return None
    completion=getattr(e,'_move_completions',{}).get(event.get('completion_id'))
    data=completion.get('marksman_attack',{}) if completion else {}
    if data.get('feature')!=WATCH:return None
    saved=data.get('watch_reaction')
    if saved is None:return None
    facts=saved['facts'];owner_id=facts['owner_id']
    expected={'source':WATCH,'actor_id':event['actor'].entity_id,'target_id':event['target'].entity_id,
        'owner_id':owner_id,'completion_id':event['completion_id'],'round':event['round']}
    if (facts!=expected or saved['fingerprint']!=__import__('root_resolution').fingerprint(facts)
            or completion['actor']is not event['actor'] or completion['targets']!=[event['target']]):raise ValueError('actual Overwatch native attack origin changed')
    if live:
        owner=e._active_turn_actor
        watched=watch_state(e,event['actor'])
        if (owner is None or owner.entity_id!=owner_id or event['phase']!='accuracy_boundary'
                or watched is None or event['target'].entity_id not in watched['targets']):return None
    return deepcopy(facts)


def deadeye_roll(e,actor,target,move,natural):
    row=scope(e,actor,target,move)
    if not row or not row.get('deadeye'):return natural
    import fast_combat as FAST
    other=FAST.roll(e,actor);rolls=[natural,other]
    answer=e.rulings.decide({'type':'marksman_deadeye_accuracy','unit':DEAD,'actor_id':actor.entity_id,'rolls':rolls,'text':'Choose first or second actual Accuracy result.'})
    if type(answer)is not int or answer not in (0,1):raise ValueError('Dead-Eye needs one actual Accuracy result choice')
    chosen=rolls[answer];row.update(rolls=rolls,chosen=answer,lower=chosen==min(rolls))
    completion=getattr(e,'_move_completions',{}).get(row.get('completion_id'))
    if completion is not None:completion['marksman_attack'].update(rolls=rolls,chosen=answer,lower=row['lower'])
    return chosen


def deadeye_critical(e,actor,target,move,hit):
    row=scope(e,actor,target,move)
    return bool(hit and row and row.get('deadeye') and row.get('lower'))
