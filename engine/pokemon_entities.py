"""Individual Pokemon and eggs have distinct persistent identities and states.

Species records are templates. Missing individual facts stay unknown; breeding
and hatching procedures supply decisions rather than having this schema invent them.
"""
from copy import deepcopy
from math import isfinite
import state_fields as F
import world_entities as W


LOYALTY_SOURCE = 'input/ch05-pokemon.md:567-632'
LOYALTY_MEANINGS = {
    0: '혐오와 강한 반항; 행동은 극단적인 두려움부터 적극적인 반항까지 다양함',
    1: '트레이너를 싫어함; 친밀도 0보다 덜 극단적인 반항',
    2: '트레이너를 용납하고 충분히 좋아하지만 특별한 애착은 없음',
    3: '통상적인 호감과 어느 정도의 존경; 지속적인 돌봄과 함께 보내는 시간이 관계의 근거',
    4: '친밀도 3과 같은 종류의 행동에 더 큰 호감과 존경',
    5: '진정한 친구로서 큰 신뢰와 존중을 나누는 상호 유대',
    6: '진정한 유대와 절대적인 신뢰; 서로를 위해 위험을 감수할 의향',
}


def loyalty_value(actor, *, required=False):
    value=actor.spec.get('loyalty')
    if value is not None:F.integer(value,'GM-secret loyalty',0,6)
    elif required:raise ValueError('GM loyalty for the actual trainer relationship is unknown')
    return value


def effective_loyalty_value(actor, *, engine, required=False):
    """Source-owned effective rank; the observed current-owner baseline stays 0..6."""
    value=loyalty_value(actor,required=required)
    if engine is None:return value
    if value is None:return None
    W.require_actors(engine,actor)
    owner=W.actor_index(engine).get(actor.spec.get('trainer_id'))
    if owner is None:return value
    import mentor
    row=mentor.acquired(owner,mentor.EGG_TUTOR)
    return value+(1 if row and row['snapshot']['source']['variant']=='local_csv' else 0)


def _loyalty_relations(actor):
    rows=actor.spec.get('loyalty_relations',{})
    if not isinstance(rows,dict):raise ValueError('loyalty relations must be an owner identity mapping')
    for owner,row in rows.items():
        W._text(owner,'loyalty relation trainer identity')
        if not isinstance(row,dict):raise ValueError('loyalty relation observation required')
        value=row.get('value')
        if value is not None:F.integer(value,'observed loyalty',0,6)
        W._text(row.get('reason'),'GM loyalty observation reason')
        if row.get('hint') is not None and not isinstance(row['hint'],str):raise ValueError('public loyalty hint must be GM-selected text')
    owner=actor.spec.get('trainer_id')
    if owner in rows and rows[owner].get('value')!=loyalty_value(actor):raise ValueError('current loyalty and actual trainer relation disagree')
    return rows


def loyalty_projection(actor, *, viewer='player',engine=None):
    if viewer not in ('player','gm'):raise ValueError('explicit player or GM projection required')
    value=loyalty_value(actor);rows=_loyalty_relations(actor);owner=actor.spec.get('trainer_id')
    row=rows.get(owner,{})
    if viewer=='player':return {'hint':row.get('hint')} if row.get('hint') is not None else {}
    return {'trainer_id':owner,'value':value,'known':value is not None,'meaning':LOYALTY_MEANINGS.get(value),
        **({'effective_value':effective_loyalty_value(actor,engine=engine)} if engine is not None else {}),
        'source':LOYALTY_SOURCE,'observation':deepcopy(row) if row else None,
        'change_authority':'GM judgment; elapsed time, food and isolated kindness never automatically change the rank'}


