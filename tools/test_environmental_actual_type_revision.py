"""Actual native types feed observed collateral effects after their producer ends."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
from grid import Grid
import attack_damage_history as HISTORY
import declarative_move_contracts as DECLARATIVE
import environmental_attacks as ATTACKS
import environmental_item_state as ITEMS
import resolution_transaction as TX
import weather_state as WEATHER
import world_entities as WORLD
import combat_timing as TIMING
import frequency as FREQUENCY
import state_grants as GRANTS
import native_scenario_fixture as SCENARIO
import test_core_nicolette_weather as NICOLETTE


class EnvironmentalActualTypeRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    pokemon = NICOLETTE.NicoletteWeatherTests.pokemon
    fixture = NICOLETTE.NicoletteWeatherTests.fixture
    turn = NICOLETTE.NicoletteWeatherTests.turn
    layer = NICOLETTE.NicoletteWeatherTests.layer

    def world(self, moves, target_moves=('move/몸통박치기',)):
        e = Engine(self.r, seed=49214); e.grid = Grid(20, 20)
        a = Combatant(self.r, build_pokemon(self.r, '이브이', 40, name='actual attacker',
            moves=list(moves), abilities=[], extra={'types': ['노말']}))
        t = Combatant(self.r, build_pokemon(self.r, '이브이', 60, name='actual recipient',
            moves=list(target_moves), abilities=[], side='foe', extra={'types': ['노말']}))
        e.gm.add_combatant(a, pos=(1, 1), side='party', reason='observed actual attacker')
        e.gm.add_combatant(t, pos=(2, 1), side='foe', reason='observed actual recipient')
        e.start_round(e.everyone); e.start_of_turn(a, initiative_count=20)
        return e, a, t

    def hit(self, e, a, t, move, **options):
        with patch.object(Engine, 'd20', return_value=12):
            e.use_move(a, t, move, situational=100, set_damage=True, **options)
        row = HISTORY.records(t)[-1]
        self.assertEqual(row['receipt']['source'], move)
        self.assertEqual(row['attacker_id'], a.entity_id)
        return {k: row[k] for k in ('attacker_id', 'target_id', 'sequence')}

    def object(self, e, holder, uid='camera', rule='item/카메라-키트'):
        WORLD.register_object(e, uid, kind='item_instance', item_rule_id=rule,
            owner_id=holder.entity_id, location={'kind': 'unknown'}, reason='observed physical possession')

    def observe(self, e, holder, uid='camera', **options):
        args = dict(event_id='collateral:' + uid, move_id='move/웨더볼',
                    material='ordinary_electronics', exposed=True,
                    reason='GM observed this actual attack reaching this physical possession')
        args.update(options)
        return e.gm.observe_environmental_attack(holder, uid, **args)

    def test_native_weather_ball_forces_each_current_type_and_history_survives_later_weather(self):
        for weather, actual, material, rule, outcome in (
                ('sunny', '불꽃', 'herb', 'item/힘의가루', 'destroyed'),
                ('rain', '물', 'ordinary_electronics', 'item/카메라-키트', 'electrical_failure'),
                ('hail', '얼음', 'liquid_medicine', 'item/상처약', 'frozen')):
            with self.subTest(weather=weather):
                e, a, t = self.world(['move/웨더볼'])
                e.gm.set_weather(weather, reason='actual scene weather')
                e.gm.set_types(t, [actual], reason='resistant target must not choose a favorable type')
                self.object(e, t, rule=rule)
                reference = self.hit(e, a, t, 'move/웨더볼')
                self.assertEqual(HISTORY.records(t)[-1]['move_type'], actual)
                self.assertEqual(self.r.move('move/웨더볼')['type'], '노말')
                e.gm.set_weather('sandstorm', reason='weather changed after the actual attack')
                row = self.observe(e, t, material=material, native_attack=reference)
                self.assertEqual((row['move_type'], row['outcome']), (actual, outcome))
                before = e.export_state(); snapshot = e.gm.snapshot()
                loaded = Engine.import_state(self.r, json.loads(json.dumps(before, ensure_ascii=False)))
                for world in (e, loaded):
                    holder = WORLD.actor_index(world)[t.entity_id]
                    saved = world.export_state()
                    self.assertEqual(self.observe(world, holder, material=material, native_attack=reference), row)
                    self.assertEqual(world.export_state(), saved)
                e.gm.set_weather('rain', reason='later unrelated weather'); e.gm.restore(snapshot)
                self.assertEqual(self.observe(e, t, material=material, native_attack=reference), row)

    def test_native_electrify_retypes_ranged_water_melee_fire_and_rain_weather_ball(self):
        for move, weather in (('move/물대포', None), ('move/불꽃펀치', None), ('move/웨더볼', 'rain')):
            with self.subTest(move=move):
                e, a, t = self.world([move], ['move/송전'])
                if weather:e.gm.set_weather(weather, reason='actual rain before Electrify')
                self.object(e, t); self.object(e, t, 'herb', 'item/힘의가루')
                e.end_of_turn(a); e.start_of_turn(t, initiative_count=19)
                e.use_move(t, a, 'move/송전')
                self.assertTrue(any(effect.get('type') == 'type_override_moves' for effect in a.registry))
                e.end_of_turn(t); e.start_round(e.everyone); e.start_of_turn(a, initiative_count=20)
                reference = self.hit(e, a, t, move)
                self.assertEqual(HISTORY.records(t)[-1]['move_type'], '전기')
                row = self.observe(e, t, move_id=move, native_attack=reference)
                self.assertEqual((row['move_type'], row['outcome']), ('전기', 'electrical_failure'))
                SCENARIO.assert_rejected_unchanged(e,
                    lambda: self.observe(e, t, 'herb', move_id=move, material='herb', native_attack=reference),
                    reason_pattern='actual attack type does not support')

    def test_electrify_overlaps_restore_and_expire_only_at_each_caster_next_turn_end(self):
        e, a, caster = self.world(['move/물대포'], ['move/송전'])
        provider = Combatant(self.r, build_trainer(self.r, 'actual PP Up provider', 20,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10),
            moves=[], abilities=[], extra={'items': {'item/pp업': 1}}))
        e.gm.set_position(caster, (4, 1), reason='actual three-metre separation for ranged attacks')
        e.gm.add_combatant(provider, pos=(4, 2), side='foe', reason='actual possessed PP Up dose')
        self.object(e, caster, 'charged-camera'); self.object(e, caster, 'restored-camera')

        def live(expected):
            rows = [row for row in TIMING.records(a) if row.get('source') == 'move/송전']
            self.assertEqual({row['grant_source'] for row in rows}, expected)
            self.assertEqual(len(rows), len(expected))
            self.assertTrue(all(row['turn_owner'] is caster for row in rows))
            registered = [row for row in a.registry if row.get('type') == 'type_override_moves']
            self.assertEqual({row[GRANTS.TAG] for row in registered}, expected)
            self.assertEqual(len(registered), len(expected))
            for source in expected:
                self.assertEqual(a.spec[GRANTS.KEY]['sources'][source]['owner_id'], caster.entity_id)
                self.assertIn(source, a.spec[GRANTS.KEY]['effects'])
            return rows

        def next_target_turn():
            e.end_round(); e.start_round(e.everyone); e.start_of_turn(a, initiative_count=20)

        def next_caster_turn():
            e.start_of_turn(provider, initiative_count=19); e.end_of_turn(provider)
            e.start_of_turn(caster, initiative_count=18)

        # Electrify is EOT. An actual paid PP Up dose permits legal overlapping uses.
        self.assertEqual(FREQUENCY.move_frequency(e, 'move/송전', caster), ('every_other_turn', 1))
        e.end_of_turn(a); e.start_of_turn(provider, initiative_count=19)
        self.assertEqual(e.use_item(provider, 'item/pp업', caster, selected_move='move/송전'), (1, 0))
        self.assertEqual(provider.spec['items']['item/pp업'], 0)
        self.assertEqual(provider.budget['standard'], 0)
        self.assertEqual(FREQUENCY.move_frequency(e, 'move/송전', caster), ('at_will', 1))
        e.end_of_turn(provider); e.start_of_turn(caster, initiative_count=18)
        e.use_move(caster, a, 'move/송전')
        rows = [row for row in TIMING.records(a) if row.get('source') == 'move/송전']
        self.assertEqual(len(rows), 1)
        first_row = rows[0]
        first = first_row['grant_source']
        self.assertEqual(first_row['turn_deadline'], caster.custom_conditions['combat_turn_serial'] + 1)
        e.end_of_turn(caster); live({first})

        next_target_turn(); live({first})
        charged_reference = self.hit(e, a, caster, 'move/물대포')
        self.assertEqual(HISTORY.records(caster)[-1]['move_type'], '전기')
        e.end_of_turn(a); live({first})
        next_caster_turn(); live({first})
        e.use_move(caster, a, 'move/송전')
        rows = [row for row in TIMING.records(a) if row.get('source') == 'move/송전']
        self.assertEqual(len(rows), 2)
        sources = {row['grant_source'] for row in rows}
        self.assertEqual(len(sources), 2); self.assertIn(first, sources)
        second = next(iter(sources - {first}))
        self.assertEqual({row['turn_deadline'] for row in rows},
                         {caster.custom_conditions['combat_turn_serial'],
                          caster.custom_conditions['combat_turn_serial'] + 1})
        live({first, second})
        self.assertEqual(caster.move_uses['move/송전'], 2)
        snapshot = e.gm.snapshot('actual-overlapping-electrify')
        e.end_of_turn(caster); live({second})
        self.assertNotIn(first, a.spec[GRANTS.KEY]['sources'])
        self.assertNotIn(first, a.spec[GRANTS.KEY]['effects'])
        e.gm.restore(snapshot); live({first, second})
        self.assertIs(e._active_turn_actor, caster)

        ids = (a.entity_id, caster.entity_id, provider.entity_id)
        e = Engine.import_state(Rules(ROOT, ruleset='core'),
            json.loads(json.dumps(e.export_state(), ensure_ascii=False)))
        a, caster, provider = (WORLD.actor_index(e)[uid] for uid in ids)
        live({first, second}); self.assertIs(e._active_turn_actor, caster)
        e.end_of_turn(caster); live({second})
        self.assertNotIn(first, a.spec[GRANTS.KEY]['sources'])
        self.assertNotIn(first, a.spec[GRANTS.KEY]['effects'])

        next_target_turn(); live({second})
        self.hit(e, a, caster, 'move/물대포')
        self.assertEqual(HISTORY.records(caster)[-1]['move_type'], '전기')
        e.end_of_turn(a); live({second})
        next_caster_turn(); live({second})
        e.end_of_turn(caster); live(set())
        self.assertNotIn(second, a.spec[GRANTS.KEY]['sources'])
        self.assertNotIn(second, a.spec[GRANTS.KEY]['effects'])

        next_target_turn()
        restored_reference = self.hit(e, a, caster, 'move/물대포')
        self.assertEqual(HISTORY.records(caster)[-1]['move_type'], '물')
        old = self.observe(e, caster, 'charged-camera', move_id='move/물대포',
            native_attack=charged_reference)
        new = self.observe(e, caster, 'restored-camera', move_id='move/물대포',
            native_attack=restored_reference)
        self.assertEqual((old['move_type'], new['move_type']), ('전기', '물'))
        self.assertTrue(e.validate_state()['valid'])

    def test_clear_and_sandstorm_weather_ball_cannot_create_water_collateral(self):
        for weather, actual in ((None, '노말'), ('sandstorm', '바위')):
            with self.subTest(weather=weather):
                e, a, t = self.world(['move/웨더볼']); self.object(e, t)
                if weather:e.gm.set_weather(weather, reason='actual sandstorm')
                reference = self.hit(e, a, t, 'move/웨더볼')
                self.assertEqual(HISTORY.records(t)[-1]['move_type'], actual)
                SCENARIO.assert_rejected_unchanged(e,
                    lambda: self.observe(e, t, native_attack=reference),
                    reason_pattern='actual attack type does not support')

    def test_consumed_native_plasma_type_is_retained_and_observation_cannot_consume_it_again(self):
        e, a, t = self.world(['move/몸통박치기'], ['move/플라스마피스트'])
        self.object(e, t)
        e.end_of_turn(a); e.start_of_turn(t, initiative_count=19)
        self.hit(e, t, a, 'move/플라스마피스트')
        self.assertEqual(len(DECLARATIVE.live(a, 'next_normal_attack_type')), 1)
        e.end_of_turn(t); e.start_round(e.everyone); e.start_of_turn(a, initiative_count=20)
        reference = self.hit(e, a, t, 'move/몸통박치기')
        self.assertFalse(DECLARATIVE.live(a, 'next_normal_attack_type'))
        producer_state = deepcopy(a.spec, GRANTS._transition_token_anchors(e))
        first = self.observe(e, t, move_id='move/몸통박치기', native_attack=reference)
        self.assertEqual(first['move_type'], '전기')
        self.assertEqual(a.spec, producer_state)
        self.assertFalse(DECLARATIVE.live(a, 'next_normal_attack_type'))
        replay_state = e.export_state()
        self.assertEqual(self.observe(e, t, move_id='move/몸통박치기', native_attack=reference), first)
        self.assertEqual(a.spec, producer_state)
        self.assertFalse(DECLARATIVE.live(a, 'next_normal_attack_type'))
        self.assertEqual(e.export_state(), replay_state)

    def test_multiple_weather_requires_pre_cost_choice_and_preserves_rudolf_ground_exception(self):
        for ground, selected in ((False, '얼음'), (True, '땅')):
            e, trainer, a, t = self.fixture(ground=ground)
            self.layer(e, trainer, a); self.turn(e, a)
            self.assertEqual(set(WEATHER.effective_weathers(e, a)), {'hail', 'sandstorm'})
            if not ground:
                SCENARIO.assert_rejections_unchanged(e, [
                    lambda: e.use_move(a, t, 'move/웨더볼'),
                    lambda: e.use_move_on(a, t, 'move/웨더볼', e.everyone),
                    lambda: e.use_move(a, t, 'move/웨더볼', weather_ball_type='전기')],
                    reason_pattern=['explicit Weather Ball type before Move cost',
                                    'explicit Weather Ball type before Move cost',
                                    'must match an actual effective weather'])
            with patch.object(Engine, 'd20', return_value=12):
                options = {} if ground else {'weather_ball_type': selected}
                e.use_move_on(a, t, 'move/웨더볼', e.everyone, set_damage=True, **options)
            self.assertEqual(HISTORY.records(t)[-1]['move_type'], selected)
            self.assertTrue(e.validate_state()['valid'])

    def test_missing_or_mismatched_native_context_and_changed_replays_are_atomic(self):
        e, a, t = self.world(['move/물대포'])
        self.object(e, t); reference = self.hit(e, a, t, 'move/물대포')
        wrong_actor = dict(reference, attacker_id=t.entity_id)
        wrong_target = dict(reference, target_id=a.entity_id)
        SCENARIO.assert_rejections_unchanged(e, [
            lambda: self.observe(e, t, move_id='move/물대포'),
            lambda: self.observe(e, t, native_attack=reference),
            lambda: self.observe(e, t, move_id='move/물대포', native_attack=wrong_actor),
            lambda: self.observe(e, t, move_id='move/물대포', native_attack=wrong_target),
            lambda: self.observe(e, t, move_id='move/물대포', native_attack=dict(reference, sequence=999)),
            lambda: self.observe(e, t, move_id='move/물대포', native_attack=reference, actual_type='물')],
            reason_pattern=['explicit GM-observed actual type', 'does not match', 'does not match',
                            'occurrence does not exist', 'occurrence does not exist', 'one actual type evidence source'])
        row = self.observe(e, t, move_id='move/물대포', native_attack=reference, exposed=False)
        self.assertEqual(row['outcome'], 'protected')
        self.assertFalse(ITEMS.active(e._physical_objects['camera']))
        SCENARIO.assert_rejections_unchanged(e, [
            lambda: self.observe(e, t, move_id='move/물대포', native_attack=reference, exposed=True),
            lambda: self.observe(e, t, move_id='move/물대포', actual_type='물', exposed=False),
            lambda: self.observe(e, a, move_id='move/물대포', native_attack=reference, exposed=False)],
            reason_pattern='replay changed')

    def test_targetless_explicit_gm_type_and_legacy_history_do_not_use_catalogue_or_current_weather(self):
        e, a, t = self.world(['move/웨더볼'])
        self.object(e, t)
        row = self.observe(e, t, actual_type='물')
        self.assertEqual(row['type_evidence'], {'kind': 'gm_observation'})
        self.assertFalse(HISTORY.records(t))
        e.gm.set_weather('sunny', reason='unrelated later weather')
        self.assertEqual(self.observe(e, t, actual_type='물'), row)
        # A saved pre-fix observation has no type_evidence; it remains historical.
        self.object(e, t, 'legacy-camera')
        old = self.observe(e, t, 'legacy-camera', move_id='move/물대포', actual_type='물')
        legacy = e._physical_objects['legacy-camera'][ATTACKS.FIELD][old['event_id']]
        legacy.pop('type_evidence'); legacy['sha256'] = TX.request_fingerprint({k:v for k,v in legacy.items() if k!='sha256'})
        saved = e.export_state(); loaded = Engine.import_state(self.r, json.loads(json.dumps(saved, ensure_ascii=False)))
        holder = WORLD.actor_index(loaded)[t.entity_id]
        before = loaded.export_state()
        self.assertEqual(self.observe(loaded, holder, 'legacy-camera', move_id='move/물대포'), legacy)
        self.assertEqual(loaded.export_state(), before)
        SCENARIO.assert_rejected_unchanged(loaded,
            lambda: self.observe(loaded, holder, 'legacy-camera', move_id='move/물대포', actual_type='전기'),
            reason_pattern='replay changed')

    def test_saved_native_type_witness_cannot_be_rebound_even_with_a_new_observation_hash(self):
        e, a, t = self.world(['move/물대포']); self.object(e, t)
        reference = self.hit(e, a, t, 'move/물대포')
        row = self.observe(e, t, move_id='move/물대포', native_attack=reference)
        actual = e._physical_objects['camera'][ATTACKS.FIELD][row['event_id']]
        actual['type_evidence']['occurrence_sha256'] = '0' * 64
        actual['sha256'] = TX.request_fingerprint({k:v for k,v in actual.items() if k!='sha256'})
        self.assertFalse(e.validate_state()['valid'])
        with self.assertRaises(ValueError):e.export_state()


if __name__ == '__main__':
    unittest.main()
