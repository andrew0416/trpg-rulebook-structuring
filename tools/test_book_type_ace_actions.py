"""Type Ace special actions through acquired features and actual native turns.

Reuse acquisition fixture helpers without inheriting or collecting its tests.
Move completions below are produced by Engine, never caller supplied hits.
"""
from unittest.mock import patch
import unittest

import test_book_type_ace_acquisition as fixture
from engine import Engine, Rules
import action_points as AP
import action_resources as RESOURCES
import movement_actions as MOVEMENT
import move_defense_reactions as DEFENSE
import state_fields as FIELDS
import type_ace as TA


class TypeAceActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    # Only fixture methods are borrowed: no inherited test methods or load_tests.
    setUp = fixture.TypeAceAcquisitionTests.setUp
    setup = fixture.TypeAceAcquisitionTests.setup
    add = fixture.TypeAceAcquisitionTests.add
    acquire = fixture.TypeAceAcquisitionTests.acquire
    rejected = fixture.TypeAceAcquisitionTests.rejected
    combat = fixture.TypeAceAcquisitionTests.combat
    next_turn = fixture.TypeAceAcquisitionTests.next_turn
    communication = fixture.TypeAceAcquisitionTests.communication
    valid = fixture.TypeAceAcquisitionTests.valid

    def branch(self, branch, *features):
        self.setup()
        skill = TA.SKILLS[branch][0]
        self.t.spec['type_link_skills'][branch] = skill
        FIELDS.base_patch(self.t, {'skills':dict(self.t.spec['skills'], **{skill:6})},
            reason='observed actual Master Type-linked skill')
        for pokemon in (self.p, self.q):
            FIELDS.base_patch(pokemon, {'types':[branch]}, reason='actual matching owned pair')
        self.acquire(branch=branch)
        for feature in features:
            self.acquire(feature, branch)

    def answer(self, key, value):
        self.e.rulings.answers[:] = [a for a in self.e.rulings.answers if a['key'] != key]
        self.e.rulings.add_answer(key, value, reason='actual selected scene choice')

    def known(self, actor, *moves):
        for move in moves:
            if move not in actor.moves:
                self.e.gm.set_move(actor, move, reason='actual complete known Move list')

    def native(self, actor, target, move, *, face=10):
        self.known(actor, move)
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(actor, target, move, self.e.everyone, set_damage=True)

    def completed(self, actor, move=None):
        return next(row for row in reversed(list(self.e._move_completions.values()))
            if row['actor'] is actor and row['phase'] == 'complete'
            and (move is None or row['move_id'] == move))

    def sustain(self, feature):
        self.communication()
        self.combat(self.t)
        before = AP.available(self.t)
        TA.activate(self.e, self.t, self.p, TA.uid(feature))
        self.assertEqual(AP.available(self.t), before - 2)
        self.e.end_of_turn(self.t)
        self.e.start_of_turn(self.p, initiative_count=30)

    def special(self, feature, **options):
        return TA.special(self.e, self.t, self.p, TA.uid(feature), **options)

    def test_fairy_lights_attacks_hit_or_miss_spend_one_for_temp_hp_or_actual_free_wind(self):
        for face, choice in ((1,'temporary_hp'), (10,'temporary_hp'), (10,'fairy_wind')):
            with self.subTest(face=face, choice=choice):
                self.branch('페어리', 'Fairy Lights')
                self.combat(self.p)
                self.special('Fairy Lights')
                self.assertEqual((TA._lights(self.p)['ace_lights'], self.p.budget['standard']), (3,0))
                self.answer('type_ace_fairy_light', choice)
                self.e.end_of_turn(self.p)
                self.e.start_of_turn(self.b, initiative_count=20)
                hp = self.b.hp
                # A status attack observes the light without absorbing its temp HP.
                self.native(self.b, self.p, 'move/거짓울음', face=face)
                self.assertEqual(TA._lights(self.p)['ace_lights'], 2)
                self.assertEqual(self.p.budget['standard'], 0)
                if choice == 'temporary_hp':
                    self.assertEqual(self.p.temp_hp, self.e.tick(self.p))
                else:
                    self.assertLess(self.b.hp, hp)
                    self.assertEqual(self.completed(self.p)['move_id'], 'move/요정의바람')
                    self.assertNotIn('move/요정의바람', self.p.moves)
                self.valid()
        self.branch('페어리', 'Fairy Lights')
        self.combat(self.p)
        self.special('Fairy Lights')
        self.answer('type_ace_fairy_light', 'temporary_hp')
        self.e.gm.set_position(self.b, (9,2), reason='actual attacker seven meters away')
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.b, initiative_count=20)
        self.native(self.b, self.p, 'move/거짓울음')
        self.assertEqual(TA._lights(self.p)['ace_lights'], 3)
        self.assertEqual(self.p.temp_hp, 0)

    def test_fairy_light_extended_control_and_rite_heal_use_remaining_actual_lights(self):
        self.branch('페어리', 'Fairy Lights', 'Fairy Rite')
        # Both native creation and Extended positioning may happen before combat.
        self.special('Fairy Lights')
        elapsed = self.e.elapsed_seconds
        projection = TA.control_lights(self.e, self.t, self.p,
            positions=[(8,2),(2,8),(1,2)], seconds=60, reason='actual individual candle positioning')
        self.assertEqual(self.e.elapsed_seconds, elapsed + 60)
        self.assertEqual(set(projection['positions']), {(8,2),(2,8),(1,2)})
        self.assertEqual(projection['quality'], 'mild_candle')
        self.rejected(lambda:TA.control_lights(self.e,self.t,self.p,
            positions=[(9,2),(2,8),(1,2)],seconds=60,reason='outside six meters'), 'six|6')
        self.combat(self.p)
        self.e.lose_hp(self.p, 300, source='actual earlier damage')
        self.e.lose_hp(self.q, 1000, source='actual earlier damage')  # keep the printed healing below the maximum
        for options, pattern in (({'hp':self.p.level+1},'sacrifice'),
                ({'hp':1,'target':self.b},'ally'),
                ({'hp':1,'lights':[self.p]*4},'available Fairy Lights')):
            args = dict(target=self.q, hp=1, lights=[])
            args.update(options)
            self.rejected(lambda args=args:self.special('Fairy Rite', **args), pattern)
        hp = self.p.hp, self.q.hp
        self.special('Fairy Rite', target=self.q, hp=self.p.level, lights=[self.p,self.q,self.q])
        self.assertEqual(self.p.hp, hp[0] - self.p.level + self.e.tick(self.p))
        self.assertEqual(self.q.hp, hp[1] + self.p.level + 2*self.e.tick(self.q))
        self.assertEqual((self.p.budget['standard'],TA._lights(self.p)['ace_lights']), (0,0))
        self.valid()
        # Adopted author errata: Fairy Rite has no Fairy Lights creation trigger.
        self.branch('페어리','Fairy Lights','Fairy Rite')
        self.combat(self.p)
        self.e.lose_hp(self.p,300,source='actual earlier damage')
        self.e.lose_hp(self.q,400,source='actual earlier damage')
        self.assertIsNone(TA._lights(self.p))
        hp = self.p.hp,self.q.hp
        self.special('Fairy Rite',target=self.q,hp=self.p.level)
        self.assertEqual((self.p.hp,self.q.hp),(hp[0]-self.p.level,hp[1]+self.p.level))
        self.assertEqual(self.p.budget['standard'],0)
        for sacrifice in (0,1):
            self.next_turn(self.p)
            self.special('Fairy Rite',target=self.q,hp=sacrifice)
        self.next_turn(self.p)
        self.rejected(lambda:self.special('Fairy Rite',target=self.q,hp=1),'frequency')
        self.valid()

    def test_ghost_step_hides_until_reachable_return_and_is_once_per_pokemon_scene(self):
        self.branch('고스트', 'Ghost Step')
        self.e.gm.set_movement_capabilities(self.p, {'land':3,'sky':0,'swim':0},
            basis='base', reason='actual three-meter Shift capability')
        self.combat(self.p)
        self.special('Ghost Step', mode='land')
        self.assertTrue(TA.ghost_hidden(self.p))
        self.assertEqual(self.p.budget['shift'], 0)
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.b, initiative_count=20)
        hp = self.p.hp
        self.native(self.b, self.p, 'move/거짓울음')
        self.assertEqual((self.p.hp,self.p.stages['spd']), (hp,0))
        self.answer('type_ace_ghost_return', [(3,2),(3,3),(3,4)])
        self.next_turn(self.p)
        self.assertFalse(TA.ghost_hidden(self.p))
        self.assertEqual(self.p.pos, (3,4))
        self.assertEqual(self.p.budget['shift'], 1)
        self.rejected(lambda:self.special('Ghost Step',mode='land'), 'frequency|once')
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.q,initiative_count=20)
        TA.special(self.e,self.t,self.q,TA.uid('Ghost Step'),mode='land')
        self.assertTrue(TA.ghost_hidden(self.q))
        self.valid()

    def test_haunting_tokens_actual_ghost_moves_pay_each_printed_condition_and_faint_free(self):
        for cost, conditions in ((1,set()),(2,{'저주'}),(3,{'억압'}),(4,{'잠듦','악몽'})):
            with self.subTest(cost=cost):
                self.branch('고스트', 'Ghost Step', 'Haunting Curse')
                # The Stratagem's target is any owned Pokemon, not only Ghosts.
                FIELDS.base_patch(self.p, {'types':['노말']}, reason='actual non-Ghost Stratagem recipient')
                self.e.gm.set_position(self.p, (3,2), reason='actual adjacent Lick user')
                self.sustain('Haunting Curse')
                for n in range(cost):
                    if n:self.next_turn(self.p)
                    self.native(self.p, self.b, 'move/핥기')
                self.assertEqual(TA.sustained(self.e,self.p,TA.uid('Haunting Curse'))[1]['tokens'], cost)
                if cost == 4:
                    self.answer('type_ace_faint_curse', {'target_id':self.b.entity_id,'cost':cost})
                    self.e.lose_hp(self.p,self.p.hp,source='actual fainting producer')
                    self.assertTrue(self.p.fainted)
                else:
                    self.next_turn(self.p)
                    self.rejected(lambda:self.special('Haunting Curse',target=self.q,cost=cost),
                        'tokens|foe|six')
                    self.special('Haunting Curse',target=self.b,cost=cost,
                        **({'stats':['atk']} if cost == 1 else {}))
                    self.assertEqual(self.p.budget['standard'],0)
                self.assertTrue(conditions <= self.b.conditions)
                if cost == 1:self.assertEqual(self.b.stages['atk'],-1)
                row = TA.sustained(self.e,self.p,TA.uid('Haunting Curse'))
                if row:self.assertEqual(row[1]['tokens'],0)
                self.valid()

    def test_boo_ghost_return_and_actual_setup_resolution_gain_smite_and_block_defenses(self):
        for source in ('Ghost Step','move/고스트다이브','move/섀도다이브'):
            with self.subTest(source=source):
                self.branch('고스트', 'Ghost Step', 'Haunting Curse', 'Boo!')
                FIELDS.base_patch(self.b,{'types':['물']},reason='actual foe vulnerable to Ghost Smite')
                self.e.gm.set_position(self.p,(3,2),reason='actual adjacent Ghost attacker')
                self.sustain('Haunting Curse')
                self.answer('type_ace_choice', True)
                if source == 'Ghost Step':
                    self.special(source,mode='land')
                    self.answer('type_ace_ghost_return',[(3,3)])
                    self.next_turn(self.p)
                    move = 'move/핥기'
                    expected_tokens = 2
                else:
                    self.native(self.p,self.b,source)
                    self.assertEqual(TA.sustained(self.e,self.p,TA.uid('Haunting Curse'))[1]['tokens'],1)
                    self.next_turn(self.p)
                    move = source
                    expected_tokens = 2
                hp = self.b.hp
                # A natural miss still deals Smite damage, not an automatic hit.
                self.native(self.p,self.b,move,face=1)
                self.assertLess(self.b.hp,hp)
                actual = self.completed(self.p,move)['move']
                self.assertIn('강타',actual['keywords'])
                for category in ('intercept','dodge','parry','shield'):
                    self.assertTrue(DEFENSE._prohibited(self.e,actual,category))
                self.assertFalse(TA._buff(self.p,'ace_boo'))
                self.assertEqual(TA.sustained(self.e,self.p,TA.uid('Haunting Curse'))[1]['tokens'],expected_tokens)
                self.valid()

    def test_fey_trance_social_or_fairy_status_uses_actual_cap_mode_and_next_shift_debt(self):
        for move, mode in (('move/거짓울음','land'),('move/애교부리기','sky')):
            with self.subTest(move=move,mode=mode):
                self.branch('페어리','Fairy Lights','Fey Trance')
                FIELDS.base_patch(self.p,{'types':['노말']},reason='actual unrestricted Fey Trance recipient')
                self.e.gm.set_position(self.b,(8,2),reason='actual six-meter foe')
                self.e.gm.set_movement_capabilities(self.b,{'land':3,'sky':3,'swim':0},
                    basis='base',reason='actual limited approach capabilities')
                self.sustain('Fey Trance')
                path = [(x,2) for x in (7,6,5,4,3)]
                if mode == 'sky':path = [{'position':p,'altitude':0} for p in path]
                self.answer('type_ace_fey_approach',{'mode':mode,'path':path})
                self.native(self.p,self.b,move)
                self.assertIn('헤롱헤롱',self.b.conditions)
                self.assertEqual(self.b.pos,(5,2))
                self.assertEqual(RESOURCES.pending(self.b),{'shift':1})
                self.e.end_of_turn(self.p)
                self.e.start_of_turn(self.b,initiative_count=20)
                self.assertEqual(self.b.budget['shift'],0)
                self.e.end_of_turn(self.b)
                self.e.end_round()
                self.combat(self.p)
                self.native(self.p,self.b,move)
                self.assertEqual(self.b.pos,(5,2))
                self.assertEqual(RESOURCES.pending(self.b),{})
                self.valid()

    def test_fey_trance_pure_vertical_approach_and_away_path_boundary(self):
        self.branch('페어리','Fairy Lights','Fey Trance')
        self.e.gm.set_position(self.b,(2,2),reason='actual vertically separated foe')
        self.e.gm.set_movement_capabilities(self.b,{'land':0,'sky':2,'swim':0},
            basis='base',reason='actual aerial approach capability')
        MOVEMENT.entry_mode(self.b,'공중/부유',altitude=4)
        self.sustain('Fey Trance')
        # The planar flanking rule leaves cross-plane foe membership pending, so the aerial
        # foe faces exactly one grounded foe here: the approaching Fey Trance Pokemon.
        self.e.gm.recall(self.q,reason='actual recalled partner')
        self.t.on_field=False
        self.answer('type_ace_fey_approach',{'mode':'sky',
            'path':[{'position':(2,2),'altitude':5}]})
        self.known(self.p,'move/애교부리기')
        self.rejected(lambda:self.native(self.p,self.b,'move/애교부리기'), 'toward|approach|distance')
        self.answer('type_ace_fey_approach',{'mode':'sky',
            'path':[{'position':(2,2),'altitude':z} for z in (3,2,1)]})
        self.native(self.p,self.b,'move/애교부리기')
        self.assertEqual((self.b.pos,self.b.spec['_movement_altitude']),((2,2),2))
        self.assertEqual(RESOURCES.pending(self.b),{'shift':1})
        self.valid()

    def test_celerity_target_alternatives_add_initiative_and_disengage_actual_slowed_budget(self):
        for types, mode in ((['비행'],'land'),(['노말'],'sky'),(['노말'],'levitate')):
            with self.subTest(types=types,mode=mode):
                self.branch('비행','Celerity')
                FIELDS.base_patch(self.p,{'types':types},reason='actual printed Celerity target alternative')
                self.e.gm.set_movement_capabilities(self.p,{'land':10,'sky':10 if mode=='sky' else 0,
                    'levitate':10 if mode=='levitate' else 0,'swim':0},basis='base',reason='actual ten-meter movement')
                self.e.gm.set_position(self.p,(2,4),reason='actual open Disengage lane')
                before = self.e.initiative_value(self.p).value
                self.sustain('Celerity')
                self.assertEqual(self.e.initiative_value(self.p).value,before+6)
                cap = MOVEMENT.distance_budget(self.e,self.p,mode,as_slowed=True)
                self.assertGreater(cap,2)
                path = [(x,4) for x in range(3,11)]
                if mode != 'land':path = [{'position':point,'altitude':0} for point in path]
                result = TA.disengage(self.e,self.p,path,mode=mode)
                self.assertEqual(result['distance'],cap)
                self.assertEqual(self.p.budget['shift'],0)
                self.valid()
        self.branch('비행','Celerity')
        FIELDS.base_patch(self.p,{'types':['노말']},reason='actual grounded non-Flying target')
        self.communication()
        self.combat(self.t)
        self.rejected(lambda:TA.activate(self.e,self.t,self.p,TA.uid('Celerity')),'Flying|Sky|Levitate')

    def test_clever_ruse_actual_miss_free_disengage_deliberate_standard_and_round_limit(self):
        self.branch('악','Clever Ruse')
        self.combat(self.p)
        self.native(self.p,self.b,'move/악의파동',face=1)
        completion = self.completed(self.p)['id']
        shift = self.p.budget['shift']
        TA.react(self.e,self.t,self.p,TA.uid('Clever Ruse'),completion,
            choices=['evasion','disengage'],path=[(3,2)])
        self.assertEqual((self.p.pos,self.p.budget['shift']),((3,2),shift))
        self.assertEqual(TA.evasion_extra(self.p),4)
        self.rejected(lambda:self.special('Clever Ruse',choices=['evasion','ignore_evasion']),
            'round|Standard')
        self.next_turn(self.p)
        self.assertEqual(TA.evasion_extra(self.p),0)
        self.special('Clever Ruse',choices=['evasion','ignore_evasion'])
        self.assertEqual(self.p.budget['standard'],0)
        self.assertTrue(TA.ignore_stat_evasion(self.p))
        self.next_turn(self.p)
        self.assertTrue(TA.ignore_stat_evasion(self.p))
        self.e.end_of_turn(self.p)
        self.assertFalse(TA.ignore_stat_evasion(self.p))
        self.valid()
        for trigger in ('hit','partial_hit','not_own_turn'):
            with self.subTest(rejected_trigger=trigger):
                self.branch('악','Clever Ruse')
                self.combat(self.p)
                if trigger == 'partial_hit':
                    second = self.add('second actual Dark area target','pokemon',(4,3),side='foe')
                    # An area Move shares one accuracy face; the second target's higher Evasion turns it into the miss.
                    self.e.gm.set_stage(second,'eva',value=6,reason='actual independent evasion bonus on the second target')
                    self.known(self.p,'move/바크아웃')
                    with patch.object(Engine,'d20',return_value=10):
                        self.e.use_move_on(self.p,self.b,'move/바크아웃',self.e.everyone,set_damage=True)
                    actual = self.completed(self.p)
                    self.assertTrue(TA._completed_targets(actual))
                    self.assertTrue(TA._completed_targets(actual,False))
                else:
                    self.native(self.p,self.b,'move/악의파동',face=10 if trigger=='hit' else 1)
                    actual = self.completed(self.p)
                if trigger == 'not_own_turn':
                    self.e.end_of_turn(self.p)
                    self.e.start_of_turn(self.b,initiative_count=20)
                self.rejected(lambda:TA.react(self.e,self.t,self.p,TA.uid('Clever Ruse'),actual['id'],
                    choices=['evasion','ignore_evasion']), 'missed|own.*turn|turn')

    def test_zephyr_shift_defends_actual_ranged_damage_powder_and_weather_until_next_turn_end(self):
        self.branch('비행','Celerity','Zephyr Shield')
        self.e.gm.set_position(self.q,(4,3),reason='actual equally defended unshielded comparison ally')
        self.combat(self.p)
        self.special('Zephyr Shield',action='shift')
        self.assertEqual(self.p.budget['shift'],0)
        self.e.end_of_turn(self.p)
        self.e.start_of_turn(self.b,initiative_count=20)
        before = self.q.hp
        self.native(self.b,self.q,'move/물대포')
        ordinary = before-self.q.hp
        self.next_turn(self.b)
        before = self.p.hp
        self.native(self.b,self.p,'move/물대포')
        self.assertEqual(before-self.p.hp,ordinary-10)
        actual = self.completed(self.b)['move']
        self.assertEqual(TA.accuracy(self.e,self.b,self.p,actual,{}),-1)
        self.next_turn(self.b)
        self.native(self.b,self.p,'move/버섯포자')
        self.assertNotIn('잠듦',self.p.conditions)
        self.e.gm.set_weather('hail',rounds=5,reason='actual damaging weather')
        before = self.p.hp
        self.next_turn(self.p)
        self.assertEqual(self.p.hp,before)
        self.e.end_of_turn(self.p)
        self.assertFalse(TA._buff(self.p,'ace_zephyr'))
        self.e.end_round()
        self.combat(self.p)
        self.assertLess(self.p.hp,before)
        self.valid()

    def test_zephyr_standard_only_skips_actual_flying_setup_and_interrupt_owes_standard(self):
        for action in ('standard','shift'):
            with self.subTest(action=action):
                self.branch('비행','Celerity','Zephyr Shield')
                self.e.gm.set_position(self.p,(3,2),reason='actual Fly resolution adjacent origin')
                self.e.gm.choose_learned_capability_policy(self.p,'move/공중날기','move_entry',
                    reason='actual selected printed Fly capability source')
                self.known(self.p,'move/공중날기')
                self.combat(self.p)
                self.special('Zephyr Shield',action=action)
                self.next_turn(self.p)
                hp = self.b.hp
                with patch.object(Engine,'d20',return_value=10):
                    self.e.use_setup_move_on(self.p,self.b,'move/공중날기',self.e.everyone,
                        setup_options={'path':[]} if action=='standard' else {})
                if action=='standard':
                    self.assertLess(self.b.hp,hp)
                    self.assertIsNone(self.p.setup_move)
                    self.assertEqual(self.p.move_uses['move/공중날기'],1)
                else:
                    self.assertEqual(self.b.hp,hp)
                    self.assertEqual(self.p.setup_move,'move/공중날기')
                self.valid()
        self.branch('비행','Celerity','Zephyr Shield')
        self.combat(self.b)
        trigger = {'kind':'turn','actor_id':self.b.entity_id,
            'serial':self.b.custom_conditions['combat_turn_serial'],'round':self.e.round_no}
        queued = TA.zephyr_interrupt(self.e,self.t,self.p,trigger=trigger,payment='next')
        self.e.begin_initiative_reaction(queued['window_id'],queued['order'][0])
        self.special('Zephyr Shield',action='standard')
        self.e.finish_initiative_reaction()
        self.assertIs(self.e._active_turn_actor,self.b)
        self.assertEqual(RESOURCES.pending(self.p),{'standard':1})
        self.e.end_of_turn(self.b)
        self.e.start_of_turn(self.p,initiative_count=10)
        self.assertEqual(self.p.budget['standard'],0)
        self.valid()

    def test_tornado_three_restricted_standards_and_between_shifts_share_actual_cap_and_daily_target(self):
        self.branch('비행','Celerity','Zephyr Shield','Tornado Charge')
        self.e.gm.set_position(self.p,(2,4),reason='actual open Tornado lane')
        self.e.gm.set_position(self.b,(2,5),reason='actual adjacent foe off the Tornado lane')
        self.e.gm.set_movement_capabilities(self.p,{'land':6,'sky':0,'swim':0},
            basis='base',reason='actual six-meter total turn capability')
        self.known(self.p,'move/바람일으키기','move/물대포','move/브레이브버드','move/에어슬래시')
        self.combat(self.p)
        TA.tornado(self.e,self.t,self.p)
        self.assertEqual(self.p.budget['standard'],3)
        before = self.b.hp
        # A forbidden Move cannot consume any of the restricted actions.
        self.native(self.p,self.b,'move/물대포')
        self.assertEqual((self.p.budget['standard'],self.b.hp),(3,before))
        self.native(self.p,self.b,'move/브레이브버드')  # Flying but not at-will/EOT: forbidden under Tornado Charge
        self.assertEqual(self.p.budget['standard'],3)
        self.special('Zephyr Shield',action='standard')
        first = TA.tornado_shift(self.e,self.t,self.p,[(3,4),(4,4),(5,4),(6,4)],mode='land')
        self.assertEqual(first['distance'],4)
        self.native(self.p,self.b,'move/바람일으키기')
        second = TA.tornado_shift(self.e,self.t,self.p,[(7,4),(8,4),(9,4)],mode='land')
        self.assertEqual(second['distance'],2)
        self.native(self.p,self.b,'move/에어슬래시')
        self.assertEqual((self.p.budget['standard'],self.p.pos),(0,(8,4)))
        self.next_turn(self.p)
        self.rejected(lambda:TA.tornado(self.e,self.t,self.p),'frequency|spent')
        self.valid()


if __name__ == '__main__':
    unittest.main()
