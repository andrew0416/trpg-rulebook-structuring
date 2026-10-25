"""Explicit world identity, relation and location contracts.

Identifiers and observation records are modelling conventions. They neither
certify legal character generation nor confer action permission. Core actor,
physical-object and item-instance integrity is checked here; optional vehicle,
Pokebot, augmentation and rune mechanics retain separate unresolved contracts.
"""
from copy import deepcopy
from dataclasses import fields
from math import isfinite
import state_fields as F


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' must be nonempty text')
    return value


def actor_id(actor):
    value = _text(actor.spec.get('id'), 'actor identity')
    if getattr(actor, 'entity_id', value) != value:
        raise ValueError('actor identity disagrees with its permanent identity')
    return value


def actors(engine, extra=()):
    """Traverse actual state references, including off-field/delayed actors.

    Historical snapshots are deliberately not members of the current world.
    Repeated references to one actor are fine; distinct actors sharing an ID
    are checked separately by actor_index.
    """
    from state_codec import native_data_types, native_batch_type, _types
    pure_records = native_data_types();batch_type=native_batch_type();actor_type=_types()[1]
    found = {}; seen = set()
    scalar_types = (str, int, float, bool, bytes, type(None))
    def visit(value):
        key = id(value)
        if key in seen:
            return
        seen.add(key)
        if type(value) is actor_type:
            found[key] = value
            for field, child in vars(value).items():
                if field != 'r' and type(child) not in scalar_types:
                    visit(child)
        elif type(value) is batch_type:
            visit(value.outcomes)
        elif type(value) in pure_records:
            for field in fields(value):
                visit(getattr(value, field.name))
        elif isinstance(value, dict):
            for k, v in value.items():
                if type(k) not in scalar_types:visit(k)
                if type(v) not in scalar_types:visit(v)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for child in value:
                if type(child) not in scalar_types:visit(child)
    visit(getattr(getattr(engine, 'gm', None), 'everyone', []))
    for field, value in vars(engine).items():
        if field not in ('r', 'gm', 'rulings', 'rng'):
            visit(value)
    visit(extra)
    return tuple(found.values())


def actor_index(engine, extra=()):
    result = {}
    for actor in actors(engine, extra):
        uid = actor_id(actor)
        if uid in getattr(engine, '_partial_entities', {}):
            raise ValueError('complete actor collides with a partial entity; materialization must explicitly replace that record')
        if uid in result and result[uid] is not actor:
            raise ValueError('distinct actors share identity: ' + uid)
        result[uid] = actor
    return result


def require_actors(engine, *subjects):
    """Require live world members using this engine's selected rules.

    Transaction participants and historical/caller-owned sheets do not register
    an actor. Off-field actors reached through live world state remain valid.
    """
    index=actor_index(engine)
    for subject in subjects:
        if getattr(subject,'r',None) is not engine.r or index.get(getattr(subject,'entity_id',None)) is not subject:
            raise ValueError('execution requires actual registered actor/target')
    return index


def identity_field(engine, subject, field, *, index=None):
    """Read actual actor identity/relations without granting ownership or actions."""
    index = require_actors(engine, subject) if index is None else index
    if getattr(subject, 'r', None) is not engine.r or index.get(actor_id(subject)) is not subject:
        raise ValueError('actual registered actor required')
    if field in ('entity_id', 'kind'):
        return actor_id(subject) if field == 'entity_id' else subject.kind
    if field == 'owner_id':
        owner=subject.spec.get('trainer_id')
        if owner is not None:
            if type(owner) is not str or not owner.strip():
                raise ValueError('owner identity must be nonempty text')
            resolved=index.get(owner)
            if resolved is None or resolved.kind!='trainer' or resolved.r is not engine.r:
                raise ValueError('owner must resolve to an actual trainer in this world')
        # Missing ownership is unknown, not the current actor or controller.
        return owner
    if field in ('controller_kind', 'controller_id'):
        control=subject.spec.get('controller')
        if control is None:
            return None
        if type(control) is not dict or control.get('kind') not in ('gm','player','actor','pending'):
            raise ValueError('invalid controller relation')
        kind=control['kind'];identity=control.get('id')
        if kind!='gm' and (type(identity) is not str or not identity.strip()):
            raise ValueError('controller identity must be nonempty text')
        if kind=='actor':
            resolved=index.get(identity)
            if resolved is None or resolved.r is not engine.r:
                raise ValueError('controller must resolve to an actual actor in this world')
        # Pending identifiers name unresolved choices, never an authority.
        # A GM controller has a known kind, but no required actor/player ID.
        return kind if field=='controller_kind' else identity if kind in ('actor','player') else None
    raise ValueError('unsupported identity field')


def actor_identity(engine, identity):
    """Resolve an existing actor ID to read-only identity facts, never register it."""
    identity = _text(identity, 'actor identity')
    index = actor_index(engine)
    subject = index.get(identity)
    if subject is None:
        raise ValueError('unknown actor identity: ' + identity)
    return {field: identity_field(engine, subject, field, index=index)
            for field in ('entity_id', 'kind', 'owner_id', 'controller_kind', 'controller_id')}


def entity_index(engine, extra=()):
    """Index existing native stores without creating entities or action rights."""
    import pokemon_entities as P
    index = actor_index(engine, extra=extra)
    def add(uid, value):
        _text(uid, 'entity identity')
        if uid in index:
            raise ValueError('entity identity collides across native stores: ' + uid)
        index[uid] = value
    for store, key in (('_physical_objects', 'id'), ('_partial_entities', 'entity_id')):
        registry = getattr(engine, store, {})
        if type(registry) is not dict:
            raise ValueError('entity registry must be a mapping')
        for uid, row in registry.items():
            if type(row) is not dict or row.get(key) != uid:
                raise ValueError('entity registry key disagrees with record identity')
            _text(row.get('kind'), 'entity kind')
            add(uid, row)
    for registry in (P.egg_index(engine), P.fossil_index(engine)):
        for uid, (_, row) in registry.items():
            add(uid, row)
    return index


