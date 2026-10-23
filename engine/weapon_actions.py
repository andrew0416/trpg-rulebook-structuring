"""Sourced weapon equipment adaptations; keep base move IDs, effects and frequency."""
import copy
import json
from pathlib import Path
import re
import skill_modifiers as SKILL

SOURCE = "ch09-equipment/장비/무기"

def policy(engine, *, validate=True):
    return rules_policy(engine.r,validate=validate)


def rules_policy(rules, *, validate=True):
    if validate and rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError("selected weapon variant needs its own policy")
    if not hasattr(rules,"_weapon_policy"):
        rules._weapon_policy=json.loads((Path(rules.root)/"data/weapon-policy.json").read_text(encoding="utf-8"))
    return rules._weapon_policy

def validate_grant(engine, actor, weapon, move_id):
    rules=policy(engine); row=rules["moves"].get(move_id)
    if row is None:raise ValueError("selected move is not a sourced ordinary weapon grant")
    if actor.kind=='pokemon' and not weapon.get('living_actor') and row['rank']>4:raise ValueError('Wielder cannot gain weapon moves above Adept')
    if engine.r._selected_rule(move_id)!=move_id:raise ValueError("selected weapon move variant requires its own policy")
    import optional_weapon_framework as FRAMEWORK
    if FRAMEWORK.skill_rank(engine,actor,weapon)<row["rank"]:raise ValueError("weapon move rank prerequisite not met")
    if row["kinds"] is not None and weapon["kind"] not in row["kinds"]:
        raise ValueError("weapon move is restricted to another weapon kind")
    if row["rank"]>=6 and (weapon.get("grade","간단")!="좋음" or weapon.get("slot","주요손").replace(" ","")=="반대손"):
        raise ValueError("Master weapon move requires a Fine weapon outside the off-hand slot")

def prepare(engine, actor, move, weapon_id=None):
    import optional_weapon_framework as FRAMEWORK
    import living_weapon as LIVING
    borrowed=LIVING.borrowed(engine,actor,move)
    if borrowed is not None:return borrowed
    borrowed=LIVING.prepare_borrowed(engine,actor,move,weapon_id)
    if borrowed is not None:return borrowed
    if move.get('_weapon_attack',{}).get('source')=='item/몬스터볼-캐논':
        weapon_id=move['_weapon_attack']['key']
    if weapon_id is not None and move.get('id') == engine.r.move_id('오물폭탄'):
        import csv_item_physical_contracts as CSV_ITEMS
        obj = getattr(engine, '_physical_objects', {}).get(weapon_id, {})
        if obj.get('item_rule_id') == 'item/몬스터볼-캐논':
            profile = CSV_ITEMS.cannon_profile(engine,actor,weapon_id,projectile='sludge_bomb')
            out = copy.deepcopy(move)
            out['range'] = '15, 대상 1'
            out['_weapon_attack'] = {'key':weapon_id,'range':{'origin':15,'targets':1,'parsed':True,'raw':out['range']},
                'db_bonus':0,'accuracy_bonus':profile['accuracy_bonus'],'minimum_distance':0,'source':'item/몬스터볼-캐논'}
            return out
    if "_weapon_attack" in move:
        if move['_weapon_attack'].get('intrinsic'):
            import csv_item_capability_contracts as CSV_CAPABILITIES
            intrinsic=CSV_CAPABILITIES.tinkerer_move(actor,engine.r.move(move['id']),engine=engine)
            if intrinsic is None:raise ValueError('intrinsic weapon source is no longer available')
            return intrinsic
        return FRAMEWORK.adapt_move(engine,actor,move)
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    optional=OPTIONAL_EQUIPMENT.prepare_weapon_move(engine,actor,move,weapon_id)
    if optional is not None:return FRAMEWORK.adapt_move(engine,actor,optional)
    import csv_item_capability_contracts as CSV_CAPABILITIES
    intrinsic=CSV_CAPABILITIES.tinkerer_weapon(actor)
    if intrinsic and move.get("id") in intrinsic.get("moves", ()):
        if weapon_id not in (None,intrinsic["weapon_id"]):raise ValueError("selected weapon is not the intrinsic Tinkerer weapon")
        return CSV_CAPABILITIES.tinkerer_move(actor,move,engine=engine)
    ledger=actor.custom_conditions.get("equipped_weapons",{})
    candidates=[(key,entry) for key,entry in ledger.items() if move["id"] in entry.get("available_moves",[])]
    if weapon_id is not None:
        candidates=[x for x in candidates if weapon_id in (x[0],x[1]["weapon"]["name"],x[1].get("instance_id"))]
        if len(candidates)!=1:raise ValueError("selected physical weapon does not grant this move")
    elif len(candidates)>1:
        raise ValueError("shared weapon move requires an explicit weapon_id")
    if not candidates:
        if move.get("source")=="weapon":raise ValueError("weapon is no longer equipped")
        if move["id"] in policy(engine,validate=False)["moves"]:
            raise ValueError("ordinary weapon move requires an equipped granting weapon")
        return move
    key,entry=candidates[0];weapon=entry["weapon"]
    import wielder_capability as WIELDER
    if not LIVING.require_weapon(engine,actor,weapon):WIELDER.require_weapon(engine,actor,weapon)
    policy(engine)
    enhanced=move["id"]==entry["struggle_id"]
    if not enhanced:
        if FRAMEWORK.profile_for_weapon(engine,actor,weapon) and FRAMEWORK.profile_for_weapon(engine,actor,weapon)["arcane"]:
            FRAMEWORK.validate_loadout(engine,actor,weapon)
        else:validate_grant(engine,actor,weapon,move["id"])
    out=adapt_weapon_move(engine,actor,move,key,weapon,enhanced=enhanced)
    return FRAMEWORK.adapt_move(engine,actor,out)


