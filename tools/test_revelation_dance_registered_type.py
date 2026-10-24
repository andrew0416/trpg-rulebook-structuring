"""R559 registered first type; Dance-use counting remains a separate obligation."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import math
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from grid import Grid
from ruleset import RuleFilter, RuleSelection
import attack_damage_history as HISTORY
import custom_species as CUSTOM
import declarative_move_contracts as DECLARATIVE
import effects_ext as EXT
import homebrew_state as HOME
import native_scenario_fixture as NATIVE
import world_entities as WORLD

MOVE = 'move/잠재댄스'
BAILE = 'pokemon/춤추새-이글이글스타일'
SENSU = 'pokemon/춤추새-하늘하늘스타일'


class RevelationDanceRegisteredTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = Rules(ROOT, ruleset='core')
        cls.tera_rules = Rules(ROOT, ruleset='homebrew')

    def world(self, species=BAILE, target_species='이브이', *, rules=None):
        rules = rules or self.core
        e = Engine(rules, seed=55940)
        e.grid = Grid(20, 20)
        # Use the actual sourced Lv40 list, including its R559 opportunity.
        a = Combatant(rules, build_pokemon(rules, species, 40, abilities=[]))
        t = Combatant(rules, build_pokemon(rules, target_species, 60,
            abilities=[], side='foe'))
        e.gm.add_combatant(a, pos=(2, 2), side='party', reason='observed registered dancer')
        e.gm.add_combatant(t, pos=(3, 2), side='foe', reason='observed actual recipient')
        for actor in (a, t):
            NATIVE.prepare_body(e, actor, size=actor.spec['size'], offsets=[(0, 0)],
                reason='observed one-cell battle footprint')
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        self.assertIn(MOVE, a.moves)
        return e, a, t

    def restore(self, e, a, t):
        restored = Engine.import_state(e.r, json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        index = WORLD.actor_index(restored)
        return restored, index[a.entity_id], index[t.entity_id]

    def actual_hit(self, e, a, t, *, face=12):
        observations = []
        formulas = []
        original = EXT.effectiveness_hook
        original_damage = Engine.roll_damage
        def observe(engine, attacker, target, move, mm, mult, ctx):
            result = original(engine, attacker, target, move, mm, mult, ctx)
            if move['id'] == MOVE and ctx.get('hit') is True:
                observations.append((ctx['actual_damage_type'], result))
            return result
        def observe_damage(engine, attacker, target, move, *args, **kwargs):
            result = original_damage(engine, attacker, target, move, *args, **kwargs)
            if move['id'] == MOVE:
                formulas.append(deepcopy(kwargs['_reaction_event']['damage_formula']))
            return result
        before_hp = t.hp
        before_temp = t.temp_hp
        with patch.object(Engine, 'd20', return_value=face), patch.object(EXT, 'effectiveness_hook', side_effect=observe), patch.object(Engine, 'roll_damage', new=observe_damage):
            dealt = e.use_move(a, t, MOVE, situational=100, set_damage=True)
        self.assertEqual(a.budget['standard'], 0)
        if face == 1:
            self.assertEqual(dealt, 0)
            self.assertEqual(HISTORY.records(t), [])
            self.assertEqual(observations, [])
            return dealt, observations
        record = HISTORY.records(t)[-1]
        self.assertEqual(record['receipt']['source'], MOVE)
        self.assertEqual(record['receipt']['damage_class'], '특수')
        self.assertEqual(record['attacker_id'], a.entity_id)
        self.assertEqual(record['target_id'], t.entity_id)
        self.assertEqual(record['receipt']['requested'], dealt)
        self.assertEqual(HISTORY.amount(record), before_hp-t.hp+before_temp-t.temp_hp)
        self.assertEqual(record['move_type'], observations[-1][0])
        self.assertEqual(len(formulas), 1)
        formula = formulas[0]
        self.assertEqual(formula['multiplier'], observations[-1][1])
        self.assertEqual(dealt, max(0, math.floor(formula['after_defense']*formula['multiplier']*formula['other_multiplier'])+formula['adjustment']))
        return dealt, observations

    def test_baile_resistance_tie_and_weakness_are_mandatory_fire_native_hits(self):
        for target, multiplier in (('꼬부기', .5), ('이브이', 1.0), ('이상해꽃', 1.5)):
            with self.subTest(target=target):
                e, a, t = self.world(target_species=target)
                species = e.r.species[a.spec['species']]
                self.assertEqual(species['_source']['record_span'], [780, 780])
                self.assertEqual(species['types'], ['불꽃', '비행'])
                self.assertIn({'to': MOVE, 'source': 'level_up', 'level': 40},
                    e.r.learnset_links[species['name']]['moves'])
                move = deepcopy(e.r.move(MOVE))
                self.assertEqual(move['_source']['record_span'], [559, 559])
                self.assertEqual((move['damage_base'], move['ac'], move['class'], move['type']), (9, 2, '특수', '노말'))
                mm = e.r.move_mech(MOVE)[0]
                before = e.export_state()
                self.assertEqual(EXT.effective_type(e, a, t, move, mm, consume=False), '불꽃')
                self.assertEqual(e.damage_base(a, move, target=t), 9+math.floor(e.formula('stab')))
                # damage_base emits the actual STAB diagnostic; every other byte of state remains unchanged.
                root = before['nodes'][before['root']['$ref']]
                attrs = dict(before['nodes'][root['attrs']['$ref']]['items'])
                before['nodes'][attrs['log_lines']['$ref']]['items'].append(
                    f"    자속보정: DB 9 → {9+math.floor(e.formula('stab'))}  => [combat/stab]")
                self.assertEqual(e.export_state(), before)
                dealt, observed = self.actual_hit(e, a, t)
                self.assertEqual(observed, [('불꽃', multiplier)])
                self.assertGreater(dealt, 0)
                self.assertEqual(e.r.move(MOVE), move)
                self.assertTrue(self.restore(e, a, t)[0].validate_state()['valid'])

    def test_sensu_normal_immunity_uses_ghost_and_keeps_native_cost_and_receipt(self):
        e, a, t = self.world(SENSU)
        self.assertEqual(e.r.species[a.spec['species']]['_source']['record_span'], [783, 783])
        self.assertEqual(e.r.species[a.spec['species']]['types'], ['고스트', '비행'])
        before = t.hp
        dealt, observed = self.actual_hit(e, a, t)
        self.assertEqual((dealt, t.hp), (0, before))
        self.assertEqual(observed, [('고스트', 0.0)])
        self.assertEqual(HISTORY.amount(HISTORY.records(t)[-1]), 0)
        self.assertTrue(self.restore(e, a, t)[0].validate_state()['valid'])

    def test_all_registered_catalog_forms_keep_their_order_without_a_form_label_guess(self):
        forms = ((BAILE, '불꽃', 780), ('pokemon/춤추새-훌라훌라스타일', '에스퍼', 781),
                 ('pokemon/춤추새-파칙파칙스타일', '전기', 782), (SENSU, '고스트', 783))
        for sid, first, record in forms:
            with self.subTest(species=sid):
                e, a, t = self.world(sid)
                self.assertEqual(a.spec['species'], sid)
                self.assertEqual(e.r.species[sid]['_source']['record_span'], [record, record])
                note = e.r.learnsets[e.r.species[sid]['name']]['note']
                self.assertIn('꿀', note)
                self.assertIn(first, note)
                move = e.r.move(MOVE)
                self.assertEqual(EXT.effective_type(e, a, t, move, e.r.move_mech(MOVE)[0], consume=False), first)
                self.assertEqual(self.restore(e, a, t)[1].spec['species'], sid)

    def test_gm_base_type_and_active_tera_do_not_rewrite_registration_through_both_restores(self):
        for mode in ('gm_base', 'tera'):
            with self.subTest(mode=mode):
                e, a, t = self.world(rules=self.tera_rules if mode == 'tera' else self.core)
                registered = deepcopy(e.r.species[BAILE])
                if mode == 'gm_base':
                    e.gm.set_types(a, ['물', '비행'], reason='observed individual base-type edit, no species registration')
                else:
                    HOME.observe_type(e, a, '물', reason='observed ordinary Tera choice')
                    HOME.observe_active(e, a, True, reason='observed selected active Tera form')
                self.assertEqual(a.types[0], '물')
                e.gm.snapshot('registered-dance')
                e.gm.restore('registered-dance')
                e, a, t = self.restore(e, a, t)
                self.assertEqual(a.types[0], '물')
                self.assertEqual(a.spec['species'], BAILE)
                self.assertEqual(e.r.species[BAILE], registered)
                before = e.export_state()
                self.assertEqual(EXT.effective_type(e, a, t, e.r.move(MOVE), e.r.move_mech(MOVE)[0], consume=False), '불꽃')
                self.assertEqual(e.export_state(), before)
                _, observed = self.actual_hit(e, a, t)
                self.assertEqual(observed, [('불꽃', 1.0)])

    def test_explicit_custom_species_registration_is_distinct_from_individual_gm_typing(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'registered-dancer.json'
            definition = CUSTOM.template_from(self.core, BAILE, '도감등록댄서', author='actual GM')
            # This GM-authored dancer deliberately has no Abilities, matching world(abilities=[]).
            # A copied draft's unresolved bare Adaptability is not a core registration.
            definition.update(types=['물', '비행'], abilities={}, dex='GM559',
                learnset={'level_up': [{'level': 40, 'move': '잠재댄스'}], 'tm': [], 'egg': [], 'tutor': []})
            path.write_text(json.dumps(definition, ensure_ascii=False), encoding='utf-8')
            rules = Rules(ROOT, ruleset='core')
            rules.ruleset = RuleFilter({'sources': ['core', 'custom'], 'variants': []})
            registered = rules.load_custom_species(str(path))
            self.assertIn(registered['id'], rules.custom_species)
            self.assertEqual(rules._selected_rule(registered['id']), registered['id'])
            self.assertEqual(registered['types'], ['물', '비행'])
            excluded = Rules(ROOT, ruleset='core', custom_species=[str(path)])
            self.assertNotIn(registered['id'], excluded.species)
            with self.assertRaises(KeyError):
                build_pokemon(excluded, registered['id'], 40, abilities=[])
            e, a, t = self.world(registered['id'], rules=rules)
            e.gm.set_types(a, ['불꽃'], reason='observed individual type change after custom registration')
            e, a, t = self.restore(e, a, t)
            self.assertEqual(a.types, ['불꽃'])
            _, observed = self.actual_hit(e, a, t)
            self.assertEqual(observed, [('물', 1.0)])

    def test_excluded_move_and_registered_species_reject_before_cost_or_rng(self):
        for excluded in (MOVE, BAILE):
            with self.subTest(excluded=excluded):
                # Own Rules so the profile observation cannot leak into other cases.
                rules = Rules(ROOT, ruleset='core')
                e, a, t = self.world(rules=rules)
                rules.ruleset = RuleFilter({'sources': ['core'], 'variants': [], 'exclude_units': [excluded]})
                rules.selection = RuleSelection(rules.ruleset, list(rules.selection.units.values()))
                before = deepcopy((a.spec, a.budget, a.move_uses, t.spec, t.hp, e.rng.getstate()))
                with self.assertRaises(ValueError):
                    e.use_move(a, t, MOVE, set_damage=True)
                self.assertEqual((a.spec, a.budget, a.move_uses, t.spec, t.hp, e.rng.getstate()), before)
                with self.assertRaises(ValueError):
                    EXT.effective_type(e, a, t, rules.move(MOVE), rules.move_mech(MOVE)[0], consume=False)

    def test_registered_source_preflight_failure_is_atomic_for_world_and_rng(self):
        rules = Rules(ROOT, ruleset='core')
        e, a, t = self.world(rules=rules)
        selected = Rules._selected_rule
        before = e.export_state()
        def unavailable(current, uid, *args, **kwargs):
            if uid == BAILE:
                raise ValueError('registered dancer source unavailable')
            return selected(current, uid, *args, **kwargs)
        with patch.object(Rules, '_selected_rule', new=unavailable):
            with self.assertRaisesRegex(ValueError, 'registered dancer source unavailable'):
                e.use_move(a, t, MOVE, set_damage=True)
        self.assertEqual(e.export_state(), before)

    def test_native_plasma_preserves_non_normal_dance_then_consumes_real_normal_attack(self):
        e, a, t = self.world(target_species='제라오라')
        self.assertIn('move/플라스마피스트', t.moves)
        e.gm.set_temp_hp(a, 1000, reason='observed temporary HP keeps the native setup hit nonlethal')
        # Pound is an actual Lv1 Oricorio Move; GM observes the current known slot.
        self.assertIn({'to': 'move/막치기', 'source': 'level_up', 'level': 1},
            e.r.learnset_links[e.r.species[BAILE]['name']]['moves'])
        e.gm.set_move(a, 'move/에어슬래시', add=False, reason='observed known slot made available')
        e.gm.set_move(a, 'move/막치기', reason='observed retained natural Lv1 Move')
        e.end_of_turn(a)
        e.start_of_turn(t, initiative_count=19)
        with patch.object(Engine, 'd20', return_value=12):
            e.use_move(t, a, 'move/플라스마피스트', situational=100, set_damage=True)
        pending = deepcopy(DECLARATIVE.live(a, 'next_normal_attack_type'),
            {id(actor): actor.entity_id for actor in WORLD.actor_index(e).values()})
        self.assertEqual(len(pending), 1)
        e.end_of_turn(t)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        e, a, t = self.restore(e, a, t)
        self.assertEqual(EXT.effective_type(e, a, t, e.r.move(MOVE), e.r.move_mech(MOVE)[0], consume=False), '불꽃')
        _, observed = self.actual_hit(e, a, t)
        self.assertEqual(observed, [('불꽃', 1.0)])
        self.assertEqual(deepcopy(DECLARATIVE.live(a, 'next_normal_attack_type'),
            {id(actor): actor.entity_id for actor in WORLD.actor_index(e).values()}), pending)
        e.end_of_turn(a)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        with patch.object(Engine, 'd20', return_value=12):
            e.use_move(a, t, 'move/막치기', situational=100, set_damage=True)
        self.assertFalse(DECLARATIVE.live(a, 'next_normal_attack_type'))
        self.assertEqual(HISTORY.records(t)[-1]['move_type'], '전기')
        self.assertTrue(self.restore(e, a, t)[0].validate_state()['valid'])

    def test_explicit_extension_overrides_match_registered_base_and_preserve_all_move_override(self):
        # Synthetic GM extension policies, distinct from the native R129 source witness.
        for selector, expected in (('노말 damaging', '불꽃'), ('all', '전기')):
            with self.subTest(selector=selector):
                e, a, t = self.world()
                e.apply_effect(a, a, {'type': 'type_override_moves', 'target': 'self',
                    'moves': selector, 'as_type': '전기'}, nat=None, hit=True, dealt=0,
                    src='gm/revelation-registered-type-extension')
                _, observed = self.actual_hit(e, a, t)
                self.assertEqual(observed, [(expected, 1.0)])

    def test_miss_and_native_frequency_rejection_keep_normal_move_lifecycle(self):
        e, a, t = self.world()
        self.actual_hit(e, a, t, face=1)
        self.assertTrue(self.restore(e, a, t)[0].validate_state()['valid'])
        e.end_of_turn(a)
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=20)
        before = deepcopy((a.spec, a.budget, a.move_uses, t.hp, e.rng.getstate()))
        self.assertEqual(e.use_move(a, t, MOVE, set_damage=True), 0)
        self.assertEqual((a.spec, a.budget, a.move_uses, t.hp, e.rng.getstate()), before)


if __name__ == '__main__':
    unittest.main()
