"""S-cls_c-1/2: native Trapper item action and kind-associated Naturewalk immunity.

Sources: ch04:2156-2164, ch07:43-45, ch09:964; English core 1.05 p149/p227.
Historical receipts remain historical facts; they never authorize a new deployment.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from native_scenario_fixture import assert_rejected_unchanged
import book_survivalist_fixture as FIX
import state_codec as CODEC
import state_grants as G
import survivalist_class as SC
import turn as TURN

WALL = tuple((5, y) for y in range(8))


class SurvivalistTrapsSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        SC.definitions(self.rules)

    def create(self, engine, trainer, tool_id='tool', terrain='grassland'):
        FIX.env(engine, trainer, terrain)
        return engine.survivalist_activity(
            trainer, 'create_trap_tool', tool_id=tool_id, terrain_name=terrain,
            minutes=30, reason='actual crafting in the observed terrain')

    def deploy(self, engine, trainer, tool_id='tool', cells=WALL):
        return engine.survivalist_activity(
            trainer, 'deploy_trap_tool', tool_id=tool_id, cells=list(cells),
            reason='actual consumable item use')

    def instances(self, engine):
        return [row for envelope in engine.hazards.values() for row in envelope['instances']]

    def test_default_item_use_needs_no_ruling_and_pays_one_standard(self):
        world = FIX.scene(self.rules)
        engine, trainer = world['engine'], world['trainer']
        self.create(engine, trainer)
        FIX.battle(engine, trainer)
        result = self.deploy(engine, trainer)
        self.assertEqual((result['used']['action'], result['used']['ruling']), ('standard', None))
        self.assertEqual((trainer.budget['standard'], trainer.budget['swift']), (0, 1))
        self.assertEqual(len(self.instances(engine)), 8)
        self.assertTrue(engine.validate_state()['valid'])

    def test_old_swift_and_free_rulings_cannot_reduce_a_new_deployment_cost(self):
        for action in ('swift', 'free'):
            with self.subTest(old_ruling=action):
                world = FIX.scene(self.rules)
                engine, trainer = world['engine'], world['trainer']
                self.create(engine, trainer)
                FIX.ruling(engine, SC.DEPLOY_RULING, action)
                FIX.battle(engine, trainer)
                used = self.deploy(engine, trainer)['used']
                self.assertEqual((used['action'], used['ruling']), ('standard', None))
                self.assertEqual((trainer.budget['standard'], trainer.budget['swift']), (0, 1))

    def test_no_standard_action_rejects_without_consuming_tool_hazards_or_rng(self):
        world = FIX.scene(self.rules)
        engine, trainer = world['engine'], world['trainer']
        self.create(engine, trainer)
        FIX.ruling(engine, SC.DEPLOY_RULING, 'free')
        FIX.battle(engine, trainer)
        self.assertTrue(TURN.spend(engine, trainer, 'standard', 'actual earlier Standard Action'))
        assert_rejected_unchanged(
            engine, lambda: self.deploy(engine, trainer),
            reason_pattern='Trapper deployment action unavailable')
        self.assertEqual((trainer.spec[SC.TOOLS][0]['status'], trainer.spec[SC.TOOLS][0]['used']), ('ready', None))
        self.assertEqual(engine.hazards, {})

    def test_each_hazard_kind_accepts_naturewalk_for_its_other_associated_terrains(self):
        cases = (
            ('grassland', 'dust', '사막'),
            ('forest', 'tangle', '습지'),
            ('ocean', 'slick', '툰드라'),
            ('mountain', 'abrasion', '동굴'),
            ('mountain', 'abrasion', '도시'),
        )
        for terrain, kind, naturewalk in cases:
            with self.subTest(creation=terrain, naturewalk=naturewalk):
                world = FIX.scene(self.rules)
                engine, trainer, foe = world['engine'], world['trainer'], world['foe']
                tool = self.create(engine, trainer, terrain=terrain)
                FIX.battle(engine, trainer)
                self.deploy(engine, trainer)
                G.grant(foe, 'capabilities', 'Naturewalk(' + naturewalk + ')', 'fixture:trap-naturewalk', 'fixture')
                before = deepcopy(foe.stages)
                FIX.next_turn(engine, trainer, foe, count=15)
                engine.approach(foe, trainer)
                self.assertLess(foe.pos[0], 5, 'the foe actually crosses the Hazard wall')
                self.assertFalse({'둔화', '실명', '구속', '취약'} & foe.conditions)
                self.assertEqual(foe.stages, before)
                self.assertEqual(len(self.instances(engine)), 8)
                self.assertEqual({row['source_id'] for row in self.instances(engine)}, {SC.TRAPPER + '#' + kind + '#' + terrain})
                self.assertEqual((tool['terrain'], trainer.spec[SC.TOOLS][0]['terrain']), (terrain, terrain))
                self.assertTrue(engine.validate_state()['valid'])

    def test_unrelated_naturewalk_still_receives_the_creation_terrain_effect(self):
        world = FIX.scene(self.rules)
        engine, trainer, foe = world['engine'], world['trainer'], world['foe']
        self.create(engine, trainer)
        FIX.battle(engine, trainer)
        self.deploy(engine, trainer)
        G.grant(foe, 'capabilities', 'Naturewalk(숲)', 'fixture:trap-naturewalk', 'fixture')
        FIX.next_turn(engine, trainer, foe, count=15)
        engine.approach(foe, trainer)
        self.assertLess(foe.pos[0], 5)
        self.assertTrue({'둔화', '실명'} <= foe.conditions)
        self.assertEqual(len(self.instances(engine)), 7)

    def test_associated_terrain_immunity_survives_json_and_gm_restore_with_the_creation_identity(self):
        world = FIX.scene(self.rules)
        engine, trainer, foe = world['engine'], world['trainer'], world['foe']
        self.create(engine, trainer)
        FIX.battle(engine, trainer)
        self.deploy(engine, trainer)
        G.grant(foe, 'capabilities', 'Naturewalk(사막)', 'fixture:trap-naturewalk', 'fixture')
        engine.gm.snapshot('dust-with-desert-naturewalk')
        loaded, index = FIX.restore(self.rules, engine)
        restored_trainer, restored_foe = index[trainer.entity_id], index[foe.entity_id]
        FIX.next_turn(loaded, restored_trainer, restored_foe, count=15)
        loaded.approach(restored_foe, restored_trainer)
        self.assertLess(restored_foe.pos[0], 5)
        self.assertFalse({'둔화', '실명'} & restored_foe.conditions)
        self.assertEqual(len(self.instances(loaded)), 8)
        engine.gm.restore('dust-with-desert-naturewalk')
        FIX.next_turn(engine, trainer, foe, count=15)
        engine.approach(foe, trainer)
        self.assertFalse({'둔화', '실명'} & foe.conditions)
        self.assertEqual({row['source_id'] for row in self.instances(engine)}, {SC.TRAPPER + '#dust#grassland'})
        self.assertEqual(trainer.spec[SC.TOOLS][0]['terrain'], 'grassland')
        self.assertTrue(engine.validate_state()['valid'])

    def test_deployment_under_a_foe_waits_for_actual_entry_before_consuming_a_metre(self):
        world = FIX.scene(self.rules)
        engine, trainer, foe = world['engine'], world['trainer'], world['foe']
        self.create(engine, trainer)
        FIX.battle(engine, trainer)
        cells = tuple((5, y) for y in range(6)) + ((7, 2), (8, 2))
        self.deploy(engine, trainer, cells=cells)
        self.assertEqual(foe.pos, (8, 2))
        self.assertFalse({'둔화', '실명'} & foe.conditions)
        self.assertEqual(len(self.instances(engine)), 8)
        # Fix the actual route: equal-cost diagonal paths need not cross (7, 2).
        for cell in ((7, 1), (7, 3)):
            engine.gm.set_terrain(cell, 'blocking', reason='observed corridor into the tested trap metre')
        FIX.next_turn(engine, trainer, foe, count=15)
        engine.approach(foe, trainer)
        self.assertTrue({'둔화', '실명'} <= foe.conditions)
        self.assertNotIn((7, 2), [row['cell'] for row in self.instances(engine)])
        self.assertIn((8, 2), [row['cell'] for row in self.instances(engine)])

    def test_unruled_new_receipts_cannot_claim_a_swift_or_free_payment(self):
        world = FIX.scene(self.rules)
        engine, trainer = world['engine'], world['trainer']
        self.create(engine, trainer)
        FIX.battle(engine, trainer)
        self.deploy(engine, trainer)
        engine.gm.snapshot('current-standard-payment')
        for action in ('swift', 'free'):
            with self.subTest(tampered_action=action):
                trainer.spec[SC.TOOLS][0]['used']['action'] = action
                self.assertFalse(engine.validate_state()['valid'])
                with self.assertRaisesRegex(ValueError, 'Trapper deployment receipt changed'):
                    CODEC.dump_engine(engine)
                engine.gm.restore('current-standard-payment')
                self.assertEqual(trainer.spec[SC.TOOLS][0]['used']['action'], 'standard')

    def test_historical_ruling_receipts_roundtrip_unchanged_without_repayment_or_reuse(self):
        world = FIX.scene(self.rules)
        engine, trainer = world['engine'], world['trainer']
        self.create(engine, trainer, 'old-tool')
        self.create(engine, trainer, 'new-tool')
        FIX.battle(engine, trainer)
        receipt = self.deploy(engine, trainer, 'old-tool')['used']
        engine.end_of_turn(trainer)
        engine.end_round()
        FIX.battle(engine, trainer)
        budget, history = deepcopy(trainer.budget), deepcopy(trainer._action_history)
        for action in ('standard', 'swift', 'free'):
            with self.subTest(historical_payment=action):
                FIX.ruling(engine, SC.DEPLOY_RULING, action)
                payload = json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False))
                # An old-save fixture changes only the historical receipt; the current turn is native and fresh.
                nodes = [node for node in payload['nodes'].values() if node['kind'] == 'dict'
                         and ['region_id', receipt['region_id']] in node['items']
                         and ['action', 'standard'] in node['items'] and ['ruling', None] in node['items']]
                self.assertEqual(len(nodes), 1)
                for pair in nodes[0]['items']:
                    if pair[0] == 'action':
                        pair[1] = action
                    elif pair[0] == 'ruling':
                        pair[1] = SC.DEPLOY_RULING
                loaded = CODEC.load_engine(self.rules, payload)
                import world_entities as W
                actor = W.actor_index(loaded)[trainer.entity_id]
                expected = dict(receipt, action=action, ruling=SC.DEPLOY_RULING)
                self.assertEqual(actor.spec[SC.TOOLS][0]['used'], expected)
                self.assertEqual([row['answer'] for row in loaded.rulings.answers if row['key'] == SC.DEPLOY_RULING], [action])
                self.assertEqual((actor.budget, actor._action_history), (budget, history))
                loaded.gm.snapshot('historical-deployment')
                again, index = FIX.restore(self.rules, loaded)
                self.assertEqual(index[trainer.entity_id].spec[SC.TOOLS][0]['used'], expected)
                assert_rejected_unchanged(
                    loaded, lambda: self.deploy(loaded, actor, 'old-tool'), reason_pattern='already used')
                new = self.deploy(loaded, actor, 'new-tool')['used']
                self.assertEqual((new['action'], new['ruling'], actor.budget['standard']), ('standard', None, 0))
                loaded.gm.restore('historical-deployment')
                self.assertEqual(actor.spec[SC.TOOLS][0]['used'], expected)
                self.assertEqual((actor.budget, actor._action_history), (budget, history))
                self.assertTrue(loaded.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
