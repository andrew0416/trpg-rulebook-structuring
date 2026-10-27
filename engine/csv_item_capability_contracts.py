"""Native actions and projections for remaining CSV capability/environment rows."""
import arithmetic_policy as NUMERIC
from copy import deepcopy
from math import ceil, isfinite

import common_checks as C
import csv_item_contract_policy as POLICY
import roll_pools as POOLS


STATE = "csv_remaining_capability_state"
POISON_MOVES = frozenset(("애시드봄", "독침천발", "페이탈클로", "맹독엄니", "독찌르기", "독침",
                          "포이즌테일", "셸암즈", "오물공격", "오물폭탄", "스모그"))
PICKUP_TABLE = (
    (5, 'none'), (7, 'x_item'), (10, 'berry'), (13, 'poke_ball'),
    (16, 'status_healing'), (17, 'evolution_stone'), (18, 'vitamin'),
    (19, 'held_item'), (20, 'tm'),
)
PICKUP_SOURCE = {'file':'input/ch10-index-reference.md',
    'sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}
PICKUP_ITEMS_SOURCE = {'file':'input/ch09-equipment.md',
    'sha256':'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2'}


def pickup_category(rules, face):
    from source_context import verified_source
    verified_source(rules, PICKUP_SOURCE, label='Pickup category table')
    C.integer(face, 'Pickup d20 face', 1, 20)
    return next(category for maximum, category in PICKUP_TABLE if face <= maximum)


def _pickup_item(rules, category, item_id):
    from source_context import verified_source
    verified_source(rules, PICKUP_ITEMS_SOURCE, label='Pickup item categories')
    if category == 'tm':
        import pokemon_teaching as TEACHING
        row = TEACHING.catalog(rules)['machines'].get(item_id)
        if (not isinstance(row, dict) or row.get('kind') != 'TM'
                or type(row.get('number')) is not int or item_id != 'TM' + str(row['number'])):
            raise ValueError('Pickup TM reward needs an actual selected TM catalog identity')
        return item_id
    import equipment_item_contracts as EQUIPMENT,restorative_items as MEDICINE
    import vitamin_moves as VITAMINS,food_effects as FOOD
    header = EQUIPMENT.selected_item(rules, item_id)
    stones = {'item/' + name for name in ('불꽃의돌','물의돌','천둥의돌','리프의돌','달의돌',
                                         '태양의돌','빛의돌','어둠의돌','각성의돌')}
    # These Chapter 9 evolution-only entries share the catalog's coarse
    # use='held'; unlike King's Rock/Razor Claw/Razor Fang, they have no
    # separate entry in the printed Held Items table.
    evolution_only = {'item/' + name for name in ('심해의이빨','심해의비늘','용의비늘','업그레이드',
        '괴상한패치','에레키부스터','마그마부스터','동글동글돌','금속코트','프로텍터',
        '영계의천','향기주머니','휘핑팝')}
    eligible = {
        'x_item': item_id in MEDICINE.X_ITEMS,
        'berry': header.get('category') == '음식' and item_id.endswith('열매') and FOOD.handles(item_id),
        'poke_ball': header.get('use') == 'ball',
        'status_healing': item_id in (MEDICINE.HELD_CONSUMABLES - MEDICINE.X_ITEMS) | set(FOOD.DRINKS),
        'evolution_stone': item_id in stones,
        'vitamin': item_id in VITAMINS.ALL_ITEMS,
        'held_item': header.get('category') == '포켓몬 도구' and header.get('use') == 'held'
                     and item_id not in stones | evolution_only,
    }
    if not eligible.get(category, False):
        raise ValueError('GM selected item is outside the rolled Pickup category')
    return item_id


def _caps(actor):
    import state_grants as GRANTS
    return set(GRANTS.effective(actor, "capabilities"))


def has(actor, name):
    return name in _caps(actor)


def require(actor, name):
    if not has(actor, name):
        raise ValueError(name + " actual capability required")


def _state(actor):
    value = actor.spec.setdefault(STATE, {"version": 1, "receipts": []})
    validate_actor(actor)
    return value


def _read_state(actor):
    """Validate a lookup without creating an authoritative receipt ledger."""
    validate_actor(actor)
    value = actor.spec.get(STATE)
    return {} if value is None else value


def language(actor):
    return {"understands_human": True, "speaks_human": True, "source": "C2CSV/item-data:81:5"} if has(actor, "언어") else None


EGG_WARMER = 'capability/알-부화기'
EGG_HATCHER = 'C2CSV/item-data:82:5'
HEAT_KINDS = ('egg_hatcher_homebrew', 'egg_warmer_core')
HEAT = 'hatch_time_contributions'


def _heat_source(rules, source):
    if source == EGG_HATCHER:
        return '알부화기', 2, 'egg_hatcher_homebrew'
    if source != EGG_WARMER or rules._selected_rule(source) != source:
        raise ValueError('exact selected Egg Warmer source required')
    import hashlib, source_context as SOURCES
    reference={'file':'input/ch10-index-reference.md',
               'sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}
    content=SOURCES.verified_source(rules,reference,label='Egg Warmer')
    if hashlib.sha256(content.decode('utf-8-sig').splitlines()[36].encode('utf8')).hexdigest() != '16305b284639173da74fc35fffeb297b41321051bb47fa47a84eeaad2799d762':
        raise ValueError('Egg Warmer exact source statement changed')
    return '알 부화기', 10, 'egg_warmer_core'


def _validate_heat(engine, receipt):
    import resolution_transaction as TX
    if type(receipt) is not dict or receipt.get('kind') not in HEAT_KINDS:
        raise ValueError('actual Egg Warmer contribution required')
    fields={'kind','source','actor_id','egg_id','at','unknown_index','sequence','seconds','reduced_seconds','day','d2' if receipt['kind']=='egg_hatcher_homebrew' else 'd10'}
    if set(receipt)!=fields|{'sha256'} or receipt['sha256']!=TX.request_fingerprint({k:v for k,v in receipt.items() if k!='sha256'}):
        raise ValueError('Egg Warmer contribution changed')
    source=EGG_HATCHER if receipt['kind']=='egg_hatcher_homebrew' else EGG_WARMER
    if receipt['source']!=source:raise ValueError('Egg Warmer source changed')
    sides=2 if source==EGG_HATCHER else 10
    face=C.integer(receipt['d2' if sides==2 else 'd10'],'Egg Warmer actual die face',1,sides)
    expected=(86400 if face==2 else 0) if sides==2 else (face*3600 if face>1 else 0)
    if receipt['seconds']!=expected:raise ValueError('Egg Warmer contribution does not match its die')
    C.integer(receipt['reduced_seconds'],'Egg Warmer effective reduction',0,expected)
    C.integer(receipt['at'],'Egg Warmer use time',0,engine.elapsed_seconds)
    C.integer(receipt['unknown_index'],'Egg Warmer clock index',0,len(engine.unresolved_time_intervals))
    C.integer(receipt['sequence'],'Egg Warmer use identity',1)
    C.integer(receipt['day'],'Egg Warmer observed day',0)
    for key in ('actor_id','egg_id'):
        if not isinstance(receipt[key],str) or not receipt[key]:raise ValueError('Egg Warmer actual identity required')
    return receipt


def egg_heat_seconds(engine, egg):
    """Read physical warmth on this egg; never require a past heater's capability."""
    rows=egg.get(HEAT,[])
    if type(rows) is not list:raise ValueError('Egg Warmer contributions must be records')
    seen=set();total=0
    for row in rows:
        _validate_heat(engine,row)
        key=(row['actor_id'],row['sequence'])
        if row['egg_id']!=egg['entity_id'] or key in seen:
            raise ValueError('Egg Warmer contribution belongs to one actual egg')
        seen.add(key);total+=row['seconds']
        if egg.get('produced_at') is not None and row['at']<egg['produced_at']:
            raise ValueError('Egg Warmer cannot predate its actual egg')
    return total


def heat_egg(engine, actor, egg_id, *, source=EGG_HATCHER, fixed_d2=None, fixed_d10=None):
    """Both printed variants share actual targets, rolling clock and native commit."""
    import state_grants as GRANTS
    import world_entities as WORLD
    WORLD.require_actors(engine, actor)
    return GRANTS.transition(engine,actor,lambda e,a:_heat_egg(e,a,egg_id,source=source,fixed_d2=fixed_d2,fixed_d10=fixed_d10))


def _heat_egg(engine, actor, egg_id, *, source, fixed_d2, fixed_d10):
    name,sides,kind=_heat_source(engine.r,source)
    if not ({name,source}&_caps(actor)):raise ValueError(name+' actual capability required')
    if actor.kind != 'pokemon':raise ValueError('Egg Warmer requires a Pokemon')
    import pokemon_entities as POKEMON_ENTITIES
    entry = POKEMON_ENTITIES.egg_index(engine).get(egg_id)
    egg = entry[1] if entry is not None else None
    if not isinstance(egg, dict) or egg.get("kind") != "egg" or egg.get("hatched"):
        raise ValueError("Egg Hatcher needs one actual Pokemon Egg")
    if (sides==2 and fixed_d10 is not None) or (sides==10 and fixed_d2 is not None):
        raise ValueError('Egg Warmer die evidence must match its source')
    fixed=fixed_d2 if sides==2 else fixed_d10
    if fixed is not None:C.integer(fixed,'Egg Warmer d'+str(sides)+' face',1,sides)
    day = C.integer(actor.spec.get("frequency_state", {}).get("day", 0), "Egg Hatcher observed day", 0)
    state = _read_state(actor)
    past = [row for row in state.get("receipts", [])
            if isinstance(row, dict) and row.get("kind") in HEAT_KINDS]
    if state.get("egg_hatcher_days") and not past:
        raise ValueError("legacy Egg Hatcher use needs its actual 24-hour receipt")
    import elapsed_time as TIME,creation_egg as CREATION,resolution_transaction as TX
    for row in past:
        if TIME.bounds(engine,row.get('at'),row.get('unknown_index',0),0,label='Egg Warmer actual use clock')[0]<86400:
            raise ValueError('Egg Warmer 24-hour use is spent')
    remaining=CREATION.hatch_remaining(engine,egg)
    if remaining is None and 'hatch_remaining_seconds' in egg:
        remaining=C.integer(egg['hatch_remaining_seconds'],'actual egg hatch clock',0)
    face=POOLS.die(engine.rng,sides,fixed=fixed)
    reduction=(86400 if face==2 else 0) if sides==2 else (face*3600 if face>1 else 0)
    if remaining is not None:egg['hatch_remaining_seconds']=max(0,remaining-reduction)
    _state(actor).setdefault("egg_hatcher_days", []).append(day)
    receipt={'kind':kind,'source':source,'actor_id':actor.entity_id,'egg_id':egg_id,'day':day,
             'd2' if sides==2 else 'd10':face,'seconds':reduction,
             'reduced_seconds':reduction if remaining is None else min(remaining,reduction),
             'at':engine.elapsed_seconds,'unknown_index':len(engine.unresolved_time_intervals),
             'sequence':len(_state(actor)['receipts'])+1}
    receipt['sha256']=TX.request_fingerprint(receipt)
    _state(actor)["receipts"].append(receipt)
    egg.setdefault(HEAT,[]).append(deepcopy(receipt))
    return deepcopy(receipt)


def juicer_begin(engine, actor, berry_instance_id):
    require(actor, "과즙기")
    import item_maturation as MATURATION
    return MATURATION.begin_sessions(engine, actor, berry_instance_id)


def juicer_session(engine, actor, *, berry_consumed=False, bottled=False,
                   container_selection=None, recipient=None, reason=None):
    require(actor, "과즙기")
    import item_maturation as MATURATION
    return MATURATION.session_step(engine, actor, berry_consumed=berry_consumed,
        bottled=bottled, container_selection=container_selection, recipient=recipient, reason=reason)


GATHER_UNOWN = 'capability/안농-모으기'
UNOWN_SUMMON = 'gather_unown_core'


def _unown_source(rules):
    if rules._selected_rule(GATHER_UNOWN) != GATHER_UNOWN:
        raise ValueError('exact selected core Gather Unown source required')
    import source_context as SOURCES
    SOURCES.verified_source(rules, {'file':'input/ch10-index-reference.md',
        'sha256':'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'},
        label='core Gather Unown')


def _unown_receipts(actor):
    import resolution_transaction as TX
    rows=[]
    for row in actor.spec.get(STATE,{}).get('receipts',[]):
        if not isinstance(row,dict) or row.get('kind') != UNOWN_SUMMON:continue
        fields={'kind','source','actor_id','unown_id','level','d8','selection','at','unknown_index','sha256'}
        if set(row)!=fields or row['sha256']!=TX.request_fingerprint({k:v for k,v in row.items() if k!='sha256'}):
            raise ValueError('core Gather Unown actual use receipt changed')
        if row['source']!=GATHER_UNOWN or row['actor_id']!=actor.entity_id:
            raise ValueError('core Gather Unown source or summoner identity changed')
        if not isinstance(row['unown_id'],str) or not row['unown_id'].strip():raise ValueError('actual summoned identity required')
        faces=row['d8']
        if not isinstance(faces,list) or len(faces)!=2:raise ValueError('two actual d8 faces required')
        for face in faces:C.integer(face,'Gather Unown d8 face',1,8)
        C.integer(row['level'],'summoned Unown level',2,16)
        if row['level']!=sum(faces):raise ValueError('summoned level must match the actual 2d8 roll')
        _unown_selection(row['selection'])
        C.integer(row['at'],'Gather Unown use time',0)
        C.integer(row['unknown_index'],'Gather Unown clock index',0)
        rows.append(row)
    return rows


def _unown_selection(selection):
    # The source gives no distribution over Unown forms. A GM supplies the
    # observed random result; it never substitutes another species or a sheet.
    if type(selection) is not dict or set(selection)!={'species_id','form','reason'} or selection['species_id']!='pokemon/안농':
        raise ValueError('observed random selection of the actual Unown species required')
    for key in ('form','reason'):
        if not isinstance(selection[key],str) or not selection[key].strip():raise ValueError('observed random Unown '+key+' required')


def summon_unown(engine, actor, *, entity_id, selection, location, side, side_reason, fixed_d8=None):
    """Core native summon. Arrival establishes no trainer relationship.

    selection is a GM observation {species_id, form, reason}, not an existing
    actor/spec. The native species builder owns the new individual sheet.
    """
    import state_grants as GRANTS,world_entities as WORLD
    WORLD.require_actors(engine,actor)
    return GRANTS.transition(engine,actor,lambda e,a:_summon_unown(e,a,entity_id,selection,location,side,side_reason,fixed_d8))


def _summon_unown(engine, actor, entity_id, selection, location, side, side_reason, fixed_d8):
    _unown_source(engine.r)
    rune=__import__('rune_master').gather_authorized(engine,actor)
    if not rune and (actor.kind!='pokemon' or actor.level<20 or not ({GATHER_UNOWN,'안농 모으기'}&_caps(actor))):
        raise ValueError('core Gather Unown requires an actual level-20 Pokemon with its live capability')
    import world_entities as WORLD,elapsed_time as TIME,resolution_transaction as TX
    if not isinstance(entity_id,str) or not entity_id.strip() or entity_id in WORLD.entity_index(engine):
        raise ValueError('fresh distinct actual summoned Unown identity required')
    _unown_selection(selection)
    WORLD._text(side,'GM-observed independent Unown side')
    WORLD._text(side_reason,'GM Unown side observation reason')
    import state_fields as F
    placement=F.location(location)
    if fixed_d8 is not None:
        if not isinstance(fixed_d8,(tuple,list)) or len(fixed_d8)!=2:raise ValueError('two actual d8 faces required')
        for face in fixed_d8:C.integer(face,'Gather Unown d8 face',1,8)
    _read_state(actor)
    for row in _unown_receipts(actor):
        if TIME.bounds(engine,row['at'],row['unknown_index'],0,label='Gather Unown actual weekly clock')[0]<604800:
            raise ValueError('core Gather Unown actual week is spent')
    import turn as TURN
    if not TURN.spend(engine,actor,'standard','안농 모으기'):
        return {'summoned':False,'reason':'no_standard_action'}
    faces=[POOLS.die(engine.rng,8,fixed=None if fixed_d8 is None else fixed_d8[i]) for i in range(2)]
    level=min(sum(faces),actor.level)
    from builder import build_pokemon
    from engine import Combatant
    spec=build_pokemon(engine.r,selection['species_id'],level,wild=True,side=side,
        extra={'id':entity_id,'gather_unown_origin':{'source':GATHER_UNOWN,'summoner_id':actor.entity_id,
            'selection':deepcopy(selection),'side_observation':{'side':side,'reason':side_reason}}})
    # A random physical form is an appearance observation, not a mechanical
    # species/form override. Unknown disposition, loyalty and nature stay so.
    spec.pop('pos',None);spec['location']=placement
    unown=Combatant(engine.r,spec)
    engine.gm.add_combatant(unown,side=side,reason='core Gather Unown: '+side_reason)
    receipt={'kind':UNOWN_SUMMON,'source':GATHER_UNOWN,'actor_id':actor.entity_id,'unown_id':entity_id,
        'level':level,'d8':faces,'selection':deepcopy(selection),'at':engine.elapsed_seconds,
        'unknown_index':len(engine.unresolved_time_intervals)}
    receipt['sha256']=TX.request_fingerprint(receipt)
    _state(actor)['receipts'].append(receipt)
    return {'summoned':True,'pokemon':unown,'receipt':deepcopy(receipt)}


def gather_unown(engine, actor, unown, *, occult_total):
    require(actor, "안농모으기")
    if actor.kind != "pokemon" or actor.level < 20 or unown.kind != "pokemon" or unown.level != 15 or "안농" not in str(unown.spec.get("species", unown.name)):
        raise ValueError("Gather Unown needs level 20 user and one actual random level-15 Unown")
    session = getattr(engine, "session_epoch", 0)
    last = _state(actor).get("gather_unown_session")
    if last is not None and session - last < 4:
        raise ValueError("Gather Unown four-session frequency is spent")
    import turn as TURN
    if not TURN.spend(engine, actor, "standard", "안농모으기"):
        return {"summoned": False, "reason": "no_standard_action"}
    if unown not in engine.everyone:
        engine.gm.add_combatant(unown)
    unown.on_field = True
    allied = occult_total >= 16
    if allied:
        unown.side = actor.side
    _state(actor)["gather_unown_session"] = session
    _state(actor)["hidden_power_frequency"] = "At-Will"
    receipt = {"summoned": True, "unown_id": unown.entity_id, "level": 15, "occult_total": occult_total,
               "immediate_ally": allied, "session": session}
    _state(actor)["receipts"].append(receipt)
    return receipt


def hidden_power_frequency(actor, ordinary):
    return "At-Will" if has(actor, "안농모으기") else ordinary


def poison_glands_profile(actor):
    require(actor, "독샘")
    return {"type": "독", "classes": ("물리", "특수"), "source": "C2CSV/item-data:87:5"}


def poison_glands_eligible(move, *, homebrew=False):
    name = str(move.get("name", ""))
    if name in POISON_MOVES:
        return True
    if not homebrew or move.get("type") != "독":
        return False
    import re
    import pass_moves as PASS
    from custom_species import parse_range
    import frequency as FREQUENCY
    raw = str(move.get("range", ""))
    counts=re.findall(r'(?:대상|targets?)\s*(\d+)|(\d+)\s*(?:체|대상|targets?)',raw,re.I)
    keywords=[]
    for field in ('keywords','keyword'):
        value=move.get(field,'')
        keywords.extend(value if isinstance(value,(list,tuple)) else re.split(r'[,;\s]+',str(value)))
    frequency=move.get('frequency')
    kind=('at_will' if frequency=='At-Will' else 'every_other_turn' if frequency=='EOT'
          else FREQUENCY.parse(frequency)[0])
    multiple = (parse_range(raw).get('shape')
                or any(token in raw for token in ("폭발", "원뿔", "버스트", "광선", "전체", "필드", "모든", "다수"))
                or re.search(r'\b(?:blast|burst|cone|line)\b',raw,re.I)
                or PASS.is_pass(move)
                or any(int(left or right)>1 for left,right in counts)
                or any(str(token).strip().casefold() in ('통과','pass') for token in keywords))
    return bool(homebrew and move.get("type") == "독" and kind in ('at_will','every_other_turn') and not multiple)


def sense_life(engine, observer, target, *, distance_m=None, gm_basis=None):
    require(observer, "생명감지")
    import world_entities as WORLD
    WORLD.require_actors(engine, observer, target)
    if observer.kind != "pokemon":raise ValueError("Life Sense requires an actual Pokemon observer")
    if distance_m is not None and (type(distance_m) not in (int, float) or not isfinite(distance_m) or distance_m < 0):
        raise ValueError("Life Sense needs an observed finite nonnegative distance")
    if gm_basis is not None:
        WORLD._text(gm_basis, "Life Sense GM distance basis")
        if distance_m is None:raise ValueError("GM distance basis needs its actual measured distance")
        basis = {"kind": "gm_observation", "reason": gm_basis}
    else:
        import body_state as BODY
        from grid import cheb
        measured = min(cheb(a, b) for a in BODY.cells(observer, require_complete=True)
                       for b in BODY.cells(target, require_complete=True))
        from physical_limits import number
        observer_height=number(observer.spec.get('_movement_altitude',0),'Life Sense observer altitude',minimum=0)
        target_height=number(target.spec.get('_movement_altitude',0),'Life Sense target altitude',minimum=0)
        measured = max(measured, abs(observer_height - target_height))
        if distance_m is not None and distance_m != measured:
            raise ValueError("Life Sense distance disagrees with actual body geometry")
        distance_m = measured
        basis = {"kind": "body_geometry"}
    excluded = target.kind == 'pokemon' and ("고스트" in target.types or has(target, "숨죽이기")) or target.dead
    return {"located": distance_m <= 5 and not excluded, "distance_m": distance_m,
            "excluded": "ghost_or_dead_silent" if excluded else None, "target_id": target.entity_id, "basis": basis}


def scavenge(engine, actor, *, fixed_d20=None, during="extended_action",
             duration_minutes=None, duration_reason=None, rest_id=None):
    require(actor, "청소부")
    import world_entities as WORLD, state_grants as GRANTS
    WORLD.require_actors(engine, actor)
    if during not in ("extended_action", "extended_rest"):
        raise ValueError("Scavenger occurs during an Extended Action or Extended Rest")
    if engine.encounter_active:
        raise ValueError("Scavenger requires actual noncombat activity")
    day = actor.spec.get("frequency_state", {}).get("day", 0)
    if day in _read_state(actor).get("scavenger_days", []):
        raise ValueError("Scavenger daily use is spent")
    C.integer(duration_minutes, "Scavenger actual activity minutes", 1)
    WORLD._text(duration_reason, "Scavenger GM duration reason")
    if fixed_d20 is not None:C.integer(fixed_d20, "Scavenger d20 face", 1, 20)
    if during == 'extended_action' and rest_id is not None:
        raise ValueError('Scavenger Extended Action cannot claim a rest identity')
    if actor.dead or actor.fainted:raise ValueError('Scavenger requires a conscious actor')
    if during == 'extended_rest':
        WORLD._text(rest_id, 'Scavenger actual rest')
        if duration_minutes < engine.r.mech('combat/resting')['extended_rest']['min_hours'] * 60:
            raise ValueError('Scavenger requires an actual Extended Rest interval')
    engine.preflight_advance_time(duration_minutes * 60, [actor])
    def apply(e, a):
        import activity_jobs as JOBS, turn as TURN, downtime as DT, resolution_transaction as TX
        start=e.elapsed_seconds
        if during == 'extended_action':
            if not TURN.spend(e, a, 'extended', '청소부'):
                raise ValueError('Scavenger requires its Extended Action')
            job_id = 'scavenger:' + a.entity_id + ':' + str(day)
            JOBS._start(e, a, (), job_id=job_id, source='C2CSV/item-data:89:5',
                policy={'required_seconds': duration_minutes*60}, context={'reason':duration_reason})
            completed=JOBS._work(e, JOBS._row(e, job_id), interval_id=job_id+':work', seconds=duration_minutes*60)
            if (completed['status']!='complete' or completed['progress_seconds']!=duration_minutes*60
                    or completed['end_seconds']!=start+duration_minutes*60):
                raise ValueError('Scavenger requires actual completed activity time')
            activity = {'job_id':job_id}
        else:
            activity = DT.observe_activity(e, [a], duration_minutes, qualifies_as_rest=True,
                reason=duration_reason, rest_id=rest_id)[0]
            rest=a.spec.get('rest_interval',{})
            if (activity.get('qualifies_as_rest') is not True or activity.get('start')!=start
                    or activity.get('end')!=start+duration_minutes*60 or rest.get('id')!=rest_id
                    or rest.get('total_minutes',0)<duration_minutes):
                raise ValueError('Scavenger requires actual completed Extended Rest')
        if e.elapsed_seconds!=start+duration_minutes*60:
            raise ValueError('Scavenger actual activity clock did not complete')
        # The actual activity and reward share the native rollback boundary.
        face = POOLS.die(e.rng, 20, fixed=fixed_d20)
        face = __import__('oracle').replace_d20(e,a,face,'scavenger')
        category = pickup_category(e.r, face)
        _state(a).setdefault('scavenger_days', []).append(day)
        receipt = {'kind':'scavenger', 'day':day, 'd20':face, 'item_id':None, 'category':category,
                   'pickup_source':deepcopy(PICKUP_SOURCE), 'during':during,
                   'activity':activity, 'actor_id':a.entity_id, 'rolled_at':e.elapsed_seconds, 'gm_selection':None}
        receipt['sha256'] = TX.request_fingerprint(receipt)
        _state(a)['receipts'].append(receipt)
        return deepcopy(receipt)
    return GRANTS.transition(engine, actor, apply)


def _legacy_scavenge_receipt(receipt):
    # Preserve historical stock and receipts without inventing a past GM choice.
    return set(receipt) == {'kind','day','d20','item_id','during','activity','actor_id','sha256'}


def resolve_scavenge_reward(engine, actor, *, day, item_id, reason):
    """The rolled category is fixed; the GM selects the actual item once."""
    import world_entities as WORLD,state_grants as GRANTS,resolution_transaction as TX
    WORLD.require_actors(engine, actor)
    validate_world(engine, WORLD.actor_index(engine))
    C.integer(day, 'Scavenger reward day', 0)
    WORLD._text(reason, 'Scavenger GM item selection reason')
    rows = [row for row in _read_state(actor).get('receipts', [])
            if row.get('kind') == 'scavenger' and row.get('day') == day]
    if len(rows) != 1:raise ValueError('one actual rolled Scavenger activity required')
    receipt = rows[0]
    if _legacy_scavenge_receipt(receipt):
        return C.PendingDecision('Legacy Scavenger loot needs actual GM and inventory reconciliation',
            basis={'original_receipt':deepcopy(receipt),
                   'printed_category':pickup_category(engine.r, receipt['d20']),
                   'inventory_preserved':True, 'actual_gm_selection_required':True,
                   'automatic_inventory_adjustment':False})
    if receipt['category'] == 'none':raise ValueError('Pickup 1-5 finds nothing')
    if receipt['gm_selection'] is not None:raise ValueError('Scavenger reward was already selected')
    selected = _pickup_item(engine.r, receipt['category'], item_id)
    def apply(e, a):
        row = next(row for row in _state(a)['receipts'] if row.get('kind') == 'scavenger' and row['day'] == day)
        previous = deepcopy(row)
        a.spec.setdefault('items', {})[selected] = C.integer(a.spec.get('items', {}).get(selected, 0),
                                                           'actual reward inventory count', 0) + 1
        row.update(item_id=selected, gm_selection={'item_id':selected, 'reason':reason,
                                                  'at':e.elapsed_seconds, 'source':deepcopy(PICKUP_ITEMS_SOURCE)})
        row['sha256'] = TX.request_fingerprint({k:v for k,v in row.items() if k != 'sha256'})
        e.gm._rec('Scavenger GM Pickup item', previous, row, reason, a)
        return deepcopy(row)
    return GRANTS.transition(engine, actor, apply)


def _tinkerer_selection(rules,weapon_class,moves):
    import weapon_actions as WEAPONS
    if weapon_class != 'large_melee':raise ValueError('Tinkerer intrinsic scrap weapon uses the Large Melee class')
    if not isinstance(moves,list) or not 1<=len(moves)<=2:raise ValueError('Tinkerer selects one Proficient and optional Master Move')
    definitions=WEAPONS.rules_policy(rules)['moves']
    for mid,rank in zip(moves,(4,6)):
        definition=definitions.get(mid)
        if definition is None or definition['rank']!=rank or rules._selected_rule(mid)!=mid:
            raise ValueError('Tinkerer needs an actual selected weapon Move of the chosen rank')
        # The intrinsic scrap weapon may select only Large Melee compatible Moves.
        allowed=definition['kinds']
        if allowed is not None and '대형 근접무기' not in allowed:
            raise ValueError('Tinkerer weapon Move is restricted to another weapon class')


def configure_tinkerer(engine, actor, *, weapon_class, proficient_move, master_move=None, steel=False):
    require(actor, "땜장이")
    import world_entities as WORLD
    WORLD.require_actors(engine, actor)
    if actor.kind != 'pokemon':raise ValueError('Tinkerer requires an actual Pokemon')
    _tinkerer_selection(engine.r,weapon_class,[proficient_move]+([master_move] if master_move else []))
    if type(steel) is not bool:raise ValueError('Tinkerer optional Steel choice must be explicit')
    if master_move is not None and actor.level < 30:
        raise ValueError("Tinkerer Master Move requires level 30 and a selected Move")
    day = actor.spec.get("frequency_state", {}).get("day", 0)
    current = _read_state(actor).get("tinkerer")
    if current and current["configured_day"] == day:
        raise ValueError("Tinkerer daily configuration is spent")
    if master_move is not None:
        import held_equipment as HELD
        if HELD.any_held(actor):
            raise ValueError("Master Tinkerer configuration forbids a held item")
    row = {"weapon_id": "intrinsic-scrap:" + actor.entity_id, "weapon_class": weapon_class,
           "moves": [proficient_move] + ([master_move] if master_move else []), "steel": bool(steel),
           "configured_day": day, "intrinsic": True, "unstealable": True, "uses_held_slot": master_move is not None,
           "source":'C2CSV/item-data:92:5'}
    import state_grants as GRANTS,turn as TURN
    def apply(e,c):
        if not TURN.spend(e,c,'extended','땜장이 무기 개조'):raise ValueError('Tinkerer configuration requires its Extended Action')
        source='tinkerer:'+c.entity_id
        GRANTS.revoke(c,source,engine=e)
        _state(c)['tinkerer']=deepcopy(row)
        GRANTS.grant_moves(c,row['moves'],source,'capability',owner_id=c.entity_id,
                          lifetime='while_capability',rule_id='C2CSV/item-data:92:5',mode='permission')
        GRANTS.state(c)['sources'][source]['required_capability']='땜장이'
        return deepcopy(row)
    return GRANTS.transition(engine,actor,apply)


def tinkerer_weapon(actor):
    row = _read_state(actor).get("tinkerer")
    if not row or not has(actor,'땜장이'):return None
    source=actor.spec.get('state_grants',{}).get('sources',{}).get('tinkerer:'+actor.entity_id,{})
    if (source.get('rule_id')!='C2CSV/item-data:92:5' or source.get('move_mode')!='permission'
            or source.get('required_capability')!='땜장이' or source.get('grants',{}).get('moves')!=row['moves']):return None
    return deepcopy(row)


def tinkerer_move(actor, move, *, engine=None):
    row = tinkerer_weapon(actor)
    if not row or move.get("id") not in row["moves"]:
        return None
    if row['uses_held_slot']:
        import held_equipment as HELD
        if actor.level<30 or HELD.any_held(actor):raise ValueError('Master Tinkerer requires level 30 and forfeits held items')
    result = deepcopy(move)
    if row["steel"]:
        result["type"] = "강철"
    if engine is None:raise ValueError('intrinsic weapon adaptation needs its actual engine')
    import weapon_actions as WEAPONS,world_entities as WORLD
    WORLD.require_actors(engine,actor)
    kinds={'small_melee':'소형 근접무기','large_melee':'대형 근접무기','short_ranged':'단거리 사격무기','long_ranged':'장거리 사격무기'}
    result=WEAPONS.adapt_weapon_move(engine,actor,result,row['weapon_id'],{'kind':kinds[row['weapon_class']]},weapon_bonuses=False)
    result['_weapon_attack'].update(source='C2CSV/item-data:92:5',intrinsic=True)
    result["_exclude_stab"] = True
    result["source_weapon"] = row["weapon_id"]
    return result


def muscle_power_bonus(actor):
    return 2 if has(actor, "개선된 인조 근육") else 0


def muscle_jump_bonus(actor):
    return {"high_jump": 1, "long_jump": 1} if has(actor, "개선된 인조 근육") else {"high_jump": 0, "long_jump": 0}


def injury_recovery_seconds(actor, ordinary_seconds):
    C.integer(ordinary_seconds, "ordinary injury recovery seconds", 0)
    return NUMERIC.ceil_ratio(ordinary_seconds,2) if has(actor, "개선된 인조 근육") else ordinary_seconds


def daily_injury_heal(actor, ordinary):
    C.integer(ordinary, "ordinary daily healed injuries", 0)
    return ordinary + (1 if has(actor, "개선된 인조 근육") else 0)


def essence_view(actor):
    projection=actor.spec.get('csv_essence_projection')
    essence = C.integer(projection['essence'] if isinstance(projection,dict) else actor.spec.get("essence", 10), "Essence", 0)
    return {"essence": essence, "base_injuries": 3 if essence == 0 else 1 if essence <= 7 else 0,
            "aura_and_ghost_moves_allowed": essence > 4, "ghost_weakness_steps": 1 if essence <= 2 else 0,
            "augmentation_allowed": essence > 0 and "고스트" not in actor.types}


def essence_move_allowed(actor, move):
    view = essence_view(actor)
    keywords=str(move.get('keywords','')).casefold()
    aura = any(word in keywords for word in ('오러','파동','aura'))
    return bool(view["aura_and_ghost_moves_allowed"] or move.get("type") != "고스트" and not aura)


def essence_effectiveness(actor, move_type, multiplier):
    view = essence_view(actor)
    if move_type != "고스트" or not view["ghost_weakness_steps"]:
        return multiplier
    sequence = {0.0: 1.0, 0.125: 0.25, 0.25: 0.5, 0.5: 1.0, 1.0: 1.5, 1.5: 2.0, 2.0: 3.0, 3.0: 3.0}
    return sequence.get(multiplier, multiplier)


def reconcile_essence_augmentations(engine, actor):
    if actor.spec.get('csv_essence_projection') is not None:
        return sync_essence(engine,actor)
    view = essence_view(actor)
    if view["augmentation_allowed"]:
        return []
    removed = []
    for key in list(actor.spec.get("augmentations", {})):
        removed.append(key)
        actor.spec["augmentations"].pop(key)
    _state(actor)["receipts"].append({"kind": "essence_augmentation_removal", "removed": removed,
                                      "at": engine.elapsed_seconds})
    return removed


def sync_essence(engine, actor):
    """Project the explicit CSV option from the one actual augmentation graph."""
    import special_entities as SPECIAL,world_entities as WORLD
    rows=[row for row in getattr(engine,'_physical_objects',{}).values()
          if row.get('kind')=='augmentation_set' and row.get('actor_id')==actor.entity_id
          and row.get('essence_profile')=='C2CSV/inventory:100:17']
    if not rows:
        actor.spec.pop('csv_essence_projection',None)
        return []
    if len(rows)!=1:raise ValueError('one actual CSV Essence augmentation owner required')
    row=rows[0];removed=[]
    if '고스트' in actor.types and row['installations']:
        removed=deepcopy(row['installations']);row['installations']=[]
        row.setdefault('essence_removals',[]).append({'source':'C2CSV/inventory:100:17','at':engine.elapsed_seconds,'installations':removed,'reason':'actual Ghost type'})
        import augmentation_moves as AUGMENT_MOVES
        AUGMENT_MOVES.sync(engine)
    view=SPECIAL.validate_record(engine,row)
    actor.spec['csv_essence_projection']={'source':'C2CSV/inventory:100:17','augmentation_set_id':row['id'],
        'essence':view['essence'],'installations':deepcopy(row['installations'])}
    if view['essence']<=4:
        actor.spec['capabilities']=[cap for cap in actor.spec.get('capabilities',[]) if not aura_capability(cap)]
    return removed


def aura_capability(value):
    from skill_modifiers import key
    return key(value) in {key(v) for v in ('파동 감지','Aura Reader','capability/파동-감지','파동술','Aura Pulse','capability/파동술')}


def essence_base_injuries(actor):
    return essence_view(actor)['base_injuries'] if 'csv_essence_projection' in actor.spec else 0


def toxic_environment(actor, toxicity, effects):
    if toxicity not in ("low", "middle", "high") or not isinstance(effects, dict):
        raise ValueError("toxic environment needs explicit low/middle/high effects")
    if has(actor, "함정면역"):
        effective = None
    elif has(actor, "함정내성"):
        effective = {"high": "middle", "middle": "low", "low": None}[toxicity]
    else:
        effective = toxicity
    return {"original": toxicity, "effective": effective, "negative_effects": deepcopy(effects.get(effective, [])) if effective else []}


def start_navigation(engine, actor, navigation_id, *, lightyears):
    require(actor, "에스퍼 네비게이터")
    import world_entities as WORLD
    WORLD.require_actors(engine,actor)
    if actor.kind!='pokemon':raise ValueError('Psychic Navigator requires an actual Pokemon')
    if not isinstance(navigation_id, str) or not navigation_id or type(lightyears) not in (int, float) or not isfinite(lightyears) or lightyears <= 0:
        raise ValueError("Psychic Navigator needs a route identity and positive distance")
    routes = _state(actor).setdefault("navigation_routes", {})
    row = routes.setdefault(navigation_id, {"lightyears": lightyears, "dc": ceil(lightyears * 15),
                                             "total": 0, "checks": [], "completed": False, "started_at":engine.elapsed_seconds})
    if row["lightyears"] != lightyears:
        raise ValueError("navigation route identity cannot change distance")
    return deepcopy(row)


def navigation_check(engine, actor, navigation_id, *, skill, total, check_id=None):
    require(actor, "에스퍼 네비게이터")
    if skill not in ("지각", "집중") or type(total) is not int:
        raise ValueError("Psychic Navigator uses one actual Perception or Focus total")
    row = _state(actor).get("navigation_routes", {}).get(navigation_id)
    if not isinstance(row, dict):
        raise ValueError("actual unfinished navigation route required")
    return navigation_contribute(engine, actor, actor, navigation_id, skill=skill, total=total, check_id=check_id)


def navigation_contribute(engine, owner, contributor, navigation_id, *, skill, total, check_id=None):
    import world_entities as WORLD,state_grants as GRANTS
    WORLD.require_actors(engine,owner,contributor)
    require(owner,'에스퍼 네비게이터')
    require(contributor, "에스퍼 네비게이터")
    if contributor.kind!='pokemon':raise ValueError('Psychic Navigator contributor must be an actual Pokemon')
    row = _state(owner).get("navigation_routes", {}).get(navigation_id)
    if not isinstance(row, dict):
        raise ValueError("actual unfinished cooperative route required")
    if check_id is not None:
        WORLD._text(check_id,'actual navigation step identity')
        previous=next((r for r in row['checks'] if r.get('id')==check_id),None)
        if previous:
            if (previous['actor_id'],previous['skill'],previous['total'])!=(contributor.entity_id,skill,total):
                raise ValueError('navigation step identity cannot change its actual contribution')
            return deepcopy(row)
    if row['completed']:raise ValueError('actual unfinished cooperative route required')
    if skill not in ("지각", "집중") or type(total) is not int:
        raise ValueError("cooperative navigation needs an actual supported skill total")
    engine.preflight_advance_time(300,[owner,contributor])
    def apply(e,c,*others):
        start=e.elapsed_seconds
        e.advance_time(300,[c,*others])
        r=c.spec[STATE]['navigation_routes'][navigation_id]
        r['total']+=total
        r['checks'].append({'id':check_id or navigation_id+':step:'+str(len(r['checks'])+1),
            'actor_id':contributor.entity_id,'skill':skill,'total':total,'minutes':5,'started_at':start,'at':e.elapsed_seconds})
        r['completed']=r['total']>=r['dc']
        return deepcopy(r)
    return GRANTS.transition(engine,owner,apply,participants=() if contributor is owner else (contributor,))


def navigation_jump(actor, navigation_id):
    row = _state(actor).get("navigation_routes", {}).get(navigation_id)
    if not isinstance(row, dict):
        raise ValueError("actual navigation route required")
    return {"safe": row["completed"], "total": row["total"], "dc": row["dc"],
            "gm_consequence_required": not row["completed"]}


def validate_actor(actor):
    state = actor.spec.get(STATE)
    if state is None:
        return True
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("receipts"), list):
        raise ValueError("remaining CSV capability state is invalid")
    if state.get('juicer'):
        raise ValueError('legacy CSV Juicer needs an actual observed physical maturation record')
    _unown_receipts(actor)
    import resolution_transaction as TX
    for receipt in state['receipts']:
        if not isinstance(receipt,dict) or receipt.get('kind')!='scavenger' or 'activity' not in receipt:continue
        if (receipt.get('sha256')!=TX.request_fingerprint({k:v for k,v in receipt.items() if k!='sha256'})
                or receipt.get('actor_id')!=actor.entity_id):
            raise ValueError('Scavenger actual activity receipt changed')
        C.integer(receipt['day'],'Scavenger observed day',0)
        C.integer(receipt['d20'],'Scavenger actual d20 face',1,20)
        if receipt['day'] not in state.get('scavenger_days',[]):raise ValueError('Scavenger daily receipt missing')
        if _legacy_scavenge_receipt(receipt):
            if not isinstance(receipt['item_id'], str) or not receipt['item_id']:
                raise ValueError('legacy Scavenger receipt needs its original item identity')
            continue
        C.integer(receipt.get('rolled_at'), 'Scavenger actual roll time', 0)
        if (receipt.get('pickup_source') != PICKUP_SOURCE
                or receipt.get('category') != pickup_category(actor.r, receipt['d20'])
                or 'gm_selection' not in receipt):
            raise ValueError('Scavenger needs its actual source category and GM selection receipt')
        choice = receipt['gm_selection']
        if choice is None:
            if receipt.get('item_id') is not None:raise ValueError('Pickup item requires actual GM selection')
        elif (not isinstance(choice, dict) or choice.get('source') != PICKUP_ITEMS_SOURCE
                or choice.get('item_id') != receipt.get('item_id')
                or _pickup_item(actor.r, receipt['category'], receipt['item_id']) != receipt['item_id']
                or not isinstance(choice.get('reason'), str) or not choice['reason'].strip()):
            raise ValueError('Scavenger GM item differs from its source category')
        else:C.integer(choice.get('at'), 'Scavenger GM item selection time', receipt['rolled_at'])
    row=state.get('tinkerer')
    if row is not None:
        if not isinstance(row,dict) or row.get('source')!='C2CSV/item-data:92:5' or row.get('weapon_id')!='intrinsic-scrap:'+actor.entity_id:
            raise ValueError('Tinkerer requires its actual sourced intrinsic weapon')
        _tinkerer_selection(actor.r,row.get('weapon_class'),row.get('moves'))
        C.integer(row.get('configured_day'),'Tinkerer actual configuration day',0)
        if row.get('intrinsic') is not True or row.get('unstealable') is not True or type(row.get('steel')) is not bool or type(row.get('uses_held_slot')) is not bool or row['uses_held_slot']!=(len(row['moves'])==2):
            raise ValueError('Tinkerer intrinsic ownership or held-slot state changed')
    routes=state.get('navigation_routes',{})
    if not isinstance(routes,dict):raise ValueError('actual navigation routes must be records')
    for route_id,route in routes.items():
        if not isinstance(route_id,str) or not route_id or not isinstance(route,dict):raise ValueError('actual navigation destination identity required')
        distance=route.get('lightyears')
        if type(distance) not in (int,float) or not isfinite(distance) or distance<=0 or route.get('dc')!=ceil(distance*15):raise ValueError('navigation distance or DC changed')
        C.integer(route.get('started_at'),'actual navigation start time',0)
        if not isinstance(route.get('checks'),list):raise ValueError('actual navigation step records required')
        ids=set();total=0;last=route['started_at']
        for check in route['checks']:
            if not isinstance(check,dict) or not isinstance(check.get('id'),str) or not check['id'] or check['id'] in ids:
                raise ValueError('one actual navigation contribution per step identity required')
            ids.add(check['id'])
            if not isinstance(check.get('actor_id'),str) or not check['actor_id'] or check.get('skill') not in ('지각','집중') or type(check.get('total')) is not int or check.get('minutes')!=5:raise ValueError('navigation contributor and actual supported skill total required')
            C.integer(check.get('started_at'),'navigation step start',last)
            C.integer(check.get('at'),'navigation step end',check['started_at']+300,check['started_at']+300)
            total+=check['total'];last=check['at']
        if route.get('total')!=total or type(route.get('completed')) is not bool or route['completed']!=(total>=route['dc']):raise ValueError('navigation progress must match its actual five-minute steps')
    return True


def validate_world(engine, index):
    POLICY.policy(engine.r)
    for row in getattr(engine,'_physical_objects',{}).values():
        if row.get('kind')=='augmentation_set' and row.get('essence_profile')=='C2CSV/inventory:100:17':
            actor=index.get(row.get('actor_id'))
            if actor is None or actor.spec.get('csv_essence_projection') is None:
                raise ValueError('actual selected CSV Essence graph requires its source-owned actor projection')
    for actor in index.values():
        projection=actor.spec.get('csv_essence_projection')
        if projection is not None:
            import special_entities as SPECIAL
            row=getattr(engine,'_physical_objects',{}).get(projection.get('augmentation_set_id'),{})
            if (row.get('kind')!='augmentation_set' or row.get('actor_id')!=actor.entity_id or row.get('essence_profile')!='C2CSV/inventory:100:17'
                    or projection!={'source':'C2CSV/inventory:100:17','augmentation_set_id':row['id'],
                        'essence':SPECIAL.validate_record(engine,row)['essence'],'installations':row['installations']}):
                raise ValueError('CSV Essence projection differs from its actual source augmentation graph')
        validate_actor(actor)
        for receipt in actor.spec.get(STATE,{}).get('receipts',[]):
            if not isinstance(receipt,dict) or receipt.get('kind')!='scavenger' or 'activity' not in receipt:continue
            if not _legacy_scavenge_receipt(receipt) and (receipt['rolled_at'] > engine.elapsed_seconds
                    or (receipt['gm_selection'] is not None and receipt['gm_selection']['at'] > engine.elapsed_seconds)):
                raise ValueError('Scavenger roll and GM selection need actual observed time')
            activity=receipt['activity']
            if receipt['during']=='extended_action':
                import activity_jobs as JOBS
                row=JOBS._row(engine,activity.get('job_id'))
                if (row['owner'] is not actor or row['source']!='C2CSV/item-data:89:5'
                        or row['status']!='complete' or row['progress_seconds']<=0):
                    raise ValueError('Scavenger actual completed activity required')
            elif receipt['during']=='extended_rest':
                import rest_intervals as INTERVALS
                if (activity not in actor.spec.get(INTERVALS.ACTIVITIES,[])
                        or activity.get('qualifies_as_rest') is not True
                        or activity.get('minutes',0)<engine.r.mech('combat/resting')['extended_rest']['min_hours']*60):
                    raise ValueError('Scavenger actual Extended Rest required')
            else:raise ValueError('Scavenger actual activity kind changed')
        import elapsed_time as TIME
        for receipt in _unown_receipts(actor):
            TIME.bounds(engine,receipt['at'],receipt['unknown_index'],0,label='Gather Unown actual weekly clock')
        for route in actor.spec.get(STATE,{}).get('navigation_routes',{}).values():
            if route['started_at']>engine.elapsed_seconds:raise ValueError('navigation start is in the future')
            for check in route['checks']:
                if check['actor_id'] not in index or check['at']>engine.elapsed_seconds:raise ValueError('navigation needs its actual contributor and observed clock')
    return True
