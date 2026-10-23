"""C09-083: one actual maker check becomes one manufactured tag's level.

The existing transformation owns production and the existing SkillEvent owns
the observed dice. This adapter only binds their original identities. Later
barrier, weapon and burning effects have separate source contracts.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import resolution_transaction as _FINGERPRINTS

import arithmetic_policy as M
import acquisition_qualification as QUALIFICATION
import common_checks as C
import crafting_products as PRODUCTS
import crafting_recipes as RECIPES
import crafting_resources as RESOURCES
import skill_feature_actions as SKILLS
import skill_modifiers as MODS
import transformation_use as TRANSFORM
import world_entities as WORLD

SOURCE = 'edge/부적-제작자'
ITEM = 'item/순결의부적-1'
CLAUSE = 'C09-083'
PROFILE = 'cleanse_tag_profile'
PINS = {
    'input/ch09-equipment.md': 'b5aeb6b82af4b05fe0b369368f8b0181ed3b1d22079e8a86a1c4248e6cbf92d2',
    'input/ch03-skills-edges-feats.md': 'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23',
}


def handles(source):
    return source == SOURCE


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('actual Cleanse Tag declaration requires nonempty text')
    return value


def _hash(value):
    try:
        return _FINGERPRINTS.json_fingerprint(value, sort_keys=True, compact=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError('serializable Cleanse Tag intent required') from exc


def definition(rules):
    for filename, expected in PINS.items():
        if expected is None or sha256((Path(rules.root) / filename).read_bytes()).hexdigest() != expected:
            raise ValueError('Cleanse Tag source text changed: ' + filename)
    for source in (SOURCE, ITEM):
        if rules._selected_rule(source) != source:
            raise ValueError('selected Cleanse Tag source requires its own adapter')
        rulings = getattr(rules, 'rulings', None)
        if rulings and any(getattr(rulings, field, {}).get(source) for field in ('mech', 'effects')):
            raise ValueError('overridden Cleanse Tag source requires its own adapter')
    if rules.item_effects(ITEM)[1].get('id') != ITEM:
        raise ValueError('actual selected Cleanse Tag item identity required')
    M.validate_source(rules)
    return {'source': SOURCE, 'item_id': ITEM, 'clause': CLAUSE,
            'action': 'extended', 'level': 'actual final native maker Occult total'}


def _rank(engine, actor):
    if actor.kind != 'trainer':
        raise ValueError('actual trainer Tag Scribe required')
    owned = actor.spec.get('edges', [])
    if not isinstance(owned, list) or not any(x in (SOURCE, '부적 제작자') for x in owned):
        raise ValueError('actual acquired Tag Scribe edge required')
    if MODS.rank(engine.r, actor, '오컬트학')[2] < 3:
        raise ValueError('Tag Scribe requires Novice Occult')
    return MODS.effective_rank(engine.r, actor, '오컬트학')


def crafting_policy(engine, actor, source, seconds):
    if not handles(source):
        raise ValueError('unsupported Cleanse Tag crafting source')
    definition(engine.r)
    C.integer(seconds, 'declared extended work seconds', 1)
    rank = _rank(engine, actor)
    return {'action': 'extended', 'frequency': {'kind': 'daily', 'uses': M.ratio(rank, 2)}}


def _work(value):
    if type(value) is not dict or set(value) != {'source', 'paper', 'prayer', 'seconds', 'reason'}:
        raise ValueError('explicit paper, prayer and extended-work observation required')
    if value['source'] != 'gm/observation' or value['paper'] is not True or value['prayer'] is not True:
        raise ValueError('GM must observe actual paper and prayer preparation')
    C.integer(value['seconds'], 'GM declared extended work seconds', 1)
    _text(value['reason'])
    return deepcopy(value)


def _recipe(work):
    return {'id': 'native:cleanse-tag', 'source': SOURCE,
            'output': {'item_id': ITEM, 'key': ITEM},
            'requirements': [
                {'id': 'scribe', 'condition': {'kind': 'owned', 'fields': ['edges'],
                 'names': [SOURCE, '부적 제작자']}, 'reason': 'actual acquired Tag Scribe'},
                {'id': 'occult', 'condition': {'kind': 'skill', 'skill': '오컬트학',
                 'rank': 3, 'effective': False}, 'reason': 'Novice Occult prerequisite'}],
            'materials': [], 'seconds': work['seconds']}


def _options(actor, event_id, instance_id, work, skill_options):
    _text(event_id); _text(instance_id)
    work = _work(work)
    skill_options = deepcopy(skill_options or {})
    if type(skill_options) is not dict or set(skill_options) - {
            'fixed', 'mods', 'penalty_count', 'fixed_penalties', 'helper_rank', 'helper_bonus',
            'skill_context', 'skill_stunt'}:
        raise ValueError('native skill options only; caller tag level is forbidden')
    token = _hash([SOURCE, actor.entity_id, event_id])
    skill_options['roll_id'] = 'cleanse-tag:' + token + ':occult'
    options = {'recipe': _recipe(work), 'count': 1, 'reason': work['reason'],
               'work': work, 'skill_options': skill_options, 'sequence_id': 'cleanse-tag:' + token}
    product = {'mode': 'create', 'instance_ids': [instance_id], 'owner_id': actor.entity_id,
               'state': 'intact', 'attachments': []}
    return options, product


class CleanseTagUse(TRANSFORM.TransformationUse):
    operation = 'craft_item'

    def perform(self, engine, actor, options):
        _work(options['work'])
        if options['recipe'] != _recipe(options['work']) or options['count'] != 1:
            raise ValueError('exact single Cleanse Tag recipe required')
        event = SKILLS.event(engine, actor, options['skill_options']['roll_id'])
        if event is None or event.state != 'final':
            raise ValueError('actual final maker Occult event required before production')
        return RECIPES.perform(engine, actor, options['recipe'], count=1, reason=options['reason'])

    def sources(self, engine, actor, options, result):
        return [RESOURCES.SOURCE, SOURCE, ITEM]

    def bind_product(self, engine, actor, result, plan):
        options = plan['intent']['options']
        roll_id = options['skill_options']['roll_id']
        event = SKILLS.event(engine, actor, roll_id)
        if event is None or event.state != 'final' or event.skill != MODS.skill_id(engine.r.skill_policy, '오컬트학'):
            raise ValueError('actual final native Occult required')
        profile = {'source': SOURCE, 'item_id': ITEM, 'maker_id': actor.entity_id,
                   'production_id': plan['id'], 'event_id': plan['event_id'],
                   'instance_id': result['product_instance_ids'][0], 'roll_id': roll_id,
                   'level': event.final.total, 'rank_at_creation': event.prepared[2],
                   'intent_sha256': plan['intent_sha256']}
        result[PROFILE] = profile
        engine._physical_objects[profile['instance_id']][PROFILE] = deepcopy(profile)


def craft(engine, maker, *, event_id, instance_id, work, skill_options=None):
    """Create a single identified tag; level is always derived, never an input."""
    WORLD.require_actors(engine, maker)
    definition(engine.r)
    validate_world(engine, WORLD.actor_index(engine))
    options, product = _options(maker, event_id, instance_id, work, skill_options)
    request = dict(options, product_policy=product, event_id=event_id)
    plan = PRODUCTS.preflight(engine, maker, 'craft_item', options, product, event_id)
    if 'replay' in plan:
        return plan['replay']
    RECIPES.prepare(engine, maker, options['recipe'], count=1)
    basis = {'source': SOURCE, 'intent_sha256': plan['intent_sha256']}
    result = SKILLS.sequence(engine, options['sequence_id'], basis,
        [(maker, '오컬트학', options['skill_options'])],
        lambda rolls: CleanseTagUse().execute(engine, TRANSFORM.TransformRequest(maker, request)))
    validate_world(engine, WORLD.actor_index(engine))
    return result


def validate_world(engine, index=None):
    index = WORLD.actor_index(engine) if index is None else index
    objects = getattr(engine, '_physical_objects', {})
    found = {}; rolls = set()
    for actor in index.values():
        for production_id, row in actor.spec.get(PRODUCTS.KEY, {}).items():
            result = row.get('transformation', {}).get('result', {})
            if result.get('recipe_source') != SOURCE and PROFILE not in result:
                continue
            definition(engine.r)
            profile = result.get(PROFILE)
            if type(profile) is not dict or set(profile) != {
                    'source', 'item_id', 'maker_id', 'production_id', 'event_id', 'instance_id',
                    'roll_id', 'level', 'rank_at_creation', 'intent_sha256'}:
                raise ValueError('original Cleanse Tag profile required')
            intent = row['intent']; options = intent['options']; product = intent['product_policy']
            work = _work(options['work'])
            expected_options, expected_product = _options(actor, row['event_id'], profile['instance_id'], work,
                {k: v for k, v in options['skill_options'].items() if k != 'roll_id'})
            if options != expected_options or product != expected_product or intent['operation'] != 'craft_item':
                raise ValueError('Cleanse Tag production request changed')
            if result['recipe_definition'] != _recipe(work) or result['count'] != 1 or result['item_id'] != ITEM:
                raise ValueError('Cleanse Tag native output changed')
            # Validate the historical native admission, never live ownership or
            # the maker's later rank. Current rights only admit a new craft.
            qualified = QUALIFICATION.require(SOURCE, actor.entity_id, 'recipe:native:cleanse-tag', [
                QUALIFICATION.check(rule['id'], 'prerequisite', True, rule['reason'])
                for rule in _recipe(work)['requirements']])
            if result.get('qualification') != qualified:
                raise ValueError('original Tag Scribe and Novice Occult qualification required')
            if (profile['source'], profile['item_id'], profile['maker_id'], profile['production_id'],
                    profile['event_id'], profile['intent_sha256']) != (
                    SOURCE, ITEM, actor.entity_id, production_id, row['event_id'], row['intent_sha256']):
                raise ValueError('Cleanse Tag original production binding changed')
            if profile['roll_id'] != options['skill_options']['roll_id'] or profile['roll_id'] in rolls:
                raise ValueError('one actual maker roll belongs to one tag only')
            rolls.add(profile['roll_id'])
            event = SKILLS.event(engine, actor, profile['roll_id'])
            run = getattr(engine, '_skill_sequences', {}).get(options['sequence_id'])
            if (event is None or event.state != 'final' or event.final is None
                    or event.skill != MODS.skill_id(engine.r.skill_policy, '오컬트학')
                    or run is None or run['basis'] != {'source': SOURCE, 'intent_sha256': row['intent_sha256']}
                    or len(run['requests']) != 1 or run['requests'][0][0] is not actor
                    or run['requests'][0][1] != event.request or run['requests'][0][-1] != profile['roll_id']
                    or event.request != SKILLS._request(engine, actor, '오컬트학', options['skill_options'])):
                raise ValueError('actual original maker Occult event missing or changed')
            C.integer(profile['level'], 'actual tag level')
            C.integer(profile['rank_at_creation'], 'historical maker rank', 3)
            if profile['rank_at_creation'] != event.prepared[2] or profile['rank_at_creation'] != event.first.rank:
                raise ValueError('historical maker rank differs from original native skill event')
            if profile['level'] != event.final.total:
                raise ValueError('Cleanse Tag level differs from original final Occult')
            uid = profile['instance_id']; obj = objects.get(uid)
            if (obj is None or obj.get('item_rule_id') != ITEM or obj.get(PROFILE) != profile
                    or result.get('product_instance_ids') != [uid] or uid in found):
                raise ValueError('actual single original Cleanse Tag body required')
            found[uid] = profile
    for uid, obj in objects.items():
        if PROFILE in obj and uid not in found:
            raise ValueError('copied Cleanse Tag profile lacks original production')
    validate_barriers(engine, index)
    validate_weapon_tags(engine, index)
    return True


def level(engine, instance_id):
    """Read the persistent original level of an actual currently usable tag."""
    # Includes the native original-reference and request-hash checks before
    # this module's source profile checks; save/load use the same boundary.
    PRODUCTS.validate_world(engine, WORLD.actor_index(engine))
    WORLD.entity_identity(engine, instance_id, kind='item_instance')
    obj = engine._physical_objects[instance_id]
    WORLD.require_physical_access(obj)
    if obj.get('item_rule_id') != ITEM or PROFILE not in obj:
        raise ValueError('actual source-bound Cleanse Tag required')
    return obj[PROFILE]['level']


# C09-085 / Core1.05 p302: Regularly-Effective Damage is the whole base
# matchup, including a dual-type Ghost. Later ordinary modifiers still apply.
WEAPON = 'cleanse_tag_weapon'
WEAPON_CLAUSE = 'C09-085'


def _weapon_body(engine, instance_id, *, usable=True):
    import optional_weapon_framework as FW
    obj = getattr(engine, '_physical_objects', {}).get(instance_id)
    if not isinstance(obj, dict):raise ValueError('actual physical weapon required')
    if usable:WORLD.require_physical_access(obj)
    if FW.PROFILE in obj:
        FW.object_profile(engine, instance_id, usable=usable)
    else:
        import optional_physical_equipment as OPTIONAL
        uid = obj.get('item_rule_id')
        if uid not in OPTIONAL.KINDS or not OPTIONAL.definition(engine.r, uid).get('weapon_kind'):
            raise ValueError('actual source-observed physical weapon required')
    return obj


def attached_weapon(obj):
    state = obj.get(WEAPON)
    if state and state['current'] is not None:
        return state['observations'][state['current']]['weapon_id']
    return None


def attached_appendage(obj):
    state=obj.get(WEAPON)
    return state['observations'][state['current']]['appendage'] if state and state['current'] is not None else None


def _appendage(engine,actor_id,appendage_id):
    import body_state as BODY
    actor=WORLD.actor_index(engine).get(actor_id)
    if actor is None:raise ValueError('actual appendage bearer required')
    BODY.validate_appendages(actor)
    if appendage_id not in actor.spec.get('observed_appendages',{}):
        raise ValueError('actual observed body appendage required')
    return actor


def prepare_appendage(engine,actor,move,appendage_id=None):
    previous=move.get('_attack_appendage')
    if appendage_id is None and previous is None:return move
    uid=appendage_id if appendage_id is not None else previous['appendage_id']
    _appendage(engine,actor.entity_id,uid)
    if move.get('_weapon_attack') or move.get('class') not in ('물리','특수'):
        raise ValueError('appendage choice requires an actual unarmed attack')
    expected=dict(actor_id=actor.entity_id,appendage_id=uid)
    if previous is not None and previous!=expected:raise ValueError('actual attacking appendage changed')
    return dict(move,_attack_appendage=expected)


def observe_weapon(engine, actor, instance_id, *, event_id, weapon_id=None, appendage=None, reason):
    """Observe actual attachment/removal, without inventing a placement action."""
    import state_grants as G
    WORLD.require_actors(engine, actor)
    _text(event_id);_text(reason)
    PRODUCTS.validate_world(engine, WORLD.actor_index(engine))
    WORLD.entity_identity(engine, instance_id, kind='item_instance')
    obj = engine._physical_objects[instance_id]
    WORLD.require_usable_object(obj)
    if obj.get('item_rule_id') != ITEM or PROFILE not in obj:
        raise ValueError('actual original Cleanse Tag required')
    old = obj.get(WEAPON)
    if old and event_id in old['observations']:
        row=old['observations'][event_id]
        if (row['actor_id'], row['weapon_id'], row['appendage'], row['reason']) != (actor.entity_id, weapon_id, appendage, reason):
            raise ValueError('same weapon attachment observation changed')
        return deepcopy(row)
    current=attached_weapon(obj);part=attached_appendage(obj)
    if current or part:
        if current:
            body=_weapon_body(engine,current)
            if actor.entity_id not in (body.get('owner_id'),body.get('carrier_id'),body.get('equipped_by')):
                raise ValueError('actual weapon holder must remove its attached tag')
        elif actor.entity_id!=part['actor_id']:raise ValueError('actual appendage bearer must remove its tag')
        if weapon_id is not None or appendage is not None:raise ValueError('remove the existing tag attachment first')
    else:
        WORLD.require_physical_access(obj)
        if actor.entity_id not in (obj.get('owner_id'),obj.get('carrier_id'),obj.get('equipped_by')):
            raise ValueError('actual accessible tag required')
        if weapon_id is None and appendage is None:raise ValueError('actual attached tag required for removal')
    if any(obj.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id')):
        raise ValueError('release actual tag equipment and carry before attachment')
    barrier=obj.get(BARRIER)
    if barrier and barrier['observations'][barrier['current']]['attached']:
        raise ValueError('remove the actual surface attachment first')
    if weapon_id is not None:
        if appendage is not None:raise ValueError('one actual attachment target required')
        body=_weapon_body(engine,weapon_id)
        if actor.entity_id not in (body.get('owner_id'),body.get('carrier_id'),body.get('equipped_by')):
            raise ValueError('actual accessible weapon required')
    if appendage is not None:
        if type(appendage) is not dict or set(appendage)!={'actor_id','appendage_id'}:
            raise ValueError('actual appendage bearer and identity required')
        _appendage(engine,**appendage)
    def apply(e,a):
        tag=e._physical_objects[instance_id]
        state=tag.setdefault(WEAPON,dict(source=ITEM,instance_id=instance_id,
            current=None,observations={},use=None))
        row=_seal(dict(event_id=event_id,actor_id=a.entity_id,weapon_id=weapon_id,appendage=deepcopy(appendage),
            reason=reason,at=e.elapsed_seconds,ordinal=len(state['observations'])+1))
        state['observations'][event_id]=row;state['current']=event_id
        WORLD._set_object_location(tag,{'kind':'unknown'})
        e.gm._rec('Cleanse Tag weapon',None,row,reason)
        return deepcopy(row)
    return G.transition(engine,actor,apply)


def observe_appendage(engine,actor,instance_id,bearer,appendage_id,*,event_id,reason):
    WORLD.require_actors(engine,bearer)
    return observe_weapon(engine,actor,instance_id,event_id=event_id,
        appendage=dict(actor_id=bearer.entity_id,appendage_id=appendage_id),reason=reason)


def weapon_effectiveness(engine, attacker, target, move, actual_type, mult, context):
    """Pure native preview; the live weapon producer supplies its actual key."""
    if (target.kind!='pokemon' or '고스트' not in target.types or
            actual_type not in ('노말','격투') or move.get('class') not in ('물리','특수')):
        return mult
    attack=move.get('_weapon_attack');part=move.get('_attack_appendage');weapon_id=None
    if part:
        prepare_appendage(engine,attacker,move)
    else:
        if not attack or attack.get('intrinsic'):return mult
        entry=attacker.custom_conditions.get('equipped_weapons',{}).get(attack.get('key'))
        if not entry or not entry.get('instance_id'):return mult
        weapon_id=entry['instance_id']
    tags=[obj for obj in getattr(engine,'_physical_objects',{}).values()
          if (attached_appendage(obj)==part if part else attached_weapon(obj)==weapon_id)
          and not any(WORLD.physical_lifecycle(obj)[k]
              for k in ('consumed','destroyed'))]
    if not tags:return mult
    if weapon_id:
        import weapon_actions as ACTIONS
        prepared=ACTIONS.prepare(engine,attacker,move,weapon_id)
        if prepared.get('_weapon_attack')!=attack:
            raise ValueError('actual prepared weapon attack required')
        body=_weapon_body(engine,weapon_id)
        if body.get('equipped_by')!=attacker.entity_id:
            raise ValueError('actual equipped weapon holder required')
    definition(engine.r)
    context['cleanse_tag_weapon']=[dict(instance_id=tag['id'],weapon_id=weapon_id,appendage=deepcopy(part),
        attachment=tag[WEAPON]['current'],attacker_id=attacker.entity_id,target_id=target.entity_id,
        move_id=move['id'],actual_type=actual_type) for tag in tags]
    return 1.0


def after_weapon_damage(engine, attacker, target, move, receipt, plans, history_token):
    """Only the live recorded native application can destroy the same tag."""
    if plans is None:return
    for plan in plans:
        _finish_weapon_damage(engine,attacker,target,move,receipt,plan,history_token)


def _finish_weapon_damage(engine,attacker,target,move,receipt,plan,history_token):
    import attack_damage_history as HISTORY
    frame=getattr(engine,'_attack_history_scopes',{}).get(history_token)
    if (frame is None or frame['attacker'] is not attacker or frame['target'] is not target
            or frame['move_id']!=move['id'] or not frame.get('history_recorded')):
        raise ValueError('Cleanse Tag consumption needs actual native damage application')
    row=HISTORY.records(target)[-1]
    if row['receipt']!=receipt or row['attacker_id']!=attacker.entity_id or row['move_type']!=plan['actual_type']:
        raise ValueError('Cleanse Tag damage differs from its actual native receipt')
    if HISTORY.amount(row)<=0:return
    completions=[row for row in getattr(engine,'_move_completions',{}).values()
        if row['actor'] is attacker and row['move_id']==move['id'] and row['phase']=='targets']
    if len(completions)!=1:raise ValueError('actual native Move completion required for Cleanse Tag use')
    obj=engine._physical_objects[plan['instance_id']];state=obj[WEAPON]
    if (attached_weapon(obj)!=plan['weapon_id'] or attached_appendage(obj)!=plan['appendage']
            or state['current']!=plan['attachment']
            or plan['attacker_id']!=attacker.entity_id or plan['target_id']!=target.entity_id
            or plan['move_id']!=move['id']):
        raise ValueError('Cleanse Tag actual attack binding changed')
    WORLD.require_usable_object(obj)
    use=_seal(dict(plan,history_sequence=row['sequence'],at=engine.elapsed_seconds,
        receipt=deepcopy(receipt),completion_id=completions[0]['id']))
    state['use']=use
    WORLD.finish_physical_use(engine,obj,'destroyed',dict(source=ITEM,by_actor_id=attacker.entity_id,
        at=engine.elapsed_seconds,cleanse_weapon_use=deepcopy(use)))


def validate_weapon_tags(engine,index):
    import attack_damage_history as HISTORY
    for uid,obj in getattr(engine,'_physical_objects',{}).items():
        state=obj.get(WEAPON)
        if state is None:continue
        if (PROFILE not in obj or set(state)!={'source','instance_id','current','observations','use'}
                or state['source']!=ITEM or state['instance_id']!=uid or not state['observations']):
            raise ValueError('actual original weapon tag state required')
        ordinals=set()
        for key,row in state['observations'].items():
            _verified(row)
            if (set(row)!={'event_id','actor_id','weapon_id','appendage','reason','at','ordinal','sha256'}
                    or row['event_id']!=key or row['actor_id'] not in index):
                raise ValueError('actual weapon attachment observation required')
            _text(row['reason']);C.integer(row['at'],'attachment time',0,engine.elapsed_seconds)
            C.integer(row['ordinal'],'attachment order',1,len(state['observations']))
            if row['ordinal'] in ordinals:raise ValueError('unique weapon attachment order required')
            ordinals.add(row['ordinal'])
            if row['weapon_id'] is not None:_weapon_body(engine,row['weapon_id'],usable=False)
            if row['appendage'] is not None:
                if row['weapon_id'] is not None:raise ValueError('one actual attachment target required')
                _appendage(engine,**row['appendage'])
        current=state['observations'].get(state['current'])
        if current is None or current['ordinal']!=len(state['observations']):
            raise ValueError('latest actual weapon attachment required')
        use=state['use'];weapon_id=current['weapon_id'];part=current['appendage']
        if use is not None:
            _verified(use)
            if set(use)!={'instance_id','weapon_id','appendage','attachment','attacker_id','target_id','move_id',
                    'actual_type','history_sequence','at','receipt','completion_id','sha256'}:
                raise ValueError('actual weapon damage consumption required')
            target=index.get(use['target_id']);actor=index.get(use['attacker_id'])
            if (target is None or actor is None or target.kind!='pokemon' or use['instance_id']!=uid
                    or use['weapon_id']!=weapon_id or use['appendage']!=part or use['attachment']!=state['current']
                    or use['actual_type'] not in ('노말','격투')):
                raise ValueError('same actual weapon/tag/recipient required')
            HISTORY.validate_actor(target)
            completion=getattr(engine,'_move_completions',{}).get(use['completion_id'])
            if (completion is None or completion['actor'] is not actor or completion['move_id']!=use['move_id']):
                raise ValueError('original native weapon recipient event required')
            original=completion['move']
            if weapon_id:
                original_uid=(original.get('_optional_weapon_framework') or original.get('_optional_crafted_equipment') or {}).get('instance_id')
                if original_uid!=weapon_id:raise ValueError('original native weapon selection changed')
            elif original.get('_attack_appendage')!=part:
                raise ValueError('original native appendage selection changed')
            n=C.integer(use['history_sequence'],'native damage sequence',1,len(HISTORY.records(target)))
            row=HISTORY.records(target)[n-1]
            if (row['attacker_id']!=actor.entity_id or row['move_type']!=use['actual_type']
                    or row['receipt']!=use['receipt'] or row['receipt']['source']!=use['move_id']
                    or row['at']!=use['at'] or HISTORY.amount(row)<=0):
                raise ValueError('original positive native damage receipt required')
            expected=dict(source=ITEM,by_actor_id=actor.entity_id,at=use['at'],cleanse_weapon_use=use)
            if obj.get('destroyed')!=expected:raise ValueError('actual qualifying damage must destroy the same tag')
        elif (weapon_id or part) and not any(WORLD.physical_lifecycle(obj)[k] for k in ('consumed','destroyed')):
            if any(obj.get(k) for k in ('carrier_id','equipped_by','telekinetic_holder_id')):
                raise ValueError('attached tag cannot also be separately held')
            if WORLD.location_of(obj)!={'kind':'unknown'}:
                raise ValueError('attached tag follows its actual weapon location')
    return True


# C09-084. The English source is authoritative for the translation's omitted
# "Phasing through that surface" condition. This is not a radial movement wall.
BARRIER = 'cleanse_tag_barrier'
BARRIER_CLAUSE = 'C09-084'


def _seal(row):
    row['sha256'] = _hash({k: v for k, v in row.items() if k != 'sha256'})
    return row


def _verified(row):
    if type(row) is not dict or row.get('sha256') != _hash({k: v for k, v in row.items() if k != 'sha256'}):
        raise ValueError('Cleanse Tag barrier record changed')


def _wall(value):
    import movement_actions as MOVE
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('actual surface wall segment required')
    a, b = (MOVE._point(x) for x in value)
    if abs(a[0]-b[0])+abs(a[1]-b[1]) != 1:
        raise ValueError('actual cardinal cell-edge surface required')
    return tuple(sorted((a, b)))


def _surface(engine, surface_id, walls, anchor_wall, method, reason, *, current=True):
    _text(surface_id); _text(reason)
    if method not in ('glued', 'taped', 'nailed'):
        raise ValueError('tag must actually be glued, taped or nailed to the surface')
    if current and engine.grid is None:
        raise ValueError('actual mapped surface required')
    if not isinstance(walls, (list, tuple)) or not walls:
        raise ValueError('observed actual surface segments required')
    actual = [_wall(x) for x in walls]; anchor = _wall(anchor_wall)
    if len(set(actual)) != len(actual) or anchor not in actual or current and not set(actual) <= engine.grid.walls:
        raise ValueError('attachment must identify actual existing surface and anchor segment')
    if current and any(not engine.grid.inside(q) for wall in actual for q in wall):
        raise ValueError('actual surface must fit the map')
    return dict(surface_id=surface_id, walls=[list(map(list, x)) for x in sorted(actual)],
                anchor_wall=list(map(list, anchor)), method=method, reason=reason)


def observe_barrier(engine, instance_id, *, event_id, attached=True, surface_id=None,
                    walls=None, anchor_wall=None, method=None, reason):
    """GM observes a real attachment; the source specifies no action cost."""
    import state_grants as G
    _text(event_id); _text(reason)
    if type(attached) is not bool:raise ValueError('explicit attachment state required')
    level(engine, instance_id)
    obj = engine._physical_objects[instance_id]
    if any(obj.get(k) for k in ('carrier_id', 'equipped_by', 'telekinetic_holder_id')):
        raise ValueError('release actual carried/equipped tag before surface attachment')
    data = _surface(engine, surface_id, walls, anchor_wall, method, reason) if attached else None
    if not attached and any(x is not None for x in (surface_id, walls, anchor_wall, method)):
        raise ValueError('removal does not declare a replacement surface')
    old = obj.get(BARRIER)
    if old and event_id in old['observations']:
        row = old['observations'][event_id]
        if (row['attached'], row['surface'], row['reason']) != (attached, data, reason):
            raise ValueError('same attachment observation changed')
        return deepcopy(row)
    if old and any(row['status']=='pending' for row in old['attempts'].values()):
        raise ValueError('resolve the same pending Focus before changing its observed surface')
    def apply(e, actor):
        body = e._physical_objects[instance_id]
        state = body.setdefault(BARRIER, dict(source=ITEM, instance_id=instance_id,
            current=None, observations={}, attempts={}))
        if not attached and (state['current'] is None or not state['observations'][state['current']]['attached']):
            raise ValueError('actual attached tag required for removal')
        row = _seal(dict(event_id=event_id, attached=attached, surface=data,
                         reason=reason, at=e.elapsed_seconds))
        state['observations'][event_id] = row; state['current'] = event_id
        WORLD._set_object_location(body, {'kind': 'grid', 'cell': data['anchor_wall'][0]} if attached else {'kind': 'unknown'})
        e.gm._rec('Cleanse Tag surface', None, row, reason)
        return deepcopy(row)
    return G.transition(engine, None, apply)


def _elapsed(engine, row):
    import elapsed_time as TIME
    return TIME.bounds(engine, row['clock_anchor'], row['unknown_index'], row['elapsed_base'], label='Cleanse retry clock')


def _latest_failure(state, actor_id):
    rows = [r for r in state['attempts'].values() if r['actor_id'] == actor_id and r['status'] == 'failed']
    return max(rows, key=lambda row: row['ordinal']) if rows else None


def observe_retry_elapsed(engine, instance_id, actor, seconds, *, reason):
    """Resolve only the existing failed encroacher's bounded clock uncertainty."""
    import state_grants as G
    WORLD.require_actors(engine, actor); _text(reason)
    PRODUCTS.validate_world(engine, WORLD.actor_index(engine))
    obj = engine._physical_objects.get(instance_id, {})
    row = _latest_failure(obj.get(BARRIER, {'attempts': {}}), actor.entity_id)
    if row is None:raise ValueError('actual failed Cleanse Tag check required')
    lo, hi = _elapsed(engine, row)
    C.integer(seconds, 'observed failed-check elapsed seconds', lo, hi)
    uid = row['attempt_id']
    def apply(e, c):
        target = e._physical_objects[instance_id][BARRIER]['attempts'][uid]
        before = deepcopy(target)
        target.update(clock_anchor=e.elapsed_seconds, unknown_index=len(e.unresolved_time_intervals), elapsed_base=seconds)
        _seal(target); e.gm._rec('Cleanse retry elapsed', before, target, reason, c)
        return [seconds, seconds]
    return G.transition(engine, actor, apply)


