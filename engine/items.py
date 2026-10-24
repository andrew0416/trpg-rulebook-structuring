"""
아이템·재주·엣지 소비기: C층 mech(data/items-mech.json + items-llm.json, feats-mech + feats-llm, edges-llm)를 전투원에 꽂는다.
  - 지니는 도구/장비 패시브: bonus_damage(타입별 +5)·damage_reduction(타입/물리/특수 한정)·accuracy/evasion/initiative/crit_range/save_mod·면역·전투단계 상시
  - 소모 아이템(약·음식·열매): engine.use_item(user, item, target) → heal / cure_status / revive / stage_change / temp_hp / 영양제(stat_base_mod)
  - 몬스터볼: ball_modifier(engine, ball, trainer, target) → 1d20 포획 굴림 보정 (에라타 환산: 설명문의 조건을 표로)
  - 재주(feat)·엣지: 트레이너 spec['feats'] / ['edges'] → 상시 수정치는 패시브로, 발동조건은 fire_event 트리거로, 자기 포켓몬 대상 효과는 pokemon 목록에
룰북 원문 효과 가운데 엔진 밖의 것(제작·서술·콘테스트)은 'rule'/'gm'/'craft' 로 남고 등록 시 로그에만 남는다.
"""
import arithmetic_policy as M
import frequency as FREQ
import action_points as AP
import action_metadata as ACTION_META
import state_grants as GRANTS
import re
from copy import deepcopy
import held_equipment as HELD
import species_classification as CLASSIFICATION

import effects as FX
import effects_ext as EXT

TYPES = ["노말", "격투", "비행", "독", "땅", "바위", "벌레", "고스트", "강철", "불꽃", "물", "풀", "전기", "에스퍼", "얼음", "드래곤", "악", "페어리"]
PASSIVE_ITEM_TYPES = {"bonus_damage", "damage_reduction", "accuracy_mod", "evasion_mod", "initiative_mod", "crit_range_mod", "crit_range", "save_mod", "stage_base_mod", "stage_change",
                      "stat_base_mod", "immune_stage_loss", "status_immunity", "weather_immunity", "keyword_immunity", "type_immunity", "move_immunity", "damage_base_mod",
                      "resistance_step", "immunity", "damage_roll_mod", "temp_hp", "stat_mod", "grounded", "grant_ability", "grant_move", "grant_capability", "speed_mod"}
CONSUMABLE_TYPES = {"heal", "cure_status", "cure_all_status", "revive", "stage_change", "temp_hp", "stat_base_mod", "counter", "exp_gain", "stage_reset", "apply_status", "hp_loss", "injury", "heal_injury"}
MAGIC_ROOM_KEY = "magic_room_passive_suspension"


# ---------- 효과 정규화 (초안/규칙 기반의 필드 흔들림 → 엔진 키) ----------
def _type_in(s):
    return next((t for t in TYPES if t in str(s)), None)


def normalize(e, default_target="self"):
    """draft 의 'moves': '불꽃 damaging' / 'vs_type' / 'if': 'physical' 등을 패시브 테이블이 읽는 키로 옮긴다."""
    e = dict(e)
    t = e.get("type")
    if t == "bonus_damage":
        moves = e.get("moves", "")
        ty = _type_in(moves) or e.get("move_type")
        if "chosen" in str(moves) + str(ty):
            # Keep an unresolved selection explicit; None would mean every type.
            e["move_type"] = "chosen"
        elif ty:
            e["move_type"] = ty
        if "damaging" in str(moves):
            e["damaging_only"] = True
        e.pop("moves", None)
    elif t == "damage_reduction":
        ty = e.get("vs_type") or _type_in(e.get("if", "")) if "type" in str(e.get("if", "")) or e.get("vs_type") else None
        condition = str(e.get("if", "")) + " " + str(e.get("vs", ""))
        cls = "물리" if "physical" in condition else "특수" if "special" in condition else "원거리" if "ranged" in condition else None
        if ty or cls:
            e["_scope"] = {"type": ty, "class": cls}
            e.pop("if", None)
    elif t == "crit_range_mod":
        e = {"type": "crit_range", "delta": int(e["value"]) if isinstance(e.get("value"), int) else 0, "moves": e.get("moves", "all"), "_src": e}
    elif t == "stage_base_mod":
        e = dict(e, type="stage_change", delta=int(e.get("value", 1)), base=True, target="self")
        e.pop("value", None)  # Retain species restrictions and other conditions.
    elif t == "stage_change" and e.get("while") == "held":
        e = dict(e, base=True)
    elif t == "status_immunity":
        st = e.get("status")
        e = {"type": "immunity", "status": [s.strip() for s in re.split(r"[/,·]", str(st))] if isinstance(st, str) else list(st or [])}
    elif t == "resistance_step" and isinstance(e.get("if"), str):
        # Exact typed resistance declarations share the ordinary damage
        # consumer.  Preserve every other predicate as unresolved registry
        # data rather than guessing a universal passive.
        match = re.fullmatch(r"\s*attack\s+type\s*==\s*(\S+)\s*", e["if"], re.I)
        if match and match.group(1) in TYPES:
            e["types"] = [match.group(1)]
            e.pop("if", None)
    elif t == "type_immunity":
        e = {"type": "immunity", "to": e.get("type") or e.get("type_")}
    elif t == "initiative_mod" and not isinstance(e.get("value"), int):
        e["value"] = 0
    if t in ("accuracy_mod", "evasion_mod", "damage_reduction", "temp_hp", "stat_base_mod") and e.get("target") in ("holder", "wearer", "user", "own pokemon", None):
        e["target"] = default_target
    return e


# ---------- 지니는 도구 / 장비 ----------
def item_slot_options(header, effects):
    """Known core slots. Slash/or means alternatives; plus means simultaneous slots.
    Homebrew implant/capacity slots remain outside this core-slot parser.
    """
    raw=next((e.get('slot') for e in effects if isinstance(e,dict) and e.get('type')=='trainer_slot'),None)
    raw=raw or header.get('trainer_slot') or header.get('slot')
    if not raw:return []
    aliases={'주요손':'주요손','주로쓰는손':'주요손','손':'주요손',
             '반대손':'반대손','머리':'머리','머리도구':'머리','몸통':'몸통','발':'발','장신구':'장신구'}
    options=[]
    for alternative in re.split(r'/|또는',str(raw).replace(', 또는',' 또는')):
        parts=[re.sub(r'\s+','',x) for x in alternative.strip().split('+')]
        if not parts or any(x not in aliases for x in parts):return []
        options.append([aliases[x] for x in parts])
    return options


