"""Selection foundation public contract and reuse by native/external readers."""
from pathlib import Path
from copy import copy,deepcopy
from hashlib import sha256
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_source_policy as fixture
from ruleset import RuleFilter,RuleSelection

class SourceSelectionTests(unittest.TestCase):
 setUpClass=classmethod(fixture.Tests.setUpClass.__func__)
 row=fixture.Tests.row
 supplied=fixture.Tests.supplied
 def setUp(self):fixture.Tests.setUp(self)
 def select(self,**kw):return self.rules.select_source_definition(self.uid,source=self.row(self.uid)['source'],**kw)
 def test_record_is_detached_and_revalidated_not_an_authority_token(self):
  record=self.select();self.assertEqual(record['selected_id'],self.uid)
  self.assertEqual(self.rules.validate_source_selection(record),record)
  record['source']['file']='another.md'
  with self.assertRaisesRegex(ValueError,'selection changed'):self.rules.validate_source_selection(record)
  self.assertNotEqual(self.rules.selection.units[self.uid]['source']['file'],'another.md')
  record=self.select();record['schema']=True
  with self.assertRaises(ValueError):self.rules.validate_source_selection(record)

 def test_policy_binding_keeps_complete_values_and_rejects_locator_version_or_ambiguity(self):
  row=self.row(self.uid);known=deepcopy(row)
  binding=self.rules.bind_source_policy(self.uid,row)
  self.assertEqual(binding['definition']['values']['cost'],2)
  row['values']['cost']=99
  self.assertEqual(binding['definition']['values']['cost'],2)
  self.assertEqual(known,self.row(self.uid))
  for change in ('locator','version','ambiguity'):
   candidate=deepcopy(known)
   if change=='locator':candidate['locator']={'lines':[999999,999999]}
   elif change=='version':candidate['version']='unselected-version'
   else:candidate=[candidate,dict(deepcopy(candidate),values={'cost':99})]
   with self.subTest(change=change),self.assertRaisesRegex(ValueError,'complete source policy'):
    self.rules.bind_source_policy(self.uid,candidate)

 def test_policy_history_requires_known_values_and_never_reselects_current_authority(self):
  import source_selection
  row=self.row(self.uid);binding=self.rules.bind_source_policy(self.uid,row)
  with patch.object(self.rules,'_selected_rule',side_effect=AssertionError('history is not a new activation')):
   self.assertEqual(source_selection.policy_values(binding,[row])['cost'],2)
  binding['definition']['values']['cost']=99
  from root_resolution import fingerprint
  binding['definition_hash']=fingerprint(binding['definition'])
  with self.assertRaisesRegex(ValueError,'known producing'):
   source_selection.policy_values(binding,[row])
  row['values']={'enabled':True};binding=self.rules.bind_source_policy(self.uid,row)
  binding['definition']['values']['enabled']=1
  binding['definition_hash']=fingerprint(binding['definition'])
  with self.assertRaisesRegex(ValueError,'known producing'):
   source_selection.policy_values(binding,[row])

 def test_policy_binding_calls_custom_reader_and_preserves_registered_locator_without_new_package_fields(self):
  uid='authored/selection/policy-record';file='input/db/edges.csv'
  source={'file':file,'sha256':sha256((ROOT/file).read_bytes()).hexdigest()}
  self.rules.register_source_policy_definitions([{'id':uid,'title':'미용사','source':source,
   'locator':{'record':24},'tags':[],'rationale':'existing public declaration locator'}])
  row={'rule_id':uid,'source':source,'values':{'target_limit':'trainer_skill_rank'}}
  binding=self.rules.bind_source_policy(uid,row)
  self.assertEqual(binding['selection']['source']['record'],24)
  with patch.object(self.rules,'_selected_rule',side_effect=ValueError('custom reader denies')) as reader:
   with self.assertRaisesRegex(ValueError,'custom reader denies'):self.rules.bind_source_policy(uid,row)
  reader.assert_called_once_with(uid)
 def test_rebuilt_excluding_profile_invalidates_prior_record(self):
  record=self.select();self.rules.ruleset=RuleFilter({'exclude_units':[self.uid]})
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
  with self.assertRaises(ValueError):self.rules.validate_source_selection(record)
 def test_explicit_versions_require_reader_support(self):
  self.rules.ruleset=RuleFilter({'unit_versions':{self.uid:'reviewed-version'}})
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
  with self.assertRaises(ValueError):self.select()
  record=self.select(supports_versions=True);self.assertEqual(record['version'],'reviewed-version')
  self.assertEqual(self.rules.validate_source_selection(record),record)
 def test_changed_source_after_record_is_rejected(self):
  source=self.row(self.uid)['source']
  with TemporaryDirectory() as directory:
   rules=copy(self.rules);rules.root=directory;p=Path(directory)/source['file'];p.parent.mkdir(parents=True);p.write_bytes((ROOT/source['file']).read_bytes())
   record=rules.select_source_definition(self.uid,source=source)
   p.write_bytes(p.read_bytes()+b'\nchanged source\n')
   with self.assertRaisesRegex(ValueError,'source changed'):rules.validate_source_selection(record)
 def test_native_context_and_external_policy_share_selection_contract(self):
  original=self.rules.select_source_definition
  with patch.object(self.rules,'select_source_definition',wraps=original) as selected:
   self.rules.mech(self.uid)
   self.rules.resolve_source_policy(self.document,**self.supplied())
  calls=[c for c in selected.call_args_list if c.args==(self.uid,)]
  self.assertTrue(any(c.kwargs.get('source') is None for c in calls))
  self.assertTrue(any(c.kwargs.get('source')==self.row(self.uid)['source'] for c in calls))

 def test_same_named_body_and_csv_sources_keep_distinct_records(self):
  name='미용사';body='edge/미용사';file='input/db/edges.csv'
  definition={'id':'authored/selection/groomer-csv','title':name,
   'source':{'file':file,'sha256':sha256((ROOT/file).read_bytes()).hexdigest()},
   'locator':{'record':24},'tags':[],
   'rationale':'CSV target limit and body XP bonus must retain distinct source identities'}
  self.rules.register_source_policy_definitions([definition])
  csv=self.rules.select_source_definition(definition['id'],source=definition['source'])
  original=self.rules.select_source_definition(body)
  self.assertNotEqual(csv['selected_id'],original['selected_id'])
  self.assertEqual(csv['source']['record'],24)
  self.assertEqual(original['source']['file'],'ch03-skills-edges-feats.md')
  with self.assertRaisesRegex(ValueError,'does not match'):
   self.rules.select_source_definition(body,source=definition['source'])
 def test_native_policy_uses_shared_contract_for_active_sources_only(self):
  import native_rule_policy as policy
  original=self.rules.select_source_definition
  with patch.object(self.rules,'select_source_definition',wraps=original) as selected:
   outcome=policy.evaluate(self.rules,'skill_stunt',{'dowsing':False})
  self.assertEqual(outcome['values']['pool'],{'dice':-1,'modifier':6})
  identities={call.args[0] for call in selected.call_args_list}
  self.assertIn(policy.PRECEDENCE_SOURCE,identities)
  self.assertIn(policy.SOURCE['stunt'],identities)
  self.assertNotIn(policy.SOURCE['dowsing'],identities)

 def test_registered_source_snapshots_are_checked_without_caller_hash(self):
  import json
  registry=json.loads((ROOT/'data/content-source-identities.json').read_text(encoding='utf-8'))
  units=registry['units']
  pinned=[unit for unit in units if 'sha256' in unit['source']]
  # Three exact CSV rows and Enhanced Embrace were added to the prior144 snapshots.
  added={'C2CSV/input/db/feats.csv:R7:main':('db/feats.csv',[7,7],'record_span'),
         'C2CSV/input/db/feats.csv:R253:main':('db/feats.csv',[253,253],'record_span'),
         'C2CSV/input/db/feats.csv:R273:main':('db/feats.csv',[273,273],'record_span'),
         'feat/강화된-포용':('supp-fantasy.md',[923,939],'lines')}
  self.assertEqual(len(pinned),144+len(added))
  by_id={unit['id']:unit for unit in pinned};self.assertEqual(len(by_id),144+len(added))
  for uid,(file,span,key) in added.items():
   self.assertEqual((by_id[uid]['source']['file'],by_id[uid]['source'][key]),(file,span))
  for number in (14,15,16,17):
   uid='C2CSV/input/db/feats.csv:R'+str(number)+':main'
   self.assertEqual(by_id[uid]['source']['record_span'],[number,number])
  # Retain the earlier exact CSV/front anchors alongside the four Training sources.
  for number in (759,51,107,110,265,33,36,128):
   uid='C2CSV/input/db/feats.csv:R'+str(number)+':main'
   self.assertEqual(by_id[uid]['source']['record_span'],[number,number])
  front=by_id['source/front/translation-table-authority']['source']
  self.assertEqual((front['file'],front['lines']),('ch00-front.md',[9,13]))
  for unit in pinned:
   with self.subTest(identity=unit['id']):
    self.assertEqual(unit['source']['sha256'],registry['source_snapshots'][unit['source']['file']])
    record=self.rules.select_source_definition(unit['id'])
    self.assertEqual(record['selected_id'],unit['id'])
    self.assertEqual(record['verified_reference']['sha256'],unit['source']['sha256'])
    for field in ('file','lines','record_span'):
     if field in unit['source']:self.assertEqual(record['source'][field],unit['source'][field])
    self.assertEqual(self.rules.validate_source_selection(record),record)
 def test_pinned_native_csv_rejects_changed_bytes_and_replacement_hash(self):
  uid='C2CSV/input/db/edges.csv:R24:main'
  record=self.rules.select_source_definition(uid);self.assertEqual(record['source']['record_span'],[24,24])
  original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged' if path.name=='edges.csv' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):self.rules.select_source_definition(uid)
  with self.assertRaisesRegex(ValueError,'snapshot'):
   self.rules.select_source_definition(uid,source={'file':'input/db/edges.csv','sha256':'0'*64})

 def test_native_reader_checks_registered_body_source_without_public_record(self):
  original=Path.read_bytes
  self.rules.mech('combat/struggle')
  file=self.rules.selection.units['combat/struggle']['source']['file']
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged' if path.as_posix().endswith('/input/'+file) else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):self.rules.mech('combat/struggle')
 def test_source_change_rejects_real_training_before_time_xp_and_rng(self):
  import test_category2_progression_state as progression
  from state_codec import dump_engine
  progression.ProgressionStateTests.r=self.rules
  fixture=progression.ProgressionStateTests();fixture.setUp();pokemon=fixture.pokemon(5)
  before=dump_engine(fixture.e);original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged' if path.name=='ch05-pokemon.md' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):fixture.train(pokemon)
  self.assertEqual(before,dump_engine(fixture.e))

 def test_derived_reader_checks_dependency_source_before_returning_identity(self):
  from ruleset import RuleSelection
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.loaded.selection.units.values()))
  uid='derived/source-selection-test'
  self.rules.selection.register_derived({'id':uid,'title':'derived reader',
   'source':{'file':'ch09-equipment.md'}},['combat/struggle'])
  self.assertEqual(self.rules._selected_rule(uid),uid)
  file=self.rules.selection.units['combat/struggle']['source']['file'];original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged' if path.as_posix().endswith('/input/'+file) else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):self.rules._selected_rule(uid)


 def exclude(self,uid):
  self.rules.ruleset=RuleFilter({'exclude_units':[uid]})
  self.rules.selection=RuleSelection(self.rules.ruleset,list(self.rules.selection.units.values()))

 def test_acquired_chocolate_cannot_spend_or_heal_after_its_source_is_excluded(self):
  from test_category3_food_effects import FoodTests
  f=FoodTests();f.rules=self.rules;f.setUp();f.p.hp=1
  acquired=f.snack();self.exclude('item/초코바');before=f.state()
  with self.assertRaises(ValueError):
   f.e.consume_food_buff(f.p,buff_id=acquired['buff_id'],action_kind='swift',action_reason='actual buff use')
  self.assertEqual(f.state(),before)

 def test_acquired_stat_exception_cannot_survive_excluded_definition(self):
  from test_category2_stat_edge_state import StatEdgeStateTests
  import pokemon_stat_edges as stat,downtime
  f=StatEdgeStateTests();f.r=self.rules;f.setUp();pokemon=f.pokemon()
  raised=f.state_for_boundary(pokemon,'atk');f.teach(pokemon,'atk')
  self.assertEqual(stat.exemptions(self.rules,pokemon.spec),{'atk'})
  self.exclude(stat.ATTACK_CONFLICT);before=f.snap()
  with self.assertRaises(ValueError):
   downtime.gain_exp_combatant(f.e,pokemon,'to next level',stat_choices={36:raised})
  self.assertEqual(f.snap(),before)

 def test_tutor_cannot_borrow_excluded_feature_before_spending(self):
  from test_category2_mentor_move_state import MentorMoveStateTests
  import pokemon_teaching as teaching
  f=MentorMoveStateTests();f.r=self.rules;f.setUp();pokemon=f.pokemon(5)
  self.exclude(teaching.MOVE_TUTOR);before=f.before(pokemon)
  with self.assertRaises(ValueError):f.teach(pokemon,'열풍',teaching.MOVE_TUTOR)
  self.assertEqual(f.before(pokemon),before)

 def test_display_name_lookup_rechecks_selected_source(self):
  # The display-name fallback must have the same freshness boundary as IDs.
  uid='move/화염방사';alias='Flamethrower display alias'
  self.rules.moves=deepcopy(self.rules.moves);self.rules.moves[uid]['name']=alias
  units=deepcopy(list(self.rules.selection.units.values()))
  for unit in units:
   if unit['id']==uid:unit['name']=alias;unit['title']=alias
  self.rules.selection=RuleSelection(self.rules.ruleset,units)
  self.assertEqual(self.rules.move_id(alias),uid)
  original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged' if path.name=='moves.csv' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):self.rules.move_id(alias)

 def test_expand_horizons_feature_does_not_admit_same_named_unresolved_edge(self):
  from ruleset import UnresolvedRuleSelection
  feature='feat/시야-넓히기';edge='poke_edge/unreviewed-expand-alias'
  unit=deepcopy(self.rules.selection.units['poke_edge/시야-넓히기'])
  unit.update(id=edge,source_group='기타/홈브류');unit['source']['record_span']=[65,65]
  selection=RuleSelection(self.rules.ruleset,[deepcopy(self.rules.selection.units[feature]),unit])
  self.assertEqual(selection.resolve(feature),feature)
  with self.assertRaisesRegex(UnresolvedRuleSelection,'unknown_variant_lineage'):selection.resolve(edge)
  with self.assertRaises(UnresolvedRuleSelection):selection.resolve_name('시야 넓히기')

 def test_expand_horizons_reviewed_csv_keeps_distinct_source_and_name_ambiguity(self):
  from ruleset import UnresolvedRuleSelection
  feature='feat/시야-넓히기';edge='poke_edge/시야-넓히기'
  selected=self.rules.select_source_definition(feature)
  self.assertEqual(selected['selected_id'],feature)
  self.assertEqual(selected['source']['file'],'ch04-trainer-classes.md')
  csv=self.rules.select_source_definition(edge)
  self.assertEqual(csv['selected_id'],edge)
  self.assertEqual(csv['source']['file'],'db/poke-edges.csv')
  self.assertEqual(csv['verified_reference']['sha256'],'8e4bbb735033db781ca011f98885c1b5fe1b900da75a196b9e6f8734ceff946d')
  self.assertEqual(self.rules.selection.dependencies[edge],(feature,))
  with self.assertRaises(UnresolvedRuleSelection):
   self.rules.selection.resolve_name('시야 넓히기')
  self.assertEqual(self.rules.selection.resolve_name('시야 넓히기',('feat/',)),feature)
  self.assertEqual(self.rules.selection.resolve_name('시야 넓히기',('poke_edge/',)),edge)
  self.assertEqual(self.rules.selection.units[edge]['source']['record_span'],[64,64])

 def shock_package(self):
  import json
  package=json.loads((ROOT/'data/foundation-source-policy-package.json').read_text(encoding='utf-8'))
  result=self.rules.load_source_policy_package(package)
  self.assertEqual(result[0]['status'],'PolicyInputsRequired')
  return self.rules.source_policy_document(package['policies'][0]['id'])

 def test_optional_shock_injury_requires_explicit_gm_choice_without_default(self):
  document=self.shock_package()
  pending=self.rules.resolve_source_policy(document)
  self.assertEqual(pending['status'],'PolicyInputsRequired');self.assertIsNone(pending['values'])
  for choice in (False,True):
   result=self.rules.resolve_source_policy(document,decisions={'optional_injury_enabled':{'value':choice,'reason':'explicit campaign choice'}})
   self.assertEqual(result['values'],{'optional_injury_enabled':choice})
   self.assertFalse(result['effects_executed'])
  for wrong in ({'context':{'optional_injury_enabled':True}},
                {'decisions':{'optional_injury_enabled':{'value':1,'reason':'not boolean'}}},
                {'decisions':{'optional_injury_enabled':{'value':True,'reason':''}}}):
   with self.assertRaises(ValueError):self.rules.resolve_source_policy(document,**wrong)

 def test_optional_shock_policy_rechecks_selected_source_and_source_bytes(self):
  document=self.shock_package();original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged' if path.name=='supp-polygon.md' else raw
  supplied={'optional_injury_enabled':{'value':True,'reason':'campaign choice'}}
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):
    self.rules.resolve_source_policy(document,decisions=supplied)
  self.exclude('supp-polygon/증강의-단점')
  with self.assertRaises(ValueError):self.rules.resolve_source_policy(document,decisions=supplied)

 def test_every_minor_gift_keeps_outcome_dependencies_and_selected_source(self):
  import json
  f=json.loads((ROOT/'data/verification/category2-edge-work-plan.json').read_text(encoding='utf-8'))['foundation_discovery']
  self.assertEqual(len(f['minor_gift_candidates']),36)
  for gift in f['minor_gift_candidates']:
   with self.subTest(gift=gift['name']):
    self.assertTrue(gift['requirements']['outcome'])
    prefix=gift['file']+':L'+str(gift['start'])+'/'
    mapped=[r for r in f['unit_requirement_mapping']['mapped'] if r['requirement_ref'].startswith(prefix)]
    dependencies={uid for row in mapped for uid in row['unit_ids']}
    self.assertIn('source_policy.selection',dependencies)
    self.assertTrue(dependencies-{'source_policy.selection','scripting.load','scripting.execute','acquisition.qualification','acquisition.receipt','acquisition.withdrawal'})
    candidates=[]
    for uid,unit in self.rules.selection.units.items():
     source=unit['source'];bounds=source.get('lines',[])
     if source.get('file')==gift['file'].removeprefix('input/') and len(bounds)==2 and bounds[0]<=gift['start']<=gift['end']<=bounds[1]:candidates.append(uid)
    self.assertTrue(candidates)
    for uid in candidates:
     record=self.rules.select_source_definition(uid)
     self.assertEqual(record['selected_id'],uid)
     self.assertEqual(self.rules.validate_source_selection(record),record)

 def test_acquired_minor_gift_rejects_changed_supplement_before_actual_roll(self):
  import test_category3_blessing_skills as blessing_fixture
  import blessing_skill_features as gifts
  f=blessing_fixture.Tests();f.rules=self.rules;f.setUp();f.gift(gifts.STAGE)
  self.assertEqual(f.roll('매력',purpose='singing',fixed=[2]*3).total,8)
  before=f.snapshot();original=Path.read_bytes
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged' if path.name=='supp-blessings.md' else raw
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):f.roll('매력',purpose='singing')
  self.assertEqual(f.snapshot(),before)

 def test_native_feature_reader_cannot_choose_a_same_named_kind_by_priority(self):
  from ruleset import UnresolvedRuleSelection
  with self.assertRaises(UnresolvedRuleSelection):self.rules.feat_effects('시야 넓히기')
  # Exact identity preserves an unsupported reader result without borrowing
  # another kind's payload; source selection itself was tested independently.
  result=self.rules.feat_effects('feat/시야-넓히기')
  if result[0] is not None:self.assertEqual(result[1]['id'],'feat/시야-넓히기')

 def test_same_kind_duplicate_titles_require_exact_source_identity(self):
  from ruleset import UnresolvedRuleSelection
  for name,ids in [('작열',('feat/작열','feat/작열-1')),('타입 동기화',('feat/타입-동기화','feat/타입-동기화-1'))]:
   with self.subTest(name=name):
    with self.assertRaises(UnresolvedRuleSelection):self.rules.feat_effects(name)
    for uid in ids:
     result=self.rules.feat_effects(uid)
     if result[0] is not None:self.assertEqual(result[1]['id'],uid)
 def test_item_and_augmentation_same_name_do_not_choose_first_record(self):
  from ruleset import UnresolvedRuleSelection
  with self.assertRaises(UnresolvedRuleSelection):self.rules.item_effects('스마트비전')
  for uid in ('item/스마트비전','augment/스마트비전'):
   result=self.rules.item_effects(uid)
   if result[0] is not None:self.assertEqual(result[1]['id'],uid)

 def test_unrelated_ambiguous_inventory_does_not_block_selected_consumable(self):
  from test_category3_food_effects import FoodTests
  from ruleset import UnresolvedRuleSelection
  import item_stock
  f=FoodTests();f.rules=self.rules;f.setUp();f.p.hp=1
  f.a.spec['items']={'맛있는물':1,'다우징 로드':1}
  before=f.state()
  with self.assertRaises(UnresolvedRuleSelection):item_stock.prepare(f.e,f.a,'item/다우징-로드')
  self.assertEqual(f.state(),before)
  result=f.drink()
  self.assertEqual(result['healed'],min(20,f.p.max_hp-1))
  self.assertEqual(f.a.spec['items'],{'맛있는물':0,'다우징 로드':1})

if __name__=='__main__':unittest.main()