def observe_loyalty(engine,actor,value,*,reason,hint=None,request_id=None,expected_revision=None):
    """GM observation of the current relationship; no automatic affection award."""
    W._text(reason,'GM loyalty observation reason')
    if value is not None:F.integer(value,'GM-secret loyalty',0,6)
    if hint is not None and not isinstance(hint,str):raise ValueError('public loyalty hint must be text or absent')
    actors=W.actor_index(engine);owner=actor.spec.get('trainer_id')
    if actors.get(actor.entity_id) is not actor or actor.kind!='pokemon':raise ValueError('actual Pokemon required')
    if owner not in actors or actors[owner].kind!='trainer':raise ValueError('actual current trainer relationship required')
    rows=deepcopy(_loyalty_relations(actor));revision=actor.spec.get('loyalty_revision',0)
    F.integer(revision,'loyalty observation revision',0)
    payload={'trainer_id':owner,'value':value,'reason':reason,'hint':hint}
    receipts=actor.spec.get('loyalty_observations',{})
    if request_id is not None:
        from resolution_transaction import replay_result
        prior=replay_result(receipts,request_id,payload)
        if prior is not None:return prior
    if expected_revision is not None and expected_revision!=revision:raise ValueError('loyalty observation revision changed')
    row={**payload,'source':LOYALTY_SOURCE,'at':engine.elapsed_seconds,'revision':revision+1}
    result={'intent':payload,'before':loyalty_value(actor),'after':value,'revision':revision+1}
    rows[owner]=row
    actor.spec.update(loyalty=value,loyalty_relations=rows,loyalty_revision=revision+1)
    if request_id is not None:actor.spec.setdefault('loyalty_observations',{})[request_id]=deepcopy(result)
    # Ordinary shared logs contain no secret number, reason, or inferred rank.
    engine.gm._rec('친밀도 관측','비공개','비공개','GM 전용 관계 관측',actor)
    return deepcopy(result)


def prepare_loyalty_transfer(actor,old_owner,new_owner,*,reason,at):
    """Preserve observations by relationship, never transfer affection by name."""
    W._text(reason,'ownership transfer reason')
    rows=deepcopy(_loyalty_relations(actor));value=loyalty_value(actor)
    if old_owner not in rows:
        rows[old_owner]={'value':value,'reason':'Previously imported current-owner observation; original time unknown',
            'hint':None,'source':LOYALTY_SOURCE,'at':None,'legacy_import':True}
    # A past observation for a returning owner remains the last known fact.
    # Time alone supplies no rule for changing it; a GM may update it explicitly.
    return {'loyalty':rows.get(new_owner,{}).get('value'),'loyalty_relations':rows}


def validate_actor(actor):
    spec = actor.spec
    import legendary_commands as LEGENDARY
    LEGENDARY.validate_actor(actor)
    import mentor
    mentor.validate_actor(actor)
    import pokemon_activities as ACTIVITIES
    ACTIVITIES.validate_disobedience_actor(actor)
    _loyalty_relations(actor)
    validate_dispositions(actor)
    if spec.get("loyalty") is not None:
        F.integer(spec["loyalty"], "GM-secret loyalty", 0, 6)
    for key in ("gender", "nature", "species"):
        if spec.get(key) is not None:
            W._text(spec[key], "individual " + key)
    for key in ("height_m", "weight_kg"):
        value = spec.get(key)
        if value is not None and (type(value) not in (int, float) or not isfinite(value) or value < 0):
            raise ValueError("individual " + key + " must be a known nonnegative physical measurement")
    for key in ("inheritance_moves",):
        value = spec.get(key, [])
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value) or len(set(value)) != len(value):
            raise ValueError(key + " must preserve distinct move identities")
    return True