def register_item(engine, c, item_name=None, *, source_instance_id=None, as_held=False, held_slot=None, projection=None, resolved_conditions=None):
    """c.item(또는 지정 이름)의 패시브를 등록. 반환: 등록한 effect 수.

    projection: a sourced Fashionista item projection (Dashing Makeover, Dress to
    Impress) that installs the item effects under its own source without any
    physical slot. resolved_conditions: printed item conditions that an actual
    producer has resolved (e.g. the Chic Choice-item suppression), never a guess.
    """
    name = item_name or c.item
    if not name:
        return 0
    import fashionista as FASHIONISTA
    if projection is not None:
        if source_instance_id is not None or as_held or held_slot is not None:raise ValueError("a projected item registration has no physical slot")
        FASHIONISTA.validate_projection(projection)
    if resolved_conditions is not None and (type(resolved_conditions) is not dict or any(type(k) is not str or type(v) is not bool for k,v in resolved_conditions.items())):
        raise ValueError("resolved item conditions must map printed conditions to explicit booleans")
    import researcher_features as RF
    relic=RF.relic_effects(engine,c,name)
    effs, header = relic if relic is not None else engine.r.item_effects(name)
    import blessing_skill_features as BLESSINGS
    shard=BLESSINGS.shard_item(engine,c,name)
    if shard is not None:effs,header=shard
    if effs is None:
        engine.log(f"  {c.name} 도구 {name}: DB 에 없음", "item/unknown")
        return 0
    import gem_effects as GEMS
    gem=GEMS.definition(engine.r,header.get('id'))
    if gem is not None:
        if c.kind=='trainer' and (as_held or held_slot is not None):raise ValueError('Trainer Type Gem requires its off-hand or accessory equipment slot')
        header=dict(header,trainer_slot='반대손 또는 장신구')
        effs=[]
    if header.get("use") == "consumable" or header.get("category") in ("약", "음식"):
        # Holding and consuming are distinct states. A known consumable has a
        # held-source receipt even though merely holding it applies no effects.
        engine.log(f"  {c.name} 도구 {name}: 소모 아이템 보유 (use_item 으로 사용)", f"item/{name}")
        effs=[]
    if c.kind == "trainer" and "포켓몬 전용" in str(header.get("desc", "")):
        engine.log(f"  {c.name} 도구 {name}: 포켓몬 전용 → 트레이너에게 효과 없음", f"item/{name}")
        return 0
    canonical_id = header.get("id", name)
    if source_instance_id is not None:
        if not isinstance(source_instance_id,str) or not source_instance_id.strip():
            raise ValueError("equipment instance requires an explicit identity")
        instance=getattr(engine,"_physical_objects",{}).get(source_instance_id)
        if not isinstance(instance,dict) or instance.get("kind")!="item_instance" or instance.get("item_rule_id")!=canonical_id:
            raise ValueError("equipment instance does not identify this actual item rule")
        import world_entities as W
        W.require_physical_access(instance)
        if 'crafting_origin' in instance and instance.get('disabled'):raise ValueError('disabled crafted product needs its explicit repair')
        if instance.get("equipped_by") not in (None,c.entity_id) or instance.get("carrier_id") not in (None,c.entity_id):
            raise ValueError("equipment instance is possessed by another actor")
        if c.entity_id not in (instance.get("owner_id"),instance.get("carrier_id"),instance.get("equipped_by")):
            raise ValueError("equipment instance must be owned or carried by this actor")
        actors=engine.gm._snapshot_actors(vars(engine))
        actors[id(c)]=c
        for actor in actors.values():
            for entry in getattr(actor,"_item_reg",{}).values():
                if entry.get("instance_id")==source_instance_id:
                    if actor is c and entry.get("item_id")==canonical_id:return 0
                    raise ValueError("equipment instance already has an active registration")
    import static_equipment_contracts as STATIC_EQUIPMENT
    static_plan=STATIC_EQUIPMENT.prepare_register(engine,c,canonical_id,source_instance_id)
    import equipment_variant_contracts as EQUIPMENT_VARIANTS
    variant_plan=EQUIPMENT_VARIANTS.prepare_register(engine,c,canonical_id,source_instance_id,projection=projection)
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    optional_plan=OPTIONAL_EQUIPMENT.prepare_register(engine,c,canonical_id,source_instance_id)
    import fashion_items as FASHION
    fashion_plan=FASHION.prepare_register(engine,c,canonical_id,source_instance_id)
    import held_item_reactions as HELD_REACTIONS
    reaction_plan=HELD_REACTIONS.prepare_register(engine,c,canonical_id)
    for effect in effs:
        if (STATIC_EQUIPMENT.consumes_effect(static_plan,effect)
                or EQUIPMENT_VARIANTS.consumes_effect(variant_plan,effect)
                or OPTIONAL_EQUIPMENT.consumes_effect(optional_plan,effect)
                or FASHION.consumes_effect(fashion_plan,effect)
                or HELD_REACTIONS.consumes_effect(reaction_plan,effect)):continue
        if isinstance(effect,dict) and effect.get("type")=="grant_move":GRANTS.move_grants(engine.r,effect)
        if isinstance(effect,dict) and effect.get("type")=="grant_ability":GRANTS.ability_grant(engine.r,effect)
        if isinstance(effect,dict) and effect.get("type")=="grant_capability":GRANTS.capability_values(effect.get("capability"))
    reg = getattr(c, "_item_reg", {})
    is_held=projection is None and (c.kind=="pokemon" or as_held or held_slot is not None or any(x['name']==name for x in HELD.entries(c)))
    held=HELD.prepare(c,name,canonical_id,source_instance_id,held_slot) if is_held else None
    if held and held.get('registration_key') in reg:return 0
    if held and c.kind == "pokemon" and FASHIONISTA.chic(c) is not None:
        carried = FASHIONISTA.wardrobe_items(engine, c)
        if any(entry is held for entry in HELD.entries(c)):
            carried.remove(held.get('item_id') or engine.r.item_effects(held['name'])[1].get('id'))
        FASHIONISTA._wardrobe_constraints(engine, c, [*carried, canonical_id])
    duplicate=[r for r in reg.values() if r.get("item_id")==canonical_id]
    if duplicate and not is_held:return 0
    registration_key=projection['registration_key'] if projection is not None else name if name not in reg else "slot:"+held['slot_id']
    if projection is not None and registration_key in reg:raise ValueError("item projection registration key already in use")
    effects_pending=bool(duplicate and effs)
    if effects_pending:effs=[]  # Distinct physical copies are retained; no guessed stacking.
    slots = []
    if c.kind == "trainer" and not as_held and projection is None:
        options = item_slot_options(header, effs)
        if optional_plan and OPTIONAL_EQUIPMENT.slot_options(optional_plan):
            options = OPTIONAL_EQUIPMENT.slot_options(optional_plan)
        if canonical_id == "item/캡슐캐논":
            import net_capsule as NET
            options = NET.cannon_slots(engine)
        ignored_optional = OPTIONAL_EQUIPMENT.ignored_registration_keys(optional_plan)
        occupied = {slot for key, entry in reg.items() if key not in ignored_optional for slot in entry.get("slots", [])}
        occupied.update(slot for entry in c.custom_conditions.get("equipped_weapons",{}).values() for slot in entry.get("slots",[]))
        if options:
            slots = next((option for option in options if not occupied.intersection(option)), None)
            if slots is None:
                slots = FASHIONISTA.accessory_slot(engine, c, canonical_id, effs, options, occupied, reg)
            if slots is None:
                engine.log(f"  {c.name}: 장비 슬롯이 이미 사용 중 → {name} 등록 거부", "ch09/장비")
                return 0
    reg = c.__dict__.setdefault("_item_reg", {})
    if projection is not None:
        source_id = projection["source_id"]
        GRANTS._source(c, source_id, "item", owner_id=projection["owner_id"], lifetime=projection["lifetime"], rule_id=canonical_id, tutor_points=0,
                       instance_id=None, identity_evidence="feature_projection", projection={k:v for k,v in projection.items() if k!="source_id"})
    else:
        source_id = "equipment:" + (source_instance_id or str(c.spec.get("id", c.name)) + ":" + canonical_id + (":"+held["slot_id"] if held and registration_key!=name else ""))
        GRANTS._source(c, source_id, "item", owner_id=c.spec.get("id"), lifetime="equipped", rule_id=canonical_id, tutor_points=0,
                       instance_id=source_instance_id, identity_evidence="registered_instance" if source_instance_id else "legacy_actor_rule")
    effect_sources = []
    n = 0
    for index, raw in enumerate(effs):
        if not isinstance(raw, dict):
            continue
        if (STATIC_EQUIPMENT.consumes_effect(static_plan,raw)
                or EQUIPMENT_VARIANTS.consumes_effect(variant_plan,raw)
                or OPTIONAL_EQUIPMENT.consumes_effect(optional_plan,raw)
                or FASHION.consumes_effect(fashion_plan,raw)
                or HELD_REACTIONS.consumes_effect(reaction_plan,raw)):
            continue
        effect = normalize(raw)
        species_condition = re.fullmatch(r"species\s*==\s*(.+)", str(effect.get("if", "")))
        if species_condition:
            species = engine.r.species.get(c.spec.get("species"), {}).get("name", c.spec.get("species"))
            if c.kind != "pokemon" or species != species_condition.group(1).strip():
                continue
            effect.pop("if", None)
        kind = effect.get("type")
        if resolved_conditions is not None and isinstance(effect.get("if"), str) and effect["if"] in resolved_conditions:
            # A sourced producer resolved this printed condition; false skips the row without a prompt.
            if not resolved_conditions[effect["if"]]:
                continue
            effect = {k:v for k,v in effect.items() if k != "if"}
        unresolved = effect.get("move_type") == "chosen" or effect.get("_scope", {}).get("type") == "chosen" or (kind == "stage_change" and effect.get("stat") not in c.stages)
        if unresolved or (kind == "stage_change" and effect.get("base") and effect.get("if")):
            prompt = {"type":"gm","choice":f"{name}: 도구의 타입·스탯 선택 또는 조건 확인 후 적용: {raw}","effect_to_resolve":raw}
            EXT._prompt(engine,prompt,prompt["choice"],src=f"item/{name}",attacker=c,target=c)
            continue
        effect_source = source_id + ":" + str(index)
        effect_sources.append(effect_source)
        if kind == "grant_ability" and isinstance(effect.get("grant_ability"),str) and effect["grant_ability"] in engine.r.ability_effects:
            GRANTS.grant(c,"abilities",effect["grant_ability"],source_id,"item",owner_id=c.spec.get("id"),lifetime="equipped",rule_id=canonical_id)
            engine.register_abilities_one(c,effect["grant_ability"])
        elif kind == "grant_move":
            for mid in GRANTS.move_grants(engine.r,effect):GRANTS.grant(c,"moves",mid,source_id,"item",owner_id=c.spec.get("id"),lifetime="equipped",rule_id=canonical_id)
        elif kind == "grant_capability":
            for value in GRANTS.capability_values(effect.get("capability")):GRANTS.grant(c,"capabilities",value,source_id,"item",owner_id=c.spec.get("id"),lifetime="equipped",rule_id=canonical_id)
        elif kind == "immunity" and effect.get("status"):
            for value in effect["status"]:GRANTS.set_member(c,"status_immune",value,effect_source)
        elif kind == "weather_immunity":
            for value in re.split(r"[/,]",str(effect.get("weather"))):
                GRANTS.set_member(c,"weather_immune",value.strip(),effect_source)
        elif kind == "keyword_immunity":
            GRANTS.set_member(c,"keyword_immune",effect.get("keyword"),effect_source)
        elif kind == "move_immunity":
            for value in effect.get("moves",[]) if isinstance(effect.get("moves"),list) else []:
                GRANTS.set_member(c,"move_immune",value,effect_source)
        elif kind == "grounded":
            GRANTS.scalar(c,"grounded",1,effect_source)
        elif kind == "stage_change" and effect.get("base") and isinstance(effect.get("delta"),int):
            import combat_stage_sources as STAGE_SOURCES
            STAGE_SOURCES.add_base(c,effect_source,effect["stat"],effect["delta"],source=canonical_id,ends=effect_source)
            GRANTS.state(c)["effects"][effect_source]={"rows":[],"listeners":[],"stages":True}
        elif kind == "initiative_mod":
            GRANTS.numeric(c,"initiative_bonus",int(effect["value"]),effect_source)
        elif kind == "save_mod" and isinstance(effect.get("value"),int) and not effect.get("once"):
            GRANTS.numeric(c,"save_mod",effect["value"],effect_source)
        elif kind == "speed_mod" and isinstance(effect.get("value"),int) and effect.get("movement") in (None,"land"):
            GRANTS.numeric(c,"movement",effect["value"],effect_source)
        elif kind == "immunity" and effect.get("to") or kind == "crit_range" or kind == "damage_reduction" and effect.get("_scope"):
            GRANTS.apply_owned(engine,c,effect_source,lambda effect=effect:c.modifiers.append(dict(effect,_item=name)))
        elif kind in FX.PASSIVE_TYPES:
            owned=dict(effect,_ability=name)
            GRANTS.apply_owned(engine,c,effect_source,lambda owned=owned:FX.apply_passives(engine,c,[owned]),effects=[owned])
        elif kind == "gm":
            EXT._prompt(engine,effect,str(effect.get("choice") or effect.get("note") or "도구 판정 필요"),src=f"item/{name}",attacker=c,target=c)
        elif kind in ("rule","tag","restriction","trainer_slot","craft","weapon","vehicle","z_crystal","mega_stone","evolution_item","contest_dice","reroll","frequency_rule","limit"):
            continue
        else:
            GRANTS.apply_owned(engine,c,effect_source,lambda effect=effect:c.registry.append(dict(effect,_item=name)))
        n += 1
    static_sources,static_count=STATIC_EQUIPMENT.install(engine,c,source_id,static_plan)
    effect_sources.extend(static_sources)
    n+=static_count
    variant_sources,variant_count=EQUIPMENT_VARIANTS.install(engine,c,source_id,variant_plan)
    effect_sources.extend(variant_sources)
    n+=variant_count
    optional_sources,optional_count=OPTIONAL_EQUIPMENT.install(engine,c,source_id,optional_plan)
    effect_sources.extend(optional_sources)
    n+=optional_count
    fashion_sources,fashion_count=FASHION.install(engine,c,source_id,fashion_plan)
    effect_sources.extend(fashion_sources)
    n+=fashion_count
    GRANTS.state(c)["sources"][source_id]["effect_sources"]=effect_sources
    if source_instance_id is not None:
        import world_entities as WORLD
        instance["equipped_by"]=c.entity_id
        WORLD._set_object_location(instance,{"kind":"unknown"})
    reg[registration_key]={"name":name,"item_id":canonical_id,"instance_id":source_instance_id,"slots":slots,"state_source":source_id,"effect_sources":effect_sources,
               "stages":{},"abilities":[],"moves":[],"held_slot":held['slot_id'] if held else None}
    if projection is not None:reg[registration_key]["projection"]=deepcopy(projection)
    EQUIPMENT_VARIANTS.bind_registration(engine,c,reg[registration_key],variant_plan)
    OPTIONAL_EQUIPMENT.bind_registration(engine,c,reg[registration_key],optional_plan)
    if held:
        HELD.commit(c,held,item_id=canonical_id,instance_id=source_instance_id,registration_key=registration_key,effects_pending=effects_pending)
        import item_maturation as MATURATION
        MATURATION.on_held(engine,c,held)
        FASHIONISTA.reconcile_incense(engine,c)
    engine.log(f"  {c.name} 도구 {name}: 효과 {n}개 등록 ({header.get('category')})",f"item/{name}")
    if source_instance_id is not None:
        import crafting_products as PRODUCTS
        PRODUCTS.register(engine,c,instance)
    synchronize_field_suppression(engine, (c,))
    if canonical_id == 'item/만능우산':
        import ability_state_projection as PROJECTION
        PROJECTION.weather_changed(engine)
    return n


