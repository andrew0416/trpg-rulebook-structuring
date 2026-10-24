"""Native Kangaskhan birth and the actual mother/pouch relation (C10-082/083).

The named Baby Template uses the shared growth/Skill/Capability/body owners with
its printed native five-point reduction. Maternal identity is actual parentage.
"""
from copy import deepcopy
import common_checks as C

KEY = 'marsupial_baby'
SOURCE = 'capability/유대류'
STAT_SOURCE = SOURCE + '/native-baby'
SPECIES = 'pokemon/캥카'
SOURCE_FILE = {'file': 'input/ch10-index-reference.md',
               'sha256': 'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}
FLOOR_FILE = {'file': 'input/ch05-pokemon.md', 'sha256': 'bdfb5d39fec8fede32cac615a7788301336aaceefc46079c8ed7014ea76d174b'}
PROTECTION_FILE = {'file': 'source-audit/marsupial-indices-1.05.txt',
                  'sha256': 'de4089335fb49f2167cb54d80ce8e606ed60b4654f72eb8c2b8d789b776a6442'}


def source(rules):
    from source_context import verified_source
    if rules._selected_rule(SOURCE) != SOURCE:
        raise ValueError('selected Marsupial requires its own native birth policy')
    verified_source(rules, SOURCE_FILE, label='native Marsupial birth/pouch')
    verified_source(rules, FLOOR_FILE, label='original minimum-one stats')
    verified_source(rules, PROTECTION_FILE, label='maternal conscious protection', source_root='source-audit')


def record(rules, spec):
    row = spec.get(KEY)
    if row is None:
        return None
    source(rules)
    if type(row) is not dict or set(row) != {'source', 'baby_id', 'egg_id', 'birth_level',
            'mother_id', 'parentage_sha256', 'active', 'ended_level'}:
        raise ValueError('exact native Marsupial birth record required')
    if spec.get('kind') != 'pokemon' or spec.get('species') != SPECIES or row['source'] != SOURCE or row['baby_id'] != spec.get('id') or row['egg_id'] != spec.get('egg_entity_id'):
        raise ValueError('native Marsupial actual birth identity changed')
    C.integer(row['birth_level'], 'actual native birth level', 1, 100)
    if type(row['active']) is not bool or row['active'] != (row['ended_level'] is None):
        raise ValueError('native Marsupial state/exit evidence mismatch')
    if row['ended_level'] is not None:
        C.integer(row['ended_level'], 'native Marsupial exit level', 25, 25)
    return row


def active(actor):
    row = record(actor.r, actor.spec)
    return bool(row and row['active'])


def in_pouch(actor):
    row = record(actor.r, actor.spec)
    return bool(row and row['active'] and row['mother_id'])


def protected_from_attacks(actor, *, engine=None):
    """Custody continues when the actual mother loses consciousness."""
    if not in_pouch(actor):
        return False
    if engine is None:
        raise ValueError('actual world required for maternal conscious protection')
    import world_entities as W
    mother = W.require_actors(engine, actor).get(actor.spec[KEY]['mother_id'])
    if mother is None:
        raise ValueError('actual maternal pouch host required')
    return not mother.fainted


def target_present(actor, *, engine=None):
    """A pouch baby's body stays deployed with its actual mother, not as an actor."""
    if not in_pouch(actor):
        return actor.on_field
    if engine is None:
        raise ValueError('actual world required for maternal target presence')
    import world_entities as W
    mother = W.require_actors(engine, actor).get(actor.spec[KEY]['mother_id'])
    if mother is None:
        raise ValueError('actual maternal pouch host required')
    return mother.on_field and not mother.captured


def base_sources(rules, spec, others):
    row = record(rules, spec)
    if row is None or not row['active']:
        return []
    from builder import species_lookup, STATS
    import growth_stats as GS
    baseline = GS.sourced_base(species_lookup(rules, SPECIES)['base_stats'], others,
                              allow_negative=True)
    import baby_templates as BABY
    template=BABY.validate(rules,spec)
    shared=bool(template and template['source']==BABY.NATIVE_SOURCE)
    remaining=template['stat_penalty_remaining'] if shared else 5
    if not remaining:return []
    # Source composition precedes Nature/investment. The general original
    # minimum-one rule bounds the initial native reduction before Nature.
    # Each printed fifth-level +1 restores that actual floor-clamped deficit.
    # Legacy snapshots keep their historical -5 until an explicit upgrade.
    values = {s: (max(1,min(baseline[s],max(1,baseline[s]-5)+5-remaining))
                  if shared else max(1,baseline[s]-5))-baseline[s] for s in STATS}
    return [{'source': STAT_SOURCE, 'signed': True, 'values': values}]


def prepare_birth(engine, egg, spec, *, physical_choice=None):
    if spec.get('species') != SPECIES:
        return
    source(engine.r)
    import creation_egg as E, growth_stats as GS, pokemon_stat_edges as EDGES
    from builder import species_lookup, record_allocation
    facts = egg.get(E.BINDING, {}).get('facts', {}).get('parents', [])
    mothers = [p['entity_id'] for p in facts if p['species'] == SPECIES and p['gender'] == 'female']
    if len(mothers) > 1:
        raise ValueError('actual maternal identity is ambiguous in egg parentage')
    spec[KEY] = {'source': SOURCE, 'baby_id': spec['id'], 'egg_id': egg['entity_id'],
        'birth_level': spec['level'], 'mother_id': mothers[0] if mothers else None,
        'parentage_sha256': egg.get(E.BINDING, {}).get('sha256'),
        'active': spec['level'] < 25, 'ended_level': None if spec['level'] < 25 else 25}
    import baby_templates as BABY
    BABY.prepare_native_birth(engine.r,spec,physical_choice)
    old = spec['initial_allocation']
    plan = GS.allocate(species_lookup(engine.r, SPECIES)['base_stats'], old['points'],
        strategy=spec.get('strategy', 'balanced'), nature=spec.get('nature'), rules=engine.r,
        relation_exempt=EDGES.exemptions(engine.r, spec), base_sources=EDGES.base_sources(engine.r, spec),
        fixed_point_sources=EDGES.point_sources(engine.r, spec))
    spec['stats'] = deepcopy(plan['stats'])
    spec['initial_allocation'] = deepcopy(plan)
    record_allocation(engine.r, spec, 'native_marsupial_birth', source=SOURCE)


def require_independent(engine, actor):
    if active(actor):
        raise ValueError('native Marsupial baby cannot participate in combat or act')


def children(engine, mother):
    import world_entities as W
    return [a for a in W.actors(engine) if in_pouch(a) and a.spec[KEY]['mother_id'] == mother.entity_id]


def group(engine, actor):
    require_independent(engine, actor)
    return [actor, *children(engine, actor)]


def sync(engine):
    import world_entities as W
    index = W.actor_index(engine)
    for baby in index.values():
        if not active(baby):
            continue
        baby.on_field = False
        row = baby.spec[KEY]
        if not in_pouch(baby):
            continue
        mother = index.get(row['mother_id'])
        if mother is None:
            raise ValueError('native pouch requires its actual mother')
        baby.location = deepcopy(mother.location)


def finish_birth_placement(engine):
    import world_entities as W
    index = W.actor_index(engine)
    for mother in index.values():
        for baby in children(engine, mother):
            if mother.spec.get('trainer_id') != baby.spec.get('trainer_id'):
                continue  # Physical custody follows mother; ownership is independent.
            m, b = mother.spec.get('party_location'), baby.spec.get('party_location')
            if m is None or b is None or m['location'] == b['location']:
                continue
            owner = index.get(m['owner_id'])
            if owner is None:
                raise ValueError('actual pouch party owner required')
            registry = owner.spec['pokemon_registry']
            constrain_roster(engine, [mother, baby], registry)
            for actor in (mother, baby):
                actor.spec['party_location'] = {**deepcopy(registry[actor.entity_id]), 'pokemon_id': actor.entity_id}
                if registry[actor.entity_id]['location'] == 'storage':actor.on_field = False
            owner.spec['pokemon_registry_revision'] += 1
    sync(engine)


def constrain_roster(engine, roster, registry):
    """Two actual Pokemon still use two party places, including in one ball."""
    for mother in roster:
        for baby in children(engine, mother):
            if mother.spec.get('trainer_id') != baby.spec.get('trainer_id'):
                continue
            if baby.entity_id not in registry:
                raise ValueError('pouch mother and actual baby need the same owned roster')
            m, b = registry[mother.entity_id], registry[baby.entity_id]
            if m['location'] != b['location']:
                # A finite capacity cannot leave an unwilling pouch baby behind.
                storage = m if m['location'] == 'storage' else b
                for row in (m, b):
                    row.update(location='storage', destination=deepcopy(storage['destination']))


def on_level(rules, spec, log=None):
    row = record(rules, spec)
    if row is None or not row['active'] or spec['level'] < 25:
        return False
    import baby_templates as BABY
    template=BABY.validate(rules,spec)
    if template and template['source']==BABY.NATIVE_SOURCE:
        if template['stat_penalty_remaining']:raise ValueError('native Template must withdraw before pouch exit')
        row.update(active=False,ended_level=25)
        if log is not None:log.append('  Marsupial: shared Baby Template ends before actual pouch exit')
        return True
    import growth_stats as GS
    from builder import record_allocation
    current = GS.project(rules, spec)
    row.update(active=False, ended_level=25)
    prepared = GS.source_plans(rules, spec, current)
    chosen = prepared['base']
    spec.setdefault('allocation_migrations', []).append({'kind': 'native_marsupial_exit',
        'species': spec['species'], 'level': spec['level'], 'source': SOURCE,
        'reason': 'actual level 25 ends native baby/pouch state',
        'plan': deepcopy(chosen['plan']), 'growth_event_offset': len(spec.get('growth_investment_events', []))})
    spec['stats'] = deepcopy(chosen['stats'])
    record_allocation(rules, spec, 'native_marsupial_exit', source=SOURCE)
    if log is not None:
        log.append('  Marsupial: actual level 25 ends native baby template and pouch')
    return True


def projection(actor, *, engine=None):
    row = record(actor.r, actor.spec)
    if row is None:
        return None
    import baby_templates as BABY
    template=BABY.validate(actor.r,actor.spec)
    return {**deepcopy(row), 'in_pouch': in_pouch(actor), 'can_act': not active(actor),
            'template_upgrade_required':template is None or template['source']!=BABY.NATIVE_SOURCE,
            'protected_from_attacks': protected_from_attacks(actor, engine=engine), 'counts_as_pokemon': 1,
            'same_ball_as_mother': row['mother_id'] if in_pouch(actor) else None}


def ball_view(engine, mother):
    import world_entities as W
    W.require_actors(engine, mother)
    validate_world(engine)
    return {'source': SOURCE, 'ball_storage_actor_id': mother.entity_id,
            'occupant_ids': [] if mother.on_field and not mother.captured else [a.entity_id for a in group(engine, mother)]}


def attack_blocked(attacker, target, move, *, engine=None):
    if not protected_from_attacks(target, engine=engine):return False
    if move.get('class') in ('물리', '특수'):return True
    mm, _ = attacker.r.move_mech(move['id'])
    effects = [effect for effect in mm.get('effects_exec', []) if effect.get('type') != 'targeting_rule']
    if effects and all(effect.get('type') in ('heal', 'cure_status') for effect in effects):return False
    return attacker.side != target.side


def custody(engine, baby):
    import world_entities as W
    row = record(engine.r, baby.spec)
    if not in_pouch(baby):return None
    mother = W.actor_index(engine).get(row['mother_id'])
    if mother is None:raise ValueError('actual maternal pouch host required')
    return {'mother_id': mother.entity_id, 'location': W.location_of(mother),
            'ball_storage_actor_id': mother.entity_id if mother.captured or not mother.on_field else None,
            'baby_owner_id': baby.spec.get('trainer_id'), 'mother_owner_id': mother.spec.get('trainer_id')}


def validate_world(engine):
    import world_entities as W, pokemon_entities as P, creation_egg as E
    index = W.actor_index(engine)
    eggs = None
    for baby in index.values():
        row = record(engine.r, baby.spec)
        if row is None:
            continue
        if row['active'] != (baby.level < 25):
            raise ValueError('native Marsupial must end at actual level 25')
        if eggs is None:
            eggs = P.egg_index(engine)
        entry = eggs.get(row['egg_id'])
        if entry is None or not entry[1]['hatched'] or entry[1].get('pokemon_id') != baby.entity_id:
            raise ValueError('native Marsupial requires its actual successful birth')
        egg = entry[1]
        import baby_templates as BABY
        template=BABY.validate(engine.r,baby.spec)
        if template and template['source']==BABY.NATIVE_SOURCE:
            origin=template['native_origin'];birth_choice=egg.get('gm_hatch_details',{}).get('baby_template')
            if origin['kind']=='birth':
                if BABY.native_physical_choice(birth_choice)!=origin['physical_choice']:
                    raise ValueError('native physical choice must match its actual birth receipt')
            elif birth_choice is not None:
                raise ValueError('complete native birth cannot be reinterpreted as a legacy upgrade')
        binding = egg.get(E.BINDING, {})
        if row['parentage_sha256'] != binding.get('sha256') or row['birth_level'] != egg['hatch_level']:
            raise ValueError('native Marsupial birth/parentage evidence changed')
        mothers = [p['entity_id'] for p in binding.get('facts', {}).get('parents', [])
                   if p['species'] == SPECIES and p['gender'] == 'female']
        if mothers != ([] if row['mother_id'] is None else [row['mother_id']]):
            raise ValueError('native mother must be the actual maternal birth parent')
        if row['active'] and baby.on_field:
            raise ValueError('native Marsupial baby cannot join the combat field')
        if not in_pouch(baby):
            continue
        mother = index.get(row['mother_id'])
        if mother is None or mother is baby or mother.kind != 'pokemon' or mother.spec.get('species') != SPECIES or active(mother):
            raise ValueError('actual independent native mother required')
        if W.location_of(baby) != W.location_of(mother):
            raise ValueError('actual pouch body must follow its mother location')
        m, b = mother.spec.get('party_location'), baby.spec.get('party_location')
        if baby.spec.get('trainer_id') == mother.spec.get('trainer_id') and (m is not None or b is not None) and not (m is None and b.get('location') == 'pending'):
            if m is None or b is None or any(m.get(k) != b.get(k) for k in ('owner_id', 'location', 'destination')):
                raise ValueError('pouch mother/baby must share actual ball/party storage')
