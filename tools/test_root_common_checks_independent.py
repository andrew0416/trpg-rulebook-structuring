"""Independent ordinary-check source oracles on a synthetic-admitted real root Runtime.
This does not certify source admission or the live Engine projection bridge.
"""
import sys,json,hashlib,unittest,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from engine import root_common_checks as C,root_machine as M,root_admission as A,root_inputs as I
from common_check_fixture import setup as author_setup,actor

def req(d,ids=('a',),outcomes=None):
 return dict(intent='Attempt the recorded ordinary task',actors=list(ids),decisions=[d],outcomes=outcomes or [dict(outcome='success',description='Success'),dict(outcome='failure',description='Failure'),dict(outcome='other',description='Recorded')],context_obligations=[],modifier_policy='none')
def env(d=None,actors=None,requests=None,config_changes=None):
 d=d or dict(mode='dc',skill='athletics',dc=7)
 s,p,cfg=author_setup(d,actors,requests)
 if config_changes:
  cfg.update(config_changes)
  current=M.thaw(s.runtime.machine.state.game['actors'])
  s=C.CheckSession(A.Runtime(s.runtime.registry,M.Machine(C.initial_snapshot('a'*64,current,cfg)),principals=tuple(p.values())),s.registration)
 return s,p,cfg

def begin(s,key='check',eid='e'):
 t=s.begin(eid,key);assert type(t) is A.Ticket,t
 o=s.submit(t);assert o.tag=='AwaitingInput',o
 return t

def ans(s,t,p,value):
 q=s.pending(t);assert type(q) is A.PendingInput,q
 return s.answer(q,p,value)
def select(s,p,t,d):return ans(s,t,p['gm'],d)
def response(s,p,t,name='success'):
 q=s.pending(t);val=next(x for x in q.request.domain if x['outcome']==name);return s.answer(q,p['gm'],val)
def ex(interval='one',limited=True,dc=10,**kw):
 d=dict(mode='extended',skill='athletics',dc=dc,complexity=2,limited=limited,task_id='task',interval_id=interval,interval=dict(amount=1,unit='hour'));d.update(kw);return d

def run_interval(s,p,d,key,eid,faces,name='other'):
 t=begin(s,key,eid);o=select(s,p,t,d)
 if faces is not None:o=ans(s,t,p['a'],faces)
 if o.tag=='AwaitingInput':
  raw=s.result(eid)['raw'];name=('success' if raw['status']=='complete' else 'failure' if raw['status']=='exhausted' else name)
  o=response(s,p,t,name)
 return t,o

