"""Independent native routing, cancellation, and authority checks."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from grid import Grid
import passive_events as PASSIVE
import state_grants as G
import ability_interrupt_choices as CHOICES
import tera_shell as TS


class AbilityInterruptChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.e=Engine(self.rules,530);self.e.grid=Grid(20,20)
        self.a=self.actor('attacker',(2,2),'opponent',[])
        self.t=self.actor('original recipient',(3,2),'party',['테라셸'])
        self.r=self.actor('interceptor',(3,4),'party',['테라셸'])
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

    def actor(self,name,pos,side,abilities):
        actor=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',30,
            name=name,moves=['move/물대포','move/지진','move/몸통박치기','move/위액'],
            extra={'abilities':abilities,'types':['풀','독'],'pos':pos,
                'side':side,'size':'중형','loyalty':6}))
        self.e.gm.add_combatant(actor);return actor

    def watch(self,actor):
        self.e.watch_ability_interrupt(actor,TS.SOURCE,reason='native recipient review')

    def waiting(self,*,defense=False,area=False):
        self.watch(self.t)
        if defense:
            self.watch(self.r)
            self.e.watch_move_defense(self.t,[{'actor_id':self.r.entity_id,
                'source':'maneuver/근접-가로채기'}],reason='actual Intercept then ability choice')
        with self.assertRaises(PASSIVE.PassiveEventPending):
            if area:self.e.use_move_on(self.a,self.t,'move/지진',self.e.everyone)
            else:self.e.use_move(self.a,self.t,'move/물대포',set_damage=True)
        return self.e._passive_pending

    def intercept(self,event):
        count=self.e._prepare_skill_roll(self.r,'육상')[-1]['dice_count']
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.choose_move_defense(event,self.r,use=True,
                options={'path':[(3,4),(3,3),(3,2)],'skill':'육상','mode':'land',
                    'shove_destination':[4,2],'roll_options':{'fixed':[6]*count}},
                reason='actual successful interception')

    def choose(self,event,owner=None,*,use=True,chosen='물'):
        return self.e.choose_ability_interrupt(event,owner or self.t,use=use,
            options={'chosen_type':chosen} if use else None,reason='actual source choice')

    def fresh(self):
        ids=[a.entity_id for a in (self.a,self.t,self.r)]
        self.e=Engine.import_state(Rules(ROOT,ruleset='core'),
            json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        index={a.entity_id:a for a in self.e.everyone}
        self.a,self.t,self.r=[index[i] for i in ids]

    def test_interception_offers_only_actual_recipient_then_restores_and_resumes_once(self):
        event=self.waiting(defense=True);hp=self.t.hp,self.r.hp
        self.intercept(event)
        self.assertEqual((self.t.hp,self.r.hp),hp)
        row=self.e._passive_events[event][CHOICES.KEY]
        self.assertEqual(row['offers'],[{'owner_id':self.r.entity_id,'source':TS.SOURCE}])
        before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event,self.t)
        self.assertEqual(self.e.export_state(),before)
        self.fresh();self.choose(event,self.r)
        self.assertEqual(self.t.hp,hp[0]);self.assertLess(self.r.hp,hp[1])
        self.assertEqual(self.r.types,['물']);self.assertEqual(self.t.types,['풀','독'])
        self.assertEqual(self.r._action_history,['full','free'])
        self.assertEqual(self.a.move_uses['move/물대포'],1)
        self.assertIsNone(self.e._passive_pending);self.fresh()

    def test_area_two_actual_recipients_keep_separate_choices_and_single_damage(self):
        event=self.waiting(defense=True,area=True);hp=self.t.hp,self.r.hp
        self.intercept(event)
        with self.assertRaises(PASSIVE.PassiveEventPending):self.choose(event,self.t,chosen='풀')
        self.assertEqual((self.t.hp,self.r.hp),hp)
        self.fresh();self.choose(event,self.r,use=False)
        self.assertLess(self.t.hp,hp[0]);self.assertLess(self.r.hp,hp[1])
        self.assertEqual(self.t.types,['풀']);self.assertEqual(self.r.types,['풀','독'])
        self.assertEqual(self.t._action_history,['free']);self.assertEqual(self.r._action_history,['full'])
        self.assertEqual(self.a.move_uses['move/지진'],1)
        completion=next(iter(self.e._move_completions.values()))
        self.assertEqual(completion['results'][self.r.entity_id]['dealt'],0)
        self.assertIsNone(self.e._passive_pending);self.fresh()

    def test_source_withdrawn_while_waiting_rejects_use_but_allows_decline(self):
        event=self.waiting();G.replace_baseline(self.e,self.t,'abilities',[])
        before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event)
        self.assertEqual(self.e.export_state(),before)
        self.choose(event,use=False);self.assertIsNone(self.e._passive_pending)
        self.assertEqual(getattr(self.t,'_action_history',[]),[])

    def test_native_pending_attacker_faint_cancels_without_choice_or_damage(self):
        event=self.waiting();hp=self.t.hp
        self.a.hp=0;self.e.check_fainted(self.a)
        self.e.deliver_passive_event(event)
        self.assertEqual(self.t.hp,hp);self.assertEqual(self.t.types,['풀','독'])
        self.assertIsNone(self.e._passive_pending)
        self.assertEqual(self.e._passive_events[event][CHOICES.KEY]['phase'],'cancelled')
        self.fresh()

    def test_attacker_faint_after_intercept_before_choice_preserves_cost_but_no_damage(self):
        event=self.waiting(defense=True);self.intercept(event);hp=self.t.hp,self.r.hp
        self.a.hp=0;self.e.check_fainted(self.a)
        self.e.deliver_passive_event(event)
        self.assertEqual((self.t.hp,self.r.hp),hp)
        self.assertEqual(self.r._action_history,['full'])
        self.assertIsNone(self.e._passive_pending)
        self.assertEqual(self.e._passive_events[event][CHOICES.KEY]['phase'],'cancelled')
        self.fresh()

    def test_next_owner_turn_resets_action_history_but_preserves_activation_receipt(self):
        event=self.waiting();self.choose(event)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=19)
        self.assertEqual(self.t._action_history,[])
        self.fresh();self.assertEqual(self.t.types,['물'])
        self.assertEqual(self.e._passive_events[event][CHOICES.KEY]['attempts'][0]['payment']['actions'],['free'])

    def test_forged_offer_and_paid_receipt_are_rejected_by_world_validation(self):
        event=self.waiting();row=self.e._passive_events[event][CHOICES.KEY]
        offers=deepcopy(row['offers']);row['offers'][0]['owner_id']=self.r.entity_id
        with self.assertRaises(ValueError):self.e.export_state()
        row['offers']=offers;self.choose(event)
        row=self.e._passive_events[event][CHOICES.KEY]
        row['attempts'][0]['payment']['actions']=['standard']
        with self.assertRaises(ValueError):self.e.export_state()

    def test_completed_plan_and_decision_must_still_match_native_move_and_owner(self):
        import root_resolution as HASH
        event=self.waiting();self.choose(event)
        row=self.e._passive_events[event][CHOICES.KEY]
        row['decisions']['0']['options']['chosen_type']='풀'
        with self.assertRaises(ValueError):self.e.export_state()
        row['decisions']['0']['options']['chosen_type']='물'
        attempt=row['attempts'][0];attempt['plan']['move']['id']='move/다른기술'
        attempt['plan_fingerprint']=HASH.fingerprint(attempt['plan'])
        self.t.spec[TS.KEY][attempt['plan']['grant_key']]=deepcopy(attempt['plan'])
        with self.assertRaises(ValueError):self.e.export_state()

    def test_status_move_hit_can_trigger_before_its_ability_suppression_effect(self):
        import ability_transitions as ABILITIES
        self.e.gm.choose_ability_transition(self.a,self.t,'move/위액',ability='테라셸',
            reason='actual selected source suppression')
        self.watch(self.t);hp=self.t.hp
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move(self.a,self.t,'move/위액')
        event=self.e._passive_pending
        self.assertTrue(ABILITIES.active(self.t,TS.SOURCE))
        self.choose(event,chosen='독')
        self.assertEqual(self.t.hp,hp);self.assertEqual(self.t.types,['독'])
        self.assertFalse(ABILITIES.active(self.t,TS.SOURCE))
        self.assertEqual(self.t._action_history,['free']);self.fresh()

    def test_dodge_miss_removes_recipient_offer_without_spending_shell_frequency(self):
        G.replace_baseline(self.e,self.t,'abilities',['회피','테라셸'])
        self.watch(self.t)
        self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,'source':'ability/회피'}],
            reason='Dodge before actual recipient ability choice')
        hp=self.t.hp
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move(self.a,self.t,'move/물대포',set_damage=True)
        event=self.e._passive_pending
        self.e.choose_move_defense(event,self.t,use=True,options={},reason='actual Dodge')
        self.assertIsNone(self.e._passive_pending)
        self.assertEqual(self.t.hp,hp);self.assertNotIn(TS.KEY,self.t.spec)
        self.assertEqual(self.e._passive_events[event][CHOICES.KEY]['offers'],[])
        self.assertEqual(self.t._action_history,['free'])
        self.assertNotIn(TS.SOURCE,self.t.spec['frequency_state']['activations'])
        self.fresh()


if __name__=='__main__':unittest.main()
