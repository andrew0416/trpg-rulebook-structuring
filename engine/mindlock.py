"""The three remaining named Mindlock immunity consumers, without new state.

Telepathy and Dream Reader keep their existing native owners. These adapters
do not implement the positive Mind Reader, Gentle Vibe or Warning procedures.
"""
import common_checks as C
import perception_communicate as COMM
import crafting_recipes as SOURCE_POLICY
import world_entities as WORLD
from source_context import verified_source

SOURCE = 'capability/정신봉인'
MIND_READER = 'move/마음의눈'
GENTLE_VIBE = 'ability/다정한분위기'
WARNING = 'feat/텔레파시-경고'
WARNING_NAMES = (WARNING, '텔레파시 경고', 'Telepathic Warning')
GENTLE_NAMES = (GENTLE_VIBE, '다정한분위기', 'Gentle Vibe')
ATTACK_FACT = 'mindlock_warning_immunity'
SOURCE_REFERENCE = {
    'file': 'input/ch10-index-reference.md',
    'sha256': 'c3a1d783b4f649f0f6e25a9443a90ca8079a6e036c42c6f8797e100127157abe',
}


def block(engine, holder):
    # Reuse the live capability projection and exact source admission already
    # used by Telepathy. Ability suppression does not suppress this capability.
    if not COMM._owns(holder, 'capabilities', ('정신봉인', 'Mindlock', SOURCE)):
        return None
    SOURCE_POLICY._selected(engine, SOURCE)
    verified_source(engine.r, SOURCE_REFERENCE, label='Mindlock')
    return SOURCE


def move_block(engine, attacker, target, move):
    if move.get('id') != MIND_READER:
        return None
    WORLD.require_actors(engine, attacker, target)
    SOURCE_POLICY._selected(engine, MIND_READER)
    return block(engine, target)


def gentle_block(engine, actor, ability, target):
    if ability not in GENTLE_NAMES:
        return None
    WORLD.require_actors(engine, actor, target)
    import partial_entities as PARTIAL
    import ability_transitions as ABILITIES
    PARTIAL.require_complete(actor, 'Gentle Vibe source')
    PARTIAL.require_complete(target, 'Gentle Vibe target')
    SOURCE_POLICY._selected(engine, GENTLE_VIBE)
    if not ABILITIES.active(actor, GENTLE_VIBE):
        raise ValueError('actual unsuppressed Gentle Vibe owner required')
    immunity = block(engine, target)
    if immunity is None:
        return None  # Preserve the existing unsupported positive procedure.
    return {'source': GENTLE_VIBE, 'actor_id': actor.entity_id,
            'target_id': target.entity_id, 'status': 'immune',
            'immunity_source': immunity, 'calmed': False}


def warning_interested(engine):
    # Only creates an existing native Move occurrence. Registration does not
    # grant a reaction, AP payment, Shift, trace or invented target selection.
    return any(any(name in WARNING_NAMES for name in c.spec.get('feats', ()))
               for c in WORLD.actor_index(engine).values())


def attack_immunity(engine, attacker):
    WORLD.require_actors(engine, attacker)
    return block(engine, attacker)


def warning(engine, owner, event_id):
    WORLD.require_actors(engine, owner)
    import acquired_features as ACQUIRED
    import telepathy as TELEPATHY
    import move_completion as COMPLETE
    import passive_events as EVENTS
    if not ACQUIRED.owned_rule_count(owner, WARNING):
        raise ValueError('actual acquired Telepathic Warning owner required')
    if not TELEPATHY.owns(owner):
        raise ValueError('current Telepathy capability required for Warning')
    if type(event_id) is not str:
        raise ValueError('Warning requires an actual native Move event ID')
    # Existing signed occurrence/return/completion owners establish who really
    # attacked. A caller-provided attacker or detached receipt is not authority.
    receipt = COMPLETE.require_returned_event(engine, event_id)
    event = engine._passive_events[event_id]
    EVENTS._bind_intent(engine, event)
    attacker = event['actor']
    WORLD.require_actors(engine, attacker)
    if attacker is not owner and (not getattr(owner, 'side', None) or
                                  owner.side != getattr(attacker, 'side', None)):
        raise ValueError('Warning requires the owner or an actual ally attack')
    if ATTACK_FACT not in event:
        raise ValueError('this older attack has no observed Mindlock boundary')
    immunity = event[ATTACK_FACT]
    if immunity not in (None, SOURCE):
        raise ValueError('invalid native Mindlock attack observation')
    if immunity is not None:
        SOURCE_POLICY._selected(engine, SOURCE)
        verified_source(engine.r, SOURCE_REFERENCE, label='Mindlock')
        return {'source': WARNING, 'status': 'not_triggered',
                'immunity_source': immunity, 'attacker_id': attacker.entity_id,
                'owner_id': owner.entity_id, 'event_id': receipt['event_id']}
    return {'source': WARNING, 'status': 'returned_attack', 'attacker_id': attacker.entity_id,
            'owner_id': owner.entity_id, 'event_id': receipt['event_id'],
            'reaction_boundary': 'arm_telepath_reaction before the actual pending Attack'}
