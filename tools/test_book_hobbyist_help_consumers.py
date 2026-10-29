"""Let Me Help reaches actual Trainer checks through existing action owners."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_book_hobbyist_full as H
import trainer_feature_acquisition as T,skill_feature_actions as SF,state_fields as F
import state_grants as G,world_entities as W,state_codec as CODEC,frequency as FREQ

class HelpConsumerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):H.HobbyistTests.setUpClass()
 def setUp(self):
  self.h=H.HobbyistTests();self.h.setUp();self.addCleanup(self.h.doCleanups)
  self.e=self.h.e;self.helper=self.h.a
  F.base_patch(self.helper,{'skills':dict.fromkeys(self.e.r.skill_policy['skills'],5)},reason='actual declared qualified helper skill sheet')
  T.acquire_static(self.e,self.helper,SF.HELP,acquisition_request_id='actual-general-helper')
  self.target=self.h.actor('help-consumer','trainer',(2,3),40,skills=dict.fromkeys(self.e.r.skill_policy['skills'],2))
  self.target.spec['movement']['power']=6;self.h.b.spec['movement']['power']=6
 def arm(self,*,faces=None,decision=None):
  self.e.offer_let_me_help(self.helper,self.target,request_id='consumer-help',payment='next',decision=decision or (lambda first:True),reroll_faces=[6,6] if faces is None else faces)
 def start(self):self.h.begin(self.target)
 def spent(self):
  self.assertEqual(FREQ.state(self.helper)['activations'][SF.HELP]['used'],1)
  self.assertEqual(self.helper._action_history.count('full'),1)
  self.assertNotIn(self.target.entity_id,getattr(self.e,'_let_me_help_offers',{}))
  self.h.valid()
 def skills(self,**values):
  skills=deepcopy(self.target.spec['skills']);skills.update(values)
  F.base_patch(self.target,{'skills':skills},reason='actual declared consumer skill sheet')

 def test_ordinary_action_without_explicit_id_uses_real_failed_check(self):
  self.start();self.arm();out=self.e.common_action(self.target,'의학',15,mode='skill',fixed=[1,1])
  self.assertTrue(out.check.passed);self.assertEqual(out.check.total,17);self.spent()

 def test_automatic_success_and_decline_close_observations_without_cost(self):
  self.start();self.arm(decision=lambda first:self.fail('successful check cannot activate helper'))
  history=('_action_history' in vars(self.helper),deepcopy(vars(self.helper).get('_action_history')))
  self.assertEqual(self.e.skill_check(self.target,'의학',2,fixed=[1,1]),(True,2))
  self.arm(decision=lambda first:False);self.assertEqual(self.e.skill_check(self.target,'의학',15,fixed=[1,1]),(False,2))
  rows=[row['skill_event'] for row in self.e._ap_rolls.values() if row.get('skill_event') is not None]
  self.assertEqual(len(rows),2);self.assertTrue(all(row.state=='final' for row in rows));self.assertEqual(('_action_history' in vars(self.helper),vars(self.helper).get('_action_history')),history);self.assertFalse(self.e._let_me_help_offers)

 def test_unqualified_ordinary_helper_keeps_actual_failure_and_spends_nothing(self):
  helper=self.h.actor('non-novice-helper','trainer',(1,3),30,skills={'의학':2})
  T.acquire_static(self.e,helper,SF.HELP,acquisition_request_id='unqualified-help-feature');self.start()
  history=('_action_history' in vars(helper),deepcopy(vars(helper).get('_action_history')))
  self.e.offer_let_me_help(helper,self.target,request_id='unqualified-offer',decision=lambda first:True,payment='next')
  with self.assertRaisesRegex(ValueError,'Novice'):self.e.skill_check(self.target,'의학',15,fixed=[1,1],roll_id='unqualified-check')
  self.assertEqual(SF.event(self.e,self.target,'unqualified-check').first.total,2);self.assertEqual(('_action_history' in vars(helper),vars(helper).get('_action_history')),history)

 def test_native_opposed_defender_tie_advantage_uses_rerolled_pool(self):
  self.start();self.arm()
  out=self.e.opposed_check(self.target,'육상',self.h.b,'육상',challenger_options={'fixed':[1,1]},defender_options={'fixed':[2]*6})
  self.assertTrue(out);self.spent()

 def test_native_context_opposed_uses_actual_failed_challenger(self):
  self.start();self.arm()
  out=self.e.common_action(self.target,mode='context',case='stealth_detection',context={'purpose':'pass the observed guard'},target=self.h.b,defender_role='status_quo',challenger_options={'fixed':[1,1]},defender_options={'fixed':[6,6]})
  self.assertTrue(out.check.passed);self.assertEqual(out.basis['challenger_roll'].total,17);self.spent()

 def test_weighted_team_rerolls_one_actual_contribution(self):
  other=self.h.actor('team-member','trainer',(3,3),35,skills={'의학':2});self.start();self.arm()
  out=self.e.common_action(mode='team',skill='의학',dc=12,participants=[self.target,other],required_people=2,equal_contribution=False,no_main_actor=True,contribution_weights=[2,1],weighting_reason='GM actual unequal contributions',participant_options=[{'fixed':[1,1]},{'fixed':[1,1]}])
  self.assertTrue(out.check.passed);self.assertEqual(out.check.total,36);self.spent()

 def test_weighted_team_actual_help_choice_failure_retains_first_observations_and_resumes_child(self):
  other=self.h.actor('durable-help-team-member','trainer',(3,3),35,skills={'의학':2})
  self.start();seen=[]
  self.arm(decision=lambda first:seen.append(first) or 'invalid Help reply')
  helper_before=deepcopy((getattr(self.helper,'budget',None),getattr(self.helper,'_action_history',[]),self.helper.spec))
  with self.assertRaisesRegex(ValueError,'observed Let Me Help choice'):
   self.e.common_action(mode='team',skill='의학',dc=12,participants=[self.target,other],
    required_people=2,equal_contribution=False,no_main_actor=True,contribution_weights=[2,1],
    weighting_reason='actual weighted participant contributions',
    participant_options=[{'fixed':[1,1],'roll_id':'durable-help-member'},
                         {'fixed':[1,1],'roll_id':'durable-other-member'}])
  self.assertEqual(len(seen),1)
  first=SF.event(self.e,self.target,'durable-help-member').first
  second=SF.event(self.e,other,'durable-other-member').first
  self.assertIs(seen[0],first);self.assertEqual((first.total,second.total),(2,2))
  self.assertEqual(deepcopy((getattr(self.helper,'budget',None),getattr(self.helper,'_action_history',[]),self.helper.spec)),helper_before)
  self.assertEqual(self.e._ap_rolls['durable-help-member']['help_check']['dc'],11)
  self.arm(decision=lambda first:True)
  # The already-issued Help check has its actual weighted threshold and roll ID.
  self.assertEqual(self.e.skill_check(self.target,'의학',11,fixed=[1,1],roll_id='durable-help-member'),(True,17))
  self.assertIs(SF.event(self.e,self.target,'durable-help-member').first,first)
  self.assertIs(SF.event(self.e,other,'durable-other-member').first,second)
  self.spent()

 def test_authored_roll_policy_delegates_actual_help_boundary_and_replays_without_second_cost(self):
  import hobbyist
  self.start();self.arm()
  purpose='actual authored Help-aware medical check'
  document={'schema':1,'id':'help-consumer/native-roll-policy','variants':[{
   'rule_id':SF.HELP,'source':{'file':'input/ch03-skills-edges-feats.md','sha256':hobbyist.GENERAL},
   'values':{'roll_plan':{'skill':'의학','purpose':purpose,'provider_id':self.helper.entity_id,
    'provider_requirement':{'source_id':SF.HELP,'minimum_count':1},'options':{'fixed':[1,1]}}},'inputs':{}}]}
  submissions=[{'actor':self.target,'target':self.target,'document':document,'purpose':purpose}]
  out=self.e.execute_source_policy_rolls(submissions,{'kind':'dc','dc':15},request_id='help-consumer/policy')
  self.assertEqual(out['status'],'PolicyRollsCompleted')
  self.assertEqual(out['outcome']['result']['total'],17)
  self.assertTrue(out['outcome']['result']['passed']);self.spent()
  before=self.e.export_state()
  again=self.e.execute_source_policy_rolls(submissions,{'kind':'dc','dc':15},request_id='help-consumer/policy')
  self.assertTrue(again['replayed']);self.assertEqual(self.e.export_state(),before)

 def test_additional_focus_keeps_distinct_automatic_observation_ids(self):
  self.start();self.arm()
  out=self.e.common_action(self.target,'의학',15,mode='focus_task',focus_dc=15,context={'kind':'stressful','purpose':'treat an ally','focus_reason':'distracting noise'},task_options={'fixed':[1,1]},focus_options={'fixed':[1,1]})
  self.assertTrue(out.basis['task_check'].passed);self.assertEqual(out.basis['task_roll'].total,17);self.assertFalse(out.basis['focus_check'].passed)
  rows=[row['skill_event'] for row in self.e._ap_rolls.values() if row.get('skill_event') is not None]
  self.assertEqual(len(rows),2);self.assertEqual({row.skill for row in rows},{'medical education','focus'});self.spent()

 def test_precision_focus_failure_changes_real_task_penalty(self):
  import precise_actions as P
  self.start();P.attacked(self.e,self.h.b,self.target,self.e.r.move('move/몸통박치기'));self.arm()
  out=self.e.common_action(self.target,'의학',2,mode='precise',context={'delicate':True,'activity':'ordinary_task','purpose':'fine repair'},task_options={'fixed':[1,1]},focus_options={'fixed':[1,1]})
  self.assertTrue(out.check.passed);self.assertEqual(out.basis['focus_roll'].total,17);self.assertEqual(out.basis['focus_penalty'],0);self.spent()

 def test_actual_pokemaniac_spends_standard_and_exposes_final_information(self):
  self.skills(**{'pokemon education':4});T.acquire_static(self.e,self.target,'feat/포켓몬매니아',acquisition_request_id='actual-pokemaniac')
  self.h.p.spec['nature']='대담'
  self.start();self.arm(faces=[6]*4)
  out=self.e.pokemon_activity(self.target,'pokemaniac',target=self.h.p,fixed=[1]*4)
  self.assertTrue(out['check'].passed);self.assertEqual(out['check'].total,29);self.assertEqual(self.target.budget['standard'],0);self.spent()

 def test_actual_boarding_transition_commits_help_cost_and_consumes_offer(self):
  self.skills(acrobatics=3)
  mount=self.h.actor('owned-help-mount','pokemon',(3,3),30,owner=self.target)
  F.base_patch(mount,{'movement':dict(mount.spec['movement'],power=6)},reason='observed owned mount capacity')
  value=json.loads((ROOT/'data/examples/control-mount.json').read_text(encoding='utf8'))[0]
  self.start();self.arm(faces=[6]*3)
  out=self.e.board_mount(self.target,mount,value,gm_mountable=True,roll_options={'fixed':[1]*3})
  self.assertTrue(out['passed']);self.assertEqual(out['check'].total,23);self.assertIs(W.mount_relation(W.actor_index(self.e),self.target),mount);self.spent()

 def test_actual_sensory_transition_reveals_only_after_helped_success(self):
  G.grant(self.target,'capabilities','Blindsense','fixture:sense','fixture')
  self.e.gm.observe_sensory_environment(self.target,self.h.p,paths={'spatial':True,'visual':True,'aura':True},medium='air',present=True,reason='actual observed sensory route')
  value=json.loads((ROOT/'data/examples/perception-observe.json').read_text(encoding='utf8'))[0]
  value['check']={'skill':'의학','dc':15,'purpose':'authored sensory identification'}
  self.start();self.arm();out=self.e.observe_target(self.target,self.h.p,value,roll_options={'fixed':[1,1]})
  self.assertTrue(out['check']['passed']);self.assertEqual(out['values'],{'presence':True});self.spent()

 def test_actual_staggering_load_failure_uses_helper_without_dropping_load(self):
  self.skills(athletics=1);F.base_patch(self.target,{'movement':{'land':6,'power':6}},reason='actual observed carrying capability')
  self.e.gm.set_carried_objects(self.target,[{'id':'helped-crate','weight_kg':60}],'actual weighed crate')
  self.start();self.arm(faces=[6]);out=self.e.carry_check(self.target,fixed=[1])
  self.assertTrue(out.passed);self.assertEqual(out.total,11);self.assertFalse(self.target.spec['_carried_load']['failure_pending']);self.spent()

 def test_actual_mushroom_appraisal_uses_final_check_and_physical_instance(self):
  import items
  self.skills(survival=4)
  W.register_object(self.e,'helped-mushroom',location={'kind':'unknown'},reason='actual identified mushroom',kind='item_instance',item_rule_id='item/큰버섯',owner_id=self.target.entity_id)
  items.equip_held(self.e,self.target,'큰버섯',source_instance_id='helped-mushroom')
  self.start();self.arm(faces=[6]*4);out=self.e.appraise_mushroom(self.target,instance_id='helped-mushroom',fixed=[1]*4)
  self.assertTrue(out['check'].passed);self.assertEqual(out['check'].total,29);self.assertEqual(len(out['stats']),2);self.spent()

 def test_actual_jump_boost_reaches_destination_and_preserves_shift_cost(self):
  F.base_patch(self.target,{'movement':{'land':6,'power':6,'high_jump':2,'long_jump':3}},reason='actual observed jump capabilities')
  self.start();self.arm()
  out=self.e.jump(self.target,(6,3),jump_id='helped-jump',boost='long_jump',boost_options={'fixed':[1,1]},difficult=False,clear_path=True,reason_text='GM observed clear four-metre jump')
  self.assertTrue(out['landed']);self.assertEqual(self.target.pos,(6,3));self.assertEqual(self.target.budget['shift'],0);self.spent()

 def test_scoped_roll_context_reports_final_pool_and_replays_without_second_cost(self):
  self.start();self.arm();options={'fixed':[1,1]}
  plan=self.e.plan_skill_check(self.target,'의학',purpose='actual scoped check',**options)
  request={'actor':self.target,'target':None,'provider':None,'skill':'의학','purpose':'actual scoped check','replacement':None,'options':options,'expected_plan':plan}
  out=self.e.resolve_roll_context([request],{'kind':'dc','dc':15},request_id='helped-context')
  self.assertTrue(out['result']['passed']);self.assertEqual(out['result']['total'],17);self.assertEqual(out['rolls'][0]['total'],17)
  self.assertTrue(self.e.resolve_roll_context([request],{'kind':'dc','dc':15},request_id='helped-context')['replayed']);self.spent()

 def test_saved_offer_requires_rebinding_and_completed_help_survives_cold_restore(self):
  self.start();self.arm();uid=self.target.entity_id;hid=self.helper.entity_id
  self.e=CODEC.load_engine(self.e.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)));self.h.e=self.e
  self.target=W.actor_index(self.e)[uid];self.helper=W.actor_index(self.e)[hid]
  self.assertNotIn('decision',self.e._let_me_help_offers[uid]);self.arm()
  self.assertEqual(self.e.skill_check(self.target,'의학',15,fixed=[1,1]),(True,17));self.spent()
  restored=CODEC.load_engine(self.e.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.assertEqual(FREQ.state(W.actor_index(restored)[hid])['activations'][SF.HELP]['used'],1)
  self.assertFalse(restored._let_me_help_offers)

 def test_late_helper_failure_keeps_first_roll_and_rolls_back_interrupt_cost(self):
  from unittest.mock import patch
  self.start();self.arm();original=FREQ.consume_activation
  history=('_action_history' in vars(self.helper),deepcopy(vars(self.helper).get('_action_history')))
  def fail(actor,source,*args,**kwargs):
   if source==SF.HELP:raise ValueError('late actual helper frequency failure')
   return original(actor,source,*args,**kwargs)
  with patch.object(FREQ,'consume_activation',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late actual helper'):self.e.skill_check(self.target,'의학',15,fixed=[1,1],roll_id='durable-first')
  first=SF.event(self.e,self.target,'durable-first').first
  self.assertEqual(first.total,2);self.assertEqual(('_action_history' in vars(self.helper),vars(self.helper).get('_action_history')),history)
  self.assertEqual(self.e.skill_check(self.target,'의학',15,fixed=[1,1],roll_id='durable-first'),(True,17));self.assertIs(SF.event(self.e,self.target,'durable-first').first,first);self.spent()

 def test_generic_activity_terminal_check_uses_same_actual_helper_owner(self):
  self.e.start_activity_job(self.target,job_id='helped-job',source='gameplay/skill-check',definition={'target':15,'attempt_limit':1,'interval_seconds':1,'continuity':'resumable','resume':'retain'})
  self.arm();out=self.e.attempt_activity_job('helped-job',self.target,'의학',interval_id='first',options={'fixed':[1,1]})
  self.assertEqual(out['status'],'complete');self.assertEqual(out['total'],17);self.spent()

 def test_limited_extended_failure_updates_both_history_and_native_job(self):
  self.arm()
  out=self.e.common_action(self.target,'의학',8,mode='extended',task_id='helped-extended',interval_id='first',interval={'amount':1,'unit':'second'},interval_completed=True,complexity=2,limited=True,fixed=[1,1])
  self.assertEqual((out.result.status,out.result.total),('complete',17))
  self.assertEqual(self.e.activity_job_status('extended-check:helped-extended')['total'],17);self.assertEqual(self.e.elapsed_seconds,1);self.spent()

 def test_actual_falling_check_uses_helper_before_distance_reduction(self):
  F.base_patch(self.target,{'movement':{'land':6,'high_jump':2,'long_jump':3}},reason='actual observed falling capability')
  self.target.spec['weight_class']=3
  self.start();self.arm()
  out=self.e.falling_damage(self.target,action_id='helped-fall',meters=3,intentional=True,reason='actual intentional short fall',acrobatics=True,acrobatics_options={'fixed':[1,1]},natural_sky=False,natural_sky_reason='actual Trainer has no natural Sky',acrobatics_injury_policy='distance')
  self.assertTrue(out['checks']['falling_acrobatics'].passed);self.assertEqual(out['checks']['falling_acrobatics'].total,17);self.assertEqual(out['damage_distance'],0);self.spent()

 def test_native_maneuver_uses_helped_defender_without_changing_attacker_budget(self):
  self.e.gm.set_position(self.h.b,(2,2),reason='actual adjacent opposed attacker');self.h.begin(self.h.b);self.arm()
  out=self.e.push(self.h.b,self.target,challenger_skill='육상',defender_skill='육상',fixed_accuracy=20,challenger_options={'fixed':[2]*6},defender_options={'fixed':[1,1]})
  self.assertFalse(out);self.assertEqual(self.target.pos,(2,3));self.assertEqual(self.h.b.budget['standard'],0);self.spent()

 def test_actual_three_participant_grapple_uses_its_highest_winner_owner(self):
  import grapple_state as GR
  self.e.gm.set_position(self.h.b,(3,3),reason='actual grapple participant')
  third=self.h.actor('third-grappler','trainer',(3,4),35,side='foe',skills={'육상':2})
  members=[self.target,self.h.b,third]
  GR.observe(self.e,members,dominant=self.h.b,source='gm/observation',reason='actual three-participant grapple')
  self.start();self.arm()
  checks={c.entity_id:{'skill':'육상','options':{'roll_id':'contest-'+str(i),'fixed':faces}} for i,(c,faces) in enumerate(zip(members,([1,1],[2]*6,[3,3])))}
  out=self.e.grapple_action(self.target,'contest',participant_checks=checks,winner_choices={c.entity_id:'end' if c is self.target else 'keep' for c in members},request_id='helped-multipart')
  self.assertEqual(out['winner_id'],self.target.entity_id);self.assertEqual(out['check_totals'][self.target.entity_id],17)
  self.assertTrue(all(GR.relation(self.e,c)is None for c in members));self.assertEqual(self.target.budget['standard'],0);self.assertEqual(self.target.budget['shift'],0);self.spent()

 def test_vehicle_weapon_check_commits_actual_damage_only_after_helped_success(self):
  import test_foundation_control_vehicle as V
  V.VehicleTests.setUpClass();f=V.VehicleTests();f.setUp();self.addCleanup(f.doCleanups)
  helper=f.trainer(f.poly,'vehicle-helper');helper.spec['skills']['집중']=3
  f.e.gm.add_combatant(helper,pos=(2,4),side=f.a.side,reason='actual allied vehicle helper')
  T.acquire_static(f.e,helper,SF.HELP,acquisition_request_id='vehicle-help-feature')
  f.e.offer_let_me_help(helper,f.a,request_id='weapon-help',payment='next',decision=lambda first:first.total==4,reroll_faces=[6]*4)
  before=f.t.hp;out=f.fire(fixed=[1]*4)
  self.assertTrue(out['passed']);self.assertEqual(out['check']['total'],27);self.assertLess(f.t.hp,before)
  self.assertEqual(FREQ.state(helper)['activations'][SF.HELP]['used'],1);self.assertFalse(f.e._let_me_help_offers)

 def test_repair_formula_uses_helped_total_for_actual_restored_hp(self):
  import test_foundation_repair_restore as R
  R.RepairTests.setUpClass();f=R.RepairTests();f.setUp();self.addCleanup(f.doCleanups)
  helper=f.trainer(f.poly,'repair-helper');helper.spec['skills']['기술학']=3
  f.e.gm.add_combatant(helper,side=f.a.side,reason='actual allied repair helper')
  T.acquire_static(f.e,helper,SF.HELP,acquisition_request_id='repair-help-feature')
  vehicle=f.vehicle_ready();f.e.begin_encounter(f.e.everyone);f.e.start_round(f.e.everyone);f.e.start_of_turn(f.a)
  f.e.offer_let_me_help(helper,f.a,request_id='repair-help',payment='next',decision=lambda first:first.total==4,reroll_faces=[6]*4)
  out=f.restore(f.policy(2),target='vehicle',roll_options={'fixed':[1]*4})
  self.assertTrue(out['passed']);self.assertEqual(out['check']['total'],27);self.assertEqual(vehicle['hp'],57)
  self.assertEqual(FREQ.state(helper)['activations'][SF.HELP]['used'],1);self.assertFalse(f.e._let_me_help_offers)

 def test_drown_out_failure_rerolls_actual_focus_and_cancels_native_sonic_move(self):
  from unittest.mock import patch
  from engine import Engine
  import test_book_musician_full as M
  M.MusicianTests.setUpClass();f=M.MusicianTests();f.setUp();self.addCleanup(f.doCleanups)
  f.t.spec['skills']['집중']=3;f.musician(ability='소리묻히기');foe=f.foe()
  helper=f.add('Actual Helper','trainer',(2,3),classes=[],feats=[],edges=[],moves=[],items={})
  T.acquire_static(f.e,helper,SF.HELP,acquisition_request_id='drown-help-feature')
  f.combat(foe,count=15);before=f.t.hp
  f.e.offer_let_me_help(helper,f.t,request_id='drown-help',payment='next',decision=lambda first:first.total==3,reroll_faces=[6]*3)
  def first(actor,skill,mods=0,helper_rank=0,fixed=None,**options):return Engine.skill_roll(f.e,actor,skill,mods,helper_rank,[1]*3,**options)
  with patch.object(f.e,'decide',return_value=True),patch.object(f.e,'skill_roll',side_effect=first):f.use(foe,f.t,'move/하이퍼보이스',face=20,aim=(3,3))
  self.assertEqual(f.t.hp,before);self.assertEqual(FREQ.state(helper)['activations'][SF.HELP]['used'],1);self.assertFalse(f.e._let_me_help_offers)
