"""Actual paid three-roll choice continuation; no default secondary effect."""
from copy import copy,deepcopy
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import earned_status_choices as CHOICE
import passive_events as P
import state_codec as CODEC
import world_entities as W
import combat_timing as TIME
import condition_instances as CONDITIONS

class EarnedStatusChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=Rules(ROOT,ruleset='all')

    def fixture(self,*,target_types=('노말',),fickle_component=False):
        rules=copy(self.base);rules.rulings=deepcopy(self.base.rulings)
        engine=Engine(rules,839);engine.grid=Grid(12,8)
        common={'kind':'trainer','level':30,'size':'중형',
            'stats':{'hp':100,'atk':20,'def':15,'spa':20,'spd':15,'spe':10},
            'moves':[CHOICE.POPULATION,CHOICE.FICKLE,'move/몸통박치기'],
            'abilities':[],'feats':[],'edges':[],'classes':[],
            'skills':{'육상':3,'곡예':3,'전투':3,'집중':3},'movement':{'land':6,'power':3},
            'types':['노말'],'weight_kg':30}
        actor=Combatant(rules,dict(deepcopy(common),id='choice/user',name='choice user'))
        target=Combatant(rules,dict(deepcopy(common),id='choice/target',name='choice target',types=list(target_types)))
        for body,pos,side in ((actor,(2,2),'party'),(target,(3,2),'enemy')):
            engine.gm.add_combatant(body,pos=pos,side=side,reason='actual selected move participant')
            prepare_body(engine,body,size='중형',offsets=[(0,0)],reason='actual body')
        if fickle_component:
            # This test isolates the earned-choice component. It does not certify
            # Fickle Beam's independent unresolved historical effectiveness predicate.
            engine.rule_effect(CHOICE.FICKLE,'remove',match={'type':'type_effectiveness_override'},
                reason='GM explicitly removes the separate historical boost for this choice-component fixture')
        engine.start_round(engine.everyone);engine.start_of_turn(actor,initiative_count=30)
        return engine,actor,target

    def attack(self,engine,actor,target,faces,move=CHOICE.POPULATION):
        options={'set_damage':True}
        if move==CHOICE.FICKLE:options['aim']=(5,2)
        with patch.object(Engine,'d20',side_effect=faces):
            return engine.use_move(actor,target,move,**options)

    def pending(self,engine,actor,target,faces,move=CHOICE.POPULATION):
        before=target.hp
        with self.assertRaises(P.PassiveEventPending):
            self.attack(engine,actor,target,faces,move)
        event_id=engine._passive_pending
        self.assertIsNotNone(event_id);self.assertEqual(target.hp,before)
        self.assertEqual(actor.move_uses[move],1)
        return event_id

    def restore(self,engine,actor,target):
        restored=CODEC.load_engine(self.base,json.loads(json.dumps(CODEC.dump_engine(engine),ensure_ascii=False)))
        index=W.actor_index(restored)
        return restored,index[actor.entity_id],index[target.entity_id]

    def choose(self,engine,actor,event_id,choices):
        if 3 in choices:
            engine.rulings.answers=[row for row in engine.rulings.answers if row['key']!='earned_status_choice_unresisted']
            engine.rulings.add_answer('earned_status_choice_unresisted',
                {'mode':'positive_type_multiplier_floor_one','reason':'Explicit GM fixture: neutral floor on positive type multipliers, preserve immunity and flat DR'},
                reason='Choice-component test supplies the unresolved table interpretation')
        with patch.object(Engine,'d20',side_effect=AssertionError('paid accuracy must not reroll')):
            return engine.choose_move_status(actor,event_id,choices)

    def test_zero_one_two_three_successes_and_critical_earn_exact_budget(self):
        cases=(([1,1,1],0),([15,1,1],0),([1,15,1],0),([15,15,1],1),([15,15,15],2),
               ([20,1,1],1),([20,15,1],2),([20,15,15],3),([20,20,20],3))
        for faces,budget in cases:
            with self.subTest(faces=faces):
                engine,actor,target=self.fixture()
                if budget:
                    event_id=self.pending(engine,actor,target,faces)
                    row=engine._passive_events[event_id][CHOICE.KEY]
                    self.assertEqual(row['facts']['budget'],budget)
                    self.assertEqual(row['facts']['results'],[[face>=5,face,face==20] for face in faces])
                    self.assertNotIn('취약',target.conditions)
                    choices={1:[1],2:[1,3],3:[1,2,3]}[budget]
                    self.choose(engine,actor,event_id,choices)
                else:
                    self.attack(engine,actor,target,faces)
                    self.assertNotIn('취약',target.conditions)
                    self.assertFalse(TIME.records(target))
                self.assertIsNone(engine._passive_pending)
                self.assertEqual(actor.move_uses[CHOICE.POPULATION],1)
                self.assertTrue(engine.validate_state()['valid'])

    def test_pending_invalid_owner_budget_and_options_are_atomic_then_cold_resume_once(self):
        engine,actor,target=self.fixture()
        event_id=self.pending(engine,actor,target,[15,15,1])
        for owner,choices in ((target,[1]),(actor,[]),(actor,[1,2]),(actor,[4]),(actor,[True])):
            assert_rejected_unchanged(engine,lambda owner=owner,choices=choices:
                engine.choose_move_status(owner,event_id,choices),reason_pattern='owner|earned|legal')
        engine,actor,target=self.restore(engine,actor,target)
        paid=(actor.move_uses[CHOICE.POPULATION],deepcopy(actor.budget),len(actor._action_history))
        self.choose(engine,actor,event_id,[1])
        self.assertEqual((actor.move_uses[CHOICE.POPULATION],actor.budget,len(actor._action_history)),paid)
        self.assertIn('취약',target.conditions)
        assert_rejected_unchanged(engine,lambda:engine.choose_move_status(actor,event_id,[1]),reason_pattern='pending')
        self.restore(engine,actor,target)



    def test_real_heavy_pending_keeps_selected_reply_damage_and_registered_event(self):
        import heavy_injury_adapter as HEAVY
        engine,actor,target=self.fixture()
        engine.gm.set_injuries(target,5,reason='actual pre-existing heavy injuries')
        self.assertGreater(target.hp,0);self.assertLess(actor.injuries,5)
        event_id=self.pending(engine,actor,target,[15,15,1])
        before=target.hp
        accuracy=deepcopy(engine._passive_events[event_id][CHOICE.KEY]['facts']['results'])
        paid=(actor.move_uses[CHOICE.POPULATION],deepcopy(actor.budget),len(actor._action_history))
        with self.assertRaises(HEAVY.HeavyPending) as caught:
            self.choose(engine,actor,event_id,[1])
        heavy_id=caught.exception.event_id
        self.assertEqual(engine._heavy_pending,heavy_id)
        self.assertIn(heavy_id,engine._heavy_events)
        packet=engine._heavy_events[heavy_id]
        self.assertIs(packet['target'],target);self.assertIs(packet['attacker'],actor)
        self.assertEqual(packet['status'],'pending')
        self.assertGreater(packet['amount'],0)
        self.assertLess(target.hp,before)
        self.assertEqual(target.hp,packet['observed_after']['hp'])
        row=engine._passive_events[event_id][CHOICE.KEY]
        self.assertEqual(row['choices'],[1]);self.assertTrue(row['ready'])
        self.assertEqual(row['facts']['results'],accuracy)
        self.assertFalse(row['applications']);self.assertNotIn('취약',target.conditions)
        self.assertEqual((actor.move_uses[CHOICE.POPULATION],actor.budget,len(actor._action_history)),paid)
        self.assertIs(packet['continuation_reified'],False)
        self.assertTrue(packet['unexecuted_remainder'])
        self.assertNotIn('resolution',packet)
        with self.assertRaises(HEAVY.HeavyPending) as still_pending:
            HEAVY.ensure_clear(engine)
        self.assertEqual(still_pending.exception.event_id,heavy_id)

    def test_unresisted_interpretation_is_pending_without_gm_and_survives_cold_resume(self):
        engine,actor,target=self.fixture(target_types=('바위',))
        event_id=self.pending(engine,actor,target,[20,1,1])
        before=target.hp
        with patch.object(Engine,'d20',side_effect=AssertionError('paid accuracy must not reroll')):
            with self.assertRaises(P.PassiveEventPending):
                engine.choose_move_status(actor,event_id,[3])
        self.assertEqual(target.hp,before)
        self.assertEqual(engine._passive_events[event_id]['reason'],'earned_status_choice_unresisted_interpretation')
        self.assertIsNone(engine._passive_events[event_id][CHOICE.KEY]['unresisted'])
        engine.rulings.add_answer('earned_status_choice_unresisted',
            {'mode':'also_remove_immunity','reason':'Explicit different unsupported GM interpretation'},
            reason='Unsupported interpretation must remain pending')
        with self.assertRaises(P.PassiveEventPending):
            engine.choose_move_status(actor,event_id,[3])
        self.assertEqual(engine._passive_events[event_id]['reason'],'earned_status_choice_unresisted_unsupported')
        self.assertEqual(target.hp,before)
        engine.rulings.answers=[row for row in engine.rulings.answers if row['key']!='earned_status_choice_unresisted']
        engine,actor,target=self.restore(engine,actor,target)
        self.choose(engine,actor,event_id,[3])
        self.assertLess(target.hp,before)
        self.assertEqual(actor.move_uses[CHOICE.POPULATION],1)
        self.assertEqual(engine._passive_events[event_id][CHOICE.KEY]['unresisted']['mode'],
                         'positive_type_multiplier_floor_one')

    def test_population_unresisted_choice_changes_this_damage_without_lingering_bonus(self):
        damage=[]
        for choices in ([1],[3]):
            engine,actor,target=self.fixture(target_types=('바위',))
            before=target.hp
            event_id=self.pending(engine,actor,target,[20,1,1])
            self.choose(engine,actor,event_id,choices)
            damage.append(before-target.hp)
            if choices==[3]:
                self.assertFalse(TIME.records(target))
                self.assertEqual(CHOICE.current_multiplier(engine,actor,target,
                    engine.r.move(CHOICE.POPULATION),0.5),0.5)
        self.assertGreater(damage[1],damage[0])
        engine,actor,target=self.fixture(target_types=('고스트',))
        before=target.hp
        event_id=self.pending(engine,actor,target,[20,1,1])
        self.choose(engine,actor,event_id,[3])
        # The explicitly chosen GM mode preserves real immunity. This uses a
        # native marked occurrence, not the unmarked Move's no-op branch.
        self.assertEqual(target.hp,before)
        event=engine._passive_events[event_id]
        marked=engine._move_completions[event['completion_id']]['target_moves'][target.entity_id]
        self.assertEqual(marked[CHOICE.MARKER],event_id)
        for value,expected in ((0.0,0.0),(0.25,1.0),(0.5,1.0),(1.0,1.0),(1.5,1.5),(2.0,2.0)):
            with self.subTest(multiplier=value):
                self.assertEqual(CHOICE.current_multiplier(engine,actor,target,marked,value),expected)

    def test_selected_vulnerability_and_outgoing_resistance_expire_at_target_next_turn_end(self):
        for option in (1,2):
            with self.subTest(option=option):
                engine,actor,target=self.fixture()
                move=engine.r.move('move/몸통박치기')
                baseline=engine.roll_damage(target,actor,move,set_damage=True)
                event_id=self.pending(engine,actor,target,[15,15,1])
                self.choose(engine,actor,event_id,[option])
                if option==1:self.assertIn('취약',target.conditions)
                else:
                    self.assertEqual(CHOICE.outgoing_steps(engine,target),1)
                    self.assertLess(engine.roll_damage(target,actor,move,set_damage=True),baseline)
                engine,actor,target=self.restore(engine,actor,target)
                engine.end_of_turn(actor);engine.start_of_turn(target,initiative_count=20)
                if option==1:self.assertIn('취약',target.conditions)
                else:self.assertEqual(CHOICE.outgoing_steps(engine,target),1)
                engine.end_of_turn(target)
                self.assertNotIn('취약',target.conditions)
                self.assertEqual(CHOICE.outgoing_steps(engine,target),0)
                self.assertTrue(engine.validate_state()['valid'])


    def test_late_shared_resistance_cannot_reduce_selected_current_damage(self):
        import blessing_effects as B
        damage=[]
        for option in (1,3):
            engine,actor,target=self.fixture()
            engine.gm.set_move(target,'move/리플렉터',add=True,reason='actual known protective Move')
            engine.end_of_turn(actor);engine.start_of_turn(target,initiative_count=20)
            engine.use_move(target,target,'move/리플렉터')
            engine.end_of_turn(target);engine.end_round()
            engine.start_round(engine.everyone);engine.start_of_turn(actor,initiative_count=30)
            engine.rulings.add_answer('team_blessing',True,reason='actual beneficiary choice')
            before=target.hp
            event_id=self.pending(engine,actor,target,[20,1,1])
            self.choose(engine,actor,event_id,[option])
            damage.append(before-target.hp)
            record=B.live(target)[0]
            if option==3:
                self.assertEqual(B.remaining(record),2)
                self.assertFalse(record['decisions'])
            else:self.assertEqual(B.remaining(record),1)
            self.restore(engine,actor,target)
        self.assertGreater(damage[1],damage[0])

    def test_repeated_numeric_choice_waits_for_explicit_gm_composition_before_damage(self):
        for mode,expected in (('replace',1),('add',2)):
            with self.subTest(mode=mode):
                engine,actor,target=self.fixture();before=target.hp
                event_id=self.pending(engine,actor,target,[15,15,15])
                with self.assertRaises(P.PassiveEventPending):
                    self.choose(engine,actor,event_id,[2,2])
                self.assertEqual(target.hp,before)
                self.assertEqual(engine._passive_events[event_id]['reason'],'earned_status_choice_stacking')
                engine,actor,target=self.restore(engine,actor,target)
                engine.rulings.provider=lambda q,mode=mode:({'mode':mode,'reason':'explicit GM composition choice'}
                    if q['type']=='earned_status_choice_stacking' else None)
                self.choose(engine,actor,event_id,[2,2])
                engine.rulings.provider=None
                self.assertLess(target.hp,before)
                self.assertEqual(CHOICE.outgoing_steps(engine,target),expected)
                self.assertEqual(actor.move_uses[CHOICE.POPULATION],1)
                self.restore(engine,actor,target)

    def test_fickle_choice_component_keeps_full_round_slow_and_native_suppression(self):
        for option in (1,2):
            with self.subTest(option=option):
                engine,actor,target=self.fixture(fickle_component=True)
                event_id=self.pending(engine,actor,target,[15,15,1],CHOICE.FICKLE)
                self.assertEqual(engine._passive_events[event_id][CHOICE.KEY]['facts']['budget'],1)
                self.choose(engine,actor,event_id,[option])
                if option==1:
                    self.assertIn('둔화',target.conditions)
                    records=[r for r in TIME.records(target) if CHOICE.KEY in r]
                    self.assertEqual(records[0]['count_deadline'],(engine.round_no+1,30))
                    engine,actor,target=self.restore(engine,actor,target)
                    engine.end_of_turn(actor);engine.end_round();engine.start_round(engine.everyone)
                    engine.at_initiative_count(31);self.assertIn('둔화',target.conditions)
                    engine.at_initiative_count(30);self.assertNotIn('둔화',target.conditions)
                else:
                    records=CONDITIONS.records(target,'억압')
                    self.assertTrue(records);self.assertTrue(all(r['source']==CHOICE.FICKLE for r in records))
                    self.restore(engine,actor,target)
        engine,actor,target=self.fixture(fickle_component=True)
        self.attack(engine,actor,target,[20,1,1],CHOICE.FICKLE)
        self.assertIsNone(engine._passive_pending)
        self.assertNotIn('둔화',target.conditions);self.assertNotIn('억압',target.conditions)


    def test_substitute_keeps_selected_status_off_original_body_and_marker_cannot_retarget(self):
        import substitute as SUB
        engine,actor,target=self.fixture()
        engine.gm.set_move(target,'move/대타출동',add=True,reason='actual defensive Move')
        engine.end_of_turn(actor);engine.start_of_turn(target,initiative_count=20)
        engine.use_move(target,target,'move/대타출동')
        self.assertTrue(SUB.live(target))
        engine.end_of_turn(target);engine.end_round()
        engine.start_round(engine.everyone);engine.start_of_turn(actor,initiative_count=30)
        before=target.hp
        event_id=self.pending(engine,actor,target,[15,15,1])
        self.choose(engine,actor,event_id,[1])
        self.assertEqual(target.hp,before)
        self.assertNotIn('취약',target.conditions)
        self.assertFalse(engine._passive_events[event_id][CHOICE.KEY]['applications'])
        completion=engine._move_completions[engine._passive_events[event_id]['completion_id']]
        observed=completion['target_moves'][target.entity_id]
        with self.assertRaisesRegex(ValueError,'recipient'):
            CHOICE.current_multiplier(engine,actor,actor,observed,0.5)
        self.restore(engine,actor,target)

    def test_saved_budget_choices_and_derived_deadline_tampering_are_rejected(self):
        engine,actor,target=self.fixture()
        event_id=self.pending(engine,actor,target,[15,15,1])
        row=engine._passive_events[event_id][CHOICE.KEY]
        original=deepcopy(row['facts'])
        row['facts']['budget']=2
        with self.assertRaises(ValueError):CODEC.dump_engine(engine)
        row['facts']=original
        self.choose(engine,actor,event_id,[1])
        timed=next(r for r in TIME.records(target) if CHOICE.KEY in r)
        old=timed['turn_deadline'];timed['turn_deadline']+=1
        with self.assertRaisesRegex(ValueError,'timed choice'):CODEC.dump_engine(engine)
        timed['turn_deadline']=old
        self.restore(engine,actor,target)

    def test_unbound_handler_and_modified_multi_roll_refuse_before_game_mutation(self):
        import effects as FX
        engine,actor,target=self.fixture();before=target.hp
        result=FX.run_effects(engine,actor,target,
            [{'type':'apply_status_choice','options':['취약'],'target':'target'}],
            {'hit':True},'test/unbound-choice')
        self.assertEqual((result[0],result[1]),(0,1))
        self.assertNotIn('취약',target.conditions);self.assertEqual(target.hp,before)
        engine,actor,target=self.fixture()
        engine.rule_effect(CHOICE.POPULATION,'replace',
            effect={'type':'multi_roll','rolls':2,'hit_if_any':True,'crit_if_any_crit':True},
            match={'type':'multi_roll'},reason='unsupported source producer variation')
        assert_rejected_unchanged(engine,lambda:self.attack(engine,actor,target,[15,15]),
            reason_pattern='three|choice|reviewed')


if __name__=='__main__':
    unittest.main()
