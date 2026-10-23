"""Independent consumer, mutation and continuation checks for native defense."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_move_defense_reactions as FIXTURE
from engine import Rules,Engine
import passive_events as PASSIVE
import root_resolution as ROOT_HASH
import move_defense_reactions as DEFENSE


class IndependentMoveDefenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
    setUp=FIXTURE.MoveDefenseReactionsTests.setUp
    trainer=FIXTURE.MoveDefenseReactionsTests.trainer
    watch=FIXTURE.MoveDefenseReactionsTests.watch
    waiting=FIXTURE.MoveDefenseReactionsTests.waiting
    choose=FIXTURE.MoveDefenseReactionsTests.choose
    melee=FIXTURE.MoveDefenseReactionsTests.melee
    ranged=FIXTURE.MoveDefenseReactionsTests.ranged
    completion=FIXTURE.MoveDefenseReactionsTests.completion
    fresh=FIXTURE.MoveDefenseReactionsTests.fresh

    def test_ordered_offers_resume_same_accuracy_after_first_declines(self):
        second=self.trainer('second interceptor',(3,6))
        self.e.gm.add_combatant(second)
        self.e.watch_move_defense(self.t,[
            {'actor_id':self.r.entity_id,'source':DEFENSE.MELEE},
            {'actor_id':second.entity_id,'source':DEFENSE.MELEE}],reason='explicit ordered ally offers')
        event=self.waiting();roll=self.e.rng.getstate()
        with self.assertRaises(PASSIVE.PassiveEventPending):self.choose(event,use=False)
        self.assertEqual(self.e._passive_pending,event)
        with self.assertRaises(ValueError):self.choose(event,use=False)
        self.choose(event,use=False,reactor=second)
        self.assertEqual(self.e.rng.getstate(),roll)
        self.assertEqual(self.a.move_uses['move/막치기'],1)

    def test_attacker_faint_during_defense_wait_cancels_before_reactor_payment(self):
        import action_resources as RESOURCES
        self.watch();event=self.waiting();hp=(self.t.hp,self.r.hp)
        self.a.hp=0;self.a.conditions.add('기절')
        self.e.deliver_passive_event(event)
        self.assertEqual((self.t.hp,self.r.hp),hp)
        self.assertEqual(RESOURCES.pending(self.r),{})
        self.assertEqual(self.a.move_uses['move/막치기'],1)
        self.assertEqual(self.a._action_history,['standard'])
        self.assertIsNone(self.e._passive_pending)
        self.assertTrue(self.completion()['results'][self.t.entity_id]['cancelled'])
        self.fresh()

    def test_total_blindness_cannot_attempt_intercept_or_pay_its_cost(self):
        self.e.apply_status(self.r,'완전 실명',source='independent native status')
        self.watch();event=self.waiting();before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,options=self.melee())
        self.assertEqual(self.e.export_state(),before)
        self.choose(event,use=False)

    def test_area_pending_cold_restore_keeps_original_group_and_one_received_hit(self):
        self.r.pos=(3,4)
        self.watch();event=self.waiting('move/지진',area=True)
        targets=[c.entity_id for c in self.completion()['targets']]
        self.fresh()
        options=self.melee();options['path']=[(3,4),(3,3),(3,2)]
        self.choose(event,options=options)
        row=self.completion()
        self.assertEqual([c.entity_id for c in row['targets']],targets)
        self.assertEqual(row['phase'],'complete')
        self.assertEqual(row['results'][self.r.entity_id]['dealt'],0)
        self.assertEqual(len([ev for ev in self.e._passive_events.values()
            if ev.get('defense_parent')==event and ev['target'] is self.r]),1)
        self.fresh()

    def test_receipt_damage_mutation_rejected_by_export(self):
        self.watch();event=self.waiting();self.choose(event,options=self.melee())
        self.completion()['received'][self.r.entity_id]['dealt']+=1
        with self.assertRaises(ValueError):self.e.export_state()

    def test_aggregate_total_and_parent_result_cannot_replace_actual_recipient_sum(self):
        self.watch();event=self.waiting();self.choose(event,options=self.melee())
        row=self.completion();row['defense'][self.t.entity_id]['total']+=1
        row['results'][self.t.entity_id]['dealt']+=1
        with self.assertRaises(ValueError):self.e.export_state()

    def test_false_area_membership_cannot_be_relabelled_with_new_hash(self):
        self.r.pos=(3,4)
        self.watch();event=self.waiting('move/지진',area=True)
        options=self.melee();options['path']=[(3,4),(3,3),(3,2)]
        self.choose(event,options=options)
        row=self.completion();state=row['defense'][self.t.entity_id]
        state['recipients']=[r for r in state['recipients'] if r['actor_id']!=self.t.entity_id]
        row['received'].pop(self.t.entity_id)
        with self.assertRaises(ValueError):self.e.export_state()

    def test_forged_accuracy_trigger_cannot_create_reaction_window(self):
        import initiative_interrupts as INTERRUPTS
        self.watch();event=self.waiting();before=self.e.export_state()
        with self.assertRaises((ValueError,PASSIVE.PassiveEventPending)):
            INTERRUPTS.queue(self.e,[{'id':'forged','actor_id':self.r.entity_id,
                'source':DEFENSE.MELEE,'priority':0,'mode':'reaction','payment':'next',
                'budget':{'standard':1,'shift':1},'clock':'none'}],
                trigger={'kind':'accuracy','event_id':event})
        self.assertEqual(self.e.export_state(),before)

    def test_original_accuracy_target_cannot_be_changed_even_with_new_fact_hash(self):
        self.watch();event=self.waiting();state=self.completion()['defense'][self.t.entity_id]
        state['facts']['original_id']=self.r.entity_id
        state['fingerprint']=ROOT_HASH.fingerprint(state['facts'])
        with self.assertRaises(ValueError):self.e.export_state()

    def test_actual_recipient_listener_wait_restores_and_finishes_parent_once(self):
        from hashlib import sha256
        document={'schema':1,'id':'independent/received-choice','variants':[{
            'rule_id':'move/할퀴기',
            'source':{'file':'input/db/moves.csv','sha256':sha256((ROOT/'input/db/moves.csv').read_bytes()).hexdigest()},
            'inputs':{'hit':{'authority':'context','type':'boolean','question':'Actual received hit'},
                      'choice':{'authority':'gm','type':'boolean','question':'Apply authored result'}},
            'when':{'op':'eq','left':{'$input':'hit'},'right':True},
            'values':{'effects':[{'type':'stage_change','stat':'spa','delta':1,'target':'self'}]}}]}
        key=self.e.subscribe_source_policy(self.a,'received-choice',document,inputs={'hit':'hit'})
        self.watch();parent=self.waiting()
        with self.assertRaises(PASSIVE.PassiveEventPending):self.choose(parent,options=self.melee())
        child=self.e._passive_pending
        self.assertNotEqual(parent,child)
        self.assertIs(self.e._passive_events[child]['target'],self.r)
        hp=self.r.hp;roll=self.e.rng.getstate()
        self.fresh()
        self.e.choose_passive_event(child,self.a,key,{'decisions':{'choice':{'value':True,'reason':'explicit recipient continuation'}}})
        self.assertEqual(self.r.hp,hp);self.assertEqual(self.a.stages['spa'],1)
        self.assertEqual(self.e.rng.getstate(),roll)
        self.assertEqual(self.completion()['phase'],'complete')
        self.assertIsNone(self.e._passive_pending)
        self.assertEqual(self.e.deliver_passive_event(child),'already_delivered')
        self.fresh()

    def test_already_hit_earlier_area_target_cannot_receive_the_same_move_again(self):
        self.r.pos=(3,4);self.watch()
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move_on(self.a,self.t,'move/지진',[self.a,self.r,self.t])
        event=self.e._passive_pending;hp=self.r.hp
        self.assertLess(hp,self.r.max_hp)
        self.assertEqual(self.completion()['targets'],[self.r,self.t])
        options=self.melee();options['path']=[(3,4),(3,3),(3,2)]
        self.choose(event,options=options)
        self.assertEqual(self.r.hp,hp)
        self.assertEqual(self.completion()['phase'],'complete')
        self.fresh()


if __name__=='__main__':unittest.main()