def _passive_registration(engine, actor, record):
    """Classify only registrations whose static/triggered benefit is suppressible.

    Consumables and explicit Fashion activations keep their source registration;
    Magic Room does not prevent consuming or actively turning on an item.
    """
    item_id = record.get("item_id")
    import fashion_items as FASHION
    if FASHION.definition(engine.r, item_id) is not None:
        return False
    effects, header = engine.r.item_effects(item_id)
    if header.get("use") == "consumable" or header.get("category") in ("약", "음식"):
        return False
    return True


def synchronize_field_suppression(engine, actors=None):
    """Compatibility entry for the existing field producers."""
    return synchronize_equipment_suppression(engine,actors)


def equipment_benefit_active(actor,record):
    import equipment_suppression as SUPPRESSION
    return SUPPRESSION.benefit_active(actor,record)


def synchronize_equipment_suppression(engine, actors=None):
    """Reconcile authenticated source reasons without moving equipment or stock."""
    if getattr(engine,'_equipment_suppression_reconciling',False):return True
    if actors is None:
        actors = engine.time_actors()
    actors = tuple(dict.fromkeys(actors))
    import equipment_suppression as SUPPRESSION
    engine._equipment_suppression_reconciling=True
    try:
        for actor in actors:
            reg = getattr(actor, "_item_reg", {})
            for key, record in list(reg.items()):
                reasons=SUPPRESSION.reasons(engine,actor,key,record)
                suspended=SUPPRESSION.KEY in record or MAGIC_ROOM_KEY in record
                if reasons:
                    source=record.get('state_source')
                    if not suspended:
                        if not isinstance(source,str) or source not in actor.spec.get(GRANTS.KEY,{}).get('sources',{}):
                            raise ValueError('equipment suspension requires its live source')
                        GRANTS.preflight_revoke(actor,source)
                    record[SUPPRESSION.KEY]={'reasons':reasons}
                    field=next((r for r in reasons if r['kind']=='field'),None)
                    if field:record[MAGIC_ROOM_KEY]={'field_source':field['source'],'registration_key':key}
                    else:record.pop(MAGIC_ROOM_KEY,None)
                    if not suspended:
                        import crafting_products as PRODUCTS
                        PRODUCTS.unregister(engine,actor,getattr(engine,'_physical_objects',{}).get(record.get('instance_id')))
                        GRANTS.revoke(actor,source,engine=engine)
                elif suspended:
                    saved=dict(record);reg.pop(key)
                    register_item(engine,actor,saved['name'],source_instance_id=saved.get('instance_id'),
                                  as_held=saved.get('held_slot') is not None,held_slot=saved.get('held_slot'))
    finally:
        del engine._equipment_suppression_reconciling
    return True


def unregister_item(engine,c,item_name=None,*,registration_key=None,maturation_release=True,wardrobe=False):
    """Remove this source, retaining all independent and overlapping grants.

    wardrobe: a Chic Pokemon moving its active held item into its wardrobe keeps
    Mega Evolution with the Stone stored (ch04:2031-2033), so the Mega lock is waived.
    """
    name=item_name if item_name is not None else HELD.single(c) if registration_key is None else None
    reg=getattr(c,"_item_reg",{})
    if registration_key is not None:key=registration_key
    else:
        canonical=engine.r.item_effects(name)[1].get('id') if name else None
        matches=[k for k,row in reg.items() if k==name or row.get('name')==name or canonical and row.get('item_id')==canonical]
        if len(matches)>1:raise ValueError('item name identifies multiple instances; explicit registration required')
        key=matches[0] if matches else name
    record=reg.get(key)
    if not record:return 0
    import mega_forms as MEGA
    if wardrobe is not True and MEGA.locked(engine,c,instance_id=record.get("instance_id"),registration_key=key):
        raise ValueError("active Mega Stone cannot be removed")
    if wardrobe is True and (c.kind!="pokemon" or c.spec.get("fashionista_chic") is None):raise ValueError("wardrobe removal requires an actual Chic Pokemon")
    if "state_source" not in record:
        raise ValueError("legacy equipped-effect receipt needs explicit source import before removal")
    GRANTS.preflight_revoke(c,record["state_source"])
    import equipment_variant_contracts as EQUIPMENT_VARIANTS
    import optional_physical_equipment as OPTIONAL_EQUIPMENT
    OPTIONAL_EQUIPMENT.uninstall(engine,c,record)
    EQUIPMENT_VARIANTS.uninstall(engine,c,record)
    import crafting_products as PRODUCTS
    PRODUCTS.unregister(engine,c,getattr(engine,"_physical_objects",{}).get(record.get("instance_id")))
    GRANTS.revoke(c,record["state_source"],engine=engine)
    reg.pop(key,None)
    name=record.get('name',name or key)
    selected=next((x for x in HELD.entries(c) if x.get('registration_key')==key),None)
    if selected:
        if maturation_release:
            import item_maturation as MATURATION
            MATURATION.on_release(engine,c,record.get('instance_id'))
        HELD.remove(c,selected['slot_id'])
    instance=getattr(engine,"_physical_objects",{}).get(record.get("instance_id"))
    if instance is not None and instance.get("equipped_by")==c.entity_id:
        instance.pop("equipped_by",None)
    import legendary_commands as LEGENDARY
    LEGENDARY.boundary(engine,'equipment_removed')
    if selected:
        import fashionista as FASHIONISTA
        FASHIONISTA.reconcile_incense(engine,c)
    engine.log(f"  {c.name} 도구 {name}: 효과 해제",f"item/{name}")
    if record.get('item_id') == 'item/만능우산':
        import ability_state_projection as PROJECTION
        PROJECTION.weather_changed(engine)
    return 1


def transfer_item(engine, loser, gainer, item_name=None, log=""):
    """도구 이동(교환·훔치기·건네기·떨굼): 잃는 쪽 해제 → 얻는 쪽 등록. gainer 가 None 이면 떨어뜨림."""
    name = item_name or (loser.item if loser is not None else None)
    if loser is not None and name:
        unregister_item(engine, loser, name)
    if gainer is not None and name and gainer.item == name:
        register_item(engine, gainer, name)


def item_damage_reduction(target, move, *, engine=None):
    """타입·물리/특수·원거리 한정 피해 감소(깁스·방화복·마찰저하복…)의 합."""
    total = 0
    for e in target.modifiers:
        if engine is not None and not passive_effect_allowed(engine,target,e):
            continue
        if e.get("type") != "damage_reduction" or not e.get("_scope") or not isinstance(e.get("value"), int):
            continue
        sc = e["_scope"]
        if sc.get("type") and sc["type"] != move["type"]:
            continue
        if sc.get("class") == "물리" and move["class"] != "물리":
            continue
        if sc.get("class") == "특수" and move["class"] != "특수":
            continue
        if sc.get("class") == "원거리" and "근접" in str(move.get("range", "")):
            continue
        total += e["value"]
    import equipment_variant_contracts as EQUIPMENT_VARIANTS
    return total + EQUIPMENT_VARIANTS.damage_reduction(target,move)


