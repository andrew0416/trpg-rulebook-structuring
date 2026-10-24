"""Actual R78 Weapon Union: native allocations, physical item and lifecycle."""
from pathlib import Path
from copy import deepcopy
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer, species_lookup
from grid import Grid
from state_codec import dump_engine, load_engine
from native_scenario_fixture import prepare_body, prepare_object, assert_rejected_unchanged
import csv_item_form_contracts as UNION
import state_grants as G
import capability_actions as CAP
import nature_state as NATURE
import vitamin_moves as VITAMINS
import world_entities as WORLD


class WeaponUnionCrownedSourceRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')
        cls.nature = next(name for name in cls.r.mech('pokemon/natures')['by_name']
                          if (NATURE.describe(cls.r, name)['up_stat'],
                              NATURE.describe(cls.r, name)['down_stat']) == ('atk', 'spa'))

    def scene(self, species='자시안', *, wild=False, configure=True):
        e = Engine(self.r, seed=780941)
        e.grid = Grid(20, 12)
        owner = Combatant(self.r, build_trainer(
            self.r, 'actual union owner', 30, dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 30),
            moves=['move/몸통박치기'], abilities=[], pos=(0, 0),
            items=dict.fromkeys(VITAMINS.STAT_ITEMS, 2)))
        a = Combatant(self.r, build_pokemon(
            self.r, species, 1, name='actual union user', nature=self.nature,
            moves=['struggle'], abilities=[], wild=wild, pos=(3, 3),
            extra={} if wild else {'trainer_id': owner.entity_id}))
        b = Combatant(self.r, build_trainer(
            self.r, 'actual signature target', 30,
            {'hp': 120, 'atk': 10, 'def': 5, 'spa': 10, 'spd': 5, 'spe': 10},
            moves=['move/몸통박치기'], abilities=[], side='opponent', pos=(6, 4)))
        for c in (owner, a, b):
            e.gm.add_combatant(c)
        prepare_body(e, a, size='거대', offsets=[(x, y) for x in range(3) for y in range(3)],
                     reason='observed complete three by three stock legendary footprint')
        prepare_body(e, b, size='중형', offsets=[(0, 0)], reason='observed human signature target')
        zacian = '자시안' in species
        crowned = species_lookup(self.r, '자시안-검왕' if zacian else '자마젠타-방패왕')
        item = 'item/녹슨검' if zacian else 'item/녹슨방패'
        uid = 'actual/rusted-object'
        obj = prepare_object(e, uid, kind='physical_object', owner_id=a.entity_id,
                             location={'kind': 'unknown'},
                             reason='actual user carries this inspected Rusted Sword or Shield')
        obj['csv_form_item_id'] = item
        if configure:
            self.configure(e, a, crowned)
        return e, a, b, owner, uid, crowned

    def configure(self, e, a, crowned, *, wrong_base=False):
        # These are two explicit investments, not a redistribution inferred from totals.
        investment = deepcopy(e.growth_stat_projection(a)['permanent']['investment'])
        hero = species_lookup(self.r, '자시안' if '자시안' in a.spec['species'] else '자마젠타')
        crown_base = deepcopy(crowned['base_stats'])
        if wrong_base:
            crown_base['atk'] += 1
        declarations = {
            '역전의 용사': {'species_base': deepcopy(hero['base_stats']), 'investment': deepcopy(investment)},
            '검왕' if '자시안' in a.spec['species'] else '방패왕': {
                'species_base': crown_base, 'investment': deepcopy(investment)},
        }
        return e.configure_growth_forms(a, declarations, active='역전의 용사', source='pokemon/stat-build')

    def enter(self, e, a, uid):
        return UNION.weapon_union(e, a, uid, minutes=2,
                                  reason='GM observed two minutes actually using the carried Rusted item')

    def test_actual_both_species_and_hero_aliases_gain_stats_types_signature_and_manual_exit(self):
        for species in ('자시안', '자시안-역전의-용사', '자마젠타', '자마젠타-역전의-용사'):
            for wild in (False, True):
                with self.subTest(species=species, wild=wild):
                    e, a, b, owner, uid, crowned = self.scene(species, wild=wild)
                    before = deepcopy((a.stats, a.types, a.spec['form_growth_allocations'], a.hp, a.max_hp))
                    e.gm.set_stage(a, 'atk', 1, reason='actual independent Attack combat stage')
                    power = CAP.power(a)
                    clock = e.elapsed_seconds
                    row = self.enter(e, a, uid)
                    form = '검왕' if '자시안' in species else '방패왕'
                    self.assertEqual((a.form, a.spec['form_allocations']['active']), (form, form))
                    self.assertEqual(a.stats, e.growth_stat_projection(a)['effective_stats'])
                    self.assertEqual(a.spec['stats'], a.spec['form_allocations']['forms'][form])
                    for stat in a.stats:
                        self.assertEqual(a.stats[stat] - before[0][stat],
                                         crowned['base_stats'][stat] - species_lookup(self.r, species)['base_stats'][stat])
                    self.assertEqual(a.types, crowned['types'])
                    self.assertEqual(CAP.power(a), power + 2)
                    self.assertEqual((a.hp, a.max_hp, a.stages['atk']), (before[3], before[4], 1))
                    self.assertEqual((e.elapsed_seconds - clock, row['completed_at'] - row['started_at']), (120, 120))
                    self.assertEqual(a._action_history[-1], 'extended')
                    signature = row['move']
                    self.assertNotIn(signature, a.spec['moves'])
                    self.assertIn(signature, a.moves)
                    self.assertEqual(a.spec['state_grants']['sources'][row['source']]['move_mode'], 'permission')
                    e.start_round(e.everyone)
                    e.start_of_turn(a)
                    hp = b.hp
                    with patch.object(Engine, 'd20', return_value=18):
                        damage = e.use_move(a, b, signature, set_damage=True)
                    self.assertGreater(damage, 0)
                    self.assertEqual(hp - b.hp, damage)
                    self.assertEqual(a.budget['standard'], 0)
                    self.assertEqual(a.move_uses[signature], 1)
                    e.end_of_turn(a)
                    e.end_encounter()
                    self.assertEqual(a.form, form)
                    hp = a.hp
                    exit_clock = e.elapsed_seconds
                    self.assertTrue(UNION.end_weapon_union(
                        e, a, minutes=3, reason='observed three minute voluntary release after the encounter'))
                    self.assertEqual(e.elapsed_seconds - exit_clock, 180)
                    self.assertEqual((a.form, a.stats, a.types, a.hp, a.max_hp),
                                     ('역전의 용사', before[0], before[1], hp, before[4]))
                    self.assertEqual(CAP.power(a), power)
                    self.assertEqual(a.spec['form_growth_allocations'], before[2])
                    self.assertNotIn(signature, a.moves)
                    self.assertNotIn('weapon_union', a.spec[UNION.STATE])
                    self.assertEqual(a.spec[UNION.STATE]['history'][-1]['cause'], 'extended')

    def test_nature_vitamin_and_independent_stat_sources_survive_every_real_switch(self):
        for species in ('자시안', '자마젠타'):
            with self.subTest(species=species):
                e, a, _, owner, uid, crowned = self.scene(species)
                vitamin = next(key for key, stat in VITAMINS.STAT_BY_ITEM.items() if stat == 'atk')
                self.assertEqual(e.use_item(owner, vitamin, a), (1, 0))
                G._source(a, 'actual/independent-stat', 'feature', rule_id='combat/struggle')
                G.stat(a, 'atk', 3, 'actual/independent-stat')
                original = deepcopy((a.stats, a.spec['form_growth_allocations'], a.spec['vitamins'], a.hp))
                for _ in range(2):
                    self.enter(e, a, uid)
                    projected = e.growth_stat_projection(a)
                    self.assertEqual(projected['permanent']['nature_delta']['atk'], 2)
                    self.assertEqual(projected['permanent']['nature_delta']['spa'], -2)
                    self.assertEqual(projected['permanent']['contributions']['vitamins']['atk'], 1)
                    self.assertEqual(a.stats['atk'], projected['permanent']['stats']['atk'] + 3)
                    self.assertEqual(a.spec['form_growth_allocations'], original[1])
                    self.assertEqual(a.hp, original[3])
                    UNION.end_weapon_union(e, a, minutes=1, reason='actual voluntary release interval')
                    self.assertEqual((a.stats, a.spec['form_growth_allocations'], a.spec['vitamins'], a.hp), original)
                self.assertEqual(owner.spec['items'][vitamin], 1)
                self.assertIn('actual/independent-stat', a.spec['state_grants']['sources'])

    def test_stock_capabilities_and_power_project_without_erasing_other_or_future_grants(self):
        for species in ('자시안', '자마젠타'):
            with self.subTest(species=species):
                e, a, _, _, uid, crowned = self.scene(species)
                original = G.effective(a, 'capabilities')
                self.assertIn('페이징', original)
                self.assertIn('투명', original)
                e.gm.set_movement_capabilities(
                    a, dict(a.spec['movement'], power=a.spec['movement']['power'] + 3),
                    basis='current', reason='actual current Power includes an unrelated observed bonus')
                power = CAP.power(a)
                G.grant(a, 'capabilities', '페이징', 'actual/other-phasing', 'feature', rule_id='combat/struggle')
                row = self.enter(e, a, uid)
                caps = G.effective(a, 'capabilities')
                self.assertNotIn('투명', caps)
                self.assertIn('페이징', caps)
                self.assertIn('파동술', caps)
                self.assertEqual(CAP.power(a), power + 2)
                G.grant(a, 'capabilities', '투명', 'actual/later-transparency', 'feature', rule_id='combat/struggle')
                G.grant(a, 'capabilities', '파동술', 'actual/other-aura', 'feature', rule_id='combat/struggle')
                G.grant_moves(a, [row['move']], 'actual/other-signature', 'feature',
                              rule_id='combat/struggle', mode='permission')
                G.type_operation(a, 'add', ['물'], 'actual/later-type')
                self.assertIn('투명', G.effective(a, 'capabilities'))
                before = dump_engine(e)
                for _ in range(3):
                    CAP.power(a)
                    G.effective(a, 'capabilities')
                self.assertEqual(dump_engine(e), before)
                UNION.end_weapon_union(e, a, minutes=1, reason='actual observed release')
                self.assertEqual(CAP.power(a), power)
                self.assertTrue(set(original) <= set(G.effective(a, 'capabilities')))
                self.assertIn('파동술', G.effective(a, 'capabilities'))
                self.assertIn(row['move'], a.moves)
                self.assertEqual(a.types, list(dict.fromkeys(a.spec['types'] + ['물'])))
                self.assertNotIn(row['source'], a.spec['state_grants']['sources'])
                for source in ('actual/other-phasing', 'actual/later-transparency', 'actual/other-aura'):
                    self.assertIn(source, a.spec['state_grants']['sources'])

    def test_active_union_survives_gm_and_json_restore_then_actual_faint_releases_without_action(self):
        for species in ('자시안', '자마젠타'):
            for restoration in ('gm', 'json'):
                with self.subTest(species=species, restoration=restoration):
                    e, a, _, _, uid, crowned = self.scene(species)
                    original = deepcopy((a.stats, a.types, G.effective(a, 'capabilities'), CAP.power(a)))
                    row = self.enter(e, a, uid)
                    identity = a.entity_id
                    if restoration == 'gm':
                        e.gm.snapshot('actual active source-bound Crowned form')
                        UNION.end_weapon_union(e, a, minutes=1, reason='actual release before snapshot restore')
                        e.gm.restore('actual active source-bound Crowned form')
                    else:
                        e = load_engine(self.r, dump_engine(e))
                    a = WORLD.actor_index(e)[identity]
                    self.assertEqual(a.spec[UNION.STATE]['weapon_union'], row)
                    self.assertEqual(a.types, crowned['types'])
                    self.assertIn(row['move'], a.moves)
                    clock = e.elapsed_seconds
                    history = deepcopy(a._action_history)
                    e.gm.set_hp(a, value=0, reason='actual knockout ends the source-granted form')
                    self.assertTrue(a.fainted)
                    self.assertEqual(a.hp, 0)
                    self.assertEqual((a.form, a.stats, a.types, G.effective(a, 'capabilities'), CAP.power(a)),
                                     ('역전의 용사', *original))
                    self.assertNotIn(row['move'], a.moves)
                    self.assertNotIn(row['source'], a.spec['state_grants']['sources'])
                    self.assertEqual((e.elapsed_seconds, a._action_history), (clock, history))
                    self.assertEqual(a.spec[UNION.STATE]['history'][-1]['cause'], 'faint')
                    self.assertNotIn('weapon_union', a.spec[UNION.STATE])

    def test_real_declaration_guards_reject_before_partial_form_time_or_action_payment(self):
        e, a, _, _, uid, crowned = self.scene(configure=False)
        assert_rejected_unchanged(e, lambda: self.enter(e, a, uid), reason_pattern='explicit native Hero and Crowned')
        self.configure(e, a, crowned, wrong_base=True)
        assert_rejected_unchanged(e, lambda: self.enter(e, a, uid), reason_pattern='printed Hero and Crowned')
        e, a, _, _, uid, _ = self.scene()
        for minutes, reason in ((True, 'actual'), (0, 'actual'), (None, 'actual'), (1, '')):
            assert_rejected_unchanged(e, lambda: UNION.weapon_union(e, a, uid, minutes=minutes, reason=reason),
                                      reason_pattern='Extended Action')
        assert_rejected_unchanged(e, lambda: self.enter(e, a, 'missing/rusted-object'), reason_pattern='actual Rusted item')
        with patch.object(G, 'type_operation', side_effect=ValueError('late Crowned type failure')):
            assert_rejected_unchanged(e, lambda: self.enter(e, a, uid), reason_pattern='late Crowned type failure')
        e.apply_status(a, '잠듦')
        assert_rejected_unchanged(e, lambda: self.enter(e, a, uid), reason_pattern='available actual Extended Action')
        e.cure_status(a, '잠듦')
        e.start_round(e.everyone)
        e.start_of_turn(a)
        assert_rejected_unchanged(e, lambda: self.enter(e, a, uid), reason_pattern='available actual Extended Action')
        e.end_of_turn(a)
        e.end_encounter()
        self.enter(e, a, uid)
        assert_rejected_unchanged(e, lambda: self.enter(e, a, uid), reason_pattern='already active')
        e.start_round(e.everyone)
        e.start_of_turn(a)
        assert_rejected_unchanged(e, lambda: UNION.end_weapon_union(e, a, minutes=1, reason='actual attempted exit'),
                                  reason_pattern='available actual Extended Action')


if __name__ == '__main__':
    unittest.main()
