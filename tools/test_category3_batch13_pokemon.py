"""Native full-scope candidates 050 / EX021 / CORE061; TM/HM remains partial."""
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
from contest import ContestRules,ContestEngine
import pokemon_party as PARTY
import pokemon_teaching as T
import pokemon_intelligence as I
import researcher_features as RF
import downtime as DT

CLAUSES=['DOMAIN-050','C3-EX-021','C3-CORE-061']
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=Rules(str(ROOT),ruleset='core');cls.cr=ContestRules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,371)
  self.a=Combatant(self.r,build_trainer(self.r,'Trainer',20,dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),skills={'포켓몬학':4,'일반 지식':5,'명령':4,'매력':4,'생존':4},items={'미용사 킷':1,'몬스터볼':20},extra={'edges':['edge/미용사','edge/고생물학자']}))
  self.p=self.pokemon('p');self.q=self.pokemon('q')
  self.e.gm.everyone=[self.a,self.p,self.q];self.e.everyone=self.e.gm.everyone
 def pokemon(self,name,species='브케인',level=5):
  return Combatant(self.r,build_pokemon(self.r,species,level,name=name,extra={'trainer_id':self.a.spec['id'],'tutor_points':3}))
 def act(self,activity,**kw):return self.e.pokemon_activity(self.a,activity,**kw)
 def state(self):return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),self.a.spec,self.p.spec,self.q.spec,self.p.on_field,self.q.on_field,self.p.moves,self.q.moves))
 def policy(self,**kw):
  args=dict(mode='standard',reason='GM campaign law agreed at session zero',roster=[self.p,self.q],storage={'kind':'center','id':'PC1'});args.update(kw)
  return self.act('party_policy',**args)
 def intelligence(self,**kw):
  args=dict(portrayal='Pokemon have individual personalities; wildlife remains dangerous',discussed_with=['Alice','Bob'],social=True,education=True,reason='session zero discussion');args.update(kw)
  return self.act('configure_intelligence',**args)
 def machine(self,code,instance='m'):
  self.a.spec['items'][code]=self.a.spec['items'].get(code,0)+1
  return self.act('register_machine',code=code,instance_id=instance)
 def test_frozen_source_scopes(self):
  register=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf8'))
  for entry in register['entries']:
   if entry['id'] not in CLAUSES+['DOMAIN-082']:continue
   source=entry['source_snapshot'];anchors=source.get('source_anchors',source.get('anchors',[source.get('source')]))
   for a in anchors:
    text='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a.get('start_line',a.get('start'))-1:a.get('end_line',a.get('end'))])
    self.assertEqual(text,a['excerpt'],entry['id'])
 def test_six_is_selected_campaign_limit_and_overflow_retains_owner(self):
  more=[self.pokemon(str(n)) for n in range(5)];roster=[self.p,self.q,*more];self.e.gm.everyone=[self.a,*roster]
  registry=self.policy(roster=roster)
  self.assertEqual(sum(v['location']=='carried' for v in registry.values()),6)
  last=roster[-1];self.assertEqual(registry[last.spec['id']]['location'],'storage');self.assertFalse(last.on_field)
  self.assertEqual(last.spec['trainer_id'],self.a.spec['id']);self.assertEqual(registry[last.spec['id']]['destination']['id'],'PC1')
 def test_campaign_unlimited_and_sale_exception_are_explicit(self):
  roster=[self.p,self.q,*[self.pokemon(str(n)) for n in range(5)]];self.e.gm.everyone=[self.a,*roster]
  registry=self.policy(roster=roster,exceptions={roster[-1].spec['id']:{'kind':'sale','reason':'licensed sale transport'}})
  self.assertTrue(all(r['location']=='carried' for r in registry.values()))
  self.policy(roster=roster,mode='unlimited',storage=None);self.assertIsNone(self.a.spec['pokemon_party_policy']['limit'])
 def test_eggs_remain_records_without_invented_stats_or_party_slots(self):
  self.a.spec['eggs']=[{'id':'egg/1','hatched':False}];self.policy(mode='custom',limit=2)
  view=self.act('party_registry');self.assertEqual(len(view['pokemon']),2);self.assertEqual(view['eggs'],self.a.spec['eggs']);self.assertNotIn('stats',view['eggs'][0])
 def test_owned_reserve_and_sale_transport_need_no_battle_statistics(self):
  self.policy()
  for uid,where in [('reserve/1','storage'),('sale/1','sale_transport')]:
   row=self.act('register_owned_reserve',pokemon_id=uid,species='브케인',location=where,reason='GM confirms existing ID ownership and purpose')
   self.assertEqual(row['owner_id'],self.a.spec['id']);self.assertNotIn('stats',row)
  self.policy();self.assertIn('reserve/1',self.act('party_registry')['pokemon'])
  forged=self.pokemon('new');forged.spec['id']='sale/1';before=self.state()
  with self.assertRaises(ValueError):PARTY.require_participation(self.e,forged)
  self.assertEqual(before,self.state())
 def test_roster_omission_and_wrong_owner_fail_without_state_change(self):
  before=self.state()
  with self.assertRaises(ValueError):self.policy(roster=[self.p])
  self.assertEqual(before,self.state());self.q.spec['trainer_id']='other';before=self.state()
  with self.assertRaises(ValueError):self.policy()
  self.assertEqual(before,self.state())
 def test_deposit_withdrawal_and_explicit_swap_do_not_grant_field_entry(self):
  self.policy(mode='custom',limit=1)
  self.assertFalse(self.q.on_field);before=self.state()
  with self.assertRaises(ValueError):self.act('party_place',target=self.q,location='carried')
  self.assertEqual(before,self.state())
  self.act('party_place',target=self.q,location='carried',swap=self.p)
  self.assertFalse(self.p.on_field);self.assertFalse(self.q.on_field)
  self.assertEqual(self.q.spec['party_location']['location'],'carried')
 def test_storage_actor_and_target_are_rejected_by_native_move_entry(self):
  self.policy(mode='custom',limit=1)
  before=self.state()
  with self.assertRaises(ValueError):self.e.use_move(self.q,self.p,'struggle')
  with self.assertRaises(ValueError):self.e.use_move(self.p,self.q,'struggle')
  self.assertEqual(before,self.state())
 def test_actual_successful_capture_overflow_is_registered_and_stored(self):
  self.policy(mode='custom',limit=2)
  wild=self.pokemon('wild');wild.spec.pop('trainer_id');wild.spec.update(wild=True,side='wild');wild.side='wild';self.e.gm.everyone.append(wild)
  self.assertTrue(self.e.throw_ball(self.a,wild,fixed_accuracy=20,fixed_capture=20))
  self.assertEqual(wild.spec['trainer_id'],self.a.spec['id']);self.assertEqual(wild.spec['party_location']['location'],'storage');self.assertFalse(wild.on_field)
  self.assertEqual(self.a.spec['pokemon_registry'][wild.spec['id']]['location'],'storage')
 def test_successful_capture_without_policy_keeps_ownership_and_pending_placement(self):
  self.p.spec.pop('trainer_id');self.p.spec.update(wild=True,side='wild');self.p.side='wild'
  self.assertTrue(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=20))
  self.assertTrue(self.p.captured);self.assertEqual(self.p.spec['trainer_id'],self.a.spec['id']);self.assertEqual(self.p.spec['party_location']['location'],'pending')
  with self.assertRaises(ValueError):PARTY.require_participation(self.e,self.p)
 def test_party_source_change_and_registry_mismatch_are_rejected(self):
  self.policy();old=dict(self.r.selection.aliases);self.r.selection.aliases[PARTY.SOURCE]='edge/미용사'
  try:
   before=self.state()
   with self.assertRaises(ValueError):self.act('party_place',target=self.p,location='storage')
   with self.assertRaises(ValueError):PARTY.require_participation(self.e,self.p)
   self.assertEqual(before,self.state())
  finally:self.r.selection.aliases=old
  self.a.spec['pokemon_registry'][self.p.spec['id']]['location']='storage'
  with self.assertRaises(ValueError):PARTY.require_participation(self.e,self.p)
 def test_grooming_hour_teaches_real_edge_without_a_second_hour(self):
  self.act('groom',targets=[self.p],safe=True);self.assertEqual(self.e.elapsed_seconds,3600)
  self.p.spec['skills']['육상']='2d6+2'
  out=self.act('teach_edge',target=self.p,edge=T.EDGE,skill='육상',from_grooming=True,safe=True)
  self.assertEqual(out['seconds'],0);self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(self.p.spec['tutor_points'],2)
  roll=self.e.skill_roll(self.p,'육상',fixed=[2,2,2]);self.assertEqual((roll.rank,roll.total),(3,8))
 def test_poke_edge_without_grooming_uses_actual_training_hour(self):
  self.act('teach_edge',target=self.p,edge=T.EDGE,skill='육상',safe=True);self.assertEqual(self.e.elapsed_seconds,3600)
 def test_edge_learning_rejects_missing_time_points_duplicate_or_wrong_species_rank(self):
  before=self.state()
  with self.assertRaises(ValueError):self.act('teach_edge',target=self.p,edge=T.EDGE,skill='육상',from_grooming=True,safe=True)
  self.assertEqual(before,self.state());self.act('groom',targets=[self.p],safe=True);self.p.spec['tutor_points']=0;before=self.state()
  with self.assertRaises(ValueError):self.act('teach_edge',target=self.p,edge=T.EDGE,skill='육상',from_grooming=True,safe=True)
  self.assertEqual(before,self.state());self.p.spec['tutor_points']=3
  self.act('teach_edge',target=self.p,edge=T.EDGE,skill='육상',from_grooming=True,safe=True);before=self.state()
  with self.assertRaises(ValueError):self.act('teach_edge',target=self.p,edge=T.EDGE,skill='육상',from_grooming=True,safe=True)
  self.assertEqual(before,self.state())
 def test_grooming_credit_stale_or_foreign_cannot_teach(self):
  self.act('groom',targets=[self.p],safe=True);self.p.spec['training_credit']['trainer_id']='other';before=self.state()
  with self.assertRaises(ValueError):self.act('teach_edge',target=self.p,edge=T.EDGE,skill='육상',from_grooming=True,safe=True)
  self.assertEqual(before,self.state())
 def test_grooming_experience_and_pokeedge_share_the_completed_hour(self):
  self.act('groom',targets=[self.p],safe=True);self.act('teach_edge',target=self.p,edge=T.EDGE,skill='육상',from_grooming=True,safe=True)
  out=self.act('experience_training',targets=[self.p],from_grooming=True,bonus_skill='일반 지식',safe=True)
  self.assertEqual(out['awards'],[12]);self.assertEqual(out['xp_rank'],5);self.assertEqual(self.e.elapsed_seconds,3600)
  with self.assertRaises(ValueError):self.act('experience_training',targets=[self.p],from_grooming=True,bonus_skill='일반 지식',safe=True)
 def test_grooming_activates_acquired_training_feature_on_real_skill(self):
  self.a.spec.update(classes=[RF.RESEARCHER],feats=[RF.PUSHER,RF.SKILL_TRAINER],feature_choices={RF.RESEARCHER:[['pokemon_caretaking','general']]})
  self.act('groom',targets=[self.p],pushed_skills={self.p.spec['id']:'육상'},safe=True)
  result=self.e.skill_roll(self.p,'육상',fixed=[2]*3)
  self.assertEqual(result.rank,2);self.assertEqual(len(result.faces),3);self.assertEqual(self.p.spec['pushed_skill']['training_source'],'edge/미용사')
 def test_grooming_contest_bonus_is_one_actual_die_and_expires_next_day(self):
  self.act('groom',targets=[self.p],safe=True);self.act('groom',targets=[self.p],safe=True);ce=ContestEngine(self.cr,4)
  pool={s:1 for s in self.cr.mech('contest/type-match')['ring']}
  c=ce.contestant_from_combatants(self.e,self.p,self.a,'매력',pool,bonus_stats={'edge/미용사':'귀여움'})
  expected=deepcopy(ce.rng);faces=[expected.randint(1,6) for _ in range(5)]
  ce.intro_stage([c],'귀여움')
  self.assertEqual(ce.rng.getstate(),expected.getstate())
  self.assertEqual(c.stat_dice['귀여움'],1+sum(x>=3 for x in faces))
  DT.new_day(self.p)
  with self.assertRaises(ValueError):ce.contestant_from_combatants(self.e,self.p,self.a,'매력',pool,bonus_stats={'edge/미용사':'귀여움'})
 def test_groomer_kit_prerequisite_six_limit_and_ownership_preflight(self):
  for mutation in ('kit','edge','rank','owner','seven'):
   self.setUp()
   if mutation=='kit':self.a.spec['items'].clear()
   if mutation=='edge':self.a.spec['edges'].clear()
   if mutation=='rank':self.a.spec['skills']['포켓몬학']=2
   if mutation=='owner':self.p.spec['trainer_id']='other'
   targets=[self.p] if mutation!='seven' else [self.p]*7;before=self.state()
   with self.assertRaises(ValueError):self.act('groom',targets=targets,safe=True)
   self.assertEqual(before,self.state())
 def test_fossil_identification_equal_dc_and_both_skills(self):
  for skill in ('포켓몬학','생존'):
   self.a.spec['fossils']={'f':{'species':'pokemon/암나이트','status':'fossil'}}
   fail=self.act('fossil',phase='identify',fossil_id='f',skill=skill,fixed=[1,2,3,3]);self.assertFalse(fail['check'].passed);self.assertIsNone(fail['species'])
   result=self.act('fossil',phase='identify',fossil_id='f',skill=skill,fixed=[1,3,3,3]);self.assertTrue(result['check'].passed);self.assertEqual(result['check'].dc,10)
 def test_fossil_restoration_uses_actual_machine_and_consumes_once(self):
  self.a.spec['fossils']={'f':{'species':'pokemon/암나이트','status':'fossil'}};before=self.state()
  with self.assertRaises(ValueError):self.act('fossil',phase='restore',fossil_id='f')
  self.assertEqual(before,self.state());self.a.spec['accessible_equipment']=['복원기']
  out=self.act('fossil',phase='restore',fossil_id='f');self.assertFalse(out['egg']['hatched']);self.assertEqual(out['egg']['hatch_level'],10)
  with self.assertRaises(ValueError):self.act('fossil',phase='restore',fossil_id='f')
 def test_intelligence_discussion_and_boolean_choices_required_before_mutation(self):
  for kwargs in ({'discussed_with':[]},{'social':'false'},{'education':1},{'portrayal':''}):
   with self.assertRaises(ValueError):self.intelligence(**kwargs)
   self.assertFalse(hasattr(self.e,'_pokemon_intelligence_policy'))
 def test_feral_policy_blocks_social_and_education_but_preserves_physical(self):
  self.intelligence(social=False,education=False);before=self.state()
  for skill in ('매력','일반 지식'):
   with self.assertRaises(ValueError):self.e.skill_roll(self.p,skill)
  self.assertEqual(before,self.state());self.assertEqual(self.e.skill_roll(self.p,'육상',fixed=[2,2]).total,6)  # Cyndaquil source2d6+2
 def test_policy_never_defaults_unassigned_pokemon_rank_with_or_without_configuration(self):
  self.p.spec['skills'].pop('매력',None)
  for configured in (False,True):
   if configured:self.intelligence()
   before=self.state()
   with self.assertRaisesRegex(ValueError,'no default 2d6'):self.e.skill_roll(self.p,'매력')
   self.assertEqual(before,self.state())
 def test_helper_admission_cannot_use_forbidden_skill_and_rank_mode_stays_pending(self):
  import common_checks as C
  self.intelligence(social=False,education=False);self.p.spec['skills']['매력']=4;before=self.state()
  with self.assertRaises(ValueError):self.e.common_action(self.a,'매력',10,mode='skill',helper=self.p,helper_skill='매력',fixed=[2]*4)
  self.assertEqual(before,self.state())
  out=self.e.common_action(self.p,'매력',mode='rank');self.assertIsInstance(out,C.PendingDecision);self.assertEqual(before,self.state())
 def test_party_professor_destination_and_snapshot_restore_location(self):
  self.policy(mode='custom',limit=1,storage={'kind':'professor','id':'Oak'})
  self.assertEqual(self.q.spec['party_location']['destination']['kind'],'professor')
  self.e.gm.snapshot('party');self.act('party_place',target=self.q,location='carried',swap=self.p)
  self.e.gm.restore('party');self.assertEqual(self.q.spec['party_location']['location'],'storage');self.assertFalse(self.q.on_field)
  PARTY.require_participation(self.e,self.p)
 def test_native_species_technology_exception_and_explicit_individual_exception(self):
  porygon=self.pokemon('porygon','폴리곤');self.e.gm.everyone.append(porygon)
  self.intelligence(social=False,education=False,exceptions={self.p.spec['id']:{'skills':['매력'],'reason':'individual sapient Pokemon agreed by group'}})
  self.assertEqual(self.e.skill_roll(porygon,'기술학',fixed=[2]*3).total,6)
  self.assertEqual(self.e.skill_roll(self.p,'매력',fixed=[2]*2).total,4)
  with self.assertRaises(ValueError):self.e.skill_roll(self.q,'매력')
 def test_gm_concrete_assignment_is_used_by_actual_skill_roll(self):
  self.intelligence();self.act('assign_intelligence_skills',target=self.p,skills={'일반 지식':'4d6+2'},reason='chosen Pokemon scholar template')
  roll=self.e.skill_roll(self.p,'일반 지식',fixed=[2]*4);self.assertEqual((roll.rank,roll.total),(4,10))
  before=self.state()
  with self.assertRaises(ValueError):self.act('assign_intelligence_skills',target=self.p,skills={'매력':'success'},reason='GM says')
  self.assertEqual(before,self.state())
 def test_intelligence_policy_does_not_grant_speech_obedience_capture_or_trainer_restrictions(self):
  before=deepcopy(self.p.spec);self.intelligence(social=False,education=False);self.assertEqual(before,self.p.spec)
  self.assertEqual(self.e.skill_roll(self.a,'매력',fixed=[2]*4).total,8)
 def test_intelligence_source_change_rejected_and_snapshot_restores_policy(self):
  self.intelligence();self.e.gm.snapshot('before');self.intelligence(social=False,education=False);self.e.gm.restore('before')
  self.assertTrue(self.e._pokemon_intelligence_policy['social']);old=dict(self.r.selection.aliases);self.r.selection.aliases[I.SOURCE]='edge/미용사'
  try:
   before=self.state()
   with self.assertRaises(ValueError):self.e.skill_roll(self.p,'매력')
   self.assertEqual(before,self.state())
  finally:self.r.selection.aliases=old
 def test_tm_actual_inventory_hour_tp_and_native_moveset(self):
  self.machine('TM35');out=self.act('teach_machine',target=self.p,instance_id='m')
  self.assertEqual(out['point_cost'],1);self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(self.p.spec['tutor_points'],2);self.assertEqual(self.a.spec['items']['TM35'],0)
  self.assertIn('move/화염방사',self.p.moves);self.assertEqual(self.p.moves,self.p.spec['moves'])
  before=self.state()
  with self.assertRaises(ValueError):self.act('teach_machine',target=self.p,instance_id='m')
  self.assertEqual(before,self.state())
 def test_tm_replacing_tm_move_costs_no_additional_point(self):
  self.machine('TM35');self.act('teach_machine',target=self.p,instance_id='m');self.machine('TM38','m2');self.p.spec['tutor_points']=0
  out=self.act('teach_machine',target=self.p,instance_id='m2',replace='화염방사')
  self.assertEqual(out['point_cost'],0);self.assertNotIn('move/화염방사',self.p.moves);self.assertIn('move/불대문자',self.p.moves)
 def test_tm_replacing_general_tutor_move_requires_actual_point_before_cost(self):
  self.p.moves.insert(0,'move/열풍');self.p.spec['moves']=list(self.p.moves)
  self.p.spec['move_learning']={'move/열풍':{'method':'tutor','source':'feat/가르침-기술'}}
  self.p.spec['tutor_points']=0;self.machine('TM35');before=self.state()
  with self.assertRaisesRegex(ValueError,'insufficient actual Tutor Points'):self.act('teach_machine',target=self.p,instance_id='m',replace='열풍')
  self.assertEqual(before,self.state());self.assertEqual(self.a.spec['teaching_machines']['m']['status'],'owned')
  self.p.spec['tutor_points']=1;out=self.act('teach_machine',target=self.p,instance_id='m',replace='열풍')
  self.assertEqual(out['point_cost'],1);self.assertEqual(self.p.spec['tutor_points'],0);self.assertEqual(self.e.elapsed_seconds,3600)
  self.assertEqual(self.a.spec['items']['TM35'],0);self.assertNotIn('move/열풍',self.p.moves);self.assertIn('move/화염방사',self.p.moves)
 def test_missing_inventory_or_tp_and_species_incompatibility_have_no_cost(self):
  with self.assertRaises(ValueError):self.act('register_machine',instance_id='m',code='TM35')
  self.machine('TM35');self.p.spec.pop('tutor_points');before=self.state()
  with self.assertRaises(ValueError):self.act('teach_machine',target=self.p,instance_id='m')
  self.assertEqual(before,self.state());self.p.spec['tutor_points']=3;self.p.spec['species']='pokemon/이상해씨';before=self.state()
  with self.assertRaises(ValueError):self.act('teach_machine',target=self.p,instance_id='m')
  self.assertEqual(before,self.state())
 def test_hm_unresolved_tp_does_not_consume_inventory_time_or_points(self):
  self.machine('HM1');before=self.state()
  with self.assertRaisesRegex(ValueError,'HM Tutor Point interpretation'):self.act('teach_machine',target=self.p,instance_id='m')
  self.assertEqual(before,self.state());self.assertEqual(self.a.spec['teaching_machines']['m']['status'],'owned')
 def test_hm_native_species_hour_and_instance_day_survive_gm_and_json(self):
  for point_cost in (0,1):
   with self.subTest(point_cost=point_cost):
    self.setUp();self.machine('HM1')
    def decision(target):
     policy=self.e.hm_teaching_policy(self.a,target=target,instance_id='m')
     self.assertEqual(policy['status'],'PolicyInputsRequired')
     return {'value':point_cost,'reason':'GM choice for this actual HM teaching','scope':policy['decision_scope']}
    before=self.e.elapsed_seconds
    out=self.act('teach_machine',target=self.p,instance_id='m',hm_decision=decision(self.p))
    self.assertEqual((out['seconds'],self.e.elapsed_seconds-before,self.p.spec['tutor_points']),(3600,3600,3-point_cost))
    self.assertIn('move/풀베기',self.p.moves)
    self.assertEqual((self.a.spec['items']['HM1'],self.a.spec['teaching_machines']['m']['status']),(1,'owned'))
    self.assertEqual(self.p.spec['move_learning']['move/풀베기']['instance_id'],'m')
    identities=[c.entity_id for c in (self.a,self.p,self.q)]
    self.e.gm.snapshot('HM-used');self.e.gm.restore('HM-used')
    self.assertIs(self.a,next(c for c in self.e.everyone if c.entity_id==identities[0]))
    self.e=Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
    actors={c.entity_id:c for c in self.e.everyone};self.a,self.p,self.q=[actors[x] for x in identities]
    self.e.end_scene()
    before=self.e.export_state()
    with self.assertRaisesRegex(ValueError,'already used today'):
     self.act('teach_machine',target=self.q,instance_id='m',hm_decision=decision(self.q))
    self.assertEqual(self.e.export_state(),before)
    previous_decision=decision(self.q);DT.new_day(self.q);before=self.e.export_state()
    with self.assertRaisesRegex(ValueError,'teaching calendars must agree'):
     self.act('teach_machine',target=self.q,instance_id='m',hm_decision=previous_decision)
    self.assertEqual(self.e.export_state(),before)
    DT.new_day(self.a)
    out=self.act('teach_machine',target=self.q,instance_id='m',hm_decision=decision(self.q))
    self.assertEqual((out['point_cost'],self.q.spec['tutor_points'],self.e.elapsed_seconds),(point_cost,3-point_cost,7200))
    self.assertEqual(self.a.spec['items']['HM1'],1)
    self.assertEqual(self.a.spec['teaching_machines']['m']['used_day'],self.a.spec['frequency_state']['day'])
    self.assertIn('move/풀베기',self.q.moves)
 def test_machine_late_hour_failure_keeps_item_day_moves_points_clock_and_rng(self):
  import activity_jobs as JOBS
  for code in ('TM35','HM1'):
   with self.subTest(code=code):
    self.setUp();self.machine(code);options={}
    if code.startswith('HM'):
     policy=self.e.hm_teaching_policy(self.a,target=self.p,instance_id='m')
     options['hm_decision']={'value':1,'reason':'GM choice for this HM instance and target','scope':policy['decision_scope']}
    before=self.e.export_state();native=JOBS.run_fixed
    def fail(*args,**kwargs):
     native(*args,**kwargs);args[0].rng.random();raise ValueError('late machine teaching failure')
    with patch.object(JOBS,'run_fixed',side_effect=fail):
     with self.assertRaisesRegex(ValueError,'late machine teaching failure'):
      self.act('teach_machine',target=self.p,instance_id='m',**options)
    self.assertEqual(self.e.export_state(),before)
    out=self.act('teach_machine',target=self.p,instance_id='m',**options)
    self.assertEqual((out['seconds'],self.e.elapsed_seconds,self.p.spec['tutor_points']),(3600,3600,2))
    self.assertEqual(self.a.spec['teaching_machines']['m']['status'],'owned' if code.startswith('HM') else 'consumed')
 def test_catalog_keeps_source_prices_and_missing_number_without_inference(self):
  data=T.catalog(self.r);self.assertEqual(len(data['machines']),105);self.assertNotIn('TM29',data['machines']);self.assertEqual(data['machines']['HM1']['price'],75)
  self.assertEqual(data['unassigned_price_rows'][0]['move_name'],'사이코키네시스')
 def test_actual_level_up_awards_tp_and_converts_future_tm_to_natural(self):
  self.p=self.pokemon('future',level=39);self.p.spec['moves']=['move/화염방사','struggle'];self.p.moves=list(self.p.spec['moves'])
  self.p.spec['move_learning']={'move/화염방사':{'method':'tm','source':T.MACHINES,'natural':False}}
  self.assertEqual(T.classifications(self.r,self.p.spec)['move/화염방사'],'taught')
  DT.gain_exp_combatant(self.e,self.p,'to next level')
  self.assertEqual(self.p.level,40);self.assertEqual(self.p.spec['tutor_points'],4);self.assertTrue(self.p.spec['move_learning']['move/화염방사']['natural'])
  self.assertEqual(T.classifications(self.r,self.p.spec)['move/화염방사'],'natural')

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=['engine/pokemon_party.py','engine/pokemon_teaching.py','engine/pokemon_intelligence.py','engine/pokemon_activities.py','engine/downtime.py','engine/engine.py','engine/gm_state.py','engine/researcher_features.py','engine/skill_modifiers.py','engine/common_action_checks.py','engine/builder.py','engine/contest.py','data/pokemon-machines.json','input/ch03-skills-edges-feats.md','input/ch05-pokemon.md','input/ch09-equipment.md','input/ch11-running-the-game.md','tools/test_category3_batch13_pokemon.py','data/rulesets.json','data/skill-check-policy.json','output/ruleunits.jsonl','output/entities/learnsets.json','output/entities/pokemon.json']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':CLAUSES,'partial_only':['DOMAIN-082'],'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-batch13-pokemon-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
