"""CSV paid reselection and verified withdrawal share native talent consumers."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import frequency as FREQUENCY
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import state_grants as GRANTS
import survivalist_features as V
import test_category2_survivalist_csv as CSV
import world_entities as WORLD


class TerrainTalentLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CSV.SurvivalistCSVTests.setUpClass()
        cls.r = CSV.SurvivalistCSVTests.r

    def fixture(self, *, rank=1, choose=True):
        f = CSV.SurvivalistCSVTests()
        e, a, b = f.fixture()
        a.spec['feats'] = ([*V.CHILDREN] if rank == 2 else []) + [V.TALENT]
        a.spec['feat_ranks'] = {V.TALENT: rank}
        values = ('grassland', 'mountain', 'forest', 'cave') if rank == 2 else ('grassland', 'mountain')
        f.select(e, a, values)
        if choose:
            e.survivalist_activity(a, 'choose_talents', terrains=list(values))
        f.env(e, a, 'urban')
        return f, e, a

    def select(self, e, a, values=('forest', 'cave'), choices=('forest', 'cave')):
        return e.survivalist_activity(a, 'select_csv_terrains', clause_id=V.CSV_CLAUSES[1],
                                     terrains=list(values), minutes=2,
                                     reason='observed paid daily terrain replacement',
                                     talent_terrains=None if choices is None else list(choices))

    def consumers(self, e, a, *, plains, mountain, cave=False):
        self.assertEqual(e.move_profile(a, movement_mode='land')[0], 5 if plains else 3)
        self.assertEqual(e.skill_roll(a, '통찰', fixed=[1] * 3,
                                     skill_context={'purpose': 'distant_object',
                                                    'reason': 'actual distant object'}).total, 5 if plains else 3)
        self.assertEqual(V.fall_adjustment(e, a, 5, 2), (4, 1, 1, 1) if mountain else (5, 2, 0, 0))
        e.survivalist_activity(a, 'observe_environment', terrains=['urban'],
                              light='complete_darkness', reason='actual complete darkness')
        self.assertEqual(V.vision(e, a), ('ordinary', True) if cave else ('total', False))
        e.survivalist_activity(a, 'observe_environment', terrains=['urban'],
                              light='normal', reason='return to actual normal light')

    def test_paid_reselection_replaces_both_sources_and_native_consumers_after_restores(self):
        _, e, a = self.fixture()
        import body_state
        body_state.observe_trainer_weight(e, a, 70, unit='kg', reason='GM observed actual trainer mass before fall')
        self.consumers(e, a, plains=True, mountain=True)
        e.gm.snapshot('before-reselection')
        FREQUENCY.new_day(a)
        before_seconds = e.elapsed_seconds
        row = self.select(e, a)
        self.assertEqual((row['sequence'], row['terrains']), (2, ['forest', 'cave']))
        self.assertEqual(e.elapsed_seconds - before_seconds, 120)
        self.assertEqual(a._action_history, ['extended', 'extended'])
        self.assertEqual(V.selected(e, a), V.talents(e, a))
        sources = [r for r in GRANTS.state(a)['sources'].values() if r['kind'] == 'survivalist_csv_selection']
        self.assertEqual([r['selection_sequence'] for r in sources], [2])
        payload = CODEC.dump_engine(e)
        loaded = CODEC.load_engine(self.r, json.loads(json.dumps(payload)))
        for world in (e, loaded):
            actor = WORLD.actor_index(world)[a.entity_id]
            self.consumers(world, actor, plains=False, mountain=False, cave=True)
            fall = world.falling_damage(actor, action_id='reselected-mountain-absent', meters=5,
                                        intentional=False, reason='actual fall after terrain replacement')
            self.assertEqual((fall['damage_distance'], fall['terrain_distance_reduction'],
                              fall['height_injuries'], fall['terrain_injury_reduction']), (5, 0, 2, 0))
            self.assertFalse(FREQUENCY.activation_allowed(actor, V.CSV_QUOTA, V.CSV_FREQUENCY, engine=world))
            self.assertTrue(world.validate_state()['valid'])
        e.gm.restore('before-reselection', reason='restore original paid terrain source')
        a = WORLD.actor_index(e)[a.entity_id]
        self.assertEqual(V.selected(e, a), ('grassland', 'mountain'))
        self.assertEqual(V.talents(e, a), ('grassland', 'mountain'))
        self.consumers(e, a, plains=True, mountain=True)

    def test_missing_invalid_and_unpaid_replacement_are_unchanged(self):
        _, e, a = self.fixture()
        NATIVE.assert_rejected_unchanged(e, lambda: self.select(e, a), reason_pattern='daily selection exhausted')
        FREQUENCY.new_day(a)
        for values, choices, reason in [
                (('forest', 'cave'), None, 'simultaneous Terrain Talent choices'),
                (('forest', 'cave'), ('grassland', 'mountain'), 'two distinct mastered-terrain talents'),
                (('forest', 'cave'), ('forest', 'forest'), 'two distinct mastered-terrain talents'),
                (('forest', 'cave'), ('forest',), 'two distinct mastered-terrain talents')]:
            with self.subTest(values=values, choices=choices):
                NATIVE.assert_rejected_unchanged(e, lambda: self.select(e, a, values, choices), reason_pattern=reason)
        self.assertEqual(V.talents(e, a), ('grassland', 'mountain'))

    def test_rank_two_reselection_and_later_days_do_not_inherit_old_choices(self):
        _, e, a = self.fixture(rank=2)
        for values in [('forest', 'cave', 'urban', 'desert'), ('grassland', 'mountain', 'ocean', 'tundra')]:
            FREQUENCY.new_day(a)
            self.select(e, a, values, values)
            self.assertEqual(V.talents(e, a), values)
            NATIVE.assert_rejected_unchanged(e,
                lambda: e.survivalist_activity(a, 'choose_talents', terrains=list(reversed(values))),
                reason_pattern='cannot be rewritten')
        self.assertEqual(len(a.spec[V.CSV_STATE]['history']), 3)
        # A newly acquired rank2 may replace its valid earlier rank1 choices.
        _, e, a = self.fixture()
        a.spec['feats'].extend(V.CHILDREN)
        a.spec['feat_ranks'][V.TALENT] = 2
        FREQUENCY.new_day(a)
        values = ('forest', 'cave', 'urban', 'desert')
        self.select(e, a, values, values)
        self.assertEqual(V.talents(e, a), values)
        self.assertEqual(a.spec['_survivalist_talents']['rank'], 2)

    def test_withdrawal_is_verified_dormant_and_next_paid_choice_reactivates(self):
        _, e, a = self.fixture()
        import body_state
        body_state.observe_trainer_weight(e, a, 70, unit='kg', reason='GM observed actual trainer mass before fall')
        record = deepcopy(a.spec['_survivalist_talents'])
        e.survivalist_activity(a, 'withdraw_csv_terrains', reason='withdraw actual paid terrain choice')
        payload = CODEC.dump_engine(e)
        loaded = CODEC.load_engine(self.r, json.loads(json.dumps(payload)))
        for world in (e, loaded):
            actor = WORLD.actor_index(world)[a.entity_id]
            self.assertEqual(V.selected(world, actor), ())
            self.assertEqual(V.talents(world, actor), ())
            self.assertEqual(actor.spec['_survivalist_talents'], record)
            self.consumers(world, actor, plains=False, mountain=False)
            fall = world.falling_damage(actor, action_id='withdrawn-mountain-absent', meters=5,
                                        intentional=False, reason='actual fall during terrain withdrawal')
            self.assertEqual((fall['damage_distance'], fall['terrain_distance_reduction'],
                              fall['height_injuries'], fall['terrain_injury_reduction']), (5, 0, 2, 0))
            self.assertTrue(world.validate_state()['valid'])
        FREQUENCY.new_day(a)
        self.select(e, a)
        self.assertEqual(V.talents(e, a), ('forest', 'cave'))
        self.consumers(e, a, plains=False, mountain=False, cave=True)

    def test_corrupt_previous_records_cannot_be_laundered_active_or_withdrawn(self):
        mutations = [lambda r: r.update(source='wrong/source'), lambda r: r.update(rank=2),
                     lambda r: r.update(terrains=('grassland', 'urban')),
                     lambda r: r.update(selected_seconds=-1),
                     lambda r: r.update(selected_seconds=10 ** 9)]
        for withdrawn in (False, True):
            for mutate in mutations:
                with self.subTest(withdrawn=withdrawn, mutate=mutate):
                    _, e, a = self.fixture()
                    if withdrawn:
                        e.survivalist_activity(a, 'withdraw_csv_terrains', reason='actual withdrawal')
                    FREQUENCY.new_day(a)
                    mutate(a.spec['_survivalist_talents'])
                    with self.assertRaises(ValueError):
                        V.talents(e, a)
                    NATIVE.assert_rejected_unchanged(e, lambda: self.select(e, a),
                                                     reason_pattern='Terrain Talent|talent')

    def test_talent_acquisition_before_or_after_csv_selection_keeps_explicit_order(self):
        # First CSV choice may precede the actual talent choice, as in existing callers.
        _, e, a = self.fixture(choose=False)
        e.survivalist_activity(a, 'choose_talents', terrains=['grassland', 'mountain'])
        self.assertEqual(V.talents(e, a), ('grassland', 'mountain'))
        f = CSV.SurvivalistCSVTests()
        e, a, _ = f.fixture()
        a.spec['feats'] = [V.TALENT]
        a.spec['feat_ranks'] = {V.TALENT: 1}
        self.select(e, a)
        self.assertEqual(V.talents(e, a), ('forest', 'cave'))
        e, a, _ = f.fixture()
        f.select(e, a)
        FREQUENCY.new_day(a)
        f.select(e, a, ('cave',))
        self.assertEqual(V.talents(e, a), ())
        FREQUENCY.new_day(a)
        NATIVE.assert_rejected_unchanged(e, lambda: self.select(e, a, ('cave',), ('cave',)), reason_pattern='acquired source')

    def test_class_and_talent_loss_do_not_launder_record_and_restore_keeps_choices(self):
        _, e, a = self.fixture()
        e.gm.snapshot('owned-talents')
        FREQUENCY.new_day(a)
        a.spec['classes'] = []
        self.assertEqual(e.move_profile(a, movement_mode='land')[0], 3)
        NATIVE.assert_rejected_unchanged(e, lambda: self.select(e, a), reason_pattern='acquired source')
        e.gm.restore('owned-talents', reason='restore actual class and terrain talent')
        a = WORLD.actor_index(e)[a.entity_id]
        self.assertEqual(V.talents(e, a), ('grassland', 'mountain'))
        a.spec['feats'].remove(V.TALENT)
        FREQUENCY.new_day(a)
        NATIVE.assert_rejected_unchanged(e, lambda: self.select(e, a), reason_pattern='acquired source|talent record')
        with self.assertRaises(ValueError):
            V.talents(e, a)

    def test_late_talent_failure_restores_clock_quota_sources_rng_and_aliases(self):
        _, e, a = self.fixture()
        FREQUENCY.new_day(a)
        before = CODEC.dump_engine(e)
        spec = a.spec
        original = V.choose_talents
        def fail(staged, actor, **options):
            original(staged, actor, **options)
            raise RuntimeError('late chosen talent failure')
        with patch.object(V, 'choose_talents', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'late chosen talent failure'):
                self.select(e, a)
        self.assertIs(a.spec, spec)
        self.assertEqual(CODEC.dump_engine(e), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