def _crosses(engine, actor, destination, surface):
    import body_state as BODY
    from fractions import Fraction
    anchor = _wall(surface['anchor_wall'])
    tag = tuple(Fraction(anchor[0][i]+anchor[1][i], 2) for i in range(2))
    delta = tuple(destination[i]-actor.pos[i] for i in range(2))
    # Historical attachment is not authority to recreate a removed wall.
    walls = {_wall(x) for x in surface['walls']}.intersection(engine.grid.walls)
    return any(max(abs(point[i]-tag[i]) for i in range(2)) <= 30
               for old in BODY.at_position(actor)
               for point in engine.grid.wall_crossings(old, tuple(old[i]+delta[i] for i in range(2)), walls=walls))


def _options_for_attempt(actor, instance_id, attempt_id, options):
    options = deepcopy(options or {})
    if type(options) is not dict or set(options)-{'fixed', 'mods', 'penalty_count', 'fixed_penalties',
            'helper_rank', 'helper_bonus', 'skill_context', 'skill_stunt', 'feature', 'feature_options'}:
        raise ValueError('native Focus options required; caller totals and roll IDs forbidden')
    token = _hash([ITEM, instance_id, actor.entity_id, attempt_id])
    options['roll_id'] = 'cleanse-barrier:' + token + ':focus'
    return options, 'cleanse-barrier:' + token


