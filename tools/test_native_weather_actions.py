"""Native weather actions through real HB Guide, costs, rolls and restore.

Source-only candidate: these tests have not been executed in this batch.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from native_scenario_fixture import assert_rejected_unchanged
import ability_native_actions as NATIVE
import book_survivalist_fixture as FIX
import frequency as FREQ
import state_grants as GRANTS
import survivalist_class as SC
import test_csv_survivalist_hb as HB
import turn as TURN


class NativeWeatherActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def scene(self, source, *, weather=None, guide=False):
        fixture = HB.SurvivalistHBTests()
        fixture.rules = self.rules
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        world = fixture.world(terrains=('desert',))
        engine, user = world['engine'], world['foe']
        GRANTS.grant(user, 'abilities', source, 'gm/native-weather/' + source, 'gm', rule_id=source)
        GRANTS.reconcile(engine, user)
        if weather:
            engine.gm.set_weather(weather, rounds=None, reason='actual native weather action condition')
        if guide:
            FIX.battle(engine, world['trainer'])
            FIX.audible_order(engine, world['trainer'])
            fixture.guide(engine, world['trainer'])
            FIX.next_turn(engine, world['trainer'], user, count=10)
        else:
            FIX.battle(engine, user)
        return fixture, world

    def low_hp(self, engine, user):
        engine.gm.set_hp(user, user.base_max_hp // 2 - 1, reason='actual independent below-half HP')

    def valid(self, engine):
        result = engine.validate_state()
        self.assertTrue(result['valid'], result)

    def test_hydration_rain_exempts_only_frequency_and_guide_keeps_paid_cure(self):
        source = 'ability/촉촉바디-playtest'
        for guided in (False, True):
            with self.subTest(guided=guided):
                f, w = self.scene(source, weather='rain', guide=guided)
                e, a = w['engine'], w['foe']
                e.apply_status(a, '독', source='move/독가루', applied_by=w['partner'])
                ap = deepcopy(a.spec.get('action_points'))
                result = e.activate_ability(a, source, (a, {'status':'독'}))
                self.assertNotIn('독', a.conditions)
                self.assertEqual(a.budget['swift'], 0)
                self.assertEqual(a.spec.get('action_points'), ap)
                self.assertEqual(result['details']['ignored_scene_frequency'], not guided)
                self.assertEqual(FREQ.state(a)['activations'].get(source, {}).get('used', 0), int(guided))
                self.valid(e)

    def test_hydration_suppressed_exhausted_scene_rejects_without_cost_then_expiry_restores_rain(self):
        source = 'ability/촉촉바디-playtest'
        f, w = self.scene(source, weather='rain', guide=True)
        e, a = w['engine'], w['foe']
        e.apply_status(a, '독', source='move/독가루', applied_by=w['partner'])
        e.activate_ability(a, source, (a, {'status':'독'}))
        e.apply_status(a, '독', source='move/독가루', applied_by=w['partner'])
        assert_rejected_unchanged(e, lambda:e.activate_ability(a, source, (a, {'status':'독'})), reason_pattern='frequency exhausted')
        f.next_round(e, a)
        self.assertFalse(SC.weather_ability_suppressed(e, a, source))
        result = e.activate_ability(a, source, (a, {'status':'독'}))
        self.assertTrue(result['details']['ignored_scene_frequency'])
        self.assertEqual(FREQ.state(a)['activations'][source]['used'], 1)
        self.valid(e)

    def test_all_healers_gate_weather_keep_low_hp_and_spend_daily_swift(self):
        variants = (('ability/아이스바디-playtest','hail'), ('ability/젖은접시-playtest','rain'),
                    ('ability/햇볕-playtest','sunny'), ('ability/햇볕-playtest-2','sunny'))
        for source, weather in variants:
            with self.subTest(source=source):
                f, w = self.scene(source, weather=weather, guide=True)
                e, a = w['engine'], w['foe']
                e.gm.set_hp(a, (a.base_max_hp + 1) // 2, reason='actual half-or-higher HP boundary')
                assert_rejected_unchanged(e, lambda:e.activate_ability(a, source, a), reason_pattern='unsuppressed weather|below half')
                self.low_hp(e, a)
                before = a.hp
                result = e.activate_ability(a, source, a)
                self.assertEqual(a.hp, min(a.max_hp, before + e.tick(a)))
                self.assertEqual((result['details']['healed'], a.budget['swift']), (a.hp - before, 0))
                quota = NATIVE.SUN_BLANKET[0] if source in NATIVE.SUN_BLANKET else source
                self.assertEqual(FREQ.state(a)['activations'][quota]['used'], 1)
                self.assertIn(source, a.abilities)
                self.valid(e)

    def test_healing_daily_five_persists_restore_and_does_not_reset_with_weather(self):
        source = 'ability/젖은접시-playtest'
        f, w = self.scene(source, weather='rain')
        e, a = w['engine'], w['foe']
        for use in range(5):
            if use:
                f.next_round(e, a)
            self.low_hp(e, a)
            e.activate_ability(a, source, a)
        loaded, index = FIX.restore(self.rules, e)
        other = index[a.entity_id]
        loaded.gm.set_weather('sunny', rounds=None, reason='rain ends after fifth actual daily use')
        self.low_hp(loaded, other)
        assert_rejected_unchanged(loaded, lambda:loaded.activate_ability(other, source, other), reason_pattern='frequency exhausted')
        self.assertEqual(FREQ.state(other)['activations'][source]['used'], 5)
        self.valid(loaded)

    def test_sun_blanket_uses_real_initiative_boundary_and_aliases_share_quota(self):
        source = NATIVE.SUN_BLANKET[1]
        f, w = self.scene(source, weather='sunny')
        e, a = w['engine'], w['foe']
        self.low_hp(e, a)
        loaded, index = FIX.restore(self.rules, e)
        other = index[a.entity_id]
        loaded.activate_ability(other, source, other)
        self.assertEqual(FREQ.state(other)['activations'][NATIVE.SUN_BLANKET[0]]['used'], 1)
        assert_rejected_unchanged(loaded, lambda:loaded.activate_ability(other, NATIVE.SUN_BLANKET[0], other), reason_pattern='initiative-gain boundary')
        f.next_round(e, a)
        self.assertTrue(TURN.spend(e, a, 'shift', 'actual intervening action'))
        assert_rejected_unchanged(e, lambda:e.activate_ability(a, source, a), reason_pattern='initiative-gain boundary')
        self.valid(loaded)

    def test_flower_gift_keeps_low_hp_route_and_affects_nearby_enemy_and_ally_once(self):
        source = 'ability/플라워기프트-playtest'
        f, w = self.scene(source, weather='sunny', guide=True)
        e, a = w['engine'], w['foe']
        enemy = Combatant(self.rules, FIX.pokemon_spec(self.rules, None, 'flower-enemy'))
        ally = Combatant(self.rules, FIX.pokemon_spec(self.rules, None, 'flower-ally'))
        e.gm.add_combatant(enemy, pos=(7,2), side='party', reason='actual enemy within two meters')
        e.gm.add_combatant(ally, pos=(8,3), side='wild', reason='actual ally within two meters')
        request = (a, {'stats':['atk','spa']})
        assert_rejected_unchanged(e, lambda:e.activate_ability(a, source, request), reason_pattern='unsuppressed sun|below half')
        self.low_hp(e, a)
        e.activate_ability(a, source, request)
        for stat in ('atk','spa'):
            self.assertEqual((a.stages[stat], enemy.stages[stat], ally.stages[stat]), (2,1,1))
        self.assertEqual(a.budget['swift'], 0)
        self.assertEqual(FREQ.state(a)['activations'][source]['used'], 1)
        self.valid(e)

    def test_solar_power_pays_only_on_actual_damage_roll_and_preserves_nonweather_cost(self):
        source = NATIVE.SOLAR_POWER
        for guided in (False, True):
            with self.subTest(guided=guided):
                f, w = self.scene(source, weather='sunny', guide=guided)
                e, a, target = w['engine'], w['foe'], w['partner']
                e.gm.set_position(a, (4,2), reason='actual adjacent attacking foe')
                hp, swift = a.hp, a.budget['swift']
                e.activate_ability(a, source, (a, {'move_id':'move/몸통박치기'}))
                self.assertEqual((a.hp, a.budget['swift']), (hp, swift))
                e.roll_damage(a, target, self.rules.move('move/몸통박치기'), set_damage=True)
                self.assertEqual((a.hp, a.budget['swift']), (hp, swift))
                self.assertTrue(NATIVE.solar_power_interested(a))
                with patch.object(e, 'd20', return_value=17):
                    e.use_move(a, target, 'move/몸통박치기', set_damage=True)
                receipt = next(r for r in reversed(a.spec[NATIVE.HISTORY]) if r['operation']=='solar_power')
                tick = receipt['details']['tick_cost']
                self.assertEqual((a.hp, a.budget['swift']), (hp - tick, 0))
                self.assertEqual(receipt['details']['bonus'], 5 + tick)
                self.assertEqual(receipt['details']['ignored_scene_frequency'], not guided)
                self.assertEqual(FREQ.state(a)['activations'].get(source, {}).get('used', 0), int(guided))
                self.assertFalse(NATIVE.solar_power_interested(a))
                self.valid(e)

    def test_solar_power_miss_never_pays_and_choice_expires_at_next_turn(self):
        source = NATIVE.SOLAR_POWER
        f, w = self.scene(source, weather='sunny')
        e, a, target = w['engine'], w['foe'], w['partner']
        e.gm.set_position(a, (4,2), reason='actual adjacent attacking foe')
        e.activate_ability(a, source, (a, {'move_id':'move/몸통박치기'}))
        hp = a.hp
        with patch.object(e, 'd20', return_value=1):
            e.use_move(a, target, 'move/몸통박치기', set_damage=True)
        self.assertEqual(a.hp, hp)
        self.assertEqual(a.budget['swift'], 1)
        self.assertNotIn(source, FREQ.state(a)['activations'])
        f.next_round(e, a)
        self.assertFalse(NATIVE.solar_power_interested(a))
        self.valid(e)


    def test_solar_power_bonus_reaches_actual_damage_and_ordinary_scene_limit_is_two(self):
        source = NATIVE.SOLAR_POWER
        f, w = self.scene(source)
        e, a, target = w['engine'], w['foe'], w['partner']
        e.gm.set_position(a, (4,2), reason='actual adjacent attacking foe')
        baseline, index = FIX.restore(self.rules, e)
        with patch.object(baseline, 'd20', return_value=17):
            ordinary = baseline.use_move(index[a.entity_id], index[target.entity_id], 'move/몸통박치기', set_damage=True)
        e.activate_ability(a, source, (a, {'move_id':'move/몸통박치기'}))
        tick = e.tick(a)
        with patch.object(e, 'd20', return_value=17):
            boosted = e.use_move(a, target, 'move/몸통박치기', set_damage=True)
        self.assertGreater(ordinary, 0)
        self.assertEqual(boosted, ordinary + 5 + tick)
        f.next_round(e, a)
        e.gm.set_hp(target, target.max_hp, reason='actual recovery between damage samples')
        e.activate_ability(a, source, (a, {'move_id':'move/몸통박치기'}))
        with patch.object(e, 'd20', return_value=17):
            e.use_move(a, target, 'move/몸통박치기', set_damage=True)
        self.assertEqual(FREQ.state(a)['activations'][source]['used'], 2)
        f.next_round(e, a)
        e.gm.set_hp(target, target.max_hp, reason='actual recovery before quota rejection')
        e.activate_ability(a, source, (a, {'move_id':'move/몸통박치기'}))
        hp = a.hp
        with patch.object(e, 'd20', return_value=17), self.assertRaisesRegex(ValueError, 'frequency exhausted'):
            e.use_move(a, target, 'move/몸통박치기', set_damage=True)
        self.assertEqual(a.hp, hp)
        self.assertEqual(a.budget['swift'], 1)
        self.assertEqual(FREQ.state(a)['activations'][source]['used'], 2)

    def test_solar_power_insufficient_hp_or_swift_never_pays_ability_cost(self):
        source = NATIVE.SOLAR_POWER
        for reason in ('hp', 'swift'):
            with self.subTest(reason=reason):
                f, w = self.scene(source, weather='sunny')
                e, a, target = w['engine'], w['foe'], w['partner']
                e.gm.set_position(a, (4,2), reason='actual adjacent attacking foe')
                if reason == 'hp':
                    e.gm.set_hp(a, 1, reason='insufficient actual tick HP')
                else:
                    self.assertTrue(TURN.spend(e, a, 'swift', 'actual earlier swift'))
                e.activate_ability(a, source, (a, {'move_id':'move/몸통박치기'}))
                hp = a.hp
                with patch.object(e, 'd20', return_value=17), self.assertRaisesRegex(ValueError, 'tick HP cost|action unavailable'):
                    e.use_move(a, target, 'move/몸통박치기', set_damage=True)
                self.assertEqual(a.hp, hp)
                self.assertNotIn(source, FREQ.state(a)['activations'])
                self.assertFalse(any(r['operation']=='solar_power' for r in a.spec[NATIVE.HISTORY]))

    def test_solar_power_combined_double_strike_pays_and_boosts_one_damage_roll(self):
        source=NATIVE.SOLAR_POWER
        f,w=self.scene(source)
        e,a,target=w['engine'],w['foe'],w['partner']
        e.gm.set_position(a,(4,2),reason='actual adjacent Double Strike user')
        e.gm.set_move(a,'move/더블어택',reason='actual learned Double Strike Move')
        baseline,index=FIX.restore(self.rules,e)
        with patch.object(Engine,'d20',return_value=17):
            ordinary=baseline.use_move(index[a.entity_id],index[target.entity_id],'move/더블어택',set_damage=True)
        hp=a.hp;tick=e.tick(a)
        e.activate_ability(a,source,(a,{'move_id':'move/더블어택'}))
        with patch.object(Engine,'d20',return_value=17):
            boosted=e.use_move(a,target,'move/더블어택',set_damage=True)
        self.assertGreater(ordinary,0)
        self.assertEqual(boosted,ordinary+5+tick)
        self.assertEqual(len(a.spec['multi_strike_history'][-1]['rolls']),2)
        paid=[row for row in a.spec[NATIVE.HISTORY] if row['operation']=='solar_power']
        self.assertEqual(len(paid),1)
        self.assertEqual((a.hp,a.budget['swift'],FREQ.state(a)['activations'][source]['used']),(hp-tick,0,1))
        self.assertEqual(a.move_uses['move/더블어택'],1)
        self.assertFalse(NATIVE.solar_power_interested(a))
        FIX.restore(self.rules,e)
        self.valid(e)

    def test_solar_power_cannot_refresh_receipt_after_an_unrelated_action(self):
        source = NATIVE.SOLAR_POWER
        f, w = self.scene(source)
        e, a, target = w['engine'], w['foe'], w['partner']
        e.gm.set_position(a, (4,2), reason='actual adjacent attacker')
        e.activate_ability(a, source, (a, {'move_id':'move/몸통박치기'}))
        hp, swift, shift = a.hp, a.budget['swift'], a.budget['shift']
        pay = NATIVE._pay
        def pay_then_other_action(engine, actor, recipient, selected, row, **options):
            result = pay(engine, actor, recipient, selected, row, **options)
            self.assertTrue(TURN.spend(engine, actor, 'shift', 'unrelated real action'))
            return result
        with patch.object(NATIVE, '_pay', side_effect=pay_then_other_action), \
             patch.object(Engine, 'd20', return_value=17), \
             self.assertRaisesRegex(ValueError, 'append exactly its Swift'):
            e.use_move(a, target, 'move/몸통박치기', set_damage=True)
        self.assertEqual((a.hp, a.budget['swift'], a.budget['shift']), (hp, swift, shift))
        self.assertNotIn(source, FREQ.state(a)['activations'])
        self.assertFalse(any(r['operation']=='solar_power' for r in a.spec[NATIVE.HISTORY]))
        self.assertTrue(NATIVE.solar_power_interested(a))

    def test_solar_power_paid_roll_survives_coordinator_pending_restore_without_repayment(self):
        import test_book_coordinator_full as COORD_FIX
        import coordinator as COORD
        import passive_events as PASSIVE
        case=COORD_FIX.CoordinatorFullTests()
        case.rules=self.rules;case.setUp()
        self.addCleanup(case.doCleanups)
        case.own()
        source=NATIVE.SOLAR_POWER
        GRANTS.grant(case.p,'abilities',source,'gm/solar-coordinator','gm',rule_id=source)
        GRANTS.reconcile(case.e,case.p)
        COORD.arm_damage(case.e,case.t,case.p,decision=lambda row:'waiting for actual player choice')
        case.combat(case.p,count=25)
        e,a,target=case.e,case.p,case.foe
        hp,target_hp=a.hp,target.hp;tick=e.tick(a)
        e.activate_ability(a,source,(a,{'move_id':'move/몸통박치기'}))
        with self.assertRaises(PASSIVE.PassiveEventPending) as paused:
            case.use(a,target,'move/몸통박치기',face=12)
        event_id=paused.exception.event_id
        first=e._passive_events[event_id]['coordinator_damage']['first_damage']
        self.assertEqual((a.hp,target.hp,a.budget['swift']),(hp-tick,target_hp,0))
        self.assertEqual(FREQ.state(a)['activations'][source]['used'],1)
        self.assertEqual(len([row for row in a.spec[NATIVE.HISTORY] if row['operation']=='solar_power']),1)
        case.restore('t','p','foe')
        rng=case.e.rng.getstate()
        COORD.restore_damage_choice(case.e,case.t,decision=lambda row:False)
        self.assertEqual(case.e.rng.getstate(),rng)
        self.assertEqual(case.p.hp,hp-tick)
        self.assertEqual(target_hp-case.foe.hp,first)
        self.assertEqual(case.p.move_uses['move/몸통박치기'],1)
        self.assertEqual(FREQ.state(case.p)['activations'][source]['used'],1)
        self.assertEqual(len([row for row in case.p.spec[NATIVE.HISTORY] if row['operation']=='solar_power']),1)
        self.assertFalse(NATIVE.solar_power_interested(case.p))
        self.assertIsNone(case.e._passive_pending)
        case.restore('t','p','foe')

    def test_sun_blanket_reopens_on_actual_swarm_initiative_continuation(self):
        import test_category2_swarm_transitions as SWARM_FIX
        case=SWARM_FIX.SwarmTransitionTests();case.r=self.rules;case.setUp()
        self.addCleanup(case.doCleanups)
        source=NATIVE.SUN_BLANKET[0]
        GRANTS.grant(case.p,'abilities',source,'gm/sun-blanket-swarm','gm',rule_id=source)
        GRANTS.reconcile(case.e,case.p)
        case.e.gm.set_weather('sunny',rounds=None,reason='actual sun on swarm initiative')
        case.open_turn()
        case.e.gm.set_hp(case.p,case.p.base_max_hp-20,reason='actual prior damage')
        self.assertTrue(case.spend_move(SWARM_FIX.AT_WILL)[0])
        assert_rejected_unchanged(case.e,lambda:case.e.activate_ability(case.p,source,case.p),
                                  reason_pattern='initiative-gain boundary')
        turn=case.p.custom_conditions.get('combat_turn_serial',0)
        case.e.end_of_turn(case.p)
        case.e.start_of_turn(case.p,initiative_count=15)
        self.assertEqual(case.p.custom_conditions.get('combat_turn_serial',0),turn)
        hp=case.p.hp
        result=case.e.activate_ability(case.p,source,case.p)
        self.assertEqual(result['details']['healed'],case.e.tick(case.p))
        self.assertEqual(case.p.hp,hp+case.e.tick(case.p))
        self.assertEqual(FREQ.state(case.p)['activations'][source]['used'],1)
        self.valid(case.e)

if __name__ == '__main__':
    unittest.main()