"""Bound capture comparison, separate from throw admission and acquisition."""
from dataclasses import dataclass
from copy import deepcopy
import common_checks as C

@dataclass(frozen=True)
class Procedure:
    source: str
    sides: int
    comparison: str
    automatic_faces: tuple = ()
    miss_state: str = 'recoverable_on_ground'
    failure_state: str = 'failed_capture'
    success_state: str = 'captured'

    def __post_init__(self):
        if not isinstance(self.source,str) or not self.source.strip():raise ValueError('capture procedure source required')
        C.integer(self.sides,'capture die sides',2)
        if self.comparison not in ('>=','<='):raise ValueError('capture comparison must be explicit')
        if not isinstance(self.automatic_faces,tuple):raise ValueError('immutable automatic faces required')
        for face in self.automatic_faces:C.integer(face,'automatic capture face',1,self.sides)
        if len(set(self.automatic_faces))!=len(self.automatic_faces):raise ValueError('duplicate automatic face')
        if any(not isinstance(x,str) or not x.strip() for x in (self.miss_state,self.failure_state,self.success_state)):
            raise ValueError('complete capture result states required')

    def resolve(self, natural, *, threshold, modifiers):
        C.integer(natural,'capture natural',1,self.sides)
        C.integer(threshold,'capture threshold')
        if not isinstance(modifiers,dict) or any(not isinstance(k,str) or not k.strip() for k in modifiers):
            raise ValueError('named capture modifiers required')
        for value in modifiers.values():C.integer(value,'capture modifier')
        total=natural+sum(modifiers.values())
        automatic=natural in self.automatic_faces
        captured=automatic or (total>=threshold if self.comparison=='>=' else total<=threshold)
        return dict(source=self.source,sides=self.sides,comparison=self.comparison,
                    natural=natural,modifiers=dict(modifiers),total=total,threshold=threshold,
                    automatic=automatic,captured=captured,
                    status=self.success_state if captured else self.failure_state)


def bind_native(rules, source_variant=None):
    if source_variant == 'core_105':
        import source_context as SOURCES
        SOURCES.verified_source(rules, {'file':'source-audit/ptu-core-1.05.pdf',
            'sha256':'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'},
            label='Core capture p214',source_root='source-audit')
        return Procedure('core_105/capture-p214',100,'<=',(100,)), {
            'source_variant':source_variant,'throw':{'action':'standard','ac':6,'class':'변화','range':'4 + athletics_rank'},
            'trainer_bonus_by_level':{},'capture_rate':{'source':'Core 1.05 p214'}}
    if source_variant not in (None,'official_sep2015'):
        raise ValueError('select an actual complete capture procedure')
    if source_variant=='official_sep2015':
        __import__('capture_specialist').official_source(rules,source_variant)
    selected=rules.mech('pokemon/capture-rate')
    if selected.get('_version') is not None:
        raise ValueError('selected capture version needs a complete procedure and matching ball modifiers')
    if selected.get('roll')!='1d20 + trainer_bonus' or selected.get('success')!='roll >= capture_rate':
        raise ValueError('capture roll and comparison require a matching complete procedure')
    throw=selected.get('throw',{})
    if throw.get('action')!='standard' or throw.get('class')!='변화' or throw.get('range')!='4 + athletics_rank':
        raise ValueError('capture throw policy requires a matching procedure')
    C.integer(throw.get('ac'),'capture throw AC',0)
    rates=selected.get('capture_rate',{})
    for key in ('base','per_10_levels','checkbox_penalty'):C.integer(rates.get(key),'capture '+key)
    known={'hp_le_50':'hp <= 0.5*max_hp','hp_le_25':'hp <= 0.25*max_hp',
           'injuries_ge_5':'injuries >= 5','any_status':'has persistent or volatile affliction',
           'two_evolutions_left':'evolutions_remaining == 2','one_evolution_left':'evolutions_remaining == 1'}
    rows=rates.get('checkboxes')
    if not isinstance(rows,list) or any(not isinstance(r,dict) or r.get('id') not in known for r in rows):
        raise ValueError('capture checkbox declaration requires known predicates')
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('duplicate capture checkbox')
    for row in rows:
        C.integer(row.get('boxes'),'capture checkbox count',0)
        if row.get('when')!=known[row['id']]:raise ValueError('capture checkbox predicate requires a matching procedure')
    bonuses=selected.get('trainer_bonus_by_level')
    if not isinstance(bonuses,dict) or not bonuses:raise ValueError('trainer capture bonus table required')
    for level,bonus in bonuses.items():
        if not isinstance(level,str) or not level.isdigit():raise ValueError('trainer bonus level must be numeric')
        C.integer(bonus,'trainer capture bonus')
    return Procedure('pokemon/capture-rate',20,'>='),deepcopy(selected)


