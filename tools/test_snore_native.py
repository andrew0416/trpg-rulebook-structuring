"""Selected Snore owns one sleeping native Burst activation, never a raw label."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
from native_scenario_fixture import prepare_body
import action_lifecycle as ACTION
import effects as FX
import move_completion as COMPLETE
import turn as TURN

SNORE='move/코골기'
TACKLE='move/몸통박치기'


class SnoreNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset='core')

    def scene(self,*,asleep=True,learned=True):
        self.e=Engine(self.rules,seed=583)
        self.e.grid=Grid(10,10)
        stats={'hp':80,'atk':10,'def':10,'spa':10,'spd':10,'spe':10}
        for name,position,side in (('a',(3,3),'party'),('b',(4,3),'foe'),
                                   ('c',(3,4),'party'),('outside',(6,3),'foe')):
            moves=[TACKLE]+([SNORE] if learned and name=='a' else [])
            actor=Combatant(self.rules,build_trainer(self.rules,'snore-'+name,30,
                stats,moves=moves,abilities=[],pos=position,side=side))
            self.e.gm.add_combatant(actor,reason='actual Snore Burst participant')
            prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed complete one-cell body')
            setattr(self,name,actor)
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a,initiative_count=20)
        if asleep:
            self.e.apply_status(self.a,'잠듦',source='move/수면가루',applied_by=self.b)
            self.assertIn('잠듦',self.a.conditions)
        self.assertFalse(getattr(self.e,'_execution_trace_enabled',False))

    def native(self,face=15,*,everyone=None):
        with patch.object(self.e,'d20',return_value=face):
            return self.e.use_move_on(self.a,self.b,SNORE,
                self.e.everyone if everyone is None else everyone,aim=self.a.pos,set_damage=True)

    def gameplay(self):
        # Refusal logs are observable diagnostics, not spent action/HP/RNG state.
        actors=(self.a,self.b,self.c,self.outside)
        memo={id(self.e):self.e,id(self.e.r):self.e.r,**{id(a):a for a in actors}}
        def optional(owner,name):
            # Non-active actors need not have a budget/history yet. Preserve
            # absence separately from None or an empty newly allocated value.
            return (hasattr(owner,name),getattr(owner,name,None))
        return deepcopy((self.e.rng.getstate(),self.e.round_no,self.e.elapsed_seconds,
            self.e._active_turn_actor,
            [(a.spec,a.hp,a.temp_hp,optional(a,'budget'),a.move_uses,a.conditions,a.custom_conditions,
              a.stages,optional(a,'_action_history')) for a in actors],
            optional(self.e,'_move_completions'),optional(self.e,'_passive_pending'),
            optional(self.e,'_effect_dispatch_sequence'),optional(self.e,'_native_action_resolutions')),memo)

    def completion(self):
        rows=[row for row in getattr(self.e,'_move_completions',{}).values()
              if row['actor'] is self.a and row['move_id']==SNORE]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['phase'],'complete')
        return rows[0]

    def test_asleep_native_burst_hits_all_actual_recipients_once_and_flinches_at_fifteen_without_tracing(self):
        self.scene()
        before={a.entity_id:a.hp for a in self.e.everyone}
        observed=[]
        def actual_accuracy():
            # Even a callback inside the real paid Snore cannot lend its
            # admission scope to a second unrelated Sleeping Standard action.
            self.assertTrue(getattr(self.e,'_move_activation_scopes',()))
            self.assertEqual(self.e._event_use_scopes[-1]['move_id'],SNORE)
            fake=dict(self.e.r.move(SNORE),_actual_targets=(self.b,self.c))
            self.assertFalse(ACTION.status_permission(self.e,self.a,'standard',_native_move=fake))
            observed.append(SNORE)
            return 15
        with patch.object(self.e,'d20',side_effect=actual_accuracy):
            damage=self.e.use_move_on(self.a,self.b,SNORE,self.e.everyone,
                aim=self.a.pos,set_damage=True)
        self.assertGreater(damage,0)
        self.assertEqual(observed,[SNORE])
        row=self.completion()
        self.assertEqual({a.entity_id for a in COMPLETE.actual_recipients(row)},
                         {self.b.entity_id,self.c.entity_id})
        for recipient in (self.b,self.c):
            self.assertTrue(COMPLETE.recipient_result(row,recipient)['hit'])
            self.assertLess(recipient.hp,before[recipient.entity_id])
            self.assertIn('풀죽음',recipient.conditions)
        self.assertEqual((self.a.hp,self.outside.hp),
                         (before[self.a.entity_id],before[self.outside.entity_id]))
        self.assertNotIn('풀죽음',self.a.conditions)
        self.assertNotIn('풀죽음',self.outside.conditions)
        self.assertIn('잠듦',self.a.conditions)
        receipts=[entry for entry in self.e._effect_dispatch_receipts.values()
                  if entry['source_id']==SNORE and entry['effect'].get('type')=='apply_status']
        self.assertEqual(len(receipts),2)
        self.assertTrue(all(entry['status']=='completed' and entry['effect']['on_natural_roll_min']==15
                            for entry in receipts))
        self.assertEqual((self.a.move_uses[SNORE],self.a.budget['standard']),(1,0))
        self.assertEqual(self.a._action_history,['standard'])
        self.assertFalse(getattr(self.e,'_execution_trace_enabled',False))
        report=self.e.validate_state()
        self.assertTrue(report['valid'],report['issues'])

    def test_below_threshold_and_miss_do_not_flinch_but_pay_one_actual_use(self):
        for face in (14,1):
            with self.subTest(face=face):
                self.scene()
                before=[a.hp for a in (self.b,self.c)]
                result=self.native(face)
                row=self.completion()
                self.assertEqual(bool(result),face==14)
                self.assertEqual([COMPLETE.recipient_result(row,a)['hit'] for a in (self.b,self.c)],
                                 [face==14,face==14])
                self.assertFalse(any('풀죽음' in a.conditions for a in self.e.everyone))
                if face==1:self.assertEqual([self.b.hp,self.c.hp],before)
                self.assertEqual((self.a.move_uses[SNORE],self.a.budget['standard']),(1,0))

    def test_awake_and_unlearned_snore_refuse_before_payment_or_rng(self):
        for asleep,learned in ((False,True),(True,False)):
            with self.subTest(asleep=asleep,learned=learned):
                self.scene(asleep=asleep,learned=learned)
                before=self.gameplay()
                self.assertEqual(self.native(),0)
                self.assertEqual(self.gameplay(),before)
                self.assertNotIn(SNORE,self.a.move_uses)

    def test_plain_labels_frames_and_ordinary_moves_cannot_bypass_sleep(self):
        self.scene()
        fake=dict(self.e.r.move(SNORE),_actual_targets=(self.b,self.c))
        before=self.gameplay()
        self.assertFalse(ACTION.status_permission(self.e,self.a,'standard',_native_move=fake))
        self.assertFalse(TURN.spend(self.e,self.a,'standard','move/코골기',_native_move=fake))
        with ACTION.resolution(self.e,self.a,SNORE,kind='move'):
            self.assertFalse(ACTION.status_permission(self.e,self.a,'standard',_native_move=fake))
        self.assertEqual(self.e.use_move(self.a,self.b,TACKLE,set_damage=True),0)
        self.assertEqual(self.gameplay(),before)

    def test_area_completeness_and_changed_selected_payload_reject_before_cost(self):
        self.scene()
        before=self.gameplay()
        with self.assertRaisesRegex(ValueError,'complete native target activation'):
            self.e.use_move(self.a,self.b,SNORE,set_damage=True)
        self.assertEqual(self.gameplay(),before)
        with self.assertRaisesRegex(ValueError,'omitted'):
            self.native(everyone=[self.a,self.b,self.outside])
        self.assertEqual(self.gameplay(),before)
        original=self.e.r.move_mech
        def changed(mid):
            mechanics,confidence=original(mid)
            mechanics=deepcopy(mechanics)
            if mid==SNORE:mechanics['effects_exec'][0]['on_natural_roll_min']=1
            return mechanics,confidence
        with patch.object(self.e.r,'move_mech',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'unchanged reviewed selected source'):
                self.native()
        self.assertEqual(self.gameplay(),before)

    def test_actual_ground_move_sync_and_acquired_earthroil_pay_shift_not_standard(self):
        import test_book_type_ace_reactions as FIX
        import type_ace as ACE
        case=FIX.TypeAceReactionTests()
        case.rules=self.rules
        case.family('땅','Mold the Earth','Earthroil')
        case.acquire(ACE.SYNC,branch='땅')
        case.known(case.p,SNORE)
        before_points=case.p.spec['tutor_points'];before_time=case.e.elapsed_seconds
        synced=ACE.sync(case.e,case.t,case.p,'땅',seconds=60,
            application_id='snore-ground-sync',move_id=SNORE,new_name='대지의 코골기',
            effect_decision={'mode':'preserve','reason':'preserve printed Sleep and Flinch effects','effects_exec':None},
            feasibility_review='Same printed area, accuracy, category and effects; selected Ground type only.',
            power_review='No damage base or natural Flinch threshold increase.',
            reason='actual completed Ground Move Sync')
        self.assertEqual((synced['synced_type'],case.p.spec['tutor_points'],case.e.elapsed_seconds),
                         ('땅',before_points-1,before_time+60))
        case.e.gm.set_position(case.b,(3,2),reason='actual adjacent Earthroil recipient')
        case.combat(case.p)
        case.e.apply_status(case.p,'잠듦',source='move/수면가루',applied_by=case.b)
        self.assertFalse(getattr(case.e,'_execution_trace_enabled',False))
        with patch.object(case.e,'d20',return_value=15):
            damage=ACE.use_move(case.e,case.t,case.p,case.b,SNORE,
                feature=ACE.uid('Earthroil'),choice='burst',aim=case.p.pos,set_damage=True)
        self.assertGreater(damage,0)
        row=case.completed(case.p,SNORE)
        self.assertEqual((row['move']['type'],row['move']['_class_move_range']['shape']),('땅','burst'))
        self.assertEqual((case.p.budget['shift'],case.p.budget['standard'],case.p.move_uses[SNORE]),(0,1,1))
        self.assertEqual(case.p._action_history,['shift'])
        self.assertIn('잠듦',case.p.conditions)
        self.assertIn('풀죽음',case.b.conditions)
        case.valid()
    def test_naked_source_hit_flags_cannot_install_snore_flinch(self):
        self.scene()
        effect=self.e.r.move_mech(SNORE)[0]['effects_exec'][0]
        before=(self.e.rng.getstate(),dict(self.a.budget),dict(self.a.move_uses),self.b.hp,self.c.hp)
        result=FX.run_effects(self.e,self.a,self.b,[effect],
            {'engine':self.e,'attacker':self.a,'target':self.b,'hit':True,'nat':20,
             'move':self.e.r.move(SNORE)},SNORE)
        self.assertEqual(result,(0,1))
        self.assertFalse(any('풀죽음' in a.conditions for a in self.e.everyone))
        self.assertEqual((self.e.rng.getstate(),self.a.budget,self.a.move_uses,self.b.hp,self.c.hp),before)
        self.assertTrue(any(entry['source_id']==SNORE and entry['status']=='execution_failed'
                            for entry in self.e._effect_dispatch_receipts.values()))


if __name__=='__main__':unittest.main()