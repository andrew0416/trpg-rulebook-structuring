"""Type Ace's acquired links into evasion, abilities, local weather and rulings.

The acquisition module is imported as a module, not as a TestCase superclass:
its thirteen tests are deliberately not collected again here.
"""
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_book_type_ace_acquisition as FIX
from engine import Engine
import ability_transitions as ABILITIES
import action_points as AP
import combat_timing as TIME
from builder import build_pokemon, species_lookup, STATS
import condition_recovery as RECOVERY
import effects as EFFECTS
import growth_stats as GROWTH
import pokemon_move_edges as EDGES
import turn as TURN
import type_ace as TA


class TypeAcePassiveTests(unittest.TestCase):
    setUpClass = classmethod(FIX.TypeAceAcquisitionTests.setUpClass.__func__)
    setUp = FIX.TypeAceAcquisitionTests.setUp
    setup = FIX.TypeAceAcquisitionTests.setup
    add = FIX.TypeAceAcquisitionTests.add
    acquire = FIX.TypeAceAcquisitionTests.acquire
    teach = FIX.TypeAceAcquisitionTests.teach
    combat = FIX.TypeAceAcquisitionTests.combat
    next_turn = FIX.TypeAceAcquisitionTests.next_turn
    communication = FIX.TypeAceAcquisitionTests.communication
    rejected = FIX.TypeAceAcquisitionTests.rejected
    restore = FIX.TypeAceAcquisitionTests.restore
    valid = FIX.TypeAceAcquisitionTests.valid
    sync_decision = FIX.TypeAceAcquisitionTests.sync_decision

    def family(self, branch, *features):
        skill = TA.SKILLS[branch][0]
        self.t.spec['type_link_skills'][branch] = skill
        self.e.gm.set_skill(self.t, skill, 6, reason='actual Master in explicitly selected Type Link skill')
        for pokemon in (self.p, self.q):
            self.e.gm.set_types(pokemon, [branch], reason='actual two distinct owned Pokemon of this branch')
        self.acquire(branch=branch)
        for feature in features:
            self.acquire(feature, branch)

    def answer(self, key, value):
        self.e.rulings.answers = [row for row in self.e.rulings.answers if row['key'] != key]
        self.e.rulings.add_answer(key, value, reason='explicit observed native rule choice', scope='permanent')

    def attack(self, actor, target, move, *, face=10):
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(actor, target, move, self.e.everyone, set_damage=True)

    def damage(self, actor, target, move):
        projected = EDGES.prepare(self.e, actor, self.rules.move(move))
        return self.e.roll_damage(actor, target, projected, set_damage=True)

    def third_hp(self, *, below):
        # Observe an actual level yielding an exact one-third boundary, rather
        # than rounding the boundary into an allegedly equivalent comparison.
        for level in range(self.p.level, self.p.level + 3):
            self.e.gm.set_level(self.p, level, reason='actual observed level for an exact HP threshold')
            if self.p.max_hp % 3 == 0:
                break
        self.assertEqual(self.p.max_hp % 3, 0)
        self.e.gm.set_hp(self.p, value=self.p.max_hp // 3 - int(below),
            reason='actual HP immediately at or below one third')

    def suppress(self, target, ability):
        self.e.gm.set_move(self.b, 'move/위액', reason='actual learned ability-suppression Move')
        self.e.gm.choose_ability_transition(self.b, target, 'move/위액', ability=ability,
            reason='actual selection of the acquired parameterized ability')
        self.attack(self.b, target, 'move/위액')
        self.assertIn('ability/' + ability, ABILITIES.known(target))
        self.assertFalse(ABILITIES.active(target, 'ability/' + ability))

    def test_sky_is_a_speed_candidate_without_flying_requirement_and_native_zero_waive_cap_survive(self):
        self.family('벌레', 'Insectoid Utility')
        self.e.gm.set_movement_capabilities(self.p,
            {'land':6, 'swim':0, 'sky':4, 'burrow':0, 'levitate':0}, basis='base',
            reason='actual Sky capability on a non-Flying Pokemon')
        self.assertNotIn('비행', self.p.types)
        self.e.gm.set_stat(self.p, 'def', value=30, reason='actual physical candidate exceeds Speed plus Sky')
        self.e.gm.set_stage(self.p, 'eva', value=2, reason='actual independent non-Stat evasion bonus')
        self.assertEqual(self.p.evasion('물리', engine=self.e), 8)
        self.assertEqual(self.p.evasion('특수', engine=self.e), 7)
        self.e.gm.set_stat(self.p, 'spe', value=40, reason='actual capped Speed candidate before the Sky upgrade')
        self.assertEqual(self.p.evasion('물리', engine=self.e), 9)
        self.e.gm.set_stat(self.p, 'spe', value=20, reason='actual ordinary Speed again')
        self.combat(self.b)
        move = self.rules.move('move/몸통박치기')
        self.assertFalse(self.e._accuracy_check_native(self.b, self.p, move, fixed_roll=9)[0])
        self.assertTrue(self.e._accuracy_check_native(self.b, self.p, move, fixed_roll=9, waive=True)[0])
        self.e.gm.add_condition(self.p, '잠듦', reason='actual helpless target keeps zero evasion')
        self.assertEqual(self.p.evasion('물리', engine=self.e), 0)
        self.assertTrue(self.e._accuracy_check_native(self.b, self.p, move, fixed_roll=2)[0])

    def test_clever_ruse_ignores_only_stats_and_preserves_other_evasion_in_native_accuracy(self):
        self.family('악', 'Clever Ruse')
        self.e.gm.set_stage(self.b, 'eva', value=2, reason='actual independent target evasion bonus')
        self.combat(self.p)
        move = self.rules.move('move/몸통박치기')
        self.assertEqual(self.b.evasion('물리', attacker=self.p, engine=self.e), 6)
        self.assertFalse(self.e._accuracy_check_native(self.p, self.b, move, fixed_roll=7)[0])
        TA.special(self.e, self.t, self.p, 'Clever Ruse', choices=['evasion', 'ignore_evasion'])
        self.assertEqual(self.p.budget['standard'], 0)
        self.assertEqual(self.p.evasion('물리', engine=self.e), 8)
        self.assertEqual(self.b.evasion('물리', attacker=self.p, engine=self.e), 2)
        self.assertEqual(self.b.evasion('물리', engine=self.e, ignore_stats=True), 2)
        self.assertFalse(self.e._accuracy_check_native(self.p, self.b, move, fixed_roll=3)[0])
        self.assertTrue(self.e._accuracy_check_native(self.p, self.b, move, fixed_roll=4)[0])
        self.assertTrue(self.e._accuracy_check_native(self.p, self.b, move, fixed_roll=2, waive=True)[0])
        self.restore()
        self.assertEqual(self.b.evasion('물리', attacker=self.p, engine=self.e), 2)
        self.valid()

    def test_clever_ruse_invalid_effect_choices_are_atomic_before_any_payment_or_partial_effect(self):
        self.family('악', 'Clever Ruse')
        self.combat(self.p)
        for choices in ([], ['evasion'], ['evasion', 'evasion'], ['evasion', 'invented']):
            with self.subTest(choices=choices):
                self.rejected(lambda choices=choices:TA.special(self.e, self.t, self.p,
                    'Clever Ruse', choices=choices), 'two distinct')
        self.assertEqual(self.p.budget['standard'], 1)
        self.assertFalse(TA.ignore_stat_evasion(self.p))

    def test_last_chance_native_formula_uses_five_at_exact_third_ten_below_and_actual_suppression(self):
        for below, bonus in ((False, 5), (True, 10)):
            with self.subTest(below_one_third=below):
                self.setup()
                self.acquire()
                self.third_hp(below=below)
                self.e.gm.set_move(self.p, 'move/불꽃세례', reason='actual matching attack')
                baseline = self.damage(self.p, self.b, 'move/불꽃세례')
                self.teach(ability='last_chance')
                self.assertEqual(self.damage(self.p, self.b, 'move/불꽃세례'), baseline + bonus)
                self.assertEqual(TA.ability_branches(self.e, self.p, 'last_chance'), {'불꽃'})
                self.combat(self.b)
                self.suppress(self.p, '마지막기회')
                self.assertEqual(self.damage(self.p, self.b, 'move/불꽃세례'), baseline)
                self.e.end_encounter(self.e.everyone)
                self.assertTrue(ABILITIES.active(self.p, 'ability/마지막기회'))
                self.assertEqual(self.damage(self.p, self.b, 'move/불꽃세례'), baseline + bonus)

    def test_strategist_actual_typed_move_uses_hp_boundary_and_suppression_removes_live_dr(self):
        for below, reduction in ((False, 5), (True, 10)):
            with self.subTest(below_one_third=below):
                self.setup()
                self.acquire()
                self.third_hp(below=below)
                self.e.gm.set_move(self.p, 'move/불꽃세례', reason='actual matching attack')
                baseline = self.damage(self.b, self.p, 'move/몸통박치기')
                self.teach(ability='strategist')
                self.assertEqual(self.damage(self.b, self.p, 'move/몸통박치기'), baseline)
                self.combat(self.p)
                self.attack(self.p, self.b, 'move/불꽃세례')
                self.assertEqual(self.damage(self.b, self.p, 'move/몸통박치기'), baseline - reduction)
                self.e.end_of_turn(self.p)
                self.e.start_of_turn(self.b, initiative_count=20)
                self.suppress(self.p, '타입전략가')
                self.assertEqual(self.damage(self.b, self.p, 'move/몸통박치기'), baseline)
                self.restore()
                self.assertEqual(self.damage(self.b, self.p, 'move/몸통박치기'), baseline)
                self.valid()

    def test_strategist_full_round_expiry_uses_initiative_count_not_the_triggering_turn_end(self):
        self.acquire()
        self.teach(ability='strategist')
        self.e.gm.set_move(self.p, 'move/불꽃세례', reason='actual matching attack')
        baseline = self.damage(self.b, self.p, 'move/몸통박치기')
        self.combat(self.p)
        self.attack(self.p, self.b, 'move/불꽃세례')
        self.e.end_of_turn(self.p)
        self.assertEqual(self.damage(self.b, self.p, 'move/몸통박치기'), baseline - 5)
        self.e.end_round()
        self.e.start_round(self.e.everyone)
        self.e.at_initiative_count(31)
        self.assertEqual(self.damage(self.b, self.p, 'move/몸통박치기'), baseline - 5)
        self.e.at_initiative_count(30)
        self.assertEqual(self.damage(self.b, self.p, 'move/몸통박치기'), baseline)

    def test_both_parameterized_abilities_consume_actual_move_sync_type(self):
        self.acquire()
        self.acquire(TA.REFRESH)
        self.acquire('Brightest Flame')
        self.acquire(TA.SYNC)
        self.teach(ability='last_chance')
        self.teach(ability='strategist', pokemon=self.q)
        for pokemon, identity in ((self.p, 'last-chance-sync'), (self.q, 'strategist-sync')):
            self.e.gm.set_move(pokemon, 'move/냉동빔', reason='actual known Ice attack before Move Sync')
            decision = self.sync_decision(application=identity)
            TA.sync(self.e, self.t, pokemon, '불꽃', seconds=60, **decision)
            self.assertEqual(EDGES.prepare(self.e, pokemon, self.rules.move('move/냉동빔'))['type'], '불꽃')
        incoming = self.damage(self.b, self.q, 'move/몸통박치기')
        self.combat(self.q)
        self.attack(self.q, self.b, 'move/냉동빔')
        self.assertEqual(self.damage(self.b, self.q, 'move/몸통박치기'), incoming - 5)
        self.e.end_of_turn(self.q)
        self.e.start_of_turn(self.b, initiative_count=20)
        active = self.damage(self.p, self.b, 'move/냉동빔')
        self.suppress(self.p, '마지막기회')
        self.assertEqual(active - self.damage(self.p, self.b, 'move/냉동빔'), 5)

    def test_four_acquired_weather_stratagems_are_local_activation_views_without_virtual_hp_loss(self):
        cases = (
            ('풀', 'Foiling Foliage', 'Sunlight Within', 'sunny', 'hail'),
            ('땅', 'Mold the Earth', 'Desert Heart', 'sandstorm', 'hail'),
            ('얼음', 'Glacial Ice', 'Polar Vortex', 'hail', 'sandstorm'),
            ('물', 'Flood!', 'Fishbowl Technique', 'rain', 'hail'),
        )
        for branch, parent, feature, virtual, actual in cases:
            with self.subTest(feature=feature):
                self.setup()
                self.family(branch, parent, feature)
                self.e.gm.set_types(self.p, ['노말'], reason='actual target without passive weather-damage immunity')
                self.communication()
                self.combat(self.t)
                TA.activate(self.e, self.t, self.p, feature)
                self.assertEqual(EFFECTS.effective_weather(self.e, self.p), virtual)
                self.assertIsNone(EFFECTS.effective_weather(self.e, self.q))
                self.assertIsNone(self.e.weather)
                self.e.end_of_turn(self.t)
                before = self.p.hp
                self.e.start_of_turn(self.p, initiative_count=20)
                self.assertEqual(self.p.hp, before)
                self.assertEqual(TURN.weather_damage_mod(self.e, self.p, self.rules.move('move/불꽃세례')), 0)
                self.e.end_of_turn(self.p)
                self.e.gm.set_weather(actual, reason='actual independently sourced field weather')
                self.e.end_round()
                self.e.start_round(self.e.everyone)
                before = self.p.hp
                self.e.start_of_turn(self.p, initiative_count=30)
                self.assertEqual(self.p.hp, before - self.e.tick_loss(self.p))
                self.assertEqual(self.e.weather, actual)
                self.assertEqual(EFFECTS.effective_weather(self.e, self.p), virtual)
                self.assertEqual(EFFECTS.effective_weather(self.e, self.q), actual)

    def test_sunlight_within_reaches_actual_chlorophyll_and_solarbeam_and_ends_with_its_binding(self):
        self.family('풀', 'Foiling Foliage', 'Sunlight Within')
        self.e.gm.set_ability(self.p, '엽록소', reason='actual owned weather-conditioned ability')
        self.e.gm.set_move(self.p, 'move/솔라빔', reason='actual learned weather-conditioned Move')
        self.assertEqual(self.p.stages['spe'], 0)
        self.communication()
        self.combat(self.t)
        TA.activate(self.e, self.t, self.p, 'Sunlight Within')
        self.assertEqual(self.p.stages['spe'], 4)
        self.restore()
        self.assertEqual(self.p.stages['spe'], 4)
        self.e.end_of_turn(self.t)
        self.e.start_of_turn(self.p, initiative_count=20)
        before = self.b.hp
        self.attack(self.p, self.b, 'move/솔라빔')
        self.assertLess(self.b.hp, before)
        self.assertIsNone(self.e.weather)
        self.e.end_encounter(self.e.everyone)
        self.assertIsNone(EFFECTS.effective_weather(self.e, self.p))
        self.assertEqual(self.p.stages['spe'], 0)
        self.valid()

    def test_errata_disruption_uses_half_actual_rank_without_reading_legacy_x_ruling(self):
        self.family('벌레', 'Insectoid Utility', 'Disruption Order')
        self.e.gm.set_move(self.p, 'move/시그널빔', reason='actual known damaging Bug attack')
        self.combat(self.p)
        self.attack(self.p, self.b, 'move/시그널빔')
        completion = next(key for key, row in reversed(list(self.e._move_completions.items()))
            if row['actor'] is self.p and row['move']['id'] == 'move/시그널빔')
        # Errata PDF17 supplies X. A stale Core-era answer cannot replace it.
        self.answer('type_ace_disruption_x', -99)
        TA.react(self.e, self.t, self.p, 'Disruption Order', completion)
        effects = [row for row in TIME.records(self.b) if row.get('source') == TA.uid('Disruption Order')]
        self.assertEqual(TA.rank(self.e, self.t, '벌레'), 6)
        self.assertEqual([row['accuracy_modifier'] for row in effects], [-3])
        self.assertIn('둔화', self.b.conditions)
        self.assertTrue(all(row['turn_owner'] is self.p for row in effects))
        self.valid()

    def test_errata_iron_grit_requires_actual_owned_steel_target_and_rejects_other_type_atomically(self):
        self.family('강철', 'Polished Shine', 'Iron Grit')
        self.e.gm.set_types(self.p, ['노말'], reason='actual owned non-Steel target')
        self.communication()
        self.combat(self.t)
        # Errata PDF17 fixes the target; a legacy permissive ruling is ignored.
        self.answer('type_ace_iron_grit_target', 'all_owned')
        self.rejected(lambda:TA.activate(self.e, self.t, self.p, 'Iron Grit'), 'target type|Steel|강철')
        self.e.gm.set_types(self.p, ['강철'], reason='actual owned Steel target now meets the printed target')
        before = AP.available(self.t)
        TA.activate(self.e, self.t, self.p, 'Iron Grit')
        self.assertEqual(AP.available(self.t), before - 2)
        self.assertEqual(self.p.stages['def'], 1)
        defense = self.p.staged('def')
        self.e.change_stage(self.p, 'def', -1)
        self.assertEqual(self.p.stages['def'], 1)
        self.assertEqual(self.p.staged('def'), defense)
        self.restore()
        self.assertEqual(self.p.staged('def'), defense)
        self.valid()

    def test_errata_highlander_static_ignores_evasion_only_for_isolated_dragon_attack_targets(self):
        self.family('드래곤', 'Tyrant’s Roar', 'Highlander')
        self.e.gm.set_types(self.p, ['노말'], reason='Highlander applies to owned Pokemon Dragon attacks regardless of user type')
        self.e.gm.set_move(self.p, 'move/용의파동', reason='actual known Dragon attack')
        self.e.gm.set_move(self.p, 'move/불꽃세례', reason='actual non-Dragon control attack')
        self.e.gm.set_position(self.p, (7, 5), reason='actual attacker is the permitted nearby combatant')
        self.e.gm.set_position(self.b, (8, 5), reason='actual isolated target')
        self.e.gm.set_position(self.q, (1, 10), reason='other owned Pokemon outside two meters')
        self.combat(self.p)
        dragon = self.rules.move('move/용의파동')
        self.assertIsNone(TA.sustained(self.e, self.p, TA.uid('Highlander')))
        self.assertTrue(self.e._accuracy_check_native(self.p, self.b, dragon, fixed_roll=2)[0])
        self.assertFalse(self.e._accuracy_check_native(self.p, self.b,
            self.rules.move('move/불꽃세례'), fixed_roll=2)[0])
        for actor in (self.q, self.t):
            with self.subTest(other_combatant=actor.kind):
                original = actor.pos
                self.e.gm.set_position(actor, (10, 5), reason='another combatant exactly two meters from the target')
                self.assertFalse(self.e._accuracy_check_native(self.p, self.b, dragon, fixed_roll=2)[0])
                self.e.gm.set_position(actor, original, reason='restore actual distant combatant')
        self.assertEqual(self.p.budget['standard'], 1)
        self.valid()

    def test_errata_highlander_eighteen_threshold_uses_actual_attack_and_full_round_expiry(self):
        for face, slowed in ((17, False), (18, True)):
            with self.subTest(natural_accuracy=face):
                self.setup()
                self.family('드래곤', 'Tyrant’s Roar', 'Highlander')
                self.e.gm.set_move(self.p, 'move/용의파동', reason='actual known Dragon attack')
                self.e.gm.set_position(self.p, (7, 5), reason='actual isolated Dragon attacker')
                self.e.gm.set_position(self.b, (8, 5), reason='actual isolated target')
                self.e.gm.set_position(self.q, (1, 10), reason='other Pokemon beyond the isolation radius')
                self.combat(self.p)
                self.attack(self.p, self.b, 'move/용의파동', face=face)
                self.assertEqual('둔화' in self.b.conditions, slowed)
                if slowed:
                    self.e.end_of_turn(self.p)
                    self.assertIn('둔화', self.b.conditions)
                    self.e.end_round()
                    self.e.start_round(self.e.everyone)
                    self.e.at_initiative_count(31)
                    self.assertIn('둔화', self.b.conditions)
                    self.e.at_initiative_count(30)
                    self.assertNotIn('둔화', self.b.conditions)
                self.valid()

    def test_errata_unconquerable_binds_as_free_order_and_native_end_turn_save_cures_exactly_one(self):
        original_save = RECOVERY.saving_check
        statuses = ('화상', '혼란', '저주', '헤롱헤롱', '잠듦', '마비', '독', '맹독')
        for status in statuses:
            with self.subTest(chosen_affliction=status):
                self.setup()
                self.family('드래곤', 'Tyrant’s Roar', 'Unconquerable')
                self.communication()
                self.combat(self.t)
                before = AP.available(self.t)
                TA.activate(self.e, self.t, self.p, 'Unconquerable')
                self.assertEqual(AP.available(self.t), before - 2)
                self.assertEqual(self.t.budget['standard'], 1)
                self.e.end_of_turn(self.t)
                self.e.start_of_turn(self.p, initiative_count=20)
                other = '독' if status == '화상' else '화상'
                stored = '독' if status == '맹독' else status
                for condition in (status, other):
                    self.e.gm.add_condition(self.p, condition, applied_by=self.b,
                        reason='actual affliction before the native end-turn opportunity')
                self.answer('type_ace_choice', True)
                self.answer('type_ace_unconquerable_cure', stored)
                for face in (16, 17):
                    # Keep ordinary condition saves at natural 1. Both those
                    # saves and the additional DC17 check use the real formula;
                    # only the deterministic die is supplied to the native owner.
                    def native_save(engine, actor, condition, dc, **options):
                        return original_save(engine, actor, condition, dc,
                            fixed=face if condition is None else 1)
                    if face == 17:
                        self.e.end_round()
                        self.e.start_round(self.e.everyone)
                        with patch.object(Engine, 'd20', return_value=1):
                            self.e.start_of_turn(self.p, initiative_count=20)
                    with patch.object(RECOVERY, 'saving_check', side_effect=native_save) as observed:
                        self.e.end_of_turn(self.p)
                    self.assertEqual(sum(call.args[2] is None and call.args[3] == 17
                        for call in observed.call_args_list), 1)
                    self.assertEqual(stored in self.p.conditions, face == 16)
                    self.assertIn(other, self.p.conditions)
                self.valid()

    def test_errata_unconquerable_invalid_cure_selection_rolls_back_native_turn_end(self):
        self.family('드래곤', 'Tyrant’s Roar', 'Unconquerable')
        self.communication()
        self.combat(self.t)
        TA.activate(self.e, self.t, self.p, 'Unconquerable')
        self.e.end_of_turn(self.t)
        self.e.start_of_turn(self.p, initiative_count=20)
        self.e.gm.add_condition(self.p, '화상', reason='actual eligible affliction')
        self.e.gm.add_condition(self.p, '얼음', reason='actual affliction outside the printed cure list')
        self.answer('type_ace_choice', True)
        for choice in ('얼음', '독', ['화상', '얼음']):
            with self.subTest(choice=choice):
                self.answer('type_ace_unconquerable_cure', choice)
                self.rejected(lambda:self.e.end_of_turn(self.p), 'one actual|printed|affliction')

    def test_errata_this_will_not_stand_requires_above_half_crossing_and_respects_both_scene_limits(self):
        self.family('드래곤', 'Tyrant’s Roar', 'This Will Not Stand')
        self.e.gm.set_position(self.b, (3, 2), reason='actual adjacent incoming attack')
        self.combat(self.b)
        self.answer('type_ace_choice', True)
        # Already at the boundary is not a crossing from above it.
        self.e.gm.set_hp(self.p, value=self.p.max_hp // 2, reason='actual HP already at or below half')
        self.attack(self.b, self.p, 'move/몸통박치기')
        self.assertNotIn('난동', self.p.conditions)
        self.assertEqual([self.p.stages[s] for s in ('atk', 'spa', 'spe')], [0, 0, 0])
        self.next_turn(self.b)
        self.e.gm.set_hp(self.p, value=self.p.max_hp // 2 - 1,
            reason='actual HP already below half before a barrier-only hit')
        self.e.gm.set_temp_hp(self.p, 200, duration_seconds=300,
            reason='actual barrier absorbs all of the incoming attack')
        before_hp = self.p.hp
        self.attack(self.b, self.p, 'move/몸통박치기')
        self.assertEqual(self.p.hp, before_hp)
        self.assertLess(self.p.temp_hp, 200)
        self.assertNotIn('난동', self.p.conditions)
        self.e.gm.set_temp_hp(self.p, 0, reason='actual barrier is removed before the next crossing')
        for pokemon, activates in ((self.p, True), (self.p, False), (self.q, True)):
            with self.subTest(pokemon=pokemon.name, activates=activates):
                self.next_turn(self.b)
                self.e.gm.set_hp(pokemon, value=pokemon.max_hp // 2 + 1,
                    reason='actual HP immediately above half before a real loss')
                before = {s:pokemon.stages[s] for s in ('atk', 'spa', 'spe')}
                maximum = pokemon.max_hp  # the crossing is judged at the loss; a marker injury lowers the maximum afterwards
                if pokemon is self.p and activates:
                    self.e.lose_hp(pokemon, 1 + pokemon.max_hp % 2,
                        source='actual non-attack HP loss reaches the exact half boundary')
                else:
                    self.attack(self.b, pokemon, 'move/몸통박치기')
                self.assertLessEqual(pokemon.hp * 2, maximum)
                self.assertEqual({s:pokemon.stages[s] - before[s] for s in before},
                    dict.fromkeys(before, int(activates)))
                self.assertIn('난동', pokemon.conditions)
        third = self.add('third actual Dragon partner', 'pokemon', (4, 3),
            trainer_id=self.t.entity_id, types=['드래곤'])
        self.next_turn(self.b)
        self.e.gm.set_hp(third, value=third.max_hp // 2 + 1, reason='actual third eligible crossing after two trainer uses')
        self.attack(self.b, third, 'move/몸통박치기')
        self.assertNotIn('난동', third.conditions)
        self.assertEqual([third.stages[s] for s in ('atk', 'spa', 'spe')], [0, 0, 0])
        self.valid()

    def test_errata_incandescence_native_formula_uses_half_other_stat_or_both_full_stats_with_actual_mixed_power(self):
        for has_mixed_power in (False, True):
            with self.subTest(actual_mixed_power=has_mixed_power):
                self.setup()
                self.family('불꽃', 'Brightest Flame', 'Incandescence')
                spec = build_pokemon(self.rules, '피츄', 30, name='actual Mixed Power learner', moves=[], abilities=[],
                    extra={'trainer_id':self.t.entity_id, 'tutor_points':8})
                investments = dict.fromkeys(STATS, 0)
                investments.update(atk=5, spa=5, spe=30)
                plan = GROWTH.compose(species_lookup(self.rules, '피츄')['base_stats'],
                    investments, points=40, rules=self.rules, strategy='balanced')
                spec.update(stats=plan['stats'], initial_allocation=plan)
                # Preserve the builder's actual species size; the shared
                # acquisition fixture deliberately assumes Medium actors.
                self.p = FIX.Combatant(self.rules, spec)
                self.e.gm.add_combatant(self.p, pos=(6, 6), side='party',
                    reason='actual Pokemon with directly observed level-up investments')
                FIX.prepare_body(self.e, self.p, size=spec['size'], offsets=[(0, 0)],
                    reason='actual complete body of the built Pokemon')
                self.e.gm.set_types(self.p, ['불꽃'], reason='actual Fire Pokemon for the printed Incandescence target')
                self.e.gm.observe_loyalty(self.p, 6, reason='actual willing Pokemon')
                moves = ('move/불꽃펀치', 'move/불꽃세례', 'move/몸통박치기')
                for move in moves:
                    self.e.gm.set_move(self.p, move, reason='actual known formula comparison attack')
                if has_mixed_power:
                    points = self.p.spec['tutor_points']
                    EDGES.teach_mixed_power(self.e, self.t, self.p, safe=True)
                    self.assertEqual(self.p.spec['tutor_points'], points - 2)
                self.assertEqual(EDGES.mixed_power(self.p), has_mixed_power)
                self.communication()
                self.combat(self.t)
                self.e.change_stage(self.p, 'atk', 1)
                self.e.change_stage(self.p, 'spa', 2)
                before = {move:self.damage(self.p, self.b, move) for move in moves}
                TA.activate(self.e, self.t, self.p, 'Incandescence')
                for move, other in ((moves[0], 'spa'), (moves[1], 'atk')):
                    value = self.p.staged(other)
                    expected = value - value // 2 if has_mixed_power else value // 2
                    self.assertEqual(self.damage(self.p, self.b, move) - before[move], expected)
                    self.assertEqual(EDGES.prepare(self.e, self.p, self.rules.move(move))['class'],
                        self.rules.move(move)['class'])
                self.assertEqual(self.damage(self.p, self.b, moves[2]), before[moves[2]])
                self.restore()
                self.assertEqual(EDGES.mixed_power(self.p), has_mixed_power)
                self.valid()


if __name__ == '__main__':
    unittest.main()
