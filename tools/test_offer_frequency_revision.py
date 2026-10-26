"""Original offer-frequency findings through acquired features and native actions."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine
import test_book_type_ace_acquisition as ACE_FIX
import test_book_type_ace_reactions as REACTIONS
import test_book_style_expert_full as STYLE_FIX
import test_book_chef_taste as TASTE_FIX
import test_category2_out_of_combat_eot as CLOCK_FIX
import test_book_martial_artist as MARTIAL_FIX
import book_chef_fixture as CHEF_FIX
import action_points as AP
import chef_cooking as CHEF
import combat_timing as TIME
import effect_lifetimes as LIFETIMES
import frequency as F
import state_codec as CODEC
import style_expert as STYLE
import type_ace as TA
import martial_artist as MA
import world_entities as WORLD


class TypeAceOfferFrequencyTests(unittest.TestCase):
    setUpClass = classmethod(ACE_FIX.TypeAceAcquisitionTests.setUpClass.__func__)
    setUp = ACE_FIX.TypeAceAcquisitionTests.setUp
    setup = ACE_FIX.TypeAceAcquisitionTests.setup
    add = ACE_FIX.TypeAceAcquisitionTests.add
    acquire = ACE_FIX.TypeAceAcquisitionTests.acquire
    combat = ACE_FIX.TypeAceAcquisitionTests.combat
    next_turn = ACE_FIX.TypeAceAcquisitionTests.next_turn
    communication = ACE_FIX.TypeAceAcquisitionTests.communication
    rejected = ACE_FIX.TypeAceAcquisitionTests.rejected
    restore = ACE_FIX.TypeAceAcquisitionTests.restore
    valid = ACE_FIX.TypeAceAcquisitionTests.valid
    family = REACTIONS.TypeAceReactionTests.family
    known = REACTIONS.TypeAceReactionTests.known
    answer = REACTIONS.TypeAceReactionTests.answer
    native = REACTIONS.TypeAceReactionTests.native
    sustain = REACTIONS.TypeAceReactionTests.sustain

    def no_offer(self, feature):
        decide = type(self.e.rulings).decide
        def checked(rulings, question, *args, **kwargs):
            self.assertFalse(question.get('type') == 'type_ace_choice'
                and question.get('feature') == TA.uid(feature), 'exhausted target was offered the feature')
            return decide(rulings, question, *args, **kwargs)
        return patch.object(type(self.e.rulings), 'decide', autospec=True, side_effect=checked)

    def test_chitin_exhausted_target_does_not_abort_other_status_move_and_other_target_remains_eligible(self):
        self.family('벌레', 'Insectoid Utility', 'Chitin Shield')
        self.answer('type_ace_choice', True)
        self.combat(self.b)
        self.native(self.b, self.p, 'move/초음파', face=19)
        self.assertNotIn('혼란', self.p.conditions)
        self.assertTrue(any(r.get('ace_chitin_move') == 'move/초음파' for r in TIME.records(self.p)))
        self.restore()
        with self.no_offer('Chitin Shield'):
            self.next_turn(self.b)
            self.native(self.b, self.p, 'move/거짓울음', face=19)
        self.assertEqual(self.p.stages['spd'], -2)
        self.assertEqual(self.b.budget['standard'], 0)
        self.next_turn(self.b);self.next_turn(self.b)  # Fake Tears is EOT: complete its intervening turn.
        self.native(self.b, self.q, 'move/거짓울음', face=19)
        self.assertEqual(self.b.budget['standard'],0)
        self.assertTrue(any(r.get('ace_chitin_move')=='move/거짓울음' for r in TIME.records(self.q)))
        self.assertEqual(self.q.stages['spd'], 0)
        self.assertFalse(F.activation_allowed(self.p, TA.uid('Chitin Shield'), {'kind':'scene','uses':1}, engine=self.e))
        self.assertTrue(F.activation_allowed(self.t, TA.uid('Chitin Shield'), {'kind':'daily','uses':3}, engine=self.e))
        self.e.end_of_turn(self.b); self.e.end_round(); self.e.end_scene(self.e.everyone)
        self.assertFalse(any(a['key']=='type_ace_choice' for a in self.e.rulings.answers))
        self.answer('type_ace_choice', True)  # A new Scene needs its own actual player choice.
        self.combat(self.b)
        self.native(self.b, self.p, 'move/거짓울음', face=19)
        self.assertTrue(any(r.get('ace_chitin_move') == 'move/거짓울음' for r in TIME.records(self.p)))
        with self.no_offer('Chitin Shield'):
            self.next_turn(self.b);self.next_turn(self.b)
            self.native(self.b, self.q, 'move/거짓울음', face=19)
        self.assertEqual(self.b.budget['standard'],0)
        self.assertEqual(self.q.stages['spd'], -2)
        self.valid()

    def test_simple_improvements_exhausted_target_starts_turn_and_distinct_target_can_accept(self):
        self.family('노말', 'Extra Ordinary', 'Simple Improvements')
        self.answer('type_ace_choice', True)
        self.combat(self.p)
        self.assertEqual((TA.all_rolls(self.p), self.p.temp_hp), (6, 12))
        self.restore()
        with self.no_offer('Simple Improvements'):
            self.next_turn(self.p)
        self.assertIs(self.e._active_turn_actor, self.p)
        self.assertEqual((self.p.budget['standard'], TA.all_rolls(self.p), self.p.temp_hp), (1, 0, 12))
        self.native(self.p, self.b, 'move/몸통박치기', face=19)
        self.assertEqual(self.p.budget['standard'], 0)
        self.next_turn(self.q)
        self.assertEqual((TA.all_rolls(self.q), self.q.temp_hp), (6, 12))
        self.e.end_of_turn(self.q); self.e.end_round(); self.e.end_scene(self.e.everyone)
        self.assertFalse(any(a['key']=='type_ace_choice' for a in self.e.rulings.answers))
        self.answer('type_ace_choice', True)  # Preserve Scene-scoped decisions and the daily use cap.
        self.combat(self.p)
        self.assertEqual(TA.all_rolls(self.p), 6)
        with self.no_offer('Simple Improvements'):
            self.next_turn(self.q)
        self.assertEqual((self.q.budget['standard'], TA.all_rolls(self.q)), (1, 0))
        self.valid()

    def test_gale_exhaustion_rejects_before_dice_action_or_possible_free_result(self):
        self.family('비행', 'Celerity', 'Gale Strike')
        self.known(self.p, 'move/바람일으키기')
        self.combat(self.p)
        self.answer('type_ace_gale_strike', 'second')
        for index in range(2):
            if index:self.next_turn(self.p)
            with patch.object(Engine, 'd20', side_effect=(10, 15)):
                TA.use_move(self.e, self.t, self.p, self.b, 'move/바람일으키기', feature=TA.uid('Gale Strike'), set_damage=True)
        self.next_turn(self.p)
        self.answer('type_ace_gale_strike', 'first')
        self.restore()
        with patch.object(Engine, 'd20', side_effect=AssertionError('exhausted Gale Strike rolled')):
            self.rejected(lambda: TA.use_move(self.e, self.t, self.p, self.b, 'move/바람일으키기',
                feature=TA.uid('Gale Strike'), set_damage=True), 'frequency exhausted')
        self.assertEqual(self.p.budget['standard'], 1)
        self.valid()

    def test_clever_ruse_joins_extra_evasion_cap_and_native_haze_clears_only_its_evasion(self):
        self.family('악', 'Clever Ruse')
        self.e.gm.set_stage(self.p, 'eva', value=3, reason='actual independent evasion stage')
        self.combat(self.p)
        TA.special(self.e, self.t, self.p, 'Clever Ruse', choices=['evasion', 'ignore_evasion'])
        self.assertEqual(self.p.evasion('물리', engine=self.e, ignore_stats=True), 6)
        self.assertEqual(self.p.evasion('물리', engine=self.e), 9)
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.b, initiative_count=20)
        self.native(self.b, self.b, 'move/흑안개')
        self.assertEqual((TA.evasion_extra(self.p), self.p.evasion_mod), (0, 0))
        self.assertTrue(TA.ignore_stat_evasion(self.p))
        self.restore()
        self.assertEqual(TA.evasion_extra(self.p), 0)
        self.valid()

    def test_debilitate_native_haze_clears_evasion_but_preserves_accuracy_roll_penalty(self):
        import effects_ext as EXT
        def accuracy_penalty(expected):
            observed=[];native=EXT.accuracy_hook
            def observe(engine,actor,target,move,mechanics,context):
                result=native(engine,actor,target,move,mechanics,context)
                if actor is self.b:observed.append(result[2])
                return result
            with patch.object(EXT,'accuracy_hook',side_effect=observe):
                self.e.accuracy_check(self.b,self.p,self.e.r.move('move/몸통박치기'),fixed_roll=10)
            self.assertEqual(observed,[expected])
        self.family('독', 'Potent Venom', 'Debilitate')
        self.e.gm.add_condition(self.b, '독', reason='actual poisoned foe')
        self.sustain('Debilitate')
        self.native(self.p, self.b, 'move/독침', face=10)
        self.assertEqual((TA.evasion_extra(self.b), TIME.accuracy_modifier(self.b, include_effect_contract=False)), (-2, -2))
        accuracy_penalty(-2)
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.b, initiative_count=20)
        self.native(self.b, self.b, 'move/흑안개')
        self.assertEqual((TA.evasion_extra(self.b), TIME.accuracy_modifier(self.b, include_effect_contract=False)), (0, -2))
        accuracy_penalty(-2)
        self.restore()
        self.assertEqual(TIME.accuracy_modifier(self.b, include_effect_contract=False), -2)
        accuracy_penalty(-2)
        self.e.end_of_turn(self.b);self.e.end_round();self.combat(self.p)
        self.assertEqual((TA.evasion_extra(self.b),TIME.accuracy_modifier(self.b, include_effect_contract=False)),(0,0))
        accuracy_penalty(0)
        self.valid()


class StyleFlourishFrequencyTests(unittest.TestCase):
    setUpClass = classmethod(STYLE_FIX.StyleExpertTests.setUpClass.__func__)
    setUp = STYLE_FIX.StyleExpertTests.setUp
    setup = STYLE_FIX.StyleExpertTests.setup
    acquire = STYLE_FIX.StyleExpertTests.acquire
    family = STYLE_FIX.StyleExpertTests.family
    combat = STYLE_FIX.StyleExpertTests.combat
    use = STYLE_FIX.StyleExpertTests.use
    rejected = STYLE_FIX.StyleExpertTests.rejected
    restored = STYLE_FIX.StyleExpertTests.restored

    def test_acquired_flourish_branches_have_independent_target_scene_limits_after_restore(self):
        self.family(rank=2, flourish=True)
        for partner in self.partners:
            partner.spec['poffins'].extend(['근사함'] * 3)
        self.acquire(STYLE.CLASS, stat='근사함')
        self.acquire(STYLE.RANKED['근사함'], rank=1)
        self.acquire(STYLE.RANKED['근사함'], rank=2)
        self.acquire(STYLE.FLOURISH, stat='근사함')
        self.combat()
        self.use('move/유혹', ranked=STYLE.RANKED['아름다움'], flourish=True)
        self.restored()
        self.e.end_of_turn(self.p); self.e.end_round(); self.combat()
        self.rejected(lambda: self.use('move/유혹', ranked=STYLE.RANKED['아름다움'], flourish=True), 'already affected')
        before = AP.available(self.a)
        self.use('move/부르짖기', ranked=STYLE.RANKED['근사함'], flourish=True)
        self.assertEqual((self.p.stages['spa'], self.p.stages['atk'], AP.available(self.a)), (1, 1, before - 2))
        self.assertEqual({r['style_flourish'] for r in TIME.records(self.p) if r.get('style_flourish')}, {'아름다움', '근사함'})
        self.restored()
        self.rejected(lambda: self.use('move/부르짖기', ranked=STYLE.RANKED['근사함'], flourish=True), 'already affected')
        self.e.end_of_turn(self.p); self.e.end_round(); self.e.end_scene(self.e.everyone); self.combat()
        self.use('move/유혹', ranked=STYLE.RANKED['아름다움'], flourish=True)
        self.assertEqual({r['style_flourish'] for r in TIME.records(self.p) if r.get('style_flourish')}, {'아름다움'})
        self.assertTrue(self.e.validate_state()['valid'])


class ChefEvasionResetTests(unittest.TestCase):
    setUpClass = classmethod(TASTE_FIX.ChefTasteTests.setUpClass.__func__)
    setUp = TASTE_FIX.ChefTasteTests.setUp
    trade_in = TASTE_FIX.ChefTasteTests.trade_in

    def test_sour_taste_joins_extra_evasion_cap_and_expires_at_native_stage_reset(self):
        world = CHEF_FIX.scene(self.rules, pokemon_nature=CHEF_FIX.nature_for(self.rules, '신맛', 'liked'))
        e, chef, p, foe = (world[k] for k in ('engine', 'chef', 'partner', 'foe'))
        snack = CHEF_FIX.cook(e, chef, recipe='tasty_snack', snack='신맛 캔디')
        served = CHEF_FIX.serve(e, chef, snack['batch_id'], p)
        CHEF_FIX.ruling(e, 'scene_end')
        CHEF_FIX.battle(e, foe)
        self.trade_in(e, p, served['buff_id'], attacker=foe, target=p)
        CHEF_FIX.decline_all(e, chef)
        self.assertEqual(CHEF.evasion_bonus(p, '물리'), 1)
        retained=deepcopy([r for r in TIME.records(p) if r.get(CHEF.BONUS)])
        self.assertEqual(len(retained),1)
        if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
        e.end_round();CHEF_FIX.battle(e,foe)
        e.gm.set_stage(p, 'eva', value=6, reason='actual independent evasion at cap')
        self.assertEqual(p.evasion('물리', engine=e, ignore_stats=True), 6)
        e.gm.set_move(foe, 'move/흑안개', reason='actual learned native stage reset')
        e.use_move_on(foe, foe, 'move/흑안개', e.everyone)
        self.assertEqual(foe.budget['standard'],0)
        self.assertEqual((p.evasion_mod, CHEF.evasion_bonus(p, '물리')), (0, 1))
        self.assertEqual([r for r in TIME.records(p) if r.get(CHEF.BONUS)],retained)
        loaded, actors = CHEF_FIX.restore(self.rules, e)
        restored=actors[p.entity_id]
        self.assertEqual(CHEF.evasion_bonus(restored, '물리'), 1)
        self.assertEqual([r for r in TIME.records(restored) if r.get(CHEF.BONUS)],retained)
        loaded.end_scene()
        self.assertEqual(CHEF.evasion_bonus(restored, '물리'),0)
        self.assertFalse(any(r.get(CHEF.BONUS) for r in TIME.records(restored)))
        self.assertTrue(loaded.validate_state()['valid'])


class PummelingEvasionResetTests(unittest.TestCase):
    setUpClass = classmethod(MARTIAL_FIX.MartialArtistTests.setUpClass.__func__)
    setUp = MARTIAL_FIX.MartialArtistTests.setUp
    setup = MARTIAL_FIX.MartialArtistTests.setup
    acquire = MARTIAL_FIX.MartialArtistTests.acquire
    start = MARTIAL_FIX.MartialArtistTests.start
    next = MARTIAL_FIX.MartialArtistTests.next
    use = MARTIAL_FIX.MartialArtistTests.use
    restore = MARTIAL_FIX.MartialArtistTests.restore
    valid = MARTIAL_FIX.MartialArtistTests.valid

    def haze(self, actor, count):
        self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_of_turn(actor, initiative_count=count)
        self.e.gm.set_move(actor, 'move/흑안개', reason='actual learned stage reset')
        self.e.use_move_on(actor, actor, 'move/흑안개', self.e.everyone)

    def test_tag_evasion_caps_resets_and_rebuilds_at_accuracy_cap_without_erasing_history(self):
        for earned in (2, 6):
            with self.subTest(earned_accuracy=earned):
                self.setup(); self.acquire(training=1); self.start()
                MA.arm(self.e, self.a, 'pummeling_momentum', target=self.t)
                for index in range(earned):
                    if index:self.next()
                    self.use('마하펀치')
                self.e.gm.set_stage(self.a, 'eva', value=6, reason='independent extra evasion at cap')
                self.assertEqual(self.a.evasion('물리', attacker=self.t, engine=self.e, ignore_stats=True), 6)
                tag = self.a.spec[MA.TAG]
                original_completion = tag['completion_id']
                original_gain = deepcopy(self.e._move_completions[original_completion][MA.TAG])
                self.haze(self.t, 20)
                self.assertEqual((MA.bonus(self.a, self.t), MA.bonus(self.a, self.t, evasion=True)), (earned, 0))
                self.assertEqual(self.a.evasion('물리', attacker=self.t, engine=self.e, ignore_stats=True), 0)
                self.assertEqual(self.e._move_completions[original_completion][MA.TAG], original_gain)
                self.restore(); self.valid()
                self.next(); self.use('마하펀치')
                self.assertEqual((MA.bonus(self.a, self.t), MA.bonus(self.a, self.t, evasion=True)), (min(6, earned+1), 1))
                self.assertEqual(self.e._move_completions[original_completion][MA.TAG], original_gain)
                self.assertEqual(MA.bonus(self.a, self.u, evasion=True), 0)
                self.assertEqual(self.a.evasion('물리', attacker=self.t, engine=self.e, ignore_stats=True), 1)
                self.restore(); self.valid()
                original = deepcopy(self.a.spec[MA.TAG])
                for corruption in ('increase', 'remove', 'null'):
                    self.a.spec[MA.TAG] = deepcopy(original)
                    if corruption == 'increase':self.a.spec[MA.TAG]['evasion']['value'] = 2
                    elif corruption == 'remove':self.a.spec[MA.TAG].pop('evasion')
                    else:self.a.spec[MA.TAG]['evasion'] = None
                    MA._seal_tag(self.a.spec[MA.TAG])
                    self.assertFalse(self.e.validate_state()['valid'])
                self.a.spec[MA.TAG] = original
                self.haze(self.u, 10)
                self.assertEqual((MA.bonus(self.a, self.t), MA.bonus(self.a, self.t, evasion=True)), (min(6, earned+1), 0))
                self.restore(); self.valid()
                self.next(); self.e.end_of_turn(self.a)
                self.assertNotIn(MA.TAG, self.a.spec)
                self.assertEqual(MA.bonus(self.a, self.t, evasion=True), 0)


class SceneMoveWorldClockTests(unittest.TestCase):
    setUpClass = classmethod(CLOCK_FIX.OutOfCombatEotTests.setUpClass.__func__)
    setUp = CLOCK_FIX.OutOfCombatEotTests.setUp

    def use_scene(self):
        return self.e.use_move(self.p, self.p, 'move/똬리틀기', free_action=True)

    def test_scene_move_uses_world_seconds_and_cap_without_actor_turns_across_restore(self):
        move = 'move/똬리틀기'
        self.e.gm.set_move(self.p, move, reason='actual learned Scene x2 Move')
        self.use_scene()
        self.e.advance_time(9, [self.p])
        before = (deepcopy(self.p.spec), deepcopy(self.p.stages), self.e.rng.getstate())
        self.use_scene()
        self.assertEqual((self.p.spec, self.p.stages, self.e.rng.getstate()), before)
        identity = self.p.entity_id
        self.e = CODEC.load_engine(self.rules, CODEC.dump_engine(self.e))
        self.p = WORLD.actor_index(self.e)[identity]
        self.e.advance_time(1, [self.p])
        self.use_scene()
        self.assertEqual((self.p.move_uses[move], self.p.stages['atk'], self.p.stages['def']), (2, 2, 2))
        self.e.advance_time(3600, [self.p])
        before = (deepcopy(self.p.spec), deepcopy(self.p.stages), self.e.rng.getstate())
        self.use_scene()
        self.assertEqual((self.p.spec, self.p.stages, self.e.rng.getstate()), before)
        self.e.end_scene([self.p]); self.use_scene()
        self.assertEqual(self.p.move_uses[move], 1)


if __name__ == '__main__':
    unittest.main()
