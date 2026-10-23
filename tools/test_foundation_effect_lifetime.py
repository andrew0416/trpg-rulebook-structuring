"""Common lifetime declarations exercised through real native consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer
from grid import Grid
from state_codec import StateCodecError
import combat_timing as TIME
import effect_lifetimes as LIFE
import effect_lifetime_policy as POLICY
import forced_movement as FORCED
import effects as FX


class EffectLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def setUp(self):
        self.e = Engine(self.r, 913)
        def actor(name, pos):
            return Combatant(self.r, build_trainer(self.r, name, 20,
                dict.fromkeys(('hp','atk','def','spa','spd','spe'),20), pos=pos))
        self.a = actor('lifetime owner', (1,1)); self.b = actor('lifetime target', (5,1))
        self.e.gm.add_combatant(self.a); self.e.gm.add_combatant(self.b)

    def apply(self, effect, source='gm/lifetime/a'):
        return self.e.apply_effect(self.a, self.b, effect, None, True, 0, source)

    def modifier(self, value=3, **controls):
        return dict(type='accuracy_mod', value=value, target='self', **controls)

    def test_seconds_deadlines_and_sources_remain_independent_across_scene_and_day(self):
        self.assertEqual(self.apply(self.modifier(duration={'seconds':90000})), (1,0))
        self.apply(self.modifier(value=7, duration={'seconds':10}), 'gm/lifetime/b')
        self.e.end_scene(self.e.everyone)
        self.e.advance_time(9); self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),10)
        self.e.advance_time(1); self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),3)
        self.e.advance_time(86400); self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),3)
        self.e.advance_time(3590); self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),0)
        self.assertEqual([x['ended_at'] for x in self.a.custom_conditions['effect_lifetime_history']], [10,90000])

    def test_actual_condition_cure_ends_only_its_continuous_source(self):
        self.e.apply_status(self.a,'마비')
        self.apply(self.modifier(**{'while':{'owner':'user','condition':'마비'}}))
        self.apply(self.modifier(value=7,duration={'seconds':30}), 'gm/lifetime/b')
        self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),10)
        self.e.cure_status(self.a,'마비')
        self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),7)
        self.assertEqual(self.a.custom_conditions['effect_lifetime_history'][0]['event']['kind'],'condition_ended')

    def test_real_displacement_ends_region_contribution_using_full_body(self):
        self.e.grid = Grid(10,10)
        self.apply(self.modifier(**{'while':{'owner':'user','cells':[[1,1]],'membership':'all'}}))
        self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),3)
        result = FORCED.displace(self.e,self.b,self.a,direction=(1,0),distance=1,source='gm/displacement')
        self.assertEqual(result['position'],(2,1))
        self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),0)
        self.apply(self.modifier(**{'while':{'owner':'user','cells':[[2,1]],'membership':'all'}}))
        self.e.gm.set_position(self.a,(3,1),reason='actual GM position observation')
        self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),0)

    def test_owner_turn_repeats_once_per_actual_event_and_consumes_its_limit(self):
        self.e.start_round(self.e.everyone); self.e.start_of_turn(self.a,initiative_count=20)
        self.apply(dict(type='stage_change',stat='def',delta=-1,repeat={'event':'turn_end','owner':'user','times':2}))
        self.assertEqual(self.b.stages['def'],0)
        self.e.end_of_turn(self.a); self.assertEqual(self.b.stages['def'],-1)
        TIME.end_turn(self.e,self.a); self.assertEqual(self.b.stages['def'],-1)
        self.e.start_of_turn(self.b,initiative_count=10); self.e.end_of_turn(self.b)
        self.assertEqual(self.b.stages['def'],-1)
        self.e.end_round(); self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.a,initiative_count=20); self.e.end_of_turn(self.a)
        self.assertEqual(self.b.stages['def'],-2); self.assertFalse(TIME.records(self.b))
        self.assertEqual(self.b.custom_conditions['effect_lifetime_history'][0]['state'],'consumed')

    def test_large_time_advance_delivers_each_due_instant_and_stops_at_deadline(self):
        self.b.hp -= 40
        self.apply(dict(type='heal',amount=5,repeat={'seconds':3,'times':10},duration={'seconds':10}))
        before = self.b.hp; self.e.advance_time(15)
        self.assertEqual(self.b.hp,before+15)
        history = self.b.custom_conditions['effect_lifetime_history'][0]
        self.assertEqual([x['token'] for x in history['deliveries']],[3,6,9])
        self.assertEqual(history['ended_at'],10)

    def test_repeat_failure_rolls_back_time_and_all_prior_deliveries(self):
        self.b.hp -= 40
        self.apply(dict(type='heal',amount=5,repeat={'seconds':3,'times':3}))
        before = (self.e.elapsed_seconds,self.b.hp,len(self.e._effect_dispatch_receipts))
        original = FX.run_effects
        calls = []
        def fail_second(*args,**kwargs):
            calls.append(True)
            if len(calls)==2:raise ValueError('observed second consequence failure')
            return original(*args,**kwargs)
        with patch.object(FX,'run_effects',side_effect=fail_second):
            with self.assertRaisesRegex(ValueError,'second consequence'):self.e.advance_time(9)
        self.assertEqual((self.e.elapsed_seconds,self.b.hp,len(self.e._effect_dispatch_receipts)),before)
        self.assertEqual(TIME.records(self.b)[0]['lifetime_deliveries'],[])

    def test_turn_boundary_rolls_back_all_common_deliveries_on_late_failure(self):
        self.e.start_round(self.e.everyone); self.e.start_of_turn(self.a,initiative_count=20)
        for delta in (-1,1):
            self.apply(dict(type='stage_change',stat='def',delta=delta,repeat={'event':'turn_end','owner':'user','times':2}))
        original=FX.run_effects; calls=[]
        def fail_second(*args,**kwargs):
            calls.append(True)
            if len(calls)==2:raise ValueError('late boundary failure')
            return original(*args,**kwargs)
        with patch.object(FX,'run_effects',side_effect=fail_second):
            with self.assertRaisesRegex(ValueError,'late boundary'):TIME.end_turn(self.e,self.a)
        self.assertEqual(self.b.stages['def'],0)
        self.assertEqual([row['lifetime_deliveries'] for row in TIME.records(self.b)],[[],[]])

    def test_zero_time_preserves_native_life_synchronization(self):
        self.b.hp=0; self.assertNotIn('기절',self.b.conditions)
        self.e.advance_time(0)
        self.assertEqual(self.e.elapsed_seconds,0); self.assertIn('기절',self.b.conditions)

    def test_repeat_cure_records_completed_delivery_before_continuous_ending(self):
        self.e.apply_status(self.b,'마비')
        self.apply(dict(type='cure_status',status='마비',repeat={'seconds':3,'times':3},
                        **{'while':{'owner':'target','condition':'마비'}}))
        self.e.advance_time(9)
        self.assertNotIn('마비',self.b.conditions); self.assertFalse(TIME.records(self.b))
        history = self.b.custom_conditions['effect_lifetime_history'][0]
        self.assertEqual(history['ended_at'],3)
        self.assertEqual(len(history['deliveries']),1)
        self.assertEqual(history['event']['kind'],'condition_ended')

    def test_source_and_occurrence_selectors_end_only_selected_contributions(self):
        self.apply(self.modifier(duration={'seconds':30}))
        self.apply(self.modifier(value=5,duration={'seconds':30}))
        self.apply(self.modifier(value=7,duration={'seconds':30}),'gm/lifetime/b')
        occurrence = TIME.records(self.a)[0]['effect_occurrence']
        self.assertEqual(self.e.end_effects(self.a,occurrence=occurrence),1)
        self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),12)
        self.assertEqual(self.e.end_effects(self.a,source='gm/lifetime/a'),1)
        self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),7)
        with self.assertRaises(ValueError):self.e.end_effects(self.a)

    def test_save_restore_retains_real_owners_receipts_and_next_delivery(self):
        self.b.hp -= 40
        self.apply(dict(type='heal',amount=5,repeat={'seconds':3,'times':3}))
        self.e.advance_time(3)
        restored = Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state())))
        a = next(c for c in restored.everyone if c.entity_id==self.a.entity_id)
        b = next(c for c in restored.everyone if c.entity_id==self.b.entity_id)
        self.assertIs(TIME.records(b)[0]['lifetime_actor'],a)
        before=b.hp; restored.advance_time(6)
        self.assertEqual(b.hp,before+10); self.assertFalse(TIME.records(b))
        self.assertEqual([x['token'] for x in b.custom_conditions['effect_lifetime_history'][0]['deliveries']],[3,6,9])
        Engine.import_state(self.r,json.loads(json.dumps(restored.export_state())))
        b.custom_conditions['effect_lifetime_history'].append(dict(b.custom_conditions['effect_lifetime_history'][0]))
        with self.assertRaises(StateCodecError):restored.export_state()

    def test_forged_deadline_and_replayed_delivery_cannot_be_saved(self):
        self.apply(self.modifier(duration={'seconds':30}))
        TIME.records(self.a)[0][POLICY.KEY]['end_at'] += 1
        with self.assertRaises(StateCodecError):self.e.export_state()
        self.setUp()
        self.b.hp -= 40
        self.apply(dict(type='heal',amount=5,repeat={'seconds':3,'times':3}))
        self.e.advance_time(3)
        deliveries = TIME.records(self.b)[0]['lifetime_deliveries']
        deliveries.append(dict(deliveries[0]))
        with self.assertRaises(StateCodecError):self.e.export_state()

    def test_declared_target_turn_expiry_uses_actual_owner_and_type_consumer(self):
        self.e.start_round(self.e.everyone); self.e.start_of_turn(self.a,initiative_count=20)
        original = self.b.types[:]
        self.apply(dict(type='type_change',add_type='물',target='target',until={'event':'turn_end','owner':'target','after':1}))
        self.assertIn('물',self.b.types)
        self.e.end_of_turn(self.a); self.assertIn('물',self.b.types)
        self.e.start_of_turn(self.b,initiative_count=10); self.e.end_of_turn(self.b)
        self.assertEqual(self.b.types,original)

    def test_declared_scene_boundary_leaves_seconds_and_other_sources_active(self):
        self.apply(self.modifier(until={'event':'scene_end'}))
        self.apply(self.modifier(value=7,duration={'seconds':30}),'gm/lifetime/b')
        self.e.end_scene(self.e.everyone)
        self.assertEqual(LIFE.numeric(self.a,'accuracy_modifier'),7)

    def test_ambiguous_or_unbounded_declarations_fail_before_installation(self):
        for controls in ({'until':{'event':'turn_end'}}, {'repeat':'every turn'},
                         {'duration':{'seconds':True}}, {'while':'maybe active'}):
            with self.subTest(controls=controls):
                with self.assertRaises(ValueError):self.apply(self.modifier(**controls))
                self.assertFalse(TIME.records(self.a))


if __name__=='__main__':unittest.main()
