from pathlib import Path
import sys,unittest,copy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import acquisition_qualification as Q
import test_foundation_policy_replay as F
from state_codec import dump_engine

class QualificationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.PolicyReplayTests.setUpClass()
 def declaration(self):
  return dict(source_id='combat/struggle',provider='teacher-A',stage='creation',
   checks=[Q.check('skill','prerequisite',False,'skill prerequisite'),Q.check('rank','rank',True,'maximum rank')],
   waivers=[dict(source_id='combat/struggle',provider='teacher-A',stage='creation',checks=['skill'],reason='explicit provider grant')])
 def test_provider_stage_and_source_scope_do_not_leak(self):
  declaration=self.declaration();self.assertEqual(Q.evaluate(**declaration)['status'],'qualified')
  for field in ('provider','stage','source_id'):
   altered=copy.deepcopy(declaration);altered[field]='other'
   self.assertEqual(Q.evaluate(**altered)['status'],'denied')
 def test_rank_repeat_selection_constraints_cannot_be_waived(self):
  for kind in ('rank','repeat','selection','capacity','stage'):
   declaration=self.declaration();declaration['checks'][1].update(kind=kind,passed=False)
   self.assertEqual(Q.evaluate(**declaration)['status'],'denied')
   declaration['waivers'][0]['checks'].append('rank')
   with self.assertRaises(ValueError):Q.evaluate(**declaration)
 def test_unknown_and_malformed_facts_are_not_qualified(self):
  declaration=self.declaration();declaration['waivers']=[];declaration['checks'][0]['passed']=None
  self.assertEqual(Q.evaluate(**declaration)['status'],'pending')
  declaration['checks'][0]['passed']=1
  with self.assertRaises(ValueError):Q.evaluate(**declaration)
 def test_external_policy_evaluates_without_granting_or_mutating(self):
  f=F.PolicyReplayTests();f.setUp();declaration=self.declaration();declaration.pop('source_id')
  f.row['values']={'qualification':declaration}
  before=dump_engine(f.e)
  result=f.e.evaluate_source_policy_qualification(f.c,f.c,f.doc)
  self.assertEqual(result['status'],'PolicyQualificationEvaluated')
  self.assertEqual(result['qualification']['status'],'qualified')
  self.assertFalse(result['qualification']['acquired']);self.assertFalse(result['effects_executed'])
  self.assertEqual(dump_engine(f.e),before)
  self.assertEqual(result['selected_id'],'combat/struggle')

 def test_json_stage_rank_cap_and_locked_selection_do_not_leak(self):
  f=F.PolicyReplayTests();f.setUp();declaration=self.declaration();declaration.pop('source_id')
  declaration['rank_request']={'selection':'focus','requested_rank':4,'policies':{
   'creation':{'max_rank':3,'blocked_selections':['athletics']},
   'advancement':{'max_rank':4,'blocked_selections':[]}}}
  f.row['values']={'qualification':declaration}
  def result():return f.e.evaluate_source_policy_qualification(f.c,f.c,f.doc)['qualification']
  self.assertEqual(result()['status'],'denied')
  declaration['rank_request']['requested_rank']=3
  self.assertEqual(result()['status'],'qualified')
  declaration['rank_request']['selection']='athletics'
  self.assertEqual(result()['status'],'denied')
  declaration['stage']='advancement';declaration['checks'][0]['passed']=True
  declaration['rank_request']['requested_rank']=4
  self.assertEqual(result()['status'],'qualified')
  declaration['stage']='unknown'
  with self.assertRaises(ValueError):result()
 def test_predicates_keep_unknown_and_reject_boolean_as_rank(self):
  self.assertIsNone(Q.predicate({'op':'all','terms':[True,None]}))
  self.assertFalse(Q.predicate({'op':'all','terms':[False,None]}))
  self.assertTrue(Q.predicate({'op':'any','terms':[True,None]}))
  with self.assertRaises(ValueError):Q.predicate({'op':'le','left':True,'right':3})
  self.assertFalse(Q.predicate({'op':'in','left':True,'right':[1]}))
  d=self.declaration();d['waivers']=[]
  d['checks'][0].pop('passed');d['checks'][0]['test']={'op':'ge','left':None,'right':3}
  result=Q.evaluate(**d)
  self.assertEqual(result['status'],'pending');self.assertIn('test',result['checks'][0])

 def grant_fixture(self):
  import test_foundation_policy_grant_payments as GR
  GR.PolicyGrantTests.setUpClass();f=GR.PolicyGrantTests();f.setUp()
  f.op['qualification']={'provider':f.a.entity_id,'stage':'teaching',
    'checks':[Q.check('capacity','capacity',True,'available capacity')],'waivers':[]}
  return f
 def test_qualified_grant_commits_payment_and_historical_qualification_once(self):
  from state_codec import load_engine
  f=self.grant_fixture();doc=f.load(f.doc(f.op))
  first=f.run_policy(doc,request_id='qualified/one')
  self.assertEqual(first['qualification']['status'],'qualified')
  self.assertEqual(f.c.spec['tutor_points'],2)
  restored=load_engine(f.r,dump_engine(f.e));a,c=restored.everyone;before=dump_engine(restored)
  replay=restored.execute_source_policy_grants(a,c,doc,request_id='qualified/one')
  self.assertTrue(replay['replayed']);self.assertEqual(replay['qualification'],first['qualification'])
  self.assertEqual(dump_engine(restored),before)
 def test_denied_pending_and_wrong_provider_grants_change_nothing(self):
  import source_policy as P
  for value in (False,None):
   f=self.grant_fixture();f.op['qualification']['checks'][0]['passed']=value
   before=dump_engine(f.e)
   with self.assertRaises(P.PolicyExecutionPending if value is None else ValueError):f.run_policy(f.doc(f.op))
   self.assertEqual(dump_engine(f.e),before)
  f=self.grant_fixture();f.op['qualification']['provider']='other-provider';before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'actual granting actor'):f.run_policy(f.doc(f.op))
  self.assertEqual(dump_engine(f.e),before)

 def test_acquisition_reads_live_target_state_and_replay_keeps_original_evidence(self):
  f=self.grant_fixture()
  f.op['qualification']['checks']=[{'id':'level','kind':'prerequisite','reason':'level requirement',
   'test':{'op':'ge','left':{'$input':'level'},'right':10}}]
  doc=f.load(f.doc(f.op,inputs={'level':{'authority':'state','type':'integer','question':'Actual target level',
   'binding':{'subject':'target','field':'level'}}}))
  f.c.level=9;before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'qualification denied'):f.run_policy(doc,request_id='live/one')
  self.assertEqual(dump_engine(f.e),before)
  f.c.level=10;first=f.run_policy(doc,request_id='live/one')
  self.assertEqual(first['qualification']['checks'][0]['test']['left'],10)
  f.c.level=9;before=dump_engine(f.e)
  replay=f.run_policy(doc,request_id='live/one')
  self.assertTrue(replay['replayed']);self.assertEqual(replay['qualification'],first['qualification'])
  self.assertEqual(dump_engine(f.e),before)

 def replacement_fixture(self):
  f=self.grant_fixture();f.c.spec['capabilities']=['cap/a']
  f.op['replacement']={'provider':f.a.entity_id,'stage':'gift','child_id':'child/a',
   'original':'cap/a','choice':'cap/new','candidates':{'cap/new':[Q.check('eligible','prerequisite',True,'candidate eligible')]}}
  return f
 def test_duplicate_replacement_binds_provider_and_saved_paid_child(self):
  import state_grants as G
  from state_codec import load_engine
  f=self.replacement_fixture();doc=f.load(f.doc(f.op))
  first=f.run_policy(doc,request_id='replace/one')
  self.assertTrue(first['replacement']['duplicate'])
  self.assertEqual(first['replacement']['provider'],f.a.entity_id)
  self.assertIn('cap/new',G.effective(f.c,'capabilities'))
  self.assertIn('cap/a',G.effective(f.c,'capabilities'))
  self.assertEqual(f.c.spec['tutor_points'],2)
  restored=load_engine(f.r,dump_engine(f.e));a,c=restored.everyone;before=dump_engine(restored)
  result=restored.execute_source_policy_grants(a,c,doc,request_id='replace/one')
  self.assertTrue(result['replayed']);self.assertEqual(result['replacement'],first['replacement'])
  self.assertEqual(dump_engine(restored),before)
 def test_invalid_replacement_never_spends_or_grants(self):
  import source_policy as P
  for mode in ('not_duplicate','wrong_provider','outside','already_owned','denied','pending'):
   f=self.replacement_fixture();r=f.op['replacement']
   if mode=='not_duplicate':f.c.spec['capabilities']=[]
   elif mode=='wrong_provider':r['provider']='someone_else'
   elif mode=='outside':r['choice']='outside'
   elif mode=='already_owned':f.c.spec['capabilities'].append('cap/new')
   else:r['candidates']['cap/new'][0]['passed']=None if mode=='pending' else False
   before=dump_engine(f.e)
   with self.assertRaises(P.PolicyExecutionPending if mode=='pending' else ValueError):f.run_policy(f.doc(f.op),request_id='bad')
   self.assertEqual(dump_engine(f.e),before)

if __name__=='__main__':unittest.main()
