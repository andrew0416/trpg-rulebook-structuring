from pathlib import Path
from hashlib import sha256
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_grant_payments as F
import state_grants as G
import composition_reconcile as C
from state_codec import dump_engine,load_engine

class ReconciliationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):F.GrantPaymentTests.setUpClass()
 def setUp(self):
  self.f=F.GrantPaymentTests();self.f.setUp();f=self.f
  f.buy(allocation={'child/a':1,'child/b':0,'child/c':0})
  file=f.rules.selection.units['combat/struggle']['source']['file']
  self.row={'rule_id':'combat/struggle','source':{'file':'input/'+file,'sha256':sha256((ROOT/'input'/file).read_bytes()).hexdigest()},
   'inputs':{'level':{'type':'integer','authority':'state','question':'Actual level','binding':{'subject':'target','field':'level'}}},
   'values':{'retained':{'op':'ge','left':{'$input':'level'},'right':10}}}
  self.doc={'schema':1,'id':'retain-level','variants':[self.row]}
 def bind(self):
  f=self.f;f.e.bind_grant_withdrawal_policy(f.c,'child/a',{'prerequisite_loss':{'allowed':True,'refund_mode':'actual'}})
  f.e.bind_grant_reconciliation(f.c,'child/a',self.doc,cause='prerequisite_loss')
 def lower(self):
  f=self.f;G.transition(f.e,f.c,lambda e,c:c.spec.update(level=9))
 def test_native_transition_refunds_only_lost_source_and_keeps_independent_grant(self):
  f=self.f;G.grant(f.c,'capabilities','witness/a','permanent','feature',rule_id='combat/struggle')
  self.bind();self.lower()
  self.assertNotIn('child/a',f.c.spec[G.KEY]['sources']);self.assertIn('permanent',f.c.spec[G.KEY]['sources'])
  self.assertIn('witness/a',G.effective(f.c,'capabilities'));self.assertEqual(f.c.spec['tutor_points'],3)
  self.lower();self.assertEqual(f.c.spec['tutor_points'],3)
 def test_dependency_conflict_rolls_back_parent_mutation_and_all_refunds(self):
  f=self.f;self.bind();f.e.bind_grant_dependencies(f.c,'child/b',['child/a']);before=dump_engine(f.e)
  with self.assertRaisesRegex(C.ReconciliationPending,'retained grant depends'):self.lower()
  self.assertEqual(dump_engine(f.e),before)
 def test_retention_contract_survives_restore(self):
  f=self.f;self.bind();e=load_engine(f.rules,dump_engine(f.e));c=e.everyone[2]
  G.transition(e,c,lambda engine,actor:actor.spec.update(level=9))
  self.assertNotIn('child/a',c.spec[G.KEY]['sources']);self.assertEqual(c.spec['tutor_points'],3)
 def test_missing_actual_relation_is_pending_and_parent_change_is_rolled_back(self):
  f=self.f
  self.row['inputs']={'owner':{'type':'string','authority':'state','question':'Actual owner','binding':{'subject':'target','field':'owner_id'}}}
  self.row['values']['retained']={'op':'eq','left':{'$input':'owner'},'right':f.owner.entity_id}
  self.bind();before=dump_engine(f.e)
  with self.assertRaises(C.ReconciliationPending):G.transition(f.e,f.c,lambda e,c:c.spec.pop('trainer_id'))
  self.assertEqual(dump_engine(f.e),before)
 def test_weather_change_retracts_bound_source_in_world_only_transition(self):
  f=self.f;f.e.weather='rain'
  self.row['inputs']={'rain':{'type':'boolean','authority':'state','question':'Actual rain','binding':{'subject':'world','field':'weather_is','weather':'rain'}}}
  self.row['values']['retained']={'$input':'rain'}
  self.bind()
  G.transition(f.e,None,lambda e,c:setattr(e,'weather',None))
  self.assertNotIn('child/a',f.c.spec[G.KEY]['sources']);self.assertEqual(f.c.spec['tutor_points'],3)
 def test_species_binding_reads_actual_identity_and_rolls_back_unknown(self):
  f=self.f;first,second=list(f.rules.species)[:2];f.c.spec['species']=first
  self.row['inputs']={'species':{'type':'string','authority':'state','question':'Actual species','binding':{'subject':'target','field':'species_id'}}}
  self.row['values']['retained']={'op':'eq','left':{'$input':'species'},'right':first}
  self.bind();before=dump_engine(f.e)
  with self.assertRaises(C.ReconciliationPending):G.transition(f.e,f.c,lambda e,c:c.spec.pop('species'))
  self.assertEqual(dump_engine(f.e),before)
  G.transition(f.e,f.c,lambda e,c:c.spec.update(species=second))
  self.assertNotIn('child/a',f.c.spec[G.KEY]['sources'])

 def test_provider_removal_revisits_previously_checked_recipient(self):
  from copy import deepcopy
  f=self.f;provider_doc=deepcopy(self.doc)
  G.grant(f.owner,'capabilities','provider-mark','provider/source','feature',rule_id='combat/struggle')
  f.e.bind_grant_withdrawal_policy(f.owner,'provider/source',{'prerequisite_loss':{'allowed':True,'refund_mode':'none'}})
  f.e.bind_grant_reconciliation(f.owner,'provider/source',provider_doc,cause='prerequisite_loss')
  self.row['inputs']={'provider':{'type':'boolean','authority':'state','question':'Actual provider grant',
   'binding':{'subject':'entity','entity_id':f.owner.entity_id,'field':'grant_active','source_id':'provider/source'}}}
  self.row['values']['retained']={'$input':'provider'}
  self.bind();f.e.everyone=f.e.gm.everyone=[f.c,f.owner,f.other]
  G.transition(f.e,f.owner,lambda e,c:c.spec.update(level=9))
  self.assertNotIn('provider/source',f.owner.spec[G.KEY]['sources'])
  self.assertNotIn('child/a',f.c.spec[G.KEY]['sources']);self.assertEqual(f.c.spec['tutor_points'],3)
 def test_unchanged_inputs_skip_predicate_but_never_skip_source_validation(self):
  from unittest.mock import patch
  import acquisition_qualification as Q
  f=self.f;self.bind();cache={};original=Q.predicate
  with patch.object(Q,'predicate',wraps=original) as evaluate:
   C.reconcile(f.e,f.c,cache=cache);C.reconcile(f.e,f.c,cache=cache)
   self.assertEqual(evaluate.call_count,1)
   f.c.spec['level']=11;C.reconcile(f.e,f.c,cache=cache);self.assertEqual(evaluate.call_count,2)
  contract=f.c.spec[G.KEY]['sources']['child/a']['reconciliation']
  contract['document']['variants'][0]['source']['sha256']='0'*64
  with self.assertRaises(ValueError):C.reconcile(f.e,f.c,cache=cache)

 def test_slot_loss_waits_without_partial_removal_then_accepts_explicit_choice(self):
  from copy import deepcopy
  import move_state as M
  f=self.f;source='retained/slots';uid=M.GUIDANCE
  row=G._source(f.c,source,'feature',rule_id=uid,owner_id=f.owner.entity_id,lifetime='your_pokemon')
  row['move_slot_policy']={'rule_id':uid}
  moves=[]
  for mid in f.rules.moves:
   try:selected=f.rules.move_id(mid)
   except ValueError:continue
   if selected==mid:moves.append(mid)
   if len(moves)==7:break
  self.assertEqual(len(moves),7)
  G.set_baseline(f.c,'moves',moves)
  doc=deepcopy(self.doc);variant=doc['variants'][0];variant['rule_id']=uid
  file=f.rules.selection.units[uid]['source']['file']
  variant['source']={'file':'input/'+file,'sha256':sha256((ROOT/'input'/file).read_bytes()).hexdigest()}
  f.e.bind_grant_withdrawal_policy(f.c,source,{'prerequisite_loss':{'allowed':True,'refund_mode':'none'}})
  f.e.bind_grant_reconciliation(f.c,source,doc,cause='prerequisite_loss')
  self.bind();before=dump_engine(f.e)
  with self.assertRaisesRegex(C.ReconciliationPending,'forgotten-move choice'):self.lower()
  self.assertEqual(dump_engine(f.e),before)
  # Supply the player's concrete forgetting choice in the same transaction.
  def resolve(e,c):
   G.set_baseline(c,'moves',moves[:-1]);c.spec['level']=9
  G.transition(f.e,f.c,resolve)
  self.assertNotIn(source,f.c.spec[G.KEY]['sources']);self.assertNotIn('child/a',f.c.spec[G.KEY]['sources'])
  self.assertEqual(f.c.moves,moves[:-1]);self.assertEqual(f.c.spec['tutor_points'],3)

 def test_retention_loss_preserves_all_form_bases_and_independent_stat_source(self):
  from copy import deepcopy
  import form_allocations as FORMS
  f=self.f;forms={'normal':deepcopy(f.c.spec['stats']),'alternate':dict(f.c.spec['stats'],atk=20)}
  f.e.configure_form_allocations(f.c,forms,active='normal',source='combat/struggle')
  G._source(f.c,'retained/stat','feature',rule_id='combat/struggle');G.stat(f.c,'atk',3,'retained/stat')
  f.e.bind_grant_withdrawal_policy(f.c,'retained/stat',{'prerequisite_loss':{'allowed':True,'refund_mode':'none'}})
  f.e.bind_grant_reconciliation(f.c,'retained/stat',self.doc,cause='prerequisite_loss')
  G._source(f.c,'independent/stat','feature',rule_id='combat/struggle');G.stat(f.c,'atk',2,'independent/stat')
  self.bind();self.lower()
  out=FORMS.project(f.c)
  self.assertEqual(f.c.spec[FORMS.KEY]['forms'],forms)
  self.assertEqual((out['normal']['effective']['atk'],out['alternate']['effective']['atk']),(12,22))
  FORMS.switch(f.e,f.c,'alternate');self.assertEqual(f.c.stats['atk'],22)
  restored=load_engine(f.rules,dump_engine(f.e));c=restored.everyone[2]
  self.assertEqual(FORMS.project(c),FORMS.project(f.c));self.assertEqual(c.spec[FORMS.KEY]['forms'],forms)

if __name__=='__main__':unittest.main()
