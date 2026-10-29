"""Native stage producers share protection without changing raw stage editing."""
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]

from builder import build_pokemon, build_trainer
from engine import Combatant, Rules
import class_actor_state_reactions as REACTIONS
from native_scenario_fixture import prepare_body
import effects as FX
import fashion_items as FASHION
import state_fields as FIELDS
import turn as TURN
import test_category2_class_actor_state_reactions as reaction_fixture
import test_category2_fashion_item_contracts as fashion_fixture
import test_category2_static_equipment_batch as equipment_fixture


class StageEffectBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def world(self, protection, *, fashion_kind='beauty'):
        helper = reaction_fixture.ClassActorStateReactionTests()
        helper.rules = self.rules
        if protection != 'beauty':
            e, owner, attacker, target = helper.fixture(
                feats=[REACTIONS.DEEP_COLD], partner_types=('얼음',),
                partner_moves=('냉동빔', '용해액', '겁주기'))
            for actor, size in ((owner, '중형'), (attacker, '소형'), (target, '소형')):
                prepare_body(e, actor, size=size, offsets=[(0, 0)],
                    reason='GM observes the named stage-protection scene bodies')
            if protection == 'amulet':
                target = Combatant(self.rules, build_trainer(
                    self.rules, 'Amulet wearer', 20,
                    dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 20),
                    moves=[], abilities=[]))
                e.gm.add_combatant(target, pos=(4, 0), side='foe', reason='actual stage protection target')
                equipment_fixture.StaticEquipmentBatchTests().equip(e, target, 'item/클리어참', 'stage-boundary')
                prepare_body(e, target, size='중형', offsets=[(0, 0)],
                    reason='GM observes the actual Amulet wearer body')
            return helper, e, owner, attacker, target, None

        fashion = fashion_fixture.FashionItemContractTests()
        fashion.rules = self.rules
        fashion.setUp()
        item_id = {'beauty': 'item/아름다운-패션-1', 'smart': 'item/슬기로운-패션-1',
                   'cute': 'item/귀여운-패션-1'}[fashion_kind]
        identity = fashion.make(item_id)
        e, target = fashion.e, fashion.p
        owner = Combatant(self.rules, build_trainer(
            self.rules, 'Cold owner', 30,
            dict(hp=40, atk=12, **{'def': 12}, spa=12, spd=12, spe=12),
            moves=[], abilities=[],
            skills={'생존': '숙련', '일반지식': '숙련', '명령': '숙련', '협박': '숙련'},
            extra={'feats': [REACTIONS.DEEP_COLD], 'edges': [], 'type_link_skills': {'풀': '생존'}}))
        attacker = Combatant(self.rules, build_pokemon(
            self.rules, '이상해씨', 20, name='Cold partner',
            moves=['냉동빔', '용해액', '겁주기'], abilities=[],
            extra={'trainer_id': owner.entity_id, 'trainer': owner.name, 'types': ['얼음']}))
        e.gm.add_combatant(owner, pos=(0, 3), side='foe', reason='actual stage source')
        e.gm.add_combatant(attacker, pos=(1, 3), side='foe', reason='actual stage attacker')
        for actor, size in ((fashion.a, '중형'), (fashion.p, '소형'), (fashion.q, '소형'),
                            (owner, '중형'), (attacker, '소형')):
            prepare_body(e, actor, size=size, offsets=[(0, 0)],
                reason='GM observes the named Fashion stage-protection scene bodies')
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        e.start_of_turn(target, initiative_count=20)
        if fashion_kind in ('beauty', 'smart'):
            e.arm_fashion_reaction(target, item_id, instance_id=identity)
        e.end_of_turn(target)
        return helper, e, owner, attacker, target, identity

    def produce(self, producer, world):
        helper, e, owner, attacker, target, _ = world
        if producer == 'effect':
            e.apply_effect(attacker, target,
                {'type': 'stage_change', 'stat': 'atk', 'delta': -1, 'target': 'target'},
                2, True, 0, 'move/울음소리')
            return 'move/울음소리', ('atk',)
        helper.start(e, attacker)
        if producer == 'deep_cold':
            helper.hit(e, attacker, target, '냉동빔')
            event = helper.pending_one(e, owner, REACTIONS.DEEP_COLD)
            result = e.resolve_class_actor_state_reaction(owner, event['id'], use=True)
            self.assertTrue(result['frozen'])
            return REACTIONS.DEEP_COLD, ('atk', 'spa', 'spe')
        e.gm.observe_loyalty(attacker, 6, reason='actual owned Pokemon command')
        e.rng.seed(5)
        move_id = 'move/겁주기' if producer == 'auto_stage' else 'move/용해액'
        if producer == 'auto_stage':
            self.assertEqual(e.r.move_mech(move_id)[1], 'auto')
        e.use_move(attacker, target, move_id)
        return move_id, ('spd',)

    def test_native_producer_protection_table(self):
        for producer in ('effect', 'deep_cold', 'natural_roll', 'auto_stage'):
            for protection in ('none', 'amulet', 'beauty'):
                with self.subTest(producer=producer, protection=protection):
                    world = self.world(protection)
                    _, e, owner, attacker, target, identity = world
                    with patch.object(FX, 'apply_stage_changes', wraps=FX.apply_stage_changes) as boundary:
                        source, stats = self.produce(producer, world)
                    calls = [call for call in boundary.call_args_list if call.kwargs['source_id'] == source]
                    self.assertEqual(len(calls), 1, 'one actual producer effect must reach the shared boundary')
                    self.assertEqual(calls[0].args[1].entity_id,
                        (owner if producer == 'deep_cold' else attacker).entity_id)
                    self.assertEqual(calls[0].args[2].entity_id, target.entity_id)
                    self.assertEqual(calls[0].args[3], dict.fromkeys(stats, -1))
                    # Deep Cold installs Frozen before stage loss; Frozen forbids
                    # the optional Fashion Free Action, so acceptance is not spent.
                    blocked = protection == 'amulet' or (protection == 'beauty' and producer != 'deep_cold')
                    self.assertEqual({stat: target.stages[stat] for stat in stats},
                        dict.fromkeys(stats, 0 if blocked else -1))
                    if protection == 'beauty':
                        obj = e._physical_objects[identity]
                        if producer == 'deep_cold':
                            self.assertIn('얼음', target.conditions)
                            self.assertNotIn(FASHION.STATE, obj)
                            self.assertEqual(FASHION._armed_instance(target, 'beauty'), identity)
                        else:
                            history = obj[FASHION.STATE]['history']
                            self.assertEqual(len(history), 1)
                            self.assertEqual(history[0]['target_id'], calls[0].args[1].entity_id)
                            self.assertIsNone(FASHION._armed_instance(target, 'beauty'))
                    self.assertTrue(e.validate_state()['valid'])

    def test_source_self_condition_and_raw_edit_exceptions(self):
        for kind, protection in (('self', 'amulet'), ('self', 'beauty'),
                                 ('condition', 'amulet'), ('raw', 'amulet')):
            with self.subTest(kind=kind, protection=protection):
                _, e, _, attacker, target, identity = self.world(protection)
                if kind == 'raw':
                    e.change_stage(target, 'atk', -1)
                else:
                    e.apply_effect(target if kind == 'self' else attacker, target,
                        {'type': 'stage_change', 'stat': 'atk', 'delta': -1, 'target': 'target'},
                        2, True, 0, 'condition/test' if kind == 'condition' else 'move/울음소리')
                self.assertEqual(target.stages['atk'], -1)
                if identity is not None:
                    self.assertEqual(FASHION._armed_instance(target, 'beauty'), identity)
                self.assertTrue(e.validate_state()['valid'])

        for kind in ('beauty', 'smart', 'cute'):
            with self.subTest(unavailable_fashion=kind):
                _, e, _, attacker, target, identity = self.world('beauty', fashion_kind=kind)
                e.apply_status(target, '얼음', source='move/냉동빔', applied_by=attacker)
                self.assertIn('얼음', target.conditions)
                actions = len(target._action_history)
                if kind == 'beauty':
                    e.apply_effect(attacker, target,
                        {'type': 'stage_change', 'stat': 'atk', 'delta': -1, 'target': 'target'},
                        2, True, 0, 'move/울음소리')
                    self.assertEqual(target.stages['atk'], -1)
                elif kind == 'smart':
                    enemy = attacker
                    e.gm.set_position(enemy, (target.pos[0] + 1, target.pos[1]),
                        reason='SMART scenario requires this observed enemy adjacent to the mover')
                    self.assertNotEqual(enemy.side, target.side)
                    self.assertTrue(e.adjacent(enemy, target))
                    TURN.trigger_aoo(e, target, 'actual observed opportunity trigger', [enemy])
                    self.assertTrue(enemy.aoo_used)
                else:
                    with self.assertRaisesRegex(ValueError, 'Fashion Free Action is unavailable'):
                        e.activate_fashion_item(target, 'item/귀여운-패션-1', instance_id=identity)
                self.assertEqual(len(target._action_history), actions)
                self.assertNotIn(FASHION.STATE, e._physical_objects[identity])
                if kind != 'cute':
                    self.assertEqual(FASHION._armed_instance(target, kind), identity)
                self.assertTrue(e.validate_state()['valid'])

    def test_all_accuracy_and_evasion_stay_in_the_same_effect_boundary(self):
        _, e, _, attacker, target, _ = self.world('none')
        for stat in ('all', 'acc', 'eva'):
            with self.subTest(stat=stat):
                e.apply_effect(attacker, target,
                    {'type': 'stage_change', 'stat': stat, 'delta': -1, 'target': 'target'},
                    2, True, 0, 'move/울음소리')
        self.assertEqual(target.stages, dict.fromkeys(('atk', 'def', 'spa', 'spd', 'spe'), -1))
        self.assertEqual((target.accuracy_stage, target.evasion_mod), (-1, -1))
        self.assertTrue(e.validate_state()['valid'])

    def test_invalid_source_and_late_reaction_failure_do_not_consume_fashion(self):
        helper, e, owner, attacker, target, identity = self.world('beauty')
        before = e.export_state()
        for source, context, changes in (('', None, {'atk': -1}),
                ('move/울음소리', {'source_id': 'condition/other'}, {'atk': -1}),
                ('move/울음소리', None, {'atk': -1, 'def': 1})):
            with self.subTest(source=source), self.assertRaises(ValueError):
                FX.apply_stage_changes(e, attacker, target, changes, source_id=source, context=context)
            self.assertEqual(e.export_state(), before)
        e.gm.set_ability(attacker, '위협', reason='actual native Ability acquired before its activation')
        helper.start(e, attacker)
        before = e.export_state()
        native = FX.apply_stage_changes

        def fail_after_protection(*args, **kwargs):
            native(*args, **kwargs)
            actual_engine, _, actual_target = args[:3]
            self.assertIsNone(FASHION._armed_instance(actual_target, 'beauty'))
            self.assertEqual(len(actual_engine._physical_objects[identity][FASHION.STATE]['history']), 1)
            raise ValueError('late stage boundary failure')

        with patch.object(FX, 'apply_stage_changes', side_effect=fail_after_protection), self.assertRaisesRegex(ValueError, 'late stage boundary failure'):
            e.activate_ability(attacker, '위협', target)
        self.assertEqual(e.export_state(), before)
        self.assertEqual(FASHION._armed_instance(target, 'beauty'), identity)


if __name__ == '__main__':
    unittest.main()