def entity_identity(engine, identity, *, kind=None):
    """Detached identity facts, including actual composition references.

    Known identity is not an executable-rule admission or a complete sheet.
    Missing ownership/control remains unknown. Partial bodies stay partial.
    """
    identity = _text(identity, 'entity identity')
    index = entity_index(engine)
    if identity not in index:
        raise ValueError('unknown entity identity: ' + identity)
    subject = index[identity]
    if not isinstance(subject, dict):
        result = actor_identity(engine, identity)
    else:
        entity_kind = _text(subject.get('kind'), 'entity kind')
        result = {'entity_id': identity, 'kind': entity_kind,
                  'owner_id': subject.get('owner_id'),
                  'controller_kind': 'actor' if subject.get('controller_id') is not None else None,
                  'controller_id': subject.get('controller_id')}
        for key in ('owner_id', 'controller_id'):
            uid = result[key]
            if uid is not None:
                _text(uid, key)
                related = index.get(uid)
                if related is None or isinstance(related, dict) or getattr(related, 'r', None) is not engine.r:
                    raise ValueError(key + ' must resolve to an actual actor')
    if kind is not None and result['kind'] != _text(kind, 'required kind'):
        raise ValueError('entity kind does not match declaration')
    def component_ids(row):
        if not isinstance(row, dict):
            return []
        refs = []
        for field in ('components', 'installations', 'section_ids'):
            values = row.get(field, [])
            if type(values) is not list:
                raise ValueError('composition references must be lists')
            for value in values:
                if field == 'section_ids':
                    uid = value
                else:
                    if type(value) is not dict:
                        raise ValueError('component instance record required')
                    uid = value.get('instance_id')
                _text(uid, 'component identity')
                if uid not in index:
                    raise ValueError('component must resolve to a distinct actual entity')
                refs.append(uid)
        if len(set(refs)) != len(refs):
            raise ValueError('duplicate component identity')
        return refs
    visited = set()
    def validate_composition(uid, ancestors):
        if uid in ancestors:
            raise ValueError('composition cannot contain a cycle')
        if uid in visited:
            return
        for child in component_ids(index[uid]):
            validate_composition(child, ancestors | {uid})
        visited.add(uid)
    validate_composition(identity, set())
    components = component_ids(subject)
    parent = subject.get('parent_id') if isinstance(subject, dict) else None
    if parent is not None and (parent == identity or parent not in index
            or isinstance(index[parent], dict) and index[parent].get('kind') == 'weak_part'):
        raise ValueError('weak part parent must resolve to an actual body')
    children = sorted(uid for uid, row in index.items()
                      if isinstance(row, dict) and row.get('kind') == 'weak_part'
                      and row.get('parent_id') == identity)
    result.update(parent_id=parent, component_ids=components, weak_part_ids=children)
    if getattr(engine, '_physical_objects', {}).get(identity) is subject:
        result.update(physical_lifecycle(subject))
    return deepcopy(result)


def mount_relation(index, rider, *, proposed_mount_id=None):
    """Validate actual mount references without inventing capacity or movement."""
    uid=actor_id(rider)
    if index.get(uid) is not rider:
        raise ValueError('mounted rider must be an actual registered actor')
    current=proposed_mount_id if proposed_mount_id is not None else rider.spec.get('mount_id')
    seen={uid};first=None
    while current is not None:
        _text(current,'mount identity')
        if current in seen:
            raise ValueError('mount relation cannot contain self-mounting or a cycle')
        seen.add(current)
        mount=index.get(current)
        if mount is None or mount.kind!='pokemon':
            raise ValueError('mount relation must resolve to an actual Pokemon')
        if first is None:first=mount
        current=mount.spec.get('mount_id')
    return first


def require_mount_target(engine, rider, target):
    index=actor_index(engine)
    if index.get(actor_id(target)) is not target:
        raise ValueError('mount target must be the actual registered Pokemon')
    mount_relation(index,rider,proposed_mount_id=actor_id(target))
    return target


def validate_mount_relations(engine, index=None):
    index=actor_index(engine) if index is None else index
    import keystone_state as K
    K.validate_world(engine,index)
    import telekinetic_load as TK
    TK.validate_world(engine,index)
    for rider in index.values():mount_relation(index,rider)


def location_of(entity):
    """No implicit origin: absence of known coordinates is unknown."""
    if isinstance(entity, dict):
        if 'location' in entity:
            return F.location(entity['location'])
        position = entity.get('pos')
    else:
        state = vars(entity)
        if 'location' in state:
            return F.location(state['location'])
        position = state.get('pos')
    return F.location({'kind':'grid', 'cell':position}) if position is not None else {'kind':'unknown'}


def grid_cell(entity):
    loc = location_of(entity)
    if loc['kind'] != 'grid':
        raise ValueError('concrete grid location is not established')
    return loc['cell']


def distance_known(left, right):
    a, b = location_of(left), location_of(right)
    if a['kind'] != 'grid' or b['kind'] != 'grid':
        return None
    if a.get('map_id') != b.get('map_id'):
        return None
    return max(abs(a['cell'][i]-b['cell'][i]) for i in (0, 1))


def _fact(reason, source):
    return {'reason':_text(reason, 'GM observed fact reason'), 'source':_text(source, 'observed fact source')}


def _set_object_location(row, location):
    row['location'] = F.location(location)
    if row['location']['kind'] == 'grid':
        row['pos'] = row['location']['cell']
    else:
        row.pop('pos', None)