def rate(engine,target,rarity=0,*,source_variant=None,hp=None):
    procedure,selected=bind_native(engine.r,source_variant)
    current=target.hp if hp is None else C.integer(hp,'capture-only HP observation',1)
    if procedure.sides==20:
        cr=selected['capture_rate'];boxes=0
        ctx={'hp_le_50':current*2<=target.base_max_hp,'hp_le_25':current*4<=target.base_max_hp,
             'injuries_ge_5':target.injuries>=5,
             'any_status':any(engine.r.condition_class(s) in ('persistent','volatile') for s in target.conditions),
             'two_evolutions_left':target.spec.get('evolutions_remaining',0)==2,
             'one_evolution_left':target.spec.get('evolutions_remaining',0)==1}
        boxes=sum(row['boxes'] for row in cr['checkboxes'] if ctx[row['id']])
        import arithmetic_policy as M
        return cr['base']+M.ratio(target.level,10)*cr['per_10_levels']+rarity-boxes*cr['checkbox_penalty'],boxes
    C.integer(rarity,'Core GM capture rarity adjustment')
    if current<=0:raise ValueError('Core capture requires positive HP or actual Catch Combo')
    health=30 if current==1 else 15 if current*4 <= target.base_max_hp else 0 if current*2 <= target.base_max_hp else -15 if current*4 <= target.base_max_hp*3 else -30
    evolutions=C.integer(target.spec.get('evolutions_remaining',0),'remaining evolution stages',0,2)
    conditions=sum(10 if engine.r.condition_class(s)=='persistent' else 5 if engine.r.condition_class(s)=='volatile' else 0 for s in target.conditions)
    total=100-2*target.level+health+{2:10,1:0,0:-10}[evolutions]+5*target.injuries+conditions
    total-=10 if target.spec.get('shiny',False) else 0
    total-=30 if target.spec.get('legendary',False) else 0
    total+=10 if '구속' in target.conditions else 0
    total+=5 if '둔화' in target.conditions else 0
    return total+rarity,0


def ball_modifier(engine,name,trainer,target,procedure):
    import items
    value,why=items.ball_modifier(engine,name,trainer,target)
    # The official September conversion explicitly gives the inverse of each
    # original modifier. Use that complete paired table, including Timer bounds.
    if procedure.sides==100:
        __import__('capture_specialist').official_source(engine.r,'official_sep2015')
        return -5*value,why+' (Core paired modifier)'
    return value,why