def adapt_weapon_move(engine,actor,move,key,weapon,*,enhanced=False,weapon_bonuses=True):
    """Shared ordinary and intrinsic weapon range, shape and accuracy rules."""
    import turn as TURN
    kind=TURN.WEAPON_KIND[weapon['kind']]
    out=copy.deepcopy(move)
    rng=copy.deepcopy(engine.r.moves_mech.get(move["id"],{}).get("header",{}).get("range",{}))
    raw=out.get("range","")
    if not enhanced and ("WR" in raw or "무기 범위" in raw):
        origin="melee" if "근접" in kind["range"] else int(kind["range"].split(",")[0])
        raw=raw.replace("무기 범위",str(origin)).replace("WR",str(origin)).replace("melee","근접")
        rng.update(origin=origin,parsed=True,raw=raw)
        match=re.search(r"대상\s*(\d+)",raw)
        if match:rng["targets"]=int(match.group(1))
        if "폭발" in raw:
            size=re.search(r"폭발\s*(\d+)",raw)
            if size:rng.update(shape="blast",size=int(size.group(1)))
        out["range"]=raw
    if "근접" not in kind["range"] and type(rng.get("origin")) in (int,float) and "자신" not in raw:
        import throwing_masteries as THROWING
        rng["origin"]=THROWING.extend(actor,rng["origin"],'ranged_weapon')
        raw=re.sub(r"^\s*\d+(?:\.\d+)?",str(rng["origin"]),raw,count=1)
        rng["raw"]=raw;out["range"]=raw
    if not enhanced and weapon_bonuses and isinstance(out.get("ac"),int):out["ac"]+=kind["ac"]
    out["_weapon_attack"]={"key":key,"range":rng,"db_bonus":0 if enhanced or not weapon_bonuses else kind["db"],
        "accuracy_bonus":-2 if weapon.get("slot","주요손").replace(" ","")=="반대손" else 0,
        "minimum_distance":kind.get("min_range",0),"source":SOURCE}
    import living_weapon as LIVING
    out['_weapon_attack']['accuracy_bonus']+=LIVING.penalty(engine,actor,key)
    return out

