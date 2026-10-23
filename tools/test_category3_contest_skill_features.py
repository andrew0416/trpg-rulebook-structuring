"""Native contest skill exceptions: real source, owner, dice, actions and lifetimes."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from ruleset import RuleFilter,ExcludedRuleSelection
import contest_features as F
import common_checks as C
import action_points as AP
import turn as TURN
import downtime as DOWNTIME
class Sequence:
 def __init__(self,faces):self.faces=list(faces)
 def randint(self,a,b):return self.faces.pop(0)
SCOPES={'C3-EX-062':'abfeec4cf110803fc317316bd09ee589d22b90ff639475aad52afd6570d9aa19','C3-EX-063':'7073540c6ede1365295ee0af310fa0f024b1318f3188b1c47e49cef6d1044532','C3-EX-064':'3232db5971a44bc153591f38565ec1ec559ad4bdb64da5ee958dacb0536a41dd'}
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def fixture(self,stat='근사함',feature=F.STUNT):
  self.e=Engine(self.r,seed=222);ranked,skill,_=F.RANKED[stat]
  common={'level':25,'stats':dict(hp=10,atk=21,**{'def':10},spa=10,spd=10,spe=30)}
  self.t=Combatant(self.r,dict(common,id='trainer/t',name='T',kind='trainer',skills={skill:'초보','매력':'초보'},classes=['class/코디네이터',F.STYLE],edges=['edge/우아함'],feats=[ranked,feature],feat_ranks={ranked:1},feature_choices={F.STYLE:[stat]}))
  self.p=Combatant(self.r,dict(common,id='pokemon/p',name='P',kind='pokemon',trainer_id='trainer/t',skills={'육상':'초보','매력':'초보'},poffins=[stat]*3))
  self.w=Combatant(self.r,dict(common,id='pokemon/w',name='W',kind='pokemon',wild=True,disposition='중립'))
  self.e.everyone=[self.t,self.p,self.w];self.e.gm.everyone=self.e.everyone
  self.context={'source':'ordinary','dramatic_risk':True,'action':'불타는 건물에서 구조','risk':'붕괴하는 지붕을 넘어 더 위험한 지름길 선택'}
 def setUp(self):self.fixture()
 def stunt(self,**kw):
  options={'context':self.context,'fixed':[1]*5};options.update(kw)
  return self.e.contest_skill_feature(self.t,self.p,F.STUNT,'육상',12,**options)
 def mistakes(self,dc=12,**kw):
  options={'fixed':[1]*3,'reroll_faces':[2]*3,'decision':lambda first:True};options.update(kw)
  return self.e.contest_skill_feature(self.t,self.p,F.MISTAKES,'육상',dc,**options)
 def friends(self,**kw):
  options={'target':self.w,'friendship_performer':self.p,'friendship_audience':'performer','fixed':[2]*5};options.update(kw)
  return self.e.pokemon_activity(self.t,'befriend',**options)
 def snapshot(self):
  state=[deepcopy(self.t.spec),deepcopy(self.p.spec),deepcopy(self.w.spec),list(self.e.log_lines),[(k,{kk:vv for kk,vv in v.items() if kk not in ('beneficiary','payer')}) for k,v in self.e._ap_rolls.items()]]
  for actor in (self.t,self.p):state.append({x:deepcopy(getattr(actor,x,None)) for x in ('budget','_action_history','took_standard','_standard_action_round','_restricted_action_taken')})
  state.append(self.e.rng.getstate() if hasattr(self.e.rng,'getstate') else self.e.rng.faces[:]);return state
 def used(self,feature):return self.t.spec.get('frequency_state',{}).get('activations',{}).get(feature,{}).get('used',0)
 def test_source_full_scopes_and_trigger_exclusions(self):
  entries=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries']
  for uid,sha in SCOPES.items():
   row=next(r for r in entries if r['id']==uid);self.assertEqual(row['scope_sha256'],sha)
   for a in row['source_snapshot']['source_anchors']:
    excerpt='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start_line']-1:a['end_line']])
    self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['excerpt_sha256'])
 def test_stunt_actual_poffins_stat_cap_and_shared_modifiers(self):
  self.p.stages['atk']=6;self.e.boost_roll(self.t,self.p,roll_id='stunt1',kind='skill')
  out=self.stunt(mods=2,helper_rank=4,helper_bonus=4,penalty_count=1,fixed_penalties=[2],roll_id='stunt1')
  self.assertEqual(out['roll'].faces,(1,)*5);self.assertEqual(out['roll'].rank,3)
  self.assertEqual(out['roll'].total,12);self.assertTrue(out['check'].passed)
  self.assertEqual(self.e._ap_rolls['stunt1']['state'],'resolved');self.assertEqual(self.used(F.STUNT),1)
  self.p.stats['atk']=99;self.p.spec['poffins']=['근사함']*6
  out=self.stunt(fixed=[1]*8)
  self.assertEqual((len(out['roll'].faces),out['roll'].modifier,out['roll'].total),(8,3,11))
 def test_stunt_daily_two_counts_failure_and_refreshes_at_explicit_day(self):
  for _ in range(2):self.assertFalse(self.stunt()['check'].passed)
  before=self.snapshot()
  with self.assertRaises(ValueError):self.stunt()
  self.assertEqual(self.snapshot(),before)
  DOWNTIME.new_day(self.t);DOWNTIME.new_day(self.p);self.assertFalse(self.stunt()['check'].passed)
  self.assertEqual(self.used(F.STUNT),1)
 def test_stunt_rejects_nonordinary_and_nonrisk_contexts_before_state(self):
  contexts=[dict(self.context,source=s) for s in ('intercept','combat_maneuver','move','ability')]+[{},dict(self.context,dramatic_risk=False),dict(self.context,action=''),dict(self.context,risk='')]
  for context in contexts:
   with self.subTest(context=context):
    before=self.snapshot()
    with self.assertRaises(ValueError):self.stunt(context=context)
    self.assertEqual(self.snapshot(),before)
 def test_both_feature_paths_enforce_real_owner_acquisition_rank_and_branch(self):
  for stat,feature in [('근사함',F.STUNT),('슬기로움',F.MISTAKES)]:
   changes=[lambda:self.t.spec['feats'].remove(feature),lambda:self.t.spec['classes'].remove(F.STYLE),lambda:self.t.spec['feat_ranks'].clear(),lambda:self.t.spec['skills'].update({F.RANKED[stat][1]:'미숙'}),lambda:self.p.spec.update(poffins=[stat]*2),lambda:self.p.spec.update(trainer_id='other'),lambda:self.t.spec['feature_choices'].update({F.STYLE:['강인함']})]
   for i,change in enumerate(changes):
    with self.subTest(feature=feature,change=i):
     self.fixture(stat,feature);change();before=self.snapshot()
     with self.assertRaises(ValueError):(self.stunt if feature==F.STUNT else self.mistakes)()
     self.assertEqual(self.snapshot(),before)
 def test_feature_ruleset_exclusion_includes_transitive_acquisition(self):
  base=self.r
  for feature,stat in [(F.STUNT,'근사함'),(F.MISTAKES,'슬기로움')]:
   for uid in (feature,F.STYLE,F.RANKED[stat][0],'class/코디네이터','edge/우아함'):
    with self.subTest(feature=feature,source=uid):
     self.r=Rules(ROOT);self.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[uid]});self.r._apply_ruleset();self.fixture(stat,feature);before=self.snapshot()
     with self.assertRaises(ExcludedRuleSelection):(self.stunt if feature==F.STUNT else self.mistakes)()
     self.assertEqual(self.snapshot(),before)
  self.r=base
 def test_stunt_late_rng_or_action_failure_rolls_back_everything(self):
  for mode in ('bad_face','sleep'):
   with self.subTest(mode=mode):
    self.fixture();self.e.rng=Sequence([0,2,2,2,2])
    if mode=='sleep':self.t.conditions.add('잠듦')
    before=self.snapshot()
    with self.assertRaises(ValueError):self.stunt(fixed=None)
    self.assertEqual(self.snapshot(),before)
 def test_mistakes_only_real_failed_check_opens_choice_and_replaces_result(self):
  self.fixture('슬기로움',F.MISTAKES);seen=[]
  out=self.mistakes(decision=lambda first:seen.append(first) or True)
  self.assertEqual(seen,[C.CheckResult(3,12,-9,False)])
  self.assertEqual(out['roll'].faces,(2,2,2));self.assertEqual(out['roll'].total,11)
  self.assertFalse(out['check'].passed);self.assertEqual(out['poffin_bonus'],5);self.assertEqual(self.used(F.MISTAKES),1)
 def test_mistakes_success_never_offers_and_decline_never_spends(self):
  self.fixture('슬기로움',F.MISTAKES);seen=[]
  out=self.mistakes(fixed=[4]*3,decision=lambda first:seen.append(first) or True)
  self.assertTrue(out['check'].passed);self.assertFalse(seen);self.assertEqual(self.used(F.MISTAKES),0)
  out=self.mistakes(decision=lambda first:seen.append(first) or False)
  self.assertFalse(out['rerolled']);self.assertEqual(out['roll'].total,3);self.assertEqual(len(seen),1);self.assertEqual(self.used(F.MISTAKES),0)
 def test_mistakes_reuses_ap_helper_and_penalty_rules_once(self):
  self.fixture('슬기로움',F.MISTAKES);self.e.boost_roll(self.t,self.p,roll_id='retry1',kind='skill');available=AP.available(self.t)
  out=self.mistakes(dc=15,mods=2,helper_rank=4,helper_bonus=4,penalty_count=1,fixed_penalties=[3],reroll_penalties=[1],roll_id='retry1')
  self.assertEqual(out['first_roll'].total,7);self.assertEqual(out['roll'].total,17)
  self.assertTrue(out['check'].passed);self.assertEqual(AP.available(self.t),available)
  self.assertEqual(self.e._ap_rolls['retry1']['state'],'resolved')
  with self.assertRaises(ValueError):self.e.skill_roll(self.p,'육상',fixed=[1]*3,roll_id='retry1')
 def test_mistakes_daily_three_counts_failed_rerolls_and_day_refresh(self):
  self.fixture('슬기로움',F.MISTAKES)
  for _ in range(3):self.assertFalse(self.mistakes()['check'].passed)
  before=self.snapshot()
  with self.assertRaises(ValueError):self.mistakes()
  self.assertEqual(self.snapshot(),before)
  DOWNTIME.new_day(self.t);DOWNTIME.new_day(self.p);self.mistakes();self.assertEqual(self.used(F.MISTAKES),1)
 def test_mistakes_observed_error_keeps_initial_roll_and_ap_but_preflight_error_does_not_roll(self):
  import observed_resolution as OBS
  for mode in ('choice','sleep','reroll_face'):
   with self.subTest(mode=mode):
    self.fixture('슬기로움',F.MISTAKES);self.e.boost_roll(self.t,self.p,roll_id='retry1',kind='skill')
    self.e.rng=Sequence([1,1,1,0,2,2]);choice=(lambda check:'yes') if mode=='choice' else (lambda check:True)
    if mode=='sleep':self.t.conditions.add('잠듦')
    before=self.snapshot()
    with self.assertRaises(ValueError):self.mistakes(fixed=None,reroll_faces=None,decision=choice,roll_id='retry1')
    if mode=='sleep':self.assertEqual(self.snapshot(),before);continue
    self.assertEqual(self.e.rng.faces,[0,2,2]);self.assertEqual(self.e._ap_rolls['retry1']['state'],'resolved');self.assertEqual(self.used(F.MISTAKES),0)
    observed=self.e._ap_rolls['retry1'][OBS.KEY];self.assertEqual(observed['state'],'pending');self.assertEqual(observed['observation']['first'].total,4)
    out=self.mistakes(fixed=None,reroll_faces=None,decision=lambda check:False,roll_id='retry1')
    self.assertEqual(out['first_roll'].total,4);self.assertEqual(self.e.rng.faces,[0,2,2]);self.assertEqual(observed['state'],'complete')
 def test_triggered_free_action_outside_owner_turn_preserves_general_authority(self):
  self.fixture('슬기로움',F.MISTAKES);self.e.start_round([self.t,self.p]);self.e.start_of_turn(self.p)
  self.assertFalse(TURN.spend(self.e,self.t,'free','ordinary'))
  before=self.p.budget.copy();out=self.mistakes()
  self.assertTrue(out['rerolled']);self.assertEqual(self.p.budget,before);self.assertEqual(self.t._action_history,['free'])
  self.assertFalse(TURN.spend(self.e,self.t,'free','ordinary'))
 def test_friends_missing_audience_is_pending_without_cost(self):
  self.fixture('귀여움',F.FRIENDS);before=self.snapshot()
  self.assertIsInstance(self.friends(friendship_audience=None),C.PendingDecision);self.assertEqual(self.snapshot(),before)
 def test_friends_actual_performer_dice_disposition_and_scene_lifetime(self):
  self.fixture('귀여움',F.FRIENDS);out=self.friends()
  self.assertEqual(out['check'].total,13);self.assertTrue(out['check'].passed)
  self.assertEqual(self.w.spec['dispositions'],{'pokemon:pokemon/p':'우호적'})
  self.assertNotIn('trainer:trainer/t',self.w.spec['dispositions']);self.assertFalse(getattr(self.p,'_action_history',[]));self.assertEqual(self.t._action_history,['free'])
  with self.assertRaises(ValueError):self.friends()
  self.e.end_scene([self.t,self.p,self.w]);self.friends(fixed=[3]*5);self.assertEqual(self.used(F.FRIENDS),1)
 def test_friends_failed_performer_cannot_bypass_with_group(self):
  self.fixture('귀여움',F.FRIENDS);out=self.friends(fixed=[1]*5);self.assertFalse(out['check'].passed)
  self.e.end_scene([self.t,self.p,self.w])
  self.e.pokemon_activity(self.t,'disposition_ruling',target=self.w,disposition='중립',reason='GM explicit audience',group_id='party',group_members=[self.t.spec['id'],self.p.spec['id']])
  with self.assertRaises(ValueError):self.friends(friendship_audience='group',group_id='party')
  self.assertEqual(self.w.spec['befriend_failures'],['pokemon:pokemon/p'])
 def test_friends_group_requires_explicit_members_and_no_implicit_trainer_transfer(self):
  self.fixture('귀여움',F.FRIENDS)
  with self.assertRaises(ValueError):self.friends(friendship_audience='trainer')
  with self.assertRaises(ValueError):self.friends(friendship_audience='group',group_id='missing')
  self.e.pokemon_activity(self.t,'disposition_ruling',target=self.w,disposition='중립',reason='GM explicit party',group_id='party',group_members=[self.t.spec['id'],self.p.spec['id']])
  out=self.friends(friendship_audience='group',group_id='party')
  self.assertEqual(out['audience'],'group:party');self.assertEqual(self.w.spec['dispositions'],{'group:party':'우호적'})
 def test_friends_late_invalid_roll_restores_both_actions_and_rng(self):
  self.fixture('귀여움',F.FRIENDS);self.e.rng=Sequence([0,2,2,2,2]);self.p.budget={'standard':1,'shift':1,'swift':1}
  before=self.snapshot()
  with self.assertRaises(ValueError):self.friends(fixed=None)
  self.assertEqual(self.snapshot(),before)
 def test_friends_keeps_ordinary_trainer_action_authority(self):
  self.fixture('귀여움',F.FRIENDS);self.e.start_round([self.t,self.p]);self.e.start_of_turn(self.p);before=self.snapshot()
  with self.assertRaises(ValueError):self.friends()
  self.assertEqual(self.snapshot(),before)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=['engine/observed_resolution.py','engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/items.py','engine/common_action_checks.py','engine/gm_state.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','data/planter-policy.json','tools/test_category3_contest_skill_features.py','engine/contest_features.py','engine/engine.py','engine/pokemon_activities.py','engine/ruleset.py','engine/skill_modifiers.py','engine/common_checks.py','engine/resolution_transaction.py','engine/action_points.py','engine/ap_roll_bonus.py','engine/frequency.py','engine/downtime.py','engine/turn.py','engine/action_lifecycle.py','engine/action_metadata.py','engine/capability_actions.py','engine/physical_limits.py','engine/heavy_injury_adapter.py','data/capability-policy.json','data/skill-check-policy.json','data/lookup-tables.json','data/core-rules.json','data/contest-rules.json','data/conditions.json','data/rulesets.json','output/entities/moves.json','output/ruleunits.jsonl','input/ch03-skills-edges-feats.md','input/ch04-trainer-classes.md','input/ch05-pokemon.md','input/ch08-contests.md','output/source-audit/2026-10-10/ptu-core-1.05.pdf']
 paths += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 paths += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 paths += ['engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 paths += ['engine/blessing_skill_features.py','tools/test_category3_friendship_completion.py']

 paths += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 paths += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':list(SCOPES),'completion_scopes':['C3-EX-062','C3-EX-063','C3-EX-064'],'partial_scopes':[],'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},'source_review':{'lines':['ch04:1247-1257','ch04:1284-1287','ch04:1308-1312'],'ex063_remaining':[],'ex063_policy':'Trainer Free feature grants its named Pokemon attempt immediately; no unprinted Pokemon Standard cost. Explicit GM performer/group disposition and identity-scoped changed-circumstance retry use the native activity API.'}}
 (ROOT/'output/category3-contest-skill-features-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
