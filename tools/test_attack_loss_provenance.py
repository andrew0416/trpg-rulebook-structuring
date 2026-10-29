"""Actual attacks and passive loss share balances without sharing wake authority."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'engine') not in sys.path:sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import state_fields as F
import turn as TURN
import effects as FX
import temporary_hp as TEMP
import attack_damage_history as HISTORY
from state_codec import load_engine


class AttackLossTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')

    def setUp(self):
        self.e=Engine(self.r,6);self.e.everyone=self.e.gm.everyone=[]
        self.a=self.actor('attacker');self.b=self.actor('sleeper')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

    def actor(self,name,kind='pokemon'):
        c=Combatant(self.r,dict(name=name,kind=kind,level=20,stats={s:30 for s in F.STATS},
            types=['노말'],moves=['move/스피드스타','move/분노의앞니','move/용의분노','move/꿈먹기'],
            abilities=[],movement={'land':4}))
        c.side='party' if name=='attacker' else 'foes';self.e.everyone.append(c);return c

    def sleep(self):
        self.assertTrue(self.e.apply_status(self.b,'잠듦'))
        self.assertTrue(self.e.apply_status(self.b,'악몽'))

    def loss_state(self):
        return deepcopy((self.b.hp,self.b.temp_hp,self.b.injuries,self.b.conditions,
                         self.b.custom_conditions,HISTORY.records(self.b)))

    def test_actual_damage_wakes_with_real_or_only_temporary_hp_loss(self):
        for shield in (0,1000):
            with self.subTest(shield=shield):
                self.setUp();self.sleep();TEMP.grant(self.e,self.b,shield)
                hp=self.b.hp
                self.e.use_move_on(self.a,self.b,'move/스피드스타',self.e.everyone)
                self.assertNotIn('잠듦',self.b.conditions);self.assertNotIn('악몽',self.b.conditions)
                self.assertGreater(HISTORY.amount(HISTORY.records(self.b)[-1]),0)
                if shield:self.assertEqual(self.b.hp,hp);self.assertLess(self.b.temp_hp,shield)
                else:self.assertLess(self.b.hp,hp)
                self.assertEqual(self.a.budget['standard'],0)

    def test_native_direct_loss_preserves_class_amount_and_one_actual_application(self):
        for move,expected in (('move/분노의앞니',None),('move/용의분노',15)):
            with self.subTest(move=move):
                self.setUp();self.sleep();before=self.b.hp
                expected=before//2 if expected is None else expected
                TEMP.grant(self.e,self.b,5)
                self.e.use_move_on(self.a,self.b,move,self.e.everyone)
                self.assertEqual((self.b.hp,self.b.temp_hp),(before-expected+5,0))
                self.assertNotIn('잠듦',self.b.conditions)
                rows=HISTORY.records(self.b);self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['receipt']['source'],move)
                self.assertEqual(rows[0]['receipt']['damage_class'],self.r.move(move)['class'])
                self.assertEqual(HISTORY.amount(rows[0]),expected)
                actual=[r for r in self.e._effect_dispatch_receipts.values() if 'attack_hp_loss' in r]
                self.assertEqual(len(actual),1);self.assertEqual(actual[0]['status'],'completed')
                self.assertEqual(self.a.budget['standard'],0)

    def test_awake_dream_eater_target_rejects_both_native_entries_before_payment(self):
        for routed in (False,True):
            with self.subTest(routed=routed):
                self.setUp()
                def state():
                    return deepcopy((self.a.budget,self.a.move_uses,self.a.hp,self.b.hp,
                        self.a.temp_hp,self.b.temp_hp,self.a.conditions,self.b.conditions,
                        self.a.custom_conditions,self.b.custom_conditions,
                        getattr(self.a,'_action_history',None),self.e.rng.getstate(),
                        getattr(self.e,'_effect_dispatch_receipts',{})))
                before=state()
                with patch.object(self.e,'d20',side_effect=AssertionError('ineligible target must not roll')):
                    result=(self.e.use_move_on(self.a,self.b,'move/꿈먹기',self.e.everyone)
                            if routed else self.e.use_move(self.a,self.b,'move/꿈먹기'))
                self.assertEqual(result,0);self.assertEqual(state(),before)
                self.assertTrue(any('잠든 대상에게만' in line for line in self.e.log_lines))

    def test_dream_eater_source_exception_keeps_sleep_after_actual_damage(self):
        self.sleep();before=self.b.hp
        self.e.use_move_on(self.a,self.b,'move/꿈먹기',self.e.everyone)
        self.assertLess(self.b.hp,before);self.assertIn('잠듦',self.b.conditions)
        self.assertIn('악몽',self.b.conditions)

    def test_passive_and_unbound_effect_labels_do_not_become_attack_provenance(self):
        self.sleep();TEMP.grant(self.e,self.b,40);hp=self.b.hp
        self.e.lose_hp(self.b,3,source='독')
        effect={'type':'hp_loss','value':4,'target':'target'}
        result=FX.run_effects(self.e,self.a,self.b,[effect],
            {'attacker':self.a,'target':self.b,'hit':True,'move':self.r.move('move/용의분노')},'move/용의분노')
        self.assertEqual(result[1],0);self.assertIn('잠듦',self.b.conditions)
        self.assertEqual((self.b.hp,self.b.temp_hp),(hp,33));self.assertEqual(HISTORY.records(self.b),[])

    def test_miss_and_zero_native_loss_do_not_wake_or_forge_positive_loss(self):
        self.sleep();self.e.rng.seed(31)  # first actual d20 is a natural 1
        self.e.use_move_on(self.a,self.b,'move/분노의앞니',self.e.everyone)
        self.assertIn('잠듦',self.b.conditions);self.assertEqual(HISTORY.records(self.b),[])
        self.setUp();self.sleep();self.b.damage_cap={'value':0}
        self.e.use_move_on(self.a,self.b,'move/스피드스타',self.e.everyone)
        self.assertIn('잠듦',self.b.conditions)
        self.assertEqual(HISTORY.amount(HISTORY.records(self.b)[-1]),0)

    def test_actual_poison_turn_end_loss_does_not_wake(self):
        self.sleep();self.assertTrue(self.e.apply_status(self.b,'독'))
        hp=self.b.hp
        self.e.start_round([self.b,self.a]);self.e.start_of_turn(self.b)
        self.e.rng.seed(31)
        self.e.end_of_turn(self.b)
        self.assertLess(self.b.hp,hp);self.assertIn('잠듦',self.b.conditions)
        self.assertEqual(HISTORY.records(self.b),[])

    def test_gm_and_json_restore_preserve_actual_loss_history_without_reapplying(self):
        self.sleep();self.e.use_move_on(self.a,self.b,'move/용의분노',self.e.everyone)
        state=self.loss_state();saved=self.e.gm.snapshot()
        loaded=load_engine(self.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        b=next(c for c in loaded.everyone if c.entity_id==self.b.entity_id)
        self.assertEqual((b.hp,b.temp_hp,b.conditions),(self.b.hp,self.b.temp_hp,self.b.conditions))
        self.assertEqual(HISTORY.records(b),HISTORY.records(self.b))
        self.e.lose_hp(self.b,7);self.e.gm.restore(saved)
        self.assertEqual(self.loss_state(),state)

    def test_late_wake_failure_rolls_back_damage_and_loss_with_its_history(self):
        original=Engine.cure_status
        def fail(e,c,condition):
            result=original(e,c,condition)
            if condition=='잠듦':raise ValueError('late wake failure')
            return result
        for move in ('move/스피드스타','move/용의분노'):
            with self.subTest(move=move):
                self.setUp();self.sleep();TEMP.grant(self.e,self.b,7);before=self.loss_state()
                with patch.object(Engine,'cure_status',fail):
                    if move=='move/스피드스타':
                        with self.assertRaisesRegex(ValueError,'late wake failure'):
                            self.e.use_move_on(self.a,self.b,move,self.e.everyone)
                    else:
                        self.e.use_move_on(self.a,self.b,move,self.e.everyone)
                        self.assertTrue(any(r['status']=='execution_failed' for r in self.e._effect_dispatch_receipts.values()))
                self.assertEqual(self.loss_state(),before)
                self.assertFalse(hasattr(self.e,'_attack_loss_effect_scopes'))


if __name__=='__main__':unittest.main()
