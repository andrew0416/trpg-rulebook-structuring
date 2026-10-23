from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_grant_payments as F
import state_grants as G
from state_codec import dump_engine,load_engine

class WithdrawalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.GrantPaymentTests.setUpClass()
 def fixture(self):
  f=F.GrantPaymentTests();f.setUp();f.buy(allocation={'child/a':1,'child/b':0,'child/c':0});return f
 def test_retained_dependent_blocks_refund_and_joint_withdrawal_pays_once(self):
  f=self.fixture();f.e.bind_grant_dependencies(f.c,'child/b',['child/a'])
  before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'retained grant depends'):f.refund(['child/a'])
  self.assertEqual(dump_engine(f.e),before)
  result=f.refund(['child/a','child/b']);self.assertEqual(result['tutor_points_refunded'],1)
  self.assertIn('witness/c',G.effective(f.c,'capabilities'))
  f.refund(['child/a','child/b']);self.assertEqual(f.c.spec['tutor_points'],3)
 def test_irreversible_use_survives_restore_and_blocks_every_revoke_path(self):
  f=self.fixture();f.e.record_irreversible_grant_use(f.c,'child/a',event_id='use/one',reason='consumed permanently')
  f.e.record_irreversible_grant_use(f.c,'child/a',event_id='use/one',reason='consumed permanently')
  loaded=load_engine(f.rules,dump_engine(f.e));c=loaded.everyone[2];before=dump_engine(loaded)
  with self.assertRaisesRegex(ValueError,'irreversible'):loaded.refund_grant_sources(c,['child/a'],request_id='refund',reason='test')
  self.assertEqual(dump_engine(loaded),before)
  with self.assertRaisesRegex(ValueError,'irreversible'):G.revoke(c,'child/a',engine=loaded)
  self.assertEqual(dump_engine(loaded),before)
 def test_dependency_rebinding_and_cycles_reject_without_mutation(self):
  f=self.fixture();f.e.bind_grant_dependencies(f.c,'child/b',['child/a']);before=dump_engine(f.e)
  with self.assertRaises(ValueError):f.e.bind_grant_dependencies(f.c,'child/b',[])
  with self.assertRaisesRegex(ValueError,'cyclic'):f.e.bind_grant_dependencies(f.c,'child/a',['child/b'])
  self.assertEqual(dump_engine(f.e),before)

 def test_no_refund_partial_withdrawal_needs_no_invented_allocation(self):
  f=F.GrantPaymentTests();f.setUp();f.buy()
  out=f.refund(['child/a'],refund_mode='none')
  self.assertEqual(out['tutor_points_refunded'],0);self.assertEqual(f.c.spec['tutor_points'],2)
  row=f.e.acquisition_receipts(f.c)[0]
  self.assertEqual(row['children'][0]['state'],'withdrawn_without_refund')
  self.assertIsNone(row['children'][0]['refund_allocation'])
  loaded=load_engine(f.rules,dump_engine(f.e));c=loaded.everyone[2];before=dump_engine(loaded)
  loaded.refund_grant_sources(c,['child/a'],request_id='refund/one',reason='explicit withdrawal',refund_mode='none')
  self.assertEqual(dump_engine(loaded),before)
  with self.assertRaises(ValueError):loaded.refund_grant_sources(c,['child/a'],request_id='refund/one',reason='explicit withdrawal')
  self.assertEqual(dump_engine(loaded),before)
 def test_json_cause_policy_gates_real_refund(self):
  import test_foundation_policy_grant_payments as P
  import source_policy as SP
  P.PolicyGrantTests.setUpClass();f=P.PolicyGrantTests();f.setUp();f.run_policy(f.doc(f.op))
  op=f.refund();op['withdrawal']={'cause':'retraining','policies':{
   'retraining':{'allowed':False,'refund_mode':'actual'},'expiry':{'allowed':True,'refund_mode':'none'}}}
  before=dump_engine(f.e)
  with self.assertRaisesRegex(ValueError,'cause denied'):f.run_policy(f.doc(op,'withdraw'))
  self.assertEqual(dump_engine(f.e),before)
  op['withdrawal']['policies']['retraining']['allowed']=None
  with self.assertRaises(SP.PolicyExecutionPending):f.run_policy(f.doc(op,'withdraw'))
  self.assertEqual(dump_engine(f.e),before)
  op['withdrawal']['cause']='expiry'
  result=f.run_policy(f.doc(op,'withdraw'),request_id='expiry/one')
  self.assertEqual(result['withdrawal']['cause'],'expiry')
  self.assertEqual(result['grant_result']['tutor_points_refunded'],0)
  self.assertEqual(f.c.spec['tutor_points'],2)

 def test_unallocated_partial_actual_refund_is_explicit_pending(self):
  import test_foundation_policy_grant_payments as P
  import source_policy as SP
  P.PolicyGrantTests.setUpClass();f=P.PolicyGrantTests();f.setUp();f.run_policy(f.doc(f.op))
  op=f.refund();op['sources']=['child/a'];before=dump_engine(f.e)
  with self.assertRaisesRegex(SP.PolicyExecutionPending,'allocation'):f.run_policy(f.doc(op,'partial'))
  self.assertEqual(dump_engine(f.e),before)
  op['allocations']={'group/one':{'child/a':1,'child/b':0}}
  out=f.run_policy(f.doc(op,'partial'))
  self.assertEqual(out['grant_result']['tutor_points_refunded'],1)

 def transfer_fixture(self):
  f=F.GrantPaymentTests();f.setUp()
  F.PARTY.configure(f.e,f.owner,mode='standard',reason='owner',roster=[f.c],storage={'kind':'center','id':'one'})
  F.PARTY.configure(f.e,f.other,mode='standard',reason='other',roster=[],storage={'kind':'center','id':'two'})
  f.buy();return f
 def test_saved_owner_loss_policy_drives_native_transfer_without_refund(self):
  f=self.transfer_fixture()
  for key in ('child/a','child/b','child/c'):
   f.e.bind_grant_withdrawal_policy(f.c,key,{'provider_loss':{'allowed':True,'refund_mode':'none'}})
  e=load_engine(f.rules,dump_engine(f.e));owner,other,c=e.everyone
  out=F.PARTY.transfer(e,owner,target=c,new_owner=other,reason='trade',request_id='bound-trade')
  self.assertEqual(c.spec['tutor_points'],2);self.assertEqual(c.spec['trainer_id'],other.entity_id)
  self.assertEqual(out['cleanup']['tutor_points_refunded'],0)
  self.assertEqual(out['cleanup']['withdrawal_policies']['child/a']['cause'],'provider_loss')
  before=dump_engine(e)
  self.assertEqual(F.PARTY.transfer(e,owner,target=c,new_owner=other,reason='trade',request_id='bound-trade'),out)
  self.assertEqual(dump_engine(e),before);F.PAY.validate(c)
 def test_owner_loss_pending_denial_and_missing_cause_are_atomic(self):
  import acquisition_withdrawal as W
  for policies,error in [({'provider_loss':{'allowed':None,'refund_mode':'actual'}},W.WithdrawalPolicyPending),
     ({'provider_loss':{'allowed':False,'refund_mode':'actual'}},ValueError),
     ({'expiry':{'allowed':True,'refund_mode':'none'}},ValueError)]:
   with self.subTest(policies=policies):
    f=self.transfer_fixture();f.e.bind_grant_withdrawal_policy(f.c,'child/a',policies);before=dump_engine(f.e)
    with self.assertRaises(error):F.PARTY.transfer(f.e,f.owner,target=f.c,new_owner=f.other,reason='trade',request_id='trade')
    self.assertEqual(dump_engine(f.e),before)
 def test_bound_policy_cannot_be_replaced_or_mutated_by_caller(self):
  f=self.fixture();policies={'provider_loss':{'allowed':True,'refund_mode':'none'}}
  result=f.e.bind_grant_withdrawal_policy(f.c,'child/a',policies);before=dump_engine(f.e)
  result['provider_loss']['allowed']=False;policies['provider_loss']['allowed']=False
  self.assertEqual(dump_engine(f.e),before)
  with self.assertRaisesRegex(ValueError,'cannot be replaced'):f.e.bind_grant_withdrawal_policy(f.c,'child/a',policies)
  self.assertEqual(dump_engine(f.e),before)

 def test_pending_policy_can_resolve_without_rewriting_settled_decision(self):
  f=self.fixture()
  f.e.bind_grant_withdrawal_policy(f.c,'child/a',{'provider_loss':{'allowed':None,'refund_mode':'none'}})
  f.e.bind_grant_withdrawal_policy(f.c,'child/a',{'provider_loss':{'allowed':True,'refund_mode':'none'}})
  before=dump_engine(f.e)
  with self.assertRaises(ValueError):f.e.bind_grant_withdrawal_policy(f.c,'child/a',{'provider_loss':{'allowed':None,'refund_mode':'none'}})
  self.assertEqual(dump_engine(f.e),before)
  result=G.revoke_owner(f.e,f.c,f.owner.entity_id,'owner loss')
  self.assertEqual(result['tutor_points_refunded'],0)
  self.assertEqual(f.c.spec['tutor_points'],2)

if __name__=='__main__':unittest.main()