def phasing_passage(engine, actor, destination, *, checks=None):
    """Public source gate for actual Phasing consumers; does not move or pay.

    checks maps physical tag IDs to {attempt_id, skill_options}. An unresolved
    first check or retry clock returns PendingDecision. Native observations and
    tag destruction are durable before the movement owner's transaction begins.
    """
    import movement_actions as MOVE
    import state_grants as G
    WORLD.require_actors(engine, actor)
    PRODUCTS.validate_world(engine, WORLD.actor_index(engine))
    destination = MOVE._point(destination)
    if engine.grid is None:return C.PendingDecision('actual Phasing surface geometry required')
    names = {MODS.key(str(x).removeprefix('capability/')) for x in G.effective_capabilities(actor)}
    if not {MODS.key(x) for x in ('Phasing', '통과', '페이징')}.intersection(names):
        raise ValueError('actual acquired Phasing capability required')
    if any(BARRIER in obj for obj in getattr(engine, '_physical_objects', {}).values()):definition(engine.r)
    checks = {} if checks is None else checks
    if type(checks) is not dict:raise ValueError('per-tag actual Focus declarations required')
    # Validate input structure before exposing any native die.
    for uid, declaration in checks.items():
        _text(uid)
        if type(declaration) is not dict or set(declaration) != {'attempt_id', 'skill_options'}:
            raise ValueError('identified actual Focus attempt required')
        _text(declaration['attempt_id'])
    for uid, obj in list(getattr(engine, '_physical_objects', {}).items()):
        state = obj.get(BARRIER)
        if state is None or WORLD.physical_lifecycle(obj)['destroyed'] or WORLD.physical_lifecycle(obj)['consumed']:continue
        observation = state['observations'][state['current']]
        if not observation['attached'] or not _crosses(engine, actor, destination, observation['surface']):continue
        previous = _latest_failure(state, actor.entity_id)
        if previous is not None:
            low, high = _elapsed(engine, previous)
            if low < 3600:
                if high >= 3600:return C.PendingDecision('observe actual elapsed time since this encroacher failed against this tag')
                return False
        declaration = checks.get(uid)
        if declaration is None:return C.PendingDecision('actual Focus check required for Cleanse Tag ' + uid)
        attempt_id = declaration['attempt_id']
        options, sequence_id = _options_for_attempt(actor, uid, attempt_id, declaration['skill_options'])
        saved_options = {k: v for k, v in options.items() if k != 'feature_options'}
        intent = dict(actor_id=actor.entity_id, placement=state['current'], origin=list(actor.pos),
                      destination=list(destination), skill_options=saved_options)
        row = state['attempts'].get(attempt_id)
        if row is not None:
            if row['intent'] != intent:raise ValueError('cannot change observed Cleanse Tag passage')
            if row['status'] != 'pending':raise ValueError('completed Focus attempt cannot authorize another passage')
        else:
            pending = [r for r in state['attempts'].values() if r['actor_id'] == actor.entity_id and r['status'] == 'pending']
            if pending:raise ValueError('resume the same pending Cleanse Tag Focus attempt')
            SKILLS.prepared_for_sequence(engine, actor, '집중', options)
            def begin(e, c):
                target = e._physical_objects[uid][BARRIER]
                target['attempts'][attempt_id] = _seal(dict(attempt_id=attempt_id, actor_id=c.entity_id,
                    intent=intent, sequence_id=sequence_id, roll_id=options['roll_id'], level=obj[PROFILE]['level'],
                    ordinal=len(target['attempts'])+1,
                    status='pending', clock_anchor=e.elapsed_seconds, unknown_index=len(e.unresolved_time_intervals), elapsed_base=0))
            G.transition(engine, actor, begin)
        def resolve(rolls):
            def complete(e, c):
                body = e._physical_objects[uid]; attempt = body[BARRIER]['attempts'][attempt_id]
                passed = rolls[0].total > attempt['level']
                attempt.update(status='passed' if passed else 'failed', clock_anchor=e.elapsed_seconds,
                    unknown_index=len(e.unresolved_time_intervals), elapsed_base=0)
                _seal(attempt)
                if passed:
                    WORLD.finish_physical_use(e, body, 'destroyed', dict(source=ITEM, by_actor_id=c.entity_id,
                        at=e.elapsed_seconds, cleanse_attempt_id=attempt_id))
                return passed
            return G.transition(engine, actor, complete)
        passed = SKILLS.sequence(engine, sequence_id, dict(source=ITEM, instance_id=uid, intent_sha256=_hash(intent)),
                                 [(actor, '집중', options)], resolve)
        if not passed:return False
    return True