def actor_projection(actor, *, viewer="player"):
    if viewer not in ("player", "gm"):
        raise ValueError("explicit player or GM projection required")
    validate_actor(actor)
    import body_state as BODY
    result = {"entity_id": actor.entity_id, "name": actor.name,
        "species_id": actor.spec.get("species"), "kind": actor.kind,
        "level": actor.level, "location": W.location_of(actor),
        "gender": actor.spec.get("gender"), "nature": actor.spec.get("nature"),
        "height_m": actor.spec.get("height_m"), "weight_kg": BODY.weight_kg(actor),
        "size": actor.spec.get("size"), "weight_class": actor.weight_class,
        "types": list(actor.types), "moves": list(actor.moves), "abilities": list(actor.abilities),
        "inheritance_moves": deepcopy(actor.spec.get("inheritance_moves", []))}
    result["description"] = {key: actor.spec.get(key) for key in F.DESCRIPTION_FIELDS}
    import nature_state as NATURE
    result["nature_state"] = NATURE.describe(actor.r, actor.spec.get("nature"))
    result["loyalty_state"] = loyalty_projection(actor, viewer=viewer)
    if viewer == "gm":
        result["loyalty"] = actor.spec.get("loyalty")
    return result


def species_projection(rules, species_id):
    record = rules.species.get(species_id)
    if record is None:
        raise ValueError("selected species template required")
    result = deepcopy(record)
    result["record_kind"] = "egg_catalog_placeholder" if record.get("name") == "알" else "species_template"
    result["individual_identity"] = None
    import species_metadata as METADATA
    result["template_facts"] = METADATA.project(rules, record)
    # Catalog sex ratios and measurements never become observed individual facts.
    return result


def prepare_egg(engine, owner, data):
    """Preflight a concrete producer's unhatched egg before costs/state commit."""
    if W.actor_index(engine).get(owner.entity_id) is not owner or owner.kind != "trainer":
        raise ValueError("actual trainer owner required")
    result = deepcopy(data)
    result.update(entity_id=F.new_id("egg"), kind="egg", owner_id=owner.entity_id)
    result.setdefault("parents", [])
    result.setdefault("species", None)
    result.setdefault("hatch_level", None)
    result.setdefault("gm_hatch_details", None)
    result.setdefault("hatch_timing", {"status": "pending", "reason": "GM hatch time has not been established"})
    import creation_egg as CREATION
    CREATION.bind_parents(engine,owner,result)
    validate_egg(engine, owner, result)
    if any(row.get("id") == result["id"] for row in owner.spec.get("eggs", [])):
        raise ValueError("producer egg key already exists for this owner")
    if result["entity_id"] in W.entity_index(engine):
        raise ValueError("new egg identity collides with an existing entity")
    return result


def validate_egg(engine, owner, row):
    if not isinstance(row, dict) or row.get("kind") != "egg":
        raise ValueError("an egg uses its own object schema, never a zero-stat Combatant")
    W._text(row.get("entity_id"), "egg identity")
    W._text(row.get("id"), "owner-scoped producer egg key")
    W._text(row.get("source"), "egg source")
    if row.get("owner_id") != owner.entity_id:
        raise ValueError("egg ownership must match its actual containing registry")
    if type(row.get("hatched")) is not bool:
        raise ValueError("egg hatch state must be explicit")
    parents = row.get("parents", [])
    if not isinstance(parents, (list, tuple)) or any(not isinstance(x, str) or not x for x in parents) or len(set(parents)) != len(parents):
        raise ValueError("parent provenance must contain distinct individual identities")
    if row.get("species") is not None:
        W._text(row["species"], "egg species")
    if row.get("source")=="edge/고생물학자":
        if 'fossil_birth_policy' not in row and row.get("hatch_level")!=10:raise ValueError("fossil eggs hatch at level10")
        W._text(row.get('fossil_entity_id'),'actual original fossil identity')
        W._text(row.get('restored_by'),'actual fossil restorer identity')
    if row.get("hatch_level") is not None:
        F.integer(row["hatch_level"], "selected hatch level", 1, 100)
    if row.get("produced_at") is not None:
        F.integer(row["produced_at"], "egg production time", 0)
    timing = row.get("hatch_timing")
    if not isinstance(timing, dict) or timing.get("status") not in ("pending", "observed_ready", "hatched"):
        raise ValueError("explicit hatch timing observation required")
    W._text(timing.get("reason"), "hatch timing basis")
    if row["hatched"]:
        W._text(row.get("pokemon_id"), "hatched actual Pokemon identity")
        if timing["status"] != "hatched":
            raise ValueError("hatched egg and timing state disagree")
    elif row.get("pokemon_id") is not None:
        raise ValueError("unhatched egg cannot already identify a hatched Pokemon")
    import creation_egg as CREATION
    CREATION.validate_binding(engine,row)
    import creation_fossil as FOSSIL
    FOSSIL.validate_egg(row)
    return True


