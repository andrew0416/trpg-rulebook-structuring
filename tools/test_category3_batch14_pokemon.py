"""Full frozen scopes CORE060/062/063: actual creation, checks, moves and requests."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
from ruleset import RuleFilter
from custom_species import template_from
import pokemon_understanding as U
import regional_pokemon as R
import common_checks as C
CLAUSES=['C3-CORE-060','C3-CORE-062','C3-CORE-063']
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.core=Rules(str(ROOT),ruleset='core');cls.temp=tempfile.TemporaryDirectory()
  variant=template_from(cls.core,'깨비참','밤숲깨비참','GM explicit regional adaptation')
  variant.update(notes='black plumage for this forest; no bonus inferred from color',skills={'은신':4,'육상':2,'곡예':3,'전투':2,'집중':2,'통찰':3},movement={'land':4,'sky':7,'levitate':4},capabilities=['야시'],abilities={'기본 특성':['부유'],'숨겨진 특성':['방음'],'대단한 특성':[]},types=['악','비행'])
  variant['learnset']={'level_up':[{'level':1,'move':'쪼기'}],'tm':[],'tutor':[],'egg':[]}
  cls.variant_path=Path(cls.temp.name)/'night_forest.json';cls.variant_path.write_text(json.dumps(variant,ensure_ascii=False),encoding='utf8')
  cls.r=Rules(str(ROOT),ruleset='core')
  cls.r.ruleset=RuleFilter({'sources':['core','custom'],'variants':[]},'test-core-custom')
  cls.r.load_custom_species(str(cls.variant_path))
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def setUp(self):
  self.e=Engine(self.r,107)
  self.a=Combatant(self.r,build_trainer(self.r,'T',20,dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),skills={'포켓몬학':4,'명령':4},items={}))
  self.p=Combatant(self.r,build_pokemon(self.r,'잉어킹',5,name='p',extra={'trainer_id':self.a.spec['id'],'loyalty':3,'skills':{'육상':3,'전투':2,'매력':2}}))
  self.q=Combatant(self.r,build_pokemon(self.r,'깨비참',5,name='q',extra={'trainer_id':self.a.spec['id']}))
  self.e.everyone=[self.a,self.p,self.q];self.e.gm.everyone=self.e.everyone
 def act(self,activity,**kw):return self.e.pokemon_activity(self.a,activity,**kw)
 def state(self):return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),self.a.spec,self.p.spec,self.q.spec,self.p.hp,self.q.hp,getattr(self.p,'budget',None),getattr(self.p,'_action_history',None),len(self.e.gm.everyone)))
 def settings(self,**kw):
  args=dict(humanlike=False,outside_water={k:False for k in U.ACTIVITY_KINDS},discussed_with=['Alice','Bob'],reason='participants agreed before play');args.update(kw)
  return self.act('pokemon_settings',**args)
 def body(self,**kw):
  args=dict(target=self.p,aquatic_body=True,in_water=False,reason='GM observes a fish body on dry ground');args.update(kw)
  return self.act('observe_pokemon_body',**args)
 def profile(self,**kw):
  args=dict(target=self.p,habitat='its familiar freshwater river',organization='local school with a leader',domains={},reason='GM establishes individual scoped understanding');args.update(kw)
  return self.act('understanding_profile',**args)
 def request(self,**kw):
  args=dict(target=self.p,request_id='r',intent='retrieve a familiar object',understanding={'domains':['spatial_memory'],'context':'retrieve the previously shown basket'});args.update(kw)
  return self.act('request_help',**args)
 def assess(self,**kw):
  args=dict(target=self.p,request_id='r',decisions={'spatial_memory':True},reason='GM confirms it remembers this particular location');args.update(kw)
  return self.act('assess_pokemon_request',**args)
 def resolve(self,**kw):
  args=dict(target=self.p,request_id='r',decision='accept',explanation='GM confirms the understood request is accepted');args.update(kw)
  return self.act('resolve_help',**args)
 def region(self,**kw):
  args=dict(base_species='깨비참',variant_species='밤숲깨비참',individual_id='pokemon/regional1',name='Regional',level=5,region='Night Forest',ecological_context='competition with dark-feathered predators',rarity_reason='only this isolated population',reason='GM explicitly chooses this regional individual',abilities=['부유']);args.update(kw)
  return self.act('create_regional_pokemon',**args)
 def test_fixed_source_scopes_are_unchanged(self):
  rows=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf8'))['entries']
  for row in rows:
   if row['id'] not in CLAUSES:continue
   source=row['source_snapshot']['source'];actual='\n'.join((ROOT/source['file']).read_text(encoding='utf-8-sig').splitlines()[source['start']-1:source['end']])
   self.assertEqual(source['excerpt'],actual,row['id'])
 def test_regional_factory_separates_base_and_actual_native_skill_move_capability(self):
  base=deepcopy((self.r.species['pokemon/깨비참'],self.q.spec));made=self.region()
  self.assertEqual(base,(self.r.species['pokemon/깨비참'],self.q.spec));self.assertFalse(made.on_field)
  self.assertEqual(self.e.skill_roll(made,'은신',fixed=[2]*4).total,8);self.assertEqual(self.e.move_profile(made,'sky'),(7,'공중/부유'))
  self.assertIn('move/쪼기',made.moves);self.assertEqual(made.abilities,['부유']);self.assertIn('야시',made.spec['capabilities'])
  self.assertEqual(made.spec['regional_variant']['base_species'],'pokemon/깨비참');self.assertIn('black plumage',made.spec['regional_variant']['appearance'])
 def test_regional_native_known_move_and_selected_ability_effect(self):
  made=self.region();made.on_field=True;self.q.on_field=True
  self.e.register_abilities(made)
  self.assertTrue(any(x.get('type')=='immunity' and x.get('to')=='땅 moves' for x in made.modifiers))
  self.e.gm.set_types(made,['악'],'isolate the actual ability from Flying type immunity')
  self.assertEqual(self.e.roll_damage(self.q,made,self.r.move('move/지진'),set_damage=True),0)
  made.abilities_suppressed=True;self.assertGreater(self.e.roll_damage(self.q,made,self.r.move('move/지진'),set_damage=True),0);made.abilities_suppressed=False
  self.e.begin_encounter([made,self.q]);self.e.start_round([made,self.q]);self.e.start_of_turn(made)
  hp=self.q.hp;self.e.use_move(made,self.q,'move/쪼기',situational=100);self.assertLess(self.q.hp,hp)
 def test_regional_requires_concrete_choice_not_region_wide_automatic_bonus(self):
  before=self.state()
  with self.assertRaises(ValueError):self.region(rarity_reason='')
  with self.assertRaises(ValueError):self.region(variant_species='깨비참')
  with self.assertRaises(ValueError):self.region(abilities=['방음'])
  with self.assertRaises(ValueError):self.region(abilities=None)
  self.assertEqual(before,self.state());made=self.region()
  with self.assertRaises(ValueError):self.region()
  self.assertEqual(sum(c.spec.get('regional_variant') is not None for c in self.e.gm.everyone),1)
 def test_regional_source_selection_and_definition_change_reject_before_cost(self):
  made=self.region();old=dict(self.r.selection.aliases);self.r.selection.aliases[R.SOURCE]='edge/미용사'
  try:
   rng=self.e.rng.getstate()
   with self.assertRaises(ValueError):self.e.skill_roll(made,'은신')
   with self.assertRaises(ValueError):self.region(individual_id='new')
   self.assertEqual(rng,self.e.rng.getstate())
  finally:self.r.selection.aliases=old
  species=self.r.species[made.spec['species']];previous=deepcopy(species['movement']);species['movement']['sky']=99
  try:
   with self.assertRaises(ValueError):self.e.move_profile(made,'sky')
  finally:species['movement']=previous
 def test_regional_definition_custom_source_must_remain_selected(self):
  made=self.region();old=self.r.ruleset;self.r.ruleset=RuleFilter({'sources':['core'],'variants':[]},'core')
  try:
   with self.assertRaises(ValueError):self.e.skill_roll(made,'은신')
  finally:self.r.ruleset=old
 def test_profile_has_separate_domains_baselines_and_social_organization(self):
  before=deepcopy((self.p.stats,self.p.spec['skills'],self.p.moves));row=self.profile(domains={'tool_use':{'status':'unknown','scope':'human devices','basis':'no observed training'}})
  self.assertEqual(row['domains']['basic_commands']['status'],'expected');self.assertEqual(row['domains']['habitat_survival']['scope'],'its familiar freshwater river')
  self.assertEqual(row['organization'],'local school with a leader');self.assertEqual(before,(self.p.stats,self.p.spec['skills'],self.p.moves))
  with self.assertRaises(ValueError):self.profile(domains={'iq':100})
 def test_ordinary_command_comprehension_never_grants_obedience_or_ownership(self):
  self.profile();self.p.spec['loyalty']=0
  before=self.p.spec['trainer_id'];out=self.act('command_loyalty',target=self.p,fixed=[1]*4)
  self.assertFalse(out['obeys']);self.assertEqual(self.p.spec['trainer_id'],before)
 def test_actual_request_requires_scoped_understanding_before_native_execution(self):
  self.profile();self.request();before=self.state()
  with self.assertRaises(ValueError):self.resolve()
  self.assertEqual(before,self.state());self.assess();out=self.resolve();self.assertEqual(out['status'],'completed');self.assertIsInstance(out['result'],C.ActionOutcome)
  with self.assertRaises(ValueError):self.resolve()
 def test_understood_request_still_uses_actual_native_skill_check(self):
  self.profile();self.request();self.assess()
  out=self.resolve(decision='check',skill='육상',dc=9,roll_options={'fixed':[3]*3})
  self.assertEqual(out['request']['check']['total'],9);self.assertTrue(out['request']['check']['passed'])
  with self.assertRaises(ValueError):self.assess()
 def test_failed_native_precondition_ends_request_without_sprint_or_replay(self):
  self.profile();self.request(action='sprint',options={'source_policy':'ch07_turn'});self.assess()
  out=self.resolve(decision='check',skill='육상',dc=9,roll_options={'fixed':[1]*3});self.assertEqual(out['status'],'awaiting_result')
  before=deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),self.p.spec,self.p.custom_conditions,getattr(self.p,'budget',None),getattr(self.p,'_action_history',None)))
  out=self.resolve(outcome='failure');self.assertEqual(out['status'],'completed');self.assertEqual(out['result'].outcome,'failure');self.assertEqual(out['request']['last_phase'],'failed_precondition')
  self.assertEqual(before,(self.e.elapsed_seconds,self.e.rng.getstate(),self.p.spec,self.p.custom_conditions,getattr(self.p,'budget',None),getattr(self.p,'_action_history',None)));self.assertNotIn('질주',self.p.custom_conditions)
  with self.assertRaises(ValueError):self.resolve()
  self.assertEqual(len(self.a.spec['pokemon_requests']['r']['responses']),2)
 def test_regional_factory_snapshot_restores_roster_and_allows_unconsumed_identity(self):
  before=tuple(self.e.everyone);self.e.gm.snapshot('before_creation');made=self.region();self.e.gm.restore('before_creation')
  self.assertEqual(tuple(self.e.everyone),before);self.assertEqual(tuple(self.e.gm.everyone),before)
  other=self.region();self.assertIsNot(other,made);self.assertEqual(other.spec['id'],made.spec['id'])
 def test_each_explicit_communication_capability_is_optional_language_only(self):
  for capability in U.LANGUAGE_CAPABILITIES:
   self.setUp();self.profile();self.p.spec.setdefault('capabilities',[]).append(capability)
   self.request(understanding={'domains':['human_language'],'context':'this spoken request'});self.assess(decisions={'human_language':True},language_exception=capability)
   self.assertEqual(self.resolve()['status'],'completed');self.assertNotIn('education',self.p.spec['pokemon_understanding']['domains'])
 def test_unknown_or_false_facet_is_not_automatic_success(self):
  for value in (False,None):
   self.setUp();self.profile();self.request();self.assess(decisions={'spatial_memory':value});before=self.state()
   with self.assertRaises(ValueError):self.resolve()
   self.assertEqual(before,self.state());out=self.resolve(decision='refuse');self.assertEqual(out['status'],'refused')
 def test_experience_is_individual_scoped_and_does_not_invent_xp_or_global_iq(self):
  self.profile();before=deepcopy((self.p.stats,self.p.spec.get('exp'),self.p.spec.get('tutor_points'),self.q.spec))
  self.act('record_pokemon_experience',target=self.p,event_id='walk1',domains={'spatial_memory':{'status':'established','scope':'one familiar field layout'}},description='actual repeated walk with trainer and observed recall')
  self.assertEqual(before,(self.p.stats,self.p.spec.get('exp'),self.p.spec.get('tutor_points'),self.q.spec));self.assertNotIn('education',self.p.spec['pokemon_understanding']['domains'])
  with self.assertRaises(ValueError):self.act('record_pokemon_experience',target=self.p,event_id='walk1',domains={'tool_use':{'status':'established','scope':'all machinery'}},description='duplicate event')
 def test_profile_or_request_change_invalidates_unconsumed_assessment(self):
  for changed in ('profile','intent','options','settings'):
   self.setUp();self.profile();self.request();self.assess()
   if changed=='profile':self.profile(domains={'education':{'status':'unknown','scope':'human machines','basis':'no instruction'}})
   if changed=='intent':self.a.spec['pokemon_requests']['r']['intent']='operate a telephone'
   if changed=='options':self.a.spec['pokemon_requests']['r']['requested_options']={'mode':'skill','skill':'육상','dc':1}
   if changed=='settings':self.settings(humanlike=True)
   before=self.state()
   with self.assertRaises(ValueError):self.resolve()
   self.assertEqual(before,self.state())
 def test_request_options_cannot_be_replaced_behind_assessment(self):
  self.profile();self.request();self.assess();before=self.state()
  with self.assertRaises(ValueError):self.resolve(options={'mode':'no_roll','outcome':'success','description':'do an unrelated task'})
  self.assertEqual(before,self.state())
 def test_language_exception_needs_actual_capability_and_never_grants_education(self):
  self.profile();self.request(understanding={'domains':['human_language','education'],'context':'understand a spoken explanation of a telephone and operate it'})
  before=self.state()
  with self.assertRaises(ValueError):self.assess(decisions={'human_language':True,'education':None},language_exception='텔레파시')
  self.assertEqual(before,self.state());self.p.spec.setdefault('capabilities',[]).append('텔레파시')
  self.assess(decisions={'human_language':True,'education':None},language_exception='텔레파시');before=self.state()
  with self.assertRaises(ValueError):self.resolve()
  self.assertEqual(before,self.state());self.assess(decisions={'human_language':True,'education':True},language_exception='텔레파시',reason='GM confirms separate actual education on this device and communication ability')
  self.assertEqual(self.resolve()['status'],'completed')
 def test_lost_language_capability_and_selected_source_are_rechecked(self):
  self.profile();self.p.spec.setdefault('capabilities',[]).append('텔레파시');self.request(understanding={'domains':['human_language'],'context':'understand this spoken request'})
  self.assess(decisions={'human_language':True},language_exception='텔레파시');self.p.spec['capabilities'].remove('텔레파시');before=self.state()
  with self.assertRaises(ValueError):self.resolve()
  self.assertEqual(before,self.state())
 def test_campaign_settings_require_informed_explicit_choices(self):
  for kwargs in ({'humanlike':'yes'},{'outside_water':{}},{'outside_water':{k:1 for k in U.ACTIVITY_KINDS}},{'discussed_with':[]}):
   with self.assertRaises(ValueError):self.settings(**kwargs)
   self.assertFalse(hasattr(self.e,'_pokemon_setting_policy'))
 def test_humanlike_setting_is_permission_guidance_not_numeric_or_task_success(self):
  before=self.state();self.settings(humanlike=True);self.assertEqual(before,self.state())
  self.profile();self.request(understanding={'domains':['tool_use','education'],'context':'use unfamiliar fire extinguisher then telephone'})
  before=self.state()
  with self.assertRaises(ValueError):self.resolve()
  self.assertEqual(before,self.state())
 def test_water_type_does_not_infer_fish_body_or_forbid_actual_movement(self):
  self.settings();self.assertIn('물',self.p.types)
  self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[2]*3).total,6)
  self.body(aquatic_body=False);self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[2]*3).total,6)
 def test_registered_aquatic_outside_water_missing_policy_blocks_before_rng(self):
  self.body();before=self.state()
  with self.assertRaisesRegex(ValueError,'policy is unresolved'):self.e.skill_roll(self.p,'육상')
  self.assertEqual(before,self.state())
 def test_restricted_outside_water_blocks_native_move_skill_movement_sprint(self):
  self.settings();self.body();before=self.state()
  for fn in (lambda:self.e.skill_roll(self.p,'육상'),lambda:self.e.use_move(self.p,self.q,'struggle'),lambda:self.e.move_profile(self.p),lambda:self.e.sprint(self.p,source_policy='ch07_turn')):
   with self.assertRaises(ValueError):fn()
   self.assertEqual(before,self.state())
 def test_restricted_outside_water_blocks_no_roll_jump_before_shift_and_position(self):
  from grid import Grid
  self.settings();self.body();self.e.grid=Grid(10,10);self.p.pos=(1,1);self.p.spec['movement'].update(high_jump=1,long_jump=2)
  before=deepcopy((self.state(),self.p.pos,self.p.custom_conditions))
  with self.assertRaisesRegex(ValueError,'outside-water'):self.e.jump(self.p,(2,1),jump_id='dry-jump',difficult=False,clear_path=True,reason_text='actual clear short jump')
  self.assertEqual(before,(self.state(),self.p.pos,self.p.custom_conditions));self.assertNotIn('_jump_attempts',self.p.spec)
 def test_restricted_aquatic_request_refusal_is_allowed_but_execution_is_not(self):
  self.settings();self.body();self.request(understanding=None);before=self.state()
  with self.assertRaises(ValueError):self.resolve()
  self.assertEqual(before,self.state());self.assertEqual(self.resolve(decision='refuse')['status'],'refused')
 def test_functional_policy_and_return_to_water_do_not_create_capabilities(self):
  original=deepcopy(self.p.spec['movement']);self.settings(outside_water={k:True for k in U.ACTIVITY_KINDS});self.body()
  self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[2]*3).total,6);self.assertEqual(self.p.spec['movement'],original)
  self.settings();self.body(in_water=True);self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[2]*3).total,6)
 def test_each_outside_water_action_kind_is_independent(self):
  permissions={k:False for k in U.ACTIVITY_KINDS};permissions['skill']=True;self.settings(outside_water=permissions);self.body()
  self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[2]*3).total,6)
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.q,'struggle')
 def test_source_change_refuses_settings_body_profile_and_native_action_before_mutation(self):
  self.settings();self.body(in_water=True);old=dict(self.r.selection.aliases);self.r.selection.aliases[U.SOURCE]='edge/미용사'
  try:
   before=self.state()
   for fn in (self.settings,self.body,self.profile,lambda:self.e.skill_roll(self.p,'육상')):
    with self.assertRaises(ValueError):fn()
    self.assertEqual(before,self.state())
  finally:self.r.selection.aliases=old
 def test_snapshot_before_configuration_removes_later_setting_policy(self):
  self.e.gm.snapshot('before');self.settings();self.assertTrue(hasattr(self.e,'_pokemon_setting_policy'))
  self.e.gm.restore('before');self.assertFalse(hasattr(self.e,'_pokemon_setting_policy'))
 def test_snapshot_restores_policy_profile_body_and_request_consumption(self):
  self.settings(outside_water={k:True for k in U.ACTIVITY_KINDS});self.body();self.profile();self.request();self.assess();self.e.gm.snapshot('s')
  self.resolve();self.settings();self.e.gm.restore('s');self.assertTrue(self.e._pokemon_setting_policy['outside_water']['request'])
  self.assertEqual(self.a.spec['pokemon_requests']['r']['status'],'awaiting_gm');self.assertEqual(self.resolve()['status'],'completed')
 def test_json_restores_informed_water_policy_and_actual_native_permission(self):
  import state_codec as CODEC
  returned=self.settings(outside_water={k:True for k in U.ACTIVITY_KINDS})
  expected=deepcopy(returned)
  returned['outside_water']['skill']=False;returned['discussed_with'].append('detached result')
  self.assertEqual(self.e._pokemon_setting_policy,expected)
  self.body();body=deepcopy(self.p.spec['pokemon_body_environment']);movement=deepcopy(self.p.spec['movement'])
  identities=[c.entity_id for c in (self.a,self.p,self.q)]
  self.e=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  actors={c.entity_id:c for c in self.e.everyone};self.a,self.p,self.q=[actors[uid] for uid in identities]
  self.assertEqual(self.e._pokemon_setting_policy,expected)
  self.assertEqual(self.p.spec['pokemon_body_environment'],body)
  self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[2]*3).total,6)
  self.assertEqual(self.p.spec['movement'],movement)
  self.settings();before=self.state()
  with self.assertRaisesRegex(ValueError,'outside-water'):self.e.skill_roll(self.p,'육상',fixed=[2]*3)
  self.assertEqual(self.state(),before)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':getattr(t,'_testMethodName',t.id()),'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':getattr(t,'_testMethodName',t.id()),'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':getattr(t,'_testMethodName',t.id()),'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/pokemon_understanding.py','engine/regional_pokemon.py','engine/pokemon_requests.py','engine/pokemon_activities.py','engine/pokemon_intelligence.py','engine/custom_species.py','engine/builder.py','engine/engine.py','engine/gm_state.py','engine/movement_actions.py','engine/capability_actions.py','engine/ruleset.py','engine/skill_modifiers.py','engine/researcher_features.py','input/ch11-running-the-game.md','input/ch05-pokemon.md','input/ch06-gameplay.md','data/rulesets.json','output/ruleunits.jsonl','output/entities/pokemon.json','output/entities/learnsets.json','output/entities/species_skills.json','tools/test_category3_batch14_pokemon.py']
 files=sorted(set(files)|{p.relative_to(ROOT).as_posix() for p in (ROOT/'engine').glob('*.py')})
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':CLAUSES,'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-batch14-pokemon-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
