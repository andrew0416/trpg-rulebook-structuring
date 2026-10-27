"""Shared maneuver admission, action/AoO, hit, opposed roll and result stages."""
from copy import deepcopy
import body_state as BODY,common_checks as C,turn as TURN,skill_modifiers as SKILLS
import skill_maneuver_actions as SM,world_entities as W,state_grants as G
import crafting_recipes as Q,effects as FX

PUSH='maneuver/밀기'
TRIP='maneuver/걸기'

def slippery_skill(engine,actor,chosen,source):
    """Only Slippery's three printed defending checks gain this alternative."""
    uid='edge/약삭빠름'
    if source not in (PUSH,TRIP,'maneuver/붙잡기','maneuver/붙잡기/contest'):return None
    if SKILLS.skill_id(engine.r.skill_policy,chosen,required=True)!='stealth':return None
    import acquired_features as A,hobbyist as H,source_context as C
    if A.owned_rule_count(actor,uid)!=1:return None
    C.verified_source(engine.r,{'file':'input/ch03-skills-edges-feats.md','sha256':H.GENERAL},label='Slippery')
    if engine.r.selection.units[uid]['source']['lines']!=[466,468]:raise ValueError('actual Slippery source required')
    if not H.skill_waived(actor,uid) and SKILLS.rank(engine.r,actor,'은신')[2]<3:raise ValueError('Slippery requires Novice Stealth')
    return H.direct_skill(actor,uid,'은신')


def _options(options,purpose):
    result=dict(options or {});context=result.get('skill_context')
    if purpose is None:
        if context is not None:raise ValueError('offensive maneuver has no resisting-skill context')
    else:
        if context is not None and (not isinstance(context,dict) or context.get('purpose')!=purpose):raise ValueError('actual maneuver skill context cannot be replaced')
        result['skill_context']=context or {'purpose':purpose,'reason':'actual native '+purpose+' maneuver check'}
    return result


def _permission(e,a,t,source,grant,config):
    import action_lifecycle as ACTION
    permission=ACTION.maneuver_authority(e,grant,a,t,source)
    if config is not None and grant is None:permission={key:config[key] for key in ('action_cost','accuracy','opposed','success')}
    return permission


def _requirements(e,a,t,requirements):
    sources=set()
    for row in requirements:
        subject=a if row['who']=='actor' else t;node=row['condition']
        if node['kind']=='capability':
            names={str(x).removeprefix('capability/') for x in G.effective_capabilities(subject)}
            passed=bool(names.intersection(node['names']))
        else:passed=Q._observe(e,subject,node,sources)
        if not passed:raise ValueError('maneuver qualification failed: '+row['id'])