def egg_index(engine):
    result = {}; actors = W.actor_index(engine)
    for owner in actors.values():
        local = set()
        for row in owner.spec.get("eggs", []):
            validate_egg(engine, owner, row)
            if row["id"] in local:
                raise ValueError("egg producer key repeated within one owner")
            local.add(row["id"])
            uid = row["entity_id"]
            if uid in result or uid in actors or uid in getattr(engine, "_physical_objects", {}) or uid in getattr(engine, "_partial_entities", {}):
                raise ValueError("egg identity collides with another actual entity")
            if row["hatched"]:
                child = actors.get(row["pokemon_id"])
                if child is None or child.kind != "pokemon":
                    raise ValueError("hatched egg must resolve to the actual Pokemon")
            result[uid] = (owner, row)
    return result


def egg_projection(engine, egg_entity_id):
    entry = egg_index(engine).get(egg_entity_id)
    if entry is None:
        raise ValueError("actual egg identity required")
    owner, row = entry
    result = deepcopy(row)
    result["owner_location"] = W.location_of(owner)
    import physical_incubator as INCUBATOR
    result.update(INCUBATOR.projection(engine,row))
    result["combatant"] = False
    return result


def validate_world(engine):
    eggs=egg_index(engine);fossils=fossil_index(engine);actors=W.actor_index(engine)
    import legendary_commands as LEGENDARY
    LEGENDARY.validate_world(engine,actors)
    import pokemon_activities as ACTIVITIES
    ACTIVITIES.validate_disobedience_world(engine,actors)
    if set(eggs)&set(fossils):raise ValueError('egg/fossil identities collide')
    for uid,(owner,row) in fossils.items():
        if row['status']=='fossil':continue
        egg_entry=eggs.get(row['egg_entity_id'])
        if egg_entry is None or egg_entry[1].get('fossil_entity_id')!=uid:raise ValueError('restored fossil needs its actual egg source reference')
        egg=egg_entry[1]
        if egg.get('restored_by')!=row['restored_by'] or egg.get('species')!=row['species']:raise ValueError('fossil/egg original restorer and species disagree')
        restorer=actors.get(row['restored_by'])
        if restorer is None or restorer.kind!='trainer':raise ValueError('actual fossil restorer reference required')
        if row['status']=='hatched' and (not egg['hatched'] or egg.get('pokemon_id')!=row['pokemon_id']):raise ValueError('fossil/egg/child lifetime state disagrees')
        if row['status']=='hatched':
            child=actors[row['pokemon_id']]
            if child.spec.get('fossil_entity_id')!=uid or child.spec.get('fossil_egg_entity_id')!=egg['entity_id']:raise ValueError('hatched Pokemon must retain original fossil and egg lineage')
        if row['status']=='restored_to_egg' and egg['hatched']:raise ValueError('fossil restoration state lags actual egg hatch')
    for owner,egg in eggs.values():
        if egg.get('fossil_entity_id') is not None:egg_fossil(engine,egg)
    import creation_fossil as FOSSIL
    FOSSIL.validate_world(engine,fossils,eggs,actors)
    import physical_incubator as INCUBATOR
    INCUBATOR.validate_world(engine,eggs)
    return True


