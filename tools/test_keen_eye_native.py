"""Native Keen Eye and R755 one-round grant. Source-only candidate tests."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import book_survivalist_fixture as FIX
import trainer_feature_acquisition as ACQUIRE
import survivalist_class as SC
import state_grants as GRANTS
import effects as FX
import keen_eye as KEEN
import vision_impairment as VISION

class KeenEyeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

 def setUp(self):
  previous=self.rules.rulings;self.rules.rulings=deepcopy(previous)
  self.addCleanup(setattr,self.rules,'rulings',previous)

 def world(self,*,actual=False,edition='csv_hb',terrain='mountain'):
  w=FIX.scene(self.rules,feats=() if actual else (SC.CLASS,SC.NATURAL,SC.TRAPPER))
  e,a,p=(w[k] for k in ('engine','trainer','partner'))
  if actual:
   GRANTS.grant(p,'abilities','날카로운눈','gm/keen-eye-fixture','gm',rule_id=KEEN.SOURCE)
   GRANTS.reconcile(e,p)
  else:
   ACQUIRE.acquire_static(e,a,SC.GUIDE,acquisition_request_id='keen-eye/guide',selection={'edition':edition})
  FIX.env(e,a,terrain);FIX.env(e,p,terrain);FIX.battle(e,a)
  return w

 def guide(self,w,**options):
  return w['engine'].survivalist_activity(w['trainer'],'wilderness_guide',reason='actual audible Guide',**options)

 def effect(self,e,a,p,value,source,*,timed=False):
  effect={'type':'accuracy_mod','target':'target','value':value}
  if timed:effect['until']='encounter_end'
  return e.apply_effect(a,p,effect,15,True,0,source)

 def test_actual_and_virtual_share_loss_and_ordinary_blindness_immunity(self):
  for actual in (True,False):
   with self.subTest(actual=actual):
    w=self.world(actual=actual);e,p,foe=(w[k] for k in ('engine','partner','foe'))
    original=list(p.abilities)
    if not actual:self.guide(w);self.assertEqual(p.abilities,original)
    self.assertTrue(KEEN.active(e,p));before=p.accuracy_stage
    FX.apply_stage_changes(e,foe,p,{'acc':-2,'atk':-2},source_id='gm/stage-loss-case')
    self.assertEqual(p.accuracy_stage,before);self.assertEqual(p.stages['atk'],-2)
    self.effect(e,foe,p,-2,'gm/accuracy-loss-case');self.assertEqual(p.accuracy_stage,before)
    FX.apply_stage_changes(e,p,p,{'acc':2},source_id='gm/accuracy-bonus-case')
    self.assertEqual(p.accuracy_stage,before+2)
    self.assertFalse(e.apply_status(p,'실명',source='gm/blindness-case'))
    self.assertNotIn('실명',p.conditions)
    self.assertTrue(e.validate_state()['valid'])

 def test_penalties_are_removed_before_they_cancel_positive_timed_bonuses(self):
  for actual in (True,False):
   with self.subTest(actual=actual):
    w=self.world(actual=actual);e,a,p,foe=(w[k] for k in ('engine','trainer','partner','foe'))
    if not actual:self.guide(w)
    move=self.rules.move('move/냉동빔')
    threshold=move['ac']+foe.evasion(move['class'],engine=e,attacker=p,ignore_nonstats=True)
    roll=max(2,threshold-1);self.assertLess(roll,20)
    self.effect(e,a,p,2,'gm/positive-timed-accuracy',timed=True)
    self.effect(e,foe,p,-6,'gm/negative-timed-accuracy',timed=True)
    self.assertTrue(e.accuracy_check(p,foe,move,situational=-6,fixed_roll=roll)[0])
    loaded,index=FIX.restore(self.rules,e)
    self.assertTrue(loaded.accuracy_check(index[p.entity_id],index[foe.entity_id],move,situational=-6,fixed_roll=roll)[0])
    self.assertTrue(loaded.validate_state()['valid'])

 def test_nonstat_evasion_is_ignored_but_stats_and_natural_one_still_matter(self):
  w=self.world(actual=True);e,p,foe=(w[k] for k in ('engine','partner','foe'))
  move=self.rules.move('move/냉동빔')
  e.gm.set_stage(foe,'eva',value=6,reason='explicit GM non-stat evasion')
  stats=foe.evasion(move['class'],engine=e,ignore_nonstats=True);self.assertGreater(stats,0)
  self.assertEqual(foe.evasion(move['class'],attacker=p,engine=e,conditional_bonus=3),stats)
  threshold=move['ac']+stats
  self.assertTrue(e.accuracy_check(p,foe,move,fixed_roll=threshold)[0])
  self.assertFalse(e.accuracy_check(p,foe,move,fixed_roll=threshold-1)[0])
  self.assertFalse(e.accuracy_check(p,foe,move,fixed_roll=1)[0])
  self.assertTrue(e.accuracy_check(p,foe,move,fixed_roll=20)[0])

 def test_total_blindness_stays_and_still_prohibits_priority(self):
  w=self.world(actual=True);e,p,foe=(w[k] for k in ('engine','partner','foe'))
  self.assertTrue(e.apply_status(p,'완전-실명',source='gm/total-blindness-case'))
  self.assertEqual(VISION.accuracy_level(e,p),'total')
  with self.assertRaisesRegex(ValueError,'Total Blindness'):
   VISION.require_move(e,p,self.rules.move('move/전광석화'))
  move=self.rules.move('move/냉동빔');threshold=move['ac']+foe.evasion(move['class'],engine=e,attacker=p)
  self.assertTrue(e.accuracy_check(p,foe,move,fixed_roll=threshold)[0])
  self.assertIn('완전-실명',p.conditions)

 def test_virtual_restore_same_count_expiry_and_encounter_cleanup(self):
  w=self.world();e,a,p,foe=(w[k] for k in ('engine','trainer','partner','foe'))
  self.guide(w);loaded,index=FIX.restore(self.rules,e);q=index[p.entity_id]
  self.assertTrue(KEEN.active(loaded,q));self.assertFalse(KEEN.active(loaded,index[foe.entity_id]))
  loaded.end_of_turn(index[a.entity_id]);loaded.end_round();loaded.start_round(loaded.everyone)
  loaded.at_initiative_count(21);self.assertTrue(KEEN.active(loaded,q))
  loaded.at_initiative_count(20);self.assertFalse(KEEN.active(loaded,q))
  FX.apply_stage_changes(loaded,index[foe.entity_id],q,{'acc':-2},source_id='gm/expired-loss-case')
  self.assertEqual(q.accuracy_stage,-2)
  self.assertTrue(loaded.apply_status(q,'실명',source='gm/expired-blindness-case'))
  e.end_encounter(round_elapsed_seconds=10);self.assertFalse(KEEN.active(e,p))
  self.assertTrue(loaded.validate_state()['valid'])

 def test_existing_ordinary_blindness_and_low_light_are_projected_without_erasing_the_source(self):
  w=self.world();e,a,p=(w[k] for k in ('engine','trainer','partner'))
  self.assertTrue(e.apply_status(p,'실명',source='gm/before-guide-blindness'))
  self.assertEqual(VISION.accuracy_level(e,p),'ordinary')
  self.assertEqual(p.evasion('물리',engine=e),0)
  self.guide(w)
  self.assertEqual(VISION.accuracy_level(e,p),'none')
  self.assertGreater(p.evasion('물리',engine=e),0)
  self.assertIn('실명',p.conditions)
  loaded,index=FIX.restore(self.rules,e);q=index[p.entity_id]
  self.assertEqual(VISION.accuracy_level(loaded,q),'none')
  loaded.end_of_turn(index[a.entity_id]);loaded.end_round();loaded.start_round(loaded.everyone)
  loaded.at_initiative_count(20)
  self.assertEqual(VISION.accuracy_level(loaded,q),'ordinary')
  w=self.world(actual=True);e,p=w['engine'],w['partner']
  FIX.env(e,p,'mountain',light='low_light')
  self.assertEqual(VISION.accuracy_level(e,p),'none')
  FIX.env(e,p,'mountain',light='complete_darkness')
  self.assertEqual(VISION.accuracy_level(e,p),'total')

 def test_book_other_terrain_and_suppression_are_controls(self):
  for edition,terrain in (('book','mountain'),('csv_hb','forest')):
   with self.subTest(edition=edition,terrain=terrain):
    w=self.world(edition=edition,terrain=terrain)
    self.guide(w,**({'terrain_name':terrain} if edition=='book' else {}))
    self.assertFalse(KEEN.active(w['engine'],w['partner']))
  w=self.world(actual=True);e,p,foe=(w[k] for k in ('engine','partner','foe'))
  p.abilities_suppressed=True
  self.assertFalse(KEEN.active(e,p))
  FX.apply_stage_changes(e,foe,p,{'acc':-2},source_id='gm/suppressed-loss-case')
  self.assertEqual(p.accuracy_stage,-2)
  self.assertTrue(e.apply_status(p,'실명',source='gm/suppressed-blindness-case'))

if __name__=='__main__':unittest.main()

