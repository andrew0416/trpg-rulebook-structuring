"""Duelist's completed Move consumers use native recipients, including Intercept."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_book_duelist_momentum as FIXTURE
from engine import Combatant
from builder import build_trainer
import duelist as D
import move_completion as COMPLETE
import move_defense_reactions as DEFENSE
import passive_events as PASSIVE
import combat_timing as TIME
import frequency as FREQUENCY
import state_codec as CODEC
import initiative_interrupts as INTERRUPTS
import action_lifecycle as ACTION


class DuelistActualRecipientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIXTURE.DuelistMomentumTests.setUpClass()
        cls.rules=FIXTURE.DuelistMomentumTests.rules

    def fixture(self,*,tag_actual=False,manual=False,directed=False,types=None,blocked=False):
        f=FIXTURE.DuelistMomentumTests();f.rules=self.rules
        f.setup(directed=directed,enemy_types=['물'])
        c=Combatant(self.rules,build_trainer(self.rules,'actual Duelist interceptor',20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),
            extra={'side':'foe','pos':(3,3),'types':list(types or ['노말']),
                   'skills':{'육상':5},'movement':{'land':8},'movement_basis':'current','abilities':[]}))
        f.e.gm.add_combatant(c)
        if blocked:f.e.gm.set_ability(c,'불가사의부적',reason='native actual recipient cannot be hit')
        if tag_actual:
            f.start(f.a);f.e.manual_feat(f.a,D.CLASS,c)
        if manual:
            f.rounds(3);f.manual(2)
        return f,c

    def intercept(self,f,c,*,manual=False,faces=(6,6,6,6,6),seize=None,natural=20,restore=False):
        e,p,t=f.e,f.p,f.t
        if seize is None:f.start(p)
        before=D.momentum(p)
        before_hp=p.hp
        f.seize_budget=deepcopy(getattr(p,'budget',None))
        if seize is not None:
            self.assertIsNone(e.round_start_seconds)
            self.assertFalse(ACTION.ordinary_permission(e,p))
            self.assertFalse(ACTION.ordinary_permission(e,c))
        e.watch_move_defense(t,[{'actor_id':c.entity_id,'source':DEFENSE.MELEE}],
            reason='actual Duelist completion recipient')
        with patch.object(type(e),'d20',new=lambda e:natural):
            with self.assertRaises(PASSIVE.PassiveEventPending) as pending:
                if seize is not None:
                    e.seize_the_moment(f.a,p,event_id=seize,move='move/몸통박치기',target=t,set_damage=True)
                elif manual:e.use_move_on(p,t,'move/불태우기',e.everyone,set_damage=True)
                else:e.use_move(p,t,'move/몸통박치기',set_damage=True)
        event=e._passive_pending
        self.assertEqual(event,pending.exception.event_id)
        self.assertIn(event,e._passive_events)
        if seize is not None:
            self.assertTrue(ACTION.ordinary_permission(e,p))
            self.assertFalse(ACTION.ordinary_permission(e,c))
            self.assertEqual(p.hp,before_hp)
            self.assertEqual(D.momentum(p),1)
            self.assertEqual(FREQUENCY.state(f.a)['activations'][D.SEIZE]['used'],1)
            self.assertEqual(FREQUENCY.state(p)['activations'][D.SEIZE]['used'],1)
            self.assertEqual(p.move_uses['move/몸통박치기'],1)
        if restore:
            f.e=CODEC.load_engine(self.rules,f.snapshot())
            index={actor.entity_id:actor for actor in f.e.everyone}
            f.a,f.p,f.t,c=(index[actor.entity_id] for actor in (f.a,f.p,f.t,c))
            e,p,t=f.e,f.p,f.t
            self.assertEqual(e._passive_pending,event)
            f.valid()
        f.interceptor=c
        with patch.object(type(e),'d20',new=lambda e:20):
            e.choose_move_defense(event,c,use=True,options={
                'path':[(3,3),(3,2),(3,1),(2,1),(2,0)],'skill':'육상','mode':'land',
                'shove_destination':[3,0],'roll_options':{'fixed':list(faces)}},
                reason='actual paid melee Intercept')
        row=list(e._move_completions.values())[-1]
        self.assertEqual(row['phase'],'complete');self.assertEqual(row['targets'],[t])
        self.assertIsNone(e._passive_pending)
        return row,D.momentum(p)-before

    def completed_seize(self,f,row,overflow):
        gain=next(r for r in f.p.spec[D.KEY]['gains'] if r['id']==overflow)
        self.assertEqual(gain['status'],'completed')
        self.assertEqual(FREQUENCY.state(f.a)['activations'][D.SEIZE]['used'],1)
        self.assertEqual(FREQUENCY.state(f.p)['activations'][D.SEIZE]['used'],1)
        self.assertEqual(f.p.move_uses['move/몸통박치기'],1)
        self.assertEqual(getattr(f.p,'budget',None),f.seize_budget)
        self.assertFalse(getattr(f.e,INTERRUPTS.KEY)['frames'])
        self.assertFalse(getattr(f.e,INTERRUPTS.KEY)['loans'])
        self.assertIsNone(f.e._active_turn_actor)
        self.assertFalse(getattr(f.p,'pending_action_loss',{}))
        self.assertFalse(f.e.pending_duelist_interrupts(f.a))
        self.assertEqual(row['duelist_interrupt'],overflow)
        self.assertEqual(D.momentum(f.p),1)
        self.assertFalse(ACTION.ordinary_permission(f.e,f.p))
        self.assertFalse(ACTION.ordinary_permission(f.e,f.interceptor))
        return gain

    def actual_hit(self,f,c,row):
        self.assertEqual(set(row['received']),{c.entity_id})
        self.assertEqual(COMPLETE.actual_recipients(row),[c])
        self.assertIsNone(COMPLETE.recipient_result(row,f.t))
        outcome=DEFENSE.received_result(row,c)
        self.assertTrue(outcome['hit']);self.assertFalse(outcome['cancelled'])
        self.assertFalse(outcome['hit_prevented'])
        self.assertEqual(f.t.hp,f.t.max_hp)
        return outcome

    def test_tagged_original_does_not_gain_from_untagged_actual_interceptor(self):
        f,c=self.fixture();row,delta=self.intercept(f,c)
        self.actual_hit(f,c,row);self.assertEqual(delta,0)
        self.assertFalse(any(r['origin']['kind']=='tag_hit' for r in f.p.spec.get(D.KEY,{}).get('gains',[])))
        f.valid()

    def test_tagged_actual_interceptor_gains_once_and_refresh_does_not_repeat(self):
        f,c=self.fixture(tag_actual=True);row,delta=self.intercept(f,c)
        self.actual_hit(f,c,row);self.assertEqual(delta,1)
        gains=[r for r in f.p.spec[D.KEY]['gains'] if r['origin']['kind']=='tag_hit']
        self.assertEqual([r['origin']['target'] for r in gains],[c.entity_id])
        before=D.momentum(f.p);COMPLETE.refresh(f.e);COMPLETE.refresh(f.e)
        self.assertEqual(D.momentum(f.p),before);f.valid()

    def test_failed_intercept_keeps_original_tagged_hit(self):
        f,c=self.fixture();row,delta=self.intercept(f,c,faces=(1,1,1,1,1))
        self.assertEqual(COMPLETE.actual_recipients(row),[f.t])
        self.assertTrue(COMPLETE.recipient_result(row,f.t)['hit'])
        self.assertIsNone(COMPLETE.recipient_result(row,c))
        self.assertLess(f.t.hp,f.t.max_hp);self.assertEqual(c.hp,c.max_hp)
        self.assertEqual(delta,1);f.valid()

    def test_tagged_actual_interceptor_cannot_hit_awards_no_momentum(self):
        f,c=self.fixture(tag_actual=True,blocked=True);row,delta=self.intercept(f,c)
        outcome=COMPLETE.recipient_result(row,c)
        self.assertFalse(outcome['hit']);self.assertTrue(outcome['hit_prevented'])
        self.assertEqual(c.hp,c.max_hp);self.assertEqual(f.t.hp,f.t.max_hp)
        self.assertEqual(delta,0);f.valid()

    def test_zero_damage_type_immunity_is_still_actual_tagged_hit(self):
        f,c=self.fixture(tag_actual=True,types=['고스트']);row,delta=self.intercept(f,c)
        outcome=self.actual_hit(f,c,row)
        self.assertEqual(outcome['dealt'],0);self.assertEqual(c.hp,c.max_hp)
        self.assertEqual(delta,1);f.valid()

    def test_manual_two_statuses_follow_actual_interceptor_not_original(self):
        f,c=self.fixture(manual=True);row,_=self.intercept(f,c,manual=True)
        self.actual_hit(f,c,row)
        self.assertIn('취약',c.conditions);self.assertNotIn('취약',f.t.conditions)
        self.assertTrue(any(r.get('initiative_zero') for r in TIME.records(c)))
        self.assertFalse(any(r.get('initiative_zero') for r in TIME.records(f.t)))
        self.assertFalse(any(r.get('duelist_mode')==2 for r in TIME.records(f.p)))
        f.valid()

    def test_manual_two_cannot_hit_applies_neither_status(self):
        f,c=self.fixture(manual=True,blocked=True);row,_=self.intercept(f,c,manual=True)
        outcome=COMPLETE.recipient_result(row,c)
        self.assertFalse(outcome['hit']);self.assertTrue(outcome['hit_prevented'])
        for target in (f.t,c):
            self.assertNotIn('취약',target.conditions)
            self.assertFalse(any(r.get('initiative_zero') for r in TIME.records(target)))
        self.assertFalse(any(r.get('duelist_mode')==2 for r in TIME.records(f.p)))
        f.valid()

    def test_directed_focus_observes_super_effective_actual_interceptor(self):
        f,c=self.fixture(manual=True,directed=True,types=['풀'])
        row,delta=self.intercept(f,c,manual=True);self.actual_hit(f,c,row)
        self.assertLess(c.hp,c.max_hp);self.assertEqual(delta,1)
        gains=[r for r in f.p.spec[D.KEY]['gains'] if r['origin']['kind']=='super_effective']
        self.assertEqual(len(gains),1);self.assertEqual(gains[0]['origin']['completion'],row['id'])
        before=D.momentum(f.p);COMPLETE.refresh(f.e)
        self.assertEqual(D.momentum(f.p),before);f.valid()

    def test_type_methodology_uses_resisted_actual_recipient_and_spends_two(self):
        f,c=self.fixture(tag_actual=True,manual=True,types=['물'])
        f.answer('type_methodology',True)
        row,delta=self.intercept(f,c,manual=True);self.actual_hit(f,c,row)
        self.assertEqual(delta,-1)
        self.assertEqual(FREQUENCY.state(f.a)['activations'][D.TYPE]['used'],1)
        f.valid()

    def test_seize_already_critical_cannot_heal_before_actual_hit(self):
        f,c=self.fixture(blocked=True);f.rounds(7,closed=True)
        f.e.lose_hp(f.p,f.p.base_max_hp//2,source=D.SEIZE)
        before=f.p.hp;overflow=f.e.pending_duelist_interrupts(f.a)[0]['id']
        row,_=self.intercept(f,c,seize=overflow)
        self.assertTrue(COMPLETE.recipient_result(row,c)['hit_prevented'])
        self.assertEqual(c.hp,c.max_hp);self.assertEqual(f.t.hp,f.t.max_hp)
        self.assertEqual(f.p.hp,before)
        gain=self.completed_seize(f,row,overflow)
        self.assertFalse(gain.get('heal_applied',False));f.valid()

    def test_seize_pending_native_intercept_preserves_auto_critical_payment_and_frame(self):
        f,c=self.fixture();f.rounds(7,closed=True)
        f.e.lose_hp(f.p,f.p.base_max_hp//2,source=D.SEIZE)
        before=f.p.hp;overflow=f.e.pending_duelist_interrupts(f.a)[0]['id']
        row,_=self.intercept(f,c,seize=overflow,natural=10)
        outcome=self.actual_hit(f,c,row)
        self.assertLess(c.hp,c.max_hp)
        self.assertTrue(f.e._passive_events[outcome['child_event']]['critical'])
        self.assertEqual(f.p.hp,before)
        gain=self.completed_seize(f,row,overflow)
        self.assertFalse(gain.get('heal_applied',False));f.valid()

    def test_seize_pending_restore_heals_once_after_actual_critical_hit(self):
        import life
        f,c=self.fixture();f.rounds(7,closed=True)
        f.e.lose_hp(f.p,f.p.base_max_hp//2,source=D.SEIZE)
        before=f.p.hp;overflow=f.e.pending_duelist_interrupts(f.a)[0]['id']
        with patch.object(life,'heal',wraps=life.heal) as healing:
            row,_=self.intercept(f,c,seize=overflow,restore=True)
        c=f.interceptor;outcome=self.actual_hit(f,c,row)
        self.assertTrue(f.e._passive_events[outcome['child_event']]['critical'])
        self.assertEqual(healing.call_count,1)
        self.assertEqual(healing.call_args.args[2],f.p.base_max_hp//2)
        self.assertEqual(f.p.hp,min(f.p.max_hp,before+f.p.base_max_hp//2))
        gain=self.completed_seize(f,row,overflow)
        self.assertTrue(gain['heal_applied']);self.assertEqual(gain['healed'],f.p.hp-before)
        snapshot=f.snapshot();COMPLETE.refresh(f.e);COMPLETE.refresh(f.e)
        self.assertEqual(f.snapshot(),snapshot)
        f.reject(lambda:f.e.choose_move_defense(outcome['event_id'],c,use=True,
            reason='completed native defense cannot be delivered twice'))
        f.reject(lambda:f.e.seize_the_moment(f.a,f.p,event_id=overflow,
            move='move/몸통박치기',target=f.t,set_damage=True))
        f.valid()


if __name__=='__main__':unittest.main()
