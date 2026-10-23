"""Native consumers of the five reviewed scene-limited optional effects."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
STAGE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE/'engine'), str(ROOT/'engine')]
import optional_move_modes as MODES
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from grid import Grid

MOVES = ['move/'+name for name in ('꽃가루경단', '다크홀', '섬뜩한주문', '암석액스', '백귀야행')]


class OptionalMoveModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = Rules(str(ROOT), ruleset='core')

    def setUp(self): self.make_world()

    def make_world(self):
        self.e = Engine(self.r, seed=4021)
        self.e.grid = Grid(30, 30)
        self.p = Combatant(self.r, build_pokemon(self.r, '이상해씨', 30,
            moves=MOVES, abilities=['심록']))
        self.p.pos = (10, 10)
        self.e.gm.add_combatant(self.p)
        self.t = self.add_target((11, 10))
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.p, initiative_count=20)
        self.e.d20 = lambda: 17

    def add_target(self, pos, *, ally=False):
        actor = Combatant(self.r, build_pokemon(self.r, '꼬부기', 60,
            moves=['move/몸통박치기'], abilities=['급류'],
            side=self.p.side if ally else 'wild'))
        actor.pos = pos
        self.e.gm.add_combatant(actor)
        return actor

    def select(self, mid):
        return self.e.gm.choose_optional_move_effect(self.p, mid, reason='explicit player choice')

    def next_turn(self):
        self.e.end_of_turn(self.p)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.p, initiative_count=20)

    def test_all_five_normal_modes_preserve_damage_and_secondary_effects(self):
        for mid in MOVES:
            with self.subTest(move=mid):
                if mid != MOVES[0]: self.make_world()
                self.e.d20 = lambda: 18
                hp = self.t.hp
                dealt = self.e.use_move(self.p, self.t, mid, set_damage=True)
                self.assertEqual(MODES.history(self.p), [])
                self.assertEqual(self.e.effect_stats['held'], 0, '\n'.join(self.e.log_lines))
                if mid == 'move/다크홀':
                    self.assertEqual(self.t.hp, hp)
                    self.assertIn('잠듦', self.t.conditions)
                else:
                    self.assertGreater(dealt, 0, '\n'.join(self.e.log_lines))
                    self.assertLess(self.t.hp, hp)
                if mid == 'move/섬뜩한주문': self.assertNotIn('사슬묶기', self.t.conditions)
                if mid == 'move/암석액스':
                    self.assertNotIn('조이기', self.t.conditions)
                    self.assertTrue(any('치명타' in line for line in self.e.log_lines))
                if mid == 'move/백귀야행': self.assertIn('화상', self.t.conditions)

    def test_pollen_puff_heals_current_maximum_and_has_healing_keyword(self):
        ally = self.add_target((11, 11), ally=True)
        ally.injuries = 2
        ally.hp = 10
        expected = 10 + ally.max_hp//2
        mid = 'move/꽃가루경단'
        self.select(mid)
        observed = []
        original = self.e.accuracy_check
        def observe(actor, target, move, *args, **kwargs):
            observed.append((move['class'], move['keywords']))
            return original(actor, target, move, *args, **kwargs)
        self.e.accuracy_check = observe
        dealt = self.e.use_move(self.p, ally, mid, set_damage=True)
        self.assertEqual(dealt, 0)
        self.assertEqual(ally.hp, expected, '\n'.join(self.e.log_lines))
        self.assertEqual(observed, [('변화', ['치유'])])
        self.assertEqual(MODES.history(self.p)[0]['use']['boundary'], 'activation')

    def test_invalid_choice_and_ineligible_healing_leave_cost_and_choice_unchanged(self):
        before = deepcopy(self.t.spec)
        with self.assertRaisesRegex(ValueError, 'currently know'):
            self.e.gm.choose_optional_move_effect(self.t, MOVES[0], reason='unlearned')
        self.assertEqual(self.t.spec, before)
        self.select(MOVES[0])
        before = deepcopy(self.p.spec)
        uses = deepcopy(self.p.move_uses)
        with self.assertRaisesRegex(ValueError, 'actual ally'):
            self.e.use_move(self.p, self.t, MOVES[0])
        self.assertEqual(self.p.spec, before)
        self.assertEqual(self.p.move_uses, uses)
        self.assertIsNone(MODES.history(self.p)[0]['use'])

    def test_dark_void_friendly_burst_uses_one_roll_and_one_scene_receipt(self):
        second = self.add_target((14, 10))
        ally = self.add_target((12, 10), ally=True)
        far = self.add_target((16, 10))
        mid = 'move/다크홀'
        self.select(mid)
        rolls = []
        def roll(): rolls.append(17); return 17
        self.e.d20 = roll
        self.e.use_move_on(self.p, self.t, mid, self.e.everyone)
        self.assertIn('잠듦', self.t.conditions)
        self.assertIn('잠듦', second.conditions)
        for actor in (self.p, ally, far): self.assertNotIn('잠듦', actor.conditions)
        self.assertEqual(len(rolls), 1)
        self.assertEqual(self.p.move_uses[mid], 1)
        self.assertEqual(set(MODES.history(self.p)[0]['use']['target_ids']),
                         {self.t.entity_id, second.entity_id})
        with self.assertRaisesRegex(ValueError, 'already selected'):
            self.select(mid)

    def test_infernal_parade_freezes_afflicted_target_and_db_for_whole_activation(self):
        second = self.add_target((12, 10))
        self.e.apply_status(second, '독')
        mid = 'move/백귀야행'
        self.select(mid)
        observed = []
        original = self.e.damage_base
        def observe(actor, move, *args, **kwargs):
            db = original(actor, move, *args, **kwargs)
            observed.append(db)
            return db
        self.e.damage_base = observe
        self.e.use_move_on(self.p, self.t, mid, self.e.everyone)
        self.assertGreaterEqual(len(observed), 2)
        self.assertEqual(set(observed), {12})
        self.assertIn('화상', self.t.conditions)
        self.assertEqual(len(MODES.history(self.p)), 1)
        self.assertEqual(self.p.move_uses[mid], 1)
        self.assertEqual(set(MODES.history(self.p)[0]['use']['target_ids']),
                         {t.entity_id for t in (self.t, second)})

    def test_infernal_parade_cannot_use_its_own_future_burn_as_prerequisite(self):
        mid = 'move/백귀야행'
        self.select(mid)
        uses = deepcopy(self.p.move_uses)
        hp = self.t.hp
        with self.assertRaisesRegex(ValueError, 'previously afflicted'):
            self.e.use_move_on(self.p, self.t, mid, self.e.everyone)
        self.assertEqual(self.p.move_uses, uses)
        self.assertEqual(self.t.hp, hp)
        self.assertNotIn('화상', self.t.conditions)
        self.assertIsNone(MODES.history(self.p)[0]['use'])

    def test_eerie_spell_disables_actual_last_move_and_normal_attack_does_not(self):
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.t, initiative_count=10)
        self.e.use_move(self.t, self.p, 'move/몸통박치기', set_damage=True)
        self.e.end_of_turn(self.t)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.p, initiative_count=20)
        mid = 'move/섬뜩한주문'
        self.select(mid)
        self.e.use_move(self.p, self.t, mid, set_damage=True)
        self.assertIn('사슬묶기', self.t.conditions)
        import condition_instances as CONDITIONS
        self.assertFalse(CONDITIONS.move_allowed(self.e, self.t, self.r.move('move/몸통박치기'))[0])
        self.e.cure_status(self.t, '사슬묶기')
        self.next_turn()
        self.e.use_move(self.p, self.t, mid, set_damage=True)
        self.assertNotIn('사슬묶기', self.t.conditions)

    def test_stone_axe_miss_keeps_choice_then_hit_owns_vortex_lifetime(self):
        mid = 'move/암석액스'
        self.select(mid)
        self.e.d20 = lambda: 1
        self.e.use_move(self.p, self.t, mid)
        self.assertIsNone(MODES.history(self.p)[0]['use'])
        self.assertNotIn('조이기', self.t.conditions)
        self.next_turn()
        self.next_turn()  # Printed EOT frequency remains independent of the scene mode.
        self.e.d20 = lambda: 18
        self.e.use_move(self.p, self.t, mid, set_damage=True)
        self.assertEqual(MODES.history(self.p)[0]['use']['boundary'], 'hit')
        self.assertTrue({'조이기', '둔화', '수렁'} <= self.t.conditions)
        before = self.t.hp
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.t, initiative_count=10)
        self.assertEqual(self.t.hp, before-self.e.tick(self.t))
        self.e.cure_status(self.t, '조이기')
        self.assertFalse({'조이기', '둔화', '수렁'} & self.t.conditions)

    def test_pending_used_and_expired_modes_round_trip_and_reject_tampering(self):
        self.select('move/다크홀')
        self.select('move/섬뜩한주문')
        self.e.gm.snapshot('optional-pending')
        self.e.gm.restore('optional-pending')
        del self.e.d20
        blob = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        e = Engine.import_state(self.r, blob)
        actor = next(a for a in e.everyone if a.entity_id == self.p.entity_id)
        target = next(a for a in e.everyone if a.entity_id == self.t.entity_id)
        e.d20 = lambda: 1
        e.use_move_on(actor, target, 'move/다크홀', e.everyone)
        self.assertIsNotNone(MODES.history(actor)[0]['use'])
        del e.d20
        used_blob = json.loads(json.dumps(e.export_state(), ensure_ascii=False))
        restored = Engine.import_state(self.r, used_blob)
        restored_actor = next(a for a in restored.everyone if a.entity_id == actor.entity_id)
        self.assertEqual(MODES.history(restored_actor), MODES.history(actor))
        e.end_of_turn(actor)
        e.end_scene(e.everyone)
        fresh = e.gm.choose_optional_move_effect(actor, 'move/다크홀', reason='new scene')
        self.assertEqual(fresh['scene'], 1)
        self.assertIsNone(MODES._choice(e, actor, target, 'move/섬뜩한주문'))
        actor.spec[MODES.KEY]['history'][0]['source_row_sha256'] = 'forged'
        with self.assertRaisesRegex(ValueError, 'world reference integrity'):
            e.export_state()

    def test_area_selection_and_on_hit_receipts_require_native_producers(self):
        self.select('move/다크홀')
        uses = deepcopy(self.p.move_uses)
        with self.assertRaisesRegex(ValueError, 'actual use_move_on'):
            self.e.use_move(self.p, self.t, 'move/다크홀')
        self.assertEqual(self.p.move_uses, uses)
        self.assertIsNone(MODES.history(self.p)[0]['use'])
        self.select('move/암석액스')
        move, _ = MODES.project(self.e, self.p, self.t,
            self.r.move('move/암석액스'), self.r.move_mech('move/암석액스')[0])
        with self.assertRaisesRegex(ValueError, 'actual unfinished Move'):
            MODES.on_hit(self.e, self.p, self.t, move, None)
        self.assertIsNone(MODES.history(self.p)[1]['use'])

    def test_exact_source_policy_and_changed_definition_refusal(self):
        from unittest.mock import patch
        policy = MODES.policy(self.r)
        registry = json.loads((ROOT/'data/verification/category2-csv-abilities-moves-status.json').read_text(encoding='utf-8'))
        rows = {row['row_id']: row for row in registry['rows']}
        self.assertEqual({row['clause_id'] for row in policy['moves'].values()},
            {'C2CSV-MOVE-R0016', 'C2CSV-MOVE-R0042', 'C2CSV-MOVE-R0307',
             'C2CSV-MOVE-R0669', 'C2CSV-MOVE-R0752', 'C2CSV-MOVE-R0632'})
        for mid, entry in policy['moves'].items():
            self.assertEqual(entry['source_row_sha256'], rows[entry['clause_id']]['source_row_sha256'])
            self.assertEqual(entry['source_effect'], rows[entry['clause_id']]['source_effect'])
            self.assertIsNotNone(MODES.definition(self.r, mid))
        before = deepcopy(self.p.spec)
        with patch.object(self.r, 'move_mech', return_value=({'effects_exec': []}, 'changed')):
            with self.assertRaisesRegex(ValueError, 'definition changed'):
                self.select('move/꽃가루경단')
        self.assertEqual(self.p.spec, before)

    def test_trainer_who_knows_move_uses_the_same_choice_and_restore_contract(self):
        from builder import build_trainer
        self.e.end_of_turn(self.p)
        trainer = Combatant(self.r, build_trainer(self.r, 'known-move-user', 30,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            moves=['move/꽃가루경단'], pos=(10, 11)))
        self.e.gm.add_combatant(trainer)
        self.e.start_of_turn(trainer, initiative_count=15)
        self.p.hp = 10
        expected = min(self.p.max_hp, 10+self.p.max_hp//2)
        self.e.gm.choose_optional_move_effect(trainer, 'move/꽃가루경단', reason='known trainer Move')
        self.e.use_move(trainer, self.p, 'move/꽃가루경단')
        self.assertEqual(self.p.hp, expected)
        self.assertIsNotNone(MODES.history(trainer)[0]['use'])
        del self.e.d20
        restored = Engine.import_state(self.r, json.loads(json.dumps(self.e.export_state())))
        owner = next(a for a in restored.everyone if a.entity_id == trainer.entity_id)
        self.assertEqual(MODES.history(owner), MODES.history(trainer))


if __name__ == '__main__': unittest.main()
