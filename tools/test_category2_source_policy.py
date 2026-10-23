"""Public policy preparation: source isolation and explicit typed obligations."""
from pathlib import Path
from hashlib import sha256
from copy import copy, deepcopy
import sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'engine'))
from engine import Rules
from ruleset import RuleFilter, RuleSelection
from rulings import Rulings

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.loaded = Rules(ROOT)
 def setUp(self):
  self.rules = copy(self.loaded)
  self.rules.rulings = Rulings()
  self.uid = 'combat/struggle'
  self.document = {'schema':1,'id':'authored-policy','variants':[self.row(self.uid)]}
 def row(self, uid):
  source = self.loaded.selection.units[uid]['source']['file']
  path = ROOT/'input'/source
  return {'rule_id':uid,'source':{'file':'input/'+source,'sha256':sha256(path.read_bytes()).hexdigest()},
          'values':{'cost':2,'result':{'$input':'amount'},'enabled':{'$input':'enabled'}},
          'inputs':{'amount':{'type':'integer','authority':'gm','question':'Choose amount','choices':[0,2]},
                    'enabled':{'type':'boolean','authority':'context','question':'Is enabled?'}}}
 def resolve(self, **kwargs):
  return self.rules.resolve_source_policy(self.document, **kwargs)
 def supplied(self):
  return {'context':{'enabled':False},'decisions':{'amount':{'value':0,'reason':'explicit table ruling'}}}
 def test_missing_inputs_are_obligations_without_default_or_side_effect(self):
  before = deepcopy(self.rules.rulings.__dict__)
  result = self.resolve()
  self.assertEqual(result['status'],'PolicyInputsRequired')
  self.assertIsNone(result['values'])
  self.assertEqual({x['authority'] for x in result['obligations']},{'gm','context'})
  self.assertFalse(result['effects_executed'])
  self.assertEqual(before,self.rules.rulings.__dict__)
 def test_zero_false_and_decision_reason_survive_public_binding(self):
  original = deepcopy(self.document)
  result = self.resolve(**self.supplied())
  self.assertEqual(result['values'],{'cost':2,'result':0,'enabled':False})
  self.assertEqual(result['status'],'PolicyValuesReady')
  self.assertEqual(result['decision_evidence'],[{'input':'amount','reason':'explicit table ruling'}])
  result['values']['cost']=99
  self.assertEqual(original,self.document)
  self.assertEqual(self.resolve(**self.supplied())['values']['cost'],2)
 def test_optional_gm_scope_rejects_changed_binding_without_requiring_legacy_choices_to_be_scoped(self):
  args=self.supplied();scope=self.resolve()['decision_scope']
  args['decisions']['amount']['scope']=scope
  self.assertEqual(self.resolve(**args)['status'],'PolicyValuesReady')
  self.document['variants'][0]['values']['observed_binding']={'actor':'actual one','mass':20}
  with self.assertRaises(ValueError):self.resolve(**args)
  args['decisions']['amount'].pop('scope')
  self.assertEqual(self.resolve(**args)['status'],'PolicyValuesReady')
 def test_wrong_type_choice_authority_or_missing_reason_rejected(self):
  cases = [ {'context':{'enabled':0}}, {'context':{'amount':2}},
            {'decisions':{'enabled':{'value':True,'reason':'wrong authority'}}},
            {'decisions':{'amount':{'value':True,'reason':'bool is not integer'}}},
            {'decisions':{'amount':{'value':3,'reason':'outside choices'}}},
            {'decisions':{'amount':{'value':2,'reason':''}}} ]
  for case in cases:
   with self.subTest(case=case),self.assertRaises(ValueError):self.resolve(**case)
 def test_stale_source_and_override_rejected(self):
  self.document['variants'][0]['source']['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'source changed'):self.resolve()
  self.document['variants'][0]=self.row(self.uid)
  self.rules.rulings.mech[self.uid]={'cost':99}
  with self.assertRaisesRegex(ValueError,'override'):self.resolve()
 def test_profile_exclusion_and_unsupported_version_rechecked(self):
  units=list(self.loaded.selection.units.values())
  for profile in [{'exclude_units':[self.uid]},{'unit_versions':{self.uid:'unreviewed'}}]:
   self.rules.ruleset=RuleFilter(profile)
   self.rules.selection=RuleSelection(self.rules.ruleset, units)
   with self.subTest(profile=profile),self.assertRaises(ValueError):self.resolve()
 def test_independent_authored_definitions_and_inputs_change_fingerprints(self):
  first=self.resolve(**self.supplied())
  self.document['variants'][0]['values']['cost']=7
  second=self.resolve(**self.supplied())
  self.assertNotEqual(first['definition_hash'],second['definition_hash'])
  args=self.supplied();args['decisions']['amount']['value']=2
  third=self.resolve(**args)
  self.assertNotEqual(second['inputs_hash'],third['inputs_hash'])
  self.assertEqual(third['values']['result'],2)
 def test_ambiguous_sources_never_merge_values(self):
  other='combat/tick-of-hit-points'
  self.document['variants'].append(self.row(other))
  with self.assertRaisesRegex(ValueError,'exactly one'):self.resolve()
  self.rules.ruleset=RuleFilter({'exclude_units':[self.uid]})
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
  self.document['variants'][1]['values']['cost']=8
  self.assertEqual(self.resolve(**self.supplied())['values']['cost'],8)
 def test_malformed_reference_rejected_as_declaration_error(self):
  for value in [[],{},'absent']:
   self.document['variants'][0]['values']['result']={'$input':value}
   with self.subTest(value=value),self.assertRaises(ValueError):self.resolve()

 def test_selected_replacement_uses_whole_definition_and_requires_binding(self):
  base, alternate='policy/example','policy/example-playtest'
  source=self.loaded.selection.units[self.uid]['source']
  self.rules.ruleset=RuleFilter({'variant_replaces_core':True})
  self.rules.selection=RuleSelection(self.rules.ruleset,[
   {'id':base,'title':'Example','source':source},
   {'id':alternate,'title':'Example [Playtest]','source':source}])
  old=self.row(self.uid);old['rule_id']=base
  new=deepcopy(old);new['rule_id']=alternate
  old['values']={'cost':1,'old_only':True};old['inputs']={}
  new['values']={'cost':3,'effect':'alternate'};new['inputs']={}
  self.document['variants']=[old,new]
  result=self.resolve()
  self.assertEqual(result['selected_id'],alternate)
  self.assertEqual(result['values'],{'cost':3,'effect':'alternate'})
  self.document['variants']=[old]
  with self.assertRaisesRegex(ValueError,'replacement lacks'):self.resolve()

 def test_effect_execution_and_unresolved_suffix_are_atomic(self):
  from engine import Engine, Combatant
  from builder import build_trainer
  engine=Engine(self.rules)
  actor=Combatant(self.rules,build_trainer(self.rules,'policy-owner',10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  engine.everyone=[actor];engine.gm.everyone=[actor]
  row=self.document['variants'][0];row['inputs']={}
  row['values']={'effects':[{'type':'stage_change','stat':'atk','delta':2,'target':'self'}]}
  before=actor.stages['atk']
  result=engine.execute_source_policy_effects(actor,actor,self.document)
  self.assertEqual(result['status'],'PolicyEffectsCompleted')
  self.assertEqual(actor.stages['atk'],before+2)
  self.assertTrue(result['outcomes'][0]['receipt'])
  snapshot=(deepcopy(actor.__dict__,{id(self.rules):self.rules}),engine.rng.getstate(),deepcopy(engine.log_lines),dict(engine._effect_dispatch_receipts))
  row['values']['effects'].append({'type':'not_implemented'})
  with self.assertRaisesRegex(ValueError,'bundle unresolved'):
   engine.execute_source_policy_effects(actor,actor,self.document)
  self.assertEqual(actor.__dict__,snapshot[0])
  self.assertEqual(engine.rng.getstate(),snapshot[1])
  self.assertEqual(engine.log_lines,snapshot[2])
  self.assertEqual(engine._effect_dispatch_receipts,snapshot[3])
  row['values']['effects'].pop()
  row['inputs']={'delta':{'type':'integer','authority':'gm','question':'Choose delta'}}
  row['values']['effects'][0]['delta']={'$input':'delta'}
  pending=engine.execute_source_policy_effects(actor,actor,self.document)
  self.assertEqual(pending['status'],'PolicyInputsRequired')
  self.assertEqual(actor.__dict__,snapshot[0])
  row['inputs']={};row['values']['effects'][0]['delta']=1
  row['values']['effects'][0]['_state_source']='forged'
  with self.assertRaisesRegex(ValueError,'private runtime'):
   engine.execute_source_policy_effects(actor,actor,self.document)
  row['values']['effects'][0].pop('_state_source')
  from unittest.mock import patch
  import effects
  original=effects.HANDLERS['stage_change']
  def late_failure(e,a,t,effect,ctx):
   original(e,a,t,effect,ctx);e.rng.random()
   return 'unresolved after staged mutation'
  with patch.dict(effects.HANDLERS,{'stage_change':late_failure}):
   with self.assertRaisesRegex(ValueError,'bundle unresolved'):
    engine.execute_source_policy_effects(actor,actor,self.document)
  self.assertEqual(actor.__dict__,snapshot[0])
  self.assertEqual(engine.rng.getstate(),snapshot[1])
  self.assertEqual(engine.log_lines,snapshot[2])

 def test_action_and_ap_commit_with_effects_or_roll_back_together(self):
  from engine import Engine,Combatant
  from builder import build_trainer
  engine=Engine(self.rules)
  actor=Combatant(self.rules,build_trainer(self.rules,'policy-action',10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  engine.everyone=[actor];engine.gm.everyone=[actor]
  engine.encounter_active=True;engine.round_start_seconds=0;engine._active_turn_actor=actor
  actor.budget={'standard':1,'shift':1,'swift':1}
  actor._turn_start_decisions_pending=False
  row=self.document['variants'][0];row['inputs']={}
  row['values']={'action':['standard','swift'],'ap':{'amount':2,'mode':'drain'},
                 'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}
  result=engine.execute_source_policy_action(actor,actor,self.document)
  self.assertEqual(result['status'],'PolicyActionCompleted')
  self.assertEqual(actor.budget,{'standard':0,'shift':1,'swift':0})
  self.assertEqual(actor.spec['ap_removed'],2)
  actor.budget={'standard':1,'shift':1,'swift':1}
  row['values']['ap']['mode']='spend'
  row['values']['effects'].append({'type':'not_implemented'})
  before=deepcopy(actor.__dict__,{id(self.rules):self.rules})
  with self.assertRaisesRegex(ValueError,'bundle unresolved'):
   engine.execute_source_policy_action(actor,actor,self.document)
  self.assertEqual(actor.__dict__,before)
  row['values']['effects'].pop()
  row['values']['ap']['amount']=999
  with self.assertRaisesRegex(ValueError,'insufficient'):
   engine.execute_source_policy_action(actor,actor,self.document)
  self.assertEqual(actor.__dict__,before)
  row['values']['ap']['amount']=0
  engine._active_turn_actor=None
  with self.assertRaisesRegex(ValueError,'permission or budget'):
   engine.execute_source_policy_action(actor,actor,self.document)
  self.assertEqual(actor.__dict__,before)
  engine._active_turn_actor=actor
  row['values']['action']='standard';row['values']['ap']['amount']=1
  actor.conditions.add('잠듦')
  with self.assertRaisesRegex(ValueError,'permission or budget'):
   engine.execute_source_policy_action(actor,actor,self.document)
  actor.conditions.remove('잠듦')
  self.assertEqual(actor.__dict__,before)
  engine.execute_source_policy_action(actor,actor,self.document)
  self.assertEqual(actor.spec['ap_spent'],1)
  self.assertEqual(actor.spec['ap_removed'],2)
  self.assertEqual(actor.budget,{'standard':0,'shift':1,'swift':1})
  actor.budget={'standard':1,'shift':1,'swift':1}
  stable=deepcopy(actor.__dict__,{id(self.rules):self.rules})
  rng=engine.rng.getstate()
  row['source']['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'source changed'):
   engine.execute_source_policy_action(actor,actor,self.document)
  self.assertEqual(actor.__dict__,stable);self.assertEqual(engine.rng.getstate(),rng)
  row['source']=self.row(self.uid)['source']
  self.rules.ruleset=RuleFilter({'exclude_units':[self.uid]})
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
  with self.assertRaisesRegex(ValueError,'exactly one'):
   engine.execute_source_policy_action(actor,actor,self.document)
  self.assertEqual(actor.__dict__,stable);self.assertEqual(engine.rng.getstate(),rng)

 def test_errata_preserved_class_ability_retains_source_and_restore(self):
  from engine import Engine,Combatant
  from builder import build_trainer
  import items, state_grants as G
  engine=Engine(self.rules)
  actor=Combatant(self.rules,build_trainer(self.rules,'legacy-grant',10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  actor.spec['feats']=['일그러진 영혼']
  engine.everyone=[actor];engine.gm.everyone=[actor]
  self.assertIn('errata',self.rules.ruleset.sources)
  self.assertEqual(items.register_feats(engine,actor),1)
  sources=actor.spec[G.KEY]['sources']
  keys=[key for key,row in sources.items() if row.get('rule_id')=='feat/일그러진-영혼']
  self.assertEqual(len(keys),1)
  self.assertEqual(sources[keys[0]]['grants']['abilities'],['트위스트파워'])
  self.assertIn('트위스트파워',actor.abilities)
  self.assertEqual(items.register_feats(engine,actor),0)
  engine.gm.snapshot('legacy-grant')
  G.revoke(actor,keys[0],engine=engine)
  self.assertNotIn('트위스트파워',actor.abilities)
  engine.gm.restore('legacy-grant',reason='restore preserved class grant')
  self.assertIn('트위스트파워',actor.abilities)
  self.assertEqual(actor.spec[G.KEY]['sources'][keys[0]]['rule_id'],'feat/일그러진-영혼')

 def test_decision_record_is_scoped_detached_and_restored_atomically(self):
  from engine import Engine,Combatant
  from builder import build_trainer
  import json
  engine=Engine(self.rules)
  actor=Combatant(self.rules,build_trainer(self.rules,'decision-record',10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  engine.everyone=[actor];engine.gm.everyone=[actor]
  row=self.document['variants'][0]
  row['inputs']={'amount':{'type':'integer','authority':'gm','question':'Adjudicated stage change','choices':[0,2]}}
  row['values']={'effects':[{'type':'stage_change','stat':'atk','delta':{'$input':'amount'},'target':'self'}]}
  decisions={'amount':{'value':2,'reason':'table chooses bounded amount'}}
  result=engine.execute_source_policy_effects(actor,actor,self.document,decisions=decisions)
  key=result['execution_id'];record=engine.source_policy_execution(key)
  self.assertEqual(record['actor_id'],actor.entity_id)
  self.assertEqual(record['target_id'],actor.entity_id)
  self.assertEqual(record['scope']['kind'],'single_execution')
  self.assertEqual(record['input_values'],{'amount':2})
  self.assertEqual(record['decision_evidence'][0]['reason'],'table chooses bounded amount')
  self.assertEqual(json.loads(json.dumps(record)),record)
  record['input_values']['amount']=99
  self.assertEqual(engine.source_policy_execution(key)['input_values']['amount'],2)
  engine.gm.snapshot('policy-evidence')
  second=engine.execute_source_policy_effects(actor,actor,self.document,decisions=decisions)
  self.assertNotEqual(key,second['execution_id'])
  engine.gm.restore('policy-evidence',reason='restore execution and evidence together')
  self.assertEqual(engine.source_policy_execution(key)['input_values']['amount'],2)
  with self.assertRaises(KeyError):engine.source_policy_execution(second['execution_id'])
  before=deepcopy(engine._source_policy_executions);seq=engine._source_policy_sequence
  row['values']['effects'].append({'type':'not_implemented'})
  with self.assertRaisesRegex(ValueError,'bundle unresolved'):
   engine.execute_source_policy_effects(actor,actor,self.document,decisions=decisions)
  self.assertEqual(engine._source_policy_executions,before)
  self.assertEqual(engine._source_policy_sequence,seq)

 def test_explicit_versions_select_complete_definition_without_inheritance(self):
  base=self.document['variants'][0];base['inputs']={}
  base['values']={'cost':1,'base_only':True,'effect':'base'}
  alternate=deepcopy(base);alternate['version']='alternate'
  alternate['values']={'cost':3,'effect':'alternate'}
  self.document['variants'].append(alternate)
  self.assertEqual(self.resolve()['values'],base['values'])
  self.rules.ruleset=RuleFilter({'unit_versions':{self.uid:'alternate'}})
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
  result=self.resolve()
  self.assertEqual(result['values'],{'cost':3,'effect':'alternate'})
  self.assertEqual(result['selected_version'],'alternate')
  self.document['variants'].pop()
  with self.assertRaisesRegex(ValueError,'authored policy or version'):self.resolve()

 def test_versioned_effects_execute_and_record_selected_version(self):
  from engine import Engine,Combatant
  from builder import build_trainer
  self.rules.ruleset=RuleFilter({'unit_versions':{self.uid:'alternate'}})
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
  engine=Engine(self.rules)
  actor=Combatant(self.rules,build_trainer(self.rules,'versioned-policy',10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  engine.everyone=[actor];engine.gm.everyone=[actor]
  row=self.document['variants'][0];row['inputs']={};row['version']='alternate'
  row['values']={'effects':[{'type':'stage_change','stat':'atk','delta':2,'target':'self'}]}
  result=engine.execute_source_policy_effects(actor,actor,self.document)
  self.assertEqual(actor.stages['atk'],2)
  self.assertEqual(engine.source_policy_execution(result['execution_id'])['selected_version'],'alternate')
  # The new authored reader does not relax older readers that lack version support.
  with self.assertRaises(ValueError):self.rules._selected_rule(self.uid)

 def source_definition(self, uid, file, locator, tags=()):
  return {'id':uid,'title':uid,'source':{'file':file,'sha256':sha256((ROOT/file).read_bytes()).hexdigest()},
          'locator':locator,'tags':list(tags),'rationale':'Explicit application-authored alternative; no automatic precedence'}

 def test_actual_mixed_sweeper_sources_keep_cost_and_effect_together(self):
  definitions=[self.source_definition('authored/mixed-body','input/ch05-pokemon.md',{'lines':[295,301]}),
               self.source_definition('authored/mixed-errata','input/supp-errata.md',{'lines':[793,796]}),
               self.source_definition('authored/mixed-csv','input/db/poke-edges.csv',{'record':65},tags=['homebrew'])]
  # These are reviewed selection payloads, not Edge acquisition execution.
  payloads=[{'tp_per_rank':1,'max_rank':3,'grant':{'kind':'level_up_stat_points','amount_per_rank':3,'stats':['hp','def','spd','spe']}},
            {'tp':2,'grant':{'kind':'ability','name':'트위스트파워'}},
            {'tp':3,'grant':{'kind':'ability','name':'트위스트파워'}}]
  document={'schema':1,'id':'mixed-sweeper-source-selection','variants':[
     {'rule_id':d['id'],'source':d['source'],'values':v,'inputs':{}} for d,v in zip(definitions,payloads)]}
  for selected,expected in zip(definitions,payloads):
   with self.subTest(selected=selected['id']):
    self.rules=copy(self.loaded);self.rules.rulings=Rulings()
    self.rules.ruleset=RuleFilter({'exclude_units':[d['id'] for d in definitions if d!=selected]})
    self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
    self.rules.register_source_policy_definitions(definitions)
    result=self.rules.resolve_source_policy(document)
    self.assertEqual(result['selected_id'],selected['id'])
    self.assertEqual(result['values'],expected)
    with self.assertRaisesRegex(ValueError,'unknown_variant_lineage'):
     self.rules._selected_rule('poke_edge/쌍두스위퍼')

 def test_source_registration_is_atomic_immutable_and_profile_scoped(self):
  valid=self.source_definition('authored/source-test','input/ch05-pokemon.md',{'lines':[295,301]})
  invalid=deepcopy(valid);invalid['id']='authored/bad';invalid['locator']={'lines':[0,999999]}
  before=set(self.rules.selection.units)
  with self.assertRaisesRegex(ValueError,'bounds'):
   self.rules.register_source_policy_definitions([valid,invalid])
  self.assertEqual(set(self.rules.selection.units),before)
  result=self.rules.register_source_policy_definitions([valid]);result[0]['title']='mutated'
  self.rules.register_source_policy_definitions([valid])
  changed=deepcopy(valid);changed['rationale']='different decision'
  with self.assertRaisesRegex(ValueError,'redefined'):
   self.rules.register_source_policy_definitions([changed])
  self.assertEqual(self.rules._authored_policy_sources[valid['id']],valid)
  doc={'schema':1,'id':'source-test','variants':[{'rule_id':valid['id'],'source':valid['source'],'values':{'value':1},'inputs':{}}]}
  self.assertEqual(self.rules.resolve_source_policy(doc)['values'],{'value':1})
  from engine import Engine,Combatant
  from builder import build_trainer
  engine=Engine(self.rules)
  actor=Combatant(self.rules,build_trainer(self.rules,'authored-source',10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  engine.everyone=[actor];engine.gm.everyone=[actor]
  doc['variants'][0]['values']={'effects':[{'type':'stage_change','stat':'def','delta':1,'target':'self'}]}
  executed=engine.execute_source_policy_effects(actor,actor,doc)
  self.assertEqual(actor.stages['def'],1)
  self.assertEqual(engine.source_policy_execution(executed['execution_id'])['authored_source'],valid)
  doc['variants'][0]['source']['sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'registered provenance'):self.rules.resolve_source_policy(doc)

 def package(self):
  source=self.source_definition('authored/package-source','input/ch05-pokemon.md',{'lines':[295,301]})
  policy={'schema':1,'id':'external-policy','variants':[{'rule_id':source['id'],'source':source['source'],
    'inputs':{'delta':{'type':'integer','authority':'gm','question':'Choose the declared adjustment'}},
    'values':{'effects':[{'type':'stage_change','stat':'spe','delta':{'$input':'delta'},'target':'self'}]}}]}
  return {'schema':1,'sources':[source],'policies':[policy]}

 def test_json_package_reloads_on_fresh_rules_and_executes_after_input(self):
  import json
  from engine import Engine,Combatant
  from builder import build_trainer
  raw=json.dumps(self.package(),ensure_ascii=False)
  fresh=Rules(ROOT)
  loaded=fresh.load_source_policy_package(raw)
  self.assertEqual(loaded[0]['status'],'PolicyInputsRequired')
  self.assertFalse(loaded[0]['execution_certified'])
  doc=fresh.source_policy_document('external-policy')
  copy_doc=fresh.source_policy_document('external-policy');copy_doc['variants'].clear()
  self.assertEqual(fresh.source_policy_document('external-policy'),doc)
  fresh.load_source_policy_package(raw) # identical reload is safe
  engine=Engine(fresh)
  actor=Combatant(fresh,build_trainer(fresh,'external-author',10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  engine.everyone=[actor];engine.gm.everyone=[actor]
  self.assertEqual(engine.execute_source_policy_effects(actor,actor,doc)['status'],'PolicyInputsRequired')
  self.assertEqual(actor.stages['spe'],0)
  result=engine.execute_source_policy_effects(actor,actor,doc,
     decisions={'delta':{'value':1,'reason':'explicit source-delegated adjustment'}})
  self.assertEqual(actor.stages['spe'],1)
  self.assertEqual(result['selected_id'],'authored/package-source')

 def test_bad_package_does_not_partially_register_sources_or_policies(self):
  package=self.package();bad=deepcopy(package['policies'][0]);bad['id']='bad-policy'
  bad['variants'][0]['values']['effects'][0]['type']='unsupported-operation'
  package['policies'].append(bad)
  original=self.rules.selection
  with self.assertRaisesRegex(ValueError,'unsupported package effect'):
   self.rules.load_source_policy_package(package)
  self.assertIs(self.rules.selection,original)
  self.assertFalse(hasattr(self.rules,'_source_policy_documents'))
  self.assertFalse(hasattr(self.rules,'_authored_policy_sources'))
  for raw in ['{"schema":1,"schema":1,"sources":[],"policies":[]}',
              '{"schema":NaN,"sources":[],"policies":[]}']:
   with self.subTest(raw=raw),self.assertRaises(ValueError):self.rules.load_source_policy_package(raw)
  self.rules.load_source_policy_package(self.package())
  altered=self.package();altered['policies'][0]['variants'][0]['values']['effects'][0]['stat']='atk'
  with self.assertRaisesRegex(ValueError,'cannot be redefined'):
   self.rules.load_source_policy_package(altered)
  self.assertEqual(self.rules.source_policy_document('external-policy'),self.package()['policies'][0])

 def test_typed_conditions_preserve_false_unknown_and_exact_types(self):
  row=self.document['variants'][0]
  row['inputs']={'level':{'type':'integer','authority':'context','question':'Actual level'},
                 'permission':{'type':'boolean','authority':'gm','question':'Source-delegated permission'}}
  row['values']={'value':1}
  row['when']={'all':[{'op':'ge','left':{'$input':'level'},'right':10},{'$input':'permission'}]}
  missing=self.resolve(context={'level':10})
  self.assertEqual(missing['condition']['truth'],'unknown')
  self.assertEqual(missing['status'],'PolicyInputsRequired')
  denied=self.resolve(context={'level':9})
  self.assertEqual(denied['condition']['truth'],'false')
  self.assertEqual(denied['status'],'PolicyNotApplicable')
  granted=self.resolve(context={'level':10},decisions={'permission':{'value':True,'reason':'permitted for this case'}})
  self.assertEqual(granted['condition']['truth'],'true')
  self.assertEqual(granted['status'],'PolicyValuesReady')
  # An invalid branch cannot hide behind a true disjunction.
  row['when']={'any':[True,{'op':'ge','left':{'$input':'permission'},'right':1}]}
  with self.assertRaisesRegex(ValueError,'matching exact types'):self.resolve()

 def test_condition_boolean_composition_truth_table(self):
  import source_policy_predicates as P
  specs={'a':{'type':'boolean'},'b':{'type':'boolean'}}
  states=[True,False,None]
  expected_all={(True,True):'true',(True,False):'false',(True,None):'unknown',
                (False,True):'false',(False,False):'false',(False,None):'false',
                (None,True):'unknown',(None,False):'false',(None,None):'unknown'}
  expected_any={(True,True):'true',(True,False):'true',(True,None):'true',
                (False,True):'true',(False,False):'false',(False,None):'unknown',
                (None,True):'true',(None,False):'unknown',(None,None):'unknown'}
  for a in states:
   for b in states:
    values={k:v for k,v in [('a',a),('b',b)] if v is not None}
    for op,expected in [('all',expected_all),('any',expected_any)]:
     with self.subTest(a=a,b=b,op=op):
      result=P.evaluate({op:[{'$input':'a'},{'$input':'b'}]},specs,values)
      self.assertEqual(result.truth.value,expected[(a,b)])

 def test_condition_gates_action_costs_and_effects(self):
  from engine import Engine,Combatant
  from builder import build_trainer
  engine=Engine(self.rules)
  actor=Combatant(self.rules,build_trainer(self.rules,'conditional-action',10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  engine.everyone=[actor];engine.gm.everyone=[actor]
  engine.encounter_active=True;engine.round_start_seconds=0;engine._active_turn_actor=actor
  actor.budget={'standard':1,'shift':1,'swift':1};actor._turn_start_decisions_pending=False
  row=self.document['variants'][0]
  row['inputs']={'permission':{'type':'boolean','authority':'gm','question':'Rule delegated permission'}}
  row['when']={'$input':'permission'}
  row['values']={'action':'standard','ap':{'amount':1,'mode':'spend'},
                 'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}
  before=deepcopy(actor.__dict__,{id(self.rules):self.rules});rng=engine.rng.getstate()
  pending=engine.execute_source_policy_action(actor,actor,self.document)
  self.assertEqual(pending['status'],'PolicyInputsRequired')
  declined=engine.execute_source_policy_action(actor,actor,self.document,
      decisions={'permission':{'value':False,'reason':'not permitted'}})
  self.assertEqual(declined['status'],'PolicyNotApplicable')
  self.assertEqual(actor.__dict__,before);self.assertEqual(engine.rng.getstate(),rng)
  result=engine.execute_source_policy_action(actor,actor,self.document,
      decisions={'permission':{'value':True,'reason':'explicitly permitted'}})
  self.assertEqual(actor.stages['atk'],1);self.assertEqual(actor.spec['ap_spent'],1)
  self.assertEqual(engine.source_policy_execution(result['execution_id'])['condition']['truth'],'true')

 def test_native_state_bindings_read_live_actor_and_target_not_caller_values(self):
  from engine import Engine,Combatant
  from builder import build_trainer
  engine=Engine(self.rules)
  def make(name,level):return Combatant(self.rules,build_trainer(self.rules,name,level,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  actor=make('native-facts',20);target=make('native-target',10)
  actor.spec.update(skills={'육상':6},edges=['거장'],edge_choices={'edge/거장':['육상']})
  engine.everyone=[actor,target];engine.gm.everyone=[actor,target]
  row=self.document['variants'][0]
  def fact(subject,field,skill=None):
   binding={'subject':subject,'field':field}
   if skill:binding['skill']=skill
   return {'type':'integer','authority':'state','question':'Read actual '+field,'binding':binding}
  row['inputs']={'level':fact('actor','level'),'rank':fact('actor','skill_rank','육상'),
                 'effective':fact('actor','effective_skill_rank','육상'),'target_level':fact('target','level')}
  row['when']={'op':'ge','left':{'$input':'level'},'right':21}
  row['values']={'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}
  self.assertEqual(self.resolve()['status'],'PolicyInputsRequired')
  before=actor.stages['atk']
  result=engine.execute_source_policy_effects(actor,target,self.document)
  self.assertEqual(result['status'],'PolicyNotApplicable')
  self.assertEqual(result['input_values'],{'level':20,'rank':6,'effective':8,'target_level':10})
  self.assertEqual(actor.stages['atk'],before)
  with self.assertRaisesRegex(ValueError,'non-context'):
   engine.execute_source_policy_effects(actor,target,self.document,context={'level':99})
  with self.assertRaisesRegex(ValueError,'non-delegated'):
   engine.execute_source_policy_effects(actor,target,self.document,decisions={'level':{'value':99,'reason':'override'}})
  actor.level=21
  result=engine.execute_source_policy_effects(actor,target,self.document)
  self.assertEqual(actor.stages['atk'],before+1)
  record=engine.source_policy_execution(result['execution_id'])
  self.assertEqual(record['input_values']['level'],21)
  self.assertEqual(record['state_bindings']['target_level']['subject'],'target')
  fake=copy(target)
  with self.assertRaisesRegex(ValueError,'actual registered'):
   engine.execute_source_policy_effects(actor,fake,self.document)
  row['inputs']['rank']['binding']['skill']='unknown-skill'
  with self.assertRaisesRegex(ValueError,'unknown PTK skill'):
   engine.execute_source_policy_effects(actor,target,self.document)

 def test_native_state_binding_schema_cannot_read_arbitrary_attributes(self):
  row=self.document['variants'][0];row['values']={'value':1}
  for binding in [{'subject':'actor','field':'__dict__'},
                  {'subject':'actor','field':'level','path':['spec','private']},
                  {'subject':'everyone','field':'level'}]:
   row['inputs']={'x':{'type':'integer','authority':'state','question':'read','binding':binding}}
   with self.subTest(binding=binding),self.assertRaises(ValueError):self.resolve()

 def test_execution_requires_actual_world_participants_without_state_inputs(self):
  from engine import Engine, Combatant
  from builder import build_trainer
  engine=Engine(self.rules)
  def make(name):return Combatant(self.rules,build_trainer(self.rules,name,10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  actor=make('registered-author');target=make('registered-recipient')
  outsider=make('unregistered-recipient')
  engine.everyone=[actor,target];engine.gm.everyone=[actor,target]
  row=self.document['variants'][0];row['inputs']={}
  row['values']={'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}
  # Compare observable state without copying the shared Rules identity.
  def snapshot():
   return ([deepcopy({k:v for k,v in vars(c).items() if k!='r'}) for c in (actor,target,outsider)],
           engine.rng.getstate(),deepcopy(getattr(engine,'_source_policy_executions',{})),
           getattr(engine,'_source_policy_sequence',0))
  foreign=copy(target);foreign.r=copy(self.rules)
  for who,recipient in [(outsider,target),(actor,outsider),(copy(actor),target),(actor,copy(target))]:
   with self.subTest(actor=who.entity_id,target=recipient.entity_id):
    before=snapshot()
    with self.assertRaisesRegex(ValueError,'actual registered'):
     engine.execute_source_policy_effects(who,recipient,self.document)
    self.assertEqual(snapshot(),before)
  # Even registration cannot authorize an actor attached to another Rules world.
  engine.everyone=[actor,foreign];engine.gm.everyone=[actor,foreign]
  before=snapshot()
  with self.assertRaisesRegex(ValueError,'actual registered'):
   engine.execute_source_policy_effects(actor,foreign,self.document)
  self.assertEqual(snapshot(),before)
  engine.everyone=[actor,target];engine.gm.everyone=[actor,target]
  engine.encounter_active=True;engine.round_start_seconds=0;engine._active_turn_actor=actor
  actor.budget={'standard':1,'shift':1,'swift':1}
  actor._turn_start_decisions_pending=False
  row['values'].update(action='standard',ap={'amount':1,'mode':'spend'})
  # Neither constant declarations nor actor-only reads may bypass target checks.
  for inputs in [{},{'level':{'type':'integer','authority':'state','question':'Actor level',
                             'binding':{'subject':'actor','field':'level'}}}]:
   row['inputs']=inputs
   before=snapshot();log=list(engine.log_lines)
   with self.assertRaisesRegex(ValueError,'actual registered'):
    engine.execute_source_policy_action(actor,outsider,self.document)
   self.assertEqual(snapshot(),before);self.assertEqual(engine.log_lines,log)
  row['inputs']={}
  row['values'].pop('action');row['values'].pop('ap')
  # Repeated references to the same actual object remain valid aliases.
  engine.everyone=[actor,target,actor];engine.gm.everyone=[actor,target]
  before=actor.stages['atk']
  result=engine.execute_source_policy_effects(actor,actor,self.document)
  self.assertEqual(result['status'],'PolicyEffectsCompleted')
  self.assertEqual(actor.stages['atk'],before+1)

 def test_changed_profile_rejects_cached_policy_and_native_reads_before_costs(self):
  from engine import Engine,Combatant
  from builder import build_trainer
  from ruleset import UnresolvedRuleSelection
  self.rules.ruleset=deepcopy(self.loaded.ruleset)
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
  engine=Engine(self.rules)
  actor=Combatant(self.rules,build_trainer(self.rules,'profile-current',10,
      {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[]))
  engine.everyone=engine.gm.everyone=[actor]
  engine.encounter_active=True;engine.round_start_seconds=0;engine._active_turn_actor=actor
  actor.budget={'standard':1,'shift':1,'swift':1};actor._turn_start_decisions_pending=False
  row=self.document['variants'][0];row['inputs']={}
  row['values']={'action':'standard','ap':{'amount':1,'mode':'spend'},
                'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}
  before=deepcopy(actor.__dict__,{id(self.rules):self.rules});rng=engine.rng.getstate()
  original=self.rules.ruleset
  for replace in (False,True):
   if replace:self.rules.ruleset=RuleFilter({'exclude_units':[self.uid]})
   else:original.exclude_units.add(self.uid)
   with self.subTest(replace=replace):
    with self.assertRaisesRegex(UnresolvedRuleSelection,'selection_profile_changed'):
     engine.execute_source_policy_action(actor,actor,self.document)
    with self.assertRaisesRegex(UnresolvedRuleSelection,'selection_profile_changed'):
     self.rules.mech(self.uid)
    self.assertEqual(actor.__dict__,before);self.assertEqual(engine.rng.getstate(),rng)
    self.assertFalse(getattr(engine,'_source_policy_executions',{}))
   original.exclude_units.discard(self.uid);self.rules.ruleset=original
  result=engine.execute_source_policy_action(actor,actor,self.document)
  self.assertEqual(result['status'],'PolicyActionCompleted')
  self.assertEqual(actor.spec['ap_spent'],1)
  self.assertEqual(actor.stages['atk'],before['stages']['atk']+1)

if __name__=='__main__':unittest.main()