def crit_delta(c, move, *, engine=None):
    import restorative_items as RESTORATIVE
    return RESTORATIVE.crit_delta(c) + sum(e.get("delta", 0) for e in c.modifiers if (engine is None or passive_effect_allowed(engine,c,e)) and e.get("type") == "crit_range" and "delta" in e and (e.get("moves") in ("all", None) or "damaging" in str(e.get("moves"))))


def passive_effect_allowed(engine, actor, effect):
    source = effect.get(GRANTS.TAG) if isinstance(effect, dict) else None
    if source is None:
        return True
    for record in getattr(actor, "_item_reg", {}).values():
        if source == record.get("state_source") or source in record.get("effect_sources", ()):
            return equipment_benefit_active(actor,record)
    return True


# ---------- 소모 아이템 ----------
def use_item(engine, user, item_name, target=None, free=False, accepted=True, *, duration_minutes=None, duration_reason=None, count=1, food_policy=None, selected_move=None, selected_stat=None, owner_consent_by=None, held_selection=None, container_selection=None, shell_batch_id=None, fixed_accuracy=None, resumable=False, request_id=None, aim=None, medicine_source_choice=None):
    """약·음식·열매·영양제를 대상에게 사용. 기본 행동(free=False 면 행동 예산 소비). 반환 (실행 수, 보류 수) 또는 None(DB 없음)."""
    import consumable_use as USE
    return USE.dispatch(engine,user,item_name,target,free=free,accepted=accepted,
        duration_minutes=duration_minutes,duration_reason=duration_reason,count=count,
        food_policy=food_policy,selected_move=selected_move,selected_stat=selected_stat,owner_consent_by=owner_consent_by,held_selection=held_selection, container_selection=container_selection, shell_batch_id=shell_batch_id, fixed_accuracy=fixed_accuracy,resumable=resumable,request_id=request_id,aim=aim,medicine_source_choice=medicine_source_choice)


def _use_immediate_item(engine,user,item_name,target,*,free=False,accepted=True,
                        duration_minutes=None,duration_reason=None,count=1,held_selection=None,medicine_source_choice=None):
    """Immediate source adapter; public use/selection belongs to consumable_use."""
    import food_effects as FOOD,turn as TURN
    effs,header=engine.r.item_effects(item_name)
    if any(isinstance(x,dict) and x.get('type')=='stat_base_mod' and x.get('vitamin') for x in effs or []):
        raise ValueError('Vitamin effects require the sourced Vitamin use adapter')
    import lifetime_consumables as LIFETIME
    if header.get('id') in LIFETIME.ITEMS:raise ValueError('lifetime growth requires its sourced consumption adapter')
    herbal = header.get('id') in FOOD.HERBS
    if herbal:
        FOOD.herbal_preflight(engine,target,header['id'])
        if held_selection is None and not isinstance(user.spec.get('items'),dict):raise ValueError('actual herbal medicine inventory required')
        if header['id']=='item/만능가루':effs=[{'type':'cure_status','status':'persistent all','target':'target'}]
    if duration_minutes is not None or duration_reason is not None or count!=1:
        raise ValueError('duration/count options require an Extended bandage or food item')
    if effs is None:
        engine.log(f"  {user.name}: 도구 {item_name} 은(는) DB 에 없음", "item/unknown")
        return None
    import item_stock as STOCK
    stock=STOCK.prepare(engine,user,header['id'],held_selection=held_selection,allow_empty=True)
    if stock is None:
        engine.log(f"    {user.name}: {item_name} 재고 없음",f"item/{item_name}")
        return (0,0)
    import restorative_items as RESTORATIVE
    is_x = header.get('id') in RESTORATIVE.X_ITEMS
    is_restorative = header.get("category") == "약" and not is_x and not any(isinstance(e, dict) and e.get("type") == "stat_base_mod" and e.get("vitamin") for e in effs)
    if is_x and target.kind != "pokemon":
        engine.log(f"  {user.name}: X 도구 {item_name} 은(는) 포켓몬에게만 작용 → {target.name}에게 효과 없음 (미사용)", "ch09/X-도구")
        return (0, 0)
    if is_x or is_restorative:
        pending=RESTORATIVE.preflight(engine,target,header['id'])
        if pending is not None:return pending
    medic = RESTORATIVE.medic(engine,user,target) if (is_x or is_restorative) else False
    import action_lifecycle as ACTION
    import native_rule_policy as POLICY
    policy = POLICY.evaluate(engine.r,'medicine',dict(self_use=target is user,restorative=is_restorative,medic=medic),medicine_source_choice=medicine_source_choice) if (is_restorative or is_x) else None
    import action_resources as RESOURCES
    recipient_debt = policy['values']['debt'] if policy and engine.encounter_active else None
    if recipient_debt is not None:RESOURCES.plan_debt(target,recipient_debt)
    kind = "free" if free else policy['values']['action'] if policy else "standard"
    if free and engine.encounter_active:
        engine.log("    [보류] 아이템 비용 면제만으로 실행 권한을 확정할 수 없음", "common/action-lifecycle")
        return (0, 1)
    sleep_cure = ACTION.self_cures_sleep(user, target, effs)
    if engine.encounter_active and (user.injuries>=5 and not __import__('taskmaster').ignores_acting_loss(user)) and kind in ('standard','full'):
        raise ValueError('medicine Standard/Full requires reviewed heavy-injury action composition')
    # Deterministic state/source checks precede payment. A later observed
    # event is not undone by a blanket transaction rollback.
    FX.preflight_effects(engine,user,target,effs,header['id'],consumer='items.use_item')
    def pay(e,c):
        if not TURN.spend(e,c,kind,item_name,sleep_cure=sleep_cure):return False
        receipt=STOCK.debit(e,c,stock)
        if policy:
            receipt['medicine_policy']={'source_variant':policy['source_variant'],'source_policy':deepcopy(policy['source_policy']),
                'values':deepcopy(policy['values']),'encounter_active':e.encounter_active}
        return True
    # Stage only payment and physical membership, before any healing/cure event.
    # Effects below retain their ordinary observed-event behavior.
    paid = GRANTS.transition(engine,user,pay) if held_selection is not None else pay(engine,user)
    if not paid:return (0,0)
    engine.log(f"  {user.name}이(가) {target.name}에게 {item_name} 사용 ({header.get('category')})", f"item/{item_name}")
    if engine.encounter_active and policy and not (is_restorative and target is user):
        if policy['values']['debt'] is None:
            engine.log(f"    메딕 훈련: {target.name}은(는) 행동을 잃지 않음", "edge/메딕-훈련")
        else:
            RESOURCES.schedule(target,recipient_debt)
            lost='신속' if 'swift' in recipient_debt else '이동'
            engine.log(f"    {target.name}은(는) 다음 기본 행동과 {lost} 행동을 잃음 (아이템 사용)", "ch09/아이템-사용")
    if is_x and RESTORATIVE.special_apply(engine,target,header['id']):return (1,0)
    ctx = {"attacker": user, "target": target, "hit": True, "nat": None, "engine": engine, "who": target}
    run = []
    native_done = 0
    for raw in effs:
        if not isinstance(raw, dict):
            continue
        e = dict(raw)
        t = e.get("type")
        if t == "gm":
            run.append(e)  # Preserve actionable GM prompts for consumable items too.
            continue
        if t in ("tag", "restriction", "rule", "limit", "trainer_slot"):
            if t == "rule":
                engine.log(f"    [GM 판단] {item_name}: {e.get('note') or e.get('choice')}", f"item/{item_name}")
            continue
        if t == "heal" and "amount" not in e and "value" in e:
            e["amount"] = e.pop("value")
        if t == "revive":
            if not target.fainted:
                engine.log(f"    {target.name}은(는) 기절 상태가 아님 → 효과 없음", f"item/{item_name}")
                continue
            hp = e.get("hp", 1)
            v = M.ratio(target.base_max_hp,2) if hp == "max_hp/2" else int(hp) if isinstance(hp, int) else M.ratio(target.base_max_hp,2)
            if not engine.revive(target,max(1,v)):
                engine.log(f"    {target.name}: 소생 불가", f"item/{item_name}")
                continue
            engine.log(f"    {target.name} 소생 → 체력 {target.hp}", f"item/{item_name}")
            native_done += 1
            continue
        if t == "exp_gain":
            import downtime as DT
            DT.gain_exp_combatant(engine, target, e.get("value"))
            native_done += 1
            continue
        if t == "stage_reset":
            for s, v in list(target.stages.items()):
                if v < 0:
                    target.stages[s] = 0
            engine.log(f"    {target.name} 하락한 전투단계 초기화", f"item/{item_name}")
            native_done += 1
            continue
        if t == "cure_status" and isinstance(e.get("status"), str) and e["status"] in ("persistent all", "volatile all", "any one", "all"):
            cls = "persistent" if "persistent" in e["status"] else "volatile" if "volatile" in e["status"] else None
            cured = []
            import status_sets as STATUS_SETS
            for cond in STATUS_SETS.afflictions(target):
                if cls is None or engine.r.condition_class(cond) == cls:
                    engine.cure_status(target, cond)
                    cured.append(cond)
                    if e["status"] == "any one":
                        break
            if not cured:
                engine.log(f"    치료할 상태 없음", f"item/{item_name}")
            native_done += 1
            continue
        e.setdefault("target", "target")
        run.append(e)
    done, held = FX.run_effects(engine, user, target, run, ctx, f"item/{item_name}") if run else (0, 0)
    if herbal:FOOD.herbal_consumed(engine,target,header['id'])
    return done + native_done, held


