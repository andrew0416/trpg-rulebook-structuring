"""Native user permissions remain separate from source-default type legality."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import math
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from builder import build_pokemon
from engine import Combatant, Engine, Rules
from grid import Grid
from ruleset import RuleFilter
import effects_ext as EXT
import homebrew_state as HOME
import personal_type_settings as PERSONAL
import attack_damage_history as HISTORY
import state_grants as GRANTS
import type_state as TYPES
import world_entities as WORLD
from native_scenario_fixture import assert_rejected_unchanged
from tools import test_actual_damage_type_revision as DAMAGE

PROFILE = 'personal-stellar-typeless'
MOVES = ('move/테라버스트', 'move/테라버스트-물리', 'move/테라버스트-특수')


class PersonalStellarTypelessRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset=PROFILE)
        cls.default = Rules(str(ROOT), ruleset='homebrew')

    def world(self, rules=None):
        rules = rules or self.rules
        e = Engine(rules, seed=20261024)
        e.grid = Grid(12, 12)
        a = Combatant(rules, build_pokemon(rules, '파이리', 30,
            name='Personal setting owner', abilities=[], moves=[*MOVES, 'move/불꽃세례']))
        t = Combatant(rules, build_pokemon(rules, '팬텀', 100,
            name='Real Ghost target', abilities=[], moves=['move/몸통박치기']))
        e.gm.add_combatant(a, pos=(2, 2), side='party', reason='actual Pokemon owner')
        e.gm.add_combatant(t, pos=(3, 2), side='wild', reason='actual opposing target')
        e.gm.set_types(t, ['고스트'], reason='observed single Ghost recipient')
        for stat in ('def', 'spd'):
            e.gm.set_stat(t, stat, value=20, reason='durable observable damage target')
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        return e, a, t

    def force_typeless(self, e, a):
        HOME.observe_type(e, a, PERSONAL.TYPELESS, reason='explicit personal forced Tera choice')
        return HOME.observe_active(e, a, True, reason='GM forces the user-defined typeless form')

    def test_non_tera_stellar_has_identity_stab_and_neutral_defense_without_ability(self):
        e, a, t = self.world()
        e.gm.set_types(a, ['스텔라'], reason='user permits a non-Tera Stellar Pokemon')
        self.assertEqual(a.types, ['스텔라'])
        self.assertEqual(a.abilities, [])
        self.assertFalse(HOME.tera_active(a))
        self.assertIsNone(HOME.tera_type(a))
        self.assertEqual(HOME.stab_types(a), ['스텔라'])
        self.assertIn('스텔라', TYPES.attack_types(self.rules))
        for attack in TYPES.CORE_TYPES:
            self.assertEqual(e.type_multiplier(attack, a)[0], 1)
        self.assertEqual(e.type_multiplier('스텔라', t)[0], 1)
        move = self.rules.move(MOVES[2])
        self.assertEqual(EXT.effective_type(e, a, t, move,
            self.rules.move_mech(move['id'])[0], consume=False), '노말')
        GRANTS.type_operation(a, 'add', ['불꽃'], 'personal/test-secondary-type')
        self.assertEqual(e.type_multiplier('땅', a)[0], 1.5)
        GRANTS.remove_owned(e, a, 'personal/test-secondary-type')
        self.assertEqual(a.types, ['스텔라'])
        self.assertTrue(e.validate_state()['valid'])

    def test_forced_typeless_form_is_active_with_empty_defense_and_no_type_bonus(self):
        # Historical ID retained; the user now defines an ordinary neutral Tera type.
        e, a, _ = self.world()
        row = self.force_typeless(e, a)
        self.assertEqual(row['source'], PERSONAL.SOURCE)
        self.assertTrue(HOME.tera_active(a))
        self.assertEqual(HOME.tera_type(a), PERSONAL.TYPELESS)
        self.assertEqual(a.types, [PERSONAL.TYPELESS])
        self.assertEqual(HOME.stab_types(a), ['불꽃'])
        self.assertEqual(HOME.ability_stab_types(a), ['불꽃', PERSONAL.TYPELESS])
        self.assertIn(PERSONAL.TYPELESS, TYPES.allowed_types(self.rules))
        self.assertIn(PERSONAL.TYPELESS, TYPES.attack_types(self.rules))
        self.assertEqual(HOME.damage_bonus(a, {'type': PERSONAL.TYPELESS}), 10)
        self.assertEqual(HOME.damage_bonus(a, {'type': '노말'}), 0)
        for attack in TYPES.CORE_TYPES:
            self.assertEqual(e.type_multiplier(attack, a)[0], 1)
            self.assertEqual(TYPES.matchup(self.rules, PERSONAL.TYPELESS, attack), 1)
        self.assertNotEqual(a.types, [])
        self.assertNotEqual(a.types, ['노말'])
        before = deepcopy(a.spec)
        self.assertFalse(GRANTS.type_operation(a, 'add', ['스텔라'], 'personal/blocked-type-change'))
        self.assertEqual(a.spec, before)
        e.end_scene()
        self.assertFalse(HOME.tera_active(a))
        self.assertEqual(a.types, ['불꽃'])
        self.assertEqual(HOME.tera_type(a), PERSONAL.TYPELESS)

    def test_all_three_paid_tera_blasts_are_typeless_neutral_without_matching_ten(self):
        # Historical ID retained; ordinary matching-type +10 now applies.
        for uid in MOVES:
            with self.subTest(move=uid):
                e, a, t = self.world()
                self.force_typeless(e, a)
                move = self.rules.move(uid)
                self.assertEqual(EXT.effective_type(e, a, t, move,
                    self.rules.move_mech(uid)[0], consume=False), PERSONAL.TYPELESS)
                db = 8 + (math.floor(e.formula('stab')) if uid == MOVES[0] else 0)
                expected = DAMAGE.ActualDamageTypeRevisionTests().expected(e, a, t, uid, db,
                    bonus=10, selected='spa' if uid == MOVES[0] else None)
                options = {'versatile_stat': 'spa'} if uid == MOVES[0] else {}
                before = t.hp
                with patch.object(Engine, 'd20', return_value=12):
                    damage = e.use_move(a, t, uid, set_damage=True, situational=100, **options)
                self.assertGreater(damage, 0)
                self.assertEqual(damage, expected)
                self.assertEqual(t.hp, before - damage)
                self.assertEqual(a.types, [PERSONAL.TYPELESS])
                self.assertEqual(HISTORY.records(t)[-1]['move_type'], PERSONAL.TYPELESS)
                self.assertTrue(e.validate_state()['valid'])
                restored = Engine.import_state(Rules(str(ROOT), ruleset=PROFILE),
                    json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
                restored_target = WORLD.actor_index(restored)[t.entity_id]
                self.assertEqual(HISTORY.records(restored_target), HISTORY.records(t))
                self.assertTrue(restored.validate_state()['valid'])

    def test_gm_and_fresh_rules_json_keep_stellar_and_typeless_forms_distinct(self):
        e, a, t = self.world()
        e.gm.set_types(t, ['스텔라'], reason='ordinary Stellar recipient')
        receipt = self.force_typeless(e, a)
        ids = a.entity_id, t.entity_id
        e.gm.snapshot('personal types')
        e.end_scene()
        e.gm.restore('personal types', reason='restore separate user states')
        fresh = Rules(str(ROOT), ruleset=PROFILE)
        e = Engine.import_state(fresh, json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        a, t = (WORLD.actor_index(e)[uid] for uid in ids)
        self.assertEqual(a.spec[HOME.KEY], receipt)
        self.assertEqual(a.types, [PERSONAL.TYPELESS])
        self.assertEqual(t.types, ['스텔라'])
        self.assertTrue(HOME.tera_active(a))
        self.assertFalse(HOME.tera_active(t))
        e.end_scene()
        self.assertEqual(a.types, ['불꽃'])
        self.assertEqual(t.types, ['스텔라'])
        self.assertTrue(e.validate_state()['valid'])

    def test_default_profiles_reject_permissions_and_question_marks_remain_invalid(self):
        e, a, _ = self.world(self.default)
        assert_rejected_unchanged(e, lambda: e.gm.set_types(a, ['스텔라'], reason='default legality'),
            reason_pattern='unknown or unselected type')
        assert_rejected_unchanged(e, lambda: HOME.observe_type(e, a, PERSONAL.TYPELESS, reason='default legality'),
            reason_pattern='personal typeless Terastal permission')
        e, a, _ = self.world()
        for name in ('??', '???'):
            assert_rejected_unchanged(e,
                lambda name=name: e.gm.set_types(a, [name], reason='not a defensive identity'),
                reason_pattern='unknown or unselected type')
        for name in ('??', '???'):
            assert_rejected_unchanged(e,
                lambda name=name: HOME.observe_type(e, a, name, reason='not a Tera selector'),
                reason_pattern='unknown or unselected type')

    def test_absence_markers_cannot_be_reintroduced_as_custom_defensive_types(self):
        r = Rules(str(ROOT), ruleset=PROFILE)
        for name in ('None', PERSONAL.TYPELESS, '??', '???'):
            with self.subTest(marker=name), patch.dict(r.ruleset.profile,
                    {'type_extensions': {name: {}}}):
                with self.assertRaisesRegex(ValueError, 'reserved identity'):
                    TYPES.allowed_types(r)

    def test_burn_up_and_neutral_tera_share_one_type_with_only_tera_bonus_added(self):
        e, a, t = self.world()
        e.gm.set_move(a, 'move/불사르기', reason='actual learned Burn Up')
        with patch.object(Engine, 'd20', return_value=12):
            e.use_move(a, t, 'move/불사르기', set_damage=True, situational=100)
        self.assertEqual(a._types, [])
        self.assertEqual(a.types, [PERSONAL.TYPELESS])
        self.assertFalse(HOME.tera_active(a))
        self.assertEqual(HOME.damage_bonus(a, {'type': PERSONAL.TYPELESS}), 0)
        sources=a.spec[GRANTS.KEY]['sources'].values()
        self.assertTrue(any(row.get('personal_type_setting',{}).get('source')==PERSONAL.NEUTRAL_SOURCE for row in sources))
        e.gm.set_types(t, [], reason='another actual typeless Pokemon')
        self.assertEqual(a.types, t.types)
        before_types=list(a.types)
        self.force_typeless(e, a)
        self.assertEqual(a.types, before_types)
        self.assertEqual(HOME.stab_types(a), [PERSONAL.TYPELESS])
        self.assertEqual(HOME.damage_bonus(a, {'type': PERSONAL.TYPELESS}), 10)
        e.end_of_turn(a);e.end_round();e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        db=8+math.floor(e.formula('stab'))
        expected=DAMAGE.ActualDamageTypeRevisionTests().expected(e,a,t,MOVES[1],db,bonus=10)
        before=t.hp
        with patch.object(Engine,'d20',return_value=12):
            dealt=e.use_move(a,t,MOVES[1],set_damage=True,situational=100)
        self.assertEqual((dealt,before-t.hp),(expected,expected))
        loaded=Engine.import_state(Rules(str(ROOT),ruleset=PROFILE),json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        self.assertEqual(WORLD.actor_index(loaded)[a.entity_id].types,[PERSONAL.TYPELESS])
        self.assertTrue(loaded.validate_state()['valid'])

    def test_unselected_personal_policy_keeps_printed_burn_up_fallback(self):
        e,a,t=self.world(self.default)
        e.gm.set_move(a,'move/불사르기',reason='actual printed-rule Burn Up')
        with patch.object(Engine,'d20',return_value=12):
            e.use_move(a,t,'move/불사르기',set_damage=True,situational=100)
        self.assertEqual(a.types,['노말'])
        self.assertTrue(e.validate_state()['valid'])

    def test_permission_schema_is_boolean_and_selected_policy_cannot_change_silently(self):
        for value in (None, [], {'ordinary_stellar': 1}, {'typeless_tera': 'yes'}, {'typo': True}):
            with self.subTest(settings=value), self.assertRaisesRegex(ValueError, 'named boolean permissions'):
                RuleFilter({PERSONAL.KEY: value})
        r = Rules(str(ROOT), ruleset=PROFILE)
        e, a, _ = self.world(r)
        e.gm.set_types(a, ['스텔라'], reason='actual custom type before durable save')
        saved = e.export_state()
        with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
            Engine.import_state(self.default, saved)
        r.ruleset.profile[PERSONAL.KEY]['ordinary_stellar'] = False
        with self.assertRaisesRegex(ValueError, 'selection_profile_changed_rebuild_required'):
            r._selected_rule('move/테라버스트')


if __name__ == '__main__':
    unittest.main()
