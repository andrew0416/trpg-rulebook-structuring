"""Partial common One Time Use state: explicit native activation fixture, not a sourced feature implementation."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import frequency as F
import downtime as DT
import effects as FX
import action_metadata as META
import state_codec as CODEC

class OneTimeFrequencyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,seed=89)
  spec=dict(kind='trainer',level=20,stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),40),moves=[],pos=(0,0))
  self.a=Combatant(self.rules,dict(spec,name='feature-holder'));self.b=Combatant(self.rules,dict(spec,name='target'))
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
  self.frequency={'kind':'one_time','uses':1,'raw':'일회용 - 자유 행동','action':'free'}
  self.register(self.a)
 def register(self,a):
  a.registry=[dict(type='feat_manual',name='one-time-common-fixture',usage_key='ch03-585/fixture-source',frequency=dict(self.frequency),effects=[dict(type='injury',value=1,target='target')])]
 def use(self,e=None,a=None,b=None):return (e or self.e).manual_feat(a or self.a,'one-time-common-fixture',b or self.b)
 def test_actual_manual_activation_runs_once_and_repeated_registration_does_not_refill(self):
  self.assertEqual(self.use(),(1,0));before=(deepcopy(self.a.spec),self.b.injuries,self.e.rng.getstate(),list(self.a._action_history))
  self.assertEqual(self.use(),(0,1));self.assertEqual(before,(self.a.spec,self.b.injuries,self.e.rng.getstate(),self.a._action_history))
  self.register(self.a);self.assertEqual(self.use(),(0,1));self.assertEqual(self.b.injuries,1)
 def test_scene_day_rest_and_session_never_restore_one_time_activation(self):
  self.use();self.e.end_scene();DT.new_day(self.a);DT.extended_rest(self.e,self.a,4)
  self.e.session_frequency=True;F.bind_session(self.e,self.a);F.refresh_session(self.e,self.a)
  self.assertEqual(self.use(),(0,1));self.assertEqual(self.b.injuries,1)
 def test_gm_rewind_and_durable_load_preserve_each_observed_lifetime(self):
  self.e.gm.snapshot('before');self.use();self.e.gm.restore('before');self.assertEqual(self.use(),(1,0))
  e=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)));actors={a.entity_id:a for a in e.everyone}
  a,b=actors[self.a.entity_id],actors[self.b.entity_id];self.assertEqual(self.use(e,a,b),(0,1));self.assertEqual(b.injuries,1)
 def test_frequency_policy_change_cannot_overwrite_once_ever_receipt(self):
  self.use();self.a.registry[0]['frequency']={'kind':'scene','uses':2,'raw':'장면x2 - 자유 행동','action':'free'}
  self.assertEqual(self.use(),(1,0));self.register(self.a);self.assertEqual(self.use(),(0,1));self.assertEqual(self.b.injuries,2)
 def test_native_triggered_activation_uses_same_once_ever_source_counter(self):
  self.a.ability_triggers=[dict(name='one-time-common-trigger-fixture',spec={'event':'one-time-fixture'},frequency='One Time Use',effects=[dict(type='injury',value=1,target='target')])]
  FX.fire_event(self.e,self.a,{'event':'one-time-fixture'},self.b);FX.fire_event(self.e,self.a,{'event':'one-time-fixture'},self.b)
  self.assertEqual(self.b.injuries,1)
 def test_source_spelling_and_metadata_keep_once_ever_not_legacy_atwill(self):
  for raw in ('일회용','One Time Use','One-Time Use','일회용 - 자유 행동'):
   self.assertEqual(F.parse(raw),('one_time',1))
  self.assertEqual(F.parse({'kind':'at_will','uses':1,'raw':'일회용 - 자유 행동'}),('one_time',1))
  self.assertEqual(META.resolve_feature_action({'frequency':self.frequency}),('free',''))
  for uses in (True,0,2,'1'):
   with self.assertRaises(ValueError):F.parse({'kind':'one_time','uses':uses})

if __name__=='__main__':unittest.main()