@SM.resume_entry("a",source_parameter="source")
def _prepare(e,a,t,source,skills,challenger_skill,defender_skill,fixed_accuracy,challenger_options,defender_options,basis,_grant=None,*,config=None,observe=False):
    import body_modes as BODY_MODES
    config=__import__('type_ace').threaded_config(e,a,source,config)
    BODY_MODES.require_targetable(t,engine=e,attacker=a)
    permission=_permission(e,a,t,source,_grant,config);basis=dict(basis,grant=permission)
    import movement_actions as MOVEMENT,temporary_hp as TEMP
    MOVEMENT.boundary(e,source);Q._selected(e,source);W.require_actors(e,a,t)
    __import__('type_ace').close_quarters_maneuver_preflight(e,a,source)
    if a is t or a.kind not in ('trainer','pokemon') or t.kind not in ('trainer','pokemon') or a not in e.everyone or t not in e.everyone:raise ValueError('two distinct registered trainer/Pokemon participants required')
    if not e.encounter_active or e.round_start_seconds is None:raise ValueError('actual open combat round required')
    geometry={'range':1,'remote':False,'vertical':False} if config is None else config['geometry']
    if not SM.native_reaction_resume(e,a,t,source):
        if not a.on_field or not t.on_field or a.captured or t.captured or e.grid is None or geometry['range'] is None or not BODY.in_range(e,a,t,geometry['range']):raise ValueError('reachable actual mapped maneuver target required')
        if not geometry['remote'] and (not e.adjacent(a,t) or not BODY.in_range(e,a,t,1)):raise ValueError('one reachable adjacent on-field target required')
        if not geometry['vertical'] and (a.spec.get('_movement_altitude',0)!=t.spec.get('_movement_altitude',0) or a.spec.get('_burrow',{}).get('underground') or t.spec.get('_burrow',{}).get('underground')):raise ValueError('vertical or underground maneuver geometry needs an explicit adapter')
    if (a.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(a)) and permission['action_cost']=='standard':raise ValueError('heavy Standard maneuver needs its independent event-order adapter')
    if config is not None:_requirements(e,a,t,config['requirements'])
    if fixed_accuracy is not None:C.integer(fixed_accuracy,'maneuver d20',1,20)
    TEMP.ensure_certain(e,a);TEMP.ensure_certain(e,t)
    if permission['opposed']=='waived':return [],None
    slipped=slippery_skill(e,t,defender_skill,source)
    for chosen,choices in ((challenger_skill,skills if config is None else config['challenger_skills']),(defender_skill,(*((skills if config is None else config['defender_skills'])),*(('은신',) if slipped is not None else ())))):
        allowed={SKILLS.skill_id(e.r.skill_policy,x,required=True) for x in choices}
        if SKILLS.skill_id(e.r.skill_policy,chosen,required=True) not in allowed:raise ValueError('skill is not permitted by this maneuver source')
    purpose=('resist_push' if source==PUSH else 'resist_trip') if config is None else config['resistance_purpose']
    ao=_options(challenger_options,None if config is None else config.get('challenger_purpose'));do=_options(defender_options,purpose)
    if ao.get('roll_id') is not None and ao.get('roll_id')==do.get('roll_id'):raise ValueError('distinct opposed roll identities required')
    plans=[(a,challenger_skill,ao),(t,slipped or defender_skill,do)]
    return plans,SM.prepare(e,a,t,source,dict(basis,fixed_accuracy=fixed_accuracy),plans,observe=observe)


@SM.resume_entry("a",source_parameter="source",prepared_parameter="prepared")
def _run(e,a,t,source,ac,plans,prepared,outcome,fixed_accuracy,_grant=None,*,config=None,context=None,_accuracy_bonus=0):
    config=__import__('type_ace').threaded_config(e,a,source,config)
    if __import__('type_ace').threaded_scope(e,a) is not None:ac=__import__('threaded').parameters(a)['accuracy']
    permission=_permission(e,a,t,source,_grant,config)
    C.integer(_accuracy_bonus,'internal maneuver accuracy bonus')
    if permission['opposed'] not in ('required','waived') or permission['success']!=('check' if permission['opposed']=='required' else 'automatic'):raise ValueError('explicit opposed and success policies required')
    move={'id':source,'name':source,'type':'노말','class':'변화' if config is None else config['accuracy_class'],'ac':ac,'range':'근접, 대상1','keywords':[]}
    if permission['accuracy']=='ordinary':e._prepare_accuracy_context(a,t,move,situational=_accuracy_bonus,fixed_roll=fixed_accuracy)
    def accuracy():
        import precise_actions as PRECISE
        event=PRECISE.attacked(e,a,t,move,producer='combat_maneuver')
        if permission['accuracy']=='automatic':hit,nat=True,None
        else:hit,nat,_=e.accuracy_check(a,t,move,situational=_accuracy_bonus,fixed_roll=fixed_accuracy)
        if context is not None:context.update(hit=hit,nat=nat)
        PRECISE.accuracy(event,hit,natural=nat)
        if hit:__import__('type_ace').maneuver_hit(e,a,t,source)
        else:__import__('martial_artist').maneuver_failed(e,a,t,source,opposed=False)
        return hit
    spend=lambda:True if permission['action_cost']=='included' else __import__('martial_artist').spend_maneuver(e,a,t,source,permission['action_cost'])
    original_outcome=outcome
    def outcome(won):
        result=original_outcome(won)
        if not won:__import__('martial_artist').maneuver_failed(e,a,t,source,opposed=True)
        return result
    opportunity='other_adjacent' if config is None else config['opportunity']
    def aoo():
        if opportunity!='none':TURN.trigger_aoo(e,a,source,[x for x in TURN.adjacent_enemies(e,a) if opportunity=='all_adjacent' or x is not t])
    return SM.run(e,a,prepared,attack=None if permission["action_cost"]=="included" else move,spend=spend,aoo=aoo,can_continue=lambda:TURN.can_act(e,a),accuracy=accuracy,outcome=outcome,
        opposed=lambda:True if permission['opposed']=='waived' else e.opposed_check(a,plans[0][1],t,plans[1][1],challenger_options=plans[0][2],defender_options=plans[1][2]))


