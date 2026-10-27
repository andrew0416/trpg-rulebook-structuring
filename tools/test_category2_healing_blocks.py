"""Heal Block and Psychic Noise share one source-owned gain prohibition."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]

from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
import breather as BREATHER
import custom_condition_effects as CUSTOM
import downtime as DOWNTIME
import effect_instances as INSTANCES
import healing_blocks as BLOCKS
import state_codec as CODEC
import status_sets as STATUS
import temporary_hp as TEMP_HP


HEAL_BLOCK = 'move/회복봉인'
PSYCHIC_NOISE = 'move/사이코노이즈'


class HealingBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')
        cls.rules._custom_condition_policy = json.loads(
            (STAGE / 'data/custom-condition-policy.json').read_text(encoding='utf-8'))

    def setUp(self):
        self.engine = Engine(self.rules, 678)

        def actor(name, side, moves=()):
            value = Combatant(self.rules, build_trainer(
                self.rules, name, 30,
                {'hp': 80, 'atk': 20, 'def': 20, 'spa': 25, 'spd': 20, 'spe': 20},
                moves=list(moves), side=side, abilities=[], extra={'types': []}))
            self.engine.gm.add_combatant(value, reason='healing block fixture')
            return value

        self.user = actor('source', 'party', (HEAL_BLOCK, PSYCHIC_NOISE))
        self.target = actor('primary', 'enemy')
        self.secondary = actor('secondary', 'enemy')
        self.other = actor('other source', 'party')
        self.engine.start_round(self.engine.everyone)
        self.engine.start_of_turn(self.user, initiative_count=30)

    def apply(self, source, target=None, actor=None):
        row = CUSTOM.definition(self.rules, source)
        return self.engine.apply_effect(actor or self.user, target or self.target,
            row['raw'], nat=10, hit=True, dealt=0, src=source)

    def state(self):
        actors=[]
        for actor in self.engine.everyone:
            actors.append((actor.entity_id, actor.hp, actor.temp_hp,
                deepcopy(actor.conditions), deepcopy(actor.custom_conditions),
                deepcopy(actor.spec.get('effect_instance_history', [])),
                deepcopy(getattr(actor, 'budget', None)),
                deepcopy(actor.move_uses), deepcopy(actor.counters),
                deepcopy(getattr(actor, '_action_history', None))))
        return deepcopy((self.engine.rng.getstate(), actors,
            getattr(self.engine, '_effect_dispatch_sequence', None),
            len(getattr(self.engine, '_effect_dispatch_receipts', {}))))

    def test_reviewed_rows_and_selected_payloads_are_exact(self):
        expected = {
            HEAL_BLOCK: (678, '86b5df4c629992141b616637cf65d5969aea260f461c2a15342a2eb7586cedb9'),
            PSYCHIC_NOISE: (709, '01044a459f03c64b2c5cb2f621dd1f4948f0266eb791cb3cb7caa4d1a733e335'),
        }
        for source, authority in expected.items():
            with self.subTest(source=source):
                row = CUSTOM.definition(self.rules, source)
                self.assertEqual((row['source_record']['record'],
                    row['source_record']['sha256']), authority)
                actual = [{k:v for k,v in effect.items() if not k.startswith('_')}
                    for effect in self.rules.move_mech(source)[0]['effects_exec']
                    if effect.get('type') == 'custom_condition']
                self.assertIn(row['raw'], actual)

    def test_native_heal_block_stops_every_hp_source_revive_and_temp_hp(self):
        with patch.object(self.engine, 'd20', return_value=10):
            self.engine.use_move(self.user, self.target, HEAL_BLOCK)
        self.assertEqual([row['source'] for row in BLOCKS.records(self.target)], [HEAL_BLOCK])
        self.target.hp -= 20
        hp = self.target.hp
        for source_kind in ('ordinary_item','move','feature','explicit_revive','rest','unspecified'):
            with self.subTest(source_kind=source_kind):
                self.assertEqual(self.engine.heal(self.target, 10, source_kind=source_kind), 0)
                self.assertEqual(self.target.hp, hp)
        self.assertEqual(TEMP_HP.grant(self.engine, self.target, 12), 0)
        self.assertEqual(self.target.temp_hp, 0)
        self.engine.gm.faint(self.target, reason='actual knockout under Heal Block')
        self.assertEqual([row['source'] for row in BLOCKS.records(self.target)], [HEAL_BLOCK])
        self.assertFalse(self.engine.revive(self.target, 20))
        self.assertEqual(self.target.hp, 0)
        self.assertIn('기절', self.target.conditions)

    def test_blocked_gains_preserve_life_sync_and_temporary_hp_preflight(self):
        self.apply(HEAL_BLOCK)
        self.apply(PSYCHIC_NOISE, actor=self.other)
        self.target.hp = 0
        self.assertEqual(self.engine.heal(self.target, 10, source_kind='move'), 0)
        self.assertIn('기절', self.target.conditions)
        self.assertEqual([row['source'] for row in BLOCKS.records(self.target)], [HEAL_BLOCK])

        self.apply(HEAL_BLOCK, target=self.secondary)
        self.secondary.hp = 0
        self.assertFalse(self.engine.revive(self.secondary, 20))
        self.assertIn('기절', self.secondary.conditions)
        self.assertEqual([row['source'] for row in BLOCKS.records(self.secondary)], [HEAL_BLOCK])

        elapsed = self.engine.elapsed_seconds
        self.assertEqual(TEMP_HP.grant(self.engine, self.target, 12,
            round_offset_seconds=3), 0)
        self.assertEqual(self.engine.elapsed_seconds, self.engine.round_start_seconds + 3)
        self.assertGreaterEqual(self.engine.elapsed_seconds, elapsed)
        with patch.object(TEMP_HP, '_policy', side_effect=ValueError('policy still checked')):
            with self.assertRaisesRegex(ValueError, 'policy still checked'):
                TEMP_HP.grant(self.engine, self.target, 12)

    def test_soulless_rest_recovery_uses_the_same_blocker(self):
        engine = Engine(self.rules, 679)
        source = Combatant(self.rules, build_trainer(
            self.rules, 'rest source', 30,
            {'hp':80,'atk':20,'def':20,'spa':25,'spd':20,'spe':20},
            moves=[], side='party', abilities=[], extra={'types':[]}))
        shedinja = Combatant(self.rules, build_pokemon(
            self.rules, '껍질몬', 10, moves=[], abilities=['불가사의부적']))
        engine.gm.add_combatant(source, reason='healing block rest source')
        engine.gm.add_combatant(shedinja, reason='healing block Soulless target')
        row = CUSTOM.definition(self.rules, HEAL_BLOCK)
        engine.apply_effect(source, shedinja, row['raw'], nat=10, hit=True,
            dealt=0, src=HEAL_BLOCK)
        engine.gm.faint(shedinja, reason='actual Soulless knockout under Heal Block')
        self.assertEqual(shedinja.hp, 0)
        import actor_templates as TEMPLATES
        TEMPLATES.observe_soulless_rest_task(
            engine,shedinja,rest_id='blocked-actual-thirty-minute-task',minutes=30,
            reason='GM establishes this actual thirty-minute Extended Action spent resting')
        DOWNTIME.rest(engine,shedinja,30,rest_id='blocked-actual-thirty-minute-task')
        self.assertEqual(shedinja.hp, 0)
        self.assertTrue(shedinja.fainted)
        self.assertEqual([record['source'] for record in BLOCKS.records(shedinja)],
            [HEAL_BLOCK])

    def test_independent_sources_stack_and_same_source_reapplication_is_idempotent(self):
        self.apply(HEAL_BLOCK)
        self.apply(PSYCHIC_NOISE, actor=self.other)
        self.assertEqual({row['source'] for row in BLOCKS.records(self.target)},
            {HEAL_BLOCK, PSYCHIC_NOISE})
        self.apply(HEAL_BLOCK, actor=self.other)
        self.apply(PSYCHIC_NOISE)
        self.assertEqual(len(BLOCKS.records(self.target)), 2)
        STATUS.cure_group(self.engine, self.target, 'volatile')
        self.assertEqual([row['source'] for row in BLOCKS.records(self.target)], [HEAL_BLOCK])
        self.assertTrue(BLOCKS.blocked(self.target))

    def test_heal_block_survives_ordinary_cure_and_only_its_three_boundaries_end_it(self):
        self.apply(HEAL_BLOCK)
        before = CODEC.dump_engine(self.engine)
        with self.assertRaisesRegex(ValueError, 'replacement, Breather, or encounter end'):
            self.engine.cure_status(self.target, '회복봉인')
        self.assertEqual(CODEC.dump_engine(self.engine), before)
        STATUS.cure_group(self.engine, self.target)
        self.assertTrue(BLOCKS.blocked(self.target))

        self.engine.gm.recall(self.target, reason='actual replacement')
        self.assertFalse(BLOCKS.records(self.target))
        ended = self.target.spec['effect_instance_history'][-1][INSTANCES.KEY]['end_event']
        self.assertEqual(ended['boundary'], 'replacement')

        self.setUp();self.apply(HEAL_BLOCK)
        self.engine.end_of_turn(self.user)
        self.engine.start_of_turn(self.target, initiative_count=20)
        BREATHER._recover(self.engine, self.target, None)
        self.assertFalse(BLOCKS.records(self.target))
        ended = self.target.spec['effect_instance_history'][-1][INSTANCES.KEY]['end_event']
        self.assertEqual(ended['boundary'], 'breather')

        self.setUp();self.apply(HEAL_BLOCK)
        self.engine.end_encounter(self.engine.everyone)
        self.assertFalse(BLOCKS.records(self.target))
        ended = self.target.spec['effect_instance_history'][-1][INSTANCES.KEY]['end_event']
        self.assertEqual(ended['boundary'], 'encounter_end')

    def test_psychic_noise_burst_damages_all_but_blocks_only_selected_primary(self):
        hp = (self.target.hp, self.secondary.hp)
        with patch.object(self.engine, 'targets_in_range', return_value=[self.target,self.secondary]), \
             patch.object(self.engine, 'accuracy_check', return_value=(True,10,False)), \
             patch.object(self.engine, 'roll_damage', return_value=5):
            self.engine.use_move_on(self.user, self.target, PSYCHIC_NOISE, self.engine.everyone)
        self.assertLess(self.target.hp, hp[0]);self.assertLess(self.secondary.hp, hp[1])
        self.assertEqual([row['source'] for row in BLOCKS.records(self.target)], [PSYCHIC_NOISE])
        self.assertFalse(BLOCKS.records(self.secondary))
        self.assertEqual(STATUS.afflictions(self.target, 'volatile'), ('회복 봉인',))

    def test_psychic_noise_selected_primary_is_independent_of_area_iteration_order(self):
        hp = (self.target.hp, self.secondary.hp)
        with patch.object(self.engine, 'targets_in_range',
                return_value=[self.secondary,self.target]), \
             patch.object(self.engine, 'accuracy_check', return_value=(True,10,False)), \
             patch.object(self.engine, 'roll_damage', return_value=5):
            self.engine.use_move_on(self.user, self.target, PSYCHIC_NOISE,
                [self.secondary,self.target])
        self.assertLess(self.target.hp, hp[0]);self.assertLess(self.secondary.hp, hp[1])
        self.assertEqual([row['source'] for row in BLOCKS.records(self.target)], [PSYCHIC_NOISE])
        self.assertFalse(BLOCKS.records(self.secondary))

    def test_primary_miss_secondary_hit_does_not_redirect_selected_condition(self):
        hp = (self.target.hp, self.secondary.hp)
        def accuracy(attacker, target, *args, **kwargs):
            return (target is self.secondary, 10 if target is self.secondary else 1, False)
        with patch.object(self.engine, 'targets_in_range', return_value=[self.target,self.secondary]), \
             patch.object(self.engine, 'accuracy_check', side_effect=accuracy), \
             patch.object(self.engine, 'roll_damage', return_value=5):
            self.engine.use_move_on(self.user, self.target, PSYCHIC_NOISE, self.engine.everyone)
        self.assertEqual(self.target.hp, hp[0]);self.assertLess(self.secondary.hp, hp[1])
        self.assertFalse(BLOCKS.records(self.target));self.assertFalse(BLOCKS.records(self.secondary))

    def test_psychic_noise_knockout_does_not_reapply_volatile_block_after_faint_cure(self):
        self.target.hp = 1
        with patch.object(self.engine, 'accuracy_check', return_value=(True,10,False)), \
             patch.object(self.engine, 'roll_damage', return_value=50):
            self.engine.use_move(self.user, self.target, PSYCHIC_NOISE)
        self.assertTrue(self.target.fainted)
        self.assertFalse(BLOCKS.records(self.target))
        self.assertNotIn('회복 봉인', self.target.conditions)

    def test_both_restore_paths_preserve_independent_sources_and_lifetimes(self):
        self.apply(HEAL_BLOCK);self.apply(PSYCHIC_NOISE, actor=self.other)
        self.engine.gm.snapshot('two healing blockers')
        BLOCKS.boundary(self.engine, (self.target,), 'encounter_end')
        STATUS.cure_group(self.engine, self.target, 'volatile')
        self.engine.gm.restore('two healing blockers', reason='restore source-owned blockers')
        self.assertEqual({row['source'] for row in BLOCKS.records(self.target)},
            {HEAL_BLOCK, PSYCHIC_NOISE})

        payload = json.loads(json.dumps(CODEC.dump_engine(self.engine), ensure_ascii=False))
        loaded = CODEC.load_engine(self.rules, payload)
        target = next(actor for actor in loaded.everyone if actor.entity_id == self.target.entity_id)
        self.assertEqual({row['source'] for row in BLOCKS.records(target)},
            {HEAL_BLOCK, PSYCHIC_NOISE})
        STATUS.cure_group(loaded, target, 'volatile')
        self.assertEqual([row['source'] for row in BLOCKS.records(target)], [HEAL_BLOCK])
        loaded.gm.recall(target, reason='restored replacement')
        self.assertFalse(BLOCKS.records(target))
        self.assertTrue(loaded.validate_state()['valid'])

    def test_preflight_and_boundary_failures_do_not_partially_mutate_state(self):
        before = self.state()
        original = deepcopy(self.rules._custom_condition_policy['sources'][HEAL_BLOCK])
        try:
            self.rules._custom_condition_policy['sources'][HEAL_BLOCK]['raw']['until'] = 'changed'
            with self.assertRaisesRegex(ValueError, 'custom_condition'):
                self.engine.use_move(self.user, self.target, HEAL_BLOCK)
        finally:
            self.rules._custom_condition_policy['sources'][HEAL_BLOCK] = original
        self.assertEqual(self.state(), before)

        self.apply(HEAL_BLOCK);self.apply(PSYCHIC_NOISE, actor=self.other)
        psychic = next(row for row in BLOCKS.records(self.target) if row['source']==PSYCHIC_NOISE)
        lifetime = deepcopy(psychic[INSTANCES.KEY]['lifetime'])
        psychic[INSTANCES.KEY]['lifetime'] = {'boundary':'corrupt'}
        with self.assertRaisesRegex(ValueError, 'lifetime authority'):
            BLOCKS.boundary(self.engine, (self.target,), 'encounter_end')
        self.assertEqual({row['source'] for row in BLOCKS.records(self.target)},
            {HEAL_BLOCK, PSYCHIC_NOISE})
        psychic[INSTANCES.KEY]['lifetime'] = lifetime
        self.assertTrue(self.engine.validate_state()['valid'])

        self.apply(HEAL_BLOCK, target=self.secondary)
        target_record = next(row for row in BLOCKS.records(self.target)
            if row['source'] == HEAL_BLOCK)
        secondary_record = BLOCKS.records(self.secondary)[0]
        history = self.secondary.spec.get('effect_instance_history')
        self.secondary.spec['effect_instance_history'] = 'corrupt'
        with self.assertRaisesRegex(ValueError, 'history must be a list'):
            BLOCKS.boundary(self.engine, (self.target, self.secondary), 'encounter_end')
        self.assertIn(target_record, BLOCKS.records(self.target))
        self.assertIn(secondary_record, BLOCKS.records(self.secondary))
        if history is None:self.secondary.spec.pop('effect_instance_history')
        else:self.secondary.spec['effect_instance_history'] = history

        secondary_record[INSTANCES.KEY]['holder_id'] = self.target.entity_id
        with self.assertRaisesRegex(ValueError, 'different holder'):
            BLOCKS.boundary(self.engine, (self.target, self.secondary), 'encounter_end')
        self.assertIn(target_record, BLOCKS.records(self.target))
        self.assertIn(secondary_record, BLOCKS.records(self.secondary))
        secondary_record[INSTANCES.KEY]['holder_id'] = self.secondary.entity_id
        self.assertTrue(self.engine.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
