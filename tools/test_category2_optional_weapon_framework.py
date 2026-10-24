"""Five physical weapon contracts plus an explicit incomplete alchemy boundary."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine')]
from builder import build_trainer
from engine import Combatant, Engine, Rules
from grid import Grid
import capability_actions as CAP
import combat_precision_features as CPF
import items as ITEMS
import optional_physical_equipment as CRAFTED
import optional_weapon_framework as FW
import turn as TURN
import weapon_actions as WEAPONS
import world_entities as WORLD
import state_grants as GRANTS
import state_codec as CODEC
from effect_contracts import EffectContractError


class OptionalWeaponFrameworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(str(ROOT), ruleset='all')
        # These immutable saved-policy caches are warmed by first native use;
        # include them on both sides of the complete state/RNG rollback check.
        import setup_move_state, stellar_tera_blast
        setup_move_state._policy(cls.r)
        stellar_tera_blast._policy(cls.r)

    def fixture(self, *, family='arcane', element='노말', occult=5, athletics=5, focus=5, combat=2, mystic=False):
        e = Engine(self.r, seed=116306)
        e.grid = Grid(30, 15)
        features = [FW.TRAINING, FW.ARCANIST] if family == 'arcane' else [FW.STEELHEART, FW.MASTER]
        edges = ['edge/신비한-감각'] if mystic else ['edge/원소-교감']
        choices = {} if mystic else {'edge/원소-교감': element if family == 'arcane' else '강철'}
        people = []
        for index in range(3):
            extra = {'moves': ['move/몸통박치기'], 'abilities': [], 'feats': features if index == 0 else [],
                     'edges': edges if index == 0 else [], 'edge_choices': choices if index == 0 else {},
                     'skills': {'전투': combat if index == 0 else 3, '오컬트학': occult, '육상': athletics,
                                '집중': focus, '직감': 3},
                     'movement': {'land': 6}, 'movement_basis': 'current'}
            c = Combatant(self.r, build_trainer(self.r, 'weapon-' + str(id(e)) + '-' + str(index), 30,
                          {'hp': 100, 'atk': 20, 'def': 20, 'spa': 35, 'spd': 20, 'spe': 20}, extra=extra))
            c.side = 'player' if index == 0 else 'wild'
            c.pos = (2 + index, 2)
            e.gm.add_combatant(c)
            people.append(c)
        return e, *people

    def weapon(self, e, a, uid, *, arcane=True, metal=False, kind='소형 근접무기', grade='좋음', moves=(), item_id=None):
        WORLD.register_object(e, uid, location={'kind': 'unknown'}, reason='actual weapon test body',
                              owner_id=a.entity_id, weight_kg=1,
                              kind='item_instance' if item_id else 'physical_object', item_rule_id=item_id)
        name = CRAFTED.definition(self.r, item_id)['name'] if item_id else uid
        FW.observe_weapon(e, a, uid, name=name, kind=kind, grade=grade, arcane=arcane,
                          metal=metal, moves=moves, reason='observed actual weapon material and form')
        return uid

    def start(self, e, a):
        if e._active_turn_actor is not None:
            e.end_of_turn(e._active_turn_actor)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)

    def snapshot(self, e):
        return json.dumps(e.export_state(), ensure_ascii=False, sort_keys=True)

    def restore(self, e):
        return Engine.import_state(self.r, json.loads(self.snapshot(e)))

    def test_exact_sources_four_forms_prices_and_arcane_quality_grants(self):
        self.assertEqual(set(FW.policy(self.r)['clauses']), FW.CLAUSES)
        for market, simple, fine in (('common', 2000, 4000), ('typical', 3000, 6000), ('restricted', 5000, 10000)):
            self.assertEqual((FW.quote(self.fixture()[0], '간단', market), FW.quote(self.fixture()[0], '좋음', market)), (simple, fine))
        for kind in ('소형 근접무기', '대형 근접무기', '단거리 사격무기', '장거리 사격무기'):
            with self.subTest(kind=kind):
                e, a, _, _ = self.fixture(element='물')
                uid = self.weapon(e, a, 'forms/' + kind, kind=kind, moves=['move/렌딩-스펠', 'move/베인'])
                key = FW.equip(e, a, uid)
                prepared = WEAPONS.prepare(e, a, self.r.move(key), uid)
                self.assertEqual((prepared['class'], prepared['type']), ('특수', '물'))
                self.assertIn('move/렌딩-스펠', a.moves)
                self.assertIn('move/베인', a.moves)
                self.assertEqual(e.damage_base(a, prepared), 5 + TURN.WEAPON_KIND[kind]['db'])
        e, a, _, _ = self.fixture(occult=3)
        uid = self.weapon(e, a, 'novice/simple', grade='간단', moves=['move/렌딩-스펠'])
        FW.equip(e, a, uid)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ValueError, 'tier prerequisite'):
            self.weapon(e, a, 'novice/expert-refused', moves=['move/베인'])
        # The rejected profile was never committed (the separately observed body remains).
        self.assertNotIn(FW.PROFILE, e._physical_objects['novice/expert-refused'])
        self.assertEqual(a.spec['skills']['전투'], 2)

    def test_normal_mystic_effect_range_is_attack_scoped_and_changes_native_threshold(self):
        for mystic in (False, True):
            with self.subTest(mystic=mystic):
                e, a, foe, _ = self.fixture(occult=4, mystic=mystic)
                uid = self.weapon(e, a, 'normal/' + str(mystic), moves=['move/렌딩-스펠'])
                FW.bond(e, a, uid, family='arcane')
                key = FW.equip(e, a, uid)
                move = WEAPONS.prepare(e, a, self.r.move('move/렌딩-스펠'), uid)
                self.assertEqual(CPF.effect_natural(e, a, move, 13), 16)
                self.assertEqual(CPF.effect_natural(e, a, self.r.move('move/몸통박치기'), 13), 13)
                self.assertEqual(WEAPONS.range_spec(e, move)['origin'], 'melee')
                self.assertEqual(FW.damage_roll_bonus(e, a, move), 5)
                self.start(e, a)
                original = Engine.lose_hp
                losses = []
                def observed(engine, target, amount, *args, **kwargs):
                    losses.append((target.entity_id, amount))
                    return original(engine, target, amount, *args, **kwargs)
                with patch.object(Engine, 'accuracy_check', return_value=(True, 13, False)), patch.object(Engine, 'lose_hp', observed):
                    e.use_move(a, foe, 'move/렌딩-스펠', weapon_id=uid, set_damage=True)
                self.assertIn((foe.entity_id, e.tick(foe)), losses)
                # Preparation did not mutate the shared catalogue or normal Struggle.
                self.assertEqual(self.r.move('move/렌딩-스펠')['type'], '노말')
                self.assertNotIn(FW.MARK, self.r.move('move/렌딩-스펠'))
                TURN.unequip_weapon(e, a, key)
                self.assertNotIn('move/렌딩-스펠', a.moves)

    def test_alchemy_prepared_exceptions_and_native_targetset_blocker_remain_explicit(self):
        e, a, foe, _ = self.fixture(element='물', occult=6)
        uid = self.weapon(e, a, 'recipe/nine-flames', kind='대형 근접무기',
                          moves=['move/렌딩-스펠', 'move/베인'], item_id='crafted_item/나인플레임의-스태프')
        FW.bond(e, a, uid, family='arcane')
        key = FW.equip(e, a, uid)
        normal = WEAPONS.prepare(e, a, self.r.move('move/렌딩-스펠'), uid)
        extra = WEAPONS.prepare(e, a, self.r.move('move/불꽃튀기기'), uid)
        self.assertEqual(normal['type'], '물')
        self.assertEqual(extra['type'], '불꽃')
        self.assertTrue(extra[FW.MARK]['alchemy'])
        self.assertEqual(e.damage_base(a, extra), self.r.move('move/불꽃튀기기')['damage_base'] + 2)
        self.assertEqual(e.damage_base(a, normal), self.r.move('move/렌딩-스펠')['damage_base'] + 2 + 3)
        ability = CRAFTED.definition(self.r, 'crafted_item/나인플레임의-스태프')['abilities'][0]
        self.assertIn(ability, a.abilities)
        self.start(e, a)
        before = self.snapshot(e)
        with self.assertRaisesRegex(EffectContractError, 'explicit native target-set binding'):
            e.use_move_on(a, foe, 'move/불꽃튀기기', e.everyone, weapon_id=uid)
        self.assertEqual(self.snapshot(e), before)
        restored = self.restore(e)
        ra = WORLD.actor_index(restored)[a.entity_id]
        self.assertEqual(restored._physical_objects[uid]['equipped_by'], ra.entity_id)
        ITEMS.unregister_item(restored, ra, registration_key=next(k for k, v in ra._item_reg.items() if v.get('instance_id') == uid))
        self.assertNotIn('move/불꽃튀기기', ra.moves)
        self.assertNotIn(ability, ra.abilities)
        self.assertEqual(ra.spec[FW.BONDS]['arcane']['instance_id'], uid)

    def test_bond_replacement_failure_and_unheld_ten_metre_recall_both_families(self):
        for family in ('arcane', 'steelheart'):
            with self.subTest(family=family):
                e, a, _, _ = self.fixture(family=family)
                arcane = family == 'arcane'
                first = self.weapon(e, a, family + '/old', arcane=arcane, metal=not arcane)
                second = self.weapon(e, a, family + '/new', arcane=arcane, metal=not arcane)
                FW.bond(e, a, first, family=family)
                FW.bond(e, a, second, family=family)
                self.assertEqual(a.spec[FW.BONDS][family]['instance_id'], second)
                wrong = self.weapon(e, a, family + '/wrong', arcane=False, metal=False)
                before = self.snapshot(e)
                with self.assertRaises(ValueError):
                    FW.bond(e, a, wrong, family=family)
                self.assertEqual(self.snapshot(e), before)
                WORLD.register_object(e, second, location={'kind': 'grid', 'cell': [12, 2]}, reason='unheld bond ten metres away')
                self.start(e, a)
                result = FW.recall(e, a, family=family)
                self.assertTrue(result['recalled'])
                self.assertEqual(a.budget['shift'], 0)
                self.assertEqual(e._physical_objects[second]['equipped_by'], a.entity_id)
                restored = self.restore(e)
                ra = WORLD.actor_index(restored)[a.entity_id]
                self.assertEqual(ra.spec[FW.BONDS][family]['instance_id'], second)
                self.assertEqual(restored._physical_objects[second]['equipped_by'], ra.entity_id)
                restored.gm.snapshot('bond-pair')
                restored.gm.restore('bond-pair')
                self.assertEqual(restored._physical_objects[second]['equipped_by'], ra.entity_id)

    def test_unwilling_holder_opposed_tie_loss_success_and_no_physical_copy(self):
        for family, skill in (('arcane', '오컬트학'), ('steelheart', '집중')):
            with self.subTest(family=family):
                e, a, holder, _ = self.fixture(family=family, occult=5, focus=5, athletics=5)
                uid = self.weapon(e, a, family + '/held', arcane=family == 'arcane', metal=family == 'steelheart')
                FW.bond(e, a, uid, family=family)
                CAP.set_carried(e, holder, [{'id': uid, 'weight_kg': 1}], 'actual adversary holds the bonded weapon')
                if family == 'arcane':
                    holder.spec['feats'] = [FW.TRAINING]
                    holder.spec['edges'] = ['edge/원소-교감']
                    holder.spec['edge_choices'] = {'edge/원소-교감': '노말'}
                FW.equip(e, holder, uid)
                self.start(e, a)
                count = len(e._physical_objects)
                tied = {'fixed': [2] * 5}
                result = FW.recall(e, a, family=family, unwilling=True, skill=skill,
                                   challenger_options=tied, defender_options=tied)
                self.assertFalse(result['recalled'])
                self.assertEqual(e._physical_objects[uid]['equipped_by'], holder.entity_id)
                self.assertEqual(a.budget['shift'], 0)
                self.start(e, a)
                result = FW.recall(e, a, family=family, unwilling=True, skill=skill,
                                   challenger_options={'fixed': [6] * 5}, defender_options={'fixed': [1] * 5})
                self.assertTrue(result['recalled'])
                self.assertEqual(len(e._physical_objects), count)
                self.assertFalse(holder.custom_conditions.get('equipped_weapons'))
                self.assertFalse(holder.spec['_carried_load']['objects'])
                self.assertEqual(e._physical_objects[uid]['owner_id'], a.entity_id)
                self.assertEqual(e._physical_objects[uid]['equipped_by'], a.entity_id)

    def test_steelheart_native_skill_substitution_disarm_and_round_hit_consumer(self):
        e, a, foe, _ = self.fixture(family='steelheart', athletics=4, focus=5, combat=2)
        FW.select_steelheart_source(e,a,{'value':'korean_book_outgoing','reason':'this existing scenario exercises the complete Korean outgoing definition','scope':FW.steelheart_source_choices(e)['decision_scope']})
        uid = self.weapon(e, a, 'steel/native', arcane=False, metal=True, moves=['move/강타'])
        key = FW.equip(e, a, uid)
        self.assertIn('move/강타', a.moves)
        self.assertEqual(e.damage_base(a, self.r.move(key)), 6)
        self.start(e, foe)
        self.assertFalse(TURN.disarm(e, foe, a, attacker_skill='전투', defender_skill='집중', fixed_accuracy=20,
                                    challenger_options={'fixed': [1] * 3}, defender_options={'fixed': [6] * 5}))
        self.assertEqual(e._physical_objects[uid]['equipped_by'], a.entity_id)
        self.start(e, a)
        # A hit that deals no attack damage still establishes hit history.
        with patch.object(Engine, 'accuracy_check', return_value=(True, 18, False)), patch.object(Engine, 'roll_damage', return_value=0):
            e.use_move(a, foe, 'move/몸통박치기', set_damage=True)
        self.assertIn(foe.entity_id, a.spec[FW.HITS]['targets'])
        hp = foe.hp
        TURN.reset_budget(e, a)
        with patch.object(Engine, 'accuracy_check', return_value=(True, 18, False)), patch.object(Engine, 'roll_damage', return_value=0):
            e.use_move(a, foe, key, weapon_id=uid, set_damage=True)
        self.assertEqual(foe.hp, hp - e.tick(foe))
        restored = self.restore(e)
        ra, rf = (WORLD.actor_index(restored)[x.entity_id] for x in (a, foe))
        self.assertIn(rf.entity_id, ra.spec[FW.HITS]['targets'])
        self.start(restored, ra)
        hp = rf.hp
        with patch.object(Engine, 'accuracy_check', return_value=(True, 18, False)), patch.object(Engine, 'roll_damage', return_value=0):
            restored.use_move(ra, rf, key, weapon_id=uid, set_damage=True)
        self.assertEqual(rf.hp, hp)

    def test_arcane_native_disarm_and_atomic_attack_recall_failures(self):
        e, a, foe, _ = self.fixture(occult=5)
        uid = self.weapon(e, a, 'atomic/arcane', moves=['move/렌딩-스펠'])
        FW.bond(e, a, uid, family='arcane')
        key = FW.equip(e, a, uid)
        self.start(e, foe)
        self.assertFalse(TURN.disarm(e, foe, a, attacker_skill='전투', defender_skill='오컬트학', fixed_accuracy=20,
                                    challenger_options={'fixed': [1] * 3}, defender_options={'fixed': [6] * 5}))
        self.start(e, foe)
        self.assertTrue(TURN.disarm(e, foe, a, attacker_skill='전투', defender_skill='오컬트학', fixed_accuracy=20,
                                   challenger_options={'fixed': [6] * 3}, defender_options={'fixed': [1] * 5}))
        self.assertNotIn('equipped_by', e._physical_objects[uid])
        self.assertNotIn('move/렌딩-스펠', a.moves)
        e, a, foe, _ = self.fixture(occult=5)
        uid = self.weapon(e, a, 'atomic/late-consumer', moves=['move/렌딩-스펠'])
        FW.bond(e, a, uid, family='arcane')
        key = FW.equip(e, a, uid)
        self.start(e, a)
        before = self.snapshot(e)
        rule_before = {name: json.dumps(CODEC._plain(value), ensure_ascii=False, sort_keys=True)
                       for name, value in vars(e.r).items() if name not in ('root', 'rulings', 'ruleset', 'selection', '_source_context_reads')}
        with patch.object(Engine, 'accuracy_check', return_value=(True, 13, False)), patch.object(FW, 'observe_hit', side_effect=ValueError('injected hit consumer rejection')):
            with self.assertRaisesRegex(ValueError, 'injected hit'):
                e.use_move(a, foe, 'move/렌딩-스펠', weapon_id=uid, set_damage=True)
        rule_after = {name: json.dumps(CODEC._plain(value), ensure_ascii=False, sort_keys=True)
                      for name, value in vars(e.r).items() if name not in ('root', 'rulings', 'ruleset', 'selection', '_source_context_reads')}
        changed = [name for name in set(rule_before) | set(rule_after) if rule_before.get(name) != rule_after.get(name)]
        self.assertEqual(self.snapshot(e), before, 'failed native move changed rules caches: ' + repr(changed))
        TURN.unequip_weapon(e, a, key)
        WORLD.register_object(e, uid, location={'kind': 'grid', 'cell': [13, 2]}, reason='eleven metres away')
        before = self.snapshot(e)
        with self.assertRaisesRegex(ValueError, 'ten metres'):
            FW.recall(e, a, family='arcane')
        self.assertEqual(self.snapshot(e), before)

    def test_failed_held_recall_rolls_back_native_disarm_carrier_rng_and_shift(self):
        e, a, holder, _ = self.fixture()
        uid = self.weapon(e, a, 'rollback/held')
        FW.bond(e, a, uid, family='arcane')
        CAP.set_carried(e, holder, [{'id': uid, 'weight_kg': 1}], 'actual holder before failed recall')
        holder.spec.update(feats=[FW.TRAINING], edges=['edge/원소-교감'], edge_choices={'edge/원소-교감': '노말'})
        FW.equip(e, holder, uid)
        self.start(e, a)
        before = self.snapshot(e)
        with patch.object(FW, 'equip', side_effect=ValueError('injected recall receiver failure')):
            with self.assertRaisesRegex(ValueError, 'recall receiver'):
                FW.recall(e, a, family='arcane', unwilling=True,
                          challenger_options={'fixed': [6] * 5}, defender_options={'fixed': [1] * 5})
        self.assertEqual(self.snapshot(e), before)
        self.assertEqual(e._physical_objects[uid]['equipped_by'], holder.entity_id)
        self.assertEqual(a.budget['shift'], 1)

    def test_bond_replacement_and_forged_prepared_bonus_are_rejected_at_consumer(self):
        e, a, _, _ = self.fixture(occult=6)
        first = self.weapon(e, a, 'authority/first', moves=['move/렌딩-스펠'])
        second = self.weapon(e, a, 'authority/second')
        FW.bond(e, a, first, family='arcane')
        FW.equip(e, a, first)
        prepared = WEAPONS.prepare(e, a, self.r.move('move/렌딩-스펠'), first)
        self.assertEqual(CPF.effect_natural(e, a, prepared, 10), 15)
        forged = deepcopy(prepared)
        forged[FW.MARK]['effect_bonus'] += 20
        with self.assertRaisesRegex(ValueError, 'authority changed'):
            CPF.effect_natural(e, a, forged, 10)
        unrelated = deepcopy(self.r.move('move/몸통박치기'))
        unrelated['_weapon_attack'] = deepcopy(prepared['_weapon_attack'])
        with self.assertRaisesRegex(ValueError, 'not granted'):
            CPF.effect_natural(e, a, unrelated, 10)
        FW.bond(e, a, second, family='arcane')
        with self.assertRaisesRegex(ValueError, 'authority changed'):
            CPF.effect_natural(e, a, prepared, 10)
        current = WEAPONS.prepare(e, a, self.r.move('move/렌딩-스펠'), first)
        self.assertEqual(CPF.effect_natural(e, a, current, 10), 12)

    def test_weapon_defense_reaches_existing_native_telekinetic_disarm(self):
        for family, skill in (('arcane', '오컬트학'), ('steelheart', '집중')):
            with self.subTest(family=family):
                e, a, foe, _ = self.fixture(family=family)
                uid = self.weapon(e, a, 'telekinetic/' + family, arcane=family == 'arcane', metal=family == 'steelheart')
                FW.equip(e, a, uid)
                GRANTS.grant(foe, 'capabilities', 'Telekinetic', 'fixture:telekinetic', 'fixture')
                self.start(e, foe)
                self.assertFalse(e.telekinetic_maneuver(foe, a, 'disarm', defender_skill=skill, fixed_accuracy=20,
                                                      challenger_options={'fixed': [1] * 5}, defender_options={'fixed': [6] * 5}))
                self.assertEqual(foe.budget['standard'], 0)
                self.assertEqual(e._physical_objects[uid]['equipped_by'], a.entity_id)
                self.assertTrue(WORLD.validate_world(e)['valid'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
