"""Declared ordinary ranks qualify Defender without changing effect-rank policy."""
from copy import copy, deepcopy
import json
import os
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'data/core-rules.json').is_file() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT', r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]
import intercept_profiles as PROFILES
from engine import Rules, Engine
from rulings import Rulings
from native_scenario_fixture import assert_rejected_unchanged
import test_category2_defender_intercept as ORIGINAL
import items as ITEMS
import action_resources as RESOURCES
import skill_modifiers as SKILL

TABLE = 'gameplay/skill-rank-dice'


class DefenderDeclaredRankAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Rules(ROOT, ruleset='core')

    def fixture(self, *, declared=True):
        rules = copy(self.base)
        rules.rulings = Rulings()
        if declared:
            for name, rank, dice, english in (
                    ('초월', 7, 7, 'Epic'), ('전설', 9, 9, 'Legendary'),
                    ('신화', 10, 7, 'Mythic'), ('천상', 12, 12, 'Celestial')):
                rules.rulings.set_mech(TABLE, 'by_rank_name.' + name,
                    {'rank': rank, 'dice': str(dice) + 'd6', 'eng': english},
                    reason='Campaign ordinary rank declaration before importing the Defender sheet',
                    scope='campaign', rules=rules)
        helper = ORIGINAL.DefenderInterceptTests('runTest')
        helper.rules = rules
        return helper.fixture()

    def declare_owned(self, f, rank):
        f.e.gm.set_skill(f.r, 'Athletics', rank, reason='Observed ordinary Athletics on the imported Defender sheet')
        f.r.spec['feats'] = [PROFILES.DEFENDER]
        f.r.spec['feature_stat_imports'] = {
            PROFILES.DEFENDER: {'mode': 'apply', 'base_stat': f.r.stats['hp']}}

    def acquire(self, f, rank):
        self.declare_owned(f, rank)
        ITEMS.register_feats(f.e, f.r)
        return deepcopy(f.r.custom_conditions[PROFILES.RECEIPTS][PROFILES.DEFENDER])

    def restore(self, f):
        ids = [a.entity_id for a in (f.a, f.t, f.r)]
        saved = json.loads(json.dumps(f.e.export_state(), ensure_ascii=False))
        f.e = Engine.import_state(Rules(ROOT, ruleset='core'), saved)
        actors = {a.entity_id: a for a in f.e.everyone}
        f.a, f.t, f.r = [actors[uid] for uid in ids]

    def attempt(self, f):
        row = next(row for row in f.e._move_completions.values() if row['actor'] is f.a)
        return row['defense'][f.t.entity_id]['attempts'][0]

    def test_actual_declared_numeric_and_named_ranks_register_once_without_an_upper_cap(self):
        for stored, rank in ((7, 7), ('Legendary', 9), (10, 10), ('천상', 12)):
            with self.subTest(stored=stored):
                f = self.fixture()
                before_hp, base = f.r.hp, f.r.stats['hp']
                receipt = self.acquire(f, stored)
                ITEMS.register_feats(f.e, f.r)
                self.assertEqual(receipt['qualification'], {
                    'skill': 'athletics', 'minimum': 4, 'rank_at_acquisition': rank})
                self.assertEqual(f.r.stats['hp'], base + 1)
                self.assertEqual(f.r.spec['stats']['hp'], base + 1)
                self.assertEqual(f.r.hp, before_hp)
                self.assertEqual(f.r.custom_conditions[PROFILES.RECEIPTS][PROFILES.DEFENDER], receipt)
                profile = PROFILES.profile(f.e, f.r, {}, 'maneuver/근접-가로채기')
                self.assertTrue(PROFILES.validate_profile(f.e, f.r, profile, historical=False))
                self.assertTrue(PROFILES.validate_profile(f.e, f.r, profile, historical=True))
        self.assertFalse(self.base.rulings.mech)

    def test_native_pending_restore_rank_reduction_and_withdrawal_preserve_qualified_history(self):
        f = self.fixture()
        receipt = self.acquire(f, 10)
        f.watch()
        event = f.waiting()
        self.restore(f)
        self.assertEqual(SKILL.rank(f.e.r, f.r, 'Athletics'), ('신화', '7d6', 10))
        f.choose(event, options=f.melee(faces=(6,) * 7))
        attempt = self.attempt(f)
        profile = deepcopy(attempt['cost_profile'])
        self.assertEqual(attempt['check_total'], 42)
        self.assertEqual(f.r._action_history, ['shift'])
        self.assertEqual(RESOURCES.pending(f.r), {'shift': 1})
        self.assertEqual((f.t.pos, f.r.pos), ((4, 2), (3, 2)))
        self.assertEqual(profile['modifier_sources'][0]['actor_id'], f.r.entity_id)
        self.assertEqual(profile['modifier_sources'][0]['source_id'], PROFILES.DEFENDER)
        self.assertEqual(profile['modifier_sources'][0]['acquisition'], receipt)
        f.e.gm.set_skill(f.r, 'Athletics', 3, reason='Later ordinary Athletics reduction does not undo acquisition')
        ITEMS.register_feats(f.e, f.r)
        self.assertEqual(SKILL.rank(f.e.r, f.r, 'Athletics')[2], 3)
        self.assertTrue(PROFILES.validate_profile(f.e, f.r, profile, historical=False))
        f.r.spec['feats'] = []
        self.assertEqual(PROFILES.profile(f.e, f.r, {}, 'maneuver/근접-가로채기')['action'], 'full')
        self.assertTrue(PROFILES.validate_profile(f.e, f.r, profile, historical=True))
        self.restore(f)
        self.assertEqual(self.attempt(f)['cost_profile'], profile)
        self.assertEqual(f.r.custom_conditions[PROFILES.RECEIPTS][PROFILES.DEFENDER], receipt)
        self.assertEqual(f.r._action_history, ['shift'])
        self.assertTrue(f.e.validate_state()['valid'])

    def test_forged_undeclared_and_noninteger_receipt_ranks_refuse_at_both_readers(self):
        f = self.fixture()
        self.acquire(f, 10)
        original = deepcopy(f.r.custom_conditions[PROFILES.RECEIPTS][PROFILES.DEFENDER])
        profile = PROFILES.profile(f.e, f.r, {}, 'maneuver/근접-가로채기')
        for invalid in (999, 8, 3, True, 7.0):
            with self.subTest(invalid=invalid):
                forged = deepcopy(original)
                forged['qualification']['rank_at_acquisition'] = invalid
                f.r.custom_conditions[PROFILES.RECEIPTS][PROFILES.DEFENDER] = forged
                value = deepcopy(profile)
                value['modifier_sources'][0]['acquisition'] = deepcopy(forged)
                assert_rejected_unchanged(f.e,
                    lambda: ITEMS.register_feats(f.e, f.r),
                    reason_pattern='Defender acquisition qualification receipt changed')
                assert_rejected_unchanged(f.e,
                    lambda: PROFILES.validate_profile(f.e, f.r, value, historical=True),
                    reason_pattern='Defender profile acquisition or prerequisite evidence changed')
        f.r.custom_conditions[PROFILES.RECEIPTS][PROFILES.DEFENDER] = original

    def test_effect_rank_eight_is_not_recorded_as_ordinary_acquisition_rank_and_bare_numbers_refuse(self):
        f = self.fixture(declared=False)
        f.e.gm.set_skill(f.r, 'Athletics', 6, reason='Actual Master skill before the owned Virtuoso choice')
        f.r.spec['edges'] = ['edge/거장']
        f.r.spec['edge_choices'] = {'edge/거장': ['육상']}
        receipt = self.acquire(f, 6)
        self.assertEqual(SKILL.effective_rank(f.e.r, f.r, 'Athletics'), 8)
        self.assertEqual(receipt['qualification']['rank_at_acquisition'], 6)
        for undeclared in (7, 999):
            with self.subTest(undeclared=undeclared):
                fresh = self.fixture(declared=False)
                assert_rejected_unchanged(fresh.e,
                    lambda: self.declare_owned(fresh, undeclared),
                    reason_pattern='unresolved ordinary numeric skill rank')
                self.assertNotIn(PROFILES.DEFENDER, fresh.r.spec.get('feats', []))
                self.assertNotIn(PROFILES.DEFENDER, fresh.r.custom_conditions.get(PROFILES.RECEIPTS, {}))


if __name__ == '__main__':
    unittest.main()