def _post_hit(self,trainer,target,*,record,actual_ball,combo,rarity,capture_source,
             cannon,momentum_plan,fixed_capture,procedure,gotta_swap,nat,
             choice_callback,bonus,bmod,bwhy,snare_bonus,net_bonus,manual_bonus,
             fixed_reroll,choice,collector,new_family,placement_plan,name,ball_name):
    """Resolve an admitted hit; callers own launch, accuracy and action payment."""
    import captured_momentum as MOMENTUM,roll_pools as POOLS
    import capture_specialist as SPECIALIST,pokemon_activities as POKEMON_ACTIVITIES
    import world_entities as WORLD,pokemon_party as POKEMON_PARTY,items as ITEMS
    if (target.fainted or target.hp<=0) and not combo:
        record.update(status='ball_function_not_activated',target_fainted=True)
        __import__('juggler').capture_function(self,trainer,record,actual_ball,hit=True)
        return False
    rate,boxes=self.capture_rate(target,rarity,source_variant=capture_source,hp=1 if combo else None)
    if cannon is not None:
        projectile_damage,faces=self.roll_expr(cannon['fixed_damage'],actor=trainer,purpose='damage')
        self.take_damage(target,projectile_damage)
        record['cannon']['damage']={'expression':'2d6','faces':faces,'requested':projectile_damage}
        if (target.fainted or target.dead) and not combo:
            record['status']=procedure.miss_state
            record['cannon']['target_fainted']=True
            return False
        rate,boxes=self.capture_rate(target,rarity,source_variant=capture_source,hp=1 if combo else None)
    momentum_bonus = MOMENTUM.capture(self,trainer,target,record,momentum_plan)
    natural=fixed_capture if fixed_capture is not None else POOLS.die(self.rng,procedure.sides)
    if procedure.sides==20:
        natural=__import__('oracle').replace_d20(self,trainer,natural,'capture')
        natural=__import__('roll_context').observe_native(self,trainer,'capture',natural,lambda faces:POOLS.die(self.rng,20,fixed=None if faces is None else faces[0]))
    original=natural
    natural,gotta_bonus=SPECIALIST.gotta_roll(self,trainer,natural,procedure,gotta_swap)
    accuracy_capture_bonus=-10 if procedure.sides==100 and nat==20 else 0
    import fashion_items as FASHION
    fashion_roll_modifier=FASHION.all_roll_modifier(trainer)
    if choice_callback:
        # The decision sees the completed original roll, before capture resolves.
        # It receives facts only, not a mutable record or resource store.
        facts={'natural':natural,'total':natural+bonus+bmod+snare_bonus+net_bonus+fashion_roll_modifier+manual_bonus+momentum_bonus,'dc':rate,'stacks':trainer.spec.get('collector_stacks',0)}
        try:
            choice=POKEMON_ACTIVITIES.collector_choice(choice_callback(dict(facts)),facts['stacks'])
            if fixed_reroll is not None and choice['kind']!='reroll':raise ValueError('fixed reroll requires a reroll decision')
        except Exception as exc:
            # Optional choice rejected: preserve this completed original roll,
            # ball and action cost; neither extra RNG nor stacks are consumed.
            choice={'kind':'none','cost':0}
            record['collector_choice_rejected']=type(exc).__name__+': '+str(exc)
            self.log('    수집가 선택 거절: 원래 포획 굴림을 확정합니다',POKEMON_ACTIVITIES.COLLECTOR_REVISION)
    collector_bonus=0
    if choice['cost']:
        trainer.spec['collector_stacks']-=choice['cost']
        if choice['kind']=='reroll':natural=self.roll_d20(trainer,'capture_reroll',fixed=fixed_reroll)
        else:collector_bonus=choice['cost']
    record['collector']={'choice':choice['kind'],'spent':choice['cost'],'original_natural':original,'bonus':collector_bonus,'earned':0,'choice_rejected':record.pop('collector_choice_rejected',None)}
    resolution=procedure.resolve(natural,threshold=rate,modifiers={
        'trainer':bonus,'ball':bmod,'collector':collector_bonus,'snare':snare_bonus,
        'net':net_bonus,'fashion':fashion_roll_modifier,'type_manual':manual_bonus,'captured_momentum':momentum_bonus,
        'gotta':gotta_bonus,'accuracy_natural20':accuracy_capture_bonus})
    roll=resolution['total'];ok=resolution['captured']
    record['resolution']=resolution
    record.update(captured=ok,capture_natural=natural,capture_total=roll,capture_dc=rate,
                  snare_bonus=snare_bonus,net_bonus=net_bonus,
                  fashion_roll_modifier=fashion_roll_modifier,status=resolution['status'])
    __import__('juggler').capture_function(self,trainer,record,actual_ball,hit=True)
    self.log(f"    포획 굴림 1d{procedure.sides}{bonus:+d}{bmod:+d}[{bwhy}] = {roll} vs 포획률 {rate} (체크박스 {boxes}개) → {'포획!' if ok else '실패'}", "pokemon/capture-rate")
    if ok:
        WORLD.finish_physical_use(self,actual_ball,'consumed',
            {'source':record['physical_item'],'by_actor_id':trainer.entity_id,'at':self.elapsed_seconds})
        if collector and new_family:
            trainer.spec['collector_stacks']=trainer.spec.get('collector_stacks',0)+1
            record['collector']['earned']=1
        target.captured=True
        import boss_transitions as BOSS
        BOSS.after_capture(self,target)
        if trainer.spec.get('id'):target.spec['trainer_id']=trainer.spec['id']
        record['placement']=POKEMON_PARTY.finish_capture(self,trainer,target,placement_plan)
        after=ITEMS.BALL_AFTER.get(name)
        if __import__('glitch_bender').benefits_blocked(target):after=None
        if after=='full_heal':
            self.heal(target,max(0,target.max_hp-target.hp),source_kind='ordinary_item')
            self.log(f"    {ball_name}: 포획한 {target.name} 체력 완전 회복",f"item/{name}")
        elif after:self.log(f"    {ball_name}: 포획 후 효과 {after} (GM 적용)",f"item/{name}")
        caught=trainer.spec.setdefault('caught_species',[])
        if target.spec.get('species') and target.spec['species'] not in caught:caught.append(target.spec['species'])
        MOMENTUM.after_capture(self,trainer,target,record)
    else:SPECIALIST.escaped(self,trainer,target,record)
    return ok