class Independent(unittest.TestCase):
 def test_01_no_roll_positive_has_no_randomness(self):
  for reason in ['trivial','uninteresting_failure']:
   d=dict(mode='no_roll',reason=reason);s,p,_=env(d);t=begin(s);select(s,p,t,d);q=s.pending(t);self.assertIs(type(q.request),I.ChoiceRequest);self.assertEqual(response(s,p,t).tag,'Completed');self.assertEqual(s.result('e')['rolls'],());self.assertFalse(s.result('e')['world_effects_applied'])
 def test_02_player_cannot_choose_GM_branch(self):
  d=dict(mode='no_roll',reason='trivial');s,p,_=env(d);t=begin(s);q=s.pending(t);before=s.runtime.machine.state;self.assertNotEqual(s.answer(q,p['a'],d).tag,'Completed');self.assertIs(s.runtime.machine.state,before);self.assertEqual(s.answer(q,p['gm'],d).tag,'AwaitingInput')
 def test_03_dc_equal_and_below(self):
  for dc,passed in [(7,True),(8,False)]:
   d=dict(mode='dc',skill='athletics',dc=dc);s,p,_=env(d);t=begin(s);select(s,p,t,d);ans(s,t,p['a'],[3,4]);raw=s.result('e')['raw'];self.assertEqual((raw['total'],raw['margin'],raw['passed']),(7,7-dc,passed));self.assertEqual(response(s,p,t,'success' if passed else 'failure').tag,'Completed')
 def test_04_base_ranks_exact_ordered_count(self):
  for rank in range(1,7):
   s,p,cfg=env(actors={'a':actor(rank)});t=begin(s);select(s,p,t,cfg['requests']['check']['decisions'][0]);q=s.pending(t);self.assertEqual((q.request.count,q.request.sides),(rank,6));faces=[1+(x%6)for x in range(rank)];s.answer(q,p['a'],faces);self.assertEqual(s.result('e')['rolls'][0]['faces'],tuple(faces))
 def test_05_default2_only_complete_catalog_missing(self):
  d=dict(mode='dc',skill='survival',dc=7)
  s,p,_=env(d,actors={'a':actor(6)});t=begin(s);select(s,p,t,d);self.assertEqual(s.pending(t).request.count,2)
  a=actor();a['ordinary_default']=False;s,p,_=env(d,actors={'a':a});t=begin(s);self.assertEqual(select(s,p,t,d).tag,'Blocked');self.assertIsNone(s.result('e'))
 def test_06_unknown_rank_and_invalid_base_not_default(self):
  a=actor();a['skills']['athletics']=None;s,p,cfg=env(actors={'a':a});t=begin(s);self.assertEqual(select(s,p,t,cfg['requests']['check']['decisions'][0]).tag,'Blocked')
  for rank in [True,0,7]:
   with self.assertRaises(ValueError):env(actors={'a':actor(rank)})
 def test_07_dice_bad_faces_count_type_no_fallback(self):
  s,p,cfg=env();t=begin(s);select(s,p,t,cfg['requests']['check']['decisions'][0]);q=s.pending(t);before=s.runtime.machine.state
  for bad in [[True,3],[0,3],[7,3],[3],[3,4,5],7]:
   self.assertIsInstance(s.answer(q,p['a'],bad),A.Finding);self.assertIs(s.runtime.machine.state,before)
  self.assertEqual(s.answer(q,p['a'],[3,4]).tag,'AwaitingInput')
 def test_08_penalty_separate_more_than_pool_negative(self):
  d=dict(mode='dc',skill='athletics',dc=1,penalty_count=3);s,p,_=env(d);t=begin(s);select(s,p,t,d);self.assertEqual(s.pending(t).request.count,2);ans(s,t,p['a'],[1,1]);q=s.pending(t);self.assertEqual(q.request.count,3);s.answer(q,p['a'],[6,6,6]);self.assertEqual(s.result('e')['raw']['total'],-16);self.assertEqual(s.result('e')['rolls'][0]['faces'],(1,1))
 def test_09_zero_penalty_no_extra_dice(self):
  s,p,cfg=env();t=begin(s);select(s,p,t,cfg['requests']['check']['decisions'][0]);ans(s,t,p['a'],[3,4]);self.assertIs(type(s.pending(t).request),I.ChoiceRequest)
 def test_10_opposed_tie_and_both_orders(self):
  for a,b,win in [([3,3],[2,2,2],'defender'),([4,4],[2,2,2],'challenger'),([1,1],[2,2,2],'defender')]:
   d=dict(mode='opposed',skill='athletics');s,p,_=env(d,requests={'check':req(d,['a','b'])});t=begin(s);select(s,p,t,d);ans(s,t,p['a'],a);ans(s,t,p['b'],b);self.assertEqual(s.result('e')['raw']['winner'],win)
 def test_11_opponent_roll_requires_own_principal(self):
  d=dict(mode='opposed',skill='athletics');s,p,_=env(d,requests={'check':req(d,['a','b'])});t=begin(s);select(s,p,t,d);ans(s,t,p['a'],[3,3]);q=s.pending(t);before=s.runtime.machine.state;self.assertIsInstance(s.answer(q,p['a'],[2,2,2]),A.Finding);self.assertIs(s.runtime.machine.state,before);s.answer(q,p['b'],[2,2,2]);self.assertEqual(s.result('e')['raw']['winner'],'defender')
 def test_12_team_required_count_and_equality(self):
  d=dict(mode='team',skill='athletics',dc=5,required_people=3,equal_contribution=True,no_main_actor=True)
  for b,passed in [([2,3,3],True),([2,2,3],False)]:
   s,p,_=env(d,requests={'check':req(d,['a','b'])});t=begin(s);select(s,p,t,d);ans(s,t,p['a'],[3,4]);ans(s,t,p['b'],b);raw=s.result('e')['raw'];self.assertEqual(raw['dc'],15);self.assertEqual(raw['passed'],passed)
 def test_13_team_scope_guards_required(self):
  d=dict(mode='team',skill='athletics',dc=5,required_people=3,equal_contribution=True,no_main_actor=True)
  for k in ['equal_contribution','no_main_actor']:
   bad=dict(d);bad[k]=False
   with self.assertRaises(ValueError):env(bad,requests={'check':req(bad,['a','b'])})
 def test_14_helper_novice_floor_single_primary(self):
  d=dict(mode='dc',skill='athletics',dc=7,helper_id='helper')
  for rank,bonus in [(3,1),(4,2),(5,2),(6,3)]:
   s,p,_=env(d,actors={'a':actor(2),'helper':actor(rank)});t=begin(s);select(s,p,t,d);self.assertEqual(s.pending(t).request.count,2);ans(s,t,p['a'],[2,3]);self.assertEqual(s.result('e')['raw']['total'],5+bonus);self.assertIs(type(s.pending(t).request),I.ChoiceRequest)
 def test_15_helper_below_novice_or_unknown_no_roll(self):
  d=dict(mode='dc',skill='athletics',dc=7,helper_id='helper')
  for rank in [1,2,None]:
   s,p,_=env(d,actors={'a':actor(2),'helper':actor(rank)});t=begin(s);self.assertEqual(select(s,p,t,d).tag,'Blocked');self.assertIsNone(s.result('e'))
 def test_16_high_margin_no_auto_benefit(self):
  d=dict(mode='dc',skill='athletics',dc=2);s,p,_=env(d);t=begin(s);select(s,p,t,d);ans(s,t,p['a'],[6,6]);self.assertEqual(s.result('e')['raw']['margin'],10);self.assertIsNone(s.result('e')['narrative']);self.assertFalse(s.result('e')['costs_applied']);self.assertFalse(s.result('e')['world_effects_applied'])
 def test_17_raw_fail_preserved_after_success_with_cost(self):
  d=dict(mode='dc',skill='athletics',dc=8);s,p,_=env(d);t=begin(s);select(s,p,t,d);ans(s,t,p['a'],[3,4]);self.assertEqual(response(s,p,t,'success_with_cost').tag,'Completed');r=s.result('e');self.assertFalse(r['raw']['passed']);self.assertEqual(r['narrative']['outcome'],'success_with_cost');self.assertFalse(r['costs_applied'])
 def test_18_missing_cost_or_margin_acceptance_pending(self):
  d=dict(mode='dc',skill='athletics',dc=8)
  for outcome in [dict(outcome='success_with_cost',description='Cost missing',failure_margin_accepted=True),dict(outcome='success_with_cost',description='Narrow unapproved',cost='1 item')]:
   s,p,_=env(d,requests={'check':req(d,outcomes=[outcome])});t=begin(s);select(s,p,t,d);ans(s,t,p['a'],[3,4]);self.assertEqual(ans(s,t,p['gm'],outcome).tag,'Blocked');self.assertIsNone(s.result('e')['narrative'])
 def test_19_extended_last_equality_success(self):
  d1=ex('one');d2=ex('two');s,p,_=env(actors={'a':actor(4)},requests={'one':req(d1),'two':req(d2)});run_interval(s,p,d1,'one','e1',[2,2,2,2]);run_interval(s,p,d2,'two','e2',[3,3,3,3]);r=s.result('e2')['raw'];self.assertEqual((r['total'],r['dc'],r['status'],r['attempts_used'],r['attempt_limit']),(20,20,'complete',2,2))
 def test_20_extended_exhausted_and_terminal_extra_roll(self):
  ds=[ex(x) for x in ['one','two','three']];s,p,_=env(actors={'a':actor(4)},requests={d['interval_id']:req(d)for d in ds});run_interval(s,p,ds[0],'one','e1',[2,2,2,2]);run_interval(s,p,ds[1],'two','e2',[2,3,3,3]);self.assertEqual(s.result('e2')['raw']['status'],'exhausted');t=begin(s,'three','e3');self.assertEqual(select(s,p,t,ds[2]).tag,'Blocked');self.assertIsNone(s.result('e3'));self.assertEqual(s.runtime.machine.state.game['domains']['common_checks']['tasks']['task']['total'],19)
 def test_21_extended_rank1_zero_limit_no_dice(self):
  d=ex();s,p,_=env(d,actors={'a':actor(1)});t=begin(s);select(s,p,t,d);self.assertIs(type(s.pending(t).request),I.ChoiceRequest);r=s.result('e')['raw'];self.assertEqual((r['attempt_limit'],r['attempts_used'],r['status']),(0,0,'exhausted'))
 def test_22_unlimited_negative_not_guaranteed_convergence(self):
  ds=[ex(x,limited=False,penalty_count=2)for x in ['one','two']];s,p,_=env(actors={'a':actor(1)},requests={d['interval_id']:req(d)for d in ds})
  for n,d in enumerate(ds):
   t=begin(s,d['interval_id'],'e'+str(n));select(s,p,t,d);ans(s,t,p['a'],[1]);ans(s,t,p['a'],[6,6]);response(s,p,t,'other')
  r=s.result('e1')['raw'];self.assertEqual((r['total'],r['status'],r['attempt_limit']),(-22,'in_progress',None))
 def test_23_duplicate_interval_new_event_no_reconsume(self):
  d=ex();s,p,_=env(d,actors={'a':actor(4)});run_interval(s,p,d,'check','e1',[1,1,1,1]);t=begin(s,'check','e2');self.assertEqual(select(s,p,t,d).tag,'Blocked');self.assertEqual(s.runtime.machine.state.game['domains']['common_checks']['tasks']['task']['total'],4)
 def test_24_task_changed_parameters_pending(self):
  d1=ex('one');d2=ex('two',dc=11);s,p,_=env(actors={'a':actor(4)},requests={'one':req(d1),'two':req(d2)});run_interval(s,p,d1,'one','e1',[1,1,1,1]);t=begin(s,'two','e2');self.assertEqual(select(s,p,t,d2).tag,'Blocked')
 def test_25_extended_in_combat_no_roll(self):
  d=ex();s,p,_=env(d,config_changes={'combat_active':True});t=begin(s);self.assertEqual(select(s,p,t,d).tag,'Blocked');self.assertIsNone(s.result('e'))
 def test_26_clock_and_world_not_falsely_applied(self):
  d=ex();s,p,_=env(d,actors={'a':actor(4)});run_interval(s,p,d,'check','e',[1,1,1,1]);r=s.result('e');self.assertFalse(r['owed_intervals'][0]['applied_to_clock']);self.assertEqual(s.runtime.machine.state.game['clock'],{});self.assertEqual(r['completion_scope'],'check_and_adjudication_record_only')
 def test_27_input_replay_idempotent_conflict_rejected(self):
  s,p,cfg=env();t=begin(s);select(s,p,t,cfg['requests']['check']['decisions'][0]);q=s.pending(t);o=s.answer(q,p['a'],[3,4]);before=s.runtime.machine.state;self.assertEqual(s.answer(q,p['a'],[3,4]),o);self.assertIs(s.runtime.machine.state,before);self.assertIsInstance(s.answer(q,p['a'],[4,4]),A.Finding)
 def test_28_stale_snapshot_rejects_authenticated_input(self):
  s,p,cfg=env();t=begin(s);select(s,p,t,cfg['requests']['check']['decisions'][0]);q=s.pending(t);st=s.runtime.machine.state;s.runtime.machine.state=M.Snapshot(st.profile,st.revision,st.game,st.occurrences,st.children);self.assertIsInstance(s.answer(q,p['a'],[3,4]),A.Finding);self.assertIsNone(s.result('e'))
 def test_29_payload_cannot_spoof_DC_or_actor(self):
  s,p,_=env();st=s.runtime.machine.state;e=M.Event('spoof',C.EVENT_KIND,st.profile,st.revision,{'request_key':'check','dc':1,'actors':['helper']});out=s.runtime.prepare(s.registration,e);self.assertIsInstance(out,A.Finding);self.assertIsNone(s.result('spoof'))
 def test_30_synthetic_never_source_ready(self):
  s,p,_=env();t=begin(s);self.assertEqual(t.tag,'ModelAdmitted');self.assertNotEqual(t.tag,'SourceReady')
 def test_31_unresolved_context_not_GM_yes(self):
  d=dict(mode='dc',skill='athletics',dc=7);r=req(d);r['context_obligations']=['special effect not resolved'];s,p,_=env(d,requests={'check':r});self.assertIsInstance(s.begin('e','check'),A.Finding);self.assertIsNone(s.result('e'))
 def test_32_status_or_modifier_scope_held(self):
  for k,v in [('conditions',['paralysis']),('injuries',1),('modifier_sources',['equipment']),('fainted',True)]:
   a=actor();a[k]=v;s,p,_=env(actors={'a':a});self.assertIsInstance(s.begin('e','check'),A.Finding)
 def test_33_finite_domain_unknown_choice_rejected(self):
  s,p,_=env();t=begin(s);q=s.pending(t);before=s.runtime.machine.state;self.assertIsInstance(s.answer(q,p['gm'],dict(mode='dc',skill='athletics',dc=999)),A.Finding);self.assertIs(s.runtime.machine.state,before)
 def test_34_new_occurrence_same_request_is_distinct(self):
  s,p,cfg=env();d=cfg['requests']['check']['decisions'][0]
  for e in ['e1','e2']:
   t=begin(s,eid=e);select(s,p,t,d);ans(s,t,p['a'],[3,4]);self.assertEqual(response(s,p,t).tag,'Completed')
  self.assertIsNotNone(s.result('e1'));self.assertIsNotNone(s.result('e2'))
 def test_35_same_occurrence_begin_replays_without_new_roll(self):
  s,p,cfg=env();d=cfg['requests']['check']['decisions'][0];t=begin(s);select(s,p,t,d);ans(s,t,p['a'],[3,4]);response(s,p,t);before=s.runtime.machine.state;t2=s.begin('e','check');self.assertIs(type(t2),A.Ticket);self.assertEqual(s.submit(t2).tag,'Completed');self.assertIs(s.runtime.machine.state,before)
 def test_36_exhausted_task_cannot_be_unconditional_success(self):
  d=ex();s,p,_=env(d,actors={'a':actor(2)});t=begin(s);select(s,p,t,d);ans(s,t,p['a'],[1,1]);self.assertEqual(s.result('e')['raw']['status'],'exhausted');self.assertNotEqual(response(s,p,t,'success').tag,'Completed');self.assertIsNone(s.result('e')['narrative'])
 def test_37_losing_challenger_cannot_be_unconditional_success(self):
  d=dict(mode='opposed',skill='athletics');s,p,_=env(d,requests={'check':req(d,['a','b'])});t=begin(s);select(s,p,t,d);ans(s,t,p['a'],[1,1]);ans(s,t,p['b'],[2,2,2]);self.assertEqual(s.result('e')['raw']['winner'],'defender');self.assertNotEqual(response(s,p,t,'success').tag,'Completed')

 def test_38_opposed_different_skills_and_ranks(self):
  d=dict(mode='opposed',skills={'a':'athletics','b':'survival'});a=actor(2);a['skills']['survival']=6;b=actor(6);b['skills']['survival']=3
  s,p,_=env(d,actors={'a':a,'b':b},requests={'check':req(d,['a','b'])});t=begin(s);select(s,p,t,d);self.assertEqual(s.pending(t).request.count,2);ans(s,t,p['a'],[3,3]);self.assertEqual(s.pending(t).request.count,3);ans(s,t,p['b'],[2,2,2]);self.assertEqual(s.result('e')['raw']['winner'],'defender');self.assertEqual(response(s,p,t,'failure').tag,'Completed')
 def test_39_opposed_skill_map_exact_actor_keys_and_catalog(self):
  for skills in [{'a':'athletics'},{'a':'athletics','b':'survival','helper':'athletics'},{'a':'athletics','b':'unknown'}]:
   d=dict(mode='opposed',skills=skills)
   with self.assertRaises(ValueError):env(d,requests={'check':req(d,['a','b'])})
 def test_40_opposed_skill_shorthand_cannot_conflict(self):
  d=dict(mode='opposed',skill='athletics',skills={'a':'athletics','b':'survival'})
  with self.assertRaises(ValueError):env(d,requests={'check':req(d,['a','b'])})

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Independent)
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='COMMON-CHECK-INDEPENDENT-'+t._testMethodName,status='pass'))
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='COMMON-CHECK-INDEPENDENT-'+t._testMethodName,status='fail',detail=self._exc_info_to_string(e,t)))
  def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='COMMON-CHECK-INDEPENDENT-'+t._testMethodName,status='error',detail=self._exc_info_to_string(e,t)))
 result=unittest.TextTestRunner(verbosity=1,resultclass=Result).run(suite)
 files=list((ROOT/'engine').glob('root_*.py'))+[ROOT/'engine/common_checks.py',Path(__file__),ROOT/'tools/common_check_fixture.py',ROOT/'tools/common_check_synthetic_evidence.txt',ROOT/'output/common-check-independent-plan.json']
 report=dict(scope='Synthetic-admitted actual root Runtime common-check interface; source admission and live Engine bridge not certified',results=result.rows,input_hashes={str(p.relative_to(ROOT)).replace(chr(92),'/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()},summary=dict(total=result.testsRun,passed=sum(x['status']=='pass'for x in result.rows),failed=len(result.failures),errors=len(result.errors)),whole_source_complete=False)
 (ROOT/'output/root-common-check-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');sys.exit(not result.wasSuccessful())