def observe_location(engine, entity, location, *, reason, source='gm/observation'):
    proposed = F.location(location); fact = _fact(reason, source)
    if proposed['kind'] == 'grid' and getattr(engine, 'grid', None) is not None:
        if not engine.grid.inside(proposed['cell']):
            raise ValueError('observed position is outside the current grid')
    if isinstance(entity, dict):
        import physical_planter as PHYSICAL_PLANTER
        if PHYSICAL_PLANTER.contained(entity):raise ValueError('remove the actual plant from its Portable Grower before separate placement')
        uid = _text(entity.get('id'), 'object identity')
        if getattr(engine, '_physical_objects', {}).get(uid) is not entity:
            raise ValueError('actual registered physical object required')
        if entity.get('carrier_id') or entity.get('equipped_by'):
            raise ValueError('release the carried object before assigning a ground location')
        before = location_of(entity); _set_object_location(entity, proposed)
        entity['provenance'] = fact
    else:
        uid = actor_id(entity); actor_index(engine, [entity])
        import marsupial_state as MARSUPIAL
        if MARSUPIAL.in_pouch(entity):
            raise ValueError('native pouch baby cannot be placed apart from its actual mother')
        before = location_of(entity); entity.location = proposed
        entity.__dict__['_location_provenance'] = fact
    engine.gm._rec('location '+uid, before, proposed, reason)
    if not isinstance(entity,dict):
        import body_modes as BODY_MODES
        BODY_MODES.sync_shadows(engine)
        import marsupial_state as MARSUPIAL
        MARSUPIAL.sync(engine)
    return deepcopy(proposed)


def register_object(engine, object_id, *, location, reason, weight_kg=None,
                    kind='physical_object', item_rule_id=None, owner_id=None,
                    source='gm/observation'):
    """Record a real instance; does not acquire or spend an inventory item."""
    uid = _text(object_id, 'object identity'); fact = _fact(reason, source)
    if kind not in ('physical_object', 'item_instance'):
        raise ValueError('this adapter supports physical objects and item instances only')
    index = actor_index(engine)
    entities = entity_index(engine)
    physical = getattr(engine, '_physical_objects', {})
    if uid in entities and uid not in physical or any(uid in actor.spec.get('pokemon_registry',{}) for actor in index.values()):
        raise ValueError('object identity collides with another entity or reserve Pokemon identity')
    if owner_id is not None and owner_id not in index:
        raise ValueError('object owner identity must resolve')
    if kind == 'item_instance':
        _text(item_rule_id, 'item rule identity')
        catalog = {**getattr(engine.r, 'items_mech', {}), **getattr(engine.r, 'items_llm', {}), **getattr(engine.r, 'items_reviewed', {})}
        if item_rule_id not in catalog:
            raise ValueError('item instance requires an actual item rule identity')
    elif item_rule_id is not None:
        raise ValueError('item rule identity requires item_instance kind')
    if weight_kg is not None and (type(weight_kg) not in (int, float) or not isfinite(weight_kg) or weight_kg < 0):
        raise ValueError('object weight must be finite and nonnegative')
    loc = F.location(location)
    if loc['kind'] == 'grid' and getattr(engine, 'grid', None) is not None and not engine.grid.inside(loc['cell']):
        raise ValueError('object is outside the current grid')
    registry = getattr(engine, '_physical_objects', {})
    old = registry.get(uid)
    if old is not None:
        import physical_planter as PHYSICAL_PLANTER
        if PHYSICAL_PLANTER.contained(old):raise ValueError('remove the actual plant from its Portable Grower before separate registration')
        if old.get('carrier_id') or old.get('equipped_by') or old.get('telekinetic_holder_id'):
            raise ValueError('object is currently carried; use an explicit release observation')
        if old.get('kind', 'physical_object') != kind or old.get('item_rule_id') != item_rule_id:
            raise ValueError('existing identity cannot change its physical instance kind or rule')
    row = deepcopy(old) if old is not None else {'id':uid, 'kind':kind}
    row.update(kind=kind, reason=reason, provenance=fact)
    if owner_id is not None:
        row['owner_id'] = owner_id
    if weight_kg is not None:
        row['weight_kg'] = weight_kg
    if item_rule_id is not None:
        row['item_rule_id'] = item_rule_id
    _set_object_location(row, loc)
    before = deepcopy(old)
    target = engine.__dict__.setdefault('_physical_objects', {}).setdefault(uid, {})
    target.clear(); target.update(row)
    engine.gm._rec('object '+uid, before, target, reason)
    return deepcopy(target)


def physical_lifecycle(obj):
    """Preserve independent terminal, disabled and suppressed state meanings."""
    if type(obj) is not dict:
        raise ValueError('physical object record required')
    def flag(name):
        if name not in obj:
            return False
        value = obj[name]
        if type(value) is bool:
            return value
        if type(value) is dict:
            return True
        raise ValueError('lifecycle state must be a boolean or evidence record: ' + name)
    result = {key:flag(key) for key in ('consumed','destroyed','disabled','suppressed')}
    if result['consumed'] and result['destroyed']:
        raise ValueError('consumption and destruction are distinct terminal events')
    return result


def require_present_object(obj):
    if physical_lifecycle(obj)['consumed']:
        raise ValueError('consumed physical object is no longer present')


def require_usable_object(obj):
    require_present_object(obj)
    if physical_lifecycle(obj)['destroyed']:
        raise ValueError('destroyed physical object is not usable')


def finish_physical_use(engine, obj, terminal, evidence):
    """Finalize an admitted native consumption/destruction inside its transaction.

    Native callers release equipment, load and effect registrations first.
    This does not confer permission to consume or destroy an arbitrary object.
    """
    uid = _text(obj.get('id'), 'physical identity')
    if getattr(engine, '_physical_objects', {}).get(uid) is not obj:
        raise ValueError('actual registered physical object required')
    require_usable_object(obj)
    if terminal not in ('consumed','destroyed') or type(evidence) is not dict:
        raise ValueError('explicit consumed/destroyed evidence required')
    _text(evidence.get('source'), 'terminal source')
    actor_key = 'by_actor_id' if terminal == 'consumed' or 'by_actor_id' in evidence else 'former_holder_id'
    if evidence.get(actor_key) not in actor_index(engine):
        raise ValueError('terminal event must identify an actual actor')
    if obj.get('equipped_by') or obj.get('telekinetic_holder_id'):
        raise ValueError('release active equipment and remote hold before terminal event')
    if terminal == 'consumed':
        if obj.get('carrier_id'):
            raise ValueError('release carried relation before consumption')
        if evidence['source'] != obj.get('item_rule_id'):
            raise ValueError('consumption source must match the actual item')
        if type(evidence.get('at')) is not int or evidence['at'] < 0:
            raise ValueError('consumption requires actual elapsed time')
        if obj.get('item_contents', {}).get('current') is not None:
            raise ValueError('loaded body cannot be consumed with active contents')
    import physical_incubator as INCUBATOR
    INCUBATOR.finish_body(engine,obj,actor_id=evidence[actor_key],reason='actual body '+terminal)
    obj[terminal] = deepcopy(evidence)
    __import__('telekinetic').sync_barrier(engine,obj)
    if terminal == 'consumed':
        _set_object_location(obj, {'kind':'unknown'})
    return deepcopy(obj[terminal])


