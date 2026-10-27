import sys,copy,json,hashlib,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from test_league_runtime import L, A
import test_league_runtime as _fixture_test_league_runtime
class Independent(unittest.TestCase):
 @classmethod
 def setUpClass(cls):_fixture_test_league_runtime.Tests.setUpClass();cls.f=_fixture_test_league_runtime.Tests()
 def test_01_declare_changes_only_agenda_and_intent(self):
  e,c=self.f.start();rng=e.rng.getstate();states={k:copy.deepcopy(v.spec) for k,v in c.items()};rights=e._league_runtime['agenda'].turn_rights
  self.f.declarations(e)
  self.assertEqual({k:v.spec for k,v in c.items()},states);self.assertEqual(e.rng.getstate(),rng);self.assertEqual(e._league_runtime['agenda'].turn_rights,rights)
  self.assertEqual((e.elapsed_seconds,e._active_turn_actor,e._turn_closures),(0,None,[]))
 def test_02_mode_and_existing_round_reject_before_boundary_mutation(self):
  e,c,pairs=self.f.fixture()
  with self.assertRaises(ValueError):e.start_league(pairs,mode='full_contact')
  e.start_round(list(c.values()));before=(e.round_no,e.elapsed_seconds,e.round_start_seconds)
  with self.assertRaises(ValueError):e.start_league(pairs,mode='league')
  self.assertEqual((e.round_no,e.elapsed_seconds,e.round_start_seconds),before);self.assertIsNone(e._league_runtime)
 def test_03_raw_use_move_on_rejects_before_roster_frequency_mutation(self):
  e,c=self.f.start();roster=list(e.everyone);spec=copy.deepcopy(c['a:pokemon'].spec)
  with self.assertRaises(ValueError):e.use_move_on(c['a:pokemon'],c['b:pokemon'],'struggle',[c['a:pokemon'],c['b:pokemon']])
  self.assertEqual(e.everyone,roster);self.assertEqual(c['a:pokemon'].spec,spec)
  self.assertEqual(e.league_declare('a:trainer',{'kind':'no_action'})['status'],'ready')
 def test_04_normal_actual_turns_and_resources(self):
  e,c=self.f.start();self.f.trainers(e)
  self.assertEqual([r['actor'] for r in e._turn_closures],[c['b:trainer'],c['a:trainer']])
  self.assertFalse(any(p.get('producer')=='Engine.use_move.native_standard' for p in e._heavy_events.values()))
  result=e.league_step(pokemon_intent=self.f.move());self.assertEqual(result['status'],'ready')
  self.assertEqual((c['b:pokemon'].hp,c['a:pokemon'].budget['standard'],c['a:pokemon'].move_uses),(99,0,{'struggle':1}))
  e.league_step(pokemon_intent={'kind':'no_action'});e.league_complete_round()
  self.assertEqual(e.elapsed_seconds,10);self.assertEqual([x.spec['frequency_state']['turn'] for x in c.values()],[1]*4)
  self.assertEqual(len(e._turn_closures),4);self.assertEqual(c['b:pokemon'].move_uses,{})
 def test_05_miss_is_consumed_use_not_refusal(self):
  e,c=self.f.start();e.rng.seed(31);self.f.trainers(e)
  r=e.league_step(pokemon_intent=self.f.move());self.assertEqual(r['status'],'ready');self.assertEqual(c['b:pokemon'].hp,110)
  self.assertEqual(c['a:pokemon'].move_uses,{'struggle':1});self.assertEqual(len(e._turn_closures),3)
 def test_06_both_static_unavailable_directions_keep_partner(self):
  for key in ('a:trainer','b:pokemon'):
   e,c,pairs=self.f.fixture();e.gm.set_hp(c[key],value=0,reason='independent fixture pre-existing faint')
   e.start_league(pairs,mode='league');rights=e._league_runtime['agenda'].turn_rights;self.f.finish(e)
   self.assertEqual(e._league_runtime['agenda'].turn_rights,rights);self.assertEqual(len(e._turn_closures),4);self.assertEqual(c[key].move_uses,{})
 def test_07_public_gm_faint_invalidates_before_execution(self):
  e,c=self.f.start();self.f.declarations(e);e.gm.set_hp(c['b:trainer'],value=0,reason='external state update')
  r=e.league_step();self.assertEqual(r['status'],'incomplete');self.assertEqual(e._turn_closures,[]);self.assertEqual(len(e._league_runtime['agenda'].turn_rights),4)
 def test_08_damage_faint_keeps_prefix_and_partial_round(self):
  e,c,pairs=self.f.fixture();c['b:pokemon'].hp=8;e.start_league(pairs,mode='league');self.f.trainers(e)
  r=e.league_step(pokemon_intent=self.f.move());self.assertEqual(r['status'],'incomplete');self.assertLessEqual(c['b:pokemon'].hp,0)
  self.assertEqual(c['a:pokemon'].move_uses,{'struggle':1});self.assertIs(e._active_turn_actor,c['a:pokemon']);self.assertEqual(len(e._turn_closures),2);self.assertEqual(e.elapsed_seconds,0)
  self.assertEqual(len(e._league_runtime['agenda'].records),4);self.assertNotIn('winner',r)
 def test_09_heavy_pending_retries_preserve_actual_prefix(self):
  e,c,pairs=self.f.fixture();c['b:pokemon'].hp=50;c['b:pokemon'].injuries=5;e.start_league(pairs,mode='league');self.f.trainers(e)
  e.league_step(pokemon_intent=self.f.move());event=e._heavy_pending;before=(c['b:pokemon'].hp,dict(c['a:pokemon'].move_uses),e.elapsed_seconds,len(e._turn_closures),e.rng.getstate())
  self.assertEqual(before[:4],(39,{'struggle':1},0,2))
  for action in (lambda:e.league_step(pokemon_intent=self.f.move()),e.league_complete_round,e.next_league_round,e.end_league):
   with self.assertRaises(L.LeaguePending):action()
  self.assertEqual((c['b:pokemon'].hp,c['a:pokemon'].move_uses,e.elapsed_seconds,len(e._turn_closures),e.rng.getstate()),before);self.assertEqual(e._heavy_pending,event)
 def test_10_before_league_snapshot_restores_initial_fields(self):
  e,c,pairs=self.f.fixture();e.everyone=e.gm.everyone=list(c.values());e.gm.snapshot('before')
  e.start_league(pairs,mode='league');self.f.declarations(e);e.league_step();e.gm.restore('before')
  self.assertEqual((e._league_runtime,e._turn_closures,e._ordinary_turn_rounds,e.round_no,e.elapsed_seconds),(None,[],{},0,0));self.assertTrue(all(getattr(x,'budget',None) is None for x in c.values()))
 def test_11_post_declaration_snapshot_restores_intent_and_last_target(self):
  e,c=self.f.start();self.f.trainers(e);e.gm.snapshot('beforeattack');before_rng=e.rng.getstate();e.league_step(pokemon_intent=self.f.move());e.gm.restore('beforeattack')
  self.assertIs(e._league_runtime['actors']['a:pokemon'],c['a:pokemon']);self.assertIs(e._league_runtime['close_receipts'][0]['actor'],c['b:trainer'])
  self.assertIsNone(c['a:pokemon'].last_target);self.assertEqual(c['b:pokemon'].hp,110);self.assertEqual(c['a:pokemon'].move_uses,{})
  self.assertEqual(e.rng.getstate(),before_rng) # GM snapshot v2 replays the saved RNG state
  self.assertEqual(e.league_status()['next'],(A.Phase.POKEMON,'a:pokemon'))
 def test_12_pending_snapshot_preserves_ledger_and_actor_identity(self):
  e,c,pairs=self.f.fixture();c['b:pokemon'].hp=50;c['b:pokemon'].injuries=5;e.start_league(pairs,mode='league');self.f.trainers(e);e.league_step(pokemon_intent=self.f.move());e.gm.snapshot('pending');e.gm.restore('pending')
  self.assertIs(e._heavy_events[e._heavy_pending]['target'],c['b:pokemon']);self.assertIs(e._active_turn_actor,c['a:pokemon']);self.assertEqual(c['b:pokemon'].hp,39)
  with self.assertRaises(L.LeaguePending):e.league_step(pokemon_intent={'kind':'no_action'})
 def test_13_round_clock_once_and_next_start_not_implicit_close(self):
  e,c=self.f.start();self.f.finish(e)
  with self.assertRaises(ValueError):e.league_complete_round()
  e.next_league_round();self.assertEqual((e.round_no,e.elapsed_seconds),(2,10));self.f.finish(e);self.assertEqual(e.elapsed_seconds,20)
 def test_14_unsupported_pokemon_producer_does_not_open_turn(self):
  e,c=self.f.start();self.f.trainers(e);intent=self.f.move();intent['move_id']='move/불꽃세례';r=e.league_step(pokemon_intent=intent)
  self.assertEqual(r['status'],'incomplete');self.assertIsNone(e._active_turn_actor);self.assertEqual(len(e._turn_closures),2);self.assertEqual(c['a:pokemon'].move_uses,{})
 def test_15_declaration_replacement_and_unknown_target_are_not_executed(self):
  e,c=self.f.start();self.f.declarations(e)
  with self.assertRaises(ValueError):e.league_step(pokemon_intent=self.f.move())
  self.assertEqual(e._turn_closures,[]);e.league_step();e.league_step()
  r=e.league_step(pokemon_intent=self.f.move('unknown'));self.assertEqual(r['status'],'incomplete');self.assertEqual(c['a:pokemon'].move_uses,{})
 def test_16_end_requires_complete_and_does_not_infer_winner(self):
  e,c=self.f.start()
  with self.assertRaises(ValueError):e.end_league()
  self.f.finish(e);r=e.end_league();self.assertEqual(r['status'],'encounter_ended_by_caller');self.assertIsNone(r['winner']);self.assertEqual(e.elapsed_seconds,10)
 def test_17_completed_round_roster_change_is_not_silently_replaced(self):
  e,c=self.f.start();self.f.finish(e);e.everyone.pop();observed=list(e.everyone)
  r=e.next_league_round();self.assertEqual(r['status'],'incomplete')
  self.assertEqual(e.everyone,observed);self.assertEqual((e.round_no,e.elapsed_seconds),(1,10));self.assertIsNone(e.round_start_seconds)
 def test_18_passive_damage_history_does_not_admit_active_or_malformed_state(self):
  import conditional_damage_base as DB,attack_damage_history as HISTORY
  cases=('active_streak','pending_setup','malformed_round','unknown_attacker','malformed_streaks','missing_receipt','unknown_condition')
  for kind in cases:
   with self.subTest(kind=kind):
    e,c=self.f.start();self.f.trainers(e)
    self.assertEqual(e.league_step(pokemon_intent=self.f.move())['status'],'ready')
    target=c['b:pokemon'];state=target.custom_conditions[DB.STATE]
    if kind=='active_streak':state['streaks']['struggle']={'successes':1}
    elif kind=='pending_setup':state['pending_setup']={'move_id':'struggle'}
    elif kind=='malformed_round':state['damage_round']=True
    elif kind=='unknown_attacker':state['damaged_by']['unregistered']=e.round_no
    elif kind=='malformed_streaks':state['streaks']=[]
    elif kind=='missing_receipt':target.spec[HISTORY.KEY]=[]
    else:target.custom_conditions['unknown_optional_effect']=True
    before=(target.hp,dict(c['a:pokemon'].move_uses),len(e._turn_closures),e.elapsed_seconds)
    result=e.league_step(pokemon_intent={'kind':'no_action'})
    self.assertEqual(result['status'],'incomplete')
    self.assertIn('b:pokemon:unsupported custom_conditions',result['pending']['evidence'])
    self.assertIsNone(e._active_turn_actor)
    self.assertEqual((target.hp,c['a:pokemon'].move_uses,len(e._turn_closures),e.elapsed_seconds),before)
