"""Campaign script: declare ordinary ranks without editing PTU source data.

Call configure(engine.r) before importing/updating an actor's skills.
A declaration defines a rank/pool, not the game's advancement or purchase rules.
The native d6-pool adapter and PTU effect/assistance policies remain distinct.
"""

def configure(rules, *, scope='campaign'):
    for name, row in {
        '초월': {'rank': 7, 'dice': '7d6', 'eng': 'Epic'},
        '전설': {'rank': 9, 'dice': '9d6', 'eng': 'Legendary'},
        '신화': {'rank': 10, 'dice': '7d6', 'eng': 'Mythic'},
    }.items():
        rules.rulings.set_mech(
            'gameplay/skill-rank-dice', 'by_rank_name.' + name, row,
            reason='Campaign ordinary ranks; Mythic deliberately keeps seven dice',
            scope=scope, rules=rules)

# Existing sheet API, after configure(engine.r):
# state_fields.base_patch(actor, {'skills': {'Athletics': 10}},
#                         reason='Observed campaign character sheet')
# engine.skill_roll(actor, 'Athletics', fixed=[2] * 7).total == 14