# ---------- 몬스터볼 ----------
BALL_RULES = {   # 설명문 조건 → (보정치, 조건 함수). 에라타 환산(1d20 기준) 값이다. 설명문의 '+4' 는 1d20 기준으로 읽는다.
    "몬스터볼": (0, None), "슈퍼볼": (2, None), "하이퍼볼": (3, None), "마스터볼": (20, None), "사파리볼": (0, None), "컴퍼티션볼": (0, None), "파크볼": (3, None), "프리미어볼": (0, None), "프레셔스볼": (1, None),
    "레벨볼": (4, lambda e, tr, t: any(p.level >= 2 * t.level for p in getattr(tr, "party_pokemon", []))), "루어볼": (4, lambda e, tr, t: bool(t.spec.get("fishing"))),
    "문볼": (4, lambda e, tr, t: bool(t.spec.get("stone_evolver"))), "프렌드볼": (1, None), "러브러브볼": (6, lambda e, tr, t: bool(t.spec.get("same_line_other_gender"))),
    "헤비볼": (lambda e, tr, t: max(0, t.weight_class - 1), None), "스피드볼": (4, lambda e, tr, t: max((t.spec.get("movement") or {}).values(), default=0) >= 7),
    "리피트볼": (4, lambda e, tr, t: t.spec.get("species") in set(tr.spec.get("caught_species", []))), "타이머볼": (lambda e, tr, t: min(4, max(0, e.round_no - 1) - 1), None),
    "네스트볼": (4, lambda e, tr, t: t.level <= 10), "네트볼": (4, lambda e, tr, t: bool({"물", "벌레"} & set(t.types))), "다이브볼": (4, lambda e, tr, t: bool(t.spec.get("from_water_or_underground"))),
    "럭셔리볼": (1, None), "힐볼": (1, None), "퀵볼": (lambda e, tr, t: {0: 4, 1: 4, 2: 3, 3: 2}.get(e.round_no, 0), None), "다크볼": (4, lambda e, tr, t: bool(getattr(e, "dark", False))),
    "파워볼": (4, lambda e, tr, t: t.level <= 10), "어스볼": (4, lambda e, tr, t: bool({"풀", "땅"} & set(t.types))), "혼팅볼": (4, lambda e, tr, t: bool({"악", "고스트"} & set(t.types))),
    "솔리드볼": (4, lambda e, tr, t: bool({"바위", "강철"} & set(t.types))), "히트볼": (4, lambda e, tr, t: bool({"불꽃", "전기"} & set(t.types))), "미스틱볼": (4, lambda e, tr, t: bool({"드래곤", "에스퍼"} & set(t.types))),
    "에어볼": (4, lambda e, tr, t: bool({"얼음", "비행"} & set(t.types))), "몰드볼": (4, lambda e, tr, t: bool({"독", "격투"} & set(t.types))), "가서머볼": (4, lambda e, tr, t: bool({"노말", "페어리"} & set(t.types))),
    "썬-볼": (4, lambda e, tr, t: FX.weather_matches(e,"sunny",t)), "레인-볼": (4, lambda e, tr, t: FX.weather_matches(e,"rain",t)), "헤일-볼": (4, lambda e, tr, t: FX.weather_matches(e,"hail",t)), "샌드볼": (4, lambda e, tr, t: FX.weather_matches(e,"sandstorm",t)),
    "울트라볼": (lambda e, tr, t: 0 if CLASSIFICATION.ultra_beast(e, t) else -4, None),
}
BALL_AFTER = {"힐볼": "full_heal", "프렌드볼": "loyalty+1", "럭셔리볼": "loyalty_high", "파워볼": "level+1d4", "런닝-볼": "learn_next_move"}



BALL_ALIASES = {"poke_ball": "몬스터볼"}


def ball_name(name):
    key=name.removeprefix('item/')
    return BALL_ALIASES.get(key,key)


def ball_inventory_key(actor, name='몬스터볼'):
    """Resolve a possessed ball without consuming or destroying the thrown object."""
    import common_checks as C
    canonical=ball_name(name)
    inventory=actor.spec.get('items',{})
    if not isinstance(inventory,dict):raise ValueError('actual ball inventory mapping required')
    keys=list(dict.fromkeys((name,canonical,'item/'+canonical,*[key for key,value in BALL_ALIASES.items() if value==canonical])))
    for key in keys:
        if key in inventory:
            count=C.integer(inventory[key],'actual owned ball count',0)
            if count:return key
    return None


def ball_modifier(engine, ball, trainer, target):
    """(보정치, 설명). DB(items-mech capture_mod)를 기본으로 쓰되 조건부 볼은 BALL_RULES 로 판정한다."""
    if engine.r.mech("pokemon/capture-rate").get("_version") is not None:
        raise ValueError("this ball modifier reader supports the selected d20 capture revision only")
    key = ball.replace("item/", "")
    rule = BALL_RULES.get(key)
    if rule is None:
        effs, _ = engine.r.item_effects(key)
        v = next((e.get("value", 0) for e in (effs or []) if isinstance(e, dict) and e.get("type") == "capture_mod"), 0)
        return (int(v) if isinstance(v, int) else 0), f"{key} (DB 보정 {v:+})" if isinstance(v, int) else f"{key} (보정 없음)"
    val, cond = rule
    v = val(engine, trainer, target) if callable(val) else val
    if cond is not None and not cond(engine, trainer, target):
        return 0, f"{key} 조건 불충족 → +0"
    return v, f"{key} {v:+d}"


def ball_catalog(rules):
    """DB 의 몬스터볼 목록: 이름·가격·보정 규칙(있으면)·포획 후 효과."""
    out = []
    for k, v in rules.items_mech.items():
        if k.startswith("$") or v.get("header", {}).get("category") != "몬스터볼":
            continue
        name = k.replace("item/", "")
        rule = BALL_RULES.get(name)
        out.append({"id": k, "name": name, "price": v["header"].get("price"), "modifier": (rule[0] if rule and not callable(rule[0]) else "조건/라운드" if rule else None),
                    "conditional": bool(rule and rule[1]), "after_capture": BALL_AFTER.get(name), "desc": v.get("desc", "")[:80]})
    return out


# ---------- 재주 · 엣지 ----------
TRAINER_SKIP = {"rule", "gm", "craft", "limit", "cost", "tag", "frequency_rule", "skill_rank_up", "contest_dice", "exp_gain", "restriction"}


def _feature_rows(effects):
    trigger = next((e for e in effects if isinstance(e, dict) and e.get("type") == "trigger"), None)
    manual = [normalize(e) for e in effects if isinstance(e, dict) and e.get("type") != "trigger"]
    rest = [normalize(e) for e in effects if isinstance(e, dict) and e.get("type") not in TRAINER_SKIP and e.get("type") != "trigger"]
    return trigger, manual, rest


def _static_feature(header, manual, action):
    amount, problem = AP.quote(header, manual)
    is_edge = header.get("id", "").split("/", 1)[0] in ("edge", "poke_edge")
    return not amount and not problem and (is_edge or action == "static")


def _generic_feature_reserved(engine, owner, name):
    """Pure routing query; never run acquisition adapters to discover ownership."""
    if name in __import__('warper').FEATURES and __import__('warper').acquired(owner,name):return True
    if name in __import__('telepath').FEATURES and __import__('telepath').acquired(owner,name):return True
    if name in __import__('telekinetic').FEATURES and __import__('telekinetic').acquired(owner,name):return True
    import iron_mind as IRON
    if name in IRON.NAMES and IRON.validate(owner):return True
    import native_switch_transfer as SWITCH
    if SWITCH.identity(name) is not None:return True
    import directive_features as DIRECTIVES, class_move_grants as CLASS_MOVES
    import acquired_feature_projections as ACQUIRED, feature_ability_grants as ABILITIES
    import scene_feature_ability_grants as SCENE, feature_ability_lessons as LESSONS
    import static_feature_state_grants as STATIC, class_passive_combat as CLASS_PASSIVE
    if (DIRECTIVES.identity(name) is not None or CLASS_PASSIVE.identity(name) is not None
            or any(module.identity(engine.r, name) is not None
                   for module in (CLASS_MOVES, ACQUIRED, ABILITIES, SCENE, LESSONS, STATIC))):
        return True
    # A receipted Type Ace acquisition is owned by type_ace's native adapters; the
    # generic projection would otherwise duplicate e.g. Polished Shine after restore.
    import rogue as ROGUE
    if name in ROGUE.FEATURES and ROGUE.acquired(owner,name) is not None:return True
    import provocateur as PROVOCATEUR
    if name in PROVOCATEUR.FEATURES and PROVOCATEUR.acquired(owner,name) is not None:return True
    import type_ace as TA
    if name in TA.FEATURES and TA.acquired(owner, name) is not None:
        return True
    import vitamin_capacity as VITAMINS, move_state as MOVES, training_features as TRAINING
    import combat_precision_features as PRECISION, intercept_profiles as INTERCEPT
    import enduring_awareness as AWARENESS, combat_social_edges as SOCIAL
    import maneuver_edges as MANEUVERS, elemental_connection as ELEMENTAL
    import skill_modifiers as SKILLS
    return (name in VITAMINS.ALIASES
            or MOVES.SLOT_POLICIES.get(MOVES._feature_id(owner, name)) in (MOVES.GUIDANCE, MOVES.LIFELONG)
            or any(module.identity(name) is not None for module in (TRAINING, PRECISION, INTERCEPT, SOCIAL))
            or AWARENESS._is(name, AWARENESS.AWARENESS, AWARENESS.AWARENESS_ALIASES)
            or any(SKILLS.key(name) in {SKILLS.key(x) for x in (uid, *aliases)}
                   for uid, aliases, skill in MANEUVERS.POLICIES.values())
            or any(ELEMENTAL.matches(name, source) for source in ELEMENTAL.ALIASES))


def _register_feature_effect(engine, owner, target, name, header, index, effect):
    return GRANTS.register_feature_effect(engine, owner, target, name,
        header.get("id", name), index, dict(effect, target="self", _ability=name))


