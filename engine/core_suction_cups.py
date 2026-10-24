"""Core Suction Cups: selected live defensive immunity, separate from Playtest."""
from source_context import verified_source

SOURCE = 'ability/흡반'
NAME = '흡반'
CONTRACT = {'type': 'defensive_immunity', 'effects': ['push', 'roar']}
REFERENCE = {'file': 'db/learnsets.csv', 'record_span': [380, 380], 'sha256': '9b2be5bac7189567b97ad957379124f1a001bf016a0ce45ed03f63065a10ea6a', 'additional_snapshots': {'source-audit/core-suction-cups.txt': '2019a07df4538cbca58f4730583840ff3519ab19f5079fc6a5f9cdf7038f4587'}}
EXCERPT = {'file': 'source-audit/core-suction-cups.txt', 'sha256': '2019a07df4538cbca58f4730583840ff3519ab19f5079fc6a5f9cdf7038f4587'}
TEXT = 'Ability: Suction Cups\nStatic Effect: The user is immune to Push effects, and the effects of Roar. Defensive.\n'


def validate_core_ability(rules, row):
    if (row.get('id') != SOURCE or row.get('name') != NAME or row.get('eng') != 'Suction Cups'
            or row.get('frequency') != '항상' or row.get('keyword') != '방어적'
            or row.get('native_contract') != CONTRACT or row.get('effects') != []
            or row.get('source') != REFERENCE or row.get('effect') != TEXT.splitlines()[1]
            or row.get('official_source', {}).get('extract') != EXCERPT['file']
            or row.get('official_source', {}).get('sha256') != EXCERPT['sha256']):
        raise ValueError('exact core Suction Cups definition required')
    verified_source(rules, {'file': 'input/' + REFERENCE['file'], 'sha256': REFERENCE['sha256']},
                    label='Lileep core Ability pool')
    if verified_source(rules, EXCERPT, label='core Suction Cups', source_root='source-audit').decode('utf-8') != TEXT:
        raise ValueError('complete core Suction Cups excerpt required')


def registration(rules, name):
    if name not in (NAME, SOURCE):
        return None
    if rules._selected_rule(SOURCE) != SOURCE:
        return None
    return {'name': NAME, 'source_id': SOURCE}


def active(engine, actor, *, attacker=None, move=None):
    if actor.abilities_suppressed or not any(name in (NAME, SOURCE) for name in actor.abilities):
        return False
    # A selected alternate source must use its own effect; never inherit core Roar immunity.
    if engine.r._selected_rule(SOURCE) != SOURCE:
        return False
    import ability_transitions as ABILITIES
    if not ABILITIES.active(actor, SOURCE):
        return False
    if attacker is not None and __import__('chronicler').defensive_ignored(engine, attacker, actor, move):
        return False
    return True