def declaration(value):
    Q._fields(value,('id','source','requirements','challenger_skills','defender_skills','resistance_purpose','geometry','action_cost','accuracy','accuracy_class','ac','opposed','success','opportunity','effects'))
    for key in ('id','source','resistance_purpose'):Q._text(value[key])
    if value['action_cost'] not in ('standard','shift','swift','free','included') or value['accuracy'] not in ('ordinary','automatic') or value['opposed'] not in ('required','waived') or value['success']!=('check' if value['opposed']=='required' else 'automatic'):raise ValueError('explicit maneuver action/accuracy/opposed/success policies required')
    if value['opportunity'] not in ('none','all_adjacent','other_adjacent') or value['accuracy_class'] not in ('물리','특수','변화'):raise ValueError('explicit maneuver opportunity and evasion class required')
    C.integer(value['ac'],'maneuver accuracy',0)
    Q._fields(value['geometry'],('range','remote','vertical'));geo=value['geometry']
    if geo['range'] is not None:C.integer(geo['range'],'maneuver range',1)
    if any(type(geo[key]) is not bool for key in ('remote','vertical')):raise ValueError('explicit remote and vertical maneuver policies required')
    for key in ('challenger_skills','defender_skills'):
        if type(value[key]) is not list or not value[key] or any(type(x) is not str or not x for x in value[key]):raise ValueError('explicit maneuver skill alternatives required')
    if type(value['requirements']) is not list:raise ValueError('maneuver qualification list required')
    ids=set()
    for row in value['requirements']:
        Q._fields(row,('id','who','condition','reason'));Q._text(row['id']);Q._text(row['reason'])
        if row['id'] in ids or row['who'] not in ('actor','target'):raise ValueError('distinct qualified maneuver participant required')
        ids.add(row['id']);node=row['condition']
        if type(node) is dict and node.get('kind')=='capability':Q._fields(node,('kind','names'));Q._names(node['names'])
        else:Q._condition(node)
    if (geo['remote'] or geo['vertical']) and not any(row['who']=='actor' and row['condition']['kind'] in ('capability','owned') for row in value['requirements']):raise ValueError('remote/vertical exception requires actual acquired qualification')
    if type(value['effects']) is not list:raise ValueError('maneuver result effect list required')
    return deepcopy(value)


def _execute(e,a,t,value,challenger_skill,defender_skill,fixed_accuracy,challenger_options,defender_options):
    plans,prepared=_prepare(e,a,t,value['source'],(),challenger_skill,defender_skill,fixed_accuracy,challenger_options,defender_options,{'declaration':value},config=value)
    FX.preflight_effects(e,a,t,value['effects'],value['source'])
    context={}
    def outcome(won):
        if not won:return False
        result=FX.run_effects(e,a,t,value['effects'],dict(attacker=a,target=t,nat=context.get('nat'),hit=True,dealt=0,engine=e),value['source'])
        return {'success':True,'declaration_id':value['id'],'source':value['source'],'effects':result}
    return _run(e,a,t,value['source'],value['ac'],plans,prepared,outcome,fixed_accuracy,config=value,context=context)


def execute(e,a,t,value,*,challenger_skill=None,defender_skill=None,fixed_accuracy=None,challenger_options=None,defender_options=None):
    W.require_actors(e,a,t);value=declaration(value);Q._selected(e,value['source'])
    if e.grid is None or value['geometry']['range'] is None:return C.PendingDecision('actual mapped maneuver geometry is unknown',basis={'source':value['source'],'actor_id':a.entity_id,'target_id':t.entity_id})
    options=(challenger_options or {},defender_options or {})
    # Native observed choices retain their paid receipt and RNG observations on retry.
    if any(option.get('feature') is not None for option in options):return _execute(e,a,t,value,challenger_skill,defender_skill,fixed_accuracy,*options)
    return G.transition(e,a,lambda staged,actor,target:_execute(staged,actor,target,value,challenger_skill,defender_skill,fixed_accuracy,*options),participants=(t,))
