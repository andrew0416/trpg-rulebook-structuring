"""Human-authorized Stellar interpretation, distinct from absent and Normal types."""
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
import effects_ext as EXT
import homebrew_state as HOME
import state_grants as GRANTS
import stellar_tera_blast as STELLAR
import type_state as TYPES
import world_entities as WORLD
from tools import test_actual_damage_type_revision as DAMAGE

MOVES = ('move/테라버스트', 'move/테라버스트-물리', 'move/테라버스트-특수')


class StellarLiteralTypeDistinctionRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='homebrew')

    def world(self, *, active=True, target_types=('고스트',)):
        e = Engine(self.rules, seed=610663)
        e.grid = Grid(12, 12)
        a = Combatant(self.rules, build_pokemon(self.rules, '파이리', 30,
            name='Stellar source owner', abilities=['스텔라버스트'],
            moves=[*MOVES, 'move/불꽃세례', 'move/불사르기']))
        t = Combatant(self.rules, build_pokemon(self.rules, '팬텀', 100,
            name='Actual matchup recipient', abilities=[], moves=['move/몸통박치기']))
        e.gm.add_combatant(a, pos=(2, 2), side='party', reason='actual source ability holder')
        e.gm.add_combatant(t, pos=(3, 2), side='wild', reason='actual opposing target')
        e.gm.set_types(t, list(target_types), reason='explicit matchup observation')
        for stat in ('def', 'spd'):
            e.gm.set_stat(t, stat, value=20, reason='observable damage with a durable target')
        e.register_abilities(a)
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        HOME.observe_type(e, a, '스텔라', reason='human-authorized canonical Stellar interpretation')
        if active:
            HOME.observe_active(e, a, True, reason='actual Stellar state retaining Fire defense')
        return e, a, t

    def next_turn(self, e, actor):
        e.end_of_turn(actor)
        e.start_round(e.everyone)
        e.start_of_turn(actor, initiative_count=20)

    def hit(self, e, actor, target, uid, **options):
        if uid == MOVES[0]:
            options['versatile_stat'] = 'spa'
        with patch.object(Engine, 'd20', return_value=12):
            return e.use_move(actor, target, uid, set_damage=True, situational=100, **options)

    def expected(self, e, a, t, uid, *, factor=1, bonus=10):
        selected = 'spa' if uid == MOVES[0] else None
        db = 8 + (math.floor(e.formula('stab')) if uid == MOVES[0] else 0)
        base = DAMAGE.ActualDamageTypeRevisionTests().expected(
            e, a, t, uid, db, bonus=bonus, selected=selected)
        return math.floor(base * factor)

    def test_all_three_actual_moves_use_stellar_neutrality_not_normal_immunity(self):
        for uid in MOVES:
            for defenses in [('고스트',), ('바위', '강철'), ('노말',)]:
                with self.subTest(move=uid, defenses=defenses):
                    e, a, t = self.world(target_types=defenses)
                    move = self.rules.move(uid)
                    mm = self.rules.move_mech(uid)[0]
                    self.assertEqual(EXT.effective_type(e, a, t, move, mm, consume=False), '스텔라')
                    self.assertEqual(e.type_multiplier('스텔라', t)[0], 1)
                    before = t.hp
                    damage = self.hit(e, a, t, uid)
                    self.assertEqual(damage, self.expected(e, a, t, uid))
                    self.assertEqual(t.hp, before - damage)
                    self.assertEqual(a.types, ['불꽃'])
                    self.assertTrue(e.validate_state()['valid'])

    def test_each_stellar_move_gets_the_printed_single_step_for_actual_terastal_target(self):
        for uid in MOVES:
            with self.subTest(move=uid):
                e, a, t = self.world()
                HOME.observe_type(e, t, '강철', reason='actual ordinary target Tera choice')
                HOME.observe_active(e, t, True, reason='actual target Terastal')
                ctx = {}
                self.assertEqual(EXT.effectiveness_hook(e, a, t, self.rules.move(uid),
                    self.rules.move_mech(uid)[0], 1.0, ctx), 1.5)
                self.assertEqual(ctx['stellar_tera_blast']['sources'],
                    [STELLAR.rows(self.rules)[uid]['clause_id']])
                self.assertEqual(self.hit(e, a, t, uid), self.expected(e, a, t, uid, factor=1.5))

    def test_paid_radiation_choice_keeps_stellar_base_and_coalesces_overlapping_step(self):
        for choice in (False, True):
            with self.subTest(use_radiated_type=choice):
                e, a, t = self.world()
                self.assertGreater(self.hit(e, a, t, 'move/불꽃세례'), 0)
                opportunity = a.spec[STELLAR.STATE]['opportunities'][-1]
                e.gm.activate_stellar_blast(a, opportunity['id'], '고스트', reason='real enemy hit type')
                self.next_turn(e, a)
                HOME.observe_type(e, t, '고스트', reason='actual target Tera choice')
                HOME.observe_active(e, t, True, reason='actual target form change')
                uid = MOVES[2]
                prepared = STELLAR.prepare(e, a, self.rules.move(uid), choice)
                actual = EXT.effective_type(e, a, t, prepared, self.rules.move_mech(uid)[0], consume=False)
                self.assertEqual(actual, '고스트' if choice else '스텔라')
                base = e.type_multiplier(actual, t)[0]
                ctx = {}
                factor = EXT.effectiveness_hook(e, a, t, prepared, self.rules.move_mech(uid)[0], base, ctx)
                self.assertEqual(factor, 2 if choice else 1.5)
                self.assertEqual(len(ctx['stellar_tera_blast']['sources']), 1 if choice else 2)
                self.assertEqual(self.hit(e, a, t, uid, use_radiated_type=choice),
                    self.expected(e, a, t, uid, factor=factor))
                completion = list(e._move_completions.values())[-1]
                self.assertEqual(completion['move'][STELLAR.CHOICE]['base_type'], '스텔라')
                self.assertEqual(a.types, ['불꽃'])

    def test_stellar_defense_is_not_typeless_or_normal_and_blocks_type_loss(self):
        e, a, t = self.world()
        self.assertEqual(e.type_multiplier('땅', a)[0], 1.5)
        before = deepcopy(a.spec)
        self.assertFalse(GRANTS.type_operation(a, 'remove', ['불꽃'], 'source/blocked-fire-loss'))
        self.assertEqual(a.spec, before)
        GRANTS.type_operation(t, 'remove', ['고스트'], 'source/explicit-last-type-loss')
        self.assertEqual(t.types, [])
        self.assertFalse(HOME.tera_active(t))
        for attack in TYPES.CORE_TYPES:
            self.assertEqual(e.type_multiplier(attack, t)[0], 1)
        self.assertEqual(e.type_multiplier('고스트', a)[0], 1)
        e.gm.set_types(t, ['노말'], reason='Normal differs from absent types')
        GRANTS.remove_owned(e, t, 'source/explicit-last-type-loss')
        self.assertEqual(t.types, ['노말'])
        self.assertEqual(e.type_multiplier('고스트', t)[0], 0)
        self.assertEqual(e.type_multiplier('격투', t)[0], 1.5)

    def test_korean_burn_up_normal_fallback_does_not_grant_stellar_state(self):
        e, a, t = self.world(active=False, target_types=('노말',))
        self.assertEqual(a.types, ['불꽃'])
        self.assertGreater(self.hit(e, a, t, 'move/불사르기'), 0)
        self.assertEqual(a.types, ['노말'])
        self.assertFalse(HOME.tera_active(a))
        self.assertEqual(e.type_multiplier('고스트', a)[0], 0)
        self.assertEqual(e.type_multiplier('격투', a)[0], 1.5)
        move = self.rules.move(MOVES[2])
        self.assertEqual(EXT.effective_type(e, a, t, move,
            self.rules.move_mech(move['id'])[0], consume=False), '노말')

    def test_gm_and_fresh_rules_json_preserve_stellar_and_empty_defense_separately(self):
        e, a, t = self.world()
        GRANTS.type_operation(t, 'remove', ['고스트'], 'source/explicit-last-type-loss')
        e.gm.snapshot('Stellar and absent type')
        e.end_scene()
        e.gm.restore('Stellar and absent type', reason='restore independent source states')
        ids = a.entity_id, t.entity_id
        receipt = deepcopy(a.spec[HOME.KEY])
        fresh = Rules(str(ROOT), ruleset='homebrew')
        e = Engine.import_state(fresh, json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        a, t = (WORLD.actor_index(e)[uid] for uid in ids)
        self.assertEqual(a.spec[HOME.KEY], receipt)
        self.assertEqual(a.types, ['불꽃'])
        self.assertEqual(t.types, [])
        self.assertTrue(HOME.tera_active(a))
        self.assertEqual(e.type_multiplier('땅', a)[0], 1.5)
        self.assertEqual(e.type_multiplier('땅', t)[0], 1)
        e.end_scene()
        self.assertFalse(HOME.tera_active(a))
        self.assertEqual(a.types, ['불꽃'])
        self.assertTrue(e.validate_state()['valid'])

    def test_stellar_is_attack_only_and_question_marks_do_not_create_a_type(self):
        e, a, t = self.world()
        self.assertNotIn('스텔라', TYPES.allowed_types(self.rules))
        self.assertNotIn('스텔라', TYPES.attack_types(self.rules))
        for value in ('스텔라', '??', '???'):
            before = deepcopy(t.spec)
            rng = e.rng.getstate()
            with self.assertRaises(ValueError):
                e.gm.set_types(t, [value], reason='not an ordinary defensive type')
            self.assertEqual(t.spec, before)
            self.assertEqual(e.rng.getstate(), rng)
        for value in ('??', '???'):
            with self.assertRaises(ValueError):
                e.type_multiplier(value, t)
        core = Rules(str(ROOT), ruleset='core')
        with self.assertRaises(ValueError):
            TYPES.validate_attack(core, '스텔라')
        self.assertEqual(e.type_multiplier('스텔라', t)[0], 1)


if __name__ == '__main__':
    unittest.main()
