"""Source-bounded size assertions for S-fan_a-1/-2; native execution pending."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'data/core-rules.json').exists() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT', r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0] = [str(STAGE), str(STAGE / 'engine'), str(STAGE / 'tools'),
                str(ROOT / 'engine'), str(ROOT / 'tools')]
from tools import test_fantasy_weapon_revision as FIXTURE
import combat_hit as HIT

Engine = FIXTURE.Engine
WEAPONS = FIXTURE.WEAPONS
CRAFTED = FIXTURE.CRAFTED
HISTORY = FIXTURE.HISTORY
TRACE = FIXTURE.TRACE
PASSIVE = FIXTURE.PASSIVE
FREQ = FIXTURE.FREQ

# KR ch09:439/441/456; EN core LF8914/8915/8920. Spread is a zero-size control.
# FAN-020 is the additive-grants umbrella, not an additional physical weapon.
SIZE_CASES = (
    ('FAN-034', 'crafted_item/스톰-글러브', 1, 0),
    ('FAN-035', 'crafted_item/스프레드-니들', 0, 0),
    ('FAN-035', 'crafted_item/나인플레임의-스태프', 2, 1),
    ('FAN-036', 'crafted_item/피의-낫', 2, 1),
    ('FAN-041', 'crafted_item/뇌수-창', 2, 1),
    ('FAN-043', 'crafted_item/요정의-엉덩이-차는-거친-불검', 2, 1),
    ('FAN-044', 'crafted_item/캔디-해머', 2, 1),
    ('FAN-045', 'crafted_item/카라단다', 2, 1),
    ('FAN-047', 'crafted_item/여의금고봉', 2, 1),
    ('FAN-048', 'crafted_item/엑스칼리버', 1, 0),
    ('FAN-049', 'crafted_item/카오스-던커', 2, 1),
)

# Explicit source rows, not a sample inferred from names or current policy output.
# Expected values are printed Move DB/AC plus exactly one large-weapon +2/+1.
LARGE_GRANTS = (
    ('FAN-035', 'crafted_item/나인플레임의-스태프', 'move/불꽃튀기기', 9, 3),
    ('FAN-036', 'crafted_item/피의-낫', 'move/베어가르기', 9, 3),
    ('FAN-041', 'crafted_item/뇌수-창', 'move/번개엄니', 9, 4),
    ('FAN-043', 'crafted_item/요정의-엉덩이-차는-거친-불검', 'move/베어가르기', 9, 3),
    ('FAN-045', 'crafted_item/카라단다', 'move/고스트다이브', 11, 3),
    ('FAN-045', 'crafted_item/카라단다', 'move/섀도클로', 9, 3),
    ('FAN-045', 'crafted_item/카라단다', 'move/섀도다이브', 14, 3),
    ('FAN-047', 'crafted_item/여의금고봉', 'move/마하펀치', 6, 3),
    ('FAN-047', 'crafted_item/여의금고봉', 'move/불꽃펀치', 10, 3),
    ('FAN-047', 'crafted_item/여의금고봉', 'move/깨트리기', 10, 3),
    ('FAN-049', 'crafted_item/카오스-던커', 'move/지진', 12, 3),
    ('FAN-049', 'crafted_item/카오스-던커', 'move/그라운드포스', 11, 3),
    ('FAN-049', 'crafted_item/카오스-던커', 'move/단애의칼', 14, 6),
)
SETUP_GRANTS = ('move/고스트다이브', 'move/섀도다이브')


class FantasyWeaponSizeObligationTests(unittest.TestCase):
    # Composition reuses the admitted fixture without inheriting/recollecting its tests.
    fixture = FIXTURE.FantasyWeaponRevisionTests.fixture
    equip = FIXTURE.FantasyWeaponRevisionTests.equip
    entry = FIXTURE.FantasyWeaponRevisionTests.entry
    begin = FIXTURE.FantasyWeaponRevisionTests.begin
    restore = FIXTURE.FantasyWeaponRevisionTests.restore
    facts = FIXTURE.FantasyWeaponRevisionTests.facts

    def assert_native_size(self, e, a, target, mid, uid, db, ac):
        move = WEAPONS.prepare(e, a, e.r.move(mid), uid)
        self.assertEqual(e.damage_base(a, move, target=target), db)
        self.assertEqual(move['ac'], ac)
        rng = WEAPONS.range_spec(e, move, a)
        aim = a.pos if rng.get('shape') == 'burst' else target.pos if rng.get('shape') else None
        hp = target.hp
        with patch.object(Engine, 'd20', return_value=17), \
             patch.object(HIT, 'resolve', wraps=HIT.resolve) as hit:
            dealt = e.use_move_on(a, target, mid, e.everyone,
                                  weapon_id=uid, aim=aim, set_damage=True)
        self.assertGreater(dealt, 0)
        self.assertLess(target.hp, hp)
        facts = self.facts(e, mid)
        self.assertTrue(facts)
        self.assertEqual({row['damage_base'] for row in facts}, {db})
        self.assertTrue(hit.call_args_list)
        self.assertEqual({call.kwargs['accuracy'] for call in hit.call_args_list}, {ac})
        history = HISTORY.last_damage(target)
        self.assertEqual(history['receipt']['source'], mid)
        self.assertEqual(HISTORY.amount(history), hp - target.hp)

    def test_each_crafted_struggle_native_size_is_added_once(self):
        for clause, item, size_db, size_ac in SIZE_CASES:
            with self.subTest(clause=clause, item=item):
                e, a, targets = self.fixture(count=1, element='물')
                uid = self.equip(e, a, item)
                mid = self.entry(a, uid)['struggle_id']
                original = deepcopy(e.r.move(mid))
                prepared = WEAPONS.prepare(e, a, original, uid)
                self.assertEqual(prepared['_weapon_attack']['db_bonus'], 0)
                self.assertEqual(WEAPONS.prepare(e, a, prepared, uid), prepared)
                self.begin(e, a)
                self.assert_native_size(e, a, targets[0], mid, uid, 4 + size_db, 4 + size_ac)
                self.assertEqual(e.r.move(mid), original)

    def test_every_large_recipe_grant_native_size_and_accuracy(self):
        for clause, item, mid, db, ac in LARGE_GRANTS:
            with self.subTest(clause=clause, item=item, move=mid):
                e, a, targets = self.fixture(count=1, element='물')
                target = targets[0]
                e.gm.set_types(target, ['물'], reason='actual nonimmune size-rule recipient')
                uid = self.equip(e, a, item)
                self.assertIn(mid, self.entry(a, uid)['crafted_grants'])
                original = deepcopy(e.r.move(mid))
                prepared = WEAPONS.prepare(e, a, original, uid)
                self.assertEqual(prepared['_weapon_attack']['db_bonus'], 2)
                self.assertEqual(WEAPONS.prepare(e, a, prepared, uid), prepared)
                self.begin(e, a)
                if mid in SETUP_GRANTS:
                    hp = target.hp
                    self.assertEqual(e.use_move_on(a, target, mid, e.everyone,
                                     weapon_id=uid, set_damage=True), 0)
                    self.assertEqual(a.setup_move, mid)
                    self.assertEqual(target.hp, hp)
                    e, a, target = self.restore(e, a, target)
                    TRACE.enable(e)
                    self.begin(e, a)
                self.assert_native_size(e, a, target, mid, uid, db, ac)
                self.assertEqual(e.r.move(mid), original)
                if mid in SETUP_GRANTS:
                    self.assertIsNone(a.setup_move)

    def test_raiju_added_ac_changes_the_real_hit_boundary(self):
        for natural, expected_hit in ((3, False), (4, True)):
            with self.subTest(natural=natural):
                e, a, targets = self.fixture(count=1)
                target = targets[0]
                for stat in ('def', 'spd', 'spe'):
                    e.gm.set_stat(target, stat, value=1, reason='actual zero-evasion recipient')
                uid = self.equip(e, a, 'crafted_item/뇌수-창')
                self.begin(e, a)
                hp = target.hp
                with patch.object(Engine, 'd20', return_value=natural), \
                     patch.object(HIT, 'resolve', wraps=HIT.resolve) as hit:
                    e.use_move(a, target, 'move/번개엄니', weapon_id=uid, set_damage=True)
                self.assertEqual(len(hit.call_args_list), 1)
                inputs = hit.call_args.kwargs
                self.assertEqual((inputs['accuracy'], inputs['evasion'], inputs['modifier']), (4, 0, 0))
                self.assertEqual(target.hp < hp, expected_hit)
                if expected_hit:
                    self.assertEqual(self.facts(e, 'move/번개엄니')[-1]['damage_base'], 9)
                else:
                    self.assertIsNone(HISTORY.last_damage(target))

    def test_additive_base_grants_and_declared_seven_keep_size_separate(self):
        cases = (
            ('crafted_item/여의금고봉', 'move/꿰뚫기', 'move/깨트리기', 7, 4),
            ('crafted_item/나인플레임의-스태프', 'move/렌딩-스펠', 'move/불꽃튀기기', 2, 7),
        )
        for item, base, recipe, combat, occult in cases:
            with self.subTest(item=item):
                e, a, targets = self.fixture(rank=combat, occult=occult, element='물', count=1)
                target = targets[0]
                uid = self.equip(e, a, item, profile={'moves': [base]})
                entry = self.entry(a, uid)
                self.assertIn(base, entry['available_moves'])
                self.assertIn(recipe, entry['crafted_grants'])
                for mid in (base, recipe):
                    prepared = WEAPONS.prepare(e, a, e.r.move(mid), uid)
                    self.assertEqual(e.damage_base(a, prepared), e.r.move(mid)['damage_base'] + 2)
                    self.assertEqual(prepared['ac'], e.r.move(mid)['ac'] + 1)
                mid = entry['struggle_id']
                prepared = WEAPONS.prepare(e, a, e.r.move(mid), uid)
                self.assertEqual(prepared['_weapon_attack']['db_bonus'], 1)
                self.assertEqual(WEAPONS.prepare(e, a, prepared, uid), prepared)
                self.assertEqual(a.spec['skills']['전투'], combat)
                self.assertEqual(a.spec['skills']['오컬트학'], occult)
                self.begin(e, a)
                self.assert_native_size(e, a, target, mid, uid, 7, 4)

    def test_restored_ruyi_granted_move_keeps_size_after_defense_wait(self):
        e, a, targets = self.fixture(count=2)
        first, last = targets
        uid = self.equip(e, a, 'crafted_item/여의금고봉')
        mid = 'move/마하펀치'
        e.gm.set_move(first, 'move/판별', reason='actual learned Detect')
        e.watch_move_defense(first, [{'actor_id': first.entity_id, 'source': 'move/판별'}],
                             reason='actual declared defense')
        self.begin(e, a)
        hp = (first.hp, last.hp)
        with patch.object(Engine, 'd20', return_value=17):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                CRAFTED.activate_ruyi_smite(e, a, first, mid, e.everyone,
                                           mode='burst', size=3, set_damage=True)
        event = e._passive_pending
        e, a, first, last = self.restore(e, a, first, last)
        TRACE.enable(e)
        with patch.object(Engine, 'd20', return_value=17), \
             patch.object(HIT, 'resolve', wraps=HIT.resolve) as hit:
            e.choose_move_defense(event, first, use=True, reason='actual first recipient Detect')
        self.assertEqual(first.hp, hp[0])
        self.assertLess(last.hp, hp[1])
        self.assertEqual({row['damage_base'] for row in self.facts(e, mid)}, {6})
        self.assertTrue(hit.call_args_list)
        self.assertEqual({call.kwargs['accuracy'] for call in hit.call_args_list}, {3})
        self.assertEqual(HISTORY.amount(HISTORY.last_damage(last)), hp[1] - last.hp)
        self.assertEqual(a.move_uses[mid], 1)
        key = 'optional-equipment:ruyi-smite:' + uid
        self.assertEqual(FREQ.state(a)['activations'][key]['used'], 1)
        row = next(row for row in reversed(list(e._move_completions.values()))
                   if row['actor'] is a and row['move_id'] == mid)
        self.assertTrue(row['results'][last.entity_id]['hit'])
        self.assertGreater(row['results'][last.entity_id]['dealt'], 0)
        self.assertTrue(e.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
