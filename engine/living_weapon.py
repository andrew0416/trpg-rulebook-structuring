"""Living Weapon: one consenting actual Pokemon/holder relation, no item clone.

The relation lives only on the weapon actor. Ordinary equipment records and
temporary move permissions are projections of that relation, never new actors.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import state_grants as G
import world_entities as W
import skill_modifiers as S

SOURCE='capability/살아있는-무기'
KEY='living_weapon'
HISTORY='_living_weapon_detached'
MOVEMENT='_living_weapon_movement'
SOURCE_SHA='c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'
PROFILES={
 '단칼빙':{'grade':'간단','moves':['move/상처내기'],'hands':1,'shield':False},
 '쌍검킬':{'grade':'간단','moves':['move/두번-베기'],'hands':2,'shield':False},
 '킬가르도':{'grade':'좋음','moves':['move/상처내기','move/출혈'],'hands':1,'shield':True},
}


def selected(engine):
    if engine.r._selected_rule(SOURCE)!=SOURCE:raise ValueError('selected Living Weapon source required')
    if hashlib.sha256((Path(engine.r.root)/'input/ch10-index-reference.md').read_bytes()).hexdigest()!=SOURCE_SHA:
        raise ValueError('Living Weapon source changed; review required')


def policy(engine):
    selected(engine)
    value=json.loads((Path(engine.r.root)/'data/living-weapon-policy.json').read_text(encoding='utf-8'))
    if value.get('schema_version')!=1 or value.get('source')!=SOURCE:
        raise ValueError('known Living Weapon policy required')
    return value


def _borrowing_document(value):
    return {'schema':1,'id':'native/living-weapon-borrowing','variants':[{
        'rule_id':SOURCE,'source':value['source_reference'],
        'values':{'variant':{'$input':'source_text'},'definitions':value['borrowing']},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(value['borrowing']),
            'question':'Living Weapon: Korean borrows all equipped weapon moves; English borrows only this Living Weapon\'s moves. Which complete source definition applies?'}}}]}


def borrowing_choices(engine):
    """Prepare an explicit source decision before the native equipment action."""
    import source_policy as POLICY
    return POLICY.resolve(engine.r,_borrowing_document(policy(engine)))


def _borrowing_definition(engine,row):
    value=policy(engine);choice=row.get('source_choice')
    definition=value['borrowing']['korean_all_equipped']
    if choice is not None:
        import source_policy as POLICY
        resolved=POLICY.resolve(engine.r,_borrowing_document(value),decisions={'source_text':choice})
        if resolved['status']!='PolicyValuesReady':raise ValueError('explicit Living Weapon source decision required')
        definition=resolved['values']['definitions'][resolved['values']['variant']]
    from source_context import verified_source
    reference=definition['source']
    verified_source(engine.r,reference,label='Living Weapon borrowing',
                    source_root='source-audit' if reference['file'].startswith('source-audit/') else 'input')
    return definition


def _no_guard_document(value):
    return {'schema':1,'id':'native/living-weapon-no-guard','variants':[{
        'rule_id':SOURCE,'source':value['source_reference'],
        'values':{'variant':{'$input':'source_text'},'definitions':value['no_guard']},
        'inputs':{'source_text':{'type':'string','authority':'gm','decision_kind':'source_conflict',
            'choices':list(value['no_guard']),
            'question':'Living Weapon: Korean is unaffected by No Guard; English cannot benefit from its own No Guard. Which complete source definition applies?'}}}]}


def no_guard_choices(engine):
    import source_policy as POLICY
    return POLICY.resolve(engine.r,_no_guard_document(policy(engine)))


def _no_guard_definition(engine,row):
    value=policy(engine);choice=row.get('no_guard_choice')
    definition=value['no_guard']['korean_unaffected']
    if choice is not None:
        import source_policy as POLICY
        resolved=POLICY.resolve(engine.r,_no_guard_document(value),decisions={'source_text':choice})
        if resolved['status']!='PolicyValuesReady':raise ValueError('explicit Living Weapon No Guard source decision required')
        definition=resolved['values']['definitions'][resolved['values']['variant']]
    from source_context import verified_source
    reference=definition['source']
    verified_source(engine.r,reference,label='Living Weapon No Guard',
                    source_root='source-audit' if reference['file'].startswith('source-audit/') else 'input')
    return definition


def shield_bonus(engine):
    definitions=policy(engine)['shield']
    # Presence of the errata file is not adoption; the campaign profile admits it.
    definition=definitions['errata'] if definitions['errata']['admission'] in engine.r.ruleset.sources else definitions['core']
    from source_context import verified_source
    verified_source(engine.r,definition['source'],label='Living Weapon shield')
    return definition['bonus']


def species(engine,actor):
    from builder import species_lookup
    for name in PROFILES:
        if actor.spec.get('species')==species_lookup(engine.r,name)['id']:return name
    raise ValueError('actual Honedge, Doublade or Aegislash Pokemon required')


def _present(actor):
    import supplemental_state as SUPPLEMENTAL
    return bool(getattr(actor,'on_field',True) and not actor.captured and not getattr(actor,'dead',False))


def relation(engine,actor,*,usable=False):
    """Read either participant through the single weapon-owned relation."""
    index=W.actor_index(engine)
    rows=[]
    for p in index.values():
        if KEY not in p.spec:continue
        if type(p.spec[KEY])is not dict:raise ValueError('Living Weapon relation must be a mapping')
        if p is actor or p.spec[KEY].get('wielder_id')==actor.entity_id:rows.append((p,p.spec[KEY]))
    if not rows:return None
    if len(rows)!=1:raise ValueError('Living Weapon participants have multiple relations')
    pokemon,row=rows[0]
    fields={'source','pokemon_id','wielder_id','species','consent','slots','grant_source'}
    if (type(row)is not dict or not fields<=set(row)<=fields|{'source_choice','no_guard_choice'}
        or row['source']!=SOURCE or row['pokemon_id']!=pokemon.entity_id or row['consent'] is not True
        or row['species']!=species(engine,pokemon)):
        raise ValueError('Living Weapon relation identity/source/consent changed')
    wielder=index.get(row['wielder_id'])
    if wielder is None or wielder is pokemon:raise ValueError('actual distinct Living Weapon holder required')
    if row['grant_source']!='living:'+pokemon.entity_id:raise ValueError('Living Weapon grant source identity changed')
    if row['slots'] not in (['주요손'],['반대손'],['주요손','반대손']):raise ValueError('Living Weapon hand slots changed')
    if (row['species']=='킬가르도' and row['slots']!=['주요손','반대손'] or
        row['species']=='단칼빙' and len(row['slots'])!=1):raise ValueError('Living Weapon species/hand shape changed')
    _borrowing_definition(engine,row)
    _no_guard_definition(engine,row)
    if usable:
        selected(engine)
        for participant in (pokemon,wielder):
            if not _present(participant):raise ValueError('Living Weapon requires both actual actors available on the field')
            import supplemental_state as SUPPLEMENTAL
            SUPPLEMENTAL.require_actor_access(engine,participant,'Living Weapon')
        if pokemon.pos!=wielder.pos or pokemon.spec.get('_movement_altitude',0)!=wielder.spec.get('_movement_altitude',0):
            raise ValueError('Living Weapon actual bodies are no longer together')
    return pokemon,wielder,row


def group(engine,actor):
    if actor is None:return ()
    found=relation(engine,actor)
    return (actor,) if found is None else found[:2]


def placement_cells(engine,actor,position,cells):
    found=relation(engine,actor)
    if not found:return cells
    import body_state as BODY
    return set(cells)|BODY.at_position(found[1] if actor is found[0] else found[0],position)


def require_weapon(engine,actor,weapon):
    uid=weapon.get('living_actor')
    if uid is None:return False
    found=relation(engine,actor,usable=True)
    if not found or found[0].entity_id!=uid or found[1] is not actor:
        raise ValueError('weapon requires its actual current Living Weapon holder')
    pokemon,_,row=found;profile=PROFILES[row['species']]
    expected={'name':pokemon.name,'kind':'소형 근접무기','grade':profile['grade'],
              'moves':profile['moves'],'living_actor':uid,'slot':weapon.get('slot')}
    if weapon!=expected or weapon['slot'] not in row['slots']:
        raise ValueError('Living Weapon projection differs from the actual Pokemon')
    return True


def _pay_standard(engine,actor):
    """Cooperative source action: ordinary payer, plus partner's actual payment.

    A not-yet-open partner turn reserves its Standard with the existing next
    action-loss owner. This cannot overlap another debt or refresh a spent turn.
    """
    import turn as TURN,action_resources as RESOURCES
    active=engine._active_turn_actor
    if not engine.encounter_active or active is actor:
        if not TURN.spend(engine,actor,'standard',SOURCE):raise ValueError('both participants need a Standard action')
        return
    if RESOURCES.pending(actor):raise ValueError('cooperative Living Weapon payment overlaps an existing action loss')
    pending=engine._ordinary_turn_rounds.get(actor)!=engine.round_no
    old_budget=getattr(actor,'budget',None)
    if pending:actor.budget={k:engine.r.mech('combat/action-economy')['per_round'][k] for k in RESOURCES.KINDS}
    engine._active_turn_actor=actor
    try:
        if not TURN.spend(engine,actor,'standard',SOURCE):raise ValueError('both participants need a Standard action')
    finally:
        engine._active_turn_actor=active
        if pending:actor.budget=old_budget
    if pending:RESOURCES.schedule(actor,{'standard':1})


def equip(engine,wielder,pokemon,*,consent,slots=None,source_choice=None,no_guard_choice=None):
    W.require_actors(engine,wielder,pokemon);selected(engine)
    if pokemon.kind!='pokemon' or wielder.kind not in ('trainer','pokemon') or pokemon is wielder:
        raise ValueError('actual distinct wielder and Pokemon required')
    name=species(engine,pokemon);profile=PROFILES[name]
    if consent is not True:raise ValueError('actual Living Weapon Pokemon permission required')
    if pokemon.fainted:raise ValueError('unconscious Pokemon cannot give initial Living Weapon permission')
    if relation(engine,pokemon) or relation(engine,wielder):raise ValueError('Living Weapon participant already equipped')
    if not all(_present(a) for a in (wielder,pokemon)):raise ValueError('actual available participants required')
    from grid import cheb
    if cheb(wielder.pos,pokemon.pos)>1:raise ValueError('Living Weapon must be within actual equipment reach')
    slots=list(slots or (['주요손','반대손'] if name!='단칼빙' else ['주요손']))
    if (slots not in (['주요손'],['반대손'],['주요손','반대손']) or
        name=='단칼빙' and len(slots)!=1 or name=='킬가르도' and slots!=['주요손','반대손']):
        raise ValueError('Living Weapon requires its actual species hand shape')
    occupied={s for row in wielder.custom_conditions.get('equipped_weapons',{}).values() for s in row['slots']}
    occupied.update(s for row in getattr(wielder,'_item_reg',{}).values() for s in row.get('slots',()))
    if occupied.intersection(slots):raise ValueError('Living Weapon hand slot already occupied')
    _borrowing_definition(engine,{'source_choice':source_choice})
    _no_guard_definition(engine,{'no_guard_choice':no_guard_choice})
    def apply(e,a,p):
        import turn as TURN
        _pay_standard(e,a);_pay_standard(e,p)
        row={'source':SOURCE,'pokemon_id':p.entity_id,'wielder_id':a.entity_id,'species':name,
             'consent':True,'slots':slots,'grant_source':'living:'+p.entity_id}
        if source_choice is not None:row['source_choice']=deepcopy(source_choice)
        if no_guard_choice is not None:row['no_guard_choice']=deepcopy(no_guard_choice)
        p.spec[KEY]=row;p.pos=a.pos
        p.spec['_movement_altitude']=a.spec.get('_movement_altitude',0)
        keys=[]
        for slot in (slots if name=='쌍검킬' else slots[:1]):
            weapon={'name':p.name,'kind':'소형 근접무기','grade':profile['grade'],
                    'moves':profile['moves'],'living_actor':p.entity_id,'slot':slot}
            keys.append(TURN.equip_weapon(e,a,weapon))
        if profile['shield']:
            a.custom_conditions['equipped_weapons'][keys[0]]['slots']=['주요손','반대손']
        if name=='쌍검킬' and len(slots)==2 or profile['shield']:
            G._source(a,row['grant_source'],'living_weapon',owner_id=p.entity_id,rule_id=SOURCE,lifetime='equipped')
            G.numeric(a,'evasion_mod',2 if name=='쌍검킬' else shield_bonus(e),row['grant_source'],bounds=(-6,6))
        if name=='킬가르도':
            import ability_state_projection as PROJECTION
            PROJECTION._battle_forms(p);PROJECTION._switch_form_direct(e,p,'블레이드폼')
        refresh(e,p);return {'pokemon_id':p.entity_id,'wielder_id':a.entity_id,'weapon_keys':keys}
    return G.transition(engine,wielder,apply,participants=(pokemon,))


def detach(engine,actor,*,destination=None):
    found=relation(engine,actor,usable=True)
    if found is None:raise ValueError('actual equipped Living Weapon relation required')
    pokemon,wielder,row=found
    import body_state as BODY
    if destination is not None:
        if (not isinstance(destination,(list,tuple)) or len(destination)!=2 or
            any(type(v)is not int for v in destination) or
            __import__('grid').cheb(actor.pos,destination)>1):raise ValueError('separation destination must be within one metre')
        if engine.grid is not None and not BODY.can_place(engine,actor,tuple(destination),ignore_actors=()):
            raise ValueError('separation body cannot fit destination')
    def apply(e,c,p,w):
        import turn as TURN
        if not TURN.spend(e,c,'swift',SOURCE+':separate'):raise ValueError('separation requires either participant Swift action')
        for key,entry in list(w.custom_conditions.get('equipped_weapons',{}).items()):
            if entry['weapon'].get('living_actor')==p.entity_id:TURN.unequip_weapon(e,w,key,_living_detach=True)
        G.revoke(w,row['grant_source'],engine=e);G.revoke(p,row['grant_source'],engine=e)
        p.spec.pop(KEY);p.spec[HISTORY]=True
        if destination is not None:c.pos=tuple(destination)
        return {'separated':True,'pokemon_id':p.entity_id,'wielder_id':w.entity_id}
    return G.transition(engine,actor,apply,participants=(pokemon,wielder))


def _available(engine,pokemon,wielder,row):
    import weapon_actions as WEAPONS
    own_only=_borrowing_definition(engine,row)['scope']=='own_living_weapon'
    result={}
    for key,entry in wielder.custom_conditions.get('equipped_weapons',{}).items():
        if own_only and entry['weapon'].get('living_actor')!=pokemon.entity_id:continue
        for mid in entry['available_moves']:
            if mid==entry['struggle_id']:continue
            try:WEAPONS.prepare(engine,wielder,engine.r.move(mid),weapon_id=key)
            except ValueError:continue
            result.setdefault(mid,[]).append(key)
    return result


def refresh(engine,actor):
    found=relation(engine,actor)
    if not found:return
    pokemon,wielder,row=found;sid=row['grant_source']
    import weapon_actions as WEAPONS
    for key,entry in wielder.custom_conditions.get('equipped_weapons',{}).items():
        if entry['weapon'].get('living_actor')!=pokemon.entity_id:continue
        desired=[key]
        for mid in PROFILES[row['species']]['moves']:
            try:WEAPONS.validate_grant(engine,wielder,entry['weapon'],mid)
            except ValueError:continue
            desired.append(mid)
        for mid in desired:
            if mid not in wielder.moves:
                wielder.moves.append(mid)
                if mid not in entry['introduced_moves']:entry['introduced_moves'].append(mid)
        entry['available_moves']=desired
    wanted=list(_available(engine,pokemon,wielder,row)) if _present(pokemon) and _present(wielder) else []
    prior=pokemon.spec.get(G.KEY,{}).get('sources',{}).get(sid,{})
    if prior.get('grants',{}).get('moves',[])==wanted:return
    G.revoke(pokemon,sid,engine=engine)
    if wanted:G.grant_moves(pokemon,wanted,sid,'living_weapon',owner_id=wielder.entity_id,
                           lifetime='equipped',rule_id=SOURCE,mode='permission')


def prepare_borrowed(engine,actor,move,weapon_id=None):
    found=relation(engine,actor)
    if not found or found[0] is not actor:return None
    pokemon,wielder,row=relation(engine,actor,usable=True)
    options=_available(engine,pokemon,wielder,row).get(move['id'],[])
    if not options:
        if move.get('_living_borrow'):raise ValueError('wielder no longer has this weapon move permission')
        return None
    if weapon_id is None:
        if len(options)>1:raise ValueError('borrowed weapon move requires explicit weapon_id')
        key=options[0]
    else:
        matching=[key for key in options if weapon_id in (key,wielder.custom_conditions['equipped_weapons'][key]['weapon'].get('living_actor'),wielder.custom_conditions['equipped_weapons'][key].get('instance_id'))]
        if len(matching)!=1:raise ValueError('selected donor weapon no longer grants borrowed move')
        key=matching[0]
    import weapon_actions as WEAPONS
    out=WEAPONS.prepare(engine,wielder,engine.r.move(move['id']),weapon_id=key)
    out['_living_borrow']={'pokemon_id':pokemon.entity_id,'wielder_id':wielder.entity_id,'weapon_key':key,'source':SOURCE}
    return out


def borrowed(engine,actor,move):
    marker=move.get('_living_borrow')
    if not marker:return None
    out=prepare_borrowed(engine,actor,engine.r.move(move['id']),marker.get('weapon_key'))
    if out is None or out.get('_living_borrow')!=marker:raise ValueError('Living Weapon borrowed authority changed')
    return out


def penalty(engine,actor,weapon_id):
    if weapon_id is None:return 0
    found=relation(engine,actor)
    if not found:return 0
    p,w,row=found
    entries=w.custom_conditions.get('equipped_weapons',{})
    keys={key for key,entry in entries.items() if entry['weapon'].get('living_actor')==p.entity_id}
    if weapon_id not in keys|{p.entity_id}:return 0
    relation(engine,actor,usable=True)
    return -2 if p.fainted else 0


def check_sources(engine,actor,context):
    if not isinstance(context,dict) or 'living_weapon' not in context:return ()
    declaration=context['living_weapon']
    if type(declaration)is not dict or set(declaration)!={'pokemon_id'}:raise ValueError('exact actual Living Weapon check identity required')
    found=relation(engine,actor,usable=True)
    if not found or declaration['pokemon_id']!=found[0].entity_id:raise ValueError('check requires the actual related Living Weapon equipment')
    value=penalty(engine,actor,declaration['pokemon_id'])
    return ((SOURCE,value,'fainted actual equipment check'),) if value else ()


def movement_donor(engine,actor):
    found=relation(engine,actor,usable=True)
    if found and found[0] is actor:return found[1]
    return actor


def _movement_used(engine,pokemon):
    row=pokemon.spec.get(MOVEMENT)
    if row is None:return 0
    from physical_limits import number
    if (type(row)is not dict or set(row)!={'source','round','distance'} or row['source']!=SOURCE
        or type(row['round'])is not int or not 1<=row['round']<=engine.round_no):
        raise ValueError('Living Weapon shared round movement receipt changed')
    number(row['distance'],'Living Weapon shared movement',minimum=0)
    return row['distance'] if row['round']==engine.round_no else 0


def movement_remaining(engine,actor,*,movement_mode=None):
    found=relation(engine,actor,usable=True)
    if not found or not engine.encounter_active:return None
    pokemon,wielder,_=found
    definition=policy(engine)['movement']
    from source_context import verified_source
    verified_source(engine.r,definition['source'],label='Living Weapon shared round movement',source_root='source-audit')
    speed,_=engine.move_profile(wielder,movement_mode=movement_mode)
    return max(0,speed-_movement_used(engine,pokemon))


def can_shift(engine,actor,distance,*,movement_mode=None):
    remaining=movement_remaining(engine,actor,movement_mode=movement_mode)
    return remaining is None or distance<=remaining


def shifted(engine,actor,distance):
    """Receipt for actual committed native movement, shared across both turns.

    Keep it outside the equipped relation so detaching/re-engaging cannot refill
    the same round. Native movement cursors own continuation and duplicate entry.
    """
    found=relation(engine,actor)
    if not found:return
    if engine.encounter_active:
        pokemon=found[0]
        pokemon.spec[MOVEMENT]={'source':SOURCE,'round':engine.round_no,
                               'distance':_movement_used(engine,pokemon)+distance}
    sync(engine,actor)


def sync(engine,actor):
    found=relation(engine,actor)
    if not found:return
    p,w,row=found;other=w if p is actor else p
    other.pos=actor.pos;other.airborne=getattr(actor,'airborne',False)
    other.spec['_movement_altitude']=actor.spec.get('_movement_altitude',0)


def locked_form(engine,actor,form):
    found=relation(engine,actor)
    return bool(found and found[0] is actor and found[2]['species']=='킬가르도' and form!='블레이드폼')


def no_guard(effect):
    values=(effect.get('_ability'),effect.get('_rule_id'),effect.get('source_id'))
    return any(x in ('노가드 [Playtest]','ability/노가드-playtest','ability:노가드 [Playtest]','No Guard') for x in values)


def ignore_no_guard(engine,attacker,target,effect,*,effect_owner=None):
    if not no_guard(effect):return False
    for actor in (attacker,target):
        found=relation(engine,actor)
        if not found or found[0] is not actor:continue
        if _no_guard_definition(engine,found[2])['scope']=='unaffected':return True
        metadata=(getattr(effect_owner,'spec',{}).get(G.KEY,{}).get('sources',{})
                  .get(effect.get(G.TAG),{}))
        owner_id=metadata.get('owner_id') or getattr(effect_owner,'entity_id',None)
        if (actor is attacker and owner_id==actor.entity_id
            and type(effect.get('value'))in (int,float) and effect['value']>0):return True
    return False


def accuracy_stage(engine,attacker,target,ordinary):
    """Exclude only sourced No Guard, then keep the existing bounded law."""
    endpoints=[(a,found) for a in (attacker,target)
               if (found:=relation(engine,a)) and found[0] is a]
    if not endpoints:return ordinary
    ledger=attacker.spec.get(G.KEY,{})
    row=ledger.get('numbers',{}).get('accuracy_stage')
    if row is None:return ordinary
    sources=ledger.get('sources',{})
    broad=any(_no_guard_definition(engine,found[2])['scope']=='unaffected' for _,found in endpoints)
    own=any(a is attacker for a,_ in endpoints)
    receipts=ledger.get('ability_receipts',{})
    removed=[]
    for uid,value in row['sources'].items():
        metadata=sources.get(uid,{})
        if not no_guard({'_rule_id':metadata.get('rule_id'),'source_id':uid}):continue
        owner=metadata.get('owner_id')
        own_source=owner==attacker.entity_id or (owner is None and uid in receipts.values())
        if broad or own and own_source and value>0:removed.append(uid)
    if not removed:return ordinary
    stage=row['base']+sum(value for uid,value in row['sources'].items() if uid not in removed)
    return __import__('combat_modifiers').accuracy_stage(attacker,engine,stage=max(-6,min(6,stage)))

def validate_world(engine,index):
    for p in index.values():
        if MOVEMENT in p.spec:_movement_used(engine,p)
        if KEY not in p.spec:continue
        pokemon,w,row=relation(engine,p)
        selected(engine)
        entries=[entry for entry in w.custom_conditions.get('equipped_weapons',{}).values() if entry['weapon'].get('living_actor')==p.entity_id]
        expected=len(row['slots']) if row['species']=='쌍검킬' else 1
        if len(entries)!=expected or {slot for entry in entries for slot in entry['slots']}!=set(row['slots']):
            raise ValueError('Living Weapon actual hand/equipment projections disagree')
        for entry in entries:
            # Unavailable actors retain identity, but cannot be used remotely.
            if _present(p) and _present(w):require_weapon(engine,w,entry['weapon'])
        if locked_form(engine,p,p.form):raise ValueError('equipped Aegislash must remain in Blade Form')
        if row['species']=='킬가르도':
            bonus=w.spec.get(G.KEY,{}).get('numbers',{}).get('evasion_mod',{}).get('sources',{}).get(row['grant_source'])
            if bonus!=shield_bonus(engine):raise ValueError('Living Weapon shield differs from the selected source profile')
        permission=p.spec.get(G.KEY,{}).get('sources',{}).get(row['grant_source'])
        if permission and (permission.get('move_mode')!='permission' or permission.get('rule_id')!=SOURCE or permission.get('owner_id')!=w.entity_id):
            raise ValueError('Living Weapon move permission ownership changed')
    for w in index.values():
        for entry in w.custom_conditions.get('equipped_weapons',{}).values():
            uid=entry['weapon'].get('living_actor')
            if uid and (uid not in index or KEY not in index[uid].spec or index[uid].spec[KEY]['wielder_id']!=w.entity_id):
                raise ValueError('orphan actual Living Weapon equipment')
    return True


