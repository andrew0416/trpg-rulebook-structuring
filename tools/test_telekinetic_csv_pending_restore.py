"""Actual CSV Psyshock paid wait and completion-owned Overload obligation."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import test_telekinetic_csv as CSV
from engine import Engine
import action_points as AP
import passive_events as PASSIVE
import state_codec as CODEC
import telekinetic as TK
import weapon_actions as WEAPONS


class CsvPsyshockContinuationTests(unittest.TestCase):
    setUpClass=classmethod(CSV.CSVTests.setUpClass.__func__)
    setUp=CSV.CSVTests.setUp
    family=CSV.CSVTests.family

    def watch_defense(self):
        f=self.f
        f.e.gm.set_move(f.b,'move/판별',reason='actually learned native Detect defense')
        f.e.watch_move_defense(f.b,[{'actor_id':f.b.entity_id,'source':'move/판별'}],
            reason='actual target may use its known Detect against the incoming area hit')

    def test_actual_defense_wait_cold_resume_preserves_csv_area_and_one_native_payment(self):
        f=self.f;self.family(TK.OVERLOAD)
        f.e.gm.set_position(f.c,(6,3),reason='second actual Psyshock area recipient')
        f.begin();self.watch_defense()
        ap=AP.available(f.a);hp=(f.b.hp,f.c.hp)
        with patch.object(Engine,'d20',return_value=18) as accuracy_roll:
            with self.assertRaises(PASSIVE.PassiveEventPending):
                f.e.use_telekinetic_move(f.a,f.b,TK.PSYSHOCK,overload=True,aim=(6,2))
            event_id=f.e._passive_pending
            self.assertIn(event_id,f.e._passive_events)
            self.assertEqual((f.a.budget['standard'],f.a.budget['swift'],AP.available(f.a)),(0,0,ap-1))
            self.assertEqual(f.a.move_uses[TK.PSYSHOCK],1)
            self.assertEqual((f.b.hp,f.c.hp),hp)
            self.assertEqual(accuracy_roll.call_count,1)
            f.restore()
            self.assertTrue(TK.local_csv(f.a,TK.OVERLOAD))
            f.e.choose_move_defense(event_id,f.b,use=False,reason='actual Detect owner declines this defense')
            self.assertIsNone(f.e._passive_pending)
            self.assertEqual(accuracy_roll.call_count,1)
        rows=[row for row in f.e._move_completions.values()
              if row['actor'] is f.a and row['move_id']==TK.PSYSHOCK]
        self.assertTrue(rows);self.assertTrue(all(row['phase']=='complete' for row in rows))
        self.assertEqual({target.entity_id for row in rows for target in row['targets']},
                         {f.b.entity_id,f.c.entity_id})
        self.assertTrue(all(WEAPONS.range_spec(f.e,row['move'],f.a)['origin']==4 and
                            WEAPONS.range_spec(f.e,row['move'],f.a)['size']==2 for row in rows))
        self.assertLess(f.b.hp,hp[0]);self.assertLess(f.c.hp,hp[1])
        self.assertEqual((f.a.budget['standard'],f.a.budget['swift'],AP.available(f.a)),(0,0,ap-1))
        self.assertEqual(f.a.move_uses[TK.PSYSHOCK],1)
        f.restore();before=deepcopy(CODEC.dump_engine(f.e))
        self.assertEqual(f.e.deliver_passive_event(event_id),'already_delivered')
        self.assertEqual(CODEC.dump_engine(f.e),before)
        f.valid()

    def test_actual_pending_pays_once_and_rejects_saved_source_choice_or_payment_binding_changes(self):
        f=self.f;self.family(TK.OVERLOAD)
        f.e.gm.set_position(f.c,(6,3),reason='actual second area recipient')
        f.begin();self.watch_defense()
        with patch.object(Engine,'d20',return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                f.e.use_telekinetic_move(f.a,f.b,TK.PSYSHOCK,overload=True,aim=(6,2))
        original=CODEC.dump_engine(f.e)
        fields={'move_id','move_source','acquisition','choice','payment'}
        for field,value in (('ap',0),('ap',True),('acquisition','not-an-actual-acquisition'),('choice',None),('turn',None)):
            with self.subTest(field=field):
                payload=deepcopy(original)
                binding,=[node['items'] for node in payload['nodes'].values()
                           if node['kind']=='dict' and all(type(pair[0])is str for pair in node['items'])
                           and {pair[0] for pair in node['items']}==fields]
                if field=='ap':
                    ref=dict(binding)['payment']['$ref']
                    payment=payload['nodes'][ref]['items']
                    next(pair for pair in payment if pair[0]=='ap')[1]=value
                elif field=='choice':
                    ref=dict(binding)['choice']['$ref']
                    choice=payload['nodes'][ref]['items']
                    next(pair for pair in choice if pair[0]=='overload')[1]=False
                elif field=='turn':
                    actor,=[node for node in payload['nodes'].values() if node['kind']=='actor' and node['entity_id']==f.a.entity_id]
                    attrs=dict(payload['nodes'][actor['attrs']['$ref']]['items'])
                    conditions=payload['nodes'][attrs['custom_conditions']['$ref']]['items']
                    serial=next(pair for pair in conditions if pair[0]=='combat_turn_serial');serial[1]+=1
                else:next(pair for pair in binding if pair[0]==field)[1]=value
                before=deepcopy(payload)
                with self.assertRaises(CODEC.StateCodecError):CODEC.load_engine(f.rules,payload)
                self.assertEqual(payload,before)
                self.assertEqual(CODEC.dump_engine(f.e),original)
        row=f.e._move_completions[f.e._passive_events[f.e._passive_pending]['completion_id']]
        f.a.spec['telekinetic_move_choice']=deepcopy(row['telekinetic_overload']['choice'])
        try:
            with self.assertRaisesRegex(ValueError,'actual native Move'):
                TK.begin_move(f.e,f.a,f.b,row['move'],row['id'])
        finally:f.a.spec.pop('telekinetic_move_choice')
        self.assertEqual(CODEC.dump_engine(f.e),original)

    def test_book_psychic_supported_waits_restore_actual_push_and_original_overload_cost(self):
        import test_wish_recycle_native_continuation as CHOICES
        f=self.f
        for wait_kind in ('defense','listener'):
            with self.subTest(wait_kind=wait_kind):
                f.setup();f.family(TK.OVERLOAD);f.begin()
                if wait_kind=='defense':self.watch_defense()
                else:listener=CHOICES.NativeContinuationTests.wait_listener(f,f.a)
                before_ap=AP.available(f.a);before_hp=f.b.hp;before_pos=tuple(f.b.pos)
                with patch.object(Engine,'d20',return_value=18):
                    with self.assertRaises(PASSIVE.PassiveEventPending):
                        f.e.use_telekinetic_move(f.a,f.b,TK.PSYCHIC,overload=True,push_direction=(1,0))
                event_id=f.e._passive_pending
                self.assertEqual((f.a.budget['standard'],f.a.budget['swift'],AP.available(f.a)),(0,1,before_ap))
                self.assertEqual((f.b.hp,tuple(f.b.pos)),(before_hp,before_pos))
                f.restore()
                if wait_kind=='defense':
                    f.e.choose_move_defense(event_id,f.b,use=False,reason='actual Book Psychic target declines Detect')
                else:
                    f.e.choose_passive_event(event_id,f.a,listener,
                        {'decisions':{'decision':{'value':True,'reason':'actual standalone Book Move listener decision'}}})
                self.assertLess(f.b.hp,before_hp);self.assertEqual(tuple(f.b.pos),(before_pos[0]+1,before_pos[1]))
                self.assertIn('취약',f.b.conditions)
                self.assertEqual((f.a.budget['standard'],f.a.budget['swift'],AP.available(f.a)),(0,0,before_ap-2))
                self.assertEqual(f.a.move_uses[TK.PSYCHIC],1)
                f.restore();before=CODEC.dump_engine(f.e)
                self.assertEqual(f.e.deliver_passive_event(event_id),'already_delivered')
                self.assertEqual(CODEC.dump_engine(f.e),before);f.valid()

    def test_actual_faint_during_paid_csv_defense_wait_cancels_without_refund_or_new_damage(self):
        f=self.f;self.family(TK.OVERLOAD)
        f.e.gm.set_position(f.c,(6,3),reason='actual second area recipient')
        f.begin();self.watch_defense();hp=(f.b.hp,f.c.hp);before_ap=AP.available(f.a)
        with patch.object(Engine,'d20',return_value=18):
            with self.assertRaises(PASSIVE.PassiveEventPending):
                f.e.use_telekinetic_move(f.a,f.b,TK.PSYSHOCK,overload=True,aim=(6,2))
        event_id=f.e._passive_pending;history=deepcopy(f.a._action_history)
        f.e.gm.faint(f.a,reason='actual attacker becomes unable to finish its waiting activation')
        f.e.deliver_passive_event(event_id)
        self.assertIsNone(f.e._passive_pending);self.assertEqual((f.b.hp,f.c.hp),hp)
        self.assertEqual(AP.available(f.a),before_ap-1)
        self.assertEqual(f.a.move_uses[TK.PSYSHOCK],1);self.assertEqual(f.a._action_history,history)
        self.assertNotIn('telekinetic_move_choice',f.a.spec)
        f.restore();f.valid()
