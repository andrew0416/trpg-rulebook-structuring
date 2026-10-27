"""New cross-owner regression; original native assertions stay in their modules."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules
import hobbyist as H
import skill_modifiers as SKILLS
import taskmaster as TASK
import test_book_hobbyist_full as HOBBYIST_FIXTURE


class ReconciliationSemanticsTests(unittest.TestCase):
    def test_native_hobbyist_press_uses_virtuoso_substituted_effect_rank_without_global_skill_change(self):
        fixture = HOBBYIST_FIXTURE.HobbyistTests('runTest')
        fixture.rules = Rules(ROOT, ruleset='core+errata')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.ordinary_skills(perception=6, **{'general education': 5})
        fixture.base(edges=[
            {'id': 'edge/거장', 'choice': '통찰'},
            {'id': 'edge/기본-스킬', 'choice': '의학'},
            {'id': 'edge/기본-스킬', 'choice': '오컬트학'},
        ])
        fixture.dilettante('edge/브리더', TASK.PRESS_ACTION, substitute='통찰')
        self.assertEqual(SKILLS.rank(fixture.e.r, fixture.a, '협박')[2], 2)
        self.assertEqual(H.direct_rank(fixture.a, TASK.PRESS_ACTION, '협박', effective=False), 6)
        self.assertEqual(H.direct_rank(fixture.a, TASK.PRESS_ACTION, '협박'), 8)
        fixture.begin(fixture.a)
        before = fixture.p.hp
        TASK.press(fixture.e, fixture.a, fixture.p, stats=['atk', 'spe'], obedience=True)
        self.assertEqual(before-fixture.p.hp, max(1, fixture.p.base_max_hp//6))
        self.assertEqual((fixture.p.stages['atk'], fixture.p.stages['spe']), (1, 1))
        self.assertEqual(fixture.a._action_history, ['standard'])
        result = fixture.e.skill_roll(fixture.a, '협박', fixed=[1, 1],
            skill_context={'purpose': 'pokemon_obedience'}, skill_target=fixture.p)
        self.assertEqual((result.rank, len(result.faces), result.modifier, result.total), (2, 2, 4, 6))
        self.assertEqual(TASK.obedience_bonus(fixture.e, fixture.a,
            {'purpose': 'pokemon_obedience'}, fixture.q), 0)
        fixture.restore()
        self.assertEqual(TASK.obedience_bonus(fixture.e, fixture.a,
            {'purpose': 'pokemon_obedience'}, fixture.p), 4)
        fixture.valid()


if __name__ == '__main__':
    unittest.main()
