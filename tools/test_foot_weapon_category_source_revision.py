"""C09-066: foot weapons keep Small Melee grants and native feet behavior."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from engine import Engine
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import turn as TURN
import weapon_actions as WEAPONS
import world_entities as WORLD

ROOT = Path(__file__).resolve().parents[1]
CHEAP = 'move/비열한-습격'
GOUGE = 'move/속임수-2'
ELIGIBLE = (CHEAP, 'move/치명적-일격', 'move/맹공', GOUGE,
            'move/쳐부수기', 'move/반격', 'move/썰기', 'move/거인의-일격')
DENIED = ('move/백스윙', 'move/3중공격', 'move/불스아이', 'move/일제사격')


class FootWeaponCategorySourceRevisionTests(unittest.TestCase):
    def world(self):
        def trainer(key, pos, side):
            return {'key': key, 'kind': 'trainer', 'sheet': {
                'name': key, 'level': 30,
                'stats': dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 30),
                'skills': {'전투': 6}, 'moves': ['struggle'], 'abilities': [],
                'pos': pos, 'side': side, 'extra': {'id': 'trainer/' + key}},
                'body': {'size': '중형', 'offsets': [(0, 0)],
                         'reason': 'GM observed this one-cell trainer body'}}
        self.e, actors = NATIVE.prepare_scene(ROOT, ruleset='core', seed=5,
            grid={'width': 8, 'height': 8}, actors=[
                trainer('foot-wielder', (1, 1), 'party'),
                trainer('actual-target', (2, 1), 'opponent')])
        self.a, self.target = actors['foot-wielder'], actors['actual-target']

    def equip(self, moves, *, grade='좋음'):
        return TURN.equip_weapon(self.e, self.a, {
            'name': 'steel-toed boots', 'kind': '발 무기', 'grade': grade,
            'moves': list(moves)})

    def turn(self):
        if self.e._active_turn_actor is not None:
            self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a, initiative_count=20)

    def test_all_eight_small_melee_restrictions_grant_and_prepare_actual_foot_weapons(self):
        self.world()
        for mid in ELIGIBLE:
            with self.subTest(move=mid):
                moves = [CHEAP] if mid == CHEAP else [CHEAP, mid]
                original = deepcopy(self.e.r.move(mid))
                key = self.equip(moves)
                record = self.a.custom_conditions['equipped_weapons'][key]
                self.assertEqual(record['slots'], ['발'])
                self.assertEqual(record['available_moves'], [key, *moves])
                self.assertIn(mid, self.a.moves)
                prepared = WEAPONS.prepare(self.e, self.a, self.e.r.move(mid), key)
                self.assertEqual(prepared['_weapon_attack']['key'], key)
                self.assertEqual(prepared['_weapon_attack']['accuracy_bonus'], 0)
                self.assertEqual(prepared['ac'], original['ac'] + 1)
                self.assertEqual(WEAPONS.damage_bonus(prepared), 1)
                self.assertEqual(prepared['frequency'], original['frequency'])
                self.assertEqual(self.e.r.move(mid), original)
                TURN.unequip_weapon(self.e, self.a, key)
                self.assertFalse(set(moves).intersection(self.a.moves))

    def test_large_and_ranged_only_grants_still_reject_without_a_turn_or_mutation(self):
        self.world()
        self.assertFalse(hasattr(self.a, 'budget'))
        for mid in DENIED:
            with self.subTest(move=mid):
                NATIVE.assert_rejected_unchanged(self.e, lambda: self.equip([mid]),
                    reason_pattern='restricted to another weapon kind')
        self.assertFalse(hasattr(self.a, 'budget'))

    def test_grade_thresholds_include_declared_ordinary_seven_and_ten_without_virtuoso(self):
        self.world()
        for name, rank in (('초월', 7), ('신화', 10)):
            self.e.r.rulings.set_mech('gameplay/skill-rank-dice', 'by_rank_name.' + name,
                {'rank': rank, 'dice': f'{rank}d6', 'eng': 'Ordinary' + str(rank)},
                reason='GM declared this ordinary campaign rank before equipment',
                scope='campaign', rules=self.e.r)
        cases = (('조잡', 6, 0), ('좋음', 3, 0), ('간단', 4, 1),
                 ('간단', 6, 1), ('좋음', 5, 1), ('좋음', 6, 2),
                 ('좋음', 7, 2), ('좋음', 10, 2))
        for grade, rank, count in cases:
            with self.subTest(grade=grade, rank=rank):
                self.e.gm.set_skill(self.a, '전투', rank,
                    reason='GM observed the current ordinary Combat rank')
                key = self.equip([CHEAP, GOUGE], grade=grade)
                self.assertEqual(self.a.custom_conditions['equipped_weapons'][key]['available_moves'],
                                 [key, CHEAP, GOUGE][:count + 1])
                self.assertNotIn('edge/거장', self.a.spec.get('edges', []))
                TURN.unequip_weapon(self.e, self.a, key)

    def test_restored_small_melee_foot_grants_reach_paid_native_cheap_shot_and_gouge(self):
        self.world()
        key = self.equip([CHEAP, GOUGE])
        weapon = deepcopy(self.a.custom_conditions['equipped_weapons'][key]['weapon'])
        self.e.gm.snapshot('small-melee-foot-grants')
        TURN.unequip_weapon(self.e, self.a, key)
        self.e.gm.restore('small-melee-foot-grants', reason='restore the actual foot equipment')
        self.e = CODEC.load_engine(self.e.r, json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index = WORLD.actor_index(self.e)
        self.a, self.target = index[self.a.entity_id], index[self.target.entity_id]
        record = self.a.custom_conditions['equipped_weapons'][key]
        self.assertEqual((record['weapon'], record['slots']), (weapon, ['발']))
        for mid in (CHEAP, GOUGE):
            with self.subTest(move=mid):
                original = deepcopy(self.e.r.move(mid))
                prepared = WEAPONS.prepare(self.e, self.a, original, key)
                self.assertEqual(WEAPONS.range_spec(self.e, prepared)['origin'], 'melee')
                self.assertEqual(prepared['ac'], original['ac'] + 1)
                self.assertEqual(WEAPONS.damage_bonus(prepared), 1)
                if mid == CHEAP:
                    self.assertEqual(self.e.damage_base(self.a, prepared), original['damage_base'] + 1)
                self.turn()
                before = self.target.hp
                with patch.object(Engine, 'd20', return_value=12):
                    damage = self.e.use_move(self.a, self.target, mid, weapon_id=key, set_damage=True)
                self.assertGreater(damage, 0)
                self.assertEqual(before - self.target.hp, damage)
                self.assertEqual((self.a.move_uses[mid], self.a.budget['standard']), (1, 0))
                self.assertEqual(self.e.r.move(mid), original)
                if mid == GOUGE:
                    row = self.a.spec['multi_strike_history'][-1]
                    self.assertEqual((row['move_id'], row['rolls']),
                                     (GOUGE, [[True, 12, False], [True, 12, False]]))
                    actual = list(self.e._move_completions.values())[-1]['target_moves'][self.target.entity_id]
                    self.assertEqual(self.e.damage_base(self.a, actual), original['damage_base'] * 2 + 1)

    def test_actual_use_rechecks_rank_after_grant_before_spending_then_recovers(self):
        self.world()
        key = self.equip([CHEAP, GOUGE])
        self.turn()
        self.e.gm.set_skill(self.a, '전투', 5, reason='GM observed current Expert Combat')
        NATIVE.assert_rejected_unchanged(self.e,
            lambda: self.e.use_move(self.a, self.target, GOUGE, weapon_id=key, set_damage=True),
            reason_pattern='weapon move rank prerequisite not met')
        self.e.gm.set_skill(self.a, '전투', 6, reason='GM observed restored Master Combat')
        with patch.object(Engine, 'd20', return_value=12):
            self.assertGreater(self.e.use_move(self.a, self.target, GOUGE,
                weapon_id=key, set_damage=True), 0)
        self.assertEqual((self.a.move_uses[GOUGE], self.a.budget['standard']), (1, 0))


if __name__ == '__main__':
    unittest.main()
