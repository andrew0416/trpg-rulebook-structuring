"""Modern Paralysis' printed failed-save consequences on the native round clock."""
from copy import deepcopy
import common_checks as C
import combat_timing as CLOCK
import effect_lifetimes as LIFETIMES
import resolution_transaction as FINGERPRINTS

SOURCE = {'file': 'source-audit/english/paralysis-feb2016.txt',
          'sha256': '36208d5564e4cf690e0151e5aa42e3f4ac52d3c1593c0d41339f95fb5b858b2d'}
DEFINITION = 'fac3ee002d5cd74477a195a75a3813f26e2e96b0c2849a996d288435cacc2495'


def _source(engine):
    from source_context import verified_source
    verified_source(engine.r, SOURCE, source_root='source-audit', label='modern Paralysis clarification')
    definition = engine.r.mech('condition/마비')
    import condition_editions as EDITIONS
    definition = EDITIONS.modern_paralysis_definition(engine.r, definition)
    if FINGERPRINTS.json_fingerprint(definition, compact=True) != DEFINITION:
        raise ValueError('modern Paralysis selected definition changed; review required')


def preflight_turn(engine, actor, initiative_count=None):
    """Require a real application count before starting a turn or rolling a save."""
    import boss_transitions as BOSS
    if '마비' not in actor.conditions or not BOSS.condition_applies_this_turn(actor, '마비'):
        return
    _source(engine)
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError('modern Paralysis turn requires an actual open combat round')
    if initiative_count is None:
        CLOCK.current(engine)
    else:
        C.integer(initiative_count, 'actual Paralysis initiative count')


def failed_save(engine, actor, check):
    """Only the native failed start-turn save calls this producer."""
    _source(engine)
    if '마비' not in actor.conditions or check.get('passed') is not False or check.get('base_dc') != 11:
        raise ValueError('actual failed modern Paralysis saving check required')
    count = CLOCK.current(engine)
    C.integer(check.get('natural'), 'actual Paralysis saving d20', 1, 20)
    source = 'condition/마비'
    record = LIFETIMES.prepare(engine, actor, actor,
        {'type': 'apply_status', 'status': '취약', 'duration': '1 round'}, source)
    prohibition = LIFETIMES.prepare(engine, actor, actor,
        {'type': 'forbid', 'actions': ['attack_of_opportunity'], 'duration': '1 round'}, source)
    record['forbidden_actions'] = prohibition['forbidden_actions']
    record['paralysis_failed_save'] = {
        'clause_id': 'ERRATA-090', 'source': deepcopy(SOURCE), 'actor_id': actor.entity_id,
        'round': engine.round_no, 'count': count,
        'turn_serial': actor.custom_conditions['combat_turn_serial'], 'check': deepcopy(check),
    }
    return CLOCK.install(engine, actor, record)
