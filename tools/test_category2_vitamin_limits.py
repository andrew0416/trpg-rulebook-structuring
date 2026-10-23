"""Source Vitamin lifetime capacity and actual upgraded move-frequency consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'engine'),str(ROOT/'tools')]
from test_category2_frequency_state import SCENE, DAILY
import test_category2_frequency_state as _fixture_test_category2_frequency_state
import vitamin_moves as V,move_state as M,frequency as F,downtime as D,state_codec as CODEC

class VitaminLimitTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_frequency_state.FrequencyStateTests.setUpClass.__func__)
 setUp=_fixture_test_category2_frequency_state.FrequencyStateTests.setUp
 add=_fixture_test_category2_frequency_state.FrequencyStateTests.add
 restored=_fixture_test_category2_frequency_state.FrequencyStateTests.restored
 turn=_fixture_test_category2_frequency_state.FrequencyStateTests.turn
 use=_fixture_test_category2_frequency_state.FrequencyStateTests.use
 def snap(self):return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(c) for c in self.e.gm.everyone]),{id(self.r):self.r})
 def test_all_eight_vitamins_stop_at_shared_five_and_actual_extra_dose_cannot_change_state(self):
  for uid in sorted(V.ALL_ITEMS):
   self.setUp();self.a.spec['items']={'타우린':5}
   for _ in range(5):self.e.use_item(self.a,'타우린',self.p)
   before=deepcopy((self.p.spec['stats'],self.p.spec['tutor_points'],self.p.spec['vitamins']))
   self.a.spec['items']={uid:1};options={'selected_move':SCENE} if uid==V.PP else {}
   self.e.use_item(self.a,uid,self.p,**options)
   self.assertEqual(self.a.spec['items'][uid],0);self.assertEqual(M.vitamin_state(self.r,self.p.spec)['occupied'],5)
   self.assertEqual((self.p.spec['stats'],self.p.spec['tutor_points'],self.p.spec['vitamins']),before)
   loaded=self.restored();p=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
   self.assertEqual(M.vitamin_state(self.r,p.spec)['occupied'],5);self.assertNotIn('vitamin_special_uses',p.spec)
 def test_at_will_pp_up_has_no_effect_but_keeps_its_actual_once_only_dose_after_rest_and_restore(self):
  mid='move/단단해지기';self.e.gm.set_move(self.p,mid,True,reason='actual learned move');self.a.spec['items']={V.PP:2}
  self.assertEqual(self.e.use_item(self.a,V.PP,self.p,selected_move=mid),(0,0))
  record=self.p.spec['vitamin_special_uses'][V.PP]
  self.assertEqual(record['base_frequency'],['at_will',1]);self.assertFalse(record['effective']);self.assertEqual(M.vitamin_state(self.r,self.p.spec)['occupied'],1)
  self.assertEqual(F.move_frequency(self.e,mid,self.p),('at_will',1));self.assertEqual(self.a.spec['items'][V.PP],1)
  D.new_day(self.p);D.extended_rest(self.e,self.p,4);snapshot=self.e.gm.snapshot();loaded=self.restored()
  for e in (self.e,loaded):
   a=next(c for c in e.gm.everyone if c.entity_id==self.a.entity_id);p=next(c for c in e.gm.everyone if c.entity_id==self.p.entity_id)
   e.use_item(a,V.PP,p,selected_move=SCENE)
   self.assertEqual(F.move_frequency(e,SCENE,p),('scene',2));self.assertEqual(p.spec['vitamin_special_uses'][V.PP],record)
   self.assertEqual(a.spec['items'][V.PP],0);self.assertEqual(len(p.spec['vitamins']),1)
  self.e.gm.restore(snapshot);self.assertEqual(self.a.spec['items'][V.PP],1);self.assertEqual(len(self.p.spec['vitamins']),1)
 def test_upgraded_eot_scene_and_daily_limits_drive_actual_native_moves_and_both_restore_paths(self):
  for mid in ('move/용의춤',SCENE,DAILY):
   self.setUp();self.e.gm.set_move(self.p,mid,True,reason='actual selected learned move');self.a.spec['items']={V.PP:1}
   self.e.use_item(self.a,V.PP,self.p,selected_move=mid)
   def cast():
    if mid==DAILY:self.e.end_scene()
    if mid==SCENE:self.turn(self.p)
    self.turn(self.p);self.use(self.p,mid)
   cast();cast();self.assertEqual(self.p.move_uses[mid],2)
   original=self.e;pid=self.p.entity_id;aid=self.a.entity_id;snapshot=original.gm.snapshot();loaded=self.restored()
   for engine in (original,loaded):
    self.e=engine;self.p=next(c for c in engine.gm.everyone if c.entity_id==pid);self.a=next(c for c in engine.gm.everyone if c.entity_id==aid);self.actors=[self.a,self.p]
    cast();self.assertEqual(self.p.move_uses[mid],3)
    cast();self.assertEqual(self.p.move_uses[mid],4 if mid=='move/용의춤' else 3)
   original.gm.restore(snapshot);p=next(c for c in original.gm.everyone if c.entity_id==pid)
   self.assertEqual(p.move_uses[mid],2);self.assertEqual(p.spec['vitamin_special_uses'][V.PP]['move_id'],mid)
 def test_non_vitamin_history_and_bad_special_application_records_cannot_grant_or_persist(self):
  self.a.spec['items']={V.PP:2};self.e.use_item(self.a,V.PP,self.p,selected_move=SCENE);baseline=deepcopy(self.p.spec)
  for mutate in (lambda s:s['vitamins'].append('상처약'),lambda s:s['vitamins'].extend(['타우린']*5),lambda s:s['vitamin_special_uses'][V.PP].update(applied_at=True),lambda s:s['vitamin_special_uses'][V.PP].update(effective=False)):
   self.p.spec.clear();self.p.spec.update(deepcopy(baseline));mutate(self.p.spec);before=self.snap()
   for action in (lambda:self.e.use_item(self.a,V.PP,self.p,selected_move=SCENE),self.e.export_state):
    with self.assertRaises(ValueError):action()
    self.assertEqual(self.snap(),before)
  self.p.spec.clear();self.p.spec.update(deepcopy(baseline));self.p.spec['vitamin_special_uses'][V.PP]['applied_at']=True
  with patch.object(V,'validate',return_value=True):payload=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)

if __name__=='__main__':unittest.main()
