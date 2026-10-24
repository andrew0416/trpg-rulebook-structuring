"""Missing core Suction Cups identity and its actual Push/Roar consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine
from ruleset import RuleFilter, ExcludedRuleSelection, UnresolvedRuleSelection
import core_suction_cups as SUCTION
import effects as FX
import forced_movement as FORCED
import roar as ROAR
import state_codec as CODEC
import world_entities as WORLD
import test_category3_physics_maneuvers as PHYSICS
import test_book_style_move_dependencies as STYLE


class CoreSuctionCupsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def physics(self, ability=SUCTION.NAME):
        case = PHYSICS.Tests()
        case.r = self.rules
        case.setUp()
        case.e.gm.set_ability(case.b, ability, reason='observed core Suction Cups')
        return case

    def style(self, stat='아름다움'):
        case = STYLE.StyleMoveDependencyTests()
        case.rules = self.rules
        case.setup(stat)
        return case

    def test_core_and_both_playtest_source_identities_remain_distinct(self):
        self.assertEqual(self.rules._selected_rule(SUCTION.SOURCE), SUCTION.SOURCE)
        self.assertEqual(SUCTION.registration(self.rules, SUCTION.SOURCE), {'name': SUCTION.NAME, 'source_id': SUCTION.SOURCE})
        SUCTION.validate_core_ability(self.rules, self.rules.core_abilities[SUCTION.SOURCE])
        self.assertEqual(self.rules.core_abilities[SUCTION.SOURCE]['native_contract']['effects'], ['push', 'roar'])
        for uid in ('ability/흡반-playtest', 'ability/흡반-playtest-2'):
            with self.assertRaises(ExcludedRuleSelection):
                self.rules._selected_rule(uid)
        rows = json.loads((ROOT / 'output/entities/abilities.json').read_text(encoding='utf-8'))
        variants = [row for row in rows if row['id'] in ('ability/흡반-playtest', 'ability/흡반-playtest-2')]
        self.assertEqual([row['_source']['record_span'] for row in variants], [[482, 482], [493, 493]])
        for row in variants:
            self.assertIn('+5', row['effect'])
            self.assertIn('이동 행동', row['frequency'])
            self.assertNotIn('Roar', row['effect'])

    def test_exclusion_ambiguity_and_explicit_variant_selection_do_not_choose_core_implicitly(self):
        profile = deepcopy(self.rules.ruleset.profile)
        profile['exclude_units'] = [SUCTION.SOURCE]
        with patch.object(RuleFilter, 'load', return_value=RuleFilter(profile)):
            excluded = Rules(ROOT, ruleset='core')
        with self.assertRaises(ExcludedRuleSelection):
            excluded._selected_rule(SUCTION.SOURCE)
        ambiguous = Rules(ROOT, ruleset='playtest')
        with self.assertRaises(UnresolvedRuleSelection):
            ambiguous._selected_rule(SUCTION.SOURCE)
        for uid in ('ability/흡반-playtest', 'ability/흡반-playtest-2'):
            profile = deepcopy(ambiguous.ruleset.profile)
            profile['variant_choices'] = {SUCTION.SOURCE: uid}
            with patch.object(RuleFilter, 'load', return_value=RuleFilter(profile)):
                selected = Rules(ROOT, ruleset='playtest')
            self.assertEqual(selected._selected_rule(SUCTION.SOURCE), uid)
            self.assertEqual(selected._selected_rule(uid), uid)

    def test_native_push_spends_its_action_but_cannot_move_the_core_holder(self):
        case = self.physics(SUCTION.SOURCE)
        origin = case.b.pos
        before = (case.b.hp, deepcopy(case.b.budget), case.b.damage_reduction)
        result = case.push()
        self.assertEqual((result['pushed_metres'], result['follow_metres']), (0, 0))
        self.assertEqual(case.b.pos, origin)
        self.assertEqual((case.b.hp, case.b.budget, case.b.damage_reduction), before)
        self.assertEqual(case.a.budget['standard'], 0)

    def test_push_effect_is_blocked_but_general_forced_displacement_is_not(self):
        case = self.physics()
        origin = case.b.pos
        FX.h_push(case.e, case.a, case.b, {'meters': 2}, {'source_id': 'move/몸통박치기'})
        self.assertEqual(case.b.pos, origin)
        result = FORCED.displace(case.e, case.a, case.b, direction=(1, 0), distance=1,
                                 source='observed non-Push displacement')
        self.assertEqual((result['moved'], case.b.pos), (1, (origin[0] + 1, origin[1])))

    def test_actual_defensive_ability_bypass_preserves_suction_cups_ownership(self):
        case = self.physics()
        case.e.gm.set_ability(case.a, '틀깨기', reason='actual selected Mold Breaker')
        self.assertIn(SUCTION.NAME, case.b.abilities)
        result = case.push()
        self.assertEqual((result['pushed_metres'], case.b.pos), (1, (3, 1)))
        self.assertIn(SUCTION.NAME, case.b.abilities)
        case.a.abilities_suppressed = True
        FX.h_push(case.e, case.a, case.b, {'meters': 1}, {'source_id': 'move/몸통박치기'})
        self.assertEqual(case.b.pos, (3, 1))

    def test_native_macho_charge_keeps_actual_move_context_and_defensive_bypass(self):
        import style_expert as STYLE_EFFECT
        import type_ace as TYPE_ACE
        for bypass in (False, True):
            with self.subTest(bypass=bypass):
                case = self.style('강인함')
                case.family(effect=True)
                case.e.gm.set_ability(case.b, SUCTION.NAME, reason='actual core holder')
                if bypass:
                    case.e.gm.set_ability(case.p, '틀깨기', reason='actual selected defensive bypass')
                case.combat()
                origin = case.b.pos
                with patch.object(TYPE_ACE, 'push_immunity', wraps=TYPE_ACE.push_immunity) as immunity:
                    case.use('move/겁나는얼굴', ranked=STYLE_EFFECT.RANKED[case.stat],
                             effect=STYLE_EFFECT.IMPROVE[case.stat])
                self.assertEqual(immunity.call_count, 1)
                self.assertEqual(immunity.call_args.kwargs['move']['id'], 'move/겁나는얼굴')
                self.assertEqual(immunity.call_args.kwargs['attacker'].entity_id, case.p.entity_id)
                self.assertEqual(case.b.pos, (origin[0] + 3, origin[1]) if bypass else origin)
                self.assertEqual(case.b.stages['spe'], -2)
                self.assertIn(SUCTION.NAME, case.b.abilities)
                self.assertEqual(case.p.move_uses['move/겁나는얼굴'], 1)
                case.restored()
                self.assertTrue(case.e.validate_state()['valid'])

    def test_live_suppression_loss_and_json_restore_preserve_only_actual_core_ownership(self):
        case = self.style()
        case.e.gm.set_ability(case.b, SUCTION.NAME, reason='actual core holder')
        identity = case.b.entity_id
        self.assertTrue(SUCTION.active(case.e, case.b))
        case.b.abilities_suppressed = True
        self.assertFalse(SUCTION.active(case.e, case.b))
        case.b.abilities_suppressed = False
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(case.e))))
        holder = WORLD.actor_index(loaded)[identity]
        self.assertTrue(SUCTION.active(loaded, holder))
        loaded.gm.set_ability(holder, SUCTION.NAME, add=False, reason='observed actual ability loss')
        self.assertFalse(SUCTION.active(loaded, holder))
        self.assertTrue(loaded.validate_state()['valid'])

    def test_native_roar_round_end_and_json_restore_require_no_retreat_for_immune_target(self):
        for immune in (True, False):
            with self.subTest(immune=immune):
                case = self.style()
                if immune:
                    case.e.gm.set_ability(case.b, SUCTION.NAME, reason='actual core holder')
                case.e.gm.set_move(case.p, ROAR.SOURCE, reason='actual learned Roar')
                case.combat()
                retreats = {} if immune else {case.b.entity_id: {'path': [(x, 5) for x in range(7, 13)], 'mode': 'land'}}
                ROAR.choose(case.e, case.p, shift=[], retreats=retreats, reason='actual Roar choices')
                with patch.object(Engine, 'd20', return_value=19):
                    case.e.use_move_on(case.p, case.b, ROAR.SOURCE, case.e.everyone, set_damage=True)
                case.e.end_of_turn(case.p)
                case.restored()
                with patch.object(Engine, 'd20', return_value=19):
                    case.e.end_round()
                self.assertEqual(case.b.pos, (6, 5) if immune else (12, 5))
                self.assertTrue(case.b.on_field)
                self.assertEqual(case.p.move_uses[ROAR.SOURCE], 1)
                self.assertTrue(case.e.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
