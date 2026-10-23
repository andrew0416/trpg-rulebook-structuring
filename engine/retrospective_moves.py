"""Reviewed attacks that consume prior damage instead of the damage chart."""
import attack_damage_history as HISTORY

METAL = 'move/메탈버스트'
RAW = {'never_miss': True, 'effects_exec': [
    {'type': 'hp_loss', 'value': 'direct damage user took this round', 'target': 'all in burst'}]}
SOURCE_REF = {'file': 'input/db/moves.csv',
    'sha256': 'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'}


def project(engine, actor, move, mechanics):
    if move['id']=='move/참기':
        import bide as BIDE
        return BIDE.project(engine,actor,move,mechanics)
    if move['id'] != METAL: return move, mechanics
    from source_context import verified_source
    verified_source(engine.r,SOURCE_REF,label='Metal Burst')
    if engine.r._selected_rule(METAL) != METAL or mechanics != RAW:
        raise ValueError('selected Metal Burst source changed')
    if not engine.encounter_active: raise ValueError('Metal Burst needs an actual combat round')
    value = HISTORY.current_round(engine, actor)
    # All actual burst recipients get the same pre-activation observation.
    return dict(move, _retrospective_hp_loss=value), {
        'never_miss': True,
        'effects_exec': [{'type': 'hp_loss', 'value': value, 'target': 'target'}]}