class Results(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'LEAGUE-INDEPENDENT-'+t._testMethodName,'status':'pass'})
 def addFailure(self,t,err):super().addFailure(t,err);self.rows.append({'id':'LEAGUE-INDEPENDENT-'+t._testMethodName,'status':'fail','detail':self._exc_info_to_string(err,t)})
 def addError(self,t,err):super().addError(t,err);self.rows.append({'id':'LEAGUE-INDEPENDENT-'+t._testMethodName,'status':'error','detail':self._exc_info_to_string(err,t)})
if __name__=='__main__':
 import builtins,io
 reads=set()
 def tracing(original):
  def opened(file,mode='r',*args,**kwargs):
   if 'r' in mode or '+' in mode:
    try:
     p=Path(file).resolve()
     if p.is_relative_to(ROOT) and p.is_file():reads.add(p)
    except (ValueError,TypeError,OSError):pass
   return original(file,mode,*args,**kwargs)
  return opened
 old_open,old_io=builtins.open,io.open;builtins.open,io.open=tracing(old_open),tracing(old_io)
 try:result=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
 finally:builtins.open,io.open=old_open,old_io
 paths=set(reads)|{Path(__file__).resolve(),ROOT/'tests/test_league_runtime.py',ROOT/'input/ch07-combat.md',ROOT/'input/ch11-running-the-game.md'}
 paths.update((ROOT/'data/verification').glob('common-league*.json'))
 for module in list(sys.modules.values()):
  file=getattr(module,'__file__',None)
  if file:
   path=Path(file).resolve()
   if path.is_relative_to(ROOT/'engine') and path.suffix=='.py':paths.add(path)
 report={'tests_run':result.testsRun,'results':result.rows,'input_hashes':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},'semantic_closure':False,'scope':'Restricted actual League integration: native production, independent role rights, pending, lifecycle/clock and snapshot identity. Not whole League or arbitrary Python tamper proof.','source_evidence_destination':'data/verification/common-league*.json; author sandbox evidence/ copies are historical drafting location'}
 output=ROOT/'output/league-runtime-independent-tests.json';output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