def project_owned_pokemon_features(engine, owner, targets):
    """Project generic continuous Static exact-your-Pokemon rows only.

    Requires actual registered owner/targets and existing acquisition. Dedicated,
    triggered, paid, GM, duration/while and permanent move/ability grants retain
    their own producers. This API neither acquires nor activates any feature.
    """
    import world_entities as WORLD
    actual = WORLD.actor_index(engine)
    if owner.kind != "trainer" or actual.get(owner.entity_id) is not owner:
        raise ValueError("owned feature projection requires actual registered trainer")
    targets = tuple(targets)
    if len({id(target) for target in targets}) != len(targets) or any(
            actual.get(getattr(target, "entity_id", None)) is not target
            or target.kind != "pokemon" or target.spec.get("trainer_id") != owner.entity_id
            for target in targets):
        raise ValueError("owned feature projection requires distinct actual owned Pokemon")
    count = 0
    for name in list(owner.spec.get("feats", [])) + list(owner.spec.get("edges", [])):
        if _generic_feature_reserved(engine, owner, name):
            continue
        effects, header = engine.r.feat_effects(name)
        if effects is None:
            continue
        trigger, manual, rest = _feature_rows(effects)
        is_edge = header.get("id", "").split("/", 1)[0] in ("edge", "poke_edge")
        action, problem = ACTION_META.resolve_feature_action(header) if not is_edge else (None, "")
        if trigger is not None or any(e.get("type") == "gm" for e in manual) or problem or not _static_feature(header, manual, action):
            continue
        for index, effect in enumerate(rest):
            if (effect.get("target") != "your pokemon" or effect.get("type") in ("grant_move", "grant_ability")
                    or effect.get("duration") or effect.get("while")):
                continue
            for target in targets:
                count += bool(_register_feature_effect(engine, owner, target, name, header, index, effect))
    return count


def register_feats(engine, c, pokemon=None):
    """트레이너 spec['feats'] / spec['edges'] 의 mech 를 등록. 상시(항상) 수정치는 패시브, 발동조건은 트리거, 대상이 자기 포켓몬이면 pokemon 목록 각각에."""
    import intercept_profiles as INTERCEPT_PROFILES
    INTERCEPT_PROFILES.preflight_owned(engine,c)
    import static_feature_state_grants as STATIC_FEATURES
    # Validate the complete table-owned declaration before any older adapter
    # can mutate this actor.  This keeps a missing/invalid stat or branch
    # selection failure atomic across the existing registration pipeline.
    STATIC_FEATURES.plan(c)
    import acquired_features as ACQUIRED
    ACQUIRED.validate_class_slots(c)
    import directive_features as DIRECTIVES
    for directive_name in c.spec.get("feats", []):
        if DIRECTIVES.identity(directive_name) is not None:
            DIRECTIVES.register_owned(engine, c, directive_name)
    import vitamin_capacity as VITAMIN_CAPACITY
    VITAMIN_CAPACITY.sync_source_end(engine,c)
    import elemental_connection as ELEMENTAL
    ELEMENTAL.choices(engine,c)
    import class_move_grants as CLASS_MOVES
    CLASS_MOVES.register_all(engine,c)
    import acquired_feature_projections as ACQUIRED_PROJECTIONS
    acquired_projection_count=ACQUIRED_PROJECTIONS.register_all(engine,c)
    import feature_ability_grants as FEATURE_ABILITIES
    feature_ability_count=FEATURE_ABILITIES.register_all(engine,c)
    import scene_feature_ability_grants as SCENE_FEATURE_ABILITIES
    scene_ability_count=SCENE_FEATURE_ABILITIES.reconcile_owner(engine,c)
    import feature_ability_lessons as ABILITY_LESSONS
    import static_trainer_modifiers as STATIC_MODIFIERS
    static_modifier_count=STATIC_MODIFIERS.register_all(engine,c,pokemon)
    static_feature_count=STATIC_FEATURES.register_all(engine,c)
    names = list(c.spec.get("feats", [])) + list(c.spec.get("edges", []))
    slot_targets = pokemon
    pokemon = pokemon or [p for p in (engine.everyone or []) if p is not c and p.kind == "pokemon" and p.spec.get("trainer") == c.name]
    total = acquired_projection_count + feature_ability_count + scene_ability_count + static_modifier_count + static_feature_count
    for name in names:
        if name in {*__import__('commander').FEATURES,*__import__('commander').BUNDLES,*__import__('commander_orders').FEATURES}:continue
        import oracle as ORACLE
        if name in ORACLE.FEATURES and ORACLE.acquired(c,name):continue
        import native_switch_transfer as SWITCH
        if SWITCH.identity(name) is not None:continue
        if DIRECTIVES.identity(name) is not None:continue
        if (CLASS_MOVES.identity(engine.r,name) is not None
                or ACQUIRED_PROJECTIONS.identity(engine.r,name) is not None
                or FEATURE_ABILITIES.identity(engine.r,name) is not None
                or SCENE_FEATURE_ABILITIES.identity(engine.r,name) is not None
                or ABILITY_LESSONS.identity(engine.r,name) is not None
                or STATIC_FEATURES.identity(engine.r,name) is not None):continue
        import vitamin_capacity as VITAMIN_CAPACITY
        if VITAMIN_CAPACITY.register(engine,c,name,slot_targets):continue
        import move_state as MOVES_STATE
        if MOVES_STATE.register_passive_feature(engine,c,name,slot_targets):continue
        import training_features as TRAINING
        if TRAINING.register_owned(engine,c,name):continue
        import combat_precision_features as CPF
        if CPF.register_owned(engine,c,name):continue
        if INTERCEPT_PROFILES.register_owned(engine,c,name):continue
        import enduring_awareness as AWARENESS
        if AWARENESS.register_owned(engine,c,name):continue
        import combat_social_edges as SOCIAL
        if SOCIAL.register_owned(engine,c,name):continue
        import maneuver_edges as MANEUVER_EDGES
        if MANEUVER_EDGES.register_owned(engine,c,name):continue
        if ELEMENTAL.register_owned(engine,c,name):continue
        if _generic_feature_reserved(engine,c,name):continue
        effs, header = engine.r.feat_effects(name)
        if effs is None:
            engine.log(f"  {c.name} 재주 {name}: DB 에 없음", "feat/unknown")
            continue
        def register_row(field,value):
            source="feature:"+str(c.spec.get("id",c.name))+":"+header.get("id",name)
            row=GRANTS._source(c,source,"feature",owner_id=c.spec.get("id"),lifetime="while_owned",rule_id=header.get("id",name),tutor_points=0)
            part=source+":registration:"+field
            changed=GRANTS.register_definition_row(engine,c,part,field,value)
            parts=row.setdefault("effect_sources",[])
            if part not in parts:parts.append(part)
            return changed
        freq = (header.get("frequency") or {}).get("raw") if isinstance(header.get("frequency"), dict) else header.get("frequency")
        trig, manual_effects, rest = _feature_rows(effs)
        if any(e.get("type") == "gm" for e in manual_effects):
            register_row("registry",{"type": "feat_manual", "name": name, "trigger": (trig or {}).get("text") or freq,
                               "effects": manual_effects, "frequency": header.get("frequency"), "usage_key": header.get("id", name), "activation_header": header, "cost_effects": manual_effects})
            engine.log(f"    재주 {name}: 선택/원문 확인 필요 → GM 수동 발동", f"feat/{name}")
            continue
        n = 0
        # Edge acquisition remains its existing separate path. Feature action
        # metadata does not establish a universal Static default for edges.
        is_edge = header.get("id", "").split("/", 1)[0] in ("edge", "poke_edge")
        action, action_problem = ACTION_META.resolve_feature_action(header) if not is_edge else (None, "")
        if not is_edge and action_problem:
            register_row("registry",{"type": "feat_manual", "name": name, "trigger": (trig or {}).get("text") or freq,
                               "effects": rest, "frequency": header.get("frequency"), "usage_key": header.get("id", name), "activation_header": header, "cost_effects": manual_effects})
            engine.log(f"    재주 {name}: [보류] {action_problem}", f"feat/{name}")
            continue
        if trig is not None:
            spec = FX.parse_trigger(trig.get("text") or "")
            if spec:
                register_row("ability_triggers",{"name": name, "spec": spec, "frequency": freq, "effects": rest, "_feat": True, "usage_key": header.get("id", name), "activation_header": header, "cost_effects": manual_effects})
                n += 1
            else:
                engine.log(f"    재주 {name}: 발동조건 미해석 '{(trig.get('text') or '')[:40]}' → GM 수동 발동", f"feat/{name}")
                register_row("registry",{"type": "feat_manual", "name": name, "trigger": trig.get("text"), "effects": rest, "frequency": header.get("frequency"), "usage_key": header.get("id", name), "activation_header": header, "cost_effects": manual_effects})
            continue
        if not _static_feature(header, manual_effects, action):
            register_row("registry",{"type": "feat_manual", "name": name, "trigger": freq, "effects": rest, "frequency": header.get("frequency"), "usage_key": header.get("id", name), "activation_header": header, "cost_effects": manual_effects})
            continue
        for effect in rest:
            if effect.get("type")=="grant_move":GRANTS.move_grants(engine.r,effect)
            if effect.get("type")=="grant_ability":GRANTS.ability_grant(engine.r,effect,header.get("id",name))
        for index,e in enumerate(rest):
            tgt=str(e.get("target","self"))
            who=pokemon if ("pokemon" in tgt or tgt=="target") and pokemon else [c]
            if tgt=="your pokemon":
                import world_entities as WORLD
                owned_candidates=WORLD.actors(engine) if slot_targets is None else slot_targets
                who=[p for p in owned_candidates if p.kind=="pokemon" and p.spec.get("trainer_id")==c.entity_id]
            for w in who:
                if _register_feature_effect(engine,c,w,name,header,index,e):
                    n += 1
        total += n
        engine.log(f"  {c.name} 재주 {name}: {'발동조건' if trig else '상시'} 효과 {n}개 등록" + (f" (빈도 {freq})" if freq else ""), f"feat/{name}")
    return total


