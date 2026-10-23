"""EX063 full native grant: trainer turn, actual performer, relationship and retry."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
import test_category3_contest_skill_features as BASE
from engine import Engine,Rules,Combatant
import contest_features as F
import common_checks as C
import turn as TURN

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 fixture=BASE.Tests.fixture
 friends=BASE.Tests.friends
 snapshot=BASE.Tests.snapshot
 used=BASE.Tests.used
 def setUp(self):self.fixture('귀여움',F.FRIENDS)
 def reject(self,call):
  before=self.snapshot()
  with self.assertRaises(ValueError):call()
  self.assertEqual(self.snapshot(),before)
 def test_original_full_scope_and_inherited_metadata(self):
  r=next(x for x in json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries'] if x['id']=='C3-EX-063')
  self.assertEqual(r['scope_sha256'],BASE.SCOPES['C3-EX-063'])
  a=r['source_snapshot']['source_anchors'][0]
  excerpt='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start_line']-1:a['end_line']])
  self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['excerpt_sha256'])
  lines=(ROOT/'input/ch04-trainer-classes.md').read_text(encoding='utf-8').splitlines()
  self.assertIn('장면 - 자유 행동',lines[1284]);self.assertIn('당신의 포켓몬',lines[1285])
 def test_trainer_turn_resolves_granted_attempt_without_pokemon_action_or_authority(self):
  self.e.start_round([self.t,self.p]);self.e.start_of_turn(self.t)
  budget=deepcopy(getattr(self.p,'budget',None));history=deepcopy(getattr(self.p,'_action_history',[]))
  out=self.friends();self.assertTrue(out['check'].passed)
  self.assertEqual(self.t._action_history,['free']);self.assertEqual(getattr(self.p,'budget',None),budget)
  self.assertEqual(getattr(self.p,'_action_history',[]),history);self.assertEqual(self.used(F.FRIENDS),1)
  self.assertFalse(TURN.spend(self.e,self.p,'standard','unrelated ordinary action'))
  self.assertEqual(self.w.spec['dispositions'],{'pokemon:pokemon/p':'우호적'})
 def test_wrong_trainer_turn_still_rejects_before_any_cost(self):
  self.e.start_round([self.t,self.p]);self.e.start_of_turn(self.p)
  self.reject(self.friends)
 def test_actual_performer_and_target_identity_are_required(self):
  clone=Combatant(self.r,deepcopy(self.p.spec))
  self.reject(lambda:self.friends(friendship_performer=clone))
  other=Combatant(self.r,dict(self.w.spec,id='pokemon/foreign'))
  self.reject(lambda:self.friends(target=other))
  self.reject(lambda:self.friends(skill_target=self.p))
 def test_fainted_sleeping_or_zero_hp_performer_cannot_use_grant(self):
  for mode in ('기절','잠듦','hp'):
   with self.subTest(mode=mode):
    self.setUp()
    if mode=='hp':self.p.hp=0
    else:self.p.conditions.add(mode)
    self.reject(self.friends)
 def test_source_granted_poffin_pool_survives_policy_denial_and_unassigned_charm(self):
  import pokemon_intelligence as I
  for mode in ('campaign_denied','unassigned'):
   with self.subTest(mode=mode):
    self.setUp()
    if mode=='campaign_denied':I.configure(self.e,self.t,portrayal='animals',discussed_with=['GM','player'],social=False,education=False,reason='ordinary social skills not granted')
    else:self.p.spec['skills'].pop('매력')
    self.reject(lambda:self.e.skill_roll(self.p,'매력'))
    self.assertTrue(self.friends()['check'].passed)
    self.assertEqual(self.used(F.FRIENDS),1)
    self.reject(lambda:self.e.skill_roll(self.p,'매력'))
 def test_source_granted_pool_ignores_replaced_species_expression_but_keeps_modifiers(self):
  self.p.spec['skills']['매력']='6d6+50'
  self.e.boost_roll(self.t,self.p,roll_id='explicit-pool',kind='skill')
  out=self.friends(roll_id='explicit-pool',mods=2,helper_rank=4,penalty_count=1,fixed_penalties=[3])
  self.assertEqual(out['check'].total,15) # 5d6=10 +speed3 +AP1 +mods2 +helper2 -penalty3
 def test_captured_and_off_field_performer_are_rejected_before_trainer_cost(self):
  for field in ('captured','on_field'):
   with self.subTest(field=field):
    self.setUp();self.e.start_round([self.t,self.p]);self.e.start_of_turn(self.t)
    setattr(self.p,field,field=='captured');self.reject(self.friends)
 def test_stored_performer_cannot_use_grant_even_if_on_field_flag_is_set(self):
  import pokemon_party as P
  P.configure(self.e,self.t,mode='custom',limit=0,storage={'kind':'center','id':'center/test'},roster=[self.p],reason='GM stores this Pokemon')
  self.p.on_field=True;self.reject(self.friends)
 def test_missing_relationship_is_explicit_pending_then_same_scope_can_resolve(self):
  before=self.snapshot();pending=self.friends(friendship_audience=None)
  self.assertIsInstance(pending,C.PendingDecision);self.assertEqual(self.snapshot(),before)
  result=self.friends();self.assertTrue(result['check'].passed)
 def test_gm_retry_is_bound_to_actual_performer_not_trainer_or_group(self):
  self.assertFalse(self.friends(fixed=[1]*5)['check'].passed)
  self.w.spec['befriend_failures'].append('trainer:trainer/t')
  self.e.end_scene([self.t,self.p,self.w]);self.reject(self.friends)
  out=self.e.pokemon_activity(self.t,'disposition_ruling',target=self.w,disposition='중립',reason='GM confirms materially changed circumstances',allow_retry=True,friendship_performer=self.p,friendship_audience='performer')
  self.assertEqual(out['retry_performer'],'pokemon:pokemon/p')
  self.assertEqual(self.w.spec['befriend_failures'],['trainer:trainer/t'])
  self.assertTrue(self.friends()['check'].passed)
  self.assertEqual(self.w.spec['dispositions'],{'pokemon:pokemon/p':'우호적'})
 def test_gm_retry_does_not_refresh_scene_frequency(self):
  self.assertFalse(self.friends(fixed=[1]*5)['check'].passed)
  self.e.pokemon_activity(self.t,'disposition_ruling',target=self.w,disposition='중립',reason='changed circumstances',allow_retry=True,friendship_performer=self.p,friendship_audience='performer')
  self.reject(self.friends);self.assertEqual(self.used(F.FRIENDS),1)
 def test_gm_relationship_change_without_retry_keeps_failure_barrier(self):
  self.assertFalse(self.friends(fixed=[1]*5)['check'].passed);self.e.end_scene([self.t,self.p,self.w])
  self.e.pokemon_activity(self.t,'disposition_ruling',target=self.w,disposition='중립',reason='same failed performer joins named group',group_id='party',group_members=[self.t.spec['id'],self.p.spec['id']],friendship_performer=self.p,friendship_audience='group')
  self.reject(lambda:self.friends(friendship_audience='group',group_id='party'))
 def test_invalid_gm_group_has_no_partial_relationship_mutation(self):
  before=deepcopy(self.w.spec)
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.t,'disposition_ruling',target=self.w,disposition='중립',reason='invalid omitted performer',allow_retry=True,group_id='party',group_members=[self.t.spec['id']],friendship_performer=self.p,friendship_audience='group')
  self.assertEqual(self.w.spec,before)
 def test_gm_retry_cannot_substitute_unregistered_performer_with_same_id(self):
  self.assertFalse(self.friends(fixed=[1]*5)['check'].passed)
  clone=Combatant(self.r,deepcopy(self.p.spec));before=deepcopy(self.w.spec)
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.t,'disposition_ruling',target=self.w,disposition='중립',reason='wrong actor reference',allow_retry=True,friendship_performer=clone,friendship_audience='performer')
  self.assertEqual(self.w.spec,before)
 def test_ap_completed_id_cannot_repeat_granted_roll(self):
  self.e.boost_roll(self.t,self.p,roll_id='friendship/one',kind='skill')
  out=self.friends(roll_id='friendship/one');self.assertEqual(out['check'].total,14)
  self.e.end_scene([self.t,self.p,self.w]);self.reject(lambda:self.friends(roll_id='friendship/one'))
 def test_shown_source_example_4d6_plus3_uses_live_pool_and_unstaged_speed(self):
  self.p.spec['poffins']=['귀여움']*2
  # Three actual owned eligible Pokemon establish Style Expert independently.
  for n in range(3):
   p=Combatant(self.r,dict(self.p.spec,id='pokemon/prereq'+str(n),poffins=['귀여움']*3));self.e.everyone.append(p)
  self.p.stages['spe']=6
  out=self.friends(fixed=[2]*4);self.assertEqual(out['check'].total,11)

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=[str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py')]
 paths += ['tools/test_category3_friendship_completion.py','tools/test_category3_contest_skill_features.py','input/ch03-skills-edges-feats.md','input/ch04-trainer-classes.md','input/ch05-pokemon.md','input/ch07-combat.md','data/rulesets.json','data/skill-check-policy.json','data/contest-rules.json','output/ruleunits.jsonl']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'completion_scopes':['C3-EX-063'],'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/category3-friendship-completion-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