def validate_barriers(engine, index):
    """Single physical owner reached by native product/world/GM/JSON validation."""
    for uid, obj in getattr(engine, '_physical_objects', {}).items():
        state = obj.get(BARRIER)
        if state is None:continue
        if PROFILE not in obj or set(state) != {'source', 'instance_id', 'current', 'observations', 'attempts'}:
            raise ValueError('actual manufactured barrier tag required')
        if state['source'] != ITEM or state['instance_id'] != uid or state['current'] not in state['observations']:
            raise ValueError('barrier physical/source identity changed')
        for key, observation in state['observations'].items():
            _verified(observation)
            if set(observation) != {'event_id','attached','surface','reason','at','sha256'} or observation['event_id'] != key or type(observation['attached']) is not bool:
                raise ValueError('actual barrier attachment observation required')
            C.integer(observation['at'], 'attachment time', 0, engine.elapsed_seconds)
            _text(observation['reason'])
            surface = observation['surface']
            if observation['attached']:
                if type(surface) is not dict or set(surface) != {'surface_id','walls','anchor_wall','method','reason'}:
                    raise ValueError('original surface observation required')
                if surface != _surface(engine, **surface, current=False):raise ValueError('surface geometry changed')
            elif surface is not None:raise ValueError('removed tag has no surface')
        current = state['observations'][state['current']]
        if current['attached'] and not any(WORLD.physical_lifecycle(obj)[k] for k in ('destroyed', 'consumed')):
            if any(obj.get(k) for k in ('carrier_id', 'equipped_by', 'telekinetic_holder_id')) or WORLD.location_of(obj) != {'kind': 'grid', 'cell': tuple(current['surface']['anchor_wall'][0])}:
                raise ValueError('attached tag must remain on its actual observed surface')
        passed = []; ordinals = set()
        for key, attempt in state['attempts'].items():
            _verified(attempt); intent = attempt['intent']; actor = index.get(attempt['actor_id'])
            if set(attempt) != {'attempt_id','actor_id','intent','sequence_id','roll_id','level','ordinal','status','clock_anchor','unknown_index','elapsed_base','sha256'}:
                raise ValueError('original barrier attempt fields required')
            C.integer(attempt['ordinal'], 'original Focus order', 1, len(state['attempts']))
            if attempt['ordinal'] in ordinals:raise ValueError('unique original Focus order required')
            ordinals.add(attempt['ordinal'])
            if actor is None or attempt['attempt_id'] != key or intent['actor_id'] != actor.entity_id or intent['placement'] not in state['observations']:
                raise ValueError('actual tag encroacher and original attachment required')
            if attempt['status'] not in ('pending', 'failed', 'passed') or attempt['level'] != obj[PROFILE]['level']:
                raise ValueError('original tag level and Focus lifecycle required')
            _elapsed(engine, attempt)
            options = intent['skill_options']; supplied = {k: v for k, v in options.items() if k != 'roll_id'}
            expected, sequence_id = _options_for_attempt(actor, uid, key, supplied)
            if expected != options or attempt['roll_id'] != options['roll_id'] or attempt['sequence_id'] != sequence_id:
                raise ValueError('original native Focus identity required')
            event = SKILLS.event(engine, actor, attempt['roll_id'])
            run = getattr(engine, '_skill_sequences', {}).get(sequence_id)
            if event is not None:
                if (event.skill != MODS.skill_id(engine.r.skill_policy, '집중') or event.request != SKILLS._request(engine, actor, '집중', options)
                        or run is None or run['basis'] != dict(source=ITEM, instance_id=uid, intent_sha256=_hash(intent))
                        or run['requests'] != ((actor, event.request, options.get('feature'), attempt['roll_id']),)):
                    raise ValueError('actual original native Focus event required')
            if attempt['status'] != 'pending':
                if event is None or event.state != 'final' or (event.final.total > attempt['level']) != (attempt['status'] == 'passed'):
                    raise ValueError('barrier result differs from actual final native Focus')
            if attempt['status'] == 'passed':passed.append(attempt)
        if passed:
            if len(passed) != 1:raise ValueError('one same tag is destroyed only once')
            attempt = passed[0]
            expected = dict(source=ITEM, by_actor_id=attempt['actor_id'], at=attempt['clock_anchor'], cleanse_attempt_id=attempt['attempt_id'])
            if obj.get('destroyed') != expected:raise ValueError('successful Focus must destroy the same physical tag')

