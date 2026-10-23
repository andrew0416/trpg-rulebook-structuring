"""Category 3 Pokemon activities: real Engine integration, source scopes and failure boundaries."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import common_checks as C
import pokemon_activities as P
CLAUSES=['C3-EX-018','C3-EX-020','C3-EX-030','C3-EX-044','DOMAIN-063','DOMAIN-065','C3-EX-029','C3-EX-019','DOMAIN-064','C3-EX-124']
class PokemonActivityTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(str(ROOT),ruleset='core')
  cls.errata_rules=Rules(str(ROOT),ruleset='core+errata')
 def setUp(self):
  self.e=Engine(self.rules,seed=181)
  self.a=self.actor('trainer','trainer');self.p=self.actor('wild','pokemon');self.q=self.actor('other','pokemon')
  self.p.spec.update(wild=True,side='wild',disposition='중립',nature='대담');self.p.side='wild';self.e.gm.everyone=[self.a,self.p,self.q]
 def actor(self,name,kind):
  return Combatant(self.rules,{'id':kind+'/'+name,'name':name,'kind':kind,'level':20,'pos':(0,0),'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},'skills':{k:'숙련' for k in ['기술학','포켓몬학','매력','교활','협박','직감','육상','곡예','생존','명령']},'items':{},'edges':[],'feats':[]})
 def act(self,activity,**kw):return self.e.pokemon_activity(self.a,activity,**kw)
 def own(self,name):
  uid=P.FEATURES[name][0];self.a.spec['feats' if uid.startswith('feat/') else 'edges'].append(uid)
 def state(self):return deepcopy((self.e.rng.getstate(),self.e.elapsed_seconds,self.a.spec,self.p.spec,self.a.budget if hasattr(self.a,'budget') else None))
 def repairable(self):
  self.own('repair');self.own('basic_balls');self.a.spec['items']['몬스터볼 공구함']=1
  self.a.spec['items']['몬스터볼']=1
  self.assertFalse(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=1))
  self.act('observe_ball',attempt_id='capture-1',condition='broken',reason='GM inspected failed capture ball')
  self.a.spec['broken_balls']['b1']=self.a.spec['broken_balls'].pop('capture-1')
 def test_source_scopes_unchanged(self):
  data=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf8'))
  for entry in data['entries']:
   if entry['id'] not in CLAUSES:continue
   source=entry['source_snapshot']
   for a in source.get('source_anchors',source.get('anchors',[])):
    start=a.get('start_line',a.get('start'));end=a.get('end_line',a.get('end'))
    actual='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[start-1:end])
    self.assertEqual(actual,a['excerpt'],entry['id'])
 def test_ball_repair_equal_dc_recovers_inventory_once(self):
  self.repairable();result=self.act('repair_ball',ball_id='b1',fixed=[3,4,4,4])
  self.assertTrue(result['check'].passed);self.assertEqual(self.a.spec['items']['몬스터볼'],0)
  self.assertIn(self.a.spec['broken_balls']['b1']['physical_instance_id'],self.e._physical_objects)
  with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',fixed=[6]*4)
  self.assertEqual(self.a.spec['items']['몬스터볼'],0)
 def test_ball_failure_permanently_breaks_no_retry(self):
  self.repairable();result=self.act('repair_ball',ball_id='b1',fixed=[3,3,4,4])
  self.assertEqual(result['status'],'permanently_broken');self.assertEqual(self.a.spec['items']['몬스터볼'],0)
  with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',fixed=[6]*4)
 def test_ball_requires_acquired_edge_tool_and_correct_breakage(self):
  self.repairable()
  for key,value in [('cause','terrain_damage'),('ball_kind','unknown'),('status','permanently_broken')]:
   old=self.a.spec['broken_balls']['b1'][key];self.a.spec['broken_balls']['b1'][key]=value;before=self.state()
   with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1')
   self.assertEqual(before,self.state());self.a.spec['broken_balls']['b1'][key]=old
  self.a.spec['items'].clear();before=self.state()
  with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1')
  self.assertEqual(before,self.state());self.a.spec['accessible_equipment']=['몬스터볼 공구함'];self.a.spec['edges']=[]
  with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1')
 def test_breeding_checks_after_four_hours_then_egg_after_four_more(self):
  self.own('breeder');a=self.act('breed',pair=[self.p,self.q],task_id='egg1',phase='check',compatible=True,fixed=[3]*4)
  self.assertTrue(a['check'].passed);self.assertEqual(self.e.elapsed_seconds,14400);self.assertIsNone(a['egg']);self.assertNotIn('eggs',self.a.spec)
  b=self.act('breed',pair=[self.p,self.q],task_id='egg1',phase='finish')
  self.assertEqual(self.e.elapsed_seconds,28800);self.assertFalse(b['egg']['hatched']);self.assertEqual(len(self.a.spec['eggs']),1)
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='egg1',phase='finish')
 def test_breeding_failed_check_no_egg_invalid_declaration_no_time(self):
  self.own('breeder');before=self.state()
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='bad',phase='check',compatible=False)
  self.assertEqual(before,self.state())
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='bad',phase='check',compatible=True,fixed=[6,6])
  self.assertEqual(before,self.state())
  result=self.act('breed',pair=[self.p,self.q],task_id='failed',phase='check',compatible=True,fixed=[1]*4)
  self.assertEqual(result['status'],'failed');self.assertEqual(self.e.elapsed_seconds,14400)
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='failed',phase='finish')
 def test_breeding_prerequisite_and_target_identity(self):
  self.own('breeder');self.a.spec['skills']['포켓몬학']='미숙'
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.q],task_id='a',phase='check',compatible=True)
  self.a.spec['skills']['포켓몬학']='숙련'
  with self.assertRaises(ValueError):self.act('breed',pair=[self.p,self.p],task_id='a',phase='check',compatible=True)
  self.act('breed',pair=[self.p,self.q],task_id='a',phase='check',compatible=True,fixed=[3]*4)
  with self.assertRaises(ValueError):self.act('breed',pair=[self.q,self.p],task_id='a',phase='finish')
 def test_psychologist_optional_four_skill_substitutions_only(self):
  self.own('psychologist')
  for skill in ('매력','교활','협박','직감'):
   a=self.act('pokemon_interaction',target=self.p,skill=skill,dc=12,use_pokemon_education=True,fixed=[3]*4)
   self.assertEqual(a['skill'],'포켓몬학');self.assertTrue(a['check'].passed)
  a=self.act('pokemon_interaction',target=self.p,skill='매력',dc=12,fixed=[3]*4);self.assertEqual(a['skill'],'매력')
  with self.assertRaises(ValueError):self.act('pokemon_interaction',target=self.p,skill='명령',dc=12,use_pokemon_education=True)
  with self.assertRaises(ValueError):self.act('pokemon_interaction',target=self.a,skill='매력',dc=12,use_pokemon_education=True)
 def test_psychologist_ownership_prerequisite_and_no_global_replacement(self):
  with self.assertRaises(ValueError):self.act('pokemon_interaction',target=self.p,skill='매력',dc=12,use_pokemon_education=True)
  self.own('psychologist');self.a.spec['skills']['포켓몬학']='미숙';self.a.spec['skills']['일반 지식']='미숙'
  with self.assertRaises(ValueError):self.act('pokemon_interaction',target=self.p,skill='매력',dc=12,use_pokemon_education=True)
  self.a.spec['skills']['일반 지식']='초보';result=self.act('pokemon_interaction',target=self.p,skill='매력',dc=10,use_pokemon_education=True,fixed=[5,5]);self.assertTrue(result['check'].passed)
  self.a.spec['skills']['매력']='초보';self.assertEqual(self.e.skill_roll(self.a,'매력',fixed=[1]*3).total,3)
 def test_befriend_all_dc_boundaries_exactly_one_step_and_no_capture(self):
  for index,dc in enumerate(P.DISPOSITION_DC[:-1]):
   self.p.spec['disposition']=P.DISPOSITIONS[index];self.p.spec['dispositions']={};self.p.spec['befriend_failures']=[]
   result=self.act('befriend',target=self.p,fixed=[1]*4,mods=dc-4)
   self.assertEqual(result['check'].dc,dc);self.assertEqual(result['disposition'],P.DISPOSITIONS[index+1]);self.assertFalse(self.p.captured)
  before=self.state();result=self.act('befriend',target=self.p);self.assertEqual(result['status'],'already_very_friendly');self.assertEqual(before,self.state())
 def test_befriend_failure_blocks_repeat_gm_food_can_reset(self):
  result=self.act('befriend',target=self.p,fixed=[1]*4);self.assertFalse(result['check'].passed);self.assertEqual(self.p.spec['disposition'],'중립')
  before=self.state()
  with self.assertRaises(ValueError):self.act('befriend',target=self.p,fixed=[6]*4)
  self.assertEqual(before,self.state())
  self.act('disposition_ruling',target=self.p,disposition='우호적',reason='GM: 먹이 제공으로 개선',allow_retry=True)
  result=self.act('befriend',target=self.p,fixed=[4]*4);self.assertEqual(result['disposition'],'매우 우호적');self.assertFalse(self.p.captured)
 def test_befriend_spends_standard_and_cannot_repeat_without_budget(self):
  self.a.budget={'standard':1,'shift':1,'swift':1};self.act('befriend',target=self.p,fixed=[3]*4)
  self.assertEqual(self.a.budget['standard'],0);self.assertTrue(self.a.took_standard)
  before=self.state();result=self.act('befriend',target=self.p,fixed=[4]*4)
  self.assertIsInstance(result,C.PendingDecision);self.assertEqual(before,self.state())
 def test_befriend_requires_wild_and_explicit_disposition(self):
  self.p.spec.pop('disposition')
  with self.assertRaises(ValueError):self.act('befriend',target=self.p)
  self.p.spec['disposition']='중립';self.p.spec['wild']=False
  with self.assertRaises(ValueError):self.act('befriend',target=self.p)
 def test_pokemaniac_discloses_only_four_fields_on_dc10_success(self):
  self.own('maniac');self.a.budget={'standard':1,'shift':1,'swift':1}
  self.p.abilities=['엽록소'];self.p.types=['풀'];self.p.spec['loyalty']=4
  result=self.act('pokemaniac',target=self.p,fixed=[2,2,3,3]);self.assertTrue(result['check'].passed)
  self.assertEqual(result['information'],{'level':20,'types':['풀'],'nature':'대담','abilities':['엽록소']});self.assertEqual(self.a.budget['standard'],0)
 def test_pokemaniac_failure_ownership_prerequisite_target_and_action(self):
  with self.assertRaises(ValueError):self.act('pokemaniac',target=self.p)
  self.own('maniac');result=self.act('pokemaniac',target=self.p,fixed=[1]*4);self.assertIsNone(result['information'])
  self.a.spec['skills']['포켓몬학']='초보'
  with self.assertRaises(ValueError):self.act('pokemaniac',target=self.p)
  self.a.spec['skills']['포켓몬학']='숙련'
  with self.assertRaises(ValueError):self.act('pokemaniac',target=self.a)
  self.a.budget={'standard':0,'shift':1,'swift':1};before=self.state()
  self.assertIsInstance(self.act('pokemaniac',target=self.p),C.PendingDecision);self.assertEqual(before,self.state())
 def test_invalid_dice_do_not_spend_standard(self):
  self.a.budget={'standard':1,'shift':1,'swift':1};before=self.state()
  with self.assertRaises(ValueError):self.act('befriend',target=self.p,fixed=[7]*4)
  self.assertEqual(before,self.state())
 def test_disabled_feature_profile_refused_before_rng(self):
  self.own('psychologist');original=self.e.r._selected_rule
  with patch.object(self.e.r,'_selected_rule',side_effect=lambda uid:uid+'@unsupported' if uid=='edge/포켓몬-심리학자' else original(uid)):
   before=self.state()
   with self.assertRaises(ValueError):self.act('pokemon_interaction',target=self.p,skill='매력',dc=12,use_pokemon_education=True)
   self.assertEqual(before,self.state())
 def test_fishing_attempts_inventory_and_owner_resume_after_both_restores(self):
  import world_entities as WORLD
  for attachment in ('미끼','루어'):
   with self.subTest(attachment=attachment):
    self.setUp();self.a.spec['items'].update({'좋은낚싯대':1,attachment:1})
    self.p.spec.update(evolved=False,size='Large')
    self.act('fishing',phase='start',rod='좋은낚싯대',attachment=attachment)
    for _ in range(2):self.act('fishing',phase='wait',roll_d20=14)
    self.e.gm.snapshot('waiting-fish');self.act('fishing',phase='wait',roll_d20=14)
    self.e.gm.restore('waiting-fish');self.assertIs(WORLD.actor_index(self.e)[self.a.entity_id],self.a)
    loaded=Engine.import_state(self.rules,json.loads(json.dumps(self.e.export_state())))
    owner=WORLD.actor_index(loaded)[self.a.entity_id];target=WORLD.actor_index(loaded)[self.p.entity_id]
    result=loaded.pokemon_activity(owner,'fishing',phase='wait',roll_d20=14)
    self.assertEqual(result['source'],'ch05-pokemon/낚시');self.assertEqual(result['misses'],3)
    self.assertEqual(loaded.elapsed_seconds,900)
    self.assertEqual(owner.spec['items'][attachment],0 if attachment=='미끼' else 1)
    self.assertEqual(result['status'],'bait_consumed' if attachment=='미끼' else 'waiting')
    if attachment=='루어':
     loaded.pokemon_activity(owner,'fishing',phase='wait',roll_d20=15)
     result=loaded.pokemon_activity(owner,'fishing',phase='reel',target=target,fixed=[2]*4)
     self.assertEqual(result['status'],'landed');self.assertEqual(result['target_id'],target.spec['id'])
     self.assertFalse(target.captured);self.assertTrue(target.spec['fishing'])
     self.assertEqual(owner.spec['items']['루어'],1)
    self.assertTrue(loaded.validate_state()['valid'],loaded.validate_state()['issues'])
 def test_fishing_late_failure_source_and_actual_membership_are_atomic(self):
  self.a.spec['items'].update({'대단한낚싯대':1,'루어':1})
  before=self.e.export_state()
  with patch.object(self.rules,'_selected_rule',return_value='unreviewed-fishing-variant'):
   with self.assertRaisesRegex(ValueError,'selected fishing source'):
    self.act('fishing',phase='start',rod='대단한낚싯대',attachment='루어')
  foreign=self.actor('not-registered','trainer')
  with self.assertRaisesRegex(ValueError,'actual registered'):
   self.e.pokemon_activity(foreign,'fishing',phase='start',rod='대단한낚싯대',attachment='루어')
  self.assertEqual(self.e.export_state(),before)
  self.act('fishing',phase='start',rod='대단한낚싯대',attachment='루어');before=self.e.export_state()
  advance=Engine.advance_time
  def fail_after_time(engine,*args,**options):
   advance(engine,*args,**options);engine.rng.random();raise RuntimeError('after actual fishing time')
  with patch.object(Engine,'advance_time',fail_after_time):
   with self.assertRaisesRegex(RuntimeError,'after actual fishing time'):self.act('fishing',phase='wait')
  self.assertEqual(self.e.export_state(),before)
  self.act('fishing',phase='wait',roll_d20=15);before=self.e.export_state()
  skill_roll=Engine.skill_roll
  def fail_after_roll(engine,*args,**options):
   skill_roll(engine,*args,**options);engine.rng.random();raise RuntimeError('after actual fishing roll')
  with patch.object(Engine,'skill_roll',fail_after_roll):
   with self.assertRaisesRegex(RuntimeError,'after actual fishing roll'):self.act('fishing',phase='reel',target=self.p)
  self.assertEqual(self.e.export_state(),before)
  self.p.spec['trainer_id']=self.a.spec['id'];before=self.e.export_state()
  with self.assertRaisesRegex(ValueError,'unowned wild'):
   self.act('fishing',phase='reel',target=self.p,fixed=[2]*4)
  self.assertEqual(self.e.export_state(),before)
 def test_fishing_failed_bait_always_escapes_without_an_extra_random_roll(self):
  self.a.spec['items'].update({'대단한낚싯대':1,'미끼':1})
  self.act('fishing',phase='start',rod='대단한낚싯대',attachment='미끼')
  self.act('fishing',phase='wait',roll_d20=15);rng=self.e.rng.getstate()
  result=self.act('fishing',phase='reel',target=self.p,fixed=[1]*4)
  self.assertEqual(result['status'],'bait_lost');self.assertIs(result['escaped'],True)
  self.assertEqual(self.a.spec['items']['미끼'],0);self.assertEqual(self.e.rng.getstate(),rng)
  before=self.e.export_state()
  with self.assertRaises(ValueError):self.act('fishing',phase='reel',target=self.p,fixed=[2]*4)
  self.assertEqual(self.e.export_state(),before)
 def test_fishing_five_minutes_and_bite15_then_athletics8_not_capture(self):
  self.a.spec['items'].update({'낡은낚싯대':1,'미끼':1});self.p.level=10;self.p.spec.update(evolved=False,size='Small')
  self.act('fishing',phase='start',rod='낡은낚싯대',attachment='미끼')
  result=self.act('fishing',phase='wait',roll_d20=14);self.assertEqual(result['status'],'waiting');self.assertEqual(self.e.elapsed_seconds,300)
  result=self.act('fishing',phase='wait',roll_d20=15);self.assertEqual(result['status'],'hooked');self.assertEqual(self.e.elapsed_seconds,600)
  result=self.act('fishing',phase='reel',target=self.p,fixed=[2]*4);self.assertTrue(result['check'].passed);self.assertEqual(result['status'],'landed');self.assertFalse(self.p.captured)
 def test_fishing_three_misses_consume_bait_but_lure_reusable(self):
  for attachment in ('미끼','루어'):
   self.a.spec.pop('fishing_session',None);self.a.spec['items'].update({'대단한낚싯대':1,attachment:1})
   self.act('fishing',phase='start',rod='대단한낚싯대',attachment=attachment)
   for _ in range(3):result=self.act('fishing',phase='wait',roll_d20=1)
   self.assertEqual(self.a.spec['items'][attachment],0 if attachment=='미끼' else 1)
   self.assertEqual(result['status'],'bait_consumed' if attachment=='미끼' else 'waiting')
 def test_fishing_rod_target_limits_and_equipment_ownership(self):
  with self.assertRaises(ValueError):self.act('fishing',phase='start',rod='낡은낚싯대',attachment='미끼')
  self.a.spec['items'].update({'낡은낚싯대':1,'좋은낚싯대':1,'대단한낚싯대':1,'루어':1})
  for rod in ('낡은낚싯대','좋은낚싯대','대단한낚싯대'):
   self.a.spec.pop('fishing_session',None);self.act('fishing',phase='start',rod=rod,attachment='루어');self.act('fishing',phase='wait',roll_d20=20)
   self.p.spec.update(evolved=True,size='Large');before=self.state()
   if rod!='대단한낚싯대':
    with self.assertRaises(ValueError):self.act('fishing',phase='reel',target=self.p,fixed=[2]*4)
    self.assertEqual(before,self.state());self.p.spec['evolved']=False
    if rod=='낡은낚싯대':
     with self.assertRaises(ValueError):self.act('fishing',phase='reel',target=self.p,fixed=[2]*4)
     self.p.level=10;self.p.spec['size']='Small'
   self.assertTrue(self.act('fishing',phase='reel',target=self.p,fixed=[2]*4)['check'].passed)
 def test_fishing_failed_athletics_escape10_or_lure_stays11_bait_always_lost(self):
  self.a.spec['items'].update({'대단한낚싯대':1,'미끼':1,'루어':1})
  for attachment,escape,status in [('루어',11,'hooked'),('루어',10,'escaped'),('미끼',20,'bait_lost')]:
   self.a.spec.pop('fishing_session',None);self.act('fishing',phase='start',rod='대단한낚싯대',attachment=attachment);self.act('fishing',phase='wait',roll_d20=15)
   result=self.act('fishing',phase='reel',target=self.p,fixed=[1]*4,escape_d20=escape)
   self.assertFalse(result['check'].passed);self.assertEqual(result['status'],status)
  self.assertEqual(self.a.spec['items']['미끼'],0);self.assertEqual(self.a.spec['items']['루어'],1)
 def test_fishing_invalid_inputs_no_time_rng_or_resource_consumption(self):
  self.a.spec['items'].update({'대단한낚싯대':1,'미끼':1});self.act('fishing',phase='start',rod='대단한낚싯대',attachment='미끼');before=self.state()
  with self.assertRaises(ValueError):self.act('fishing',phase='wait',roll_d20=21)
  self.assertEqual(before,self.state());self.act('fishing',phase='wait',roll_d20=15);before=self.state()
  with self.assertRaises(ValueError):self.act('fishing',phase='reel',target=self.p,fixed=[7]*4)
  self.assertEqual(before,self.state())
 def test_beast_master_only_obedience0_or1_substitutes_intimidate(self):
  self.own('beast');self.p.spec.update(trainer_id=self.a.spec['id'],loyalty=0)
  self.a.spec['skills']['명령']='미숙'
  result=self.act('command_loyalty',target=self.p,use_intimidate=True,fixed=[5]*4);self.assertTrue(result['obeys']);self.assertEqual(result['check'].dc,20)
  self.p.spec['loyalty']=1;result=self.act('command_loyalty',target=self.p,use_intimidate=True,fixed=[2]*4);self.assertTrue(result['obeys'])
  result=self.act('command_loyalty',target=self.p,fixed=[1]*2);self.assertFalse(result['obeys']);self.assertIsInstance(result['failure'],C.PendingDecision)
  self.p.spec.update(loyalty=0,initial_disobedience=True)
  result=self.act('command_loyalty',target=self.p,dc_override=25,use_intimidate=True,fixed=[6]*4,gm_failure={'kind':'idle','reason':'GM chooses refusal'})
  self.assertFalse(result['obeys']);self.assertEqual(result['failure']['kind'],'idle')
 def test_beast_master_training_changes_limit_and_awards_actual_xp(self):
  from builder import build_pokemon
  self.own('beast');self.a.spec['skills']['명령']='불능'
  targets=[Combatant(self.rules,build_pokemon(self.rules,'이상해씨',5,name='trained'+str(i))) for i in range(4)]
  for t in targets:t.spec['trainer_id']=self.a.spec['id']
  self.e.gm.everyone.extend(targets)
  import downtime as DT
  before=[DT.exp_for_level(self.rules,t.level) for t in targets]
  result=self.act('experience_training',targets=targets,use_intimidate=True,safe=True)
  self.assertEqual(result['rank'],4);self.assertEqual(result['awards'],[7]*4);self.assertEqual(self.e.elapsed_seconds,3600)
  self.assertEqual([t.spec['exp']-x for t,x in zip(targets,before)],[7]*4)
  with self.assertRaises(ValueError):self.act('experience_training',targets=[targets[0]],use_intimidate=True,safe=True)
 def test_beast_master_training_prerequisite_and_daily_limits(self):
  from builder import build_pokemon
  target=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',5));target.spec['trainer_id']=self.a.spec['id'];self.e.gm.everyone.append(target)
  with self.assertRaises(ValueError):self.act('experience_training',targets=[target],use_intimidate=True,safe=True)
  self.own('beast');self.a.spec['skills']['협박']='미숙'
  with self.assertRaises(ValueError):self.act('experience_training',targets=[target],use_intimidate=True,safe=True)
  self.a.spec['skills']['협박']='숙련';self.a.spec['experience_training']={'day':0,'count':4};before=self.state()
  with self.assertRaises(ValueError):self.act('experience_training',targets=[target],use_intimidate=True,safe=True)
  self.assertEqual(before,self.state())
 def test_mounted_prowess_auto_boards_then_plus3_still_checks_retention(self):
  self.own('mounted');before=self.e.rng.getstate();self.a.budget={'standard':1,'shift':1,'swift':1}
  result=self.act('mounting',target=self.p,phase='mount',gm_mountable=True,skill='육상')
  self.assertTrue(result['automatic']);self.assertIsNone(result['check']);self.assertEqual(self.e.rng.getstate(),before);self.assertEqual(self.a.budget['standard'],0)
  result=self.act('mounting',target=self.p,phase='retain',skill='곡예',fixed=[1,2,2,2]);self.assertTrue(result['passed']);self.assertEqual(result['check'].total,10);self.assertEqual(result['retention_bonus'],3)
  result=self.act('mounting',target=self.p,phase='retain',skill='육상',fixed=[1]*4);self.assertFalse(result['passed']);self.assertNotIn('mount_id',self.a.spec)
 def test_mounted_prowess_ownership_prerequisite_and_gm_admission(self):
  self.own('mounted');before=self.state()
  with self.assertRaises(ValueError):self.act('mounting',target=self.p,phase='mount',gm_mountable=False)
  self.assertEqual(before,self.state());self.a.spec['skills']['곡예']='미숙';self.a.spec['skills']['육상']='미숙'
  with self.assertRaises(ValueError):self.act('mounting',target=self.p,phase='mount',gm_mountable=True)
  self.a.spec['edges']=[];self.a.spec['skills']['곡예']='숙련';result=self.act('mounting',target=self.p,phase='mount',gm_mountable=True,fixed=[1]*4)
  self.assertFalse(result['passed']);self.assertFalse(result['automatic'])
 def test_mounted_prowess_does_not_replace_other_skills_or_remove_action_cost(self):
  self.own('mounted');self.a.budget={'standard':0,'shift':1,'swift':1};before=self.state()
  result=self.act('mounting',target=self.p,phase='mount',gm_mountable=True);self.assertIsInstance(result,C.PendingDecision);self.assertEqual(before,self.state())
  with self.assertRaises(ValueError):self.act('mounting',target=self.p,phase='mount',gm_mountable=True,skill='포켓몬학')
  self.a.budget['standard']=1
  with self.assertRaises(ValueError):self.act('mounting',target=self.p,phase='mount',gm_mountable=True,fixed=[1]*4)
 def test_groomer_native_hour_own_six_pokemon_and_day_bonus(self):
  self.own('groomer');self.a.spec['items']['미용사 킷']=1
  for t in (self.p,self.q):t.spec['trainer_id']=self.a.spec['id']
  result=self.act('groom',targets=[self.p,self.q],safe=True);self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(result['intro_dice'],1)
  for t in (self.p,self.q):
   self.assertEqual(t.spec['grooming']['day'],0);self.assertEqual(t.spec['grooming']['trainer_id'],self.a.spec['id']);self.assertEqual(t.spec['training_credit']['hours'],1)
  self.act('groom',targets=[self.p],safe=True);self.assertEqual(self.p.spec['grooming']['intro_dice'],1)
 def test_groomer_requires_kit_prerequisite_and_actual_ownership(self):
  self.own('groomer')
  with self.assertRaises(ValueError):self.act('groom',targets=[self.p],safe=True)
  self.a.spec['items']['미용사 킷']=1
  with self.assertRaises(ValueError):self.act('groom',targets=[self.p],safe=True)
  self.p.spec['trainer_id']=self.a.spec['id'];before=self.state()
  with self.assertRaises(ValueError):self.act('groom',targets=[self.p]*7,safe=True)
  self.assertEqual(before,self.state())
 def test_fossils_gm_site_dc15_18_25_qualification_and_no_universal_cave_reward(self):
  for dc in (15,18,25):
   result=self.act('fossil',phase='search',site={'name':'GM deposit','fossils_present':True},dc=dc,minutes=120,
    discovery={'id':str(dc),'species':'pokemon/암나이트'},fixed=[1]*4,mods=dc-4)
   self.assertTrue(result['check'].passed);self.assertEqual(result['fossil']['species'],'pokemon/암나이트')
  self.assertEqual(self.e.elapsed_seconds,21600)
  with self.assertRaises(ValueError):self.act('fossil',phase='search',site={'name':'ordinary cave','fossils_present':False},dc=15,minutes=120,discovery={'id':'x','species':'pokemon/암나이트'})
 def test_fossil_identification_dc10_restoration_needs_machine_and_gives_unhatched_level10_egg(self):
  self.own('paleontologist');self.a.spec['fossils']={'shell':{'species':'pokemon/암나이트','status':'fossil'}}
  result=self.act('fossil',phase='identify',fossil_id='shell',skill='생존',fixed=[2,2,3,3]);self.assertTrue(result['check'].passed)
  with self.assertRaises(ValueError):self.act('fossil',phase='restore',fossil_id='shell')
  self.a.spec['items']['복원기']=1;result=self.act('fossil',phase='restore',fossil_id='shell')
  self.assertEqual(result['egg']['hatch_level'],10);self.assertFalse(result['egg']['hatched']);self.assertIsNone(result['egg']['gm_hatch_details'])
  with self.assertRaises(ValueError):self.act('fossil',phase='restore',fossil_id='shell')
 def test_real_capture_inventory_range_and_actual_ball_producer(self):
  self.a.spec['items']['몬스터볼']=1;self.p.pos=(9,0);before=self.state()
  self.assertFalse(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=1));self.assertEqual(before,self.state())
  self.p.pos=(8,0);self.assertFalse(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=1))
  self.assertEqual(self.a.spec['items']['몬스터볼'],0);record=self.a.spec['capture_attempts']['capture-1'];self.assertTrue(record['hit']);self.assertFalse(record['captured']);self.assertEqual(record['status'],'failed_capture');self.assertNotIn('broken_balls',self.a.spec)
  self.act('observe_ball',attempt_id='capture-1',condition='recovered_intact',reason='GM: intact ball recovered')
  self.assertEqual(self.a.spec['items']['몬스터볼'],0)
  self.assertEqual(tuple(self.e._physical_objects[record['physical_instance_id']]['pos']),tuple(self.a.pos))
  with self.assertRaises(ValueError):self.act('observe_ball',attempt_id='capture-1',condition='recovered_intact',reason='duplicate')
 def test_missed_capture_is_not_repairable_and_ball_can_be_retrieved(self):
  from grid import Grid
  import map_terrain as TERRAIN
  self.e.grid=Grid(10,4);self.p.pos=(2,0)
  for c in self.e.gm.everyone:self.e.gm.set_footprint(c,[(0,0)],reason='actual observed one-cell body')
  TERRAIN.observe(self.e,[(3,0)],base='regular',reason='actual ground behind target')
  self.a.spec['items']['몬스터볼']=1;self.assertFalse(self.e.throw_ball(self.a,self.p,fixed_accuracy=1,fixed_capture=20))
  self.assertEqual(self.a.spec['capture_attempts']['capture-1']['status'],'recoverable_on_ground')
  with self.assertRaises(ValueError):self.act('observe_ball',attempt_id='capture-1',condition='broken',reason='miss is not a failed capture')
  self.e.gm.observe_missed_ball_ground(self.a,attempt_id='capture-1',cell=(3,0),intact=True,reason='actual same missed ball landing')
  self.act('observe_ball',attempt_id='capture-1',condition='recovered_intact',reason='GM retrieved ball behind target');self.assertEqual(self.a.spec['items']['몬스터볼'],0)
 def test_capture_invalid_faces_owned_or_unconscious_target_do_not_spend_ball(self):
  self.a.spec['items']['몬스터볼']=1;before=self.state()
  with self.assertRaises(ValueError):self.e.throw_ball(self.a,self.p,fixed_capture=21)
  self.assertEqual(before,self.state())
  self.p.spec['trainer_id']='another-owner';self.assertFalse(self.e.throw_ball(self.a,self.p));self.assertEqual(self.a.spec['items']['몬스터볼'],1)
  self.p.spec.pop('trainer_id');self.p.hp=0;self.assertFalse(self.e.throw_ball(self.a,self.p));self.assertEqual(self.a.spec['items']['몬스터볼'],1)
 def test_beast_master_virtuoso_effective_rank8_changes_daily_limit_and_bonus15(self):
  from builder import build_pokemon
  self.own('beast');self.a.spec['skills']['협박']='달인';self.a.spec['edges'].append('edge/거장');self.a.spec['edge_choices']={'거장':['협박']}
  targets=[Combatant(self.rules,build_pokemon(self.rules,'이상해씨',5,name='virtuoso'+str(i))) for i in range(8)]
  for t in targets:t.spec['trainer_id']=self.a.spec['id']
  self.e.gm.everyone.extend(targets)
  first=self.act('experience_training',targets=targets[:6],use_intimidate=True,safe=True);second=self.act('experience_training',targets=targets[6:],use_intimidate=True,safe=True)
  self.assertEqual(first['rank'],8);self.assertEqual(first['awards'],[17]*6);self.assertEqual(second['awards'],[17]*2);self.assertEqual(self.e.elapsed_seconds,7200)
  self.assertEqual(self.a.spec['experience_training']['count'],8)
 def test_train_reserves_forbids_beast_master_substitution(self):
  from builder import build_pokemon
  self.own('beast');self.own('reserves');target=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',5));target.spec['trainer_id']=self.a.spec['id'];self.e.gm.everyone.append(target);before=self.state()
  with self.assertRaises(ValueError):self.act('experience_training',targets=[target],use_intimidate=True,use_reserves=True,safe=True)
  self.assertEqual(before,self.state())
 def test_grooming_xp_uses_chosen_education_without_second_hour_or_duplicate_xp(self):
  from builder import build_pokemon
  self.own('groomer');self.a.spec['items']['미용사 킷']=1;self.a.spec['skills']['일반 지식']='전문'
  target=Combatant(self.rules,build_pokemon(self.rules,'이상해씨',5));target.spec['trainer_id']=self.a.spec['id'];self.e.gm.everyone.append(target)
  self.act('groom',targets=[target],safe=True);result=self.act('experience_training',targets=[target],from_grooming=True,bonus_skill='일반 지식',safe=True)
  self.assertEqual(result['xp_rank'],5);self.assertEqual(result['awards'],[12]);self.assertEqual(self.e.elapsed_seconds,3600)
  with self.assertRaises(ValueError):self.act('experience_training',targets=[target],from_grooming=True,bonus_skill='일반 지식',safe=True)
 def test_ball_repair_requires_prior_crafting_edge_not_merely_ball_item(self):
  self.repairable();self.a.spec['edges'].remove('edge/몬스터볼');before=self.state()
  with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',fixed=[6]*4)
  self.assertEqual(before,self.state())
  self.own('apricorn_balls');self.a.spec['skills']['기술학']='초보';self.a.spec['skills']['생존']='미숙'
  with self.assertRaises(ValueError):self.act('repair_ball',ball_id='b1',fixed=[5]*3)
  self.a.spec['skills']['생존']='초보';result=self.act('repair_ball',ball_id='b1',fixed=[5]*3);self.assertTrue(result['check'].passed)
 def test_befriend_disposition_and_failure_are_per_trainer_unless_explicit_group(self):
  other=self.actor('second','trainer');key='trainer:'+self.a.spec['id'];other_key='trainer:'+other.spec['id']
  result=self.act('befriend',target=self.p,fixed=[3]*4);self.assertEqual(result['disposition'],'우호적')
  self.assertEqual(self.p.spec['disposition'],'중립');self.assertNotIn(other_key,self.p.spec['dispositions'])
  result=self.e.pokemon_activity(other,'befriend',target=self.p,fixed=[1]*4);self.assertFalse(result['check'].passed)
  self.assertEqual(self.p.spec['dispositions'][key],'우호적');self.assertEqual(self.p.spec['dispositions'][other_key],'중립')
  self.act('befriend',target=self.p,fixed=[4]*4);self.assertEqual(self.p.spec['dispositions'][key],'매우 우호적')
  with self.assertRaises(ValueError):self.e.pokemon_activity(other,'befriend',target=self.p,fixed=[6]*4)
  self.act('disposition_ruling',target=self.p,disposition='두려움',reason='GM treats these two as one audience',group_id='party',group_members=[self.a.spec['id'],other.spec['id']])
  self.e.pokemon_activity(other,'disposition_ruling',target=self.p,disposition='두려움',reason='GM changed circumstances permit this trainer to retry',group_id='party',allow_retry=True)
  result=self.e.pokemon_activity(other,'befriend',target=self.p,group_id='party',fixed=[2]*4);self.assertEqual(result['disposition'],'중립')
  self.assertEqual(self.p.spec['dispositions']['group:party'],'중립');self.assertEqual(self.p.spec['dispositions'][key],'매우 우호적')
  outsider=self.actor('outsider','trainer')
  with self.assertRaises(ValueError):self.e.pokemon_activity(outsider,'befriend',target=self.p,group_id='party',fixed=[6]*4)
 def test_befriend_group_failure_blocks_only_actor_and_cannot_change_audience_to_retry(self):
  other=self.actor('second','trainer')
  self.act('disposition_ruling',target=self.p,disposition='중립',reason='GM shared audience',group_id='party',group_members=[self.a.spec['id'],other.spec['id']])
  result=self.act('befriend',target=self.p,group_id='party',fixed=[1]*4);self.assertFalse(result['check'].passed)
  self.assertEqual(self.p.spec['befriend_failures'],['trainer:'+self.a.spec['id']])
  with self.assertRaises(ValueError):self.act('befriend',target=self.p,fixed=[6]*4)
  with self.assertRaises(ValueError):self.act('befriend',target=self.p,group_id='party',fixed=[6]*4)
  result=self.e.pokemon_activity(other,'befriend',target=self.p,group_id='party',fixed=[3]*4)
  self.assertTrue(result['check'].passed);self.assertEqual(self.p.spec['dispositions']['group:party'],'우호적')
  with self.assertRaises(ValueError):self.act('befriend',target=self.p,group_id='party',fixed=[6]*4)
 def test_fishing_lure_retry_cannot_replace_hooked_pokemon(self):
  self.a.spec['items'].update({'대단한낚싯대':1,'루어':1});self.act('fishing',phase='start',rod='대단한낚싯대',attachment='루어');self.act('fishing',phase='wait',roll_d20=15)
  self.act('fishing',phase='reel',target=self.p,fixed=[1]*4,escape_d20=11);self.q.spec['wild']=True;before=self.state()
  with self.assertRaises(ValueError):self.act('fishing',phase='reel',target=self.q,fixed=[6]*4)
  self.assertEqual(before,self.state());result=self.act('fishing',phase='reel',target=self.p,fixed=[2]*4);self.assertEqual(result['status'],'landed')
 def combat_command_setup(self):
  self.own('beast');self.p.spec.update(trainer_id=self.a.spec['id'],loyalty=0);self.p.side='party';self.q.side='wild';self.q.hp=self.q.max_hp
  self.e.begin_encounter([self.a,self.p,self.q]);self.e.start_round([self.a,self.p,self.q]);self.e.start_of_turn(self.p)
 def test_beast_master_actual_turn_success_executes_native_move_once(self):
  self.combat_command_setup();self.e.rng.seed(5);before=self.q.hp
  result=self.act('command_move',pokemon=self.p,target=self.q,move_id='struggle',obedience_options={'use_intimidate':True,'fixed':[5]*4},set_damage=True)
  self.assertTrue(result['obedience']['obeys']);self.assertLess(self.q.hp,before);self.assertEqual(self.p.move_uses.get('struggle'),1);self.assertEqual(self.p.budget['standard'],0)
  self.assertEqual(getattr(self.e,'_obedience_receipts',[]),[]);before_rng=self.e.rng.getstate();hp=self.q.hp
  self.e.use_move(self.p,self.q,'struggle',set_damage=True);self.assertEqual(self.q.hp,hp);self.assertEqual(self.e.rng.getstate(),before_rng)
 def test_beast_master_actual_turn_failure_does_not_roll_accuracy_or_use_move(self):
  self.combat_command_setup();before=(self.e.rng.getstate(),self.q.hp,dict(self.p.move_uses),dict(self.p.budget))
  result=self.act('command_move',pokemon=self.p,target=self.q,move_id='struggle',obedience_options={'use_intimidate':True,'fixed':[1]*4},set_damage=True)
  self.assertEqual(result['status'],'disobedient');self.assertEqual(before,(self.e.rng.getstate(),self.q.hp,dict(self.p.move_uses),dict(self.p.budget)))
  self.e.use_move(self.p,self.q,'struggle',set_damage=True);self.assertEqual(before,(self.e.rng.getstate(),self.q.hp,dict(self.p.move_uses),dict(self.p.budget)))
  self.assertIsInstance(self.act('command_move',pokemon=self.p,target=self.q,move_id='struggle',obedience_options={'use_intimidate':True,'fixed':[6]*4}),C.PendingDecision)
  result=self.act('resolve_disobedience',pokemon=self.p,decision='idle',reason='GM selects doing nothing');self.assertEqual(result['status'],'idle')
 def test_beast_master_failed_command_gm_can_choose_actual_attack_and_target(self):
  self.combat_command_setup();self.e.rng.seed(5)
  self.act('command_move',pokemon=self.p,target=self.q,move_id='struggle',obedience_options={'use_intimidate':True,'fixed':[1]*4})
  before=self.a.hp;result=self.act('resolve_disobedience',pokemon=self.p,target=self.a,move_id='struggle',decision='action',reason='GM chooses attack on trainer',set_damage=True)
  self.assertEqual(result['status'],'submitted');self.assertLess(self.a.hp,before);self.assertNotIn('pending_disobedience',self.p.spec);self.assertEqual(getattr(self.e,'_obedience_receipts',[]),[])
 def test_beast_master_command_receipt_removed_after_execution_exception(self):
  self.combat_command_setup();original=self.e.use_move
  def fails(*a,**k):raise RuntimeError('downstream execution failure')
  self.e.use_move=fails
  try:
   with self.assertRaises(RuntimeError):self.act('command_move',pokemon=self.p,target=self.q,move_id='struggle',obedience_options={'use_intimidate':True,'fixed':[5]*4})
  finally:self.e.use_move=original
  self.assertEqual(getattr(self.e,'_obedience_receipts',[]),[]);before=self.e.rng.getstate();self.e.use_move(self.p,self.q,'struggle');self.assertEqual(self.e.rng.getstate(),before)
 def test_revision_capture_modifiers_source_conversion_and_round_boundaries(self):
  import items as I
  for name,value in {'몬스터볼':0,'슈퍼볼':2,'하이퍼볼':3,'마스터볼':20,'파크볼':3,'프렌드볼':1,'럭셔리볼':1,'힐볼':1,'프레셔스볼':1}.items():self.assertEqual(I.ball_modifier(self.e,name,self.a,self.p)[0],value,name)
  for r,value in [(1,-1),(2,0),(3,1),(4,2),(5,3),(6,4),(10,4)]:self.e.round_no=r;self.assertEqual(I.ball_modifier(self.e,'타이머볼',self.a,self.p)[0],value)
  for r,value in [(1,4),(2,3),(3,2),(4,0)]:self.e.round_no=r;self.assertEqual(I.ball_modifier(self.e,'퀵볼',self.a,self.p)[0],value)
 def test_capture_trainer_milestones_and_persistent_volatile_status_only(self):
  self.p.spec['evolutions_remaining']=0;self.p.hp=self.p.base_max_hp;baseline=self.e.capture_rate(self.p)[0]
  for status in ('취약','붙잡힘','임시 체력'):
   self.p.conditions={status};self.assertEqual(self.e.capture_rate(self.p)[0],baseline)
  for statuses in ({'독'},{'혼란'},{'독','화상','혼란'}):
   self.p.conditions=statuses;self.assertEqual(self.e.capture_rate(self.p)[0],baseline-2)
  self.p.conditions=set()
  for level,bonus in [(4,0),(5,1),(9,1),(10,2),(19,2),(20,3),(29,3),(30,4),(39,4),(40,5)]:
   self.a.level=level;self.a.spec['items']['몬스터볼']=1;self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=1)
   record=self.a.spec['capture_attempts']['capture-'+str(self.a.spec['capture_attempt_serial'])];self.assertEqual(record['capture_total'],1+bonus)
 def test_capture_legacy_revision_not_silently_executed_as_d20(self):
  legacy=Engine(Rules(str(ROOT),ruleset='legacy-capture'),seed=2);before=legacy.rng.getstate();self.a.spec['items']['몬스터볼']=1
  with self.assertRaises(ValueError):legacy.capture_rate(self.p)
  with self.assertRaises(ValueError):legacy.throw_ball(self.a,self.p,fixed_capture=1)
  self.assertEqual(legacy.rng.getstate(),before);self.assertEqual(self.a.spec['items']['몬스터볼'],1)
 def fossil_egg(self):
  self.own('paleontologist');self.a.spec['items']['복원기']=1;self.a.spec['fossils']={'f1':{'species':'pokemon/암나이트','status':'fossil'}}
  self.act('fossil',phase='restore',fossil_id='f1')
  return {'gender':'female','nature':'고집','abilities':['깨어진갑옷'],'moves':['move/물대포'],'special_appearance':False,'inheritance_moves':[]}
 def test_fossil_hatches_actual_native_level10_with_gm_selected_facts(self):
  details=self.fossil_egg();result=self.act('hatch_fossil',egg_id='fossil/f1',name='새암나이트',ready=True,reason='GM confirmed the fossil egg hatch time',details=details)
  p=result['pokemon'];self.assertEqual(p.level,10);self.assertEqual(p.spec['nature'],'고집');self.assertEqual(p.abilities,['깨어진갑옷']);self.assertIn('move/물대포',p.moves)
  self.assertEqual(p.spec['gender'],'female');self.assertFalse(p.spec['special_appearance']);self.assertEqual(p.spec['inheritance_moves'],[]);self.assertIn(p,self.e.gm.everyone)
  self.assertEqual(self.a.spec['fossils']['f1']['status'],'hatched')
  with self.assertRaises(ValueError):self.act('hatch_fossil',egg_id='fossil/f1',name='duplicate',ready=True,reason='repeat',details=details)
 def test_fossil_no_premature_hatch_or_guessed_gm_properties(self):
  details=self.fossil_egg();before=self.state()
  with self.assertRaises(ValueError):self.act('hatch_fossil',egg_id='fossil/f1',name='새암나이트',ready=False,reason='not ready',details=details)
  self.assertEqual(before,self.state())
  for key in details:
   incomplete={k:v for k,v in details.items() if k!=key}
   with self.assertRaises(ValueError):self.act('hatch_fossil',egg_id='fossil/f1',name='새암나이트',ready=True,reason='GM timing',details=incomplete)
   self.assertEqual(before,self.state())
 def test_fossil_inheritance_and_special_appearance_follow_explicit_gm_choice(self):
  details=self.fossil_egg();details.update(special_appearance=True,inheritance_moves=['move/거품'])
  result=self.act('hatch_fossil',egg_id='fossil/f1',name='특별암나이트',ready=True,reason='GM special fossil',details=details)
  self.assertTrue(result['pokemon'].spec['special_appearance']);self.assertEqual(result['pokemon'].spec['inheritance_moves'],['move/거품'])
 def test_fossil_novice_paleontologist_can_search_but_unqualified_cannot_spawn_fossil(self):
  self.a.spec['skills']['포켓몬학']='초보';self.a.spec['skills']['생존']='미숙';site={'name':'GM dry lake','fossils_present':True};discovery={'id':'x','species':'pokemon/암나이트'}
  with self.assertRaises(ValueError):self.act('fossil',phase='search',site=site,dc=15,minutes=120,discovery=discovery,fixed=[5]*3)
  self.own('paleontologist');result=self.act('fossil',phase='search',site=site,dc=15,minutes=120,discovery=discovery,fixed=[5]*3)
  self.assertTrue(result['qualified']);self.assertIsNotNone(result['fossil'])
 def collector_setup(self,stacks=3):
  self.rules=self.errata_rules;self.setUp()
  self.a.spec['items']['몬스터볼']=5
  self.a.spec['feats']=['feat/포켓몬-넌-내-꺼야','feat/고급-포획-테크닉']
  self.a.spec['classes']=['class/포획전문가'];self.a.spec['feat_ranks']={'feat/고급-포획-테크닉':3}
  self.a.spec['skills'].update({'곡예':'전문','육상':'전문','통찰':'초보','은신':'초보'})
  self.a.spec['collector_stacks']=stacks;self.p.spec['species']='pokemon/이상해씨'
 def test_collector_bonus_spends_one_to_three_and_adds_exactly_that_number(self):
  for count in (1,2,3):
   self.collector_setup();result=self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=9-count,collector_choice={'kind':'bonus','stacks':count})
   self.assertTrue(result);record=self.a.spec['capture_attempts']['capture-1'];self.assertEqual(record['capture_total'],12)
   self.assertEqual(record['collector']['bonus'],count);self.assertEqual(record['collector']['spent'],count);self.assertEqual(self.a.spec['collector_stacks'],4-count)
 def test_collector_decision_sees_original_roll_then_complete_reroll_replaces_it(self):
  self.collector_setup();seen=[]
  def choose(facts):seen.append(facts);return {'kind':'reroll'}
  self.assertTrue(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=1,collector_choice=choose,fixed_reroll=20))
  self.assertEqual(seen,[{'natural':1,'total':4,'dc':12,'stacks':3}]);record=self.a.spec['capture_attempts']['capture-1']
  self.assertEqual(record['capture_natural'],20);self.assertEqual(record['capture_total'],23);self.assertEqual(record['collector']['original_natural'],1);self.assertEqual(record['collector']['bonus'],0);self.assertEqual(self.a.spec['collector_stacks'],1)
 def test_collector_new_currently_unowned_evolution_family_only_and_not_history(self):
  self.collector_setup(0);self.q.spec.update(species='pokemon/이상해꽃',trainer_id=self.a.spec['id'])
  self.assertTrue(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=20));self.assertEqual(self.a.spec['collector_stacks'],0)
  self.collector_setup(0);self.a.spec['caught_species']=['pokemon/이상해씨']
  self.assertTrue(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=20));self.assertEqual(self.a.spec['collector_stacks'],1)
  self.q.spec.update(wild=True,species='pokemon/이상해풀');self.q.side='wild'
  self.assertTrue(self.e.throw_ball(self.a,self.q,fixed_accuracy=20,fixed_capture=20));self.assertEqual(self.a.spec['collector_stacks'],1)
 def test_collector_miss_failure_no_earned_stack_or_extra_swift_cost(self):
  self.collector_setup();before=self.a.spec['collector_stacks']
  self.assertFalse(self.e.throw_ball(self.a,self.p,fixed_accuracy=1,fixed_capture=20,collector_choice={'kind':'bonus','stacks':3}));self.assertEqual(self.a.spec['collector_stacks'],before)
  self.assertFalse(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=1,collector_choice={'kind':'bonus','stacks':1}));self.assertEqual(self.a.spec['collector_stacks'],before-1)
  self.collector_setup();self.e.begin_encounter([self.a,self.p]);self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.a)
  self.assertTrue(self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=9,collector_choice={'kind':'bonus','stacks':1}));self.assertEqual(self.a.budget['swift'],1)
 def test_collector_prerequisites_invalid_choice_and_insufficient_stacks_before_cost(self):
  for edit in ('not_acquired','rank2','missing_class','one_expert'):
   self.collector_setup()
   if edit=='not_acquired':self.a.spec['feats'].remove('feat/포켓몬-넌-내-꺼야')
   elif edit=='rank2':self.a.spec['feat_ranks']['feat/고급-포획-테크닉']=2
   elif edit=='missing_class':self.a.spec['classes']=[]
   else:self.a.spec['skills']['곡예']='숙련'
   before=self.state()
   with self.assertRaises(ValueError):self.e.throw_ball(self.a,self.p,collector_choice={'kind':'bonus','stacks':1})
   self.assertEqual(before,self.state())
  for choice in ({'kind':'bonus','stacks':4},{'kind':'reroll','stacks':3},{'kind':'bonus','stacks':1,'reroll':True}):
   self.collector_setup();before=self.state()
   with self.assertRaises(ValueError):self.e.throw_ball(self.a,self.p,collector_choice=choice)
   self.assertEqual(before,self.state())
  self.collector_setup(2);before=self.state()
  with self.assertRaises(ValueError):self.e.throw_ball(self.a,self.p,collector_choice={'kind':'reroll'})
  self.assertEqual(before,self.state())
 def test_collector_core_cannot_use_errata_stacks(self):
  self.collector_setup();self.e.r=PokemonActivityTests.rules;before=self.state()
  with self.assertRaises(ValueError):self.e.throw_ball(self.a,self.p,collector_choice={'kind':'bonus','stacks':1})
  self.assertEqual(before,self.state())
 def test_collector_invalid_post_roll_choice_finalizes_original_without_refund_or_new_roll(self):
  for original in (1,20):
   for invalid in ('bad_choice','exception'):
    self.collector_setup();self.e.begin_encounter([self.a,self.p]);self.e.start_round([self.a,self.p]);self.e.start_of_turn(self.a)
    rng=self.e.rng.getstate()
    def choose(facts):
     if invalid=='exception':raise RuntimeError('host decision failure')
     return {'kind':'bonus','stacks':9}
    result=self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=original,collector_choice=choose)
    self.assertEqual(result,original==20);self.assertEqual(self.e.rng.getstate(),rng)
    self.assertEqual(self.a.spec['items']['몬스터볼'],4);self.assertEqual(self.a.budget['standard'],0)
    record=self.a.spec['capture_attempts']['capture-1'];self.assertIsNotNone(record['collector']['choice_rejected'])
    self.assertEqual(record['capture_natural'],original);self.assertEqual(record['collector']['spent'],0);self.assertEqual(self.a.spec['collector_stacks'],3+(original==20))
 def test_collector_complete_reroll_can_replace_success_with_failure(self):
  self.collector_setup();result=self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=20,collector_choice={'kind':'reroll'},fixed_reroll=1)
  self.assertFalse(result);self.assertEqual(self.a.spec['collector_stacks'],0);self.assertFalse(self.p.captured)
  self.assertEqual(self.a.spec['capture_attempts']['capture-1']['capture_natural'],1)
 def test_collector_replaced_policy_identity_refused_before_cost(self):
  for uid in (P.COLLECTOR_REVISION,P.COLLECTOR_FEAT,'feat/고급-포획-테크닉','class/포획전문가'):
   self.collector_setup();selection=self.rules.selection;before=self.state();old=dict(selection.aliases)
   selection.aliases[uid]='edge/비스트-마스터'
   try:
    with self.assertRaises(ValueError):self.e.throw_ball(self.a,self.p,collector_choice={'kind':'bonus','stacks':1})
    self.assertEqual(before,self.state())
   finally:selection.aliases=old
 def test_collector_unknown_or_malformed_family_does_not_invent_singleton_reward(self):
  for problem in ('missing','unparsed','target_missing','owned_missing'):
   self.collector_setup();name='이상해씨';ls=self.rules.learnsets[name];previous=deepcopy(ls['evolution'])
   if problem=='missing':ls['evolution']=[]
   elif problem=='unparsed':ls['evolution']=['not an interpreted family']
   elif problem=='target_missing':ls['evolution']=['1 - 꼬부기']
   else:self.q.spec.update(species='pokemon/이상해씨',trainer_id=self.a.spec['id']);self.p.spec['species']='pokemon/꼬부기';ls['evolution']=[]
   before=self.state()
   try:
    with self.assertRaises(ValueError):self.e.throw_ball(self.a,self.p,fixed_accuracy=20,fixed_capture=20)
    self.assertEqual(before,self.state());self.assertEqual(self.a.spec['collector_stacks'],3)
   finally:ls['evolution']=previous
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(PokemonActivityTests))
 files=['engine/adjudication_guidance.py','data/adjudication-guidance.json','engine/skill_maneuver_actions.py','engine/food_effects.py','engine/combat_social_edges.py','engine/net_capsule.py','engine/trainer_capabilities.py','engine/skill_feature_actions.py','engine/researcher_features.py','engine/precise_actions.py','engine/environmental_effects.py','engine/wild_equipment.py','engine/injury_recovery.py','engine/common_action_checks.py','engine/gm_state.py','engine/heavy_injury_adapter.py','engine/jump_actions.py','engine/context_actions.py','engine/pokemon_requests.py','engine/combat_timing.py','engine/combat_maneuvers.py','data/context-check-policy.json','data/cultivation-policy.json','engine/movement_actions.py','engine/weapon_actions.py','data/weapon-policy.json','engine/bandages.py','engine/crafting_activities.py','engine/contest_features.py','data/planter-policy.json','engine/pokemon_activities.py','engine/ap_roll_bonus.py','engine/items.py','engine/effects_ext.py','engine/frequency.py','engine/downtime.py','engine/builder.py','engine/engine.py','engine/capability_actions.py','engine/physical_limits.py','data/capability-policy.json','engine/skill_modifiers.py','data/skill-check-policy.json','engine/turn.py','engine/common_checks.py','engine/action_lifecycle.py','engine/ruleset.py','engine/rulings.py','input/ch02-character-creation.md','input/ch03-skills-edges-feats.md','input/ch04-trainer-classes.md','input/ch05-pokemon.md','input/ch09-equipment.md','input/supp-errata.md','data/core-rules.json','output/entities/pokemon.json','output/entities/learnsets.json','data/lookup-tables.json','data/rulesets.json','output/ruleunits.jsonl','tools/test_category3_pokemon_activities.py']
 files += ['engine/campaign_rewards.py', 'engine/league_consequences.py', 'data/campaign-reward-policy.json']
 files += ['engine/pokemon_understanding.py', 'engine/regional_pokemon.py', 'engine/source_context.py']
 files += ['engine/blessing_skill_features.py', 'engine/combat_precision_features.py', 'engine/pokemon_intelligence.py', 'engine/pokemon_party.py', 'engine/pokemon_teaching.py', 'data/pokemon-machines.json']

 files += ['engine/arithmetic.py', 'engine/arithmetic_policy.py', 'engine/effect_contracts.py', 'engine/effect_lifetimes.py', 'engine/maneuver_grants.py', 'engine/move_activation.py', 'engine/native_rule_policy.py', 'data/native-rule-policy.json']

 files += ['engine/action_lifecycle.py', 'engine/action_metadata.py', 'engine/action_points.py', 'engine/adjudication_guidance.py', 'engine/ap_roll_bonus.py', 'engine/bandages.py', 'engine/bound_ap.py', 'engine/builder.py', 'engine/capability_actions.py', 'engine/combat_maneuvers.py', 'engine/combat_social_edges.py', 'engine/combat_stage_sources.py', 'engine/combat_timing.py', 'engine/common_action_checks.py', 'engine/common_checks.py', 'engine/contest.py', 'engine/contest_features.py', 'engine/context_actions.py', 'engine/crafting_activities.py', 'engine/custom_species.py', 'engine/damage_reactions.py', 'engine/demo_rulings.py', 'engine/downtime.py', 'engine/effects.py', 'engine/effects_ext.py', 'engine/elemental_connection.py', 'engine/encounter.py', 'engine/enduring_awareness.py', 'engine/engine.py', 'engine/environmental_effects.py', 'engine/focus_tasks.py', 'engine/food_effects.py', 'engine/frequency.py', 'engine/gm_console.py', 'engine/gm_state.py', 'engine/grid.py', 'engine/heavy_injury_adapter.py', 'engine/heavy_injury_kernel.py', 'engine/heavy_standard_adapter.py', 'engine/initiative.py', 'engine/injury_recovery.py', 'engine/items.py', 'engine/jump_actions.py', 'engine/league_agenda.py', 'engine/league_runtime.py', 'engine/life.py', 'engine/maneuver_edges.py', 'engine/movement_actions.py', 'engine/net_capsule.py', 'engine/observed_resolution.py', 'engine/passive_event_profiles.py', 'engine/passive_events.py', 'engine/physical_limits.py', 'engine/physics_maneuvers.py', 'engine/pokemon_activities.py', 'engine/pokemon_requests.py', 'engine/precise_actions.py', 'engine/researcher_features.py', 'engine/resolution_transaction.py', 'engine/rest_intervals.py', 'engine/restorative_items.py', 'engine/root_admission.py', 'engine/root_children.py', 'engine/root_common_checks.py', 'engine/root_common_engine.py', 'engine/root_inputs.py', 'engine/root_machine.py', 'engine/root_resolution.py', 'engine/root_scheduler.py', 'engine/ruleset.py', 'engine/rulings.py', 'engine/skill_feature_actions.py', 'engine/skill_maneuver_actions.py', 'engine/skill_modifiers.py', 'engine/skill_stunts.py', 'engine/skill_targets.py', 'engine/survivalist_features.py', 'engine/temporary_hp.py', 'engine/test_builder.py', 'engine/test_contest.py', 'engine/test_downtime.py', 'engine/test_effects.py', 'engine/test_gm_state.py', 'engine/test_grid.py', 'engine/test_items.py', 'engine/test_maintenance.py', 'engine/test_playthrough.py', 'engine/test_rules.py', 'engine/test_ruleset.py', 'engine/test_rulings.py', 'engine/test_turn.py', 'engine/trainer_capabilities.py', 'engine/turn.py', 'engine/weapon_actions.py', 'engine/wild_equipment.py', 'data/content-source-identities.json', 'data/context-check-policy.json', 'data/skill-check-policy.json', 'data/adjudication-guidance.json', 'data/rulesets.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':CLAUSES,'results':result.rows,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-pokemon-activity-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 raise SystemExit(0 if result.wasSuccessful() else 1)
