"""Adjudication contracts; synthetic alternatives are not source-rule certification."""
from copy import copy,deepcopy
from hashlib import sha256
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
from ruleset import RuleSelection

class AdjudicationScopeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.base=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.rules=copy(self.base);self.rules.ruleset=deepcopy(self.base.ruleset);self.rules.rulings=deepcopy(self.base.rulings)
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.base.selection.units.values()))
  self.engine=Engine(self.rules,seed=715)
  self.actor=Combatant(self.rules,build_trainer(self.rules,'adjudication-owner',10,
      dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),abilities=[]))
  self.engine.everyone=self.engine.gm.everyone=[self.actor]
  source=self.rules.selection.units['combat/struggle']['source']['file']
  self.row={'rule_id':'combat/struggle','source':{'file':'input/'+source,'sha256':sha256((ROOT/'input'/source).read_bytes()).hexdigest()},
   'inputs':{'amount':{'type':'integer','authority':'gm','question':'Select one explicitly authored interpretation',
                      'decision_kind':'source_conflict','choices':[1,2]}},
   'values':{'effects':[{'type':'stage_change','stat':'atk','delta':{'$input':'amount'},'target':'self'}]}}
  self.document={'schema':1,'id':'scope-witness','variants':[self.row]}
 def prepare(self):return self.rules.resolve_source_policy(self.document)
 def decision(self):return {'amount':{'value':1,'reason':'Explicit host review of this authored interpretation',
                                     'scope':self.prepare()['decision_scope']}}
 def snapshot(self):return (deepcopy(self.actor.__dict__,{id(self.rules):self.rules}),self.engine.rng.getstate(),
                           list(self.engine.log_lines),deepcopy(getattr(self.engine,'_source_policy_executions',{})))
 def execute(self,decisions):return self.engine.execute_source_policy_effects(self.actor,self.actor,self.document,decisions=decisions)
 def test_missing_facts_delegation_and_conflict_remain_distinct(self):
  self.row['inputs'].update(fact={'type':'boolean','authority':'context','question':'Actual event fact'},
      choice={'type':'boolean','authority':'gm','decision_kind':'delegated_choice','question':'Source-delegated permission'})
  before=self.snapshot();pending=self.execute({})
  self.assertEqual(pending['status'],'PolicyInputsRequired')
  obligations={x['input']:x for x in pending['obligations']}
  self.assertEqual(obligations['fact']['authority'],'context')
  self.assertEqual(obligations['choice']['decision_kind'],'delegated_choice')
  self.assertEqual(obligations['amount']['decision_kind'],'source_conflict')
  self.assertEqual(self.snapshot(),before)
  decisions=self.decision();decisions['choice']={'value':False,'reason':'Host declines delegated permission'}
  result=self.rules.resolve_source_policy(self.document,context={'fact':False},decisions=decisions)
  self.assertEqual(result['input_values'],{'amount':1,'fact':False,'choice':False})
  self.assertEqual({x['decision_kind'] for x in result['decision_evidence']},{'source_conflict','delegated_choice'})
 def test_missing_or_foreign_scope_and_unsupported_choice_reject_before_effects(self):
  good=self.decision();before=self.snapshot()
  candidates=[{'value':1,'reason':'unscoped'},dict(good['amount'],scope=None),
              dict(good['amount'],scope=dict(good['amount']['scope'],selected_id='foreign/rule')),
              dict(good['amount'],value=3),dict(good['amount'],reason='')]
  for value in candidates:
   with self.subTest(value=value),self.assertRaises(ValueError):self.execute({'amount':value})
   self.assertEqual(self.snapshot(),before)
  with self.assertRaisesRegex(ValueError,'non-context'):
   self.rules.resolve_source_policy(self.document,context={'amount':1})
 def test_changed_definition_and_effective_profile_require_a_new_review(self):
  decision=self.decision();before=self.snapshot()
  self.row['values']['effects'][0]['stat']='def'
  with self.assertRaisesRegex(ValueError,'scope changed'):self.execute(decision)
  self.assertEqual(self.snapshot(),before)
  decision=self.decision()
  self.rules.ruleset.exclude_units.add('unused/source')
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.rules.selection.units.values()))
  with self.assertRaisesRegex(ValueError,'scope changed'):self.execute(decision)
  self.assertEqual(self.snapshot(),before)
  old=self.actor.stages['def'];result=self.execute(self.decision())
  self.assertEqual(result['status'],'PolicyEffectsCompleted');self.assertEqual(self.actor.stages['def'],old+1)
 def test_stale_interpretation_does_not_spend_action_or_ap(self):
  self.engine.encounter_active=True;self.engine.round_start_seconds=0;self.engine._active_turn_actor=self.actor
  self.actor.budget={'standard':1,'shift':1,'swift':1};self.actor._turn_start_decisions_pending=False
  self.row['values'].update(action='standard',ap={'amount':1,'mode':'spend'})
  decision=self.decision();before=self.snapshot()
  self.row['inputs']['amount']['question']='Changed conflict requiring host review'
  with self.assertRaisesRegex(ValueError,'scope changed'):
   self.engine.execute_source_policy_action(self.actor,self.actor,self.document,decisions=decision)
  self.assertEqual(self.snapshot(),before)
  result=self.engine.execute_source_policy_action(self.actor,self.actor,self.document,decisions=self.decision())
  self.assertEqual(result['status'],'PolicyActionCompleted')
  self.assertEqual(self.actor.budget['standard'],0);self.assertEqual(self.actor.spec['ap_spent'],1)
  self.assertEqual(self.actor.stages['atk'],before[0]['stages']['atk']+1)

 def test_package_and_execution_evidence_survive_restore(self):
  from state_codec import dump_engine,load_engine
  loaded=self.rules.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[self.document]}))
  self.assertEqual(loaded[0]['status'],'PolicyInputsRequired')
  self.document=self.rules.source_policy_document('scope-witness');self.row=self.document['variants'][0]
  decision=self.decision();result=self.execute(decision)
  record=self.engine.source_policy_execution(result['execution_id'])
  evidence=record['decision_evidence'][0]
  self.assertEqual(evidence['decision_kind'],'source_conflict')
  self.assertEqual(evidence['scope'],decision['amount']['scope'])
  self.assertEqual(record['input_values']['amount'],1)
  restored=load_engine(self.rules,dump_engine(self.engine))
  self.assertEqual(restored.source_policy_execution(result['execution_id']),record)
  original=deepcopy(record)
  evidence['scope']['selected_id']='edited-copy'
  self.assertEqual(self.engine.source_policy_execution(result['execution_id']),original)
 def test_declared_integer_range_rejects_before_state_or_costs(self):
  spec=self.row['inputs']['amount'];spec.pop('choices');spec['decision_kind']='delegated_choice'
  spec.update(minimum=1,maximum=2)
  before=self.snapshot();pending=self.execute({})
  self.assertEqual(pending['obligations'][0]['constraints'],{'type':'integer','minimum':1,'maximum':2})
  self.assertEqual(self.snapshot(),before)
  for value in (0,3,True,'1'):
   with self.subTest(value=value),self.assertRaisesRegex(ValueError,'invalid policy input'):
    self.execute({'amount':{'value':value,'reason':'Explicit host choice'}})
   self.assertEqual(self.snapshot(),before)
  for value in (1,2):
   result=self.rules.resolve_source_policy(self.document,decisions={'amount':{'value':value,'reason':'Within declared limits'}})
   self.assertEqual(result['values']['effects'][0]['delta'],value)
  result=self.execute({'amount':{'value':1,'reason':'Within declared limits'}})
  self.assertEqual(result['status'],'PolicyEffectsCompleted')
  self.assertEqual(self.actor.stages['atk'],before[0]['stages']['atk']+1)

 def test_invalid_ranges_are_rejected_when_loading_external_declarations(self):
  original=deepcopy(self.row['inputs']['amount'])
  for patch in ({'minimum':True},{'maximum':'2'},{'minimum':3,'maximum':2},
                {'minimum':2},{'type':'string','choices':['a','b'],'minimum':0}):
   self.row['inputs']['amount']=dict(original,**patch)
   with self.subTest(patch=patch),self.assertRaises(ValueError):
    self.rules.load_source_policy_package(json.dumps({'schema':1,'sources':[],'policies':[self.document]}))

 def test_context_range_and_one_sided_bounds_use_the_same_contract(self):
  self.row['inputs']['amount']={'type':'integer','authority':'context','question':'Actual count','minimum':0}
  self.assertEqual(self.rules.resolve_source_policy(self.document,context={'amount':0})['input_values']['amount'],0)
  with self.assertRaisesRegex(ValueError,'invalid policy input'):
   self.rules.resolve_source_policy(self.document,context={'amount':-1})
  self.row['inputs']['amount'].pop('minimum');self.row['inputs']['amount']['maximum']=0
  self.assertEqual(self.rules.resolve_source_policy(self.document,context={'amount':-2})['input_values']['amount'],-2)
  with self.assertRaisesRegex(ValueError,'invalid policy input'):
   self.rules.resolve_source_policy(self.document,context={'amount':1})

 def test_conflict_contract_requires_typed_distinct_alternatives(self):
  spec=self.row['inputs']['amount']
  for choices in [None,[],[1],[1,1],[1,True]]:
   spec['choices']=choices
   with self.subTest(choices=choices),self.assertRaises(ValueError):self.prepare()
  spec['choices']=[1,2]
  for authority in ['context','state']:
   spec['authority']=authority
   with self.assertRaisesRegex(ValueError,'decision kind'):self.prepare()
  spec['authority']='gm';spec['decision_kind']='automatic_translation_precedence'
  with self.assertRaisesRegex(ValueError,'decision kind'):self.prepare()

 def test_native_formula_and_mech_require_reason_and_supported_scope_before_mutation(self):
  rules=self.rules.rulings
  def snapshot():return deepcopy((rules.formulas,rules.mech,rules.log,self.engine.log_lines))
  for reason,scope in [('', 'scene'),('   ','campaign'),(None,'scene'),('explicit','round'),('explicit',True)]:
   for kind in ('formula','mech'):
    before=snapshot()
    with self.subTest(kind=kind,reason=reason,scope=scope),self.assertRaises(ValueError):
     if kind=='formula':self.engine.rule_formula('table.test','1',reason=reason,scope=scope)
     else:self.engine.rule_mech('combat/struggle','foundation_test',1,reason=reason,scope=scope)
    self.assertEqual(snapshot(),before)
  self.engine.rule_formula('table.test','1',reason='explicit scene decision',scope='scene')
  self.engine.rule_mech('combat/struggle','foundation_test',0,reason='explicit campaign decision',scope='campaign')
  self.assertEqual(self.engine.formula('table.test'),1)
  self.assertEqual(self.rules.mech('combat/struggle')['foundation_test'],0)
  rules.end_scene()
  self.assertNotIn('table.test',rules.formulas)
  self.assertEqual(self.rules.mech('combat/struggle')['foundation_test'],0)

if __name__=='__main__':unittest.main()
