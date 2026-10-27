"""C09-062 actual GM choices; existing weapon/transaction owners stay in use."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine')]
from engine import Rules, Engine, Combatant
from builder import build_trainer
from grid import Grid
import improvised_weapons as IW
import optional_weapon_framework as FW
import weapon_actions as WEAPONS
import world_entities as W
import turn as TURN
import move_completion as COMPLETE


class ImprovisedWeaponTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='all')
        import setup_move_state, stellar_tera_blast
        setup_move_state._policy(cls.r)
        stellar_tera_blast._policy(cls.r)

    def fixture(self):
        e = Engine(self.r, seed=9062)
        e.grid = Grid(25, 15)
        actors = []
        for n in range(2):
            c = Combatant(self.r, build_trainer(self.r, 'improvised-' + str(id(e)) + '-' + str(n), 30,
                {'hp': 100, 'atk': 20, 'def': 20, 'spa': 20, 'spd': 20, 'spe': 20},
                extra={'moves': ['move/몸통박치기'], 'abilities': [], 'feats': [],
                       'skills': {'전투': 4, '집중': 4}, 'movement': {'land': 6}, 'movement_basis': 'current'}))
            c.pos = (2 + n, 2)
            c.side = 'party' if n == 0 else 'wild'
            e.gm.add_combatant(c)
            actors.append(c)
        return e, *actors

    def weapon(self, e, a, uid='object/pillow', *, kind='소형 근접무기', moves=(),
               configure=True, ac_mode='accuracy_roll', ac_delta=0, db_delta=-1, break_after_attack=False):
        W.register_object(e, uid, location={'kind': 'unknown'}, owner_id=a.entity_id,
                          weight_kg=1, reason='GM observed the actual object')
        FW.observe_weapon(e, a, uid, name=uid, kind=kind, grade='간단', arcane=False,
                          metal=False, moves=moves, reason='GM selected the actual weapon form and grade')
        if configure:
            self.configure(e, a, uid, ac_mode=ac_mode, ac_delta=ac_delta,
                           db_delta=db_delta, break_after_attack=break_after_attack)
        return uid

    def configure(self, e, a, uid, **choices):
        return IW.configure(e, a, uid, gm_id='gm/table-a', source='gm/improvised-allowed',
                            reason='this actual object is unsuitable; explicitly chosen effects', **choices)

    def begin(self, e, a):
        if e._active_turn_actor is not None:
            e.end_of_turn(e._active_turn_actor)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)

    def snapshot(self, e):
        return json.dumps(e.export_state(), ensure_ascii=False, sort_keys=True)

    def test_source_conflict_remains_and_every_ruling_value_is_explicit(self):
        e, a, _ = self.fixture()
        uid = self.weapon(e, a, configure=False)
        source = (ROOT / IW.REFERENCE['file']).read_bytes()
        self.assertEqual(sha256(source).hexdigest(), IW.REFERENCE['sha256'])
        self.assertIn('AC에 -1', source.decode('utf-8'))
        indexed = json.loads((ROOT / 'data/verification/category2-core-clause-status.json').read_text(encoding='utf-8'))
        statement = next(row for row in indexed['clause_mappings'] if row['clause_id'] == IW.CLAUSE)
        self.assertEqual(statement['statement_sha256'], IW.STATEMENT_SHA256)
        baseline = dict(ac_mode='accuracy_roll', ac_delta=0, db_delta=-1, break_after_attack=False)
        for wrong in ({'ac_mode': None}, {'ac_delta': True}, {'db_delta': 1},
                      {'db_delta': False}, {'break_after_attack': 1}, {'db_delta': 0}):
            with self.subTest(wrong=wrong):
                before = self.snapshot(e)
                with self.assertRaises(ValueError):
                    self.configure(e, a, uid, **(baseline | wrong))
                self.assertEqual(self.snapshot(e), before)
        before = self.snapshot(e)
        with self.assertRaises(TypeError):
            IW.configure(e, a, uid, gm_id='gm', source='gm', reason='explicit')
        self.assertEqual(self.snapshot(e), before)
        for label in ('gm_id', 'source', 'reason'):
            with self.subTest(missing=label):
                inputs = dict(gm_id='gm/table-a', source='gm/improvised-allowed', reason='explicit')
                inputs[label] = ''
                with self.assertRaises(ValueError):
                    IW.configure(e, a, uid, **inputs, **baseline)
                self.assertEqual(self.snapshot(e), before)
        row = self.configure(e, a, uid, **baseline)
        self.assertEqual(row['source_conflict'], IW.AC_CONFLICT)
        self.assertEqual(row['source'], 'gm/improvised-allowed')
        self.assertEqual(row['gm_id'], 'gm/table-a')
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.configure(e, a, uid, **(baseline | {'db_delta': -2}))

    def test_roll_and_threshold_choices_change_separate_native_hit_inputs_once(self):
        import combat_hit as HIT
        for mode, delta in (('accuracy_roll', -1), ('ac_threshold', 1), ('ac_threshold', -1)):
            with self.subTest(mode=mode, delta=delta):
                e, a, target = self.fixture()
                if mode == 'ac_threshold' and delta == -1:
                    a.spec['skills']['전투'] = 6
                uid = self.weapon(e, a, ac_mode=mode, ac_delta=delta)
                key = FW.equip(e, a, uid)
                ordinary = deepcopy(self.r.move(key))
                prepared = WEAPONS.prepare(e, a, ordinary)
                self.assertEqual(WEAPONS.prepare(e, a, prepared), prepared)
                observed = []
                original = HIT.resolve
                def capture(**kwargs):
                    observed.append(kwargs)
                    return original(**kwargs)
                with patch.object(HIT, 'resolve', capture):
                    e.accuracy_check(a, target, prepared, fixed_roll=10)
                    e.accuracy_check(a, target, self.r.move('move/몸통박치기'), fixed_roll=10)
                native_ac = ordinary['ac'] - (1 if a.spec['skills']['전투'] == 6 else 0)
                self.assertEqual(observed[0]['accuracy'], native_ac + (delta if mode == 'ac_threshold' else 0))
                self.assertEqual(observed[0]['modifier'], observed[1]['modifier'] + (delta if mode == 'accuracy_roll' else 0))
                self.assertEqual(IW.ruling(e, uid)['source_conflict'], IW.AC_CONFLICT)
                self.assertNotIn(IW.MARK, ordinary)
                self.assertNotIn(IW.MARK, self.r.move('move/몸통박치기'))
                forged = deepcopy(prepared)
                forged[IW.MARK]['db_delta'] -= 1
                with self.assertRaisesRegex(ValueError, 'authority changed'):
                    e.damage_base(a, forged)
                forged = deepcopy(self.r.move('move/몸통박치기'))
                forged[IW.MARK] = deepcopy(prepared[IW.MARK])
                with self.assertRaisesRegex(ValueError, 'actual prepared physical weapon'):
                    e.damage_base(a, forged)

    def test_db_penalties_reach_struggle_and_granted_move_without_global_change(self):
        for penalty in (-1, -3, -20):
            e, a, target = self.fixture()
            uid = self.weapon(e, a, moves=['move/강타'], db_delta=penalty)
            key = FW.equip(e, a, uid)
            for mid in (key, 'move/강타'):
                with self.subTest(penalty=penalty, move=mid):
                    raw = self.r.move(mid)
                    prepared = WEAPONS.prepare(e, a, raw, uid)
                    base = raw['damage_base'] + (0 if mid == key else TURN.WEAPON_KIND['소형 근접무기']['db'])
                    self.assertEqual(e.damage_base(a, prepared), max(1, base + penalty))
                    self.assertEqual(WEAPONS.prepare(e, a, prepared), prepared)
            self.assertEqual(e.damage_base(a, self.r.move('move/몸통박치기')),
                             self.r.move('move/몸통박치기')['damage_base'])
            self.begin(e, a)
            with patch.object(Engine, 'accuracy_check', return_value=(True, 10, False)):
                self.assertGreater(e.use_move(a, target, 'move/강타', weapon_id=uid, set_damage=True), 0)
            self.assertEqual(a.move_uses['move/강타'], 1)
            self.assertEqual(a.budget['standard'], 0)
            self.assertFalse(W.physical_lifecycle(e._physical_objects[uid])['destroyed'])

    def test_native_hit_and_miss_break_only_the_used_instance_and_release_its_grants(self):
        for hit in (True, False):
            with self.subTest(hit=hit):
                e, a, target = self.fixture()
                uid = self.weapon(e, a, moves=['move/강타'], break_after_attack=True)
                other = self.weapon(e, a, 'object/other', moves=['move/강타'], configure=False)
                key = FW.equip(e, a, uid)
                other_key = FW.equip(e, a, other, slot='반대손')
                e.gm.set_move(a, 'move/강타', True)
                self.begin(e, a)
                with patch.object(Engine, 'accuracy_check', return_value=(hit, 10 if hit else 1, False)):
                    e.use_move(a, target, key, set_damage=True)
                obj = e._physical_objects[uid]
                self.assertTrue(W.physical_lifecycle(obj)['destroyed'])
                self.assertNotIn('equipped_by', obj)
                self.assertNotIn(key, a.custom_conditions['equipped_weapons'])
                self.assertNotIn(key, a.moves)
                self.assertIn(other_key, a.custom_conditions['equipped_weapons'])
                self.assertIn('move/강타', a.moves)
                self.assertFalse(W.physical_lifecycle(e._physical_objects[other])['destroyed'])
                self.assertEqual(a.budget['standard'], 0)
                token = obj['destroyed']['completion_id']
                before = self.snapshot(e)
                COMPLETE.refresh(e, token)
                self.assertEqual(self.snapshot(e), before)
                with self.assertRaises(ValueError):
                    FW.equip(e, a, uid)
                fresh = self.weapon(e, a, 'object/replacement')
                FW.equip(e, a, fresh)

    def test_unrelated_attack_invalid_target_and_cancelled_completion_do_not_break(self):
        e, a, target = self.fixture()
        uid = self.weapon(e, a, break_after_attack=True)
        key = FW.equip(e, a, uid)
        self.begin(e, a)
        target.pos = (20, 2)
        before = self.snapshot(e)
        with self.assertRaises(ValueError):
            e.use_move(a, target, key)
        self.assertEqual(self.snapshot(e), before)
        target.pos = (3, 2)
        with patch.object(Engine, 'accuracy_check', return_value=(False, 1, False)):
            e.use_move(a, target, 'move/몸통박치기')
        self.assertFalse(W.physical_lifecycle(e._physical_objects[uid])['destroyed'])
        self.begin(e, a)
        finish = COMPLETE.finish_target
        # Inject only the existing producer's cancellation flag at its native boundary.
        def cancelled(engine, token, actor, recipient, **options):
            return finish(engine, token, actor, recipient, **(options | {'cancelled': True}))
        with patch.object(COMPLETE, 'finish_target', cancelled), patch.object(Engine, 'accuracy_check', return_value=(False, 1, False)):
            e.use_move(a, target, key)
        row = list(e._move_completions.values())[-1]
        self.assertEqual(row['phase'], 'complete')
        self.assertTrue(all(x['cancelled'] for x in row['results'].values()))
        self.assertFalse(W.physical_lifecycle(e._physical_objects[uid])['destroyed'])
        self.assertIn(key, a.custom_conditions['equipped_weapons'])

    def test_ordinary_unconfigured_objects_keep_native_weapon_behavior(self):
        e, a, target = self.fixture()
        uid = self.weapon(e, a, configure=False)
        key = FW.equip(e, a, uid)
        prepared = WEAPONS.prepare(e, a, self.r.move(key))
        self.assertNotIn(IW.MARK, prepared)
        self.assertEqual(e.damage_base(a, prepared), self.r.move(key)['damage_base'])
        self.begin(e, a)
        with patch.object(Engine, 'accuracy_check', return_value=(False, 1, False)):
            e.use_move(a, target, key)
        self.assertFalse(W.physical_lifecycle(e._physical_objects[uid])['destroyed'])
        self.assertIn(key, a.custom_conditions['equipped_weapons'])

    def test_catalogue_object_identity_and_recipe_weapon_owner_are_preserved(self):
        import optional_physical_equipment as OPTIONAL
        for item_id in ('item/상처약', 'crafted_item/엑스칼리버'):
            with self.subTest(item_id=item_id):
                e, a, target = self.fixture()
                uid = 'object/catalogue-improvised'
                W.register_object(e, uid, kind='item_instance', item_rule_id=item_id,
                                  owner_id=a.entity_id, location={'kind': 'unknown'}, reason='actual catalogue body')
                recipe = OPTIONAL.definition(e.r, item_id) if item_id in OPTIONAL.KINDS else None
                profile = dict(name=recipe['name'] if recipe else '상처약',
                               kind=recipe['weapon_kind'] if recipe else '소형 근접무기',
                               grade='좋음' if recipe else '간단', arcane=False, metal=False,
                               reason='actual source identity with explicit GM improvised use')
                if recipe is None:
                    with self.assertRaises(ValueError):
                        FW.observe_weapon(e, a, uid, **profile)
                    self.assertNotIn(FW.PROFILE, e._physical_objects[uid])
                choices = dict(ac_mode='accuracy_roll', ac_delta=-1, db_delta=-1, break_after_attack=True,
                               gm_id='gm/table-a', source='gm/catalogue-improvised', reason='actual unsuitable use')
                FW.observe_weapon(e, a, uid, **profile, improvised=choices)
                self.assertEqual(IW.ruling(e, uid)['item_rule_id'], item_id)
                key = FW.equip(e, a, uid)
                registered = any(row.get('instance_id') == uid for row in getattr(a, '_item_reg', {}).values())
                self.assertEqual(registered, recipe is not None)
                self.assertEqual(set(e._physical_objects), {uid})
                self.assertEqual(e._physical_objects[uid]['item_rule_id'], item_id)
                self.begin(e, a)
                with patch.object(Engine, 'accuracy_check', return_value=(False, 1, False)):
                    e.use_move(a, target, key)
                self.assertTrue(W.physical_lifecycle(e._physical_objects[uid])['destroyed'])
                self.assertFalse(W.physical_lifecycle(e._physical_objects[uid])['consumed'])
                self.assertFalse(any(row.get('instance_id') == uid for row in getattr(a, '_item_reg', {}).values()))
                self.assertNotIn(key, a.moves)

    def test_late_break_failure_rolls_back_native_attack_cost_rng_damage_and_equipment(self):
        e, a, target = self.fixture()
        uid = self.weapon(e, a, break_after_attack=True)
        key = FW.equip(e, a, uid)
        self.begin(e, a)
        before = self.snapshot(e)
        original = W.finish_physical_use
        def fail(engine, obj, terminal, evidence):
            original(engine, obj, terminal, evidence)
            raise RuntimeError('injected after native break')
        with patch.object(W, 'finish_physical_use', fail):
            with self.assertRaisesRegex(RuntimeError, 'after native break'):
                e.use_move(a, target, key, set_damage=True)
        self.assertEqual(self.snapshot(e), before)

    def test_object_target_native_tool_receipt_breaks_on_hit_or_miss_and_replays_once(self):
        import physical_object_attacks as ATTACKS
        import physical_tool_attacks as TOOLS
        for hit in (True, False):
            with self.subTest(hit=hit):
                e, a, _ = self.fixture()
                uid = self.weapon(e, a, ac_mode='ac_threshold', ac_delta=1,
                                  db_delta=-2, break_after_attack=True)
                key = FW.equip(e, a, uid)
                TOOLS.observe(e, a, uid, contact_surface='blunt', source='gm/observed-contact', reason='actual pillow')
                target = 'object/door'
                W.register_object(e, target, location={'kind': 'grid', 'cell': [2, 3]}, reason='actual door')
                ATTACKS.configure(e, a, target, max_hp=30, reduction=0, minimum_damage=0,
                                  source='gm/door', reason='observed actual durability')
                self.begin(e, a)
                options = dict(event_id='improvised-door-' + str(hit), hit=hit, damage_before_dr=3 if hit else 0,
                               source='gm/object-attack-result', reason='explicit result after this weapon ruling')
                receipt = TOOLS.attack(e, a, target, uid, **options)
                self.assertEqual(receipt['tool_attack']['definition'][IW.MARK]['db_delta'], -2)
                self.assertTrue(W.physical_lifecycle(e._physical_objects[uid])['destroyed'])
                self.assertNotIn(key, a.moves)
                self.assertEqual(e._physical_objects[uid]['destroyed']['tool_event_id'], options['event_id'])
                before = self.snapshot(e)
                self.assertEqual(TOOLS.attack(e, a, target, uid, **options), receipt)
                self.assertEqual(self.snapshot(e), before)
                restored = Engine.import_state(self.r, json.loads(before))
                self.assertTrue(W.physical_lifecycle(restored._physical_objects[uid])['destroyed'])

    def test_ruling_and_break_restore_with_same_physical_identity_and_reject_tampering(self):
        e, a, target = self.fixture()
        uid = self.weapon(e, a, break_after_attack=True)
        key = FW.equip(e, a, uid)
        expected = deepcopy(e._physical_objects[uid][IW.FIELD])
        restored = Engine.import_state(self.r, json.loads(self.snapshot(e)))
        ra = W.actor_index(restored)[a.entity_id]
        rt = W.actor_index(restored)[target.entity_id]
        self.assertEqual(restored._physical_objects[uid][IW.FIELD], expected)
        restored.gm.snapshot('equipped-improvised')
        self.begin(restored, ra)
        with patch.object(Engine, 'accuracy_check', return_value=(False, 1, False)):
            restored.use_move(ra, rt, key)
        destroyed = Engine.import_state(self.r, json.loads(self.snapshot(restored)))
        self.assertEqual(destroyed._physical_objects[uid]['destroyed']['completion_id'],
                         restored._physical_objects[uid]['destroyed']['completion_id'])
        self.assertNotIn(key, W.actor_index(destroyed)[a.entity_id].moves)
        restored.gm.restore('equipped-improvised')
        ra = W.actor_index(restored)[a.entity_id]
        self.assertEqual(restored._physical_objects[uid][IW.FIELD], expected)
        self.assertFalse(W.physical_lifecycle(restored._physical_objects[uid])['destroyed'])
        self.assertIn(key, ra.custom_conditions['equipped_weapons'])
        bad = json.loads(self.snapshot(restored))
        corrupt = next(node for node in bad['nodes'].values()
                       if node['kind'] == 'dict' and ['clause_id', IW.CLAUSE] in node['items'])
        pair = next(pair for pair in corrupt['items'] if pair[0] == 'ac_delta')
        pair[1] += 1
        with self.assertRaises(Exception):
            Engine.import_state(self.r, bad)


if __name__ == '__main__':
    unittest.main()
