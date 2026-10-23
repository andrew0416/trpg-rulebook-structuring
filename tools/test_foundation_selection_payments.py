"""Real source alternatives retain costs during native grant execution.
This certifies the selection/payment bridge, not all Mixed Sweeper eligibility.
"""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_grant_payments as fixture
from ruleset import RuleFilter,RuleSelection
from state_codec import dump_engine,load_engine
import world_entities as W

class SelectionPaymentsTests(unittest.TestCase):
 setUpClass=classmethod(fixture.PolicyGrantTests.setUpClass.__func__)
 setUp=fixture.PolicyGrantTests.setUp
 def document(self,selected):
  definitions=[];variants=[]
  for label,file,locator,cost in [('errata','input/supp-errata.md',{'lines':[793,796]},2),('csv','input/db/poke-edges.csv',{'record':65},3)]:
   uid='authored/selection-payment/mixed-'+label
   source={'file':file,'sha256':sha256((ROOT/file).read_bytes()).hexdigest()}
   definitions.append({'id':uid,'title':'Mixed Sweeper '+label,'source':source,'locator':locator,'tags':['homebrew'] if label=='csv' else [],'rationale':'Explicit selected source cost, separate from same-named body definition.'})
   variants.append({'rule_id':uid,'source':source,'inputs':{},'values':{'grant_operation':{'type':'acquire','group_id':'mixed/grant','points':cost,'reason':'host admits this acquisition; selection bridge test','grants':[{'source_id':'mixed/ability','field':'abilities','value':'트위스트파워'}]}}})
  self.r.ruleset=RuleFilter({'exclude_units':[r['id'] for i,r in enumerate(definitions) if i!=selected]})
  self.r.selection=RuleSelection(self.r.ruleset,list(self.r.selection.units.values()))
  document={'schema':1,'id':'mixed/selection-payment','variants':variants}
  self.r.load_source_policy_package({'schema':1,'sources':definitions,'policies':[document]})
  return self.r.source_policy_document(document['id'])
 def execute(self,document):return self.e.execute_source_policy_grants(self.a,self.c,document,request_id='actual/mixed')
 def test_selected_errata_and_csv_each_charge_only_their_own_cost_and_restore(self):
  for index,cost in ((0,2),(1,3)):
   with self.subTest(cost=cost):
    self.setUp();document=self.document(index);before_stats=deepcopy(self.c.stats)
    result=self.execute(document)
    self.assertEqual(result['status'],'PolicyGrantsCompleted')
    self.assertEqual(self.c.spec['tutor_points'],3-cost)
    self.assertIn('트위스트파워',self.c.abilities)
    self.assertEqual(self.c.stats,before_stats)  # No old body stat bonus.
    self.assertEqual(result['grant_result']['rule_id'],document['variants'][index]['rule_id'])
    loaded=load_engine(self.r,dump_engine(self.e));actors=W.actor_index(loaded);before=dump_engine(loaded)
    replay=loaded.execute_source_policy_grants(actors[self.a.entity_id],actors[self.c.entity_id],document,request_id='actual/mixed')
    self.assertTrue(replay['replayed']);self.assertEqual(dump_engine(loaded),before)
 def test_selected_csv_cannot_borrow_cheaper_errata_cost(self):
  document=self.document(1);self.c.spec['tutor_points']=2;before=dump_engine(self.e)
  with self.assertRaises(ValueError):self.execute(document)
  self.assertEqual(dump_engine(self.e),before);self.assertNotIn('트위스트파워',self.c.abilities)
 def test_changed_selected_source_cannot_spend_or_replay_after_grant(self):
  document=self.document(0);self.execute(document);before=dump_engine(self.e);original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged' if path.name=='supp-errata.md' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):self.execute(document)
  self.assertEqual(dump_engine(self.e),before)

class PreservedRiderGrantTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=fixture.Rules(ROOT)
 setUp=fixture.PolicyGrantTests.setUp
 def document(self):
  uid='feat/래밍-스피드';source=self.r.selection.units[uid]['source']
  document={'schema':1,'id':'selection/preserved-rider','variants':[{'rule_id':uid,
   'source':{'file':'input/'+source['file'],'sha256':source['sha256']},
   'inputs':{'owned':{'type':'integer','authority':'state','question':'Actual acquired provider?',
     'binding':{'subject':'actor','field':'owned_rule_count','rule_id':uid}},
    'ability':{'type':'string','authority':'context','definition_kind':'ability','choices':['ability/도움닫기'],'question':'Exact preserved ability definition'}},
   'when':{'op':'ge','left':{'$input':'owned'},'right':1},
   'values':{'grant_operation':{'type':'acquire','group_id':'rider/preserved','points':2,
    'owner_id':self.a.entity_id,'lifetime':'your_pokemon','reason':'source-selection acceptance of acquired Ramming Speed provider',
    'grants':[{'source_id':'rider/run-up','field':'abilities','value':{'$input':'ability'}}]}}}]}
  self.r.load_source_policy_package({'schema':1,'sources':[],'policies':[document]})
  return self.r.source_policy_document(document['id'])
 def execute(self,doc):return self.e.execute_source_policy_grants(self.a,self.c,doc,context={'ability':'ability/도움닫기'},request_id='rider/source-selection')
 def test_errata_preserved_run_up_keeps_paid_provider_and_restore(self):
  self.assertIn('errata',self.r.ruleset.sources)
  self.a.spec['feats']=['feat/래밍-스피드'];doc=self.document()
  out=self.execute(doc)
  self.assertEqual(out['status'],'PolicyGrantsCompleted')
  self.assertEqual(self.c.spec['tutor_points'],1);self.assertIn('도움닫기',self.c.abilities)
  row=self.c.spec['state_grants']['sources']['rider/run-up']
  self.assertEqual(row['rule_id'],'feat/래밍-스피드');self.assertEqual(row['grants']['abilities'],['도움닫기'])
  loaded=load_engine(self.r,dump_engine(self.e));actors=W.actor_index(loaded);before=dump_engine(loaded)
  replay=loaded.execute_source_policy_grants(actors[self.a.entity_id],actors[self.c.entity_id],doc,context={'ability':'ability/도움닫기'},request_id='rider/source-selection')
  self.assertTrue(replay['replayed']);self.assertEqual(dump_engine(loaded),before)
  self.assertIn('도움닫기',actors[self.c.entity_id].abilities)
 def test_missing_provider_low_tp_or_changed_source_cannot_grant(self):
  doc=self.document();before=dump_engine(self.e)
  self.assertEqual(self.execute(doc)['status'],'PolicyNotApplicable');self.assertEqual(dump_engine(self.e),before)
  self.a.spec['feats']=['feat/래밍-스피드'];self.c.spec['tutor_points']=1;before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'insufficient'):self.execute(doc)
  self.assertEqual(dump_engine(self.e),before)
  self.c.spec['tutor_points']=3;native=Path.read_bytes
  for name in ('ch04-trainer-classes.md','abilities.csv'):
   before=dump_engine(self.e)
   def changed(path):return native(path)+(b'changed' if path.name==name else b'')
   with patch.object(Path,'read_bytes',changed):
    with self.assertRaisesRegex(ValueError,'changed'):self.execute(doc)
   self.assertEqual(dump_engine(self.e),before)

if __name__=='__main__':unittest.main()
