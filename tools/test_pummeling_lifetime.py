"""Earned Momentum survives changes to the rank provider until its own termination."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools'),str(ROOT/'examples')]
from engine import Rules
from rulings import Rulings
from declared_skill_ranks import configure
from native_scenario_fixture import assert_rejected_unchanged
import test_book_martial_artist as TB
import test_core_irreversible_retraining as RT
import martial_artist as MA
import skill_modifiers as S
import state_fields as F
import action_points as AP
import state_codec as CODEC
import trainer_feature_acquisition as FEATURES

VIRTUOSO='edge/거장'

class PummelingLifetimeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.base=Rules(ROOT,ruleset='core')
 def fixture(self,*,virtuoso=False,combat=6,declared=False):
  rules=copy(self.base);rules.rulings=Rulings()
  if declared:configure(rules)
  f=TB.MartialArtistTests();f.rules=rules
  actual=TB.Combatant
  def actor(rules,spec):
   if spec['id']=='trainer/martial' and virtuoso:
    spec['edges'].append(VIRTUOSO);spec['edge_choices']={VIRTUOSO:['전투']}
   return actual(rules,spec)
  with patch.object(TB,'Combatant',side_effect=actor):f.setup(combat=combat)
  f.acquire(training=1);f.start();MA.arm(f.e,f.a,'pummeling_momentum',target=f.t)
  return f
 def hits(self,f,count):
  for i in range(count):
   if i:f.next()
   f.use('마하펀치',face=15)
 def retrain(self,f,uid=VIRTUOSO):
  options=RT.IrreversibleRetrainingTests().decisions(f.e,f.a,uid,request='momentum/'+uid)
  return f.e.retrain_trainer_source(f.a,uid,**options),options
 def test_native_virtuoso_withdrawal_retains_eight_for_accuracy_evasion_and_later_hits(self):
  f=self.fixture(virtuoso=True);self.hits(f,8)
  earned=deepcopy(f.a.spec[MA.TAG]);xp=f.a.spec['exp_bank'];ap=AP.available(f.a)
  result,options=self.retrain(f)
  self.assertEqual((result['xp_paid'],f.a.spec['exp_bank']),(1,xp-1))
  self.assertNotIn(VIRTUOSO,f.a.spec['edges']);self.assertNotIn(VIRTUOSO,f.a.spec['edge_choices'])
  self.assertEqual(S.effective_rank(f.e.r,f.a,'전투'),6)
  self.assertEqual(f.a.spec[MA.TAG],earned)
  f.restore();f.valid();self.assertEqual(MA.bonus(f.a,f.t),8)
  before=f.e.export_state();self.assertEqual(f.e.retrain_trainer_source(f.a,VIRTUOSO,**options),result)
  self.assertEqual(f.e.export_state(),before)
  ordinary=f.a.evasion('물리',attacker=f.u,engine=f.e)
  self.assertEqual(f.a.evasion('물리',attacker=f.t,engine=f.e),min(9,ordinary+8))
  move=f.e.r.move('move/마하펀치')
  self.assertTrue(f.e.accuracy_check(f.a,f.t,move,fixed_roll=2)[0])
  self.assertFalse(f.e.accuracy_check(f.a,f.u,move,fixed_roll=2)[0])
  f.next();f.use('마하펀치')
  self.assertEqual((MA.bonus(f.a,f.t),AP.available(f.a)),(8,ap))
  self.assertEqual(f.a.spec[MA.TAG]['completion_id'],earned['completion_id'])
  f.restore();f.valid()
 def test_declared_rank_drop_retains_earned_bonus_and_new_tag_uses_current_cap(self):
  for rank in (7,10):
   with self.subTest(rank=rank):
    f=self.fixture(combat=rank,declared=True);self.hits(f,rank)
    F.base_patch(f.a,{'skills':dict(f.a.spec['skills'],전투=6)},reason='Observed lower ordinary Combat rank')
    f.restore();f.valid();self.assertEqual(MA.bonus(f.a,f.t),rank)
    f.next();f.use('두번차기');f.e.end_of_turn(f.a)
    self.assertEqual(MA.bonus(f.a,f.t),rank)
    f.e.end_round();f.start();f.use('마하펀치',face=1);f.e.end_of_turn(f.a)
    self.assertNotIn(MA.TAG,f.a.spec)
    f.e.end_round();f.start();MA.arm(f.e,f.a,'pummeling_momentum',target=f.t)
    ap=AP.available(f.a);f.use('마하펀치',face=15)
    self.assertEqual((MA.bonus(f.a,f.t),f.a.spec[MA.TAG]['earned_rank'],AP.available(f.a)),(1,6,ap-1))
    f.restore();f.valid()
 def test_rank_increase_only_raises_future_gain_cap_and_declared_provider_change_keeps_history(self):
  f=self.fixture(combat='신화',declared=True);self.hits(f,7)
  self.assertEqual((f.a.spec[MA.TAG]['bonus'],f.a.spec[MA.TAG]['earned_rank']),(7,10))
  self.assertEqual(len(f.e.skill_roll(f.a,'전투',fixed=[1]*7).faces),7)
  f.e.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.신화.rank',8,
   reason='Campaign changes the declared rank while preserving its pool',rules=f.e.r)
  self.assertEqual(S.effective_rank(f.e.r,f.a,'전투'),8)
  self.assertEqual(f.a.spec[MA.TAG]['earned_rank'],10)
  f.next();f.use('마하펀치');self.assertEqual((MA.bonus(f.a,f.t),f.a.spec[MA.TAG]['earned_rank']),(8,8))
  f.e.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.신화.rank',12,
   reason='Campaign raises the declared rank while preserving its pool',rules=f.e.r)
  self.assertEqual((MA.bonus(f.a,f.t),f.a.spec[MA.TAG]['earned_rank']),(8,8))
  f.next();f.use('마하펀치');self.assertEqual((MA.bonus(f.a,f.t),f.a.spec[MA.TAG]['earned_rank']),(9,12))
  f.restore();f.valid()
  self.assertEqual((S.effective_rank(f.e.r,f.a,'전투'),len(f.e.skill_roll(f.a,'전투',fixed=[1]*7).faces)),(12,7))
 def test_new_gain_provenance_rejects_resealed_rank_bonus_acquisition_and_completion_changes(self):
  f=self.fixture(declared=True);self.hits(f,2)
  earned=deepcopy(f.a.spec[MA.TAG]);f.next();f.use('두번차기')
  nonpunch=list(f.e._move_completions)[-1]
  for change in ({'earned_rank':10,'bonus':7},{'completion_id':nonpunch},
                 {'acquisition':'stale/acquisition'},{'target_id':f.u.entity_id}):
   with self.subTest(change=change):
    original=deepcopy(f.a.spec[MA.TAG]);f.a.spec[MA.TAG].update(change);MA._seal_tag(f.a.spec[MA.TAG])
    with self.assertRaisesRegex(ValueError,'provenance|observation|completed hit'):MA.validate(f.e)
    f.a.spec[MA.TAG]=original
  f.a.spec[MA.TAG].pop('earned_rank');MA._seal_tag(f.a.spec[MA.TAG])
  with self.assertRaisesRegex(ValueError,'earned-rank observation missing'):MA.validate(f.e)
  f.a.spec[MA.TAG]=original
  completed=f.e._move_completions[earned['completion_id']];observation=completed.pop(MA.TAG)
  with self.assertRaisesRegex(ValueError,'earned-rank observation changed'):MA.validate(f.e)
  completed[MA.TAG]=observation;f.restore();f.valid()
 def test_achievement_withdrawal_expires_history_and_stale_acquisition_cannot_return(self):
  f=self.fixture(virtuoso=True);self.hits(f,7)
  old=deepcopy(f.a.spec[MA.TAG]);self.retrain(f,MA.ACHIEVEMENT)
  self.assertNotIn(MA.TAG,f.a.spec);self.assertEqual(MA.bonus(f.a,f.t),0)
  FEATURES.acquire_static(f.e,f.a,MA.ACHIEVEMENT,acquisition_request_id='martial/achievement/reacquired')
  f.a.spec[MA.TAG]=old
  with self.assertRaisesRegex(ValueError,'provenance'):MA.validate(f.e)
  f.a.spec.pop(MA.TAG);f.restore();f.valid()
  f.next();MA.arm(f.e,f.a,'pummeling_momentum',target=f.t);f.use('마하펀치')
  self.assertEqual(MA.bonus(f.a,f.t),1)
  self.assertNotEqual(f.a.spec[MA.TAG]['acquisition'],old['acquisition'])
 def test_provider_retraining_failure_is_atomic_and_retry_preserves_live_tag(self):
  f=self.fixture(virtuoso=True);self.hits(f,7)
  options=RT.IrreversibleRetrainingTests().decisions(f.e,f.a,VIRTUOSO,request='momentum/failure')
  import trainer_xp_payments as XP
  with patch.object(XP,'mark_used',side_effect=ValueError('late retraining failure')):
   assert_rejected_unchanged(f.e,lambda:f.e.retrain_trainer_source(f.a,VIRTUOSO,**options),reason_pattern='late retraining failure')
  f.e.retrain_trainer_source(f.a,VIRTUOSO,**options)
  self.assertEqual((MA.bonus(f.a,f.t),S.effective_rank(f.e.r,f.a,'전투')),(7,6))
  f.restore();f.valid()
 def test_legacy_tag_keeps_original_validation_and_upgrades_on_its_next_punch(self):
  f=self.fixture();self.hits(f,2)
  f.a.spec[MA.TAG].pop('earned_rank');MA._seal_tag(f.a.spec[MA.TAG])
  f.e._move_completions[f.a.spec[MA.TAG]['completion_id']].pop(MA.TAG)
  f.restore();f.valid();self.assertIn('legacy_validation',f.a.spec[MA.TAG])
  self.assertNotIn('earned_rank',f.a.spec[MA.TAG])
  f.next();f.use('마하펀치')
  self.assertEqual((MA.bonus(f.a,f.t),f.a.spec[MA.TAG]['earned_rank']),(3,6))
  self.assertNotIn('legacy_validation',f.a.spec[MA.TAG])
  f.restore();f.valid()

 def test_valid_legacy_eight_restores_then_withdraws_provider_before_another_punch(self):
  f=self.fixture(virtuoso=True);self.hits(f,8)
  f.a.spec[MA.TAG].pop('earned_rank');MA._seal_tag(f.a.spec[MA.TAG])
  completion=f.a.spec[MA.TAG]['completion_id'];f.e._move_completions[completion].pop(MA.TAG)
  legacy=deepcopy(f.a.spec[MA.TAG]);MA.validate(f.e)
  self.assertEqual(f.a.spec[MA.TAG],legacy,'ordinary validation must not migrate')
  saved=f.e.export_state();self.assertEqual(f.a.spec[MA.TAG],legacy)
  self.assertEqual(saved['authentication'],CODEC.AUTH_NOTICE)
  bad=deepcopy(saved);changed=0
  for node in bad['nodes'].values():
   if node['kind']=='dict' and all(type(pair[0]) is str for pair in node['items']) and dict(node['items'])==legacy:
    invalid=dict(legacy,bonus=9);MA._seal_tag(invalid)
    node['items']=[[key,value] for key,value in invalid.items()];changed+=1
  self.assertEqual(changed,1)
  with self.assertRaisesRegex(CODEC.StateCodecError,'Pummeling Momentum bonus'):
   CODEC.load_engine(f.e.r,bad)
  self.assertEqual(f.a.spec[MA.TAG],legacy)
  f.restore();f.valid()
  upgraded=f.a.spec[MA.TAG]
  self.assertEqual(upgraded['legacy_validation'],{'tag':legacy,'rank_at_load':8})
  self.assertNotIn('earned_rank',upgraded)
  self.assertNotIn(MA.TAG,f.e._move_completions[completion],'migration cannot invent a native gain')
  self.assertEqual(f.e._state_codec_authentication,CODEC.AUTH_NOTICE)
  result,options=self.retrain(f)
  self.assertEqual((MA.bonus(f.a,f.t),S.effective_rank(f.e.r,f.a,'전투')),(8,6))
  before=f.e.export_state();self.assertEqual(f.e.retrain_trainer_source(f.a,VIRTUOSO,**options),result)
  self.assertEqual(f.e.export_state(),before)
  f.restore();f.valid()
  self.assertEqual(f.a.spec[MA.TAG]['legacy_validation'],{'tag':legacy,'rank_at_load':8})
  f.next();f.use('마하펀치')
  self.assertEqual(MA.bonus(f.a,f.t),8)
  self.assertNotIn('earned_rank',f.a.spec[MA.TAG])
  f.restore();f.valid()

if __name__=='__main__':unittest.main()
