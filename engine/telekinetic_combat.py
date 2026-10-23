"""Native Telekinetic consumers; common owners retain rolls, costs and effects."""
from copy import deepcopy
from pathlib import Path
import json
import arithmetic_policy as M
import common_checks as C, state_grants as G, skill_modifiers as S
import telekinetic_load as LOAD, tk_mastery as MASTERY
import maneuver_opposed as OP, world_entities as W
from physical_limits import number

SOURCE=LOAD.SOURCE
STRUGGLE_MARKER='_telekinetic_struggle'
PURPOSE='telekinetic_maneuver'
KINDS={'push':('maneuver/밀기',4,('전투','육상'),'resist_push'),
       'trip':('maneuver/걸기',6,('전투','곡예'),'resist_trip'),
       'disarm':('maneuver/무장해제',6,('전투','은신'),'resist_disarm')}


def struggle_policy(engine,decision=None):
    import source_context as CONTEXT
    document=json.loads((Path(engine.r.root)/'data/telekinetic-struggle-policy.json').read_text(encoding='utf-8'))
    # The conflict interpretation binds both actual current PTK passages.
    CONTEXT.verified_source(engine.r,document['variants'][0]['values']['conflicting_source'],label='Telekinetic combat-table')
    return engine.r.resolve_source_policy(document,decisions={} if decision is None else {'damage_policy':decision})


def prepare_struggle(engine,actor,move,choice=None):
    old=move.get(STRUGGLE_MARKER)
    if old is not None:
        if old.get('actor_id')!=actor.entity_id:raise ValueError('prepared Telekinetic Struggle belongs to another actor')
        if choice is None:choice=old['choice']
    if not isinstance(choice,dict) or not {'capability','special'}<=set(choice) or set(choice)-{'capability','special','damage_policy'} or type(choice['special']) is not bool:
        raise ValueError('Telekinetic Struggle requires capability, boolean special and an optional scoped damage policy')
    if S.key(choice['capability']) not in {S.key(x) for x in ('염력','Telekinetic',SOURCE)}:
        raise ValueError('actual Telekinetic Struggle choice required')
    if move.get('id')!='struggle' or move.get('_weapon_attack') or actor.kind not in ('trainer','pokemon') or move.get('_struggle_capability'):
        raise ValueError('Telekinetic modifies an ordinary unarmed Struggle only')
    LOAD.require(engine,actor)
    rank=MASTERY.focus(actor);C.integer(rank,'Telekinetic Focus range',1)
    policy=None;attack_stat='atk';damage_class='물리'
    if choice['special']:
        policy=struggle_policy(engine,choice.get('damage_policy'))
        if policy['status']!='PolicyValuesReady':
            raise ValueError('Telekinetic Struggle Special Attack needs the explicit scoped damage_policy from telekinetic_struggle_policy()')
        selected=policy['values']['alternatives'][policy['values']['selected']]
        attack_stat=selected['attack_stat'];damage_class=selected['damage_class']
    elif 'damage_policy' in choice:raise ValueError('damage-class adjudication applies only to Special Attack Telekinetic Struggle')
    intent=deepcopy(choice);intent['capability']='염력'
    marker={'source':SOURCE,'actor_id':actor.entity_id,'choice':intent,'attack_stat':attack_stat,
            'damage_class':damage_class,'source_resolution':policy}
    if old is not None and old!=marker:raise ValueError('prepared Telekinetic Struggle intent or source interpretation changed')
    out=deepcopy(move);out['type']='노말';out['class']=damage_class;out[STRUGGLE_MARKER]=marker
    out['_struggle_range']={'origin':rank,'targets':1,'raw':str(rank)+', 대상 1','parsed':True}
    out['range']=str(rank)+', 대상 1'
    return out


def roll_bonus(engine,actor,skill,context):
    if not isinstance(context,dict) or context.get('purpose')!=PURPOSE:return 0
    if set(context)!={'purpose','maneuver','target_id','reason'} or not isinstance(context['reason'],str) or not context['reason'].strip():
        raise ValueError('actual bound Telekinetic maneuver context required')
    LOAD.require(engine,actor)
    if S.skill_id(engine.r.skill_policy,skill)!=S.skill_id(engine.r.skill_policy,'집중'):
        raise ValueError('Telekinetic maneuver requires actual Focus')
    if context.get('maneuver') not in {r[0] for r in KINDS.values()}:
        raise ValueError('actual Telekinetic maneuver source required')
    if engine.r._selected_rule(context['maneuver'])!=context['maneuver']:raise ValueError('selected Telekinetic maneuver source required')
    other=W.actor_index(engine).get(context.get('target_id'))
    if other is None or other is actor or not engine.encounter_active:
        raise ValueError('actual distinct combat maneuver counterpart required')
    LOAD.range_check(engine,actor,other)
    return MASTERY.bonus(actor)


def _options(engine,actor,target,source,skill,supplied,*,weapon_defense=False):
    result=dict(supplied or {})
    if S.skill_id(engine.r.skill_policy,skill)==S.skill_id(engine.r.skill_policy,'집중') and not weapon_defense:
        LOAD.require(engine,actor)
        context={'purpose':PURPOSE,'maneuver':source,'target_id':target.entity_id,
                 'reason':'actual native Telekinetic maneuver Focus check'}
        if result.get('skill_context') not in (None,context):raise ValueError('actual Telekinetic maneuver context cannot be replaced')
        result['skill_context']=context
    return result