def fling_preflight(engine,actor,target,ball_name,options,*,after_damage=False):
    """Prepare codec-safe capture choices before Fling pays or detaches its ball."""
    import json
    import world_entities as WORLD,special_entities as SPECIAL,body_modes as BODY
    import actor_templates as TEMPLATES,items as ITEMS,arithmetic_policy as M
    import capture_specialist as SPECIALIST,pokemon_activities as ACTIVITIES
    import captured_momentum as MOMENTUM,pokemon_party as PARTY
    allowed={'rarity','capture_source','fixed_capture','collector_choice','fixed_reroll',
             'type_manual_instance_id','snare_conversion','gotta_swap'}
    if type(options)is not dict or set(options)-allowed:
        raise ValueError('Fling capture requires explicit supported capture options')
    # Pending moves retain data, not a callback that could change after launch.
    try:json.dumps(options,allow_nan=False)
    except (TypeError,ValueError) as exc:raise ValueError('Fling capture choices must be plain data') from exc
    WORLD.require_actors(engine,actor,target)
    SPECIAL.require_prime_independent(engine,target)
    BODY.require_targetable(target,engine=engine,attacker=actor)
    template=TEMPLATES.projection(target)
    if template and template['capture_immune']:raise ValueError('target is capture immune')
    TEMPLATES.require_ordinary(target,'boss capture and normal-form restoration')
    if actor.kind!='trainer' or target.kind!='pokemon':
        raise ValueError('Fling capture needs a trainer and a Pokemon target')
    if type(after_damage)is not bool:raise ValueError('explicit Fling damage phase required')
    combo=False if after_damage else SPECIALIST.combo_allowed(engine,actor,target)
    inactive=target.fainted or target.hp<=0
    if ((inactive and not combo and not after_damage) or target.dead or target.captured
            or getattr(target,'side',None)=='party' or target.spec.get('trainer_id') or target.spec.get('trainer')):
        raise ValueError('Fling capture requires a living unowned target')
    capture_source=options.get('capture_source')
    procedure,selected=bind_native(engine.r,capture_source)
    rarity=C.integer(options.get('rarity',0),'GM capture rarity')
    fixed_capture=options.get('fixed_capture');fixed_reroll=options.get('fixed_reroll')
    if fixed_capture is not None:C.integer(fixed_capture,'capture die',1,procedure.sides)
    if fixed_reroll is not None:C.integer(fixed_reroll,'collector reroll d20',1,20)
    declared_choice=options.get('collector_choice')
    collector=ACTIVITIES.collector_eligible(engine,actor,declared_choice is not None or fixed_reroll is not None)
    choice=ACTIVITIES.collector_choice(declared_choice,actor.spec.get('collector_stacks',0))
    if fixed_reroll is not None and choice['kind']!='reroll':
        raise ValueError('fixed reroll requires the collector reroll choice')
    name=ITEMS.ball_name(engine.r.items_mech.get(ball_name,{}).get('name',ball_name))
    if name not in ITEMS.BALL_RULES:
        effects,header=engine.r.item_effects(ball_name)
        if not effects or not any(row.get('type')=='capture_mod' for row in effects):
            raise ValueError('unsupported capture ball')
    else:engine.r._selected_rule('item/'+name)
    import csv_item_physical_contracts as CSV
    manual_id=options.get('type_manual_instance_id')
    manual_bonus=0 if manual_id is None else M.ratio(-CSV.manual_capture_modifier(engine,actor,target,manual_id),5)
    book_manual=__import__('study_books').type_capture(actor,target)
    if book_manual:
        manual_bonus=min(manual_bonus,book_manual) if procedure.sides==100 else max(manual_bonus,M.ratio(-book_manual,5))
    rate(engine,target,rarity,source_variant=capture_source,hp=1 if combo or (after_damage and inactive) else None)
    bonus=-actor.level if procedure.sides==100 else max([b for lv,b in selected['trainer_bonus_by_level'].items() if actor.level>=int(lv)],default=0)
    bmod,bwhy=ball_modifier(engine,name,actor,target,procedure)
    snare_bonus=__import__('wild_equipment').snare_bonus(engine,actor,target,
        conversion=options.get('snare_conversion'),source_variant=capture_source)
    net_bonus=__import__('net_capsule').capture_bonus(engine,target)*(-5 if procedure.sides==100 else 1)+SPECIALIST.net_modifier(engine,target,procedure)
    SPECIALIST.gotta_preflight(engine,actor,procedure,options.get('gotta_swap'))
    plan={'actor_id':actor.entity_id,'target_id':target.entity_id,'ball_name':name,
          'options':deepcopy(options),'procedure':{'source':procedure.source,'sides':procedure.sides,'comparison':procedure.comparison},
          'combo':combo,'choice':choice,'collector':collector,'bonus':bonus,'bmod':bmod,'bwhy':bwhy,
          'manual_bonus':manual_bonus,'snare_bonus':snare_bonus,'net_bonus':net_bonus,
          'momentum_plan':MOMENTUM.capture_plan(engine,actor,capture_source),
          'new_family':ACTIVITIES.collector_new_family(engine,actor,target) if collector else False,
          'placement_plan':PARTY.preflight_capture(engine,actor,target),
          'physical_source':__import__('missed_ball_body').source(engine.r)}
    json.dumps(plan,allow_nan=False)
    return plan


