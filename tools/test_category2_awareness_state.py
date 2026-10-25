"""Awareness acquired-state persistence and actual current-owner lifecycle."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from tools import test_category3_awareness as SOURCE
import enduring_awareness as A
import effects_ext as EXT
import items as ITEMS
import pokemon_party as PARTY
import state_codec as CODEC

class AwarenessStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.fx=SOURCE.Tests();self.fx.r=self.rules;self.fx.setUp();self.fx.confirm()
  self.e,self.t,self.ps=self.fx.e,self.fx.t,self.fx.p
 def load(self):
  e=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  return e,{c.entity_id:c for c in e.everyone}
 def test_durable_confirmed_acquisition_drives_actual_paralysis_save(self):
  self.e.apply_status(self.ps[0],'마비');e,actors=self.load();t,p=actors[self.t.entity_id],actors[self.ps[0].entity_id]
  self.assertEqual(t.spec['_awareness_acquisition'],self.t.spec['_awareness_acquisition'])
  e.start_round(e.everyone);e.rng=SOURCE.FixedRng([9]);e.start_of_turn(p,initiative_count=10)
  self.assertIsNone(p._turn_action_limit);self.assertIn('마비',p.conditions);self.assertEqual(p.save_mod,0)
  self.assertEqual(EXT.save_dc(e,p,'마비',11),9)
 def test_actual_transfer_removes_old_bonus_and_restores_only_on_actual_return(self):
  receiver=self.fx.actor('receiver','trainer');receiver.spec.pop('trainer_id',None);self.e.everyone.append(receiver)
  PARTY.configure(self.e,self.t,mode='unlimited',reason='actual initial roster',roster=self.ps)
  PARTY.configure(self.e,receiver,mode='unlimited',reason='actual empty roster',roster=[])
  p=self.ps[0];p.save_mod=3;historical=deepcopy(self.t.spec['_awareness_acquisition'])
  self.assertEqual(EXT.save_dc(self.e,p,'마비',11),6)
  PARTY.transfer(self.e,self.t,target=p,new_owner=receiver,reason='actual voluntary transfer',request_id='awareness-away')
  self.assertEqual(EXT.save_dc(self.e,p,'마비',11),8);self.assertEqual(p.save_mod,3)
  self.assertEqual(self.t.spec['_awareness_acquisition'],historical)
  PARTY.transfer(self.e,receiver,target=p,new_owner=self.t,reason='actual voluntary return',request_id='awareness-back')
  self.assertEqual(EXT.save_dc(self.e,p,'마비',11),6);self.assertEqual(p.save_mod,3)
 def test_gm_restore_and_source_removal_change_live_derived_bonus_without_mutating_target(self):
  self.e.gm.snapshot('owned-passive');self.t.spec['feats']=[];ITEMS.register_feats(self.e,self.t)
  self.assertEqual(EXT.save_dc(self.e,self.ps[0],'잠듦',16),16)
  self.e.gm.restore('owned-passive');ITEMS.register_feats(self.e,self.t)
  self.assertEqual(EXT.save_dc(self.e,self.ps[0],'잠듦',16),14)
  e,actors=self.load();t,p=actors[self.t.entity_id],actors[self.ps[0].entity_id]
  t.spec['feats']=[];ITEMS.register_feats(e,t);self.assertEqual(EXT.save_dc(e,p,'잠듦',16),16);self.assertEqual(p.save_mod,0)

 def csv(self):
  self.fx.setUp();self.fx.t.spec['feats']=[A.AWARENESS_CSV]
  self.fx.confirm();self.e,self.t,self.ps=self.fx.e,self.fx.t,self.fx.p

 def test_csv_source_is_preserved_through_registration_and_actual_all_condition_saves(self):
  self.csv();ITEMS.register_feats(self.e,self.t);ITEMS.register_feats(self.e,self.t)
  self.assertEqual(self.t.spec['_awareness_acquisition']['source'],A.AWARENESS_CSV)
  self.assertEqual([p.save_mod for p in [self.t,*self.ps]],[0]*4)
  for condition in ('마비','얼음','잠듦','혼란','난동','헤롱헤롱',None):
   self.assertEqual(EXT.save_dc(self.e,self.ps[0],condition,15),13)
  self.assertEqual(EXT.save_dc(self.e,self.t,'마비',11),11)
  self.e.apply_status(self.ps[0],'마비');self.e.start_round(self.e.everyone)
  self.e.rng=SOURCE.FixedRng([9]);self.e.start_of_turn(self.ps[0],initiative_count=10)
  self.assertIsNone(self.ps[0]._turn_action_limit);self.assertIn('마비',self.ps[0].conditions)
  self.assertEqual(self.ps[0].budget,{'standard':1,'shift':1,'swift':1})

 def test_csv_record_and_live_owner_lifetime_survive_both_restores_and_real_transfer(self):
  self.csv();historical=deepcopy(self.t.spec['_awareness_acquisition'])
  self.e.gm.snapshot('csv-awareness');self.t.spec['feats']=[]
  self.assertEqual(EXT.save_dc(self.e,self.ps[0],'마비',11),11)
  self.e.gm.restore('csv-awareness');self.e,actors=self.load()
  self.t=actors[self.t.entity_id];self.ps=[actors[p.entity_id] for p in self.ps]
  self.assertEqual(self.t.spec['_awareness_acquisition'],historical)
  self.assertEqual(EXT.save_dc(self.e,self.ps[0],'마비',11),9)
  receiver=Combatant(self.e.r,deepcopy(self.fx.actor('csv-receiver','trainer').spec))
  receiver.spec.pop('trainer_id',None)
  self.e.gm.add_combatant(receiver,reason='actual receiver in the restored Rules world')
  PARTY.configure(self.e,self.t,mode='unlimited',reason='actual CSV roster',roster=self.ps)
  PARTY.configure(self.e,receiver,mode='unlimited',reason='actual receiver',roster=[])
  PARTY.transfer(self.e,self.t,target=self.ps[0],new_owner=receiver,reason='actual transfer',request_id='csv-away')
  self.assertEqual(EXT.save_dc(self.e,self.ps[0],'마비',11),11)
  self.assertEqual(self.t.spec['_awareness_acquisition'],historical)
  PARTY.transfer(self.e,receiver,target=self.ps[0],new_owner=self.t,reason='actual return',request_id='csv-back')
  self.t.hp=0;self.assertEqual(EXT.save_dc(self.e,self.ps[0],'마비',11),11)
  self.t.hp=1;self.assertEqual(EXT.save_dc(self.e,self.ps[0],'마비',11),9)
  self.ps[1].abilities.clear();self.ps[1].spec['trainer_id']='elsewhere'
  self.assertEqual(EXT.save_dc(self.e,self.ps[0],'마비',11),9)

 def test_csv_missing_duplicate_switched_source_or_selection_rejects_before_native_rng(self):
  for feats in ([],[A.AWARENESS_CSV,A.AWARENESS],[A.AWARENESS_CSV,'Awareness']):
   self.fx.setUp();self.fx.t.spec['feats']=feats
   with self.assertRaises(ValueError):self.fx.confirm()
   self.assertNotIn('_awareness_acquisition',self.fx.t.spec)
  for mutation in ('missing_receipt','switched_source','duplicate','selection'):
   self.csv();p=self.ps[0];self.e.apply_status(p,'마비');self.e.start_round(self.e.everyone)
   if mutation=='missing_receipt':self.t.spec.pop('_awareness_acquisition')
   elif mutation=='switched_source':self.t.spec['feats']=[A.AWARENESS]
   elif mutation=='duplicate':self.t.spec['feats'].append(A.AWARENESS)
   selected=self.rules._selected_rule
   def resolve(uid,**options):
    return uid+'-other' if mutation=='selection' and uid==A.AWARENESS_CSV else selected(uid,**options)
   rng=self.e.rng.getstate();budget=deepcopy(getattr(p,'budget',None))
   with patch.object(self.rules,'_selected_rule',side_effect=resolve):
    with self.assertRaises(ValueError):self.e.start_of_turn(p,initiative_count=10)
    with self.assertRaises(ValueError):ITEMS.register_feats(self.e,self.t)
   self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(getattr(p,'budget',None),budget)
   self.assertIsNone(self.e._active_turn_actor)

if __name__=='__main__':unittest.main()
