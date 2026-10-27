"""CSV315–321 reuse Book owners; close missing Basic Fashion/Plate/Stall consumers."""
from copy import deepcopy
import csv
import unittest
from unittest.mock import patch

import test_book_fashionista_acquisition as fixture
from engine import Rules, Engine
import action_points as AP
import condition_recovery as RECOVERY
import effect_lifetimes as LIFETIMES
import fashion_items as FASHION
import fashionista as FA
import held_equipment as HELD
import initiative
import initiative_interrupts as INTERRUPTS
import items as I
import stall_ability as STALL
import turn as TURN
import field_effects as FIELD
import equipment_suppression as SUPPRESSION
import pokemon_party as PARTY
import state_grants as GRANTS


class FashionistaCSVFullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    setUp = fixture.FashionistaAcquisitionTests.setUp
    setup = fixture.FashionistaAcquisitionTests.setup
    add = fixture.FashionistaAcquisitionTests.add
    acquire = fixture.FashionistaAcquisitionTests.acquire
    whole = fixture.FashionistaAcquisitionTests.whole
    rejected = fixture.FashionistaAcquisitionTests.rejected
    valid = fixture.FashionistaAcquisitionTests.valid
    restore = fixture.FashionistaAcquisitionTests.restore
    item = fixture.FashionistaAcquisitionTests.item
    hold = fixture.FashionistaAcquisitionTests.hold
    wear = fixture.FashionistaAcquisitionTests.wear
    combat = fixture.FashionistaAcquisitionTests.combat
    next_turn = fixture.FashionistaAcquisitionTests.next_turn
    craft = fixture.FashionistaAcquisitionTests.craft
    incense = fixture.FashionistaAcquisitionTests.incense
    use = fixture.FashionistaAcquisitionTests.use

    def basic(self, recipe, owner=None, uid='basic:1'):
        result = self.craft('fashionista/basic-fashion-' + recipe, uid=uid, owner=owner or self.p)
        self.assertEqual(result['money_spent'], 500)
        self.assertEqual(result['recipe_source'], FA.CLASS)
        return result['item_id']

    def room(self, name):
        return FIELD.install(self.e, self.q, self.rules.move_mech(name)[0]['effects_exec'][0], name)

    def test_all_seven_csv_rows_reuse_exact_book_template_and_rank_contracts(self):
        with (fixture.ROOT / 'input/db/feats.csv').open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))[314:321]
        expected = (FA.CLASS, FA.MAKEOVER, FA.STYLE, FA.ACCESSORIZE, FA.PARFUMIER, FA.WARDROBE, FA.DRESS)
        self.assertEqual([row[0] for row in rows], [feature.split('/')[-1].replace('-', ' ') for feature in expected])
        self.whole()
        self.assertEqual([row['feature_id'] for row in FA.records(self.t, active=True)], list(expected))
        self.assertEqual(FA.chosen_skills(self.t), ['매력', '직감'])
        self.assertEqual((FA.DEFINITIONS[FA.ACCESSORIZE]['skill_requirement'], FA.DEFINITIONS[FA.PARFUMIER]['skill_requirement']),
                         ({'rank':4, 'count':1}, {'rank':5, 'count':1}))
        self.assertEqual((FA.DEFINITIONS[FA.WARDROBE]['skill_requirement'], FA.DEFINITIONS[FA.DRESS]['skill_requirement']),
                         ({'rank':4, 'count':2}, {'rank':5, 'count':2}))
        self.valid()

    def test_basic_recipe_skill_choices_gate_all_five_book_outputs_without_enabling_homebrew(self):
        self.acquire()
        expected = {'fashionista/basic-fashion-charm':'item/귀여운-패션',
                    'fashionista/basic-fashion-intuition':'item/우아한-패션'}
        actual = {row['id']:row['output']['item_id'] for row in FA.RECIPES
                  if row.get('fashionista_skill') and FA.qualifies(self.e, self.t, row['id'])}
        self.assertEqual(actual, expected)
        self.rejected(lambda:self.basic('command'), 'requirements are not met')
        for item_id in FASHION.ITEM_IDS:
            with self.assertRaises(ValueError):
                self.rules.item_effects(item_id)
        for recipe, item_id in expected.items():
            self.assertEqual(self.craft(recipe)['item_id'], item_id)
        self.assertEqual(self.t.spec['money'], 19000)
        self.valid()

    def test_book_adorable_crafted_for_another_owner_has_no_maker_or_contest_extra_contract(self):
        inventory_effects = deepcopy(self.rules.item_effects('item/귀여운-패션')[0])
        self.acquire()
        item = self.basic('charm', owner=self.q)
        self.basic('charm', owner=self.q, uid='second-book-cute')
        I.equip_held(self.e, self.q, item, source_instance_id='basic:1')
        self.combat(self.q)
        self.e.activate_fashion_item(self.q, item)
        self.assertEqual(LIFETIMES.numeric(self.q, 'evasion_modifier'), 2)
        self.assertEqual(self.q.evasion_mod, 0)  # registration alone did not install the activation
        self.rejected(lambda:self.e.activate_fashion_item(self.q, item), 'already activated')
        I.unregister_item(self.e, self.q, registration_key=HELD.entries(self.q)[0]['registration_key'])
        I.equip_held(self.e, self.q, item, source_instance_id='second-book-cute')
        self.rejected(lambda:self.e.activate_fashion_item(self.q, item), 'scene activation is exhausted')
        I.unregister_item(self.e, self.q, registration_key=HELD.entries(self.q)[0]['registration_key'])
        I.equip_held(self.e, self.q, item, source_instance_id='basic:1')
        with self.assertRaisesRegex(ValueError, 'matching equipped Fashion contest stat'):
            FASHION.contest_plan(self.e, self.q, '귀여움', set())
        self.assertEqual(self.rules.item_effects(item)[0], inventory_effects)  # no global inventory override
        self.restore()
        self.valid()
        self.assertEqual(LIFETIMES.numeric(self.q, 'evasion_modifier'), 2)
        self.e.end_of_turn(self.q)
        self.e.end_round()
        self.combat(self.q)
        self.assertEqual(LIFETIMES.numeric(self.q, 'evasion_modifier'), 0)

    def test_book_elegant_enemy_stage_loss_reaction_is_free_scene_once_without_maker_restriction(self):
        self.acquire()
        item = self.basic('intuition', owner=self.q)
        I.equip_held(self.e, self.q, item, source_instance_id='basic:1')
        self.combat(self.q)
        self.e.arm_fashion_reaction(self.q, item)
        effect = {'type':'stage_change', 'stat':'atk', 'delta':-1, 'on':'target'}
        self.e.apply_effect(self.p, self.q, effect, 2, True, 0, 'move/울음소리')
        self.assertEqual(self.q.stages['atk'], 0)
        self.e.apply_effect(self.p, self.q, effect, 2, True, 0, 'move/울음소리')
        self.assertEqual(self.q.stages['atk'], -1)
        self.assertEqual(self.q._action_history.count('free'), 1)
        self.valid()

    def test_book_rad_has_no_passive_save_bonus_and_consumes_native_next_save_once(self):
        self.setup(choices=('명령', '직감'))
        self.acquire()
        item = self.basic('command', owner=self.q)
        I.equip_held(self.e, self.q, item, source_instance_id='basic:1')
        self.assertEqual(self.q.save_mod, 0)
        self.combat(self.q)
        self.e.activate_fashion_item(self.q, item)
        self.restore()
        first = RECOVERY.saving_check(self.e, self.q, None, 8, fixed=5)
        second = RECOVERY.saving_check(self.e, self.q, None, 8, fixed=5)
        self.assertEqual((first['fashion_bonus'], first['passed'], second['fashion_bonus'], second['passed']), (4, True, 0, False))
        self.valid()

    def test_book_rough_uses_trainer_accessory_and_native_enemy_roll_penalty(self):
        self.setup(choices=('협박', '직감'))
        self.acquire()
        item = self.basic('intimidate', owner=self.t)
        I.register_item(self.e, self.t, item, source_instance_id='basic:1')
        self.assertEqual(self.t._item_reg[item]['slots'], ['장신구'])
        self.combat(self.t)
        count = self.e._prepare_skill_roll(self.q, '육상')[5]['dice_count']
        before = self.e.skill_roll(self.q, '육상', fixed=[3] * count)
        self.rejected(lambda:self.e.activate_fashion_item(self.t, item, target=self.p), 'enemy')
        self.e.activate_fashion_item(self.t, item, target=self.q)
        self.assertEqual(self.e.skill_roll(self.q, '육상', fixed=[3] * count).total, before.total - 2)
        self.valid()

    def test_book_slick_prevents_only_one_actual_opportunity_trigger(self):
        self.setup(choices=('교활', '직감'))
        self.acquire()
        item = self.basic('guile', owner=self.q)
        I.equip_held(self.e, self.q, item, source_instance_id='basic:1')
        self.combat(self.q)
        self.e.arm_fashion_reaction(self.q, item)
        TURN.trigger_aoo(self.e, self.q, 'leave adjacency', [self.p])
        self.assertFalse(self.p.aoo_used)
        TURN.trigger_aoo(self.e, self.q, 'leave adjacency again', [self.p])
        self.assertTrue(self.p.aoo_used)
        self.valid()

    def test_dashing_makeover_projects_basic_fashion_without_fabricating_a_physical_item(self):
        self.whole()
        ap = AP.available(self.t)
        before = set(getattr(self.e, '_physical_objects', {}))
        FA.makeover(self.e, self.t, self.q, 'item/귀여운-패션', recipe_id='fashionista/basic-fashion-charm',
                    seconds=600, reason='actual Basic Fashion projection')
        self.assertEqual(set(getattr(self.e, '_physical_objects', {})), before)
        self.assertEqual(HELD.entries(self.q), [])
        self.assertEqual(AP.available(self.t), ap - 2)
        self.combat(self.q)
        self.e.activate_fashion_item(self.q, 'item/귀여운-패션')
        self.assertEqual(LIFETIMES.numeric(self.q, 'evasion_modifier'), 2)
        self.restore()
        self.valid()
        self.next_turn(self.t)
        FA.end_makeover(self.e, self.t, self.q, event_id='release-basic')
        self.assertEqual(FASHION._active(self.e, self.q), [])
        self.assertEqual(AP.available(self.t), ap)
        self.valid()

    def test_dress_to_impress_activates_stored_basic_fashion_and_expires_native_sources(self):
        self.whole()
        FA.make_chic(self.e, self.t, self.p, seconds=600, reason='actual Chic model')
        self.basic('charm', uid='cute')
        self.basic('intuition', uid='elegant')
        FA.store(self.e, self.p, 'cute', 'wardrobe:1', reason='actual carried Fashion')
        FA.store(self.e, self.p, 'elegant', 'wardrobe:2', reason='actual carried Fashion')
        self.assertEqual(FASHION._active(self.e, self.p), [])
        self.combat(self.t)
        FA.dress_to_impress(self.e, self.t, self.p)
        self.e.end_of_turn(self.t)
        self.e.start_of_turn(self.p, initiative_count=25)
        self.e.activate_fashion_item(self.p, 'item/귀여운-패션')
        self.e.arm_fashion_reaction(self.p, 'item/우아한-패션')
        self.e.apply_effect(self.q, self.p, {'type':'stage_change','stat':'atk','delta':-1,'on':'target'}, 2, True, 0, 'move/울음소리')
        self.assertEqual(self.p.stages['atk'], 0)
        self.assertEqual(LIFETIMES.numeric(self.p, 'evasion_modifier'), 2)
        self.restore()
        self.valid()
        self.next_turn(self.p)
        self.assertEqual(FASHION._active(self.e, self.p), [])
        self.assertEqual(len(FA.wardrobe_items(self.e, self.p)), 2)
        self.valid()

    def test_accessorize_rejects_the_printed_fire_brace_plate_pair_and_allows_unshared_parts(self):
        self.whole()
        self.wear(self.t, 'brace', 'item/불꽃깁스')
        self.assertTrue(FA.shares_effects(self.e, 'item/불꽃깁스', 'item/불구슬플레이트'))
        self.assertEqual(self.wear(self.t, 'plate', 'item/불구슬플레이트'), 0)
        self.assertEqual(self.wear(self.t, 'booster', 'item/불꽃부스터'), 1)
        I.unregister_item(self.e, self.t, registration_key='item/불꽃깁스')
        I.unregister_item(self.e, self.t, registration_key='item/불꽃부스터')
        self.assertEqual(I.register_item(self.e, self.t, 'item/불구슬플레이트', source_instance_id='plate'), 2)
        self.assertEqual(I.item_damage_reduction(self.t, self.rules.move('move/화염방사'), engine=self.e), 15)
        self.assertEqual(self.wear(self.t, 'ice', 'item/얼음깁스'), 1)
        self.restore()
        self.valid()

    def test_all_three_actual_crafted_incenses_grant_parfumier_move_with_full_incense_native_stall(self):
        self.acquire()
        self.acquire(FA.PARFUMIER)
        for n, (recipe, item_id, cost) in enumerate((('lax','item/무사태평향로',1000), ('luck','item/행운의향로',900), ('full','item/만복향로',450))):
            with self.subTest(recipe=recipe):
                identity = 'incense:' + recipe
                result = self.craft('fashionista/incense-' + recipe, uid=identity, owner=self.p, incense_move='아로마미스트')
                self.assertEqual(result['money_spent'], cost)
                I.equip_held(self.e, self.p, item_id, source_instance_id=identity)
                self.assertIn('move/아로마미스트', self.p.moves)
                self.assertEqual(STALL.active(self.p), recipe == 'full')
                self.assertEqual(self.e.gm_prompts, [])
                self.restore()
                self.valid()
                I.unregister_item(self.e, self.p, registration_key=HELD.entries(self.p)[0]['registration_key'])
                self.assertNotIn('move/아로마미스트', self.p.moves)
                self.assertFalse(STALL.active(self.p))
        self.valid()

    def test_stall_native_order_own_count_interrupt_protection_and_item_loss(self):
        self.hold(self.p, 'full', 'item/만복향로')
        self.assertEqual(initiative.order(self.e, [self.p, self.q, self.t]), [self.t, self.q, self.p])
        self.e.prepare_initiative_schedule([self.p, self.q, self.t], source='combat/initiative')
        self.e.start_round([self.p, self.q, self.t])
        for actor in (self.t, self.q):
            self.e.start_of_turn(actor)
            self.e.end_of_turn(actor)
        self.e.start_of_turn(self.p)
        trigger = dict(kind='turn', actor_id=self.p.entity_id, serial=self.p.custom_conditions['combat_turn_serial'], round=self.e.round_no)
        request = dict(id='interrupt', actor_id=self.q.entity_id, source='combat/initiative', priority=0,
                       mode='reaction', payment='next', budget={'standard':1}, clock='none')
        self.rejected(lambda:self.e.queue_initiative_reactions([request], trigger=trigger), 'cannot be Interrupted')
        self.assertFalse(STALL.protected(self.e, self.q))
        self.restore()
        self.valid()
        I.unregister_item(self.e, self.p, registration_key=HELD.entries(self.p)[0]['registration_key'])
        self.assertFalse(STALL.active(self.p))
        self.assertEqual(self.e.queue_initiative_reactions([request], trigger=trigger)['status'], 'queued')

    def test_focus_band_real_damage_failure_then_success_scene_quota_and_cold_restore(self):
        self.whole()
        self.craft('fashionista/focused-focus-band', uid='band', owner=self.p)
        I.equip_held(self.e, self.p, 'item/기합의머리띠', source_instance_id='band')
        maximum = self.p.base_max_hp
        with patch.object(Engine, 'd20', return_value=15) as rolled:
            self.e.take_damage(self.p, maximum)
        rolled.assert_called_once()
        self.assertTrue(self.p.fainted)
        self.assertNotIn('focus:item/기합의머리띠', self.p.spec['frequency_state']['activations'])
        self.e.gm.revive(self.p, hp=maximum, reason='actual observed explicit revival')
        with patch.object(Engine, 'd20', return_value=16) as rolled:
            self.e.take_damage(self.p, maximum)
        rolled.assert_called_once()
        self.assertEqual(self.p.hp, 1)
        self.assertFalse(self.p.fainted)
        self.assertGreater(self.p.injuries, 0)  # Massive Damage still has its own native owner.
        self.restore()
        with patch.object(Engine, 'd20') as rolled:
            self.e.take_damage(self.p, 1)
        rolled.assert_not_called()
        self.assertTrue(self.p.fainted)
        self.valid()

    def test_focus_band_nonattack_loss_and_late_error_roll_back_rng_hp_and_scene_use(self):
        self.hold(self.p, 'band', 'item/기합의머리띠')
        maximum = self.p.base_max_hp
        before = self.e.export_state()
        with patch.object(Engine, 'check_fainted', side_effect=ValueError('late life validation')):
            with self.assertRaisesRegex(ValueError, 'late life validation'):
                self.e.lose_hp(self.p, maximum, source='actual passive damage')
        self.assertEqual(self.e.export_state(), before)
        with patch.object(Engine, 'd20', return_value=20):
            self.e.lose_hp(self.p, maximum, source='actual passive damage')
        self.assertEqual(self.p.hp, 1)
        self.assertFalse(self.p.fainted)
        self.valid()

    def test_focus_sash_requires_actual_full_hp_native_move_not_an_isolated_damage_label(self):
        self.u = self.add('full native sash holder', 'pokemon', (4, 2), trainer_id=self.t.entity_id,
                          stats=dict(self.common['stats'], hp=1), moves=['move/몸통박치기'])
        self.v = self.add('actual strong attacker', 'pokemon', (5, 2), side='foe',
                          stats=dict(self.common['stats'], atk=200), moves=['move/메가톤펀치'])
        self.hold(self.u, 'sash', 'item/기합의띠')
        self.combat(self.v)
        with patch.object(Engine, 'd20', return_value=18):
            self.e.use_move_on(self.v, self.u, 'move/메가톤펀치', self.e.everyone, set_damage=True)
        self.assertEqual(self.u.hp, 1)
        self.assertFalse(self.u.fainted)
        self.assertGreater(self.u.injuries, 0)
        self.restore()
        self.e.take_damage(self.u, 1)
        self.assertTrue(self.u.fainted)
        self.hold(self.p, 'isolated-sash', 'item/기합의띠')
        self.e.take_damage(self.p, self.p.base_max_hp)
        self.assertTrue(self.p.fainted)
        self.valid()

    def test_makeover_focus_band_has_no_physical_body_and_revokes_at_bound_ap_end(self):
        self.whole()
        FA.makeover(self.e, self.t, self.q, 'item/기합의머리띠', recipe_id='fashionista/focused-focus-band', seconds=600, reason='actual projected Focus Band')
        self.assertNotIn('band', self.e._physical_objects)
        self.restore()
        with patch.object(Engine, 'd20', return_value=16):
            self.e.take_damage(self.q, self.q.base_max_hp)
        self.assertEqual(self.q.hp, 1)
        FA.end_makeover(self.e, self.t, self.q, event_id='end:focus')
        with patch.object(Engine, 'd20') as rolled:
            self.e.take_damage(self.q, 1)
        rolled.assert_not_called()
        self.assertTrue(self.q.fainted)
        self.valid()

    def test_contest_fashion_real_crafted_stat_native_reroll_and_cold_receipt(self):
        from contest import ContestEngine, ContestRules
        import state_codec as CODEC
        self.acquire()
        self.rejected(lambda:self.craft('fashionista/contest-fashion', uid='untyped', owner=self.p), 'assign the crafted')
        result = self.craft('fashionista/contest-fashion', uid='contest-fashion', owner=self.p, contest_stat='귀여움')
        self.assertEqual(result['money_spent'], 500)
        self.e.gm.set_move(self.p, 'move/벌레의야단법석', reason='actual learned contest Move')
        I.equip_held(self.e, self.p, 'item/콘테스트-옷', source_instance_id='contest-fashion')
        contest_rules = ContestRules(fixture.ROOT, ruleset='core')
        contest = ContestEngine(contest_rules, seed=7)
        stats = {stat:0 for stat in FASHION.CONTEST_STATS}
        contestant = contest.contestant_from_combatants(self.e, self.p, self.t, '매력', stat_dice=stats)
        contest.perform(contestant, 'move/벌레의야단법석', '귀여움', [], False, fixed_rolls=[1,2,3,4],
                        fashion_decision=lambda preview:preview['ones'] == 1, attempt_id='fashion:1')
        self.assertEqual(len(contest._fashion_used), 1)
        loaded, participants = CODEC.load_contest(contest_rules, CODEC.dump_contest(contest, [contestant]), native_rules=self.rules)
        self.assertEqual(loaded._fashion_used, contest._fashion_used)
        native, pokemon, *_ = next(iter(loaded._native_intro_bindings.values()))
        with self.assertRaisesRegex(ValueError, 'already used'):
            FASHION.contest_plan(native, pokemon, '귀여움', loaded._fashion_used)
        self.valid()

    def test_actual_contest_accessory_and_fancy_clothes_use_existing_introduction_consumer(self):
        from contest import ContestEngine, ContestRules
        self.acquire()
        self.craft('fashionista/contest-accessory', uid='accessory', owner=self.p)
        self.craft('fashionista/fancy-clothes', uid='clothes', owner=self.t, contest_stat='아름다움')
        I.equip_held(self.e, self.p, 'item/콘테스트-장신구', source_instance_id='accessory')
        I.register_item(self.e, self.t, 'item/멋진-옷', source_instance_id='clothes')
        contest = ContestEngine(ContestRules(fixture.ROOT, ruleset='core'), seed=5)
        contestant = contest.contestant_from_combatants(self.e, self.p, self.t, '매력',
            stat_dice={stat:0 for stat in FASHION.CONTEST_STATS},
            bonus_stats={'item/콘테스트-장신구':'귀여움', 'item/멋진-옷':'아름다움'})
        self.assertEqual(len(contestant.intro_bonuses), 2)
        contest.intro_stage([contestant], '귀여움')
        self.assertTrue(contestant.intro_completed)
        self.assertTrue(any('2d6' in line for line in contest.log_lines))
        self.restore()
        with self.assertRaisesRegex(ValueError, 'assigned stat'):
            contest.contestant_from_combatants(self.e, self.p, self.t, '매력',
                stat_dice={stat:0 for stat in FASHION.CONTEST_STATS},
                bonus_stats={'item/콘테스트-장신구':'귀여움', 'item/멋진-옷':'강인함'})
        self.valid()

    def test_incense_actual_pokemon_transfer_back_and_capture_reconcile_current_maker_owner(self):
        self.acquire()
        self.acquire(FA.PARFUMIER)
        self.incense(owner=self.p, move='아로마미스트')
        I.equip_held(self.e, self.p, 'item/무사태평향로', source_instance_id='incense:1')
        self.u = self.add('actual receiving trainer', 'trainer', (8, 2), classes=[], feats=[])
        PARTY.configure(self.e, self.t, mode='unlimited', reason='actual complete maker roster', roster=[self.p])
        PARTY.configure(self.e, self.u, mode='unlimited', reason='actual complete destination roster', roster=[])
        PARTY.transfer(self.e, self.t, target=self.p, new_owner=self.u, reason='actual observed ownership transfer', request_id='give:model')
        self.assertNotIn('move/아로마미스트', self.p.moves)
        PARTY.transfer(self.e, self.u, target=self.p, new_owner=self.t, reason='actual return to original maker', request_id='return:model')
        self.assertIn('move/아로마미스트', self.p.moves)
        self.restore()
        self.incense(uid='wild-incense', owner=self.q, move='아로마미스트')
        I.equip_held(self.e, self.q, 'item/무사태평향로', source_instance_id='wild-incense')
        self.assertNotIn('move/아로마미스트', self.q.moves)
        self.q.spec['wild'] = True
        self.t.spec.setdefault('items', {})['몬스터볼'] = 1
        self.assertTrue(self.e.throw_ball(self.t, self.q, fixed_accuracy=20, fixed_capture=20))
        self.assertEqual(self.q.spec['trainer_id'], self.t.entity_id)
        self.assertIn('move/아로마미스트', self.q.moves)
        self.restore()
        self.valid()

    def test_stall_holder_may_interrupt_and_its_interrupt_does_not_gain_own_count_protection(self):
        self.hold(self.p, 'full', 'item/만복향로')
        self.e.prepare_initiative_schedule(self.e.everyone, source='combat/initiative')
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.t)
        request = dict(id='stall-react', actor_id=self.p.entity_id, source='combat/initiative', priority=0,
                       mode='reaction', payment='next', budget={'standard':1}, clock='none')
        trigger = dict(kind='turn', actor_id=self.t.entity_id, serial=self.t.custom_conditions['combat_turn_serial'], round=self.e.round_no)
        queued = self.e.queue_initiative_reactions([request], trigger=trigger)
        self.e.begin_initiative_reaction(queued['window_id'], 'stall-react')
        self.assertTrue(TURN.spend(self.e, self.p, 'standard'))
        self.assertFalse(STALL.protected(self.e, self.p))
        nested = dict(request, id='interrupt-stall-interrupt', actor_id=self.q.entity_id)
        inner = self.e.queue_initiative_reactions([nested], trigger={'kind':'reaction','window_id':queued['window_id'],'request_id':'stall-react'})
        self.e.begin_initiative_reaction(inner['window_id'], nested['id'])
        self.assertTrue(TURN.spend(self.e, self.q, 'standard'))
        self.e.finish_initiative_reaction()
        self.e.finish_initiative_reaction()
        self.assertIs(self.e._active_turn_actor, self.t)
        self.restore()
        self.valid()

    def test_stall_actual_ability_suppression_restores_order_and_full_incense_refuses_trainer(self):
        import effects as FX
        self.hold(self.p, 'full', 'item/만복향로')
        self.assertEqual(initiative.order(self.e, self.e.everyone)[-1], self.p)
        GRANTS.transition(self.e, self.p, lambda e,c:FX.h_suppress_ability(e,c,c,{},{}))
        self.assertFalse(STALL.active(self.p))
        self.assertEqual(initiative.order(self.e, self.e.everyone), [self.p, self.t, self.q])
        self.assertEqual(self.wear(self.t, 'trainer-full', 'item/만복향로'), 0)
        self.assertNotIn(STALL.NAME, self.t.abilities)
        self.restore()
        self.valid()

    def test_focus_band_same_actor_cannot_reset_rule_quota_by_re_equipping_or_swapping_instances(self):
        self.hold(self.p, 'first-band', 'item/기합의머리띠')
        self.e.gm.set_hp(self.p, value=1, reason='actual positive HP before loss')
        with patch.object(Engine, 'd20', return_value=16):
            self.e.lose_hp(self.p, 1)
        I.unregister_item(self.e, self.p, registration_key=HELD.entries(self.p)[0]['registration_key'])
        I.equip_held(self.e, self.p, 'item/기합의머리띠', source_instance_id='first-band')
        with patch.object(Engine, 'd20') as rolled:
            self.e.lose_hp(self.p, 1)
        rolled.assert_not_called()
        self.e.gm.revive(self.p, hp=1, reason='actual revival for different item observation')
        I.unregister_item(self.e, self.p, registration_key=HELD.entries(self.p)[0]['registration_key'])
        self.hold(self.p, 'second-band', 'item/기합의머리띠')
        self.restore()
        with patch.object(Engine, 'd20') as rolled:
            self.e.lose_hp(self.p, 1)
        rolled.assert_not_called()
        self.assertTrue(self.p.fainted)
        self.hold(self.q, 'other-actor-band', 'item/기합의머리띠')
        self.e.gm.set_hp(self.q, value=1, reason='different actual holder')
        with patch.object(Engine, 'd20', return_value=16) as rolled:
            self.e.lose_hp(self.q, 1)
        rolled.assert_called_once()
        self.assertFalse(self.q.fainted)
        self.valid()

    def test_focus_band_and_sash_have_separate_rule_quotas_and_sash_requires_true_full_hp(self):
        self.u = self.add('separate quota holder', 'pokemon', (4, 2), trainer_id=self.t.entity_id,
                          stats=dict(self.common['stats'], hp=1), moves=['move/몸통박치기'])
        self.v = self.add('actual quota attacker', 'pokemon', (5, 2), side='foe',
                          stats=dict(self.common['stats'], atk=200), moves=['move/메가톤펀치'])
        self.hold(self.u, 'quota-band', 'item/기합의머리띠')
        with patch.object(Engine, 'd20', return_value=16):
            self.e.lose_hp(self.u, self.u.base_max_hp)
        I.unregister_item(self.e, self.u, registration_key=HELD.entries(self.u)[0]['registration_key'])
        self.hold(self.u, 'quota-sash', 'item/기합의띠')
        self.e.gm.set_hp(self.u, value=self.u.base_max_hp, reason='observed true full HP')
        self.combat(self.v)
        self.use(self.v, self.u, 'move/메가톤펀치', face=18)
        self.assertEqual(self.u.hp, 1)
        self.assertFalse(self.u.fainted)
        quota_keys = ('focus:item/기합의머리띠', 'focus:item/기합의띠')
        quota = {key:deepcopy(self.u.spec['frequency_state']['activations'][key]) for key in quota_keys}
        self.assertEqual([quota[key]['used'] for key in quota_keys], [1, 1])
        self.restore()
        self.e.gm.set_injuries(self.u, value=0, reason='observed actual recovered injuries')
        self.e.gm.set_hp(self.u, value=self.u.base_max_hp, reason='observed true full HP after recovery')
        I.unregister_item(self.e, self.u, registration_key=HELD.entries(self.u)[0]['registration_key'])
        self.hold(self.u, 'second-sash', 'item/기합의띠')
        self.next_turn(self.v)
        # A full-HP native knockout also reaches the existing five-injury
        # adjudication boundary. Retain its original hit; do not invent/resume
        # the unresolved Heavy consequences to test the exhausted Sash quota.
        import heavy_injury_adapter as HEAVY
        with self.assertRaises(HEAVY.HeavyPending) as pending:
            self.use(self.v, self.u, 'move/메가톤펀치', face=18)
        self.assertTrue(self.u.fainted)
        self.assertEqual({key:self.u.spec['frequency_state']['activations'][key] for key in quota_keys}, quota)
        self.assertEqual(HELD.entries(self.u)[0]['instance_id'], 'second-sash')
        HEAVY.acknowledge_ruling(self.e, pending.exception.event_id, self.u,
            expected_current_state=HEAVY.observe(self.u), ruling='GM retains the observed native hit and faint; additional Heavy consequences are externally adjudicated',
            disposition=HEAVY.ContinuationDisposition.CANCELLED_BY_RULING,
            continuation_reason='GM cancels the abandoned Move remainder; no automatic resumption or Heavy source-conformance claim')
        self.valid()

    def test_focus_band_as_one_partner_only_is_in_the_same_atomic_hp_transaction(self):
        from builder import build_pokemon
        from engine import Combatant
        import csv_item_form_contracts as FORMS
        def member(species, **extra):
            actor = Combatant(self.rules, build_pokemon(self.rules, species, 20, extra=extra, moves=[],
                abilities=['흑의울음'] if species == '레이스포스' else []))
            self.e.gm.add_combatant(actor, pos=(6,3), side='party', reason='actual As One participant')
            return actor
        self.u = member('버드렉스', capabilities=['혼연일체'])
        self.v = member('레이스포스', capabilities=['탑승 2'])
        self.hold(self.v, 'mount-band', 'item/기합의머리띠')
        FORMS.mount_as_one(self.e, self.u, self.v, ability='흑의울음')
        for actor in (self.u, self.v):
            self.e.gm.set_hp(actor, value=1, reason='actual positive linked HP')
        self.assertTrue(FASHION.focus_interested(self.e, self.u))
        before = self.e.export_state()
        replace = FASHION.replace_hp
        def late_failure(engine, actor, *args, **kwargs):
            result = replace(engine, actor, *args, **kwargs)
            if actor.entity_id == self.v.entity_id:
                raise ValueError('late actual partner failure')
            return result
        def face(engine):
            engine.rng.random()
            return 16
        with patch.object(FASHION, 'replace_hp', side_effect=late_failure), patch.object(Engine, 'd20', face):
            with self.assertRaisesRegex(ValueError, 'late actual partner failure'):
                self.e.lose_hp(self.u, 1)
        self.assertEqual(self.e.export_state(), before)
        with patch.object(Engine, 'd20', return_value=16):
            self.e.lose_hp(self.u, 1)
        self.assertTrue(self.u.fainted)
        self.assertEqual(self.v.hp, 1)
        self.assertFalse(self.v.fainted)
        self.restore()
        self.valid()

    def test_focus_does_not_prevent_massive_injury_death_or_rescue_an_already_dead_actor(self):
        self.hold(self.p, 'death-band', 'item/기합의머리띠')
        self.e.gm.set_injuries(self.p, value=9, reason='observed actual severe injuries')
        self.e.gm.set_hp(self.p, value=self.p.base_max_hp, reason='observed true HP before hit')
        with patch.object(Engine, 'd20', return_value=16):
            self.e.take_damage(self.p, self.p.base_max_hp)
        self.assertEqual(self.p.hp, 1)
        self.assertGreaterEqual(self.p.injuries, 10)
        self.assertTrue(self.p.dead)
        with patch.object(Engine, 'd20') as rolled:
            self.e.lose_hp(self.p, 1)
        rolled.assert_not_called()
        self.assertTrue(self.p.dead)
        self.valid()

    def test_focus_sash_does_not_save_a_non_full_holder_from_an_actual_native_move(self):
        self.u = self.add('non-full actual sash holder', 'pokemon', (4, 2), stats=dict(self.common['stats'], hp=1))
        self.v = self.add('actual non-full test attacker', 'pokemon', (5, 2), side='foe',
                          stats=dict(self.common['stats'], atk=200), moves=['move/메가톤펀치'])
        self.hold(self.u, 'non-full-sash', 'item/기합의띠')
        self.e.gm.set_hp(self.u, value=self.u.base_max_hp-1, reason='observed not true full HP')
        self.combat(self.v)
        import heavy_injury_adapter as HEAVY
        with self.assertRaises(HEAVY.HeavyPending) as pending:
            self.use(self.v, self.u, 'move/메가톤펀치', face=18)
        self.assertTrue(self.u.fainted)
        self.assertNotIn('focus:item/기합의띠', self.u.spec.get('frequency_state',{}).get('activations',{}))
        self.assertEqual(HELD.entries(self.u)[0]['instance_id'], 'non-full-sash')
        HEAVY.acknowledge_ruling(self.e, pending.exception.event_id, self.u,
            expected_current_state=HEAVY.observe(self.u), ruling='GM retains the observed native hit and faint; additional Heavy consequences are externally adjudicated',
            disposition=HEAVY.ContinuationDisposition.CANCELLED_BY_RULING,
            continuation_reason='GM cancels the abandoned Move remainder; no automatic resumption or Heavy source-conformance claim')
        self.valid()

    def test_magic_room_distinguishes_inventory_adorable_from_actual_book_recipe_and_rejects_forged_contract(self):
        self.acquire()
        self.basic('charm', owner=self.q, uid='book-cute')
        I.equip_held(self.e, self.q, 'item/귀여운-패션', source_instance_id='book-cute')
        self.hold(self.p, 'ordinary-cute', 'item/귀여운-패션')
        ordinary = next(iter(self.p._item_reg.values()))
        source = self.p.spec[GRANTS.KEY]['sources'][ordinary['state_source']]
        source['fashion_contract'] = FASHION.book_definition(self.rules, 'item/귀여운-패션')
        with self.assertRaisesRegex(ValueError, 'actual source contract'):
            I._passive_registration(self.e, self.p, ordinary)
        source.pop('fashion_contract')
        self.room('move/매직룸')
        self.assertIn(SUPPRESSION.KEY, ordinary)
        self.assertNotIn(SUPPRESSION.KEY, next(iter(self.q._item_reg.values())))
        self.combat(self.q)
        self.e.activate_fashion_item(self.q, 'item/귀여운-패션')
        self.restore()
        self.assertEqual(LIFETIMES.numeric(self.q, 'evasion_modifier'), 2)
        self.room('move/원더룸')
        self.assertNotIn(SUPPRESSION.KEY, next(iter(self.p._item_reg.values())))
        self.valid()

    def test_magic_room_slotless_book_activation_and_focus_passive_suppress_restore_cold_and_binding(self):
        self.whole()
        FA.makeover(self.e, self.t, self.p, 'item/귀여운-패션', recipe_id='fashionista/basic-fashion-charm', seconds=600, reason='actual activated Book source')
        self.u = self.add('other actual Fashionista', 'trainer', (8, 2), classes=[], feats=[], exp_bank=100, money=10000,
                          fashionista_skill_choices=['매력','직감'])
        for feature in (FA.CLASS, FA.MAKEOVER, FA.STYLE):
            self.acquire(feature, self.u)
        FA.makeover(self.e, self.u, self.q, 'item/기합의머리띠', recipe_id='fashionista/focused-focus-band', seconds=600, reason='actual passive slotless Focus source')
        self.room('move/매직룸')
        self.assertNotIn(SUPPRESSION.KEY, next(iter(self.p._item_reg.values())))
        record = next(iter(self.q._item_reg.values()))
        self.assertIn(SUPPRESSION.KEY, record)
        with self.assertRaisesRegex(ValueError, 'actual Fashion projection'):
            FIELD.passive_equipment_suppressed(self.e, self.q, deepcopy(record))
        self.assertFalse(list(FASHION._equipment(self.e, self.q, FASHION.FOCUS_ITEMS)))
        self.restore()
        record = next(iter(self.q._item_reg.values()))
        self.assertIn(SUPPRESSION.KEY, record)
        bound = self.u.spec['ap_bound']
        saved = bound.pop(record['state_source'])
        with self.assertRaisesRegex(ValueError, 'bound Makeover'):
            FIELD.passive_equipment_suppressed(self.e, self.q, record)
        bound[record['state_source']] = saved
        self.combat(self.p)
        self.e.activate_fashion_item(self.p, 'item/귀여운-패션')
        self.assertEqual(LIFETIMES.numeric(self.p, 'evasion_modifier'), 2)
        self.room('move/원더룸')
        self.assertEqual(len(list(FASHION._equipment(self.e, self.q, FASHION.FOCUS_ITEMS))), 1)
        self.assertIsNone(next(iter(self.q._item_reg.values()))['instance_id'])
        self.restore()
        with patch.object(Engine, 'd20', return_value=16):
            self.e.lose_hp(self.q, self.q.base_max_hp)
        self.assertEqual(self.q.hp, 1)
        self.valid()

    def test_magic_room_stored_focus_dress_projection_restores_same_timed_source(self):
        self.whole()
        FA.make_chic(self.e, self.t, self.p, seconds=600, reason='actual Chic Focus model')
        self.craft('fashionista/focused-focus-band', uid='stored-band', owner=self.p)
        FA.store(self.e, self.p, 'stored-band', 'wardrobe:1', reason='actual stored Focus item')
        self.combat(self.t)
        FA.dress_to_impress(self.e, self.t, self.p)
        self.assertEqual(len(list(FASHION._equipment(self.e, self.p, FASHION.FOCUS_ITEMS))), 1)
        self.room('move/매직룸')
        self.assertFalse(list(FASHION._equipment(self.e, self.p, FASHION.FOCUS_ITEMS)))
        self.restore()
        self.room('move/원더룸')
        self.assertEqual(len(list(FASHION._equipment(self.e, self.p, FASHION.FOCUS_ITEMS))), 1)
        self.assertEqual(len(HELD.entries(self.p)), 0)
        self.assertEqual(len(FA.wardrobe_items(self.e, self.p)), 1)
        self.next_turn(self.p)
        self.assertFalse(list(FASHION._equipment(self.e, self.p, FASHION.FOCUS_ITEMS)))
        self.valid()


if __name__ == '__main__':
    unittest.main()