def transfer_egg(engine, old_owner, new_owner, egg_entity_id, *, reason, request_id):
    W._text(reason, "egg transfer reason"); W._text(request_id, "egg transfer identity")
    actors = W.actor_index(engine)
    if any(actors.get(owner.entity_id) is not owner or owner.kind != "trainer" for owner in (old_owner, new_owner)):
        raise ValueError("actual trainer owners required")
    if old_owner is new_owner:
        raise ValueError("distinct owners required")
    key = "egg:" + request_id
    intent = {"entity_id":egg_entity_id,"old_owner":old_owner.entity_id,"new_owner":new_owner.entity_id,"reason":reason}
    receipts = getattr(engine, "_world_relation_receipts", {})
    if key in receipts:
        from resolution_transaction import replay_result
        prior = replay_result({key: {'intent': receipts[key]}}, key, intent)
        return prior['intent']
    entry = egg_index(engine).get(egg_entity_id)
    if entry is None or entry[0] is not old_owner or entry[1]["hatched"]:
        raise ValueError("actual unhatched egg owned by this trainer required")
    row = entry[1]
    import physical_incubator as INCUBATOR
    INCUBATOR.require_access(engine,old_owner,row)
    if any(other.get("id") == row["id"] for other in new_owner.spec.get("eggs", [])):
        # Preserve the old producer key as provenance, not as globally unique ID.
        local_key = row["entity_id"]
    else:
        local_key = row["id"]
    proposed = deepcopy(row)
    proposed["owner_id"] = new_owner.entity_id
    proposed["id"] = local_key
    proposed.setdefault("ownership_history", []).append(deepcopy(intent))
    validate_egg(engine, new_owner, proposed)
    old_owner.spec["eggs"][:] = [existing for existing in old_owner.spec["eggs"] if existing is not row]
    row["owner_id"] = new_owner.entity_id
    row["id"] = local_key
    row.setdefault("ownership_history", []).append(deepcopy(intent))
    new_owner.spec.setdefault("eggs", []).append(row)
    if not hasattr(engine, "_world_relation_receipts"):
        engine._world_relation_receipts = {}
    engine._world_relation_receipts[key] = deepcopy(intent)
    engine.gm._rec("egg ownership",old_owner.entity_id,new_owner.entity_id,reason,None)
    return deepcopy(intent)


DISPOSITION_VALUES=('매우 적대적','적대적','두려움','중립','우호적','매우 우호적')
DISPOSITION_MEANINGS={
 '매우 적대적':'침입에 강하게 맞서며 축출하거나 공격할 가능성이 높음',
 '적대적':'침입에 맞서며 축출하거나 공격할 가능성이 높음',
 '두려움':'트레이너를 경계하며 도망치거나 숨으려 할 수 있음',
 '중립':'무시하거나 태연히 관찰하며 특별히 관여하지 않음',
 '우호적':'상호작용을 시도함; 자발적 포획 동의는 별도 사실',
 '매우 우호적':'상호작용을 시도함; 자발적 포획 동의는 별도 사실',
}


def validate_dispositions(actor):
 spec=actor.spec
 if spec.get('disposition') is not None and spec['disposition'] not in DISPOSITION_VALUES:raise ValueError('initial disposition must name one of six categories')
 groups=spec.get('disposition_groups',{});relations=spec.get('dispositions',{})
 if not isinstance(groups,dict) or not isinstance(relations,dict):raise ValueError('disposition relationships and audiences must be mappings')
 for group,members in groups.items():
  W._text(group,'disposition group identity')
  if not isinstance(members,list) or not members or len(set(members))!=len(members):raise ValueError('distinct explicit disposition group members required')
  for member in members:W._text(member,'disposition audience member identity')
 for audience,value in relations.items():
  if not isinstance(audience,str) or not audience.startswith(('trainer:','group:','pokemon:')) or not audience.split(':',1)[1]:raise ValueError('disposition must identify its trainer, Pokemon performer, or group audience')
  if audience.startswith('group:') and audience.split(':',1)[1] not in groups:raise ValueError('disposition group reference has no declared membership')
  if value not in DISPOSITION_VALUES:raise ValueError('disposition outside six categories')
 failures=spec.get('befriend_failures',[])
 if not isinstance(failures,list) or len(set(failures))!=len(failures) or any(not isinstance(x,str) or not x.startswith(('trainer:','pokemon:')) or not x.split(':',1)[1] for x in failures):raise ValueError('befriend retry locks belong to distinct actual performers')
 history=spec.get('disposition_history',[])
 if not isinstance(history,list):raise ValueError('disposition history must be a list')
 for row in history:
  if not isinstance(row,dict) or row.get('after') not in DISPOSITION_VALUES or row.get('before') not in (*DISPOSITION_VALUES,None):raise ValueError('disposition history has invalid state')
  W._text(row.get('audience'),'historical disposition audience');W._text(row.get('reason'),'historical disposition basis')
 return True