def range_spec(engine,move,actor=None):
    import pass_moves as PASS
    converted=PASS.range_spec(engine,actor,move)
    if converted is not None:return converted
    import stat_ace as STAT
    maneuver=STAT.scope(engine,actor,move)
    if maneuver is not None:return STAT.range_spec(engine,actor,move,{})
    override=move.get("_struggle_range") or move.get("_class_move_range") or move.get("_optional_move_range") or move.get("_weapon_attack",{}).get("range")
    if override:
        import duelist as DUELIST
        return DUELIST.range_spec(engine,actor,move,override)
    from copy import deepcopy
    reviewed=engine.r.moves_reviewed.get(move["id"],{})
    result=deepcopy(reviewed.get("range") or engine.r.moves_mech.get(move["id"],{}).get("header",{}).get("range") or {"raw":move.get("range","")})
    # Built-in Struggle has a source range string but no generated header.
    if 'origin' not in result and result.get('raw','').split(',')[0].strip()=='근접':
        result['origin']='melee'
    bonus=reviewed.get("weather_range_bonus")
    if bonus is not None:
        if (type(bonus) is not dict or set(bonus)!={'if_weather','value'} or
            not isinstance(bonus['if_weather'],str) or type(bonus['value']) is not int or
            type(result.get('size')) is not int):
            raise ValueError('reviewed conditional area bonus needs an exact weather and integer area size')
        import effects as FX
        if FX.weather_matches(engine,bonus['if_weather'],actor):
            result['size']+=bonus['value']
            if result['size']<=0:raise ValueError('conditional effect area must remain positive')
    import dancer as DANCER
    result=DANCER.range_spec(move,result)
    if actor is not None:
        import static_trainer_modifiers as STATIC_MODIFIERS
        result=STATIC_MODIFIERS.range_spec(actor,move,result)
        import stat_ace as STAT
        result=STAT.special_range(engine,actor,move,result)
    import native_area_hit_effects as AREA_HIT
    import duelist as DUELIST
    result=DUELIST.range_spec(engine,actor,move,AREA_HIT.range_spec(engine,move,result))
    import style_expert as STYLE
    return __import__('type_ace').range_spec(engine,actor,move,STYLE.range_spec(engine,actor,move,result))

def is_self_only(rng):
    """A self origin with no area or printed alternative has only its user."""
    return (rng.get('origin') == 'self' and not rng.get('shape')
            and not re.search(r'또는|\bor\b', rng.get('raw', ''), re.I))


def is_field(rng):
    """Whether the printed range owns the entire current combat field."""
    if not isinstance(rng,dict):raise ValueError('move range must be a mapping')
    token=str(rng.get('raw','')).split(',',1)[0].strip().casefold()
    return token in ('필드','전체','field')


def field_members(engine):
    """Actual bodies currently present in the declared encounter field.

    Field ignores distance and ordinary visibility, but never reaches reserves,
    recalled bodies, captured bodies, or actors merely known to the world.
    """
    if not engine.encounter_active:raise ValueError('Field range requires an actual encounter')
    import combat_state_lifecycle as COMBAT
    members=COMBAT.members(engine)
    present=[c for c in members if getattr(c,'on_field',True) and not getattr(c,'captured',False)]
    if not present or len({id(c) for c in present})!=len(present):raise ValueError('Field range requires distinct present encounter members')
    return present


def validate_target(engine,actor,target,move,*,allow_approach=False):
    rng=range_spec(engine,move,actor)
    if is_field(rng):
        if actor is not target:raise ValueError('Field move requires its user as the activation anchor')
        if not any(actor is c for c in field_members(engine)):raise ValueError('Field move user is not present in the encounter')
        return
    if is_self_only(rng):
        if actor is not target:raise ValueError("self move requires the user target")
        return
    spec=move.get("_weapon_attack")
    if not spec:return
    if rng.get('shape'):
        import area_targets as AREA
        import body_state as BODY
        if '_area_aim' not in move:raise ValueError('weapon area attack requires an explicit aim cell')
        if not BODY.cells(target,require_complete=True).intersection(AREA.cells(engine,actor,move)):
            raise ValueError('actual target outside explicitly aimed weapon area')
        return
    if "자신" in move.get("range",""):
        if actor is not target:raise ValueError("self weapon move requires the wielder target")
        return
    from grid import cheb
    import body_state as BODY
    distance=(min(cheb(a,b) for a in BODY.attack_cells(engine,actor,move) for b in BODY.cells(target,require_complete=True)) if engine.grid is not None else cheb(actor.pos,target.pos))
    if distance<spec["minimum_distance"]:raise ValueError("long-range weapon cannot attack within four metres")
    reach=BODY.melee_reach(actor) if rng.get("origin")=="melee" else rng.get("origin")
    if type(reach) not in (int,float):raise ValueError("weapon range needs a sourced execution policy")
    if not allow_approach and distance>reach:raise ValueError("target outside selected weapon range")
    if engine.grid is not None and not BODY.in_range(engine,actor,target,distance,move=move):raise ValueError("weapon line of sight blocked")

def accuracy_bonus(move):
    import improvised_weapons as IMPROVISED
    return move.get("_weapon_attack",{}).get("accuracy_bonus",0)+IMPROVISED.bonus(move,'accuracy_roll_delta')

