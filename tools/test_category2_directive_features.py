"""Actual CSV91 action -> completed effect -> native initiative and target clock."""
from pathlib import Path
from copy import copy, deepcopy
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
from rulings import Rulings
from state_codec import dump_engine, load_engine
import directive_features as D
import combat_timing as TIME
import items as ITEMS


class DirectiveFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, 123291)
        self.r.rulings = self.e.rulings = Rulings()
        stats = dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 20)
        stats['spe'] = 100
        self.a = Combatant(self.r, build_trainer(
            self.r, 'actual director', 20, stats, skills={'매력': 3},
            extra={'classes': [D.CLASS], 'feats': [D.FEATURE]}))
        self.b = Combatant(self.r, build_pokemon(
            self.r, '이상해씨', 20, name='unowned enemy Pokemon', nature='용감', side='enemy'))
        stats['spe'] = self.b.staged('spe') + 3
        self.c = Combatant(self.r, build_trainer(self.r, 'observer', 20, stats))
        for actor in (self.a, self.b, self.c):
            self.e.gm.add_combatant(actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a)
        self.base = self.e.initiative_value(self.b).value

    def use(self, adjustment='increase'):
        return self.e.use_decisive_director(self.a, self.b, adjustment=adjustment)

    def row(self, engine=None):
        engine = engine or self.e
        return next(row for row in engine._effect_dispatch_receipts.values()
                    if row.get('source_id') == D.SOURCE)

    def assertAtomic(self, operation, exception=ValueError):
        before = dump_engine(self.e)
        with self.assertRaises(exception):
            operation()
        self.assertEqual(dump_engine(self.e), before)

    def test_exact_selected_csv_identity_registration_and_coordinator(self):
        definition = D.definition(self.r)
        self.assertEqual(definition['source']['cells'][2], '코디네이터')
        self.assertEqual(definition['source']['record'], 91)
        self.assertEqual(self.r.selection.units[D.FEATURE]['source']['file'], 'db/feats.csv')
        before = dump_engine(self.e)
        ITEMS.register_feats(self.e, self.a)
        ITEMS.register_feats(self.e, self.a)
        self.assertEqual(dump_engine(self.e), before)
        self.assertNotIn(D.FEATURE, self.a.spec.get('unknown_feats', []))

    def test_actual_standard_positive_and_explicit_negative_unowned_enemy(self):
        out = self.use()
        self.assertEqual(out['delta'], 6)
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 6)
        self.assertEqual(self.a._action_history[-1], 'standard')
        row = self.row()
        self.assertIs(row['actor'], self.a)
        self.assertIs(row['target'], self.b)
        self.assertEqual(row['status'], 'completed')
        self.assertEqual(row[D.KEY]['plan']['charm_rank'], 3)
        self.e.end_of_turn(self.a)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a)
        minus = self.e.manual_feat(self.a, D.NAME, self.b, adjustment='decrease')
        self.assertEqual(minus['delta'], -6)
        self.assertIsNot(out['receipt'], minus['receipt'])
        self.assertEqual(self.e.initiative_value(self.b).value, self.base)

    def test_virtuoso_charm_restores_effective_signed_sixteen_without_changing_six_dice(self):
        import skill_modifiers as SKILL,state_grants as G
        for adjustment,delta in (('increase',16),('decrease',-16)):
            with self.subTest(adjustment=adjustment):
                self.setUp()
                self.e.gm.set_skill(self.a,'매력',6,reason='actual Master Charm before Virtuoso acquisition')
                G.transition(self.e,self.a,lambda e,a:a.spec.update(
                    edges=[*a.spec.get('edges',[]),'edge/거장'],edge_choices={'edge/거장':['매력']}))
                self.assertEqual(SKILL.effective_rank(self.e.r,self.a,'매력'),8)
                ids=[a.entity_id for a in (self.a,self.b)]
                self.e=load_engine(Rules(str(self.e.r.root),ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
                index={a.entity_id:a for a in self.e.everyone};self.a,self.b=[index[uid] for uid in ids]
                self.assertEqual(SKILL.rank(self.e.r,self.a,'매력')[2],6)
                self.assertEqual(self.use(adjustment)['delta'],delta)
                self.assertEqual((self.row()[D.KEY]['plan']['charm_rank'],self.e.initiative_value(self.b).value),(8,self.base+delta))
                self.e=load_engine(Rules(str(self.e.r.root),ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
                index={a.entity_id:a for a in self.e.everyone};self.a,self.b=[index[uid] for uid in ids]
                self.assertEqual((self.row()[D.KEY]['plan']['charm_rank'],self.e.initiative_value(self.b).value),(8,self.base+delta))

    def test_source_withdrawal_and_rank_growth_do_not_recalculate_paid_history(self):
        self.use()
        self.a.spec['skills']['매력'] = 5
        self.a.spec['feats'] = []
        self.a.spec['classes'] = []
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 6)
        D.validate_world(self.e, {c.entity_id: c for c in self.e.everyone})
        self.assertAtomic(self.use)
        dump_engine(self.e)

    def test_only_actual_next_target_turn_end_expires(self):
        self.use()
        self.e.end_of_turn(self.a)
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 6)
        self.e.start_of_turn(self.c)
        self.e.end_of_turn(self.c)
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 6)
        self.e.start_of_turn(self.b)
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 6)
        self.e.end_of_turn(self.b)
        self.assertEqual(self.e.initiative_value(self.b).value, self.base)
        self.assertFalse(TIME.records(self.b))
        self.assertEqual(self.b.custom_conditions['effect_lifetime_history'][-1]['state'], 'expired')
        dump_engine(self.e)

    def test_already_acted_target_waits_for_its_next_turn(self):
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.b)
        self.e.end_of_turn(self.b)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a)
        self.use()
        self.assertEqual(self.row()[D.KEY]['plan']['target_turn'], 1)
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.b)
        self.e.end_of_turn(self.b)
        self.assertEqual(self.e.initiative_value(self.b).value, self.base)

    def test_native_order_and_next_schedule_prepare_consume_real_contribution(self):
        self.assertLess(self.e.initiative_value(self.b).value, self.e.initiative_value(self.c).value)
        self.use()
        ordered = self.e.initiative(self.e.everyone)
        self.assertLess(ordered.index(self.b), ordered.index(self.c))
        self.e.end_of_turn(self.a)
        self.e.end_round()
        self.e.prepare_initiative_schedule(self.e.everyone, source='gm/observed normal schedule')
        schedule = self.e._initiative_schedule
        ordered_ids = [schedule['slots'][key]['actor'].entity_id for key in schedule['order']]
        self.assertLess(ordered_ids.index(self.b.entity_id), ordered_ids.index(self.c.entity_id))
        self.assertEqual(len(ordered_ids), 3)
        self.e.start_round(self.e.everyone)
        dump_engine(self.e)

    def test_explicit_choice_target_and_feature_class_admission_are_atomic(self):
        for bad in (None, True, 'add', 1):
            with self.subTest(adjustment=bad):
                self.assertAtomic(lambda: self.use(bad))
        self.assertAtomic(lambda: self.e.use_decisive_director(self.a, self.c, adjustment='increase'))
        for key in ('feats', 'classes'):
            old = self.a.spec[key]
            self.a.spec[key] = []
            self.assertAtomic(self.use)
            self.a.spec[key] = old
        self.e.apply_status(self.a, '잠듦')
        self.assertAtomic(self.use)

    def test_standard_own_turn_and_actual_charm_rank_are_required(self):
        import turn as TURN
        self.assertTrue(TURN.spend(self.e, self.a, 'standard', 'actual earlier Standard'))
        self.assertAtomic(self.use)
        self.e.end_of_turn(self.a)
        self.assertAtomic(self.use)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a)
        before = dump_engine(self.e)
        self.a.spec['skills']['매력'] = 7
        try:
            with self.assertRaises(ValueError):
                self.use()
        finally:
            self.a.spec['skills']['매력'] = 3
        self.assertEqual(dump_engine(self.e), before)

    def test_selected_source_corruption_and_late_install_failure_roll_back(self):
        unit = self.r.selection.units[D.FEATURE]
        before = deepcopy(unit['source'])
        unit['source']['record_span'] = [90, 90]
        try:
            self.assertAtomic(self.use)
        finally:
            unit['source'] = before
        original = TIME.install
        def late(*args, **kwargs):
            original(*args, **kwargs)
            raise ValueError('late native lifetime installation failure')
        with patch.object(TIME, 'install', side_effect=late):
            self.assertAtomic(self.use)

    def test_cloned_unregistered_actor_and_excluded_selected_source_reject_atomically(self):
        clone = copy(self.b)
        self.assertAtomic(lambda: self.e.use_decisive_director(self.a, clone, adjustment='increase'))
        outsider = Combatant(self.r, build_pokemon(self.r, '이상해씨', 20, name='not in this world'))
        self.assertAtomic(lambda: self.e.use_decisive_director(self.a, outsider, adjustment='increase'))
        before = dump_engine(self.e)
        self.r.ruleset.exclude_units.add(D.SOURCE)
        try:
            with self.assertRaises(ValueError):
                self.use()
        finally:
            self.r.ruleset.exclude_units.remove(D.SOURCE)
        self.assertEqual(dump_engine(self.e), before)

    def test_real_new_atwill_actions_compose_independent_fixed_receipts(self):
        first = self.use()
        self.e.end_of_turn(self.a)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a)
        self.a.spec['skills']['매력'] = 4
        second = self.use()
        self.assertEqual((first['delta'], second['delta']), (6, 8))
        self.assertIsNot(first['receipt'], second['receipt'])
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 14)
        self.assertEqual(len(TIME.records(self.b)), 2)
        self.assertAtomic(self.use)
        dump_engine(self.e)

    def test_independent_source_and_scene_encounter_boundaries_keep_target_clock(self):
        effect = {'type': 'initiative', 'delta': 2, 'target': 'target',
                  'until': {'event': 'turn_end', 'owner': 'target', 'after': 1}}
        self.assertEqual(self.e.apply_effect(self.c, self.b, effect, None, True, 0,
                                            'gm/independent declared initiative'), (1, 0))
        self.use()
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 8)
        self.e.end_of_turn(self.a)
        self.e.end_encounter(self.e.everyone, round_elapsed_seconds=0)
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 8)
        self.e.end_scene(self.e.everyone)
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 8)
        dump_engine(self.e)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.b)
        self.e.end_of_turn(self.b)
        self.assertEqual(self.e.initiative_value(self.b).value, self.base)

    def test_gm_and_fresh_rules_json_restore_preserve_occurrence_and_target_end(self):
        self.use()
        self.e.gm.snapshot('paid')
        payload = json.loads(json.dumps(dump_engine(self.e), ensure_ascii=False))
        loaded = load_engine(Rules(ROOT, ruleset='core'), payload)
        a, b = [next(c for c in loaded.everyone if c.entity_id == uid)
                for uid in (self.a.entity_id, self.b.entity_id)]
        self.assertEqual(loaded.initiative_value(b).value, self.base + 6)
        self.assertEqual(len(TIME.records(b)), 1)
        loaded.end_of_turn(a)
        loaded.start_of_turn(b)
        during = load_engine(Rules(ROOT, ruleset='core'), json.loads(json.dumps(dump_engine(loaded))))
        b2 = next(c for c in during.everyone if c.entity_id == b.entity_id)
        during.end_of_turn(b2)
        self.assertEqual(during.initiative_value(b2).value, self.base)
        self.e.end_of_turn(self.a)
        self.e.start_of_turn(self.b)
        self.e.end_of_turn(self.b)
        self.e.gm.restore('paid')
        self.a, self.b = [next(c for c in self.e.everyone if c.entity_id == uid)
                          for uid in (self.a.entity_id, self.b.entity_id)]
        self.assertEqual(self.e.initiative_value(self.b).value, self.base + 6)
        self.assertEqual(len(TIME.records(self.b)), 1)
        dump_engine(self.e)

    def test_forged_historical_plan_json_and_gm_restore_are_rejected(self):
        self.use()
        payload = json.loads(json.dumps(dump_engine(self.e)))
        changed = 0
        for node in payload['nodes'].values():
            if node['kind'] == 'dict':
                for pair in node['items']:
                    if pair[0] == 'charm_rank' and pair[1] == 3:
                        pair[1] = 4
                        changed += 1
        self.assertEqual(changed, 1)
        with self.assertRaises(ValueError):
            load_engine(Rules(ROOT, ruleset='core'), payload)
        self.e.gm.snapshot('paid')
        snapshot = self.e.gm.snapshots['paid']
        rows = snapshot['engine']['_effect_dispatch_receipts']
        row = next(iter(rows.values()))
        row[D.KEY]['plan']['target_id'] = self.c.entity_id
        self.assertAtomic(lambda: self.e.gm.restore('paid'))
        self.row()[D.KEY]['plan']['adjustment'] = 'decrease'
        with self.assertRaises(ValueError):
            dump_engine(self.e)


if __name__ == '__main__':
    unittest.main()
