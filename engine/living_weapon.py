"""Living Weapon: one consenting actual Pokemon/holder relation, no item clone.

The relation lives only on the weapon actor. Ordinary equipment records and
temporary move permissions are projections of that relation, never new actors.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import state_grants as G
import world_entities as W
import skill_modifiers as S

SOURCE='capability/살아있는-무기'
KEY='living_weapon'
HISTORY='_living_weapon_detached'
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
    if (type(row)is not dict or set(row)!={'source','pokemon_id','wielder_id','species','consent','slots','grant_source'}
        or row['source']!=SOURCE or row['pokemon_id']!=pokemon.entity_id or row['consent'] is not True
        or row['species']!=species(engine,pokemon)):
        raise ValueError('Living Weapon relation identity/source/consent changed')
    wielder=index.get(row['wielder_id'])
    if wielder is None or wielder is pokemon:raise ValueError('actual distinct Living Weapon holder required')
    if row['grant_source']!='living:'+pokemon.entity_id:raise ValueError('Living Weapon grant source identity changed')
    if row['slots'] not in (['주요손'],['반대손'],['주요손','반대손']):raise ValueError('Living Weapon hand slots changed')
    if (row['species']=='킬가르도' and row['slots']!=['주요손','반대손'] or
        row['species']=='단칼빙' and len(row['slots'])!=1):raise ValueError('Living Weapon species/hand shape changed')
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


def equip(engine,wielder,pokemon,*,consent,slots=None):
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
    def apply(e,a,p):
        import turn as TURN
        _pay_standard(e,a);_pay_standard(e,p)
        row={'source':SOURCE,'pokemon_id':p.entity_id,'wielder_id':a.entity_id,'species':name,
             'consent':True,'slots':slots,'grant_source':'living:'+p.entity_id}
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
            G.numeric(a,'evasion_mod',2 if name=='쌍검킬' else 1,row['grant_source'],bounds=(-6,6))
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


def _available(engine,wielder):
    import weapon_actions as WEAPONS
    result={}
    for key,entry in wielder.custom_conditions.get('equipped_weapons',{}).items():
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
    wanted=list(_available(engine,wielder)) if _present(pokemon) and _present(wielder) else []
    prior=pokemon.spec.get(G.KEY,{}).get('sources',{}).get(sid,{})
    if prior.get('grants',{}).get('moves',[])==wanted:return
    G.revoke(pokemon,sid,engine=engine)
    if wanted:G.grant_moves(pokemon,wanted,sid,'living_weapon',owner_id=wielder.entity_id,
                           lifetime='equipped',rule_id=SOURCE,mode='permission')


def prepare_borrowed(engine,actor,move,weapon_id=None):
    found=relation(engine,actor)
    if not found or found[0] is not actor:return None
    pokemon,wielder,row=relation(engine,actor,usable=True)
    options=_available(engine,wielder).get(move['id'],[])
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
    if found and found[0] is actor and found[1].kind=='pokemon':return found[1]
    return actor


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


def ignore_no_guard(engine,attacker,target,effect):
    if not no_guard(effect):return False
    return any((found:=relation(engine,a)) and found[0] is a for a in (attacker,target))


def accuracy_stage(engine,attacker,target,ordinary):
    """Exclude only sourced No Guard, then keep the existing bounded law."""
    if not any((found:=relation(engine,a)) and found[0] is a for a in (attacker,target)):return ordinary
    ledger=attacker.spec.get(G.KEY,{})
    row=ledger.get('numbers',{}).get('accuracy_stage')
    if row is None:return ordinary
    sources=ledger.get('sources',{})
    removed=[uid for uid in row['sources'] if no_guard({'_rule_id':sources.get(uid,{}).get('rule_id'),'source_id':uid})]
    if not removed:return ordinary
    import effect_lifetimes as LIFE
    stage=row['base']+sum(value for uid,value in row['sources'].items() if uid not in removed)
    return max(-6,min(6,max(-6,min(6,stage))+LIFE.numeric(attacker,'accuracy_modifier')))


def validate_world(engine,index):
    for p in index.values():
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
        permission=p.spec.get(G.KEY,{}).get('sources',{}).get(row['grant_source'])
        if permission and (permission.get('move_mode')!='permission' or permission.get('rule_id')!=SOURCE or permission.get('owner_id')!=w.entity_id):
            raise ValueError('Living Weapon move permission ownership changed')
    for w in index.values():
        for entry in w.custom_conditions.get('equipped_weapons',{}).values():
            uid=entry['weapon'].get('living_actor')
            if uid and (uid not in index or KEY not in index[uid].spec or index[uid].spec[KEY]['wielder_id']!=w.entity_id):
                raise ValueError('orphan actual Living Weapon equipment')
    return True