def damage_bonus(move):
    import improvised_weapons as IMPROVISED
    return move.get("_weapon_attack",{}).get("db_bonus",0)+IMPROVISED.bonus(move,'db_delta')
def excludes_stab(move):return bool(move.get("_weapon_attack")) or move.get("source")=="weapon"


CHOICE_EDGE="edge/선택한-무기"
CHOICE_ALIASES={SKILL.key(x) for x in (CHOICE_EDGE,"선택한 무기","무기 선택","Weapon of Choice")}

def disarm_defense(engine,actor,prevent_with_ap):
    """C3-EX-026: an explicit conditional AP declaration, paid only on defeat."""
    import action_points as AP
    owned=actor.spec.get("edges",[])
    choices=actor.spec.get("edge_choices",{})
    if not isinstance(owned,(list,tuple)) or not isinstance(choices,dict):
        raise ValueError("weapon-choice ownership/choices have invalid shape")
    count=sum(SKILL.key(v) in CHOICE_ALIASES for v in owned)
    selected=[v for k,v in choices.items() if SKILL.key(k) in CHOICE_ALIASES]
    if not count:
        if selected:raise ValueError("weapon choice requires the acquired edge")
        if prevent_with_ap not in (None,False):raise ValueError("AP Disarm prevention requires Weapon of Choice")
        return 0,False
    if count!=1 or actor.kind!="trainer":raise ValueError("Weapon of Choice requires one trainer-owned edge")
    if engine.r._selected_rule(CHOICE_EDGE)!=CHOICE_EDGE:raise ValueError("selected Weapon of Choice variant requires its own policy")
    feats=actor.spec.get("feats",[])
    if not isinstance(feats,(list,tuple)):raise ValueError("weapon feature ownership must be a list")
    weapon_feat=False
    for name in feats:
        matches=[uid for uid,u in engine.r.selection.units.items() if u.get("kind")=="entity:feat"
            and SKILL.key(name) in {SKILL.key(uid),SKILL.key(u.get("title",uid)),SKILL.key(u.get("eng") or uid)}]
        if len(matches)!=1:continue
        uid=engine.r._selected_rule(matches[0]);metadata=engine.r.selection.units[uid]
        if "무기" in metadata.get("tags",[]) or "Weapon" in metadata.get("tags",[]):weapon_feat=True
    if not weapon_feat:raise ValueError("Weapon of Choice requires an acquired [Weapon] feature")
    if len(selected)!=1 or not isinstance(selected[0],str):raise ValueError("Weapon of Choice requires one explicit weapon type")
    aliases={"대형 근접 무기":"대형 근접무기","근거리 사격무기":"단거리 사격무기","원거리 사격무기":"장거리 사격무기"}
    chosen=aliases.get(selected[0],selected[0])
    import turn as TURN
    if chosen not in TURN.WEAPON_KIND:raise ValueError("Weapon of Choice needs a sourced ordinary weapon type")
    eligible=any(record["weapon"]["kind"]==chosen for record in actor.custom_conditions.get("equipped_weapons",{}).values())
    if not eligible:
        if prevent_with_ap not in (None,False):raise ValueError("selected weapon type is not currently equipped")
        return 0,False
    if type(prevent_with_ap) is not bool:raise ValueError("Weapon of Choice needs an explicit conditional prevent_with_ap choice")
    if prevent_with_ap and AP.available(actor)<1:raise ValueError("Weapon of Choice prevention requires one available AP")
    return 2,prevent_with_ap

def disarm_options(engine,actor,options,prevent_with_ap):
    """Source-owned defense addition shared by ordinary and Telekinetic Disarm."""
    import common_checks as C,composition_derive as COMPOSITION
    bonus,prevention=disarm_defense(engine,actor,prevent_with_ap)
    import wielder_capability as WIELDER
    result=WIELDER.disarm_options(engine,actor,options)
    if bonus:
        result['mods']=COMPOSITION.derive(result.get('mods',0),
            [{'id':CHOICE_EDGE,'source':CHOICE_EDGE,'value':bonus}],
            [{'law':'add','contributors':[CHOICE_EDGE]}])['value']
    return result,bonus,prevention


def prevent_disarm(engine,actor,selected):
    if not selected:return False
    import action_points as AP
    if AP.available(actor)<1:raise ValueError("declared Disarm prevention no longer has one available AP")
    AP.spend(actor,1)
    engine.log(f"    {actor.name}: 선택한 무기 1 AP 지불 -> 무장해제 방지",CHOICE_EDGE)
    return True