def require_physical_access(obj):
    require_usable_object(obj)
    import cleanse_tags as CLEANSE
    if CLEANSE.attached_weapon(obj) or CLEANSE.attached_appendage(obj):
        raise ValueError('remove the actual weapon attachment before separate item access')
    if obj.get('telekinetic_holder_id'):
        raise ValueError('remote-held object requires explicit release and physical possession before equipment or consumption')


def prepare_carried(engine, actor, objects, reason):
    """Build a complete registry replacement without touching live state."""
    owner = actor_id(actor); index = actor_index(engine, [actor]); fact = _fact(reason, 'gm/observed-carry')
    entities = entity_index(engine, extra=(actor,))
    proposed = deepcopy(getattr(engine, '_physical_objects', {}))
    selected = {item['id'] for item in objects}
    for uid, row in proposed.items():
        if row.get('telekinetic_holder_id') == owner:
            row.pop('telekinetic_holder_id')
            _set_object_location(row, {'kind':'unknown'})
            row['provenance'] = dict(fact,detail='Remote hold released; landing not observed.')
        if row.get('carrier_id') == owner and uid not in selected:
            row.pop('carrier_id'); _set_object_location(row, {'kind':'unknown'})
            row['provenance'] = dict(fact, detail='Release observed; final ground position not supplied.')
    for item in objects:
        uid = _text(item['id'], 'object identity')
        import physical_planter as PHYSICAL_PLANTER
        if PHYSICAL_PLANTER.contained(getattr(engine,'_physical_objects',{}).get(uid)):
            raise ValueError('remove the actual plant from its Portable Grower before separate carrying')
        if uid in entities and uid not in getattr(engine, '_physical_objects', {}):
            raise ValueError('carried object identity collides with an actor')
        for other in index.values():
            if other is not actor and any(x.get('id') == uid for x in other.spec.get('_carried_load', {}).get('objects', [])):
                raise ValueError('the same physical object is already carried by another actor')
        row = proposed.setdefault(uid, {'id':uid, 'kind':'physical_object'})
        require_present_object(row)
        if row.get('carrier_id') not in (None, owner) or row.get('equipped_by') not in (None,owner):
            raise ValueError('object is physically held by another actor')
        row.update(weight_kg=item['weight_kg'], carrier_id=owner, provenance=fact, reason=reason)
        # Relative placement follows the carrier; no stale independent grid cell.
        _set_object_location(row, {'kind':'unknown'})
    return proposed


def commit_objects(engine, proposed):
    """Commit a prevalidated registry while retaining every existing instance."""
    registry = engine.__dict__.setdefault('_physical_objects', {})
    if not set(registry) <= set(proposed):
        raise ValueError('physical object deletion requires an explicit lifecycle adapter')
    # This stage has no further domain validation or callbacks: preparation is
    # complete before any live dictionary is changed.
    for uid, row in proposed.items():
        target = registry.setdefault(uid, {})
        if target is row:continue
        target.clear(); target.update(row)


def effective_location(engine, entity):
    import physical_planter as PHYSICAL_PLANTER
    if PHYSICAL_PLANTER.contained(entity):return PHYSICAL_PLANTER.location(engine,entity)
    if isinstance(entity,dict) and entity.get('kind')=='egg':
        import physical_incubator as INCUBATOR
        return INCUBATOR.location(engine,entity)
    if not isinstance(entity,dict):
        import marsupial_state as MARSUPIAL
        if MARSUPIAL.in_pouch(entity):
            mother=actor_index(engine).get(entity.spec[MARSUPIAL.KEY]['mother_id'])
            if mother is None:raise ValueError('actual maternal pouch host required')
            return location_of(mother)
    if isinstance(entity,dict):
        import cleanse_tags as CLEANSE
        weapon_id=CLEANSE.attached_weapon(entity)
        if weapon_id and not any(physical_lifecycle(entity)[k] for k in ('consumed','destroyed')):
            weapon=getattr(engine,'_physical_objects',{}).get(weapon_id)
            if weapon is None:raise ValueError('attached tag weapon is missing')
            return effective_location(engine,weapon)
        part=CLEANSE.attached_appendage(entity)
        if part and not any(physical_lifecycle(entity)[k] for k in ('consumed','destroyed')):
            bearer=actor_index(engine).get(part['actor_id'])
            if bearer is None:raise ValueError('attached tag appendage bearer is missing')
            return location_of(bearer)
    if isinstance(entity, dict) and (entity.get('carrier_id') or entity.get('equipped_by')):
        if entity.get('carrier_id') and entity.get('equipped_by') and entity['carrier_id']!=entity['equipped_by']:raise ValueError('object carrier and equipment holder disagree')
        carrier = actor_index(engine).get(entity.get('carrier_id') or entity['equipped_by'])
        if carrier is None:
            raise ValueError('object carrier is missing')
        return location_of(carrier)
    return location_of(entity)


