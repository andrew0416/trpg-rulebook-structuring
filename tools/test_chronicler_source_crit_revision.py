"""C1/C3: real source choices, native area reactions and defensive critical controls."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import test_book_chronicler_acquisition as FIXTURE
import chronicler as CH
import move_defense_reactions as DEFENSE
import passive_events as PASSIVE
import movement_actions as MOVEMENT
import action_resources as RESOURCES
import ability_transitions as ABILITIES
import blessing_effects as BLESSINGS


class ChroniclerSourceCritTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles={name:Rules(ROOT,ruleset=name) for name in ('core','playtest','all')}

    setup=FIXTURE.ChroniclerAcquisitionTests.setup
    add=FIXTURE.ChroniclerAcquisitionTests.add
    acquire=FIXTURE.ChroniclerAcquisitionTests.acquire
    whole=FIXTURE.ChroniclerAcquisitionTests.whole
    rejected=FIXTURE.ChroniclerAcquisitionTests.rejected
    valid=FIXTURE.ChroniclerAcquisitionTests.valid
    restore=FIXTURE.ChroniclerAcquisitionTests.restore
    combat=FIXTURE.ChroniclerAcquisitionTests.combat
    next_turn=FIXTURE.ChroniclerAcquisitionTests.next_turn
    use=FIXTURE.ChroniclerAcquisitionTests.use
    record=FIXTURE.ChroniclerAcquisitionTests.record
    archive_subject=FIXTURE.ChroniclerAcquisitionTests.archive_subject
    archive_place=FIXTURE.ChroniclerAcquisitionTests.archive_place
    communication=FIXTURE.ChroniclerAcquisitionTests.communication

    def setUp(self):
        self.select_profile('core')

    def select_profile(self,name):
        self.rules=self.profiles[name]
        previous=self.rules.rulings
        self.rules.rulings=deepcopy(previous)
        self.addCleanup(setattr,self.rules,'rulings',previous)
        self.setup()

    def travel(self,*,choice='통찰',profile='core'):
        if self.rules.ruleset.name!=profile:self.select_profile(profile)
        self.t.spec[CH.CHOICES]={CH.CLASS:'travel'}
        self.t.spec[CH.TRAVEL_ABILITY]=choice
        receipt=self.acquire();self.acquire(CH.PARTY)
        self.archive_place('actual recorded valley')
        CH.observe_place(self.e,self.p,'actual recorded valley',reason='actual owned Pokemon in the recorded valley')
        return receipt

    def area_wait(self,*,playtest=False,attacker=None,move='move/지진'):
        attacker=attacker or self.p
        if playtest:self.t.pos=(1,5)
        self.e.gm.set_move(attacker,move,reason='actual known area Move')
        self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,
            'source':CH.PERCEPTION_PLAYTEST if playtest else CH.PERCEPTION_ABILITY}],reason='actual owned area avoidance')
        self.combat(attacker,count=25)
        hp=self.t.hp
        with patch.object(Engine,'d20',return_value=20),self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move_on(attacker,self.t,move,self.e.everyone,set_damage=True)
        self.assertEqual(self.t.hp,hp)
        return self.e._passive_pending

    def choose(self,event,path=None,*,use=True):
        return self.e.choose_move_defense(event,self.t,use=use,
            options=None if not use else {'path':path,'mode':'land'},reason='actual Perception route choice')

    def route(self):
        return [(1,y) for y in range(1,7)]

    def critical(self,target=None,*,face=20,move='move/전광석화'):
        result=self.e.accuracy_check(self.p,target or self.b,self.e.r.move(move),fixed_roll=face)
        self.assertTrue(result[0]);return result[2]

    def profiling(self):
        self.whole();self.archive_subject(self.b,'pokemon','actual armored profile')
        self.e.gm.set_ability(self.b,'조가비갑옷/전투무장',reason='actual Defensive Shell Armor')
        self.communication();self.combat(self.t)
        CH.profile_order(self.e,self.t,self.p)
        self.e.end_of_turn(self.t);self.e.start_of_turn(self.p,initiative_count=20)

    def test_bilingual_travel_choice_uses_core_perception_and_party_grants_without_frisk(self):
        receipt=self.travel()
        self.assertEqual(receipt['snapshot']['travel_ability'],'통찰')
        for actor in (self.t,self.p):
            self.assertIn('감지',actor.abilities)
            self.assertTrue(ABILITIES.active(actor,'감지'))
            self.assertNotIn('통찰 [Playtest]',actor.abilities)
            self.assertEqual(actor.evasion_mod,0)
        self.assertEqual(CH.perception_definition(self.rules,CH.PERCEPTION_ABILITY)['action'],'shift')
        self.restore();self.valid()
        self.assertEqual(CH.owned_archives(self.t)['travel']['travel_ability'],'통찰')
        CH.observe_place(self.e,self.p,None,reason='actual Pokemon leaves recorded place')
        self.assertNotIn('감지',self.p.abilities);self.assertIn('감지',self.t.abilities)
        self.assertIn('actual recorded valley',CH.archived(self.t,'travel'))

    def test_playtest_choice_uses_actual_perception_evasion_and_preserves_source_cost(self):
        self.travel(profile='playtest')
        for actor in (self.t,self.p):
            self.assertIn('감지 [Playtest]',actor.abilities)
            self.assertEqual(actor.evasion_mod,1)
            self.assertTrue(ABILITIES.active(actor,'감지 [Playtest]'))
        self.assertEqual(CH.perception_definition(self.rules,CH.PERCEPTION_PLAYTEST)['action'],'free')
        self.restore();self.valid()

    def test_all_profile_allows_both_explicit_perception_sources_and_excludes_frisk(self):
        self.select_profile('all')
        self.assertEqual(CH._travel_ability(self.rules,CH.PERCEPTION_ABILITY),'감지')
        self.assertEqual(CH._travel_ability(self.rules,CH.PERCEPTION_PLAYTEST),'감지 [Playtest]')
        self.assertEqual(CH._travel_ability(self.rules,'Perception'),'감지')
        for wrong in ('통찰 [Playtest]','통찰 [썬문]','Frisk'):
            with self.subTest(wrong=wrong),self.assertRaisesRegex(ValueError,'Keen Eye or Perception'):
                CH._travel_ability(self.rules,wrong)
        with self.assertRaises(ValueError):CH._travel_ability(self.profiles['core'],CH.PERCEPTION_PLAYTEST)

    def test_core_actual_ally_area_interrupt_moves_full_shift_and_pays_next_shift_once(self):
        self.travel();history=list(self.t._action_history);event=self.area_wait();hp=self.t.hp
        self.restore();self.choose(event,self.route())
        self.assertEqual(self.t.pos,(1,6));self.assertEqual(self.t.hp,hp)
        self.assertEqual(self.t._action_history,history+['shift'])
        self.assertEqual(RESOURCES.pending(self.t),{'shift':1})
        self.assertIs(self.e._active_turn_actor,self.p);self.assertIsNone(self.e._passive_pending)
        self.restore();self.valid()
        self.assertEqual(RESOURCES.pending(self.t),{'shift':1})
        self.e.end_of_turn(self.p);self.e.end_round();self.combat(self.t)
        self.assertEqual(self.t.budget['shift'],0);self.assertEqual(RESOURCES.pending(self.t),{})
        self.restore();self.valid()

    def test_playtest_actual_ally_area_disengages_one_metre_free_without_opportunity_attack(self):
        self.travel(profile='playtest')
        self.c=self.add('adjacent actual enemy','pokemon',(2,4),side='foe',species='피카츄',speed=11)
        history=list(self.t._action_history);event=self.area_wait(playtest=True);hp=self.t.hp
        self.restore();self.choose(event,[(1,5),(1,6)])
        self.assertEqual(self.t.pos,(1,6));self.assertEqual(self.t.hp,hp)
        self.assertEqual(self.t._action_history,history+['free']);self.assertEqual(RESOURCES.pending(self.t),{})
        self.assertFalse(self.c.aoo_used)
        self.assertIs(self.e._active_turn_actor,self.p);self.assertIsNone(self.e._passive_pending)
        self.restore();self.valid()

    def test_invalid_area_route_and_playtest_long_shift_refuse_before_action_or_rng(self):
        self.travel();event=self.area_wait();hp=self.t.hp;before=deepcopy(self.e.export_state())
        with self.assertRaisesRegex(ValueError,'complete body'):
            self.choose(event,[(1,1),(1,2)])
        self.assertEqual(self.e.export_state(),before)
        self.choose(event,use=False);self.assertLess(self.t.hp,hp)
        self.assertEqual(RESOURCES.pending(self.t),{})
        self.select_profile('playtest');self.travel(profile='playtest');event=self.area_wait(playtest=True)
        before=deepcopy(self.e.export_state())
        with self.assertRaisesRegex(ValueError,'one-metre Disengage'):
            self.choose(event,[(1,5),(1,6),(1,7)])
        self.assertEqual(self.e.export_state(),before);self.choose(event,use=False)

    def test_enemy_area_and_ally_targeted_hit_cannot_supply_perception_trigger(self):
        for attacker_name,move in (('b','move/지진'),('p','move/물대포')):
            with self.subTest(attacker=attacker_name,move=move):
                self.setup();self.travel();attacker=getattr(self,attacker_name)
                self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,
                    'source':CH.PERCEPTION_ABILITY}],reason='wait for an actual ally area trigger')
                watch=deepcopy(self.t.spec[DEFENSE.WATCH]);history=list(self.t._action_history)
                self.combat(attacker,count=25);hp=self.t.hp
                self.use(attacker,self.t,move,face=20)
                self.assertIsNone(self.e._passive_pending);self.assertLess(self.t.hp,hp)
                self.assertEqual(attacker._action_history,['standard']);self.assertEqual(attacker.budget['standard'],0)
                self.assertEqual(self.t.pos,(1,1));self.assertEqual(self.t._action_history,history)
                self.assertEqual(RESOURCES.pending(self.t),{});self.assertEqual(self.t.spec[DEFENSE.WATCH],watch)
                self.next_turn(self.p,count=25)
                self.e.gm.set_move(self.p,'move/지진',reason='actual later qualifying ally area attack')
                with patch.object(Engine,'d20',return_value=20),self.assertRaises(PASSIVE.PassiveEventPending):
                    self.e.use_move_on(self.p,self.t,'move/지진',self.e.everyone,set_damage=True)
                self.choose(self.e._passive_pending,use=False);self.restore();self.valid()

    def test_mixed_watch_keeps_intercept_offer_and_retains_untriggered_perception(self):
        self.travel()
        self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,'source':CH.PERCEPTION_ABILITY},
            {'actor_id':self.p.entity_id,'source':DEFENSE.RANGED}],reason='actual mixed source offers')
        history=list(self.t._action_history);self.combat(self.b,count=25);hp=self.t.hp
        self.e.gm.set_move(self.b,'move/물대포',reason='actual enemy targeted attack')
        with patch.object(Engine,'d20',return_value=20),self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move_on(self.b,self.t,'move/물대포',self.e.everyone,set_damage=True)
        event=self.e._passive_pending
        self.assertEqual(DEFENSE._defense(self.e,self.e._passive_events[event])['facts']['watch']['requests'],
            [{'actor_id':self.p.entity_id,'source':DEFENSE.RANGED}])
        self.assertEqual(self.t.spec[DEFENSE.WATCH]['requests'],
            [{'actor_id':self.t.entity_id,'source':CH.PERCEPTION_ABILITY}])
        self.e.choose_move_defense(event,self.p,use=False,reason='actual ally declines Intercept')
        self.assertIsNone(self.e._passive_pending);self.assertLess(self.t.hp,hp)
        self.assertEqual(self.t._action_history,history);self.assertEqual(RESOURCES.pending(self.t),{})
        self.assertEqual(self.t.spec[DEFENSE.WATCH]['requests'],
            [{'actor_id':self.t.entity_id,'source':CH.PERCEPTION_ABILITY}])
        self.restore();self.valid()

    def test_core_status_area_can_shift_but_playtest_requires_a_damaging_attack(self):
        self.travel();event=self.area_wait(move='move/목화포자')
        self.choose(event,[(1,1),(0,1)])
        self.assertEqual(self.t.pos,(0,1));self.assertEqual(RESOURCES.pending(self.t),{'shift':1})
        self.assertEqual(self.t.stages['spe'],0)
        self.select_profile('playtest');self.travel(profile='playtest')
        self.e.gm.set_move(self.p,'move/목화포자',reason='actual known nondamaging area Move')
        self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,'source':CH.PERCEPTION_PLAYTEST}],
            reason='Playtest has a damaging-only trigger')
        self.combat(self.p,count=25)
        with patch.object(Engine,'d20',return_value=20):
            self.e.use_move_on(self.p,self.t,'move/목화포자',self.e.everyone,set_damage=True)
        self.assertIsNone(self.e._passive_pending);self.assertEqual(self.t.pos,(1,1))
        self.assertEqual(RESOURCES.pending(self.t),{});self.assertLess(self.t.stages['spe'],0)

    def test_core_paid_movement_prefix_cold_restores_without_second_shift_or_accuracy(self):
        self.travel();self.b.pos=(10,10);history=list(self.t._action_history)
        event=self.area_wait();original=MOVEMENT.departure
        def block(e,actor,destination,height,**options):
            result=original(e,actor,destination,height,**options)
            if actor.entity_id==self.t.entity_id and destination==(1,3):e.grid.blocking.add(destination)
            return result
        with patch.object(MOVEMENT,'departure',side_effect=block),self.assertRaises(PASSIVE.PassiveEventPending):
            self.choose(event,self.route())
        self.assertEqual(self.t.pos,(1,2));self.assertEqual(self.t._action_history,history+['shift'])
        self.assertEqual(RESOURCES.pending(self.t),{'shift':1})
        self.restore();self.e.grid.blocking.remove((1,3));rng=self.e.rng.getstate()
        self.e.deliver_passive_event(event)
        self.assertEqual(self.t.pos,(1,6));self.assertEqual(self.t._action_history,history+['shift'])
        self.assertEqual(RESOURCES.pending(self.t),{'shift':1});self.assertEqual(self.e.rng.getstate(),rng)
        self.restore();self.valid()

    def test_suppressed_travel_perception_is_unavailable_and_place_history_is_retained(self):
        self.travel();self.e.gm.set_move(self.b,'move/위액',reason='actual known suppression Move')
        self.e.gm.choose_ability_transition(self.b,self.t,'move/위액',ability='감지',reason='actual selected Perception suppression')
        self.combat(self.b,count=20);self.use(self.b,self.t,'move/위액',face=20)
        self.assertFalse(ABILITIES.active(self.t,'감지'))
        self.rejected(lambda:self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,
            'source':CH.PERCEPTION_ABILITY}],reason='suppressed source'),'actual owned ability')
        self.assertIn('actual recorded valley',CH.archived(self.t,'travel'));self.restore();self.valid()

    def test_profiled_native_critical_ignores_shell_only_for_archived_target_next_turn(self):
        self.profiling()
        self.c=self.add('unarchived armored foe','pokemon',(5,2),side='foe',species='피카츄',
            abilities=['조가비갑옷/전투무장'],speed=11)
        self.assertTrue(self.critical());self.assertFalse(self.critical(face=19));self.assertFalse(self.critical(self.c))
        self.restore();self.assertTrue(self.critical())
        with patch.object(Engine,'roll_damage',autospec=True,side_effect=Engine.roll_damage) as damage:
            self.use(self.p,self.b,'move/전광석화',face=20)
        self.assertTrue(damage.call_args.kwargs.get('crit',damage.call_args.args[4] if len(damage.call_args.args)>4 else False))
        self.e.end_of_turn(self.p);self.e.end_round();self.combat(self.p,count=20)
        self.assertFalse(self.critical());self.valid()

    def test_actual_mold_breaker_critical_bypass_is_selected_active_and_enemy_only(self):
        self.e.gm.set_ability(self.b,'조가비갑옷/전투무장',reason='actual Defensive Shell Armor')
        self.e.gm.set_ability(self.t,'조가비갑옷/전투무장',reason='actual same-side Defensive Shell Armor')
        self.combat(self.p,count=20);self.assertFalse(self.critical())
        self.e.gm.set_ability(self.p,'틀깨기',reason='actual native Mold Breaker source')
        self.assertTrue(self.critical());self.assertFalse(self.critical(self.t))
        self.e.end_of_turn(self.p);self.e.start_of_turn(self.b,initiative_count=10)
        self.e.gm.set_move(self.b,'move/위액',reason='actual known suppression Move')
        self.e.gm.choose_ability_transition(self.b,self.p,'move/위액',ability='틀깨기',reason='actual native bypass-source suppression')
        self.use(self.b,self.p,'move/위액',face=20)
        self.assertFalse(self.critical());self.restore();self.valid()

    def test_same_native_mold_breaker_owner_reaches_levitate_but_keeps_type_immunity(self):
        self.e.gm.set_ability(self.p,'틀깨기',reason='actual native Mold Breaker')
        self.e.gm.set_ability(self.b,'부유',reason='actual selected Levitate')
        self.e.gm.set_move(self.p,'move/진흙뿌리기',reason='actual known Ground attack')
        self.combat(self.p,count=20);hp=self.b.hp
        self.use(self.p,self.b,'move/진흙뿌리기',face=20);self.assertLess(self.b.hp,hp)
        self.c=self.add('actual Ghost foe','pokemon',(5,2),side='foe',species='고오스',types=['고스트'],speed=11)
        self.next_turn(self.p,count=20);hp=self.c.hp
        self.use(self.p,self.c,'move/전광석화',face=20);self.assertEqual(self.c.hp,hp)
        self.restore();self.valid()

    def test_selected_playtest_defensive_bypass_variants_keep_their_actual_move_type_limit(self):
        self.select_profile('playtest')
        for ability,move in (('ability/터보블레이즈-playtest','move/불꽃세례'),
                             ('ability/터보블레이즈-playtest-2','move/불꽃세례'),
                             ('ability/테라볼티지-playtest','move/전기쇼크'),
                             ('ability/테라볼티지-playtest-2','move/전기쇼크')):
            with self.subTest(ability=ability):
                self.setup()
                self.e.gm.set_ability(self.p,ability,reason='actual selected typed defensive bypass')
                self.assertEqual(ABILITIES.ability_id(self.e.r,ability),ability)
                self.assertIn(ability,ABILITIES.known(self.p))
                self.e.gm.set_ability(self.b,'조가비갑옷/전투무장',reason='actual Defensive Shell Armor')
                self.e.gm.set_move(self.p,move,reason='actual known matching attack')
                self.combat(self.p,count=20)
                self.assertTrue(self.critical(move=move))
                self.assertFalse(self.critical(move='move/전광석화'))
                with patch.object(Engine,'roll_damage',autospec=True,side_effect=Engine.roll_damage) as damage:
                    self.use(self.p,self.b,move,face=20)
                self.assertTrue(damage.call_args.kwargs.get('crit',damage.call_args.args[4] if len(damage.call_args.args)>4 else False))
                self.restore();self.valid()
                self.assertTrue(self.critical(move=move))
                self.assertFalse(self.critical(move='move/전광석화'))

    def test_ordinary_and_suppressed_shell_critical_controls_preserve_source_identity(self):
        self.e.gm.set_ability(self.b,'조가비갑옷/전투무장',reason='actual Defensive Shell Armor')
        self.combat(self.p,count=20);self.assertFalse(self.critical())
        self.e.gm.set_move(self.p,'move/위액',reason='actual known suppression Move')
        self.e.gm.choose_ability_transition(self.p,self.b,'move/위액',ability='조가비갑옷/전투무장',reason='actual selected defensive suppression')
        self.use(self.p,self.b,'move/위액',face=20)
        self.assertTrue(self.critical());self.assertIn('조가비갑옷/전투무장',self.b.spec['abilities'])
        self.restore();self.valid()

    def test_mold_breaker_does_not_bypass_actual_lucky_chant_nonability_guard(self):
        self.e.gm.set_ability(self.p,'틀깨기',reason='actual native Mold Breaker')
        self.e.gm.set_ability(self.b,'조가비갑옷/전투무장',reason='actual Defensive Shell Armor')
        self.e.gm.set_move(self.b,'move/주술',reason='actual known Lucky Chant')
        self.combat(self.b,count=20);self.use(self.b,self.b,'move/주술',face=20)
        guard=next(row for row in BLESSINGS.live(self.b) if row['source']=='move/주술')
        remaining=BLESSINGS.remaining(guard)
        self.rules.rulings.add_answer('team_blessing',True,reason='actual beneficiary accepts critical guard')
        self.e.end_of_turn(self.b);self.e.end_round();self.combat(self.p,count=20)
        self.assertFalse(self.critical());self.assertEqual(BLESSINGS.remaining(guard),remaining-1)
        self.assertTrue(CH.defensive_ignored(self.e,self.p,self.b));self.restore();self.valid()


if __name__=='__main__':unittest.main()
