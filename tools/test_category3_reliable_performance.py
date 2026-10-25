"""C3-EX-050: actual appeal, accuracy and skill replacement paths."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from contest import ContestEngine,ContestRules
from ruleset import RuleFilter,ExcludedRuleSelection
import contest_features as F
import action_points as AP
class NoRandom:
 def randint(self,a,b):raise AssertionError('replacement must not roll a die')
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT);cls.cr=ContestRules(ROOT)
 def setUp(self):
  self.e=Engine(self.r,seed=313);common={'level':25,'stats':dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),'moves':['연속자르기','몸통박치기','솔라빔','엉겨붙기']}
  self.t=Combatant(self.r,dict(common,id='t',name='T',kind='trainer',classes=['class/코디네이터'],edges=['edge/우아함'],feats=[F.NUANCED,F.RELIABLE],skills={'매력':'달인'}))
  self.p=Combatant(self.r,dict(common,id='p',name='P',kind='pokemon',trainer_id='t',skills={'육상':'초보'}))
  self.target=Combatant(self.r,dict(common,id='wild',name='W',kind='pokemon',wild=True))
  self.t.pos=(0,0);self.p.pos=(1,0);self.target.pos=(2,0)
  self.e.everyone=[self.t,self.p,self.target]
  import pokemon_entities as ENTITIES
  ENTITIES.observe_loyalty(self.e,self.p,3,reason='GM observed loyal partner for actual attack fixture')
  self.ce=ContestEngine(self.cr);self.c=self.ce.contestant_from_combatants(self.e,self.p,self.t,'매력',{'근사함':5})
 def skill(self,**kw):return self.e.contest_skill_feature(self.t,self.p,F.RELIABLE,'육상',10,**kw)
 def appeal(self,**kw):
  options=dict(reliable_performance=True);options.update(kw)
  return self.ce.perform(self.c,'연속자르기','근사함',[],False,**options)
 def accuracy(self,**kw):return self.e.accuracy_check(self.p,self.target,self.r.move('move/몸통박치기'),reliable_trainer=self.t,**kw)
 def test_scope_and_original_reference_match(self):
  row=next(r for r in json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries'] if r['id']=='C3-EX-050')
  self.assertEqual(row['scope_sha256'],'92e0f50fc0de29de3abb6af376d353930cb5519afb1207c9402499b6adb38bca')
  for a in row['source_snapshot']['source_anchors']:
   excerpt='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start_line']-1:a['end_line']])
   self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['excerpt_sha256'])
 def test_skill_uses_floor_average_for_all_ranks_without_fabricated_faces(self):
  for rank,name in enumerate(('불능','미숙','초보','숙련','전문','달인'),1):
   with self.subTest(rank=rank):
    self.setUp();self.p.spec['skills']['육상']=name;self.e.rng=NoRandom();out=self.skill()
    self.assertEqual((out['roll'].base,out['roll'].rank,out['roll'].faces),(rank*7//2,rank,()))
    self.assertEqual(self.t.spec['ap_spent'],2);self.assertEqual(self.t._action_history,['free'])
 def test_skill_keeps_modifiers_helper_penalties_and_existing_ap_bonus(self):
  self.e.boost_roll(self.t,self.p,roll_id='mean',kind='skill');self.e.rng=NoRandom()
  out=self.skill(mods=2,helper_rank=4,helper_bonus=4,penalty_count=1,fixed_penalties=[3],roll_id='mean')
  self.assertEqual(out['roll'].total,14);self.assertEqual(self.t.spec['ap_spent'],3)
  self.assertEqual(self.e._ap_rolls['mean']['state'],'resolved')
 def test_skill_fixed_faces_and_unavailable_ap_are_rejected_without_mutation(self):
  for options in ({'fixed':[3,3,4]},{}):
   if not options:self.t.spec['ap_spent']=AP.maximum(self.t)-1
   before=deepcopy(self.t.spec);rng=self.e.rng.getstate()
   with self.assertRaises(ValueError):self.skill(**options)
   self.assertEqual(self.t.spec,before);self.assertEqual(self.e.rng.getstate(),rng)
 def test_appeal_counts_final_pool_and_keeps_spending_without_center_or_fake_faces(self):
  self.ce.rng=NoRandom();self.c.excitement=2;self.c.double_next=True
  self.appeal(spend_stat_dice=2)
  self.assertEqual((self.c.appeal,self.c.fumble,self.c.stat_dice['근사함']),(11,0,3))
  self.assertFalse(self.c.double_next);self.assertEqual(self.t.spec['ap_spent'],2)
 def test_appeal_no_faces_do_not_trigger_sixes_and_zero_pool_does_not_charge(self):
  self.ce.rng=NoRandom()
  self.ce.perform(self.c,'엉겨붙기','슬기로움',[],True,reliable_performance=True)
  self.assertEqual((self.c.appeal,self.c.fumble,self.c.excitement),(3,0,0));self.assertEqual(self.t.spec['ap_spent'],2)
  self.setUp();self.p.moves=['move/회복지령'];self.c.moves=self.p.moves
  self.ce.perform(self.c,'회복지령','근사함',[],False,reliable_performance=True)
  self.assertEqual(self.c.fumble,1);self.assertNotIn('ap_spent',self.t.spec)
 def test_appeal_in_actual_run_and_repeated_uses_pay_two_each(self):
  contestants=[self.c]
  for i in (1,2):
   t=Combatant(self.r,dict(self.t.spec,id=f't{i}',name=f'T{i}'));p=Combatant(self.r,dict(self.p.spec,id=f'p{i}',name=f'P{i}',trainer_id=f't{i}'))
   self.e.everyone.extend([t,p]);contestants.append(self.ce.contestant_from_combatants(self.e,p,t,'매력',{'근사함':4}))
  def chooser(c,rnd,adj,center):return ('연속자르기',0,{'reliable_performance':True}) if c is self.c else ('연속자르기',0)
  self.ce.run(contestants,'근사함',chooser)
  self.assertEqual(self.t.spec['ap_spent'],6);self.assertEqual(self.c.fumble,0)
 def test_appeal_conflicting_reroll_and_late_action_failure_restore_state(self):
  for mode in ('fixed','coordinator','flourish','sleep'):
   with self.subTest(mode=mode):
    self.setUp();options={}
    if mode=='fixed':options['fixed_rolls']=[1]*4
    elif mode=='coordinator':options['reroll_decision']=lambda first:True
    elif mode=='flourish':options['flourish_decision']=lambda first:True
    else:self.t.conditions.add('잠듦')
    before=deepcopy(vars(self.c));spec=deepcopy(self.t.spec);rng=self.ce.rng.getstate()
    with self.assertRaises(ValueError):self.appeal(**options)
    self.assertEqual(vars(self.c),before);self.assertEqual(self.t.spec,spec);self.assertEqual(self.ce.rng.getstate(),rng)
 def test_all_three_paths_require_owner_class_prerequisites_and_master(self):
  changes=[lambda:self.t.spec['feats'].remove(F.RELIABLE),lambda:self.t.spec['feats'].remove(F.NUANCED),lambda:self.t.spec['classes'].clear(),lambda:self.t.spec['edges'].clear(),lambda:self.t.spec['skills'].update({'매력':'전문'}),lambda:self.p.spec.update(trainer_id='other')]
  for idx,change in enumerate(changes):
   for method in ('skill','appeal','accuracy'):
    with self.subTest(change=idx,path=method):
     self.setUp();change();spec=deepcopy(self.t.spec)
     with self.assertRaises(ValueError):getattr(self,method)()
     self.assertEqual(self.t.spec,spec)
 def test_contest_profile_exclusions_cover_full_dependency_chain(self):
  for uid in (F.RELIABLE,F.NUANCED,'class/코디네이터','edge/우아함'):
   with self.subTest(uid=uid):
    self.ce.r=ContestRules(ROOT,RuleFilter({'sources':['core'],'exclude_units':[uid]}))
    with self.assertRaises(ExcludedRuleSelection):self.appeal()
    self.assertNotIn('ap_spent',self.t.spec)
 def test_accuracy_natural_ten_normal_modifiers_and_critical_range(self):
  self.e.rng=NoRandom();self.p.accuracy_stage=2;self.p.modifiers.append({'type':'crit_range','min':10})
  hit,nat,crit=self.accuracy(situational=1)
  self.assertEqual((hit,nat,crit),(True,10,True));self.assertEqual(self.t.spec['ap_spent'],2)
  hit,nat,crit=self.accuracy(situational=-20)
  self.assertFalse(hit);self.assertEqual(nat,10);self.assertEqual(self.t.spec['ap_spent'],4)
 def test_accuracy_existing_ap_bonus_and_late_exception_no_feature_cost(self):
  self.e.boost_roll(self.t,self.p,roll_id='accuracy-mean',kind='accuracy');self.e.rng=NoRandom();self.accuracy(roll_id='accuracy-mean')
  self.assertEqual(self.t.spec['ap_spent'],3);self.assertEqual(self.e._ap_rolls['accuracy-mean']['state'],'resolved')
  before=deepcopy(self.t.spec);history=self.t._action_history[:]
  with patch('effects_ext.crit_hook',side_effect=ValueError('late native validation')):
   with self.assertRaises(ValueError):self.accuracy()
  self.assertEqual(self.t.spec,before);self.assertEqual(self.t._action_history,history)
 def test_native_use_move_delivers_replacement_and_setup_turn_costs_nothing(self):
  self.e.rng=NoRandom();hp=self.target.hp
  dealt=self.e.use_move(self.p,self.target,'move/몸통박치기',set_damage=True,reliable_trainer=self.t)
  self.assertGreater(dealt,0);self.assertLess(self.target.hp,hp);self.assertEqual(self.t.spec['ap_spent'],2)
  self.setUp();self.e.rng=NoRandom()
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p)
  self.assertEqual(self.e.use_move(self.p,self.target,'move/솔라빔',set_damage=True,reliable_trainer=self.t),0)
  self.assertNotIn('ap_spent',self.t.spec)
  self.e.end_of_turn(self.p);self.e.end_round()
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p)
  self.e.use_move(self.p,self.target,'move/솔라빔',set_damage=True,reliable_trainer=self.t)
  self.assertEqual(self.t.spec['ap_spent'],2)
 def test_native_invalid_selection_precedes_move_action_frequency_and_event(self):
  for mode in ('owner','ap','sleep','shared','self'):
   with self.subTest(mode=mode):
    self.setUp();kwargs={};move='move/몸통박치기'
    if mode=='owner':self.p.spec['trainer_id']='other'
    elif mode=='ap':self.t.spec['ap_spent']=AP.maximum(self.t)-1
    elif mode=='sleep':self.t.conditions.add('잠듦')
    elif mode=='shared':kwargs['_shared_accuracy']={}
    else:move='move/칼춤'
    before=deepcopy(self.t.spec);uses=deepcopy(self.p.move_uses);history=deepcopy(getattr(self.p,'_action_history',None))
    with self.assertRaises(ValueError):self.e.use_move(self.p,self.target,move,set_damage=True,reliable_trainer=self.t,**kwargs)
    self.assertEqual(self.t.spec,before);self.assertEqual(self.p.move_uses,uses);self.assertEqual(getattr(self.p,'_action_history',None),history)
 def test_actual_combat_trigger_keeps_pokemon_standard_and_trainer_free_separate(self):
  self.p.pos=(1,1);self.target.pos=(1,2)
  self.e.start_round([self.t,self.p,self.target]);self.e.start_of_turn(self.p)
  self.e.rng=NoRandom()
  self.e.use_move(self.p,self.target,'move/몸통박치기',set_damage=True,reliable_trainer=self.t)
  self.assertEqual(self.p.budget['standard'],0);self.assertEqual(self.p._action_history,['standard'])
  self.assertEqual(self.t._action_history,['free']);self.assertEqual(self.t.spec['ap_spent'],2)
 def test_native_profile_exclusions_cover_reliable_and_nuanced_sources(self):
  original=self.r
  try:
   for uid in (F.RELIABLE,F.NUANCED):
    with self.subTest(uid=uid):
     self.r=Rules(ROOT);self.r.ruleset=RuleFilter({'sources':['core'],'exclude_units':[uid]});self.r._apply_ruleset();self.setUp()
     with self.assertRaises(ExcludedRuleSelection):self.skill()
     with self.assertRaises(ExcludedRuleSelection):self.accuracy()
     self.assertNotIn('ap_spent',self.t.spec)
  finally:self.r=original
 def test_accuracy_fixed_shared_and_wrong_actor_do_not_consume(self):
  for kw in ({'fixed_roll':10},{'shared_roll':{}}):
   before=deepcopy(self.t.spec)
   with self.assertRaises(ValueError):self.accuracy(**kw)
   self.assertEqual(self.t.spec,before)
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 previous=json.loads((ROOT/'output/category3-contest-skill-features-tests.json').read_text(encoding='utf-8'))
 paths=list(dict.fromkeys([*previous['input_hashes'],'tools/test_category3_reliable_performance.py','engine/contest.py','engine/effects_ext.py','engine/weapon_actions.py']))
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['C3-EX-050'],'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},'source_review':{'ptu_page':83,'inherited_prerequisites':'ch04:481,509-519','no_fabricated_faces':True,'composite_accuracy':'shared or multi-roll selection is held before any move cost'}}
 (ROOT/'output/category3-reliable-performance-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