def set_controller(engine, actor, controller, *, reason, source='gm/control'):
    """Authority observation only; never changes ownership, side, or turn grants."""
    fact = _fact(reason, source); index = actor_index(engine, [actor])
    if not isinstance(controller, dict) or controller.get('kind') not in ('gm', 'player', 'actor', 'pending'):
        raise ValueError('controller must be gm, player, actor or pending')
    proposed = deepcopy(controller)
    if proposed['kind'] != 'gm':
        _text(proposed.get('id'), 'controller identity')
    if proposed['kind'] == 'actor' and proposed['id'] not in index:
        raise ValueError('controlling actor identity must resolve')
    proposed['provenance'] = fact
    before = deepcopy(actor.spec.get('controller')); actor.spec['controller'] = proposed
    engine.gm._rec('controller', before, proposed, reason, actor)
    return deepcopy(proposed)


def validate_world(engine):
    """Return integrity findings, never a rulebook/category completion claim."""
    issues = []; index = {}; roster = actors(engine)
    def issue(code, entity, message):
        issues.append({'code':code, 'entity_id':entity, 'message':message})
    try:
        import body_state as BODY
        BODY.validate_passages(engine)
    except (ValueError,KeyError,TypeError) as exc:
        issue('body_passage',None,str(exc))
    for actor in roster:
        try:
            uid = actor_id(actor)
        except ValueError as exc:
            issue('actor_identity', actor.spec.get('id'), str(exc)); continue
        if uid in index and index[uid] is not actor:
            issue('duplicate_actor_id', uid, 'Distinct actual actors share identity.')
        index[uid] = actor
        try:
            import grant_payments as PAYMENTS
            PAYMENTS.validate(actor)
            import trainer_xp_payments as XP_PAYMENTS
            XP_PAYMENTS.validate(actor)
            import counter_effects as COUNTERS
            COUNTERS.validate(actor)
        except ValueError as exc:
            issue('grant_payment',uid,str(exc))
        try:
            import trainer_entitlements as ENTITLEMENTS
            ENTITLEMENTS.validate(actor)
            import trainer_milestone_rewards as REWARDS
            REWARDS.validate(actor)
        except ValueError as exc:
            issue('trainer_entitlement',uid,str(exc))
        try:
            F.validate_actor(actor)
        except ValueError as exc:
            issue('actor_state', uid, str(exc))
        try:
            location_of(actor)
        except ValueError as exc:
            issue('actor_location', uid, str(exc))
    try:
        import mapless_space as MAPLESS
        MAPLESS.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('mapless_space',None,str(exc))
    try:
        import environmental_item_state as ENVIRONMENTAL_ITEMS
        ENVIRONMENTAL_ITEMS.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('environmental_item_state',None,str(exc))
    try:
        import herb_mushroom_rules as HERB
        HERB.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('herb_mushroom_state',None,str(exc))
    try:
        import pokedex_device as POKEDEX
        POKEDEX.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('pokedex_device',None,str(exc))
    try:
        import physical_object_attacks as PHYSICAL_ATTACKS
        import physical_tool_attacks as PHYSICAL_TOOLS
        import physical_combustion as PHYSICAL_COMBUSTION
        PHYSICAL_COMBUSTION.validate_world(engine)
        PHYSICAL_TOOLS.validate_world(engine)
        PHYSICAL_ATTACKS.validate_world(engine,index)
        import pass_moves as PASS_MOVES
        PASS_MOVES.validate_world(engine,index)
        import conquerors_march as MARCH
        MARCH.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('physical_object_attack',None,str(exc))
    try:
        import aura_pulse as PULSE
        PULSE.validate_world(engine,index)
        import capability_products as PRODUCTS
        PRODUCTS.validate_world(engine,index)
        import crafting_products as CRAFTED
        CRAFTED.validate_world(engine,index)
        import cultivation_growth as GROWTH
        GROWTH.validate_world(engine,index)
    except ValueError as exc:
        issue('aura_pulse_relation',None,str(exc))
    try:
        import cleanse_tag_burn as CLEANSE_BURN
        CLEANSE_BURN.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('cleanse_tag_burn',None,str(exc))
    try:
        import keystone_state as K
        K.validate_world(engine,index)
    except ValueError as exc:
        issue('keystone_relation',None,str(exc))
    try:
        import perception_observe as OBSERVE
        OBSERVE.validate_world(engine,index)
    except ValueError as exc:
        issue('sensory_environment',None,str(exc))
    try:
        import perception_communicate as COMM
        COMM.validate_world(engine,index)
        __import__('channeler').validate_world(engine,index)
    except ValueError as exc:
        issue('communication',None,str(exc))
    for rider in index.values():
        try:mount_relation(index,rider)
        except ValueError as exc:issue('mount_relation',rider.entity_id,str(exc))
    try:
        import control_mount as MOUNT
        MOUNT.validate_world(engine,index)
    except ValueError as exc:
        issue('mount_contract',None,str(exc))
    try:
        import control_vehicle as CONTROL
        CONTROL.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('machine_operation',None,str(exc))
    try:
        import control_remote as REMOTE
        REMOTE.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('remote_control',None,str(exc))
    try:
        import network_connection as NETWORK
        NETWORK.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('network_connection',None,str(exc))
    try:
        import network_integrity as INTEGRITY
        INTEGRITY.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('digital_integrity',None,str(exc))
    try:
        import repair_restore as REPAIR
        REPAIR.validate_world(engine,index)
        import missed_ball_body as BALL_BODY
        BALL_BODY.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('object_repairs',None,str(exc))
    try:
        import repair_breach as BREACH
        BREACH.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('vehicle_breaches',None,str(exc))
    try:
        import scene_lighting as LIGHT
        LIGHT.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('scene_lighting',None,str(exc))
    try:
        import environment_derive as ED
        ED.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('environment_derive',None,str(exc))
    try:
        import environment_change as EC
        EC.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('environment_changes',None,str(exc))
    try:
        import field_effects as FIELD
        FIELD.validate(engine)
        FIELD.validate_local(engine,index)
        FIELD.validate_pending_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('local_grass_field',None,str(exc))
    try:
        import grapple_state as GRAPPLE
        GRAPPLE.validate_world(engine,index)
        import map_terrain as TERRAIN
        TERRAIN.validate(engine.grid)
        import burrow_tunnels as TUNNELS
        TUNNELS.validate(engine)
        import party_actions as PARTY_ACTIONS
        PARTY_ACTIONS.validate_world(engine,index)
        import move_completion as COMPLETE
        COMPLETE.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('grapple_state',None,str(exc))
    try:
        import effect_lifetimes as LIFETIMES
        LIFETIMES.validate_type_world(engine,index)
        import ability_transitions as ABILITY_TRANSITIONS
        ABILITY_TRANSITIONS.validate_world(engine,index)
        import reactive_ability_events as REACTIVE
        REACTIVE.validate_world(engine,index)
        import move_defense_reactions as DEFENSE
        DEFENSE.validate_world(engine,index)
        import ability_interrupt_choices as ABILITY_INTERRUPTS, tera_shell as TERA_SHELL
        ABILITY_INTERRUPTS.validate_world(engine,index)
        TERA_SHELL.validate_world(engine,index)
        import ability_reaction_choices as ABILITY_REACTIONS, perish_body as PERISH_BODY
        ABILITY_REACTIONS.validate_world(engine,index)
        PERISH_BODY.validate_world(engine,index)
        import move_activation as ACTIVATION
        ACTIVATION.validate_continuations(engine,index)
        __import__('training_features').validate_core_payments(engine,index)
        __import__('commander').validate_world(engine,index)
        __import__('focused_command').validate_world(engine,index)
        __import__('commander_orders').validate_world(engine,index)
    except ValueError as exc:
        issue('timed_type_contract',None,str(exc))
    try:
        import ability_state_projection as ABILITY_STATE_PROJECTION
        ABILITY_STATE_PROJECTION.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('ability_state_projection',None,str(exc))
    try:
        import initiative_derivation as INITIATIVE
        INITIATIVE.validate_world(engine,index)
    except ValueError as exc:
        issue('initiative_contract',None,str(exc))
    try:
        import initiative_schedule as SCHEDULE
        SCHEDULE.validate_world(engine,index)
        import initiative_interrupts as INTERRUPTS
        INTERRUPTS.validate_world(engine,index)
    except ValueError as exc:
        issue('initiative_schedule_contract',None,str(exc))
    try:
        import mega_forms as MEGA
        MEGA.validate_world(engine,index)
    except ValueError as exc:
        issue('mega_form_contract',None,str(exc))
    try:
        import rest_intervals as REST
        REST.validate_world(engine,index)
    except ValueError as exc:
        issue('rest_interval',None,str(exc))
    try:
        import activity_jobs as JOBS
        JOBS.validate_world(engine,index)
    except ValueError as exc:
        issue('activity_job_contract',None,str(exc))
    try:
        import training_rewards as TRAINING_REWARDS
        TRAINING_REWARDS.validate_world(engine,index)
    except ValueError as exc:
        issue('training_reward_contract',None,str(exc))
    try:
        import injury_recovery as INJURY
        INJURY.validate_world(engine,index)
    except ValueError as exc:
        issue('injury_recovery_clock',None,str(exc))
    try:
        import environmental_effects as ENVIRONMENT
        ENVIRONMENT.validate_world(engine,index)
    except ValueError as exc:
        issue('respiration_state',None,str(exc))
    try:
        import vitamin_capacity as VITAMIN_CAPACITY
        VITAMIN_CAPACITY.validate_world(engine,index)
    except ValueError as exc:
        issue('vitamin_capacity_source',None,str(exc))
    try:
        import combat_state_lifecycle as COMBAT_STATE
        COMBAT_STATE.validate(engine)
    except ValueError as exc:
        issue('encounter_membership', None, str(exc))
    try:
        import item_maturation as MATURATION
        MATURATION.validate_world(engine,index)
    except ValueError as exc:
        issue('item_maturation',None,str(exc))
    try:
        import item_containers as CONTAINERS
        CONTAINERS.validate_world(engine,index)
    except ValueError as exc:
        issue('item_contents',None,str(exc))
    try:
        import pickup_item_copy as PICKUP_COPY
        PICKUP_COPY.validate_world(engine,index)
    except ValueError as exc:
        issue('pickup_item_copy',None,str(exc))
    try:
        import effect_instances as INSTANCES
        INSTANCES.validate_world(engine,index)
        import native_switch_transfer as SWITCH
        SWITCH.validate_world(engine,index)
    except ValueError as exc:
        issue('effect_instance',None,str(exc))
    try:
        import effect_lifetime_policy as EFFECT_TIME
        EFFECT_TIME.validate_world(engine,index)
    except ValueError as exc:
        issue('effect_lifetime',None,str(exc))
    try:
        import equipment_variant_contracts as EQUIPMENT_VARIANTS
        EQUIPMENT_VARIANTS.validate_world(engine,index)
    except ValueError as exc:
        issue('equipment_variant',None,str(exc))
    try:
        import magic_flute as MAGIC_FLUTE
        MAGIC_FLUTE.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('magic_flute',None,str(exc))
    try:
        import pester_balls as PESTER
        PESTER.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('pester_balls',None,str(exc))
    try:
        import smoke_balls as SMOKE_BALLS
        SMOKE_BALLS.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('smoke_ball',None,str(exc))
    try:
        import repels as REPELS
        REPELS.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:
        issue('repel',None,str(exc))
    try:
        import optional_physical_equipment as OPTIONAL_EQUIPMENT
        OPTIONAL_EQUIPMENT.validate_world(engine,index)
    except ValueError as exc:
        issue('optional_physical_equipment',None,str(exc))
    try:
        import optional_state_effect_contracts as OPTIONAL_STATE
        import combat_timing as OPTIONAL_CLOCK
        if any(OPTIONAL_STATE.STATE in actor.spec or
               any('optional_clause_id' in row for row in OPTIONAL_CLOCK.records(actor))
               for actor in index.values()):
            OPTIONAL_STATE.validate_world(engine)
    except (ValueError, KeyError, TypeError) as exc:
        issue('optional_state_effect',None,str(exc))
    try:
        import optional_weapon_framework as OPTIONAL_WEAPONS
        OPTIONAL_WEAPONS.validate_world(engine,index)
        __import__('telekinetic').validate_world(engine,index)
        __import__('telepath').validate_world(engine,index)
        __import__('warper').validate_world(engine,index)
        import living_weapon as LIVING
        LIVING.validate_world(engine,index)
    except ValueError as exc:
        issue('optional_weapon_framework',None,str(exc))
    try:
        import survivalist_features as SURVIVALIST
        SURVIVALIST.validate_world(engine,index)
    except ValueError as exc:
        issue('survivalist_csv_selection',None,str(exc))
    try:
        import class_actor_state_reactions as CLASS_REACTIONS
        CLASS_REACTIONS.validate_world(engine,index)
    except ValueError as exc:
        issue('class_actor_state_reaction',None,str(exc))
    try:
        import relative_movement as RELATIVE
        RELATIVE.validate_world(engine,index)
    except ValueError as exc:
        issue('relative_movement',None,str(exc))
    registered = {}
    for uid, actor in index.items():
        owner = actor.spec.get('trainer_id')
        if owner is not None and (owner not in index or index[owner].kind != 'trainer'):
            issue('dangling_owner', uid, 'Pokemon owner must resolve to an actual trainer.')
        control = actor.spec.get('controller')
        if control is not None:
            if not isinstance(control, dict) or control.get('kind') not in ('gm','player','actor','pending'):
                issue('controller', uid, 'Unknown controller kind.')
            elif control.get('kind') == 'actor' and control.get('id') not in index:
                issue('dangling_controller', uid, 'Controlling actor does not resolve.')
        placement = actor.spec.get('party_location')
        if placement is not None:
            parent = index.get(owner)
            expected = parent.spec.get('pokemon_registry', {}).get(uid) if parent is not None else None
            if placement.get('owner_id') != owner or placement.get('pokemon_id') != uid or expected != {k:v for k,v in placement.items() if k!='pokemon_id'}:
                issue('party_registry_mismatch', uid, 'Placement and owner registry disagree.')
            if placement.get('location') != 'carried' and getattr(actor, 'on_field', False):
                issue('stored_on_field', uid, 'Stored/unresolved Pokemon cannot be on the field.')
        for pid, row in actor.spec.get('pokemon_registry', {}).items():
            if pid in registered and registered[pid] != uid:
                issue('duplicate_registry_owner', pid, 'Pokemon is registered to multiple owners.')
            registered[pid] = uid
            if row.get('owner_id') != uid:
                issue('registry_owner_mismatch', pid, 'Registry record has another owner.')
            if pid not in index and not row.get('sheet_pending'):
                issue('dangling_registry_actor', pid, 'Actual registered Pokemon is absent; reserve metadata must be explicit.')
            elif pid in index and (index[pid].spec.get('trainer_id') != uid or index[pid].spec.get('party_location') is None):
                issue('registry_actor_mismatch', pid, 'Actual Pokemon ownership/placement does not match registry.')
    import special_entities as PRIME_SPECIAL
    try:PRIME_SPECIAL.validate_prime_world(engine,index)
    except ValueError as exc:issue('prime_unown_projection',None,str(exc))
    import marsupial_state as MARSUPIAL
    try:MARSUPIAL.validate_world(engine)
    except (ValueError,KeyError,TypeError) as exc:issue('marsupial_pouch_relation',None,str(exc))
    objects = getattr(engine, '_physical_objects', {})
    loads = {};equipment = {}
    try:
        import equipped_transport_saddle as EQUIPMENT_TRANSPORT
        EQUIPMENT_TRANSPORT.validate_world(engine,index)
    except (ValueError,KeyError,TypeError) as exc:issue('equipment_transport',None,str(exc))
    for uid, actor in index.items():
        for registration in getattr(actor,'_item_reg',{}).values():
            oid=registration.get('instance_id')
            if oid is None:continue
            if oid in equipment:issue('duplicate_equipment_instance',oid,'One item instance has multiple equipment registrations.')
            equipment[oid]=uid
            if oid not in objects or objects[oid].get('equipped_by')!=uid:issue('equipment_instance_mismatch',oid,'Equipment registration and physical instance holder disagree.')
        for registration in actor.custom_conditions.get('equipped_weapons', {}).values():
            oid = registration.get('weapon', {}).get('framework_instance')
            if oid is None:continue
            if oid in equipment and equipment[oid] != uid:
                issue('duplicate_equipment_instance',oid,'One physical weapon has multiple equipment holders.')
            equipment[oid] = uid
            remote=bool(registration['weapon'].get('telekinetic'))
            holder=objects.get(oid,{}).get('telekinetic_holder_id' if remote else 'equipped_by')
            if remote:
                try:__import__('telekinetic').remote(engine,actor,objects.get(oid,{}))
                except (ValueError,KeyError,TypeError) as exc:issue('equipment_instance_mismatch',oid,str(exc))
            if registration.get('instance_id') != oid or oid not in objects or holder != uid:
                issue('equipment_instance_mismatch',oid,'Weapon registration and physical instance holder disagree.')
        for row in actor.spec.get('_carried_load', {}).get('objects', []):
            oid = row.get('id')
            if oid in loads and loads[oid] != uid:
                issue('duplicate_carrier', oid, 'One physical object has two carriers.')
            loads[oid] = uid
            obj = objects.get(oid)
            holder_field='telekinetic_holder_id' if actor.spec.get('_carried_load',{}).get('mode')=='telekinetic' else 'carrier_id'
            if obj is None or obj.get(holder_field) != uid or obj.get('weight_kg') != row.get('weight_kg'):
                issue('carried_object_mismatch', oid, 'Carrying observation and physical object registry disagree.')
    for uid, obj in objects.items():
        if not isinstance(obj,dict):
            issue('object_state',uid,'Physical object state must be a record.');continue
        import special_entities as SPECIAL
        if obj.get('kind') in SPECIAL.KINDS:
            try:
                SPECIAL.validate_record(engine,obj)
            except ValueError as exc:
                issue('special_entity_state',uid,str(exc))
        if obj.get('id') != uid or uid in index:
            issue('object_identity', uid, 'Object identity mismatches key or collides with actor.')
        try:
            loc = location_of(obj)
            if 'pos' in obj and (loc['kind'] != 'grid' or tuple(obj['pos']) != loc['cell']):
                issue('object_location_alias', uid, 'Legacy position disagrees with authoritative location.')
        except ValueError as exc:
            issue('object_location', uid, str(exc))
        for field in ('owner_id','carrier_id','equipped_by'):
            if obj.get(field) is not None and obj[field] not in index:
                issue('dangling_object_'+field, uid, 'Object relationship does not resolve.')
        if 'consumed' in obj:
            consumed = obj['consumed']
            if (not isinstance(consumed, dict) or consumed.get('source') != obj.get('item_rule_id')
                    or not isinstance(consumed.get('source'), str) or not consumed['source'].strip()
                    or consumed.get('by_actor_id') not in index
                    or type(consumed.get('at')) is not int or consumed['at'] < 0):
                issue('object_consumption_evidence', uid, 'Consumed item needs its actual rule, consumer and time.')
            if obj.get('equipped_by') or obj.get('carrier_id') or uid in equipment or uid in loads:
                issue('consumed_item_registered', uid, 'Consumed item cannot remain equipped or carried.')
            if 'destroyed' in obj:
                issue('object_terminal_state', uid, 'Consumption and destruction are distinct terminal events.')
        if 'destroyed' in obj and obj.get('kind') not in SPECIAL.KINDS:
            destroyed=obj['destroyed']
            if not isinstance(destroyed,dict) or not isinstance(destroyed.get('source'),str) or not destroyed['source'].strip() or destroyed.get('by_actor_id',destroyed.get('former_holder_id')) not in index:
                issue('object_destruction_evidence',uid,'Destroyed physical object requires actual source and responsible actor/former holder evidence.')
            if obj.get('equipped_by') or uid in equipment:
                issue('destroyed_equipment_registered',uid,'Destroyed equipment cannot remain active equipment.')
        if obj.get('equipped_by') and equipment.get(uid)!=obj['equipped_by']:issue('equipment_holder_mismatch',uid,'Registered equipment holder lacks this instance in its item registration.')
        if obj.get('equipped_by') and obj.get('carrier_id') and obj['equipped_by']!=obj['carrier_id']:issue('physical_holder_mismatch',uid,'Equipment and carried-load holders disagree.')
        if obj.get('carrier_id') and loads.get(uid) != obj['carrier_id']:
            issue('carrier_load_mismatch', uid, 'Registered carrier lacks this object in its load.')
    try:
        import held_equipment as HELD
        for actor in index.values():HELD.validate(actor)
    except ValueError as exc:
        issue('held_equipment_state',None,str(exc))
    try:
        import action_resources as RESOURCES
        for actor in index.values():RESOURCES.turn_lock(actor,engine)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        issue('next_turn_action_lock',None,str(exc))
    try:
        import equipment_suppression as EQUIPMENT_SUPPRESSION
        EQUIPMENT_SUPPRESSION.validate(engine,index)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        issue('equipment_suppression_state',None,str(exc))
    try:
        import actor_templates as TEMPLATES
        TEMPLATES.validate_world_templates(engine)
    except ValueError as exc:
        issue('actor_template_state',None,str(exc))
    try:
        import pokemon_entities as POKEMON_ENTITIES
        POKEMON_ENTITIES.validate_world(engine)
    except ValueError as exc:
        issue('pokemon_entity_state',None,str(exc))
    try:
        import partial_entities as PARTIAL
        PARTIAL.validate_world(engine)
    except ValueError as exc:
        issue('partial_entity_state',None,str(exc))
    try:
        __import__('jump_move_actions').validate_world(engine,index)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:issue('jump_move_actions',None,str(exc))
    for module_name,code in (('weather_state','weather_state'),('weather_templates','weather_template_state'),('type_ace','type_ace_state'),('chronicler','chronicler_state'),('fashionista','fashionista_state'),('researcher_fields','researcher_fields_state'),('dancer','dancer_state'),('musician','musician_state'),('athlete','athlete_state'),('hunter','hunter_state'),('martial_artist','martial_artist_state'),('multi_strike','multi_strike_state'),('combat_move_reactions','combat_move_reaction_state'),('walk_it_off','walk_it_off_state')):
        try:
            import importlib
            importlib.import_module(module_name).validate(engine)
        except (TypeError,ValueError,KeyError,AttributeError) as exc:
            issue(code,None,str(exc))
    try:
        import unown_imbuement as UNOWN
        UNOWN.validate_world(engine,index)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        issue('unown_imbuement_state',None,str(exc))
    try:
        import gmax_moves as GMAX
        GMAX.validate_world(engine)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        issue('gmax_state',None,str(exc))
    try:
        import duelist as DUELIST
        DUELIST.validate_world(engine,index)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        issue('duelist_state',None,str(exc))
    try:
        import enduring_resilience as RESILIENCE
        RESILIENCE.validate_world(engine,index)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        issue('resilience_state',None,str(exc))
    try:
        import taskmaster as TASK
        TASK.validate_world(engine,index)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        issue('taskmaster_state',None,str(exc))
    try:
        __import__('provocateur').validate(engine,index)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        issue('provocateur_state',None,str(exc))
    try:
        __import__('type_sync').validate(engine)
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        issue('type_sync_feature_state',None,str(exc))
    return {'valid':not issues, 'actors':len(roster), 'objects':len(objects), 'issues':issues,
            'scope':'Current identity/location/relation integrity only; not category-2 or creation legality certification.'}


def transfer_owner(engine, pokemon, old_owner, new_owner, *, reason, request_id):
    import pokemon_party
    return pokemon_party.transfer(engine, old_owner, target=pokemon, new_owner=new_owner,
                                  reason=reason, request_id=request_id)
