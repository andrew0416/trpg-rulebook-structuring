"""Book and CSV Training Orders retain their actual complete producing source."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_training_orders_csv as FIX
from engine import Rules
from native_scenario_fixture import assert_rejected_unchanged
import training_features as TRAIN
import state_codec as CODEC
import state_grants as GRANTS
import world_entities as WORLD
import priority_limited as PRIORITY
import perception_communicate as COMM
import trainer_feature_acquisition as ACQUIRE
import root_resolution as RESOLUTION


class TrainingSourceBindingRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        answers = deepcopy(self.rules.rulings.answers)
        self.addCleanup(setattr, self.rules.rulings, 'answers', answers)

    def scene(self, *, own=False, rules=None):
        fixture = FIX.TrainingOrdersCSVTests(); fixture.r = rules or self.rules
        engine, owner, target, foe = fixture.fixture()
        fixture.open(engine); fixture.audible(engine, owner, target)
        if own: engine.start_of_turn(owner)
        return engine, owner, target, foe

    def valid(self, engine):
        result = engine.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def restore(self, engine, *, fresh=False):
        rules = Rules(ROOT, ruleset='core') if fresh else engine.r
        loaded = CODEC.load_engine(rules, json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False)))
        self.valid(loaded)
        return loaded, WORLD.actor_index(loaded)

    def test_each_book_source_rejects_self_before_communication_or_payment(self):
        for uid in TRAIN.RULES:
            for own in (False, True):
                with self.subTest(feature=uid, own_turn=own):
                    e, a, _, _ = self.scene(own=own)
                    with patch.object(COMM, 'send', side_effect=AssertionError('delivery reached')):
                        assert_rejected_unchanged(e, lambda: e.manual_feat(a, uid, a),
                                                  reason_pattern='book Training Order cannot target its issuer')
                    self.assertFalse(TRAIN.records(a)); self.assertFalse(PRIORITY.records(a))
                    self.assertNotIn('training_order_uses', a.spec)

    def test_both_definitions_keep_complete_identity_and_ordinary_or_limited_payment(self):
        for uid in TRAIN.RULES:
            for csv in (False, True):
                for own in (False, True):
                    with self.subTest(feature=uid, csv=csv, own_turn=own):
                        e, a, p, _ = self.scene(own=own)
                        requested = TRAIN.CSV_CLAUSES[uid] if csv else uid
                        out = e.manual_feat(a, requested, p)
                        binding = out['source_policy_binding']
                        self.assertEqual(binding['selection']['requested_id'], requested)
                        self.assertEqual(binding['selection']['selected_id'], requested)
                        self.assertEqual(binding['definition'], TRAIN.order_definitions(uid)[int(csv)])
                        self.assertEqual(out['source_clause_id'], binding['definition']['values']['source_clause_id'])
                        self.assertEqual(TRAIN.bonuses(TRAIN.active(p)[0]), TRAIN.RULES[uid]['bonuses'])
                        self.assertEqual(p.spec[GRANTS.KEY]['sources'][out['source']]['source_policy_binding'], binding)
                        if own:
                            self.assertEqual(out['priority_receipt']['payment']['kind'], 'ordinary')
                            self.assertEqual(a.budget, {'standard': 0, 'shift': 1, 'swift': 1})
                            self.assertFalse(PRIORITY.records(a))
                        else:
                            self.assertEqual(a.pending_action_loss, {'standard': 1})
                            self.assertEqual(PRIORITY.records(a)[0]['payment']['phase'], 'reserved')
                        self.valid(e)
                        loaded, index = self.restore(e)
                        self.assertEqual(TRAIN.active(index[p.entity_id])[0]['source_policy_binding'], binding)
                        self.assertEqual(index[a.entity_id].spec['training_order_uses'], a.spec['training_order_uses'])

    def test_each_explicit_csv_self_order_reaches_its_real_bonus_consumers(self):
        import initiative as INIT
        import effects_ext as EFFECTS
        import combat_precision_features as PRECISION
        for uid in TRAIN.RULES:
            with self.subTest(feature=uid):
                e, a, _, foe = self.scene()
                out = e.manual_feat(a, TRAIN.CSV_CLAUSES[uid], a)
                self.assertEqual(out['communication']['mode'], 'self_target_exception')
                self.assertEqual(out['source_policy_binding']['selection']['selected_id'], TRAIN.CSV_CLAUSES[uid])
                if uid == TRAIN.AGILITY:
                    self.assertEqual((e.move_profile(a, 'land')[0], INIT.value(e.r, a).value), (7, 14))
                elif uid == TRAIN.BRUTAL:
                    move = e.r.move('move/불꽃세례')
                    self.assertTrue(e.accuracy_check(a, foe, move, fixed_roll=19)[2])
                    self.assertEqual(PRECISION.effect_natural(e, a, move, 10), 11)
                elif uid == TRAIN.FOCUSED:
                    self.assertTrue(e.accuracy_check(a, foe, e.r.move('move/불꽃세례'), fixed_roll=4)[0])
                    self.assertEqual(e.skill_roll(a, '육상', fixed=[1, 1, 1]).total, 5)
                else:
                    self.assertEqual((a.evasion('물리'), EFFECTS.save_dc(e, a, '마비', 11)), (4, 9))
                self.valid(e)
                loaded, index = self.restore(e, fresh=True)
                self.assertEqual(TRAIN.bonuses(TRAIN.active(index[a.entity_id])[0]), TRAIN.RULES[uid]['bonuses'])

    def test_wrong_selected_definition_and_changed_source_reject_without_state_or_rng_change(self):
        e, a, p, _ = self.scene()
        before = CODEC.dump_engine(e)
        with patch.object(e.r, '_selected_rule', return_value=TRAIN.CSV_CLAUSES[TRAIN.BRUTAL]):
            with self.assertRaisesRegex(ValueError, 'selected acquisition source needs its own ownership query'):
                e.manual_feat(a, TRAIN.FOCUSED, p)
        self.assertEqual(CODEC.dump_engine(e), before)
        original = Path.read_bytes
        for name in (TRAIN.FOCUSED, TRAIN.CSV_CLAUSES[TRAIN.FOCUSED]):
            file = 'ch03-skills-edges-feats.md' if name == TRAIN.FOCUSED else 'feats.csv'
            def changed(path):
                raw = original(path)
                return raw + b'\nchanged\n' if path.name == file else raw
            before = CODEC.dump_engine(e)
            with patch.object(Path, 'read_bytes', changed):
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    e.manual_feat(a, name, p)
            self.assertEqual(CODEC.dump_engine(e), before)

    def test_history_uses_retained_policy_without_reselecting_and_rejects_forged_values(self):
        e, a, p, _ = self.scene(own=True)
        out = e.manual_feat(a, TRAIN.CSV_CLAUSES[TRAIN.FOCUSED], p)
        binding = deepcopy(out['source_policy_binding'])
        with patch.object(e.r, 'bind_source_policy', side_effect=AssertionError('history reselected')):
            self.assertEqual(TRAIN.validate_order_history(a), a.spec['training_order_uses'])
            self.assertEqual(TRAIN.active(p)[0]['source_policy_binding'], binding)
        for mutation in ('values', 'selected_id', 'clause', 'row_binding'):
            with self.subTest(mutation=mutation):
                loaded, index = self.restore(e)
                owner, target = index[a.entity_id], index[p.entity_id]
                use = owner.spec['training_order_uses'][0]
                if mutation == 'row_binding':
                    TRAIN.records(target)[0].pop('source_policy_binding')
                else:
                    result = use['result']
                    if mutation == 'values':
                        result['source_policy_binding']['definition']['values']['bonuses']['accuracy'] = 99
                        result['source_policy_binding']['definition_hash'] = RESOLUTION.fingerprint(result['source_policy_binding']['definition'])
                    elif mutation == 'selected_id':
                        result['source_policy_binding']['selection']['selected_id'] = TRAIN.FOCUSED
                    else: result['source_clause_id'] = 'input/ch03-skills-edges-feats.md:708-712'
                    use['integrity'] = ACQUIRE._digest('training-order/use/v1', result)
                self.assertFalse(loaded.validate_state()['valid'])
                with self.assertRaises(ValueError): self.restore(loaded)

    def test_legacy_csv_receipt_restores_without_relabelling_or_minting_a_binding(self):
        e, a, p, _ = self.scene()
        out = e.manual_feat(a, TRAIN.CSV_CLAUSES[TRAIN.FOCUSED], p)
        # Exercise exactly the accepted old producer's schema, retaining its real payment and CSV clause.
        row = TRAIN.records(p)[0]; row.pop('source_policy_binding')
        grant = p.spec[GRANTS.KEY]['sources'][out['source']]
        grant.pop('source_policy_binding'); grant.pop('source_clause_id')
        use = a.spec['training_order_uses'][0]
        use['result'].pop('source_policy_binding')
        use['integrity'] = ACQUIRE._digest('training-order/use/v1', use['result'])
        before = CODEC.dump_engine(e)
        loaded, index = self.restore(e, fresh=True)
        restored = TRAIN.active(index[p.entity_id])[0]
        expected = deepcopy(before)
        root = expected['nodes'][expected['root']['$ref']]
        attrs = expected['nodes'][root['attrs']['$ref']]['items']
        next(pair for pair in attrs if pair[0]=='_root_common_epoch')[1] += 1
        if not any(pair[0]=='_state_codec_authentication' for pair in attrs):
            attrs.append(['_state_codec_authentication',CODEC.AUTH_NOTICE])
        self.assertEqual(CODEC.dump_engine(loaded), expected)
        self.assertEqual(restored['source_clause_id'], TRAIN.CSV_CLAUSES[TRAIN.FOCUSED])
        self.assertNotIn('source_policy_binding', restored)
        self.assertEqual(index[a.entity_id].spec['training_order_uses'], a.spec['training_order_uses'])
        loaded.start_of_turn(index[a.entity_id])
        self.assertFalse(TRAIN.records(index[p.entity_id]))

    def test_actual_whip_free_dispatch_binds_csv_separately_from_logical_feature_ownership(self):
        import test_book_taskmaster_hardened as TASK_FIX
        import taskmaster as TASK
        for csv in (False, True):
            with self.subTest(csv=csv):
                fixture = TASK_FIX.TaskmasterTests(); fixture.rules = self.rules
                fixture.setup(); fixture.all_features(); fixture.combat(fixture.a)
                e, a, p = fixture.e, fixture.a, fixture.p
                e.gm.observe_sensory_environment(a, p, paths={'auditory': True}, present=True,
                                               reason='actual audible Whip Training Order')
                requested = TRAIN.CSV_CLAUSES[TRAIN.BRUTAL] if csv else TRAIN.BRUTAL
                e.manual_feat(a, TASK.PRESS_ACTION, p,
                              adjustment={'stats': ['atk', 'spe'], 'whip': {'order': requested}})
                row = TRAIN.active(p)[0]
                self.assertEqual(row['free_order_payment']['feature'], TRAIN.BRUTAL)
                self.assertEqual(row['source_policy_binding']['selection']['selected_id'], requested)
                self.assertEqual(a.budget, {'standard': 0, 'shift': 1, 'swift': 0})
                self.assertIn('free', a._action_history); self.assertFalse(PRIORITY.records(a))
                self.valid(e); self.restore(e, fresh=True)

    def test_actual_acquired_inspired_keeps_cheer_and_csv_self_exception(self):
        import test_book_cheerleader_bundle as CHEER_FIX
        import cheerleader as CHEER
        for csv, self_target in ((False, False), (True, False), (True, True)):
            with self.subTest(csv=csv, self_target=self_target):
                fixture = CHEER_FIX.CheerleaderBundleTests(); fixture.rules = self.rules; fixture.setup()
                e, a, p = fixture.e, fixture.a, fixture.p
                e.start_of_turn(a)
                requested = TRAIN.CSV_CLAUSES[TRAIN.INSPIRED] if csv else TRAIN.INSPIRED
                target = a if self_target else p
                out = e.manual_feat(a, requested, target)
                self.assertEqual(out['source_policy_binding']['selection']['selected_id'], requested)
                self.assertEqual(TRAIN.bonus(target, 'save'), 2)
                self.assertEqual(len(CHEER.live(target)), int(not self_target))
                self.assertEqual(a.budget['standard'], 0)
                self.valid(e); self.restore(e, fresh=True)

    def test_declared_seven_plus_rank_remains_legal_for_each_source(self):
        from rulings import Rulings
        import skill_modifiers as SKILLS
        for csv in (False, True):
            for rank, dice in ((7, 8), (10, 7)):
                with self.subTest(csv=csv, rank=rank, dice=dice):
                    rules = copy(self.rules); rules.rulings = Rulings()
                    rules.rulings.set_mech('gameplay/skill-rank-dice', 'by_rank_name.초월',
                        {'rank': rank, 'dice': str(dice) + 'd6', 'eng': 'Epic'},
                        reason='actual campaign ordinary rank declaration', scope='campaign', rules=rules)
                    e, a, p, _ = self.scene(own=True, rules=rules)
                    e.gm.set_skill(a, '명령', rank, reason='actual declared Command above Master')
                    requested = TRAIN.CSV_CLAUSES[TRAIN.FOCUSED] if csv else TRAIN.FOCUSED
                    e.manual_feat(a, requested, p)
                    self.assertEqual(SKILLS.rank(e.r, a, '명령')[1:], (str(dice) + 'd6', rank))
                    self.assertEqual(TRAIN.bonus(p, 'skill'), 2)
                    self.valid(e)


if __name__ == '__main__': unittest.main()