def fling_post_hit(engine,actor,target,admission,prepared_plan):
    """Consume Fling's live native hit authority; never launch or pay twice."""
    import fling_move as FLING,world_entities as WORLD,missed_ball_body as BALL_BODY
    # The move owner authenticates actual dispatch, hit recipient and launch,
    # binds the exact prepared plan, and consumes the opaque token once.
    admitted=FLING.consume_capture_admission(engine,actor,target,admission,prepared_plan)
    plan=admitted['capture_plan'];options=plan['options']
    procedure,_=bind_native(engine.r,options.get('capture_source'))
    if plan['procedure']!={'source':procedure.source,'sides':procedure.sides,'comparison':procedure.comparison}:
        raise ValueError('Fling capture procedure changed after launch')
    if (plan['actor_id']!=actor.entity_id or plan['target_id']!=target.entity_id
            or plan['ball_name']!=__import__('items').ball_name(admitted['ball_name'])):
        raise ValueError('Fling capture must use its actual actor, recipient and ball')
    obj=getattr(engine,'_physical_objects',{}).get(admitted['instance_id'])
    if (not isinstance(obj,dict) or obj.get('kind')!='item_instance'
            or obj.get('owner_id')!=actor.entity_id or obj.get('item_rule_id')!=admitted['item_rule_id']
            or obj.get('equipped_by') or obj.get('carrier_id') or obj.get('disabled')
            or obj.get('ball_integrity',{}).get('intact') is False):
        raise ValueError('Fling capture requires its actual detached intact ball')
    WORLD.require_present_object(obj)
    if plan['physical_source']!=BALL_BODY.source(engine.r):raise ValueError('Fling physical ball source changed')
    nat=C.integer(admitted['nat'],'Fling native accuracy natural',1,20)
    serial=actor.spec.get('capture_attempt_serial',0)+1
    attempt_id='capture-'+str(serial)
    record={'id':attempt_id,'item':admitted['item_rule_id'],'ball_kind':'poke_ball',
            'target':target.spec.get('id',target.name),'hit':True,'captured':False,'status':'thrown',
            'source':'pokemon/capture-rate','capture_source':options.get('capture_source'),
            'action':'move','accuracy_natural':nat,'physical_instance_id':obj['id'],
            'physical_item':admitted['item_rule_id'],'physical_source':deepcopy(plan['physical_source']),
            'throw_origin':WORLD.location_of(actor),'throw_target':WORLD.location_of(target),
            'throw_map_id':getattr(engine.grid,'_tunnel_map_id',None) if engine.grid is not None else None,
            'move_origin':{key:admitted[key] for key in ('move_id','edition','completion_id','actor_id','target_id')}}
    conversion=options.get('snare_conversion')
    if conversion is not None:
        record['snare_conversion']={'authority':'gm_ruling','source':'input/ch04-trainer-classes.md:405-407',
            'book_modifier':-10,'procedure':deepcopy(plan['procedure']),'attempt_id':attempt_id,
            'request':deepcopy(conversion),'applied_modifier':plan['snare_bonus']}
    if options.get('type_manual_instance_id') is not None:
        record['type_manual']={'instance_id':options['type_manual_instance_id'],'bonus':plan['manual_bonus'],'source':'C2CSV/inventory:70:1'}
    actor.spec['capture_attempt_serial']=serial
    actor.spec.setdefault('capture_attempts',{})[attempt_id]=record
    obj['ball_integrity']={'intact':True,'source':BALL_BODY.SOURCE,'basis':'undamaged before Fling'}
    return _post_hit(engine,actor,target,record=record,actual_ball=obj,combo=plan['combo'],
        rarity=options.get('rarity',0),capture_source=options.get('capture_source'),cannon=None,
        momentum_plan=plan['momentum_plan'],fixed_capture=options.get('fixed_capture'),procedure=procedure,
        gotta_swap=options.get('gotta_swap'),nat=nat,choice_callback=None,bonus=plan['bonus'],
        bmod=plan['bmod'],bwhy=plan['bwhy'],snare_bonus=plan['snare_bonus'],net_bonus=plan['net_bonus'],
        manual_bonus=plan['manual_bonus'],fixed_reroll=options.get('fixed_reroll'),choice=plan['choice'],
        collector=plan['collector'],new_family=plan['new_family'],placement_plan=plan['placement_plan'],
        name=plan['ball_name'],ball_name=plan['ball_name'])
