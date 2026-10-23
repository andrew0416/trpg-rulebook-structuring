from pathlib import Path
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_grant_payments as F
from state_codec import dump_engine,load_engine

class ReceiptTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.GrantPaymentTests.setUpClass()
 def fixture(self):
  f=F.GrantPaymentTests();f.setUp();return f
 def test_group_debit_is_once_children_reference_payment_and_restore(self):
  f=self.fixture();f.buy();before=dump_engine(f.e)
  rows=f.e.acquisition_receipts(f.c);self.assertEqual(dump_engine(f.e),before)
  row=rows[0];self.assertEqual(row['debit']['amount'],1);self.assertEqual(len(row['children']),3)
  self.assertTrue(all(c['individual_debit'] is None for c in row['children']))
  self.assertEqual(row['source_owner_id'],f.owner.entity_id);self.assertIsNone(row['provider_id']);self.assertEqual(row['lifetime'],'your_pokemon')
  json.dumps(rows);loaded=load_engine(f.rules,before)
  self.assertEqual(loaded.acquisition_receipts(loaded.everyone[2]),rows)
  row['children'].clear();self.assertEqual(len(f.e.acquisition_receipts(f.c)[0]['children']),3)
 def test_free_group_and_partial_refund_keep_original_payment(self):
  f=self.fixture();f.buy(allocation={'child/a':1,'child/b':0,'child/c':0})
  f.refund(['child/a'])
  row=f.e.acquisition_receipts(f.c)[0]
  self.assertEqual(row['debit']['amount'],1);self.assertEqual(row['refunded'],1)
  self.assertEqual([c['state'] for c in row['children']],['refunded','active','active'])
  free=self.fixture();free.e.acquire_grant_group(free.c,'free',free.grants,0,**free.options)
  row=free.e.acquisition_receipts(free.c)[0]
  self.assertEqual(row['debit']['amount'],0);self.assertEqual(row['refunded'],0)
 def test_existing_sheet_ownership_does_not_fabricate_receipt(self):
  f=self.fixture();f.c.spec['capabilities']=['unreceipted']
  self.assertEqual(f.e.acquisition_receipts(f.c),[])

 def test_native_teaching_receipt_retains_actual_provider_and_choice(self):
  import test_foundation_policy_teaching as T
  T.PolicyTeachingTests.setUpClass();f=T.PolicyTeachingTests();f.setUp()
  f.run_policy(context={'skill':'\uc721\uc0c1'},request_id='receipt/teaching')
  rows=f.e.acquisition_receipts(f.p)
  row=next(x for x in rows if x['basis']=='native_learned_edge')
  self.assertEqual(row['provider_id'],f.a.entity_id)
  self.assertEqual(row['debit']['amount'],1)
  self.assertIn('rank_before',row['selection'])
  restored=load_engine(f.r,dump_engine(f.e))
  actor=next(x for x in restored.everyone if x.entity_id==f.p.entity_id)
  self.assertEqual(restored.acquisition_receipts(actor),rows)

 def test_policy_execution_links_actual_granting_actor(self):
  import test_foundation_policy_grant_payments as P
  P.PolicyGrantTests.setUpClass();f=P.PolicyGrantTests();f.setUp()
  execution=f.run_policy(f.doc(f.op),request_id='receipt/provider')
  row=f.e.acquisition_receipts(f.c)[0]
  self.assertEqual(row['provider_id'],f.a.entity_id)
  self.assertEqual(row['execution_ids'],[execution['execution_id']])

 def test_temporary_source_ends_without_erasing_baseline_or_inventing_payment(self):
  import state_grants as G
  f=self.fixture();f.c.spec['capabilities']=['independent']
  G.grant(f.c,'capabilities','independent','temporary/source','feature',
   owner_id=f.owner.entity_id,lifetime='until_source_ends',rule_id='combat/struggle',tutor_points=0)
  G._source(f.c,'temporary/source','feature',rank=2,branch='declared-branch',parent_id='parent/grant')
  row=f.e.acquisition_receipts(f.c)[0]
  self.assertEqual(row['state'],'active');self.assertIsNone(row['debit'])
  self.assertEqual(row['lifetime'],'until_source_ends')
  G.revoke(f.c,'temporary/source',engine=f.e)
  self.assertIn('independent',G.effective(f.c,'capabilities'))
  rows=f.e.acquisition_receipts(f.c);self.assertEqual(rows[0]['state'],'ended')
  self.assertEqual(rows[0]['source_owner_id'],f.owner.entity_id)
  self.assertEqual(rows[0]['metadata'],{'kind':'feature','rank':2,'branch':'declared-branch','parent_id':'parent/grant'})
  self.assertIsNone(rows[0]['debit'])
  restored=load_engine(f.rules,dump_engine(f.e))
  self.assertEqual(restored.acquisition_receipts(restored.everyone[2]),rows)
  G.revoke(f.c,'temporary/source',engine=f.e)
  self.assertEqual(f.e.acquisition_receipts(f.c),rows)

 def test_resource_origin_records_awards_without_inventing_old_spending(self):
  import test_category2_progression_state as P
  import downtime as D,pokemon_progression as PROG
  P.ProgressionStateTests.setUpClass();f=P.ProgressionStateTests();f.setUp();c=f.pokemon(level=1)
  D.gain_exp_combatant(f.e,c,D.exp_for_level(f.r,5))
  before=dump_engine(f.e);account=f.e.acquisition_account(c)
  self.assertEqual(dump_engine(f.e),before)
  self.assertEqual(account['resource_events'][0]['kind'],'initial_award')
  self.assertEqual(account['resource_events'][0]['amount'],1)
  self.assertEqual(account['resource_events'][1]['kind'],'level_award')
  self.assertFalse(account['complete_spending_history'])
  c.spec[PROG.LEVEL_STATE].pop('initial_balance')
  self.assertIsNone(f.e.acquisition_account(c)['resource_events'][0]['amount'])
 def test_imported_unknown_balance_stays_unknown_until_observed(self):
  import pokemon_progression as P
  f=self.fixture();f.c.spec.pop('tutor_points')
  P.prepare_level(f.rules,f.c.spec)
  before=dump_engine(f.e);account=f.e.acquisition_account(f.c)
  self.assertEqual(dump_engine(f.e),before);self.assertFalse(account['balance_known'])
  self.assertEqual(account['resource_events'][0]['origin'],'unknown_import')
  P.observe_balance(f.e,f.c,balance=4,reason='actual current balance')
  account=f.e.acquisition_account(f.c)
  self.assertEqual(account['balance'],4)
  self.assertEqual(account['resource_events'][-1]['kind'],'balance_observation')
  self.assertEqual(account['acquisitions'],[])

if __name__=='__main__':unittest.main()