def manual_feat(engine, c, name, target=None, *, adjustment=None, communication=None):
    if name in __import__('commander_orders').FEATURES:
        return __import__('commander_orders').use(engine,c,target,name,**(adjustment or {}))
    import commander as COMMANDER
    if name == COMMANDER.MOBILIZE:
        if adjustment is not None:raise ValueError('Mobilize has no adjustment')
        return COMMANDER.mobilize(engine, c, target)
    """GM 이 발동조건을 수동으로 인정한 재주를 실행 (발동조건 파서가 못 읽은 것)."""
    import native_switch_transfer as SWITCH
    if SWITCH.identity(name) is not None:
        if adjustment is not None or communication is not None:raise ValueError('switch Feature requires its actual trigger and replacement choice')
        return SWITCH.activate(engine,c,name,target)
    import mindlock as MINDLOCK
    import directive_features as DIRECTIVES,combat_precision_features as CPF,training_features as TRAINING
    if communication is not None and not (DIRECTIVES.identity(name) is not None or CPF.identity(name)==CPF.PINPOINT or TRAINING.identity(name) is not None):
        raise ValueError('established communication requires a supported native Order adapter')
    if name in MINDLOCK.WARNING_NAMES:
        if adjustment is not None:raise ValueError('Warning has no directive adjustment')
        return MINDLOCK.warning(engine,c,target)
    import directive_features as DIRECTIVES
    if DIRECTIVES.identity(name) is not None:
        return DIRECTIVES.activate(engine, c, target, adjustment=adjustment, communication=communication)
    import training_features as TRAINING
    if TRAINING.identity(name) is not None:
        options={} if adjustment is None else adjustment
        if type(options)is not dict or set(options)-{'edition'}:raise ValueError('explicit Training Order source selection only')
        return TRAINING.orders(engine,c,name,target,communication=communication,**options)
    if adjustment is not None:
        raise ValueError("adjustment belongs only to an explicit directive choice")
    import conquerors_march as MARCH
    if name in (MARCH.FEATURE,'정복자의 행진','Conqueror’s March'):
        return MARCH.use(engine,c,target,event_id='conquerors-march:'+c.entity_id+':'+str(len(MARCH._uses(c))+1))
    if name in (MARCH.RAMMING,'래밍 스피드','Ramming Speed'):
        raise ValueError('Ramming Speed Extended TP lesson requires its separate teaching adapter')
    import feature_ability_lessons as ABILITY_LESSONS
    if ABILITY_LESSONS.identity(engine.r,name) is not None:
        raise ValueError("Ability teaching requires explicit choice, duration and payment through teach_feature_ability")
    import combat_precision_features as CPF
    if CPF.identity(name)==CPF.PINPOINT:return CPF.activate(engine,c,target,source=name,communication=communication)
    import turn as TURN
    if not TURN.can_act(engine, c):
        return (0, 1)
    for e in c.registry:
        if e.get("type") == "feat_manual" and e.get("name") == name:
            header = e.get("activation_header", {"frequency": e.get("frequency")})
            action, action_problem = ACTION_META.resolve_feature_action(header)
            if action_problem or not ACTION_META.supported_combat_action(action):
                engine.log("    [보류] " + (action_problem or "재주 행동 종류 실행 미지원: " + str(action)), "trainer/action-points")
                return (0, 1)
            frequency = e.get("frequency") or {}
            key = e.get("usage_key", name)
            if not FREQ.activation_allowed(c, key, frequency,engine=engine):
                engine.log(f"  재주 {name}: 사용 횟수 소진 → 실행 거부", f"feat/{name}")
                return (0, 1)
            cost = AP.check(engine, c, header, e.get("cost_effects", e["effects"]))
            if cost is None:
                return (0, 1)
            before_budget = dict(c.budget) if getattr(c, "budget", None) is not None else None
            before_history = (c.took_standard, list(getattr(c, "_action_history", [])), getattr(c, "_restricted_action_taken", False), getattr(c, "_standard_action_round", None))
            if not ACTION_META.supported_combat_action(action):
                engine.log("    [보류] 재주 행동 종류 해석 필요", "trainer/action-points")
                return (0, 1)
            import action_lifecycle as ACTION
            if not TURN.spend(engine, c, action, name, sleep_cure=ACTION.self_cures_sleep(c, target or c, e["effects"])):
                return (0, 1)
            tgt = target or c
            engine.log(f"  [GM 발동] 재주 {name} ({e.get('trigger')})", f"feat/{name}")
            result = FX.run_effects(engine, c, tgt, [dict(x, target=x.get("target", "target")) for x in e["effects"] if x.get("type") != "cost"], {"attacker": c, "target": tgt, "hit": True, "nat": None, "engine": engine}, f"feat/{name}")
            if result[0] > 0:
                AP.spend(c, cost, header, e.get("cost_effects", e["effects"]))
                FREQ.consume_activation(c, key, frequency,engine=engine)
                import cheerleader as CHEER
                CHEER.batch_activation(engine,c,header.get("id",key),result,orders=True)
            else:
                c.budget = before_budget
                c.took_standard, c._action_history, c._restricted_action_taken, c._standard_action_round = before_history
            return result
    return None


def replace_item(engine,c,item_name,*,source_instance_id=None,selection=None):
    """Explicit GM/sheet observation of one actual slot; not a removal effect."""
    if item_name is not None and (not isinstance(item_name,str) or not item_name.strip()):raise ValueError('known item name or None required')
    old=HELD.select(c,selection)
    if old and old['name']==item_name and old.get('instance_id')==source_instance_id:return {'changed':False,'before':dict(old),'after':dict(old)}
    before=deepcopy(HELD.entries(c))
    def apply(e,actual):
        previous=HELD.select(actual,selection)
        slot=previous['slot_id'] if previous else None
        if previous:
            if previous.get('weapon_key'):
                import turn as TURN
                TURN.unequip_weapon(e,actual,previous['weapon_key'])
            elif previous.get('registration_key'):unregister_item(e,actual,registration_key=previous['registration_key'])
            else:HELD.remove(actual,slot)
        if item_name:
            register_item(e,actual,item_name,source_instance_id=source_instance_id,as_held=True,held_slot=slot)
            if not any(x['name']==item_name and (slot is None or x['slot_id']==slot) for x in HELD.entries(actual)):raise ValueError('observed item has no eligible registration')
        _refresh_unresolved(e,actual)
        return {'changed':True,'before':before,'after':deepcopy(HELD.entries(actual))}
    return GRANTS.transition(engine,c,apply)


def equip_held(engine,actor,item_name,*,source_instance_id=None,slot_id=None):
    """Register an explicitly selected actual held slot atomically."""
    def apply(e,c):
        before={x['slot_id'] for x in HELD.entries(c)}
        register_item(e,c,item_name,source_instance_id=source_instance_id,as_held=True,held_slot=slot_id)
        candidates=[x for x in HELD.entries(c) if x['name']==item_name and (source_instance_id is None or x.get('instance_id')==source_instance_id)]
        if slot_id is not None:candidates=[x for x in candidates if x['slot_id']==slot_id]
        if not candidates:raise ValueError('item did not produce a valid actual held registration')
        return {'held':dict(candidates[-1]),'pending':HELD.pending(c)}
    return GRANTS.transition(engine,actor,apply)


def equipment_options(actor, slots=("held", "장신구")):
    result=[];seen=set();held_rows=HELD.entries(actor)
    for key,record in getattr(actor,"_item_reg",{}).items():
        name=record.get('name',key);actual_slots=record.get('slots',[])
        held=next((x for x in held_rows if x.get('registration_key')==key),None)
        if held is None:
            legacy=[x for x in held_rows if x['name']==name and not x.get('registration_key')]
            if len(legacy)==1:held=legacy[0]
        if not (held is not None and 'held' in slots or set(actual_slots).intersection(slots)):continue
        identity=record.get('instance_id') or ('legacy:'+name if key==name else 'registration:'+key)
        if identity in seen:raise ValueError('one equipment identity has multiple registrations')
        seen.add(identity)
        result.append({'key':identity,'name':name,'item_id':record.get('item_id'),'instance_id':record.get('instance_id'),'held':held is not None,'held_slot':held['slot_id'] if held else None,'registration_key':key,'slots':list(actual_slots)})
    if 'held' in slots:
        for held in held_rows:
            if held.get('weapon_key'):continue
            if any(x.get('held_slot')==held['slot_id'] for x in result):continue
            same=sum(x['name']==held['name'] for x in held_rows)>1
            identity=held.get('instance_id') or ('slot:'+held['slot_id'] if same else 'legacy:'+held['name'])
            result.append({'key':identity,'name':held['name'],'item_id':held.get('item_id'),'instance_id':held.get('instance_id'),'held':True,'held_slot':held['slot_id'],'registration_key':held.get('registration_key'),'slots':[]})
    for key,record in actor.custom_conditions.get('equipped_weapons',{}).items():
        if (record.get('item_id') == 'item/몬스터볼-캐논'
                and any(row.get('instance_id') == record.get('instance_id')
                        and row.get('item_id') == record['item_id']
                        for row in getattr(actor,'_item_reg',{}).values())):
            continue  # The actual registered item already owns this physical selection.
        held=next((r for r in held_rows if r.get('weapon_key')==key),None)
        if set(record.get('slots',[])).intersection(slots) or held is not None and 'held' in slots:
            result.append({'key':'weapon:'+key,'name':record['weapon']['name'],'instance_id':record['weapon'].get('instance_id'),'held':held is not None,'held_slot':held['slot_id'] if held else None,'slots':list(record['slots']),'weapon_key':key})
    if set(slots).intersection(('held','주요손','반대손')):
        import wielder_capability as WIELDER
        result.extend(WIELDER.natural_rows(actor))
    return result


