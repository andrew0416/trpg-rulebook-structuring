"""Batch 15: DOMAIN048 actual paired contest, and DOMAIN037 explicit partial."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from contest import ContestEngine,ContestRules
from engine import Engine,Rules,Combatant
from ruleset import RuleFilter,ExcludedRuleSelection,UnresolvedRuleSelection
import contest_features as F
import action_points as AP
import observed_resolution as OBS
class Pause(Exception):pass
class CountRng:
 def __init__(self,face=3):self.calls=0;self.face=face
 def randint(self,a,b):self.calls+=1;return self.face
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.nr=Rules(ROOT);cls.cr=ContestRules(ROOT);cls.effects={}
  for uid in cls.cr._moves:
   try:stat,effect=cls.cr.move_contest(uid)
   except (ValueError,KeyError,UnresolvedRuleSelection):continue
   cls.effects.setdefault(effect,uid)
 def setUp(self):
  self.native=Engine(self.nr);self.e=ContestEngine(self.cr);self.e.rng=CountRng()
  self.ts=[];self.ps=[];self.cs=[];self.partners=[]
  moves=list(dict.fromkeys(['move/연속자르기','move/헤롱헤롱',*self.effects.values()]))
  for i in range(3):
   common={'level':25,'stats':dict.fromkeys(['hp','atk','def','spa','spd','spe'],10),'moves':moves[:]}
   t=Combatant(self.nr,dict(common,id=f't{i}',name=f'T{i}',kind='trainer',skills={'명령':'전문','매력':'초보'},classes=['class/코디네이터',F.STYLE],edges=['edge/우아함'],feats=['feat/근사한-행위',F.FLOURISH],feat_ranks={'feat/근사한-행위':2},feature_choices={F.STYLE:['근사함'],F.FLOURISH:['근사함']}))
   p=Combatant(self.nr,dict(common,id=f'p{i}',name=f'P{i}',kind='pokemon',trainer_id=f't{i}',poffins=['근사함']*3))
   self.ts.append(t);self.ps.append(p)
   c=self.e.contestant_from_combatants(self.native,p,t,'매력',dict.fromkeys(['근사함','강인함','아름다움','슬기로움','귀여움'],4))
   self.cs.append(c);self.partners.append(self.e.trainer_participant(c))
  self.native.everyone=[*self.ts,*self.ps]
 def run_contest(self,chooser=None,mode='simultaneous',order=None,identity='paired-15'):
  if order is None:order=(lambda c,t,r:[t,c]) if mode=='simultaneous' else (lambda c,t,r:[t if r%2 else c])
  return self.e.run(self.cs,'근사함',chooser or (lambda *args:('연속자르기',0)),trainer_model=mode,trainer_order=order,contest_id=identity)
 def checkpoint_first_choice(self,mode='simultaneous'):
  with self.assertRaises(Pause):self.run_contest(lambda *args:(_ for _ in ()).throw(Pause()),mode)
 def total(self):return sum(c.appeal+c.fumble for c in [*self.cs,*self.partners])
 def test_001_fixed_full_source_048_and_unmodified_037(self):
  register=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf8'))
  expected={'DOMAIN-048':'eff1460934124b6249865f942aac196e374d8ae022b16ec5f3e6b71982a317fa','DOMAIN-037':'95868085ce0c3d252fea4c0460c096a51ab9ec19e8fea4f131a0dd75002ed820'}
  for uid,sha in expected.items():
   row=next(r for r in register['entries'] if r['id']==uid);self.assertEqual(row['scope_sha256'],sha)
   for anchor in row['source_snapshot']['anchors']:
    lines=(ROOT/anchor['file']).read_text(encoding='utf-8-sig').splitlines();text='\n'.join(lines[anchor['start']-1:anchor['end']]);self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),anchor['sha256'])
 def test_002_simultaneous_both_each_round_separate_voltage_shared_pool(self):
  seen=[]
  self.run_contest(lambda c,r,a,k:seen.append((c,r,tuple(a),k)) or ('연속자르기',0))
  self.assertEqual(len(seen),18);self.assertEqual(len(self.e.last_standings),3)
  for c,t in zip(self.cs,self.partners):
   self.assertIs(c.stat_dice,t.stat_dice);self.assertNotIn('_paired_state',vars(c))
   self.assertEqual(sum(x[0] is c for x in seen),3);self.assertEqual(sum(x[0] is t for x in seen),3)
  self.partners[0].excitement=1;self.cs[0].excitement=4;self.assertEqual(self.partners[0].excitement,1)
  first=seen[0];self.assertIs(first[0],self.partners[0]);self.assertTrue(first[3]);self.assertEqual(set(first[2]),{*self.cs[1:],*self.partners[1:]})
 def test_003_alternating_one_per_round_shared_voltage_and_effect_state(self):
  seen=[];self.run_contest(lambda c,r,a,k:seen.append((c,r,tuple(a))) or ('연속자르기',0),mode='alternating')
  self.assertEqual(len(seen),9)
  for c,t in zip(self.cs,self.partners):
   self.assertIs(c._paired_state,t._paired_state);self.assertIs(c.stat_dice,t.stat_dice)
   self.assertEqual([x[0] for x in seen if x[0] in (c,t)],[t,c,t]);t.excitement=2;self.assertEqual(c.excitement,2)
  self.assertEqual(len(seen[0][2]),2)
 def test_004_adjacency_effect_hits_both_neighbors_in_simultaneous(self):
  self.checkpoint_first_choice();others=[*self.cs[1:],*self.partners[1:]]
  for c in others:c.excitement=3
  count=[0]
  def choose(*a):
   count[0]+=1
   if count[0]>1:raise Pause()
   return self.effects['동요'],0
  with self.assertRaises(Pause):self.run_contest(choose)
  self.assertTrue(all(c.excitement==2 for c in others))
 def test_005_alternating_pending_next_effect_moves_to_other_performer(self):
  self.checkpoint_first_choice('alternating');seen=[]
  def choose(c,r,a,k):
   if r==2 and c is self.cs[0]:
    self.assertTrue(c.double_next);seen.append(self.e.rng.calls);return '연속자르기',0
   if r==3:raise Pause()
   return (self.effects['준비하기'] if r==1 and c is self.partners[0] else '연속자르기'),0
  with self.assertRaises(Pause):self.run_contest(choose,mode='alternating')
  self.assertFalse(self.cs[0].double_next);self.assertFalse(self.partners[0].double_next);self.assertTrue(seen)
  self.assertTrue(any('기술 주사위 두 배' in l for l in self.e.log_lines))
 def test_006_shared_dice_and_invalid_spend_are_atomic(self):
  self.checkpoint_first_choice();before=self.cs[0].stat_dice['근사함'];calls=[0]
  def choose(*a):
   calls[0]+=1
   return '연속자르기',3 if calls[0]==1 else 3
  with self.assertRaises(ValueError):self.run_contest(choose)
  self.assertEqual(self.cs[0].stat_dice['근사함'],before-3);self.assertIs(self.cs[0].stat_dice,self.partners[0].stat_dice)
  rng=self.e.rng.calls;pool=deepcopy(self.cs[0].stat_dice)
  with self.assertRaises(ValueError):self.run_contest(lambda *a:('연속자르기',4))
  self.assertEqual((self.e.rng.calls,self.cs[0].stat_dice),(rng,pool))
 def test_007_actual_ownership_registration_and_availability_before_intro(self):
  changes=[lambda:self.ps[0].spec.update(trainer_id='other'),lambda:setattr(self.ps[0],'captured',True),lambda:setattr(self.ps[0],'on_field',False),lambda:self.native.everyone.remove(self.ts[0]),lambda:self.ps[0].conditions.add('잠듦'),lambda:self.ps[0].spec.update(party_location={'owner_id':'t0','pokemon_id':'p0','location':'storage'})]
  for change in changes:
   self.setUp();change()
   with self.assertRaises(ValueError):self.run_contest()
   self.assertEqual(self.e.rng.calls,0);self.assertEqual(self.total(),0)
 def test_008_callback_changed_owner_registry_and_inplace_learned_moves_no_cost(self):
  changes=[lambda:self.ps[0].spec.update(trainer_id='other'),lambda:self.native.everyone.remove(self.ts[0]),lambda:self.ts[0].moves.remove('move/연속자르기'),lambda:self.ps[0].moves.append('move/たいあたり'),lambda:setattr(self.ps[0],'on_field',False)]
  for change in changes:
   self.setUp();self.checkpoint_first_choice();rng=self.e.rng.calls;pool=deepcopy(self.cs[0].stat_dice);ap=AP.available(self.ts[0])
   def choose(*a):change();return '연속자르기',1
   with self.assertRaises((ValueError,KeyError)):self.run_contest(choose)
   self.assertEqual((self.e.rng.calls,self.cs[0].stat_dice,AP.available(self.ts[0])),(rng,pool,ap));self.assertEqual(self.total(),0)
 def test_009_invalid_order_and_chooser_interrupt_resume_without_intro_replay(self):
  calls=[]
  def order(c,t,r):
   calls.append(c)
   return [t,c] if c is self.cs[0] else []
  with self.assertRaises(ValueError):self.run_contest(order=order)
  rng=self.e.rng.calls;self.assertEqual(len(self.e._paired_run['selections']),1)
  def invalid_again(c,t,r):raise Pause()
  with self.assertRaises(Pause):self.run_contest(order=invalid_again)
  self.assertEqual(self.e.rng.calls,rng)
  n=[0]
  def choose(*a):
   n[0]+=1
   if n[0]==2:raise Pause()
   return '연속자르기',0
  with self.assertRaises(Pause):self.run_contest(choose)
  score=self.partners[0].appeal;seen=[]
  self.run_contest(lambda c,r,a,k:seen.append((c,r)) or ('연속자르기',0))
  self.assertIs(seen[0][0],self.cs[0]);self.assertEqual(len(seen),17);self.assertGreater(score,0)
 def test_010_observed_choice_locks_rng_pool_and_original_contest(self):
  self.checkpoint_first_choice();seen=[]
  def interrupted(first):seen.append(first);raise Pause()
  choose=lambda *a:('연속자르기',1,{'flourish_decision':interrupted})
  with self.assertRaises(Pause):self.run_contest(choose)
  rng=self.e.rng.calls;pool=deepcopy(self.cs[0].stat_dice)
  with self.assertRaises(ValueError):self.run_contest(lambda *a:('연속자르기',0,{'flourish_decision':lambda f:False}))
  with self.assertRaises(ValueError):self.run_contest(choose,identity='different')
  with self.assertRaises(ValueError):self.run_contest(choose,mode='alternating')
  self.assertEqual((self.e.rng.calls,self.cs[0].stat_dice),(rng,pool))
  n=[0]
  def resume(*a):
   n[0]+=1
   if n[0]>1:raise Pause()
   return '연속자르기',1,{'flourish_decision':lambda f:seen.append(f) or False}
  with self.assertRaises(Pause):self.run_contest(resume)
  self.assertEqual(seen[0],seen[1]);self.assertEqual((self.e.rng.calls,self.cs[0].stat_dice),(rng,pool));self.assertFalse(self.e._flourish_used)
  observed=next(iter(self.e._performance_observations.values()))[OBS.KEY];self.assertEqual(observed['state'],'complete')
 def test_011_native_feature_cost_and_frequency_shared_across_pair(self):
  self.checkpoint_first_choice();before=AP.available(self.ts[0]);n=[0]
  def choose(*a):
   n[0]+=1
   return '연속자르기',0,{'flourish_decision':lambda f:True}
  with self.assertRaises(ValueError):self.run_contest(choose)
  self.assertEqual(AP.available(self.ts[0]),before-1);self.assertEqual(len(self.e._flourish_used),1);self.assertEqual(self.ts[0]._action_history,['free'])
  self.assertEqual(self.e._paired_run['performer'],1)
 def test_012_completed_session_cannot_reexecute_under_new_identity(self):
  self.run_contest();before=(self.total(),self.e.rng.calls,deepcopy(self.e.last_standings))
  for uid in ('paired-15','another'):
   with self.assertRaises(ValueError):self.run_contest(identity=uid)
  self.assertEqual((self.total(),self.e.rng.calls,self.e.last_standings),before);self.assertEqual(self.e._paired_run['phase'],'complete')
 def test_013_snapshot_twice_restores_native_cost_and_real_aliases(self):
  self.checkpoint_first_choice('alternating');self.e.snapshot('before');rng=self.e.rng.calls;before=AP.available(self.ts[0])
  for attempt in range(2):
   calls=[0]
   def choose(*a):
    calls[0]+=1
    if calls[0]>1:raise Pause()
    return '연속자르기',1,{'flourish_decision':lambda f:True}
   with self.assertRaises(Pause):self.run_contest(choose,mode='alternating')
   self.assertEqual(AP.available(self.ts[0]),before-1);self.assertTrue(self.e._flourish_used)
   self.e.restore('before',reason='explicit GM correction')
   self.assertEqual(AP.available(self.ts[0]),before);self.assertEqual(self.e.rng.calls,rng);self.assertFalse(self.e._flourish_used)
   for c,t in zip(self.cs,self.partners):
    self.assertIs(c.stat_dice,t.stat_dice);self.assertIs(c._paired_state,t._paired_state)
    binding=self.e._native_intro_bindings[c];self.assertIs(binding[0],self.native);self.assertIn(binding[1],self.ps);self.assertIn(binding[2],self.ts)
   self.assertEqual(self.e._paired_run['slot'],0);self.assertEqual(self.e._paired_run['performer'],0)
 def test_014_pending_snapshot_replays_same_observation_without_new_draw(self):
  self.checkpoint_first_choice();seen=[]
  def wait(f):seen.append(f);raise Pause()
  with self.assertRaises(Pause):self.run_contest(lambda *a:('연속자르기',1,{'flourish_decision':wait}))
  self.e.snapshot('pending');rng=self.e.rng.calls
  for i in range(2):
   calls=[0]
   def choose(*a):
    calls[0]+=1
    if calls[0]>1:raise Pause()
    return '연속자르기',1,{'flourish_decision':lambda f:seen.append(f) or False}
   with self.assertRaises(Pause):self.run_contest(choose)
   self.assertEqual(self.e.rng.calls,rng);self.assertEqual(seen[-1],seen[0]);self.e.restore('pending',reason='GM checkpoint test')
 def test_015_no_nested_run_or_checkpoint_in_public_callback(self):
  self.checkpoint_first_choice();rng=self.e.rng.calls
  def choose(*a):
   with self.assertRaises(ValueError):self.run_contest()
   with self.assertRaises(ValueError):self.e.snapshot('illegal')
   with self.assertRaises(ValueError):self.e.restore('illegal',reason='nested')
   raise Pause()
  with self.assertRaises(Pause):self.run_contest(choose)
  self.assertEqual(self.e.rng.calls,rng)
 def test_016_optional_interactions_require_predeclared_gm_policy(self):
  self.checkpoint_first_choice();rng=self.e.rng.calls
  with self.assertRaises(ValueError):self.run_contest(lambda *a:(self.effects['준비하기'],0,{'pair_interaction':True}))
  self.assertEqual(self.e.rng.calls,rng)
  with self.assertRaises(ValueError):self.e.configure_trainer_interactions(reason='late',double_next_from='준비하기')
 def test_017_gm_double_transfer_is_explicit_and_only_later_own_pokemon(self):
  record=self.e.configure_trainer_interactions(reason='Use Get Ready on own later Pokemon',double_next_from='준비하기')
  self.assertEqual(record['authority'],'table_ruling');n=[0]
  def choose(c,r,a,k):
   n[0]+=1
   if n[0]==1:return self.effects['준비하기'],0,{'pair_interaction':True}
   self.assertIs(c,self.cs[0]);self.assertTrue(c.double_next);self.assertFalse(self.partners[0].double_next);raise Pause()
  with self.assertRaises(Pause):self.run_contest(choose)
  with self.assertRaises(ValueError):self.run_contest(lambda *a:('연속자르기',0,{'pair_interaction':True}))
  self.assertTrue(any('participant interaction' in l for l in self.e.log_lines))
 def test_018_gm_attention_transfer_moves_existing_voltage_and_clamps(self):
  self.e.configure_trainer_interactions(reason='Transfer at most two existing voltage',attention_transfer=2)
  self.checkpoint_first_choice();self.partners[0].excitement=4;self.cs[0].excitement=4
  for c in [*self.cs[1:],*self.partners[1:]]:c.excitement=0
  calls=[0]
  def choose(*a):
   calls[0]+=1
   if calls[0]>1:raise Pause()
   return self.effects['주목 끌기'],0,{'pair_interaction':True}
  with self.assertRaises(Pause):self.run_contest(choose)
  self.assertEqual((self.partners[0].excitement,self.cs[0].excitement),(3,5))
 def test_019_selected_source_required_in_both_native_and_contest(self):
  self.e.r=ContestRules(ROOT,RuleFilter({'exclude_units':[self.e.TRAINER_SOURCE]}))
  with self.assertRaises(ExcludedRuleSelection):self.run_contest()
  self.assertEqual(self.e.rng.calls,0)
 def test_021_order_callback_registry_mutation_is_rejected_before_performance(self):
  self.checkpoint_first_choice();self.e._paired_run['selections']={};rng=self.e.rng.calls
  def order(c,t,r):
   if c is self.cs[0]:self.native.everyone.remove(self.ts[0])
   return [t,c]
  with self.assertRaises(ValueError):self.run_contest(order=order)
  self.assertEqual(self.e.rng.calls,rng);self.assertEqual(self.total(),0)
 def test_022_observed_feature_callback_unavailability_keeps_first_roll_without_cost(self):
  self.checkpoint_first_choice();before=AP.available(self.ts[0]);pool=self.cs[0].stat_dice['근사함']
  def decision(first):self.ps[0].captured=True;return True
  with self.assertRaises(ValueError):self.run_contest(lambda *a:('연속자르기',1,{'flourish_decision':decision}))
  rng=self.e.rng.calls;self.assertEqual(AP.available(self.ts[0]),before);self.assertFalse(self.e._flourish_used)
  self.assertEqual(self.cs[0].stat_dice['근사함'],pool-1);self.assertIsNotNone(self.e._paired_run['pending'])
  self.ps[0].captured=False;n=[0]
  def choose(*a):
   n[0]+=1
   if n[0]>1:raise Pause()
   return '연속자르기',1,{'flourish_decision':lambda f:False}
  with self.assertRaises(Pause):self.run_contest(choose)
  self.assertEqual(self.e.rng.calls,rng);self.assertEqual(AP.available(self.ts[0]),before)
 def test_020_smart_mapping_stays_explicit_partial_and_other_stats_native(self):
  p=self.ps[0];p.stats.update(atk=23,def_=4);p.stats['def']=5;p.stats['spd']=25;p.stats['spa']=9;p.stats['spe']=50
  with self.assertRaises(UnresolvedRuleSelection):self.e.stat_pool_from_combatant(p)
  literal=self.e.stat_pool_from_combatant(p,smart_stat_policy='ptk-literal-defense');original=self.e.stat_pool_from_combatant(p,smart_stat_policy='ptu-original-special-defense')
  self.assertEqual((literal['슬기로움'],original['슬기로움']),(0,2));self.assertEqual(literal['근사함'],5)
  self.assertEqual({k:v for k,v in literal.items() if k!='슬기로움'},{k:v for k,v in original.items() if k!='슬기로움'})
if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths={str(p.relative_to(ROOT)).replace('\\','/') for folder,pattern in [('engine','*.py'),('data','*.json')] for p in (ROOT/folder).glob(pattern)}
 paths.update(['tools/test_category3_batch15_contest.py','output/entities/moves.json','output/ruleunits.jsonl','input/ch08-contests.md','input/ch03-skills-edges-feats.md','input/ch04-trainer-classes.md','output/source-audit/2026-10-10/ptu-core-1.05.pdf'])
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':['DOMAIN-048'],'partial_scope':['DOMAIN-037'],'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)},'source_review':{'completed':'ch08-contests:273–283, full fixed trainer participation scope','partial':'DOMAIN037: PTK ch08:26 Defense vs PTU 1.05 PDF p262 Special Defense to Smart. Explicit policy is not source conflict resolution; no completed claim.','optional_examples':'ch08:281 explicitly allows GM alteration. Optional interactions are predeclared table rulings; no source authority promotion or automatic ordinary-effect rewriting.'}}
 (ROOT/'output/category3-batch15-contest-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 raise SystemExit(not result.wasSuccessful())