def disposition_projection(actor,audience):
 validate_dispositions(actor)
 if not isinstance(audience,str) or not audience.startswith(('trainer:','group:','pokemon:')) or not audience.split(':',1)[1]:raise ValueError('explicit disposition audience required')
 if audience.startswith('group:') and audience.split(':',1)[1] not in actor.spec.get('disposition_groups',{}):raise ValueError('actual declared group required')
 explicit=audience in actor.spec.get('dispositions',{})
 value=actor.spec.get('dispositions',{}).get(audience,actor.spec.get('disposition'))
 return {'entity_id':actor.entity_id,'audience':audience,'value':value,'known':value is not None,
  'meaning':DISPOSITION_MEANINGS.get(value),'basis':'specific_relationship' if explicit else 'GM_supplied_initial_disposition' if value is not None else 'unobserved',
  'members':deepcopy(actor.spec.get('disposition_groups',{}).get(audience.split(':',1)[1])) if audience.startswith('group:') else None,
  'history':deepcopy([row for row in actor.spec.get('disposition_history',[]) if row.get('audience')==audience]),
  'capture_consent_inferred':False,'source':'input/ch05-pokemon.md:721-728'}


def record_disposition(engine,target,*,audience,before,after,reason,performer,retry_allowed=False,check_total=None):
 # Producers call after their complete declaration/check commit. All input
 # domains have already been validated before spending actions or rolling.
 target.spec.setdefault('disposition_history',[]).append({'audience':audience,'before':before,'after':after,
  'reason':reason,'performer':performer,'retry_allowed':retry_allowed,'check_total':check_total,
  'at':engine.elapsed_seconds,'source':'input/ch05-pokemon.md:721-728'})


STANDARD_FOSSIL_SPECIES=('암나이트','투구','프테라','릴링','아노딥스','두개도스','방패톱스','프로토가','아켄','티고라스','아마루스')


def prepare_fossil(engine,owner,key,data):
 """Give an observed physical fossil one identity; the owner registry is authority."""
 W._text(key,'owner-scoped fossil key')
 if W.actor_index(engine).get(owner.entity_id) is not owner or owner.kind!='trainer':raise ValueError('actual fossil owner required')
 if not isinstance(data,dict) or data.get('species') not in engine.r.species:raise ValueError('GM-established known fossil species required')
 row=deepcopy(data);row.setdefault('entity_id',F.new_id('fossil'))
 row.update(id=key,kind='fossil',owner_id=owner.entity_id,material='calcified_pokemon_remains',origin_state='long_deceased_pokemon',contains_pokemon_dna=True)
 row.setdefault('status','fossil');row.setdefault('source','input/ch05-pokemon.md:742-750')
 row.setdefault('species_basis','standard_fossil' if engine.r.species[row['species']]['name'] in STANDARD_FOSSIL_SPECIES else 'GM_nonstandard_fossil')
 uid=row['entity_id'];W._text(uid,'fossil entity identity')
 entities=W.entity_index(engine);old=owner.spec.get('fossils',{}).get(key)
 if uid in entities and entities[uid] is not old:raise ValueError('fossil identity collides with another entity')
 validate_fossil(engine,owner,key,row)
 return row