def selected_equipment(actor,selection,slots=("held","장신구")):
    options=equipment_options(actor,slots)
    if selection is None and len(options)==1:return options[0]
    row=next((x for x in options if x['key']==selection or x.get('held_slot')==selection),None)
    if row is None:raise ValueError('selection does not identify eligible actual equipment')
    return row


def _unregister_selected(e,c,row):
    if row.get('weapon_key'):
        import turn as TURN
        TURN.unequip_weapon(e,c,row['weapon_key'])
    elif row.get('registration_key') is not None:unregister_item(e,c,registration_key=row['registration_key'])
    elif row.get('held_slot'):HELD.remove(c,row['held_slot'])


def _refresh_unresolved(e,c):
    # After one duplicate leaves, the sole remaining item's ordinary effect is
    # determined again. Re-register only that actual source, never guess stacking.
    for held in list(HELD.entries(c)):
        if not held.get('effects_pending'):continue
        if sum(x.get('item_id')==held.get('item_id') for x in HELD.entries(c))!=1:continue
        old=dict(held);unregister_item(e,c,registration_key=held['registration_key'],maturation_release=False)
        register_item(e,c,old['name'],source_instance_id=old.get('instance_id'),as_held=True,held_slot=old['slot_id'])


def _move_selected(engine,first,second,selections,*,preserve_slots=False):
    """Pairs contain actual giver index, receiver index and explicit key."""
    def apply(e,a,b):
        actors=(a,b);moves=[]
        for giver_idx,receiver_idx,key in selections:
            giver,receiver=actors[giver_idx],actors[receiver_idx]
            row=selected_equipment(giver,key)
            uid=row.get('instance_id');obj=getattr(e,'_physical_objects',{}).get(uid)
            if uid and (obj is None or obj.get('equipped_by')!=giver.entity_id):raise ValueError('actual equipment holder disagrees')
            moves.append((giver,receiver,row,obj))
        counts={id(c):len(HELD.entries(c)) for c in actors}
        for giver,receiver,row,obj in moves:
            if row['held']:counts[id(giver)]-=1
            if row['held'] or not preserve_slots:counts[id(receiver)]+=1
        for c in actors:
            if counts[id(c)]>HELD.capacity(c)['maximum']:raise ValueError('destination held capacity exceeded')
        import capability_actions as CAP
        import world_entities as WORLD
        loads={id(c):[dict(x) for x in c.spec.get('_carried_load',{}).get('objects',[])] for c in actors};affected=set()
        for giver,receiver,row,obj in moves:
            if obj is None or not obj.get('carrier_id'):continue
            if obj['carrier_id']!=giver.entity_id:raise ValueError('item carrier differs from holder')
            load=next((x for x in loads[id(giver)] if x['id']==row['instance_id']),None)
            if load is None or load['weight_kg']!=obj.get('weight_kg'):raise ValueError('actual carried weight evidence disagrees')
            for c in (giver,receiver):
                state=c.spec.get('_carried_load',{})
                if state.get('blocked_actions') or state.get('failure_pending'):raise ValueError('carried equipment needs current ruling')
            loads[id(giver)].remove(load);loads[id(receiver)].append(load);affected.update((id(giver),id(receiver)))
        for giver,receiver,row,obj in moves:_unregister_selected(e,giver,row)
        moving={row['instance_id'] for giver,receiver,row,obj in moves if row.get('instance_id')}
        for c in actors:
            if id(c) in affected:CAP.set_carried(e,c,[x for x in c.spec.get('_carried_load',{}).get('objects',[]) if x['id'] not in moving],'actual equipment release')
        for c in actors:
            if id(c) in affected:CAP.set_carried(e,c,loads[id(c)],'actual equipment transfer')
        for giver,receiver,row,obj in moves:
            if obj is not None:obj['equipped_by']=receiver.entity_id;WORLD._set_object_location(obj,{'kind':'unknown'})
            as_held=row['held'] or not preserve_slots
            register_item(e,receiver,row['name'],source_instance_id=row.get('instance_id'),as_held=as_held)
            if not equipment_options(receiver,('held',) if as_held else tuple(row['slots'])):raise ValueError('item has no eligible destination registration')
        for c in actors:_refresh_unresolved(e,c)
        return {'changed':bool(moves),'transfers':[{'from':giver.entity_id,'to':receiver.entity_id,'item':row['name'],'instance_id':row.get('instance_id')} for giver,receiver,row,obj in moves]}
    return GRANTS.transition(engine,first,apply,participants=(second,))


def exchange_items(engine,first,second,*,swap=True,consent_by=(),first_selection=None,second_selection=None,slots=('held',)):
    if first is second:return {'changed':False}
    import equipment_protection as PROTECTION
    selected=[]
    for i,c in enumerate((first,second) if swap else (first,)):
        options=equipment_options(c,slots)
        if not options:continue
        row=selected_equipment(c,(first_selection,second_selection)[i],slots)
        PROTECTION.require(engine,c,row,'exchange' if swap else 'give',consent_by)
        selected.append((i,1-i,row['key']))
    if not swap and HELD.any_held(second):raise ValueError('this giving source requires an empty target')
    return _move_selected(engine,first,second,selected,preserve_slots='장신구' in slots)


def transfer_equipment(engine,giver,receiver,selection,*,slots=("held","장신구"),consent_by=()):
    import equipment_protection as PROTECTION
    row=selected_equipment(giver,selection,slots)
    PROTECTION.require(engine,giver,row,'transfer',consent_by)
    if giver is receiver:return {'changed':False}
    if HELD.any_held(receiver):raise ValueError('this theft source requires an empty receiver')
    result=_move_selected(engine,giver,receiver,[(0,1,row['key'])])
    if result['transfers']:result.update(result['transfers'][0])
    return result


def drop_equipment(engine,actor,selections,*,slots=("held","장신구"),consent_by=(),source="equipment/drop"):
    selections=tuple(selections)
    if len(set(selections))!=len(selections):raise ValueError('duplicate equipment selection')
    import equipment_protection as PROTECTION
    for selection in selections:PROTECTION.require(engine,actor,selected_equipment(actor,selection,slots),'drop',consent_by)
    def apply(e,c):
        import world_entities as W
        import capability_actions as CAP
        rows=[selected_equipment(c,x,slots) for x in selections]
        for row in rows:
            if row.get('weapon_key'):
                import turn as TURN
                record=c.custom_conditions['equipped_weapons'][row['weapon_key']]
                weapon=TURN.unequip_weapon(e,c,row['weapon_key'])
                obj=getattr(e,'_physical_objects',{}).get(row.get('instance_id'))
                if obj is not None and obj.get('carrier_id'):
                    if obj['carrier_id']!=c.entity_id:raise ValueError('dropped weapon carrier disagrees')
                    load=c.spec.get('_carried_load',{})
                    if load.get('blocked_actions') or load.get('failure_pending'):raise ValueError('weapon drop needs current carrying ruling')
                    CAP.set_carried(e,c,[x for x in load.get('objects',[]) if x['id']!=row['instance_id']],'equipment weapon dropped')
                    W._set_object_location(obj,W.location_of(c))
                if not hasattr(e,'ground_items'):e.ground_items=[]
                e.ground_items.append({'item':weapon,'weapon_record':record,'location':W.location_of(c),'from_actor':c.entity_id,'source':source,'kind':'weapon','former_equipment_key':row['weapon_key']})
                continue
            uid=row.get('instance_id');obj=getattr(e,'_physical_objects',{}).get(uid)
            if uid and (obj is None or obj.get('equipped_by')!=c.entity_id):raise ValueError('dropped equipment holder disagrees')
            if obj and obj.get('carrier_id'):
                if obj['carrier_id']!=c.entity_id:raise ValueError('dropped carrier disagrees')
                load=c.spec.get('_carried_load',{})
                if load.get('blocked_actions') or load.get('failure_pending'):raise ValueError('drop needs current carrying ruling')
                CAP.set_carried(e,c,[x for x in load.get('objects',[]) if x['id']!=uid],'equipment dropped')
            _unregister_selected(e,c,row)
            if obj is not None:W._set_object_location(obj,W.location_of(c))
        _refresh_unresolved(e,c)
        return {'changed':bool(rows),'dropped':rows}
    return GRANTS.transition(engine,actor,apply)


def drop_item(engine,actor,*,selection=None,consent_by=()):
    options=equipment_options(actor,('held',))
    if not options:return {'changed':False,'dropped':[]}
    row=selected_equipment(actor,selection,('held',))
    return drop_equipment(engine,actor,[row['key']],slots=('held',),consent_by=consent_by)


def destroy_equipment(engine,actor,selection,*,reason,consent_by=()):
    """Explicit physical destruction, distinct from voluntary consumable use."""
    if not isinstance(reason,str) or not reason.strip():raise ValueError("destruction needs its actual source/reason")
    import equipment_protection as PROTECTION
    row=selected_equipment(actor,selection,("held","장신구","주요손","반대손"))
    PROTECTION.require(engine,actor,row,"destroy",consent_by)
    if row.get("weapon_key"):raise ValueError("legacy weapon destruction needs its physical-instance producer")
    if not row.get("instance_id"):raise ValueError("destruction cannot invent a physical identity for legacy equipment")
    def apply(e,c):
        actual=selected_equipment(c,selection,("held","장신구","주요손","반대손"))
        # The caller has already bound actual holder consent. Staged actors have
        # distinct object identity, so carry those validated choices explicitly.
        drop_equipment(e,c,[selection],slots=("held","장신구","주요손","반대손"),consent_by=(c,) if actor in consent_by else ())
        obj=e._physical_objects[actual["instance_id"]]
        import world_entities as WORLD
        WORLD.finish_physical_use(e,obj,"destroyed",{"source":reason,"former_holder_id":c.entity_id})
        return {"destroyed":True,"instance_id":actual["instance_id"],"source":reason}
    return GRANTS.transition(engine,actor,apply)
