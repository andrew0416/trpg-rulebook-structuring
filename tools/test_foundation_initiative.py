"""Foundation 32: declared arithmetic and actual native initiative consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer
from rulings import Rulings
from state_codec import dump_engine, load_engine, StateCodecError
import initiative_derivation as D
import combat_timing as TIME
import world_entities as WORLD
import special_entities as SPECIAL


class InitiativeFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')
        cls.poly = Rules(ROOT, ruleset='polygon')

    def setUp(self):
        self.e = Engine(self.r, 872)
        self.r.rulings = self.e.rulings = Rulings()
        self.a = self.actor('subject', 21)
        self.b = self.actor('other', 15)
        self.e.everyone = self.e.gm.everyone = [self.a, self.b]

    def actor(self, name, speed, rules=None):
        rules = rules or self.r
        stats = dict.fromkeys(('hp','atk','def','spa','spd','spe'), 20)
        stats['spe'] = speed
        return Combatant(rules, build_trainer(rules, name, 10, stats, pos=(1,1)))

    def procedure(self, order, **fields):
        return dict(source='gm/declared-initiative', order=order, rounding='floor', **fields)

    def apply(self, effect, source='gm/initiative/a'):
        return self.e.apply_effect(self.b, self.a, dict(effect, target='target'), None, True, 0, source)

    def test_declared_phase_order_changes_actual_native_result(self):
        self.a.conditions.add('마비'); self.a.initiative_bonus = 4
        self.assertIsNone(self.e.initiative_value(self.a).value)
        p = self.procedure(['add','multiply'])
        before = dump_engine(self.e)
        out = self.e.initiative_value(self.a, procedure=p)
        self.assertEqual(out.value, 12)
        self.assertEqual(out.derivation['exact'], {'numerator':25,'denominator':2})
        self.assertEqual(self.e.initiative_value(self.a, procedure=self.procedure(['multiply','add'])).value, 14)
        self.assertEqual(dump_engine(self.e), before)
        self.assertEqual(self.e.initiative([self.a,self.b],procedures={self.a.entity_id:p}), [self.b,self.a])

    def test_unknown_order_is_pending_before_clock_or_random_consumption(self):
        self.a.conditions.add('마비'); self.a.initiative_bonus = 4
        before = (self.e.elapsed_seconds,self.e.round_no,self.e.rng.getstate(),deepcopy(self.a.stats))
        out = self.e.initiative_value(self.a)
        self.assertTrue(out.adjudicable)
        self.assertEqual({r['source'] for r in out.derivation['initiative_contributions']},
                         {'condition/마비','state/initiative_bonus'})
        self.assertIsNone(self.e.initiative([self.a,self.b]))
        self.assertEqual(before, (self.e.elapsed_seconds,self.e.round_no,self.e.rng.getstate(),self.a.stats))

    def test_external_data_participates_without_engine_rule_branch(self):
        self.a.registry.append(dict(type='initiative_multiplier',
            value={'numerator':3,'denominator':2},source='homebrew/pace'))
        self.assertEqual(self.e.initiative_value(self.a).value,31)
        self.assertEqual(self.e.initiative([self.a,self.b]),[self.a,self.b])
        self.a.stages['spe']=2
        out=self.e.initiative_value(self.a)
        self.assertEqual(out.value,43)
        self.assertEqual(out.derivation['contributions'][0]['source'],'homebrew/pace')
        self.assertEqual(self.a.stats['spe'],21)

    def test_native_guile_rank_contribution_recomputes_and_current_basis_does_not_duplicate(self):
        self.a.spec.update(edges=['패기'],initiative_basis='base')
        self.a.spec['skills']['교활']=3
        out=self.e.initiative_value(self.a)
        self.assertEqual(out.value,24)
        self.assertEqual(out.derivation['contributions'][0]['source'],'edge/패기')
        self.a.spec['skills']['교활']=5
        self.assertEqual(self.e.initiative_value(self.a).value,26)
        self.a.spec['initiative_basis']='current'; self.a.initiative_bonus=5
        self.assertEqual(self.e.initiative_value(self.a).value,26)

    def test_immediate_multiplier_and_additive_producers_keep_sources(self):
        self.assertEqual(self.apply(dict(type='initiative',multiplier=0.5)),(1,0))
        self.assertEqual(self.e.initiative_value(self.a).value,10)
        self.assertEqual(self.apply(dict(type='initiative',delta=4),'gm/initiative/b'),(1,0))
        out=self.e.initiative_value(self.a,procedure=self.procedure(['add','multiply']))
        self.assertEqual(out.value,12)
        self.assertEqual({r['source'] for r in out.derivation['contributions']},
                         {'gm/initiative/a','gm/initiative/b'})
        loaded=load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
        actual=next(c for c in loaded.everyone if c.entity_id==self.a.entity_id)
        self.assertEqual(loaded.initiative_value(actual,procedure=self.procedure(['add','multiply'])).value,12)

    def test_temporary_operations_expire_independently_without_reversing_base(self):
        self.apply(dict(type='initiative',set_to=11,duration={'seconds':5}),'gm/fixed')
        self.apply(dict(type='initiative_multiplier',value=0.5,duration={'seconds':7}),'gm/half')
        self.apply(dict(type='initiative',delta=4,duration={'seconds':9}),'gm/flat')
        p=self.procedure(['replace','add','multiply'])
        self.assertEqual(self.e.initiative_value(self.a,procedure=p).value,7)
        self.assertEqual((self.a.initiative_override,self.a.initiative_bonus),(None,0))
        self.e.advance_time(5)
        self.assertEqual(self.e.initiative_value(self.a,procedure=p).value,12)
        self.e.advance_time(2)
        self.assertEqual(self.e.initiative_value(self.a,procedure=p).value,25)
        self.e.advance_time(2)
        self.assertEqual(self.e.initiative_value(self.a).value,21)
        self.assertEqual(self.a.stats['spe'],21)
        self.assertFalse(TIME.records(self.a))

    def test_temporary_zero_keeps_native_projection_and_restores_original(self):
        self.apply(dict(type='initiative',set_to=0,duration={'seconds':3}))
        self.assertEqual(self.a.initiative_override,0)
        self.assertEqual(self.e.initiative_value(self.a).value,0)
        self.assertEqual(self.a.stats['spe'],21)
        self.e.advance_time(3)
        self.assertIsNone(self.a.initiative_override)
        self.assertEqual(self.e.initiative_value(self.a).value,21)

    def test_live_flinch_stacks_take_the_declared_position(self):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.b,initiative_count=15)
        self.e.apply_status(self.a,'풀죽음',applied_by=self.b)
        self.e.apply_status(self.a,'풀죽음',applied_by=self.b)
        self.a.conditions.add('마비')
        self.assertIsNone(self.e.initiative_value(self.a).value)
        self.assertEqual(self.e.initiative_value(self.a,procedure=self.procedure(['multiply','flinch'])).value,0)
        self.assertEqual(self.e.initiative_value(self.a,procedure=self.procedure(['flinch','multiply'])).value,5)
        self.e.cure_status(self.a,'풀죽음')
        self.assertEqual(self.e.initiative_value(self.a).value,10)

    def test_actual_controller_speed_keeps_participant_contributions_explicit(self):
        WORLD.set_controller(self.e,self.a,{'kind':'actor','id':self.b.entity_id},reason='observed controller')
        self.a.initiative_bonus=4; self.b.initiative_bonus=8
        p=self.procedure(['add'],speed_subject='controller')
        out=self.e.initiative_value(self.a,procedure=p)
        self.assertEqual(out.value,19)
        self.assertEqual(out.derivation['speed_actor_id'],self.b.entity_id)
        self.assertEqual(out.derivation['participant_id'],self.a.entity_id)
        self.assertEqual(self.e.initiative_value(self.a,procedure=dict(p,contribution_subject='speed_actor')).value,23)
        WORLD.set_controller(self.e,self.a,{'kind':'player','id':'player-id'},reason='observed player')
        self.assertIsNone(self.e.initiative_value(self.a,procedure=p).value)

    def test_vehicle_uses_actual_driver_without_fabricating_vehicle_speed(self):
        self.e=Engine(self.poly,872); self.a=self.actor('driver',21,self.poly);self.b=self.actor('other driver',15,self.poly)
        self.e.everyone=self.e.gm.everyone=[self.a,self.b]
        row=dict(id='vehicle',kind='vehicle',location={'kind':'unknown'},stats={'hp':10,'def':8,'spd':6},
            hp=60,max_hp=60,breaches=0,patched_breaches=0,breach_security=3,breach_capacity=4,
            owner_id=self.a.entity_id,driver_id=self.a.entity_id,passenger_ids=[],weapon_ids=[],
            destroyed=False,overland=7,breach_resistance_armor=False)
        SPECIAL.observe(self.e,row,reason='actual vehicle observation')
        vehicle=self.e._physical_objects['vehicle']
        p=self.procedure([],speed_subject='driver',contribution_subject='none')
        self.assertIsNone(self.e.initiative_value(vehicle).value)
        self.assertEqual(self.e.initiative_value(vehicle,procedure=p).value,21)
        self.assertEqual(self.e.initiative([vehicle,self.b],procedures={'vehicle':p}),[vehicle,self.b])
        vehicle['driver_id']=self.b.entity_id
        self.assertEqual(self.e.initiative_value(vehicle,procedure=p).value,15)
        self.assertNotIn('spe',vehicle['stats'])
        self.assertIsNone(self.e.initiative_value(deepcopy(vehicle),procedure=p).value)
        loaded=load_engine(Rules(ROOT,ruleset='polygon'),json.loads(json.dumps(dump_engine(self.e))))
        out=loaded.initiative_value(loaded._physical_objects['vehicle'],procedure=p)
        self.assertEqual(out.derivation['speed_actor_id'],self.b.entity_id)

    def test_invalid_order_or_identity_cannot_be_replaced_by_a_gm_final_value(self):
        self.a.conditions.add('마비'); self.a.initiative_bonus=4
        self.e.rulings.provider=lambda prompt:dict(value=999,reason='must not override invalid input')
        for p in (self.procedure(['add']),self.procedure(['add','add','multiply']),
                  dict(self.procedure(['add','multiply']),rounding='exact')):
            self.assertIsNone(self.e.initiative([self.a],procedures={self.a.entity_id:p}))
        clone=self.actor('clone',20); clone.spec['id']=self.a.entity_id
        self.assertIsNone(self.e.initiative([clone]))
        self.assertEqual(self.e.round_no,0)
        self.assertFalse(self.e.rulings.log)

    def test_equal_priority_fixed_conflict_remains_pending(self):
        self.a.initiative_override=30
        self.apply(dict(type='initiative',set_to=0,duration={'seconds':3}))
        out=self.e.initiative_value(self.a,procedure=self.procedure(['replace']))
        self.assertTrue(out.adjudicable); self.assertIsNone(out.value)
        self.e.advance_time(3)
        self.assertEqual(self.e.initiative_value(self.a).value,30)

    def test_declared_fixed_priorities_and_source_replay_without_losing_baseline(self):
        self.apply(dict(type='initiative',set_to=30,priority=1),'gm/initial-fixed')
        self.apply(dict(type='initiative',set_to=0,priority=2,duration={'seconds':3}),'gm/temporary-fixed')
        p=self.procedure(['replace'])
        out=self.e.initiative_value(self.a,procedure=p)
        self.assertEqual(out.value,0)
        self.assertEqual({r['source'] for r in out.derivation['contributions']},
                         {'gm/initial-fixed','gm/temporary-fixed'})
        self.assertEqual(self.a.initiative_override,30)
        loaded=load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
        actual=next(c for c in loaded.everyone if c.entity_id==self.a.entity_id)
        self.assertEqual(loaded.initiative_value(actual,procedure=p).value,0)
        loaded.advance_time(3)
        self.assertEqual(loaded.initiative_value(actual).value,30)
        loaded.gm.set_initiative(actual,18,reason='explicit independent GM change')
        self.assertEqual(loaded.initiative_value(actual).value,18)
        self.assertNotIn('initiative_fixed',actual.custom_conditions)

    def test_saved_temporary_operations_replay_and_forgery_rejects(self):
        self.apply(dict(type='initiative',delta=4,duration={'seconds':3}))
        self.e.gm.snapshot('initiative')
        loaded=load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(dump_engine(self.e))))
        actual=next(c for c in loaded.everyone if c.entity_id==self.a.entity_id)
        self.assertEqual(loaded.initiative_value(actual).value,25)
        loaded.advance_time(3)
        self.assertEqual(loaded.initiative_value(actual).value,21)
        self.e.advance_time(3);self.e.gm.restore('initiative')
        self.assertEqual(self.e.initiative_value(self.a).value,25)
        TIME.records(self.a)[0]['initiative_operation']['value']=999
        with self.assertRaises(StateCodecError):dump_engine(self.e)

    def test_immediate_multiplier_forgery_cannot_save_or_execute(self):
        self.apply(dict(type='initiative',multiplier=0.5))
        self.a.registry[0]['value']=2
        self.assertIsNone(self.e.initiative_value(self.a).value)
        with self.assertRaises(StateCodecError):dump_engine(self.e)

    def test_invalid_effect_values_hold_before_native_field_clock_or_rng_change(self):
        before=(self.a.initiative_bonus,self.a.initiative_override,self.e.elapsed_seconds,self.e.rng.getstate())
        for effect in (dict(type='initiative',delta=True),dict(type='initiative',delta=3,set_to=4),
                       dict(type='initiative',multiplier=-1,duration={'seconds':3})):
            with self.assertRaises(ValueError):self.apply(effect)
        self.assertEqual(before,(self.a.initiative_bonus,self.a.initiative_override,self.e.elapsed_seconds,self.e.rng.getstate()))
        self.assertFalse(TIME.records(self.a));self.assertFalse(self.a.registry)

    def test_late_native_grant_failure_rolls_back_aggregate_and_source_ledgers(self):
        import state_grants as G
        original=G.numeric
        before=(self.a.initiative_bonus,deepcopy(self.a.spec),self.e.rng.getstate())
        def fail(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('late native numeric failure')
        with patch.object(G,'numeric',side_effect=fail):
            self.assertEqual(self.apply(dict(type='initiative',delta=4)),(0,1))
        self.assertEqual(before,(self.a.initiative_bonus,self.a.spec,self.e.rng.getstate()))

    def test_late_temporary_install_failure_rolls_back_clock_and_zero_projection(self):
        original=TIME.install
        before=(self.a.initiative_override,deepcopy(self.a.custom_conditions),self.e.elapsed_seconds,self.e.rng.getstate())
        def fail(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('late temporary installation failure')
        with patch.object(TIME,'install',side_effect=fail):
            self.assertEqual(self.apply(dict(type='initiative',set_to=0,duration={'seconds':3})),(0,1))
        self.assertEqual(before,(self.a.initiative_override,self.a.custom_conditions,self.e.elapsed_seconds,self.e.rng.getstate()))


if __name__=='__main__':
    unittest.main()