def validate_fossil(engine,owner,key,row):
 if not isinstance(row,dict):raise ValueError('fossil record must be a mapping')
 if row.get('species') not in engine.r.species:raise ValueError('known selected fossil species required')
 if row.get('status') not in ('fossil','restored_to_egg','hatched'):raise ValueError('invalid fossil lifetime state')
 # Imported owner-local observations acquire an entity ID through their native
 # identify/restore producer. Validation must not invent identities on reads.
 if row.get('entity_id') is None:return True
 W._text(row['entity_id'],'fossil entity identity')
 if owner.kind!='trainer':raise ValueError('actual fossil owner must be a trainer')
 if row.get('id')!=key or row.get('kind')!='fossil' or row.get('owner_id')!=owner.entity_id:raise ValueError('fossil identity/owner/source registry disagreement')
 if row.get('material')!='calcified_pokemon_remains' or row.get('origin_state')!='long_deceased_pokemon' or row.get('contains_pokemon_dna') is not True:raise ValueError('fossil must preserve its calcified remains and Pokemon DNA distinction')
 if row.get('species_basis') not in ('standard_fossil','GM_nonstandard_fossil'):raise ValueError('explicit fossil species basis required')
 if row.get('status')!='fossil':
  W._text(row.get('egg_entity_id'),'actual restored egg identity');W._text(row.get('restored_by'),'actual fossil restorer identity')
 if row.get('status')=='hatched':W._text(row.get('pokemon_id'),'actual hatched Pokemon identity')
 import creation_fossil as FOSSIL
 FOSSIL.validate_fossil(engine,row)
 return True


def fossil_index(engine):
 result={};actors=W.actor_index(engine)
 for owner in actors.values():
  records=owner.spec.get('fossils',{})
  if not isinstance(records,dict):raise ValueError('owned fossil registry must be a mapping')
  for key,row in records.items():
   validate_fossil(engine,owner,key,row)
   uid=row.get('entity_id')
   if uid is None:continue
   if uid in result or uid in actors or uid in getattr(engine,'_physical_objects',{}) or uid in getattr(engine,'_partial_entities',{}):raise ValueError('fossil identity collides with another entity')
   result[uid]=(owner,row)
 return result


def fossil_projection(engine,entity_id):
 entry=fossil_index(engine).get(entity_id)
 if entry is None:raise ValueError('actual fossil entity identity required')
 owner,row=entry;result=deepcopy(row);result.update(combatant=False,owner_location=W.location_of(owner))
 return result


def egg_fossil(engine,egg):
 """Find original remains even after the resulting egg changes ownership."""
 uid=egg.get('fossil_entity_id');entry=fossil_index(engine).get(uid)
 if entry is None:raise ValueError('actual original fossil source identity required')
 fossil=entry[1]
 if fossil.get('egg_entity_id')!=egg.get('entity_id'):raise ValueError('fossil and its produced egg disagree')
 return fossil


def observe_egg(engine,owner,*,egg_id,reason,parents=()):
 """Explicit GM-intervention egg producer, without invented inherited traits."""
 W._text(reason,'GM egg creation reason')
 actors=W.actor_index(engine)
 if not isinstance(parents,(list,tuple)) or len(set(parents))!=len(parents):raise ValueError('distinct actual parent identities required')
 if any(uid not in actors or actors[uid].kind!='pokemon' for uid in parents):raise ValueError('GM egg parents must identify actual Pokemon')
 row=prepare_egg(engine,owner,{'id':egg_id,'parents':list(parents),'source':'gm/egg_intervention','reason':reason,'hatched':False,'produced_at':engine.elapsed_seconds})
 owner.spec.setdefault('eggs',[]).append(row)
 return deepcopy(row)

