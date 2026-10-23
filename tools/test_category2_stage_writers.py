"""Native stage edits preserve conditional sources and durable state."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import builder,combat_stage_sources as CS,effects as FX,effects_ext as EXT

class StageWriterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,992)
  self.a=Combatant(self.r,builder.build_pokemon(self.r,'이상해씨',5,pos=(1,1),abilities=['엽록소']))
  self.b=Combatant(self.r,builder.build_trainer(self.r,'other',5,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),pos=(2,1)))
  self.e.gm.add_combatant(self.a);self.e.gm.add_combatant(self.b)
  self.e.gm.set_weather('sunny',rounds=5,reason='observed weather')
  self.assertEqual(self.a.stages['spe'],4)
 def test_gm_edit_keeps_source_snapshot_and_both_restore_paths(self):
  self.e.gm.set_stage(self.a,'spe',value=2,reason='explicit current stage')
  self.assertEqual(self.a.stages['spe'],2);CS.validate(self.a)
  self.e.gm.snapshot('stage');self.e.gm.set_stage(self.a,'spe',delta=2);self.e.gm.restore('stage')
  self.assertEqual(self.a.stages['spe'],2)
  e=Engine.import_state(self.r,self.e.export_state());a=e.everyone[0]
  self.assertEqual(a.stages['spe'],2);e.gm.set_weather(None,reason='actual weather ends')
  self.assertEqual(a.stages['spe'],-2);CS.validate(a)
  e.end_encounter();self.assertEqual(a.stages['spe'],0)
 def test_haze_resets_to_actual_default_without_erasing_weather_source(self):
  self.e.change_stage(self.a,'spe',1);self.e.change_stage(self.a,'atk',2)
  effect=next(x for x in self.r.moves_mech['move/흑안개']['effects'] if x['type']=='reset_stages')
  FX.h_reset_stages(self.e,self.a,self.a,{**effect,'target':'self'}, {})
  self.assertEqual((self.a.stages['spe'],self.a.stages['atk']),(4,0))
  CS.validate(self.a);self.e.gm.set_weather(None,reason='actual weather ends');self.assertEqual(self.a.stages['spe'],0)
 def test_swap_uses_current_values_and_preserves_each_actors_own_sources(self):
  self.e.change_stage(self.b,'spe',-2)
  FX.h_swap_stages(self.e,self.a,self.b,{'swap_stages':['spe']},{})
  self.assertEqual((self.a.stages['spe'],self.b.stages['spe']),(-2,4));CS.validate(self.a)
  self.e.gm.set_weather(None,reason='actual weather ends')
  self.assertEqual((self.a.stages['spe'],self.b.stages['spe']),(-6,4))
  self.e.end_encounter();self.assertEqual((self.a.stages['spe'],self.b.stages['spe']),(0,0))
 def test_copy_and_inversion_update_source_record_without_copying_source_ownership(self):
  self.e.change_stage(self.b,'spe',1)
  EXT.h_copy_stages(self.e,self.a,self.b,{}, {})
  self.assertEqual(self.a.stages['spe'],1);CS.validate(self.a)
  EXT.h_invert_stages(self.e,self.b,self.a,{}, {})
  self.assertEqual(self.a.stages['spe'],-1);CS.validate(self.a)
  self.e.gm.set_weather(None,reason='actual weather ends');self.assertEqual(self.a.stages['spe'],-5)
 def test_swap_rejects_invalid_second_actor_before_changing_first_actor(self):
  CS.add_base(self.b,'fixture','atk',1,source='fixture',ends='fixture')
  self.b.stages['atk']=2
  before=(deepcopy(self.a.stages),deepcopy(self.a.spec[CS.STATE]))
  with self.assertRaisesRegex(ValueError,'untracked'):FX.h_swap_stages(self.e,self.a,self.b,{'swap_stages':['spe']},{})
  self.assertEqual((self.a.stages,self.a.spec[CS.STATE]),before)
 def test_initial_stage_domain_rejects_hp_unknown_fraction_boolean_and_out_of_range(self):
  spec=builder.build_trainer(self.r,'import',5,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10))
  for stages in ({'hp':1},{'unknown':1},{'atk':0.5},{'atk':True},{'atk':7},{'spe':-7},[]):
   with self.subTest(stages=stages),self.assertRaises(ValueError):Combatant(self.r,{**spec,'initial_stages':stages})
  c=Combatant(self.r,{**spec,'initial_stages':{'atk':6,'spe':-6}})
  self.assertEqual(c.stages,dict(atk=6,**{'def':0},spa=0,spd=0,spe=-6))

if __name__=='__main__':unittest.main()