def _native(engine,actor,target,kind,*,defender_skill,fixed_accuracy,challenger_options,defender_options,item_name,prevent_with_ap,follow_steps):
    import turn as TURN, forced_movement as FORCED
    LOAD.require(engine,actor);W.require_actors(engine,actor,target)
    source,ac,defenders,resist=KINDS[kind]
    C.integer(follow_steps,'Telekinetic follow count',0)
    if follow_steps:raise ValueError('Telekinetic Push cannot repeat or follow')
    if kind!='disarm' and (item_name is not None or prevent_with_ap is not None):
        raise ValueError('equipment selections belong to actual Disarm')
    import optional_weapon_framework as FRAMEWORK
    weapon_defense=FRAMEWORK.disarm_skills(engine,target) if kind=='disarm' else set()
    if kind=='disarm':defenders=tuple(dict.fromkeys((*defenders,*weapon_defense)))
    if (S.skill_id(engine.r.skill_policy,defender_skill)==S.skill_id(engine.r.skill_policy,'집중')
            and S.skill_id(engine.r.skill_policy,defender_skill) not in weapon_defense):
        LOAD.require(engine,target);defenders=(*defenders,'집중');resist=PURPOSE
    ao=_options(engine,actor,target,source,'집중',challenger_options)
    do=_options(engine,target,actor,source,defender_skill,defender_options,
                weapon_defense=S.skill_id(engine.r.skill_policy,defender_skill) in weapon_defense)
    chosen=None;prevention=False;defense_bonus=0
    if kind=='disarm':
        import weapon_actions as WEAPONS
        import wielder_capability as WIELDER
        ao=WIELDER.disarm_options(engine,actor,ao)
        chosen=TURN.disarm_equipment(engine,target,item_name)
        if chosen is None:return False
        do,defense_bonus,prevention=WEAPONS.disarm_options(engine,target,do,prevent_with_ap)
    distance=None;direction=None
    if kind=='push':
        import body_state as BODY
        weight=number(BODY.weight_kg(target),'actual Telekinetic Push target weight',minimum=0)
        heavy=LOAD.table(actor)['heavy'][1]
        if weight>heavy:raise ValueError('Telekinetic Push target exceeds Focus-based Heavy Lifting')
        dx=(target.pos[0]>actor.pos[0])-(target.pos[0]<actor.pos[0]);dy=(target.pos[1]>actor.pos[1])-(target.pos[1]<actor.pos[1])
        if dx and dy:return C.PendingDecision('diagonal Telekinetic Push geometry requires its explicit displacement path',basis={'source':source})
        direction=(dx,dy);distance=M.ratio(MASTERY.focus(actor),2)
    config={'geometry':{'range':8,'remote':True,'vertical':False},
            'requirements':[{'id':'current-telekinetic','who':'actor','condition':{'kind':'capability','names':['염력','Telekinetic','capability/염력']},'reason':'actual source-owned Telekinetic maneuver'}],
            'challenger_skills':['집중'],'defender_skills':list(defenders),'challenger_purpose':PURPOSE,
            'resistance_purpose':resist,'action_cost':'standard','accuracy':'ordinary','opposed':'required',
            'success':'check','accuracy_class':'변화','opportunity':'other_adjacent'}
    basis={'telekinetic_source':SOURCE,'distance':distance,'direction':direction,'chosen':chosen,
           'prevention':prevention,'defense_bonus':defense_bonus,'focus_rank':MASTERY.focus(actor)}
    plans,prepared=OP._prepare(engine,actor,target,source,(),'집중',defender_skill,fixed_accuracy,ao,do,basis,config=config)
    origins=(tuple(actor.pos),tuple(target.pos))
    def outcome(won):
        if not won:return False
        if (tuple(actor.pos),tuple(target.pos))!=origins:raise ValueError('actual Telekinetic maneuver geometry changed during resolution')
        if kind=='trip':
            engine.apply_status(target,'넘어짐');return True
        if kind=='disarm':return TURN._disarm_outcome(engine,target,prevention,chosen)
        result=FORCED.displace(engine,actor,target,direction=direction,distance=distance,source=source)
        return dict(result,telekinetic_source=SOURCE,focus_rank=basis['focus_rank'],follow_metres=0)
    return OP._run(engine,actor,target,source,ac,plans,prepared,outcome,fixed_accuracy,config=config)


def maneuver(engine,actor,target,kind,*,defender_skill,fixed_accuracy=None,challenger_options=None,defender_options=None,item_name=None,prevent_with_ap=None,follow_steps=0):
    if kind not in KINDS:raise ValueError('Telekinetic maneuver must be push, trip or disarm')
    options=dict(defender_skill=defender_skill,fixed_accuracy=fixed_accuracy,challenger_options=challenger_options,
                 defender_options=defender_options,item_name=item_name,prevent_with_ap=prevent_with_ap,follow_steps=follow_steps)
    W.require_actors(engine,actor,target)
    if any(v.get('feature') is not None for v in (challenger_options or {},defender_options or {})):
        return _native(engine,actor,target,kind,**options)
    return G.transition(engine,actor,lambda e,a,t:_native(e,a,t,kind,**options),participants=(target,))

