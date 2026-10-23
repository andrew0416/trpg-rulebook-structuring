"""C10-097: live Pack Mon authority, using existing species/evolution data.

Pre-evolutions obey irrespective of level. The ten-level difference qualifies
the same-species alternative (ch10:107, contrasted by same-species ch10:109).
This grants neither trainer ownership, loyalty nor an additional action.
"""
import common_checks as C
import crafting_recipes as SOURCE_POLICY
import perception_communicate as COMM
import world_entities as WORLD
from builder import species_lookup, evolution_stages
from source_context import verified_source

SOURCE = 'capability/우두머리'
SOURCE_REFERENCE = {'file': 'input/ch10-index-reference.md',
    'sha256': 'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe'}
EVOLUTION_REFERENCE = {'file': 'input/db/learnsets.csv',
    'sha256': '9b2be5bac7189567b97ad957379124f1a001bf016a0ce45ed03f63065a10ea6a'}


def authorize(engine, commander, pokemon):
    WORLD.require_actors(engine, commander, pokemon)
    import partial_entities as PARTIAL
    for actor in (commander, pokemon):
        PARTIAL.require_complete(actor, 'Pack Mon command')
        if actor.kind != 'pokemon':raise ValueError('actual Pokemon commander and subordinate required')
        if actor.dead or actor.fainted:raise ValueError('conscious Pack Mon participants required')
        C.integer(actor.level, 'current Pokemon level', 1, 100)
    if commander is pokemon:raise ValueError('Pack Mon does not command itself')
    if not COMM._owns(commander, 'capabilities', (SOURCE, '우두머리', 'Pack Mon')):
        raise ValueError('current Pack Mon capability required')
    SOURCE_POLICY._selected(engine, SOURCE)
    verified_source(engine.r, SOURCE_REFERENCE, label='Pack Mon')
    leader = species_lookup(engine.r, commander.spec.get('species'))
    follower = species_lookup(engine.r, pokemon.spec.get('species'))
    for species in (leader, follower):SOURCE_POLICY._selected(engine, species['id'])
    if leader['id'] == follower['id']:
        relation = 'same_species'
        obeys = commander.level - pokemon.level >= 10
    else:
        # The current leader's own listed lineage excludes unrelated species
        # and alternative branches; a global stage number is never a relation.
        learnset = engine.r.learnsets.get(leader['name'], {})
        if learnset.get('_source', {}).get('file') == 'db/learnsets.csv':
            verified_source(engine.r, EVOLUTION_REFERENCE, label='Pack Mon evolution')
        stages = evolution_stages(learnset)
        own = [stage for stage, name, _ in stages if name == leader['name']]
        previous = [stage for stage, name, _ in stages if name == follower['name']]
        obeys = len(own) == 1 and len(previous) == 1 and previous[0] < own[0]
        relation = 'pre_evolution'
    if not obeys:raise ValueError('Pack Mon species/level relation does not grant command authority')
    return {'activity': 'command_loyalty', 'obeys': True, 'check': None,
            'source': SOURCE, 'commander_id': commander.entity_id,
            'pokemon_id': pokemon.entity_id, 'relation': relation,
            'commander_species': leader['id'], 'pokemon_species': follower['id'],
            'commander_level': commander.level, 'pokemon_level': pokemon.level}
