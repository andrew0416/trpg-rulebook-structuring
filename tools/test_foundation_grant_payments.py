"""Native grouped payment/withdrawal witnesses, not specific Edge acquisition certification."""
from copy import deepcopy
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import state_grants as G
import grant_payments as PAY
import pokemon_party as PARTY
import world_entities as W

class GrantPaymentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,716)
  def make(uid,kind):return Combatant(self.rules,{'id':uid,'name':uid,'kind':kind,'level':10,
    'stats':{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},'moves':[],'abilities':[],
    'skills':{},'movement':{'land':5},'tutor_points':3})
  self.owner=make('trainer/owner','trainer');self.other=make('trainer/other','trainer');self.c=make('pokemon/paid','pokemon')
  self.c.spec['trainer_id']=self.owner.entity_id
  self.e.everyone=self.e.gm.everyone=[self.owner,self.other,self.c]
  self.grants=[{'source_id':'child/'+x,'field':'capabilities','value':'witness/'+x} for x in 'abc']
  self.options={'rule_id':'combat/struggle','reason':'host-adjudicated synthetic group',
                'owner_id':self.owner.entity_id,'lifetime':'your_pokemon'}
 def buy(self,**options):return self.e.acquire_grant_group(self.c,'payment/one',self.grants,1,**dict(self.options,**options))
 def refund(self,sources,request_id='refund/one',**options):
  return self.e.refund_grant_sources(self.c,sources,request_id=request_id,reason='explicit withdrawal',**options)
 def snapshot(self):return (deepcopy(self.c.__dict__,{id(self.rules):self.rules}),self.e.rng.getstate(),list(self.e.log_lines))
 def test_group_debits_once_and_same_request_cannot_be_repurposed(self):
  first=self.buy();self.assertEqual(self.c.spec['tutor_points'],2)
  self.assertTrue(all(x['value'] in G.effective(self.c,'capabilities') for x in self.grants))
  self.assertEqual(self.buy(),first);self.assertEqual(self.c.spec['tutor_points'],2)
  before=self.snapshot()
  with self.assertRaisesRegex(ValueError,'changed input'):self.buy(reason='changed intent')
  self.assertEqual(self.snapshot(),before)
  with self.assertRaisesRegex(ValueError,'settlement required'):G.revoke(self.c,'child/a',engine=self.e)
  self.assertEqual(self.snapshot(),before)
  with self.assertRaisesRegex(ValueError,'cannot be extended'):
   G.grant(self.c,'capabilities','witness/new','child/a','feature')
  self.assertEqual(self.snapshot(),before)
 def test_partial_unknown_refund_waits_then_explicit_allocation_conserves_payment(self):
  self.buy();before=self.snapshot()
  with self.assertRaisesRegex(ValueError,'explicit allocation required'):self.refund(['child/a'])
  self.assertEqual(self.snapshot(),before)
  shares={'payment/one':{'child/a':1,'child/b':0,'child/c':0}}
  receipt=self.refund(['child/a'],allocations=shares)
  self.assertEqual(receipt['tutor_points_refunded'],1);self.assertEqual(self.c.spec['tutor_points'],3)
  self.assertNotIn('witness/a',G.effective(self.c,'capabilities'))
  self.assertIn('witness/b',G.effective(self.c,'capabilities'))
  self.assertEqual(self.refund(['child/a'],allocations=shares),receipt)
  with self.assertRaisesRegex(ValueError,'active grant'):self.refund(['child/a'],request_id='duplicate')
  self.assertEqual(self.refund(['child/b','child/c'],request_id='remaining')['tutor_points_refunded'],0)
  self.assertEqual(self.c.spec['tutor_points'],3);PAY.validate(self.c)
  # An acquisition replay is historical readback, not reacquisition after refund.
  self.buy();self.assertNotIn('witness/a',G.effective(self.c,'capabilities'))
  self.assertEqual(self.c.spec['tutor_points'],3)
 def test_whole_group_refund_needs_no_invented_child_allocation(self):
  self.buy();receipt=self.refund(['child/c','child/a','child/b'])
  self.assertEqual(receipt['tutor_points_refunded'],1)
  self.assertIsNone(self.c.spec[G.KEY]['payments']['payment/one']['allocation'])
  self.assertEqual(self.refund(['child/a','child/b','child/c']),receipt)
  self.assertEqual(self.c.spec['tutor_points'],3)
 def test_native_owner_transfer_refunds_whole_group_once(self):
  PARTY.configure(self.e,self.owner,mode='standard',reason='owner roster',roster=[self.c],storage={'kind':'center','id':'one'})
  PARTY.configure(self.e,self.other,mode='standard',reason='recipient roster',roster=[],storage={'kind':'center','id':'two'})
  self.buy()
  receipt=PARTY.transfer(self.e,self.owner,target=self.c,new_owner=self.other,reason='trade',request_id='trade')
  self.assertEqual(self.c.spec['tutor_points'],3)
  self.assertFalse(set(x['value'] for x in self.grants)&set(G.effective(self.c,'capabilities')))
  self.assertEqual(PARTY.transfer(self.e,self.owner,target=self.c,new_owner=self.other,reason='trade',request_id='trade'),receipt)
  self.assertEqual(self.c.spec['tutor_points'],3);PAY.validate(self.c)
 def test_late_invalid_grant_and_invalid_allocations_leave_no_partial_payment(self):
  before=self.snapshot();self.grants[-1]={'source_id':'child/c','field':'moves','value':'move/nonexistent','learning_route':'taught'}
  with self.assertRaises(ValueError):self.buy()
  self.assertEqual(self.snapshot(),before)
  self.grants[-1]={'source_id':'child/c','field':'capabilities','value':'witness/c'}
  for allocation in [{'child/a':1},{'child/a':1,'child/b':1,'child/c':1},{'child/a':True,'child/b':0,'child/c':0}]:
   with self.subTest(allocation=allocation),self.assertRaises(ValueError):self.buy(allocation=allocation)
   self.assertEqual(self.snapshot(),before)
  self.c.spec['tutor_points']=0;before=self.snapshot()
  with self.assertRaisesRegex(ValueError,'insufficient'):self.buy()
  self.assertEqual(self.snapshot(),before)
 def test_saved_partial_refund_resumes_without_repeating_debit_or_refund(self):
  from state_codec import dump_engine,load_engine
  self.buy(allocation={'child/a':0,'child/b':1,'child/c':0})
  self.refund(['child/b']);saved=dump_engine(self.e)
  restored=load_engine(self.rules,saved);c=W.actor_index(restored)[self.c.entity_id]
  self.assertEqual(restored.refund_grant_sources(c,['child/b'],request_id='refund/one',reason='explicit withdrawal')['tutor_points_refunded'],1)
  self.assertEqual(restored.refund_grant_sources(c,['child/a','child/c'],request_id='restored/rest',reason='explicit withdrawal')['tutor_points_refunded'],0)
  self.assertEqual(c.spec['tutor_points'],3);PAY.validate(c)
 def test_owner_transfer_after_partial_refund_returns_only_remaining_payment(self):
  PARTY.configure(self.e,self.owner,mode='standard',reason='owner roster',roster=[self.c],storage={'kind':'center','id':'one'})
  PARTY.configure(self.e,self.other,mode='standard',reason='recipient roster',roster=[],storage={'kind':'center','id':'two'})
  self.buy(allocation={'child/a':1,'child/b':0,'child/c':0})
  self.refund(['child/a'])
  result=PARTY.transfer(self.e,self.owner,target=self.c,new_owner=self.other,reason='trade',request_id='trade-after-refund')
  self.assertEqual(self.c.spec['tutor_points'],3)
  PAY.validate(self.c)

 def test_returned_acquisition_receipt_cannot_mutate_payment_state(self):
  receipt=self.buy();receipt['sources'].clear();receipt['paid']=999
  self.assertEqual(self.c.spec[G.KEY]['payments']['payment/one']['children'],['child/a','child/b','child/c'])
  self.assertEqual(self.buy()['paid'],1);PAY.validate(self.c)

 def test_zero_cost_group_can_be_partially_withdrawn_without_a_fictitious_refund(self):
  self.e.acquire_grant_group(self.c,'payment/free',self.grants,0,**self.options)
  self.assertEqual(self.refund(['child/a'])['tutor_points_refunded'],0)
  self.assertEqual(self.c.spec['tutor_points'],3)
  self.assertIn('witness/b',G.effective(self.c,'capabilities'))
  PAY.validate(self.c)

 def test_grouped_ability_uses_native_effect_and_withdrawal(self):
  self.grants=[{'source_id':'child/a','field':'abilities','value':'엽록소'}]
  self.e.gm.set_weather('sunny',rounds=None,reason='native conditional effect witness')
  before=self.c.stages['spe'];self.buy()
  self.assertIn('엽록소',self.c.abilities);self.assertEqual(self.c.stages['spe'],before+4)
  self.refund(['child/a'])
  self.assertNotIn('엽록소',self.c.abilities);self.assertEqual(self.c.stages['spe'],before)
  self.assertEqual(self.c.spec['tutor_points'],3)

 def test_grouped_moves_use_explicit_route_and_enforce_combined_taught_capacity(self):
  import move_state as M
  mids=['move/화염방사','move/냉동빔','move/번개','move/지진']
  self.grants=[{'source_id':'move-child/'+str(i),'field':'moves','value':mid,'learning_route':'taught'} for i,mid in enumerate(mids)]
  before=self.snapshot()
  with self.assertRaisesRegex(ValueError,'TM/Tutor'):self.buy()
  self.assertEqual(self.snapshot(),before)
  self.grants[-1]['learning_route']='granted'
  self.buy();view=M.validate_spec(self.rules,self.c.spec)
  self.assertEqual(view['taught_count'],3);self.assertEqual(view['classifications'][mids[-1]],'granted')
  self.assertEqual(self.c.spec['tutor_points'],2)
  opportunities=M._opportunity_candidates(self.rules,self.c.spec)
  self.assertEqual(opportunities[mids[0]][0]['group_paid_tp'],1)
  self.assertNotIn('paid_tp',opportunities[mids[0]][0])
  self.assertNotIn(mids[-1],opportunities)

 def test_corrupt_duplicate_refund_and_missing_child_are_rejected_on_save(self):
  from state_codec import dump_engine,StateCodecError
  self.buy();self.refund(['child/a','child/b','child/c'])
  row=self.c.spec[G.KEY]['payments']['payment/one']
  row['refunds'].append(deepcopy(row['refunds'][0]))
  with self.assertRaises(StateCodecError):dump_engine(self.e)
  row['refunds'].pop();row['refunds']=[]
  with self.assertRaises(StateCodecError):dump_engine(self.e)

 def test_paid_provenance_changes_reject_refund_and_save_without_mutation(self):
  from state_codec import dump_engine,StateCodecError
  self.buy();row=self.c.spec[G.KEY]['sources']['child/a']
  for field,value in [('owner_id',self.other.entity_id),('lifetime',None),('rule_id','combat/other'),('kind','item')]:
   old=row[field];row[field]=value;before=self.snapshot()
   with self.subTest(field=field):
    with self.assertRaisesRegex(ValueError,'provenance changed'):self.refund(['child/a','child/b','child/c'])
    with self.assertRaises(StateCodecError):dump_engine(self.e)
    self.assertEqual(self.snapshot(),before)
   row[field]=old
  self.assertEqual(self.refund(['child/a','child/b','child/c'])['tutor_points_refunded'],1)
 def test_paid_learning_route_cannot_be_reclassified_after_acquisition(self):
  from state_codec import dump_engine,StateCodecError
  self.grants=[{'source_id':'child/a','field':'moves','value':'move/화염방사','learning_route':'taught'}]
  self.buy();row=self.c.spec[G.KEY]['sources']['child/a'];row['learning_route']='granted'
  with self.assertRaisesRegex(ValueError,'provenance changed'):PAY.validate(self.c)
  with self.assertRaises(StateCodecError):dump_engine(self.e)
  row['learning_route']='taught';PAY.validate(self.c)
 def test_acquisition_request_is_detached_and_legacy_evidence_is_not_invented(self):
  from state_codec import dump_engine,load_engine
  self.buy();self.grants[0]['value']='changed externally'
  group=self.c.spec[G.KEY]['payments']['payment/one']
  self.assertEqual(group['request']['grants'][0]['value'],'witness/a');PAY.validate(self.c)
  group['request']['owner_id']=self.other.entity_id
  with self.assertRaisesRegex(ValueError,'request changed'):PAY.validate(self.c)
  group['request']['owner_id']=self.owner.entity_id
  group['version']=1;group.pop('request')
  restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id]
  self.assertNotIn('request',c.spec[G.KEY]['payments']['payment/one'])
  receipt=restored.refund_grant_sources(c,['child/a','child/b','child/c'],request_id='legacy/refund',reason='legacy withdrawal')
  self.assertEqual(receipt['tutor_points_refunded'],1)

 def test_original_explicit_allocation_cannot_be_silently_reassigned(self):
  self.buy(allocation={'child/a':1,'child/b':0,'child/c':0})
  group=self.c.spec[G.KEY]['payments']['payment/one']
  group['allocation']={'child/a':0,'child/b':1,'child/c':0}
  with self.assertRaisesRegex(ValueError,'explicit payment allocation changed'):self.refund(['child/b'])
  self.assertEqual(self.c.spec['tutor_points'],2)
  self.assertIn('witness/b',G.effective(self.c,'capabilities'))

 def stat_grant(self,delta=2,minimum=None):
  return {'source_id':'child/stat','field':'stats','stat':'atk','delta':delta,'minimum':minimum}
 def test_paid_stat_composes_with_independent_contribution_and_refunds_only_itself(self):
  self.grants=[self.stat_grant(),{'source_id':'child/cap','field':'capabilities','value':'witness/cap'}]
  self.buy(allocation={'child/stat':1,'child/cap':0})
  G.stat(self.c,'atk',3,'independent')
  self.assertEqual(self.c.stats['atk'],15);self.assertEqual(self.c.spec['stats']['atk'],10)
  receipt=self.refund(['child/stat']);self.assertEqual(receipt['tutor_points_refunded'],1)
  self.assertEqual(self.c.stats['atk'],13);self.assertIn('witness/cap',G.effective(self.c,'capabilities'))
  self.assertEqual(self.refund(['child/stat']),receipt);PAY.validate(self.c)
 def test_paid_stat_raw_minimum_replays_against_current_baseline(self):
  from state_codec import dump_engine,load_engine
  self.grants=[self.stat_grant(-20,1)];self.buy()
  G.stat(self.c,'atk',3,'independent');self.assertEqual(self.c.stats['atk'],4)
  restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id]
  restored.refund_grant_sources(c,['child/stat'],request_id='stat/refund',reason='withdraw stat')
  self.assertEqual(c.stats['atk'],13);self.assertEqual(c.spec['tutor_points'],3)
  PAY.validate(c)
 def test_late_invalid_stat_rolls_back_list_grants_and_payment(self):
  self.grants.append(self.stat_grant(-20));before=self.snapshot()
  with self.assertRaisesRegex(ValueError,'statistic invalid'):self.buy()
  self.assertEqual(self.snapshot(),before)
 def test_refund_that_would_leave_invalid_stat_preserves_everything(self):
  self.grants=[self.stat_grant(5)];self.buy();G.stat(self.c,'atk',-12,'independent')
  self.assertEqual(self.c.stats['atk'],3);before=self.snapshot()
  with self.assertRaisesRegex(ValueError,'withdrawal would make effective statistic invalid'):self.refund(['child/stat'])
  self.assertEqual(self.snapshot(),before)
  G.revoke(self.c,'independent',engine=self.e)
  self.refund(['child/stat']);self.assertEqual(self.c.stats['atk'],10)
 def test_paid_stat_extension_and_corrupt_contribution_are_rejected(self):
  from state_codec import dump_engine,StateCodecError
  self.grants=[self.stat_grant()];self.buy();before=self.snapshot()
  with self.assertRaisesRegex(ValueError,'cannot be extended'):G.stat(self.c,'atk',1,'child/stat',operation_id='extra')
  self.assertEqual(self.snapshot(),before)
  self.c.spec[G.KEY]['stat_sources']['atk']['sources']['child/stat']['0']['delta']=3
  with self.assertRaisesRegex(ValueError,'paid stat contribution changed'):PAY.validate(self.c)
  with self.assertRaises(StateCodecError):dump_engine(self.e)

 def test_native_owner_transfer_removes_paid_stat_and_refunds_once(self):
  PARTY.configure(self.e,self.owner,mode='standard',reason='owner roster',roster=[self.c],storage={'kind':'center','id':'one'})
  PARTY.configure(self.e,self.other,mode='standard',reason='recipient roster',roster=[],storage={'kind':'center','id':'two'})
  self.grants=[self.stat_grant(2)];self.buy();G.stat(self.c,'atk',3,'independent')
  first=PARTY.transfer(self.e,self.owner,target=self.c,new_owner=self.other,reason='trade',request_id='stat-trade')
  self.assertEqual(self.c.stats['atk'],13);self.assertEqual(self.c.spec['tutor_points'],3)
  self.assertEqual(self.c.spec['trainer_id'],self.other.entity_id)
  self.assertEqual(PARTY.transfer(self.e,self.owner,target=self.c,new_owner=self.other,reason='trade',request_id='stat-trade'),first)
  self.assertEqual(self.c.stats['atk'],13);PAY.validate(self.c)

 def test_paid_skill_modifier_changes_native_total_without_changing_rank_or_pool(self):
  import skill_modifiers as S
  self.c.spec['skills']={'육상':'3d6+2'}
  self.grants=[{'source_id':'child/skill','field':'skill_modifier','skill':'육상','delta':3}]
  self.buy();contribution=G.skill_modifier(self.c,'athletics',2,'independent/skill','feature',rule_id='combat/struggle')
  contribution['delta']=999
  result=self.e.skill_roll(self.c,'육상',fixed=[2,2,2])
  self.assertEqual(result.total,13);self.assertEqual(result.rank,3)
  self.assertEqual(S.rank(self.rules,self.c,'athletics')[2],3)
  self.assertEqual(S.effective_rank(self.rules,self.c,'athletics'),3)
  self.assertEqual(self.c.spec['skills'],{'육상':'3d6+2'})
  self.refund(['child/skill'])
  self.assertEqual(self.e.skill_roll(self.c,'athletics',fixed=[2,2,2]).total,10)
  self.assertEqual(self.c.spec['tutor_points'],3)
 def test_paid_skill_modifier_restores_and_bad_source_roll_does_not_consume_rng(self):
  from state_codec import dump_engine,load_engine
  self.c.spec['skills']={'육상':'3d6+2'}
  self.grants=[{'source_id':'child/skill','field':'skill_modifier','skill':'육상','delta':-2}]
  self.buy();restored=load_engine(self.rules,dump_engine(self.e));c=W.actor_index(restored)[self.c.entity_id]
  self.assertEqual(restored.skill_roll(c,'athletics',fixed=[2,2,2]).total,6)
  c.spec[G.KEY]['sources']['child/skill']['grants']['skill_modifiers'][0]['delta']=99
  before=restored.rng.getstate();logs=list(restored.log_lines)
  with self.assertRaisesRegex(ValueError,'paid grant changed'):restored.skill_roll(c,'athletics')
  self.assertEqual(restored.rng.getstate(),before);self.assertEqual(restored.log_lines,logs)
 def test_unknown_skill_in_mixed_group_rolls_back_prior_native_grants(self):
  self.grants.append({'source_id':'child/skill','field':'skill_modifier','skill':'not-a-skill','delta':1})
  before=self.snapshot()
  with self.assertRaisesRegex(ValueError,'unknown PTK skill'):self.buy()
  self.assertEqual(self.snapshot(),before)

if __name__=='__main__':unittest.main()
