"""Single-source retraining retires its current Edge choices with the owned source."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
from native_scenario_fixture import assert_rejected_unchanged
import test_book_martial_artist as TB
import test_core_irreversible_retraining as RT
import trainer_retraining as RETRAINING
import trainer_feature_acquisition as FEATURES
import skill_modifiers as SKILLS
import state_grants as GRANTS

VIRTUOSO='edge/거장'
ENHANCEMENT='edge/스킬-향상'

class RetrainingEdgeChoiceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def fixture(self,owned=VIRTUOSO,choice=VIRTUOSO,exp=100,repeated=False,extra_edges=()):
  f=TB.MartialArtistTests();f.rules=self.rules
  actual=TB.Combatant
  def actor(rules,spec):
   if spec['id']=='trainer/martial':
    spec['edges'] += [owned,ENHANCEMENT]+list(extra_edges)+([owned] if repeated else [])
    spec['edge_choices']={choice:['전투','육상'] if repeated else ['전투'],ENHANCEMENT:[['육상','곡예']]}
    spec['exp_bank']=exp
   return actual(rules,spec)
  with patch.object(TB,'Combatant',side_effect=actor):f.setup(combat=6)
  self.assertEqual(SKILLS.effective_rank(self.rules,f.a,'전투'),8)
  self.assertEqual(f.e.skill_roll(f.a,'육상',fixed=[1]*6).modifier,2)
  return f
 def decisions(self,f,uid=VIRTUOSO):
  return RT.IrreversibleRetrainingTests().decisions(f.e,f.a,uid,request='edge-choice/'+uid)
 def test_native_single_edge_aliases_restore_rank_roll_receipts_and_retry_once(self):
  for owned,choice in ((VIRTUOSO,VIRTUOSO),('Virtuoso','거장'),('거장','Virtuoso'),(VIRTUOSO,' virtuoso '),(VIRTUOSO,'C2CSV/input/db/edges.csv:R10:main')):
   with self.subTest(owned=owned,choice=choice):
    f=self.fixture(owned,choice);f.acquire(training=1)
    decision=self.decisions(f);source=RETRAINING.owned_source(f.e,f.a,VIRTUOSO)
    receipts=deepcopy(f.a.spec[FEATURES.LEDGER_KEY]);moves=list(f.a.moves)
    choices=deepcopy(f.a.spec['feature_choices']);abilities=deepcopy(f.a.abilities)
    retained=deepcopy({k:v for k,v in GRANTS.state(f.a)['sources'].items() if k!=source})
    result=f.e.retrain_trainer_source(f.a,VIRTUOSO,**decision)
    self.assertNotIn(owned,f.a.spec['edges'])
    self.assertNotIn(choice,f.a.spec['edge_choices'])
    self.assertEqual(f.a.spec['edge_choices'],{ENHANCEMENT:[['육상','곡예']]})
    self.assertEqual((SKILLS.rank(self.rules,f.a,'전투')[2],SKILLS.effective_rank(self.rules,f.a,'전투')),(6,6))
    self.assertEqual((len(f.e.skill_roll(f.a,'전투',fixed=[1]*6).faces),f.e.skill_roll(f.a,'육상',fixed=[1]*6).modifier),(6,2))
    self.assertEqual((f.a.spec['exp_bank'],result['xp_paid']),(99,1))
    self.assertEqual((f.a.spec[FEATURES.LEDGER_KEY],f.a.spec['feature_choices'],f.a.moves,f.a.abilities),(receipts,choices,moves,abilities))
    for key,row in retained.items():
     now=deepcopy(GRANTS.state(f.a)['sources'][key]);now.pop('withdrawal_dependencies',None)
     prior=deepcopy(row);prior.pop('withdrawal_dependencies',None)
     self.assertEqual(now,prior)
    ended=[x for x in GRANTS.state(f.a)['ended_sources'] if x['source_id']==source]
    self.assertEqual(len(ended),1);self.assertEqual(ended[0]['record']['retraining']['result'],result)
    f.valid();f.restore();f.valid()
    self.assertEqual(SKILLS.effective_rank(self.rules,f.a,'전투'),6)
    self.assertEqual(len(f.e.skill_roll(f.a,'전투',fixed=[1]*6).faces),6)
    before=f.e.export_state()
    self.assertEqual(f.e.retrain_trainer_source(f.a,VIRTUOSO,**decision),result)
    self.assertEqual(f.e.export_state(),before)
 def test_other_choice_edge_withdrawal_preserves_virtuoso_and_removes_only_its_bonus(self):
  f=self.fixture();decision=self.decisions(f,ENHANCEMENT)
  f.e.retrain_trainer_source(f.a,ENHANCEMENT,**decision)
  self.assertEqual(f.a.spec['edge_choices'],{VIRTUOSO:['전투']})
  self.assertEqual(SKILLS.effective_rank(self.rules,f.a,'전투'),8)
  self.assertEqual(f.e.skill_roll(f.a,'육상',fixed=[1]*6).modifier,0)
  f.restore();f.valid()
 def test_edge_choice_gm_cost_dependency_and_late_failure_reject_atomically(self):
  f=self.fixture();decision=self.decisions(f)
  assert_rejected_unchanged(f.e,lambda:f.e.retrain_trainer_source(f.a,VIRTUOSO,**dict(decision,gm_decision={'allowed':False,'reason':'GM refused'})),reason_pattern='allowed GM')
  import trainer_xp_payments as XP
  with patch.object(XP,'mark_used',side_effect=ValueError('late retraining failure')):
   assert_rejected_unchanged(f.e,lambda:f.e.retrain_trainer_source(f.a,VIRTUOSO,**decision),reason_pattern='late retraining')
  f=self.fixture(exp=0);decision=self.decisions(f)
  assert_rejected_unchanged(f.e,lambda:f.e.retrain_trainer_source(f.a,VIRTUOSO,**decision),reason_pattern='bank|enough|insufficient')
  f=self.fixture();sources=RT.IrreversibleRetrainingTests().sources(f.e,f.a)
  f.e.bind_grant_dependencies(f.a,sources[ENHANCEMENT],[sources[VIRTUOSO]])
  decision=self.decisions(f)
  assert_rejected_unchanged(f.e,lambda:f.e.retrain_trainer_source(f.a,VIRTUOSO,**decision),reason_pattern='retained grant depends')
 def test_multiple_actual_edge_acquisitions_keep_existing_retraining_limit(self):
  f=self.fixture(repeated=True)
  decision=dict(request_id='repeated',reason='GM considered source',gm_decision={'allowed':True,'reason':'GM considered source'},retained_dependencies={})
  assert_rejected_unchanged(f.e,lambda:f.e.retrain_trainer_source(f.a,VIRTUOSO,**decision),reason_pattern='one distinct acquired source')

 def test_native_approved_skill_stunt_choice_retires_with_its_source(self):
  import skill_stunts as STUNTS
  f=self.fixture(extra_edges=(STUNTS.SOURCE,))
  f.e.approve_skill_stunt(f.a,choice_id='narrow',skill='전투',use='controlled martial sparring',reason='GM approved narrow scene',approved=True)
  self.assertEqual(len(STUNTS.choices(f.e,f.a)),1)
  decision=self.decisions(f,STUNTS.SOURCE)
  f.e.retrain_trainer_source(f.a,STUNTS.SOURCE,**decision)
  self.assertEqual(STUNTS.choices(f.e,f.a),())
  self.assertEqual(f.a.spec['edge_choices'],{VIRTUOSO:['전투'],ENHANCEMENT:[['육상','곡예']]})
  self.assertEqual(SKILLS.effective_rank(self.rules,f.a,'전투'),8)
  f.restore();f.valid()

if __name__=='__main__':unittest.main()
