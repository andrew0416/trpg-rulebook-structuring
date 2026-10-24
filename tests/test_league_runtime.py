import sys,pathlib,unittest,json,hashlib,copy,builtins,io
READ_INPUTS=set()
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import league_runtime as L
import league_agenda as A
from unittest import mock
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def fixture(self,**changes):
  e=Engine(self.rules,0)
  def c(n,kind,speed):
   stats={k:30 for k in ('hp','atk','def','spa','spd','spe')};stats['spe']=speed
   return Combatant(self.rules,dict(name=n,kind=kind,level=10,stats=stats,types=[],abilities=[],moves=['struggle']))
  t1,p1,t2,p2=c('t1','trainer',10),c('p1','pokemon',40),c('t2','trainer',20),c('p2','pokemon',30)
  actors={'a:trainer':t1,'a:pokemon':p1,'b:trainer':t2,'b:pokemon':p2}
  for (key,field),value in changes.items():setattr(actors[key],field,value)
  return e,actors,[('a',t1,p1),('b',t2,p2)]
 def start(self):
  e,c,pairs=self.fixture();e.start_league(pairs,mode='league');return e,c
 def declarations(self,e):
  e.league_declare('a:trainer',{'kind':'no_action'});e.league_declare('b:trainer',{'kind':'no_action'})
 def trainers(self,e):self.declarations(e);e.league_step();e.league_step()
 def move(self,target='b:pokemon'):
  return dict(kind='use_move',target_id=target,move_id='struggle',set_damage=True)
 def finish(self,e):
  self.trainers(e);e.league_step(pokemon_intent={'kind':'no_action'});e.league_step(pokemon_intent={'kind':'no_action'});return e.league_complete_round()
 def test_001_derived_initiative_and_three_engine_phases(self):
  e,c=self.start()
  self.assertEqual(e.league_status()['next'],(A.Phase.DECLARE,'a:trainer'))
  self.trainers(e)
  self.assertEqual([x['actor'] for x in e._turn_closures],[c['b:trainer'],c['a:trainer']])
  self.assertEqual(e.league_status()['next'],(A.Phase.POKEMON,'a:pokemon'))
  e.league_step(pokemon_intent=self.move());e.league_step(pokemon_intent={'kind':'no_action'})
  self.assertEqual(c['b:pokemon'].hp,99)
  self.assertEqual(e.league_complete_round()['status'],'round_complete');self.assertEqual(e.elapsed_seconds,10)
 def test_002_declaration_no_turn_budget_frequency_hp_time_effect(self):
  e,c=self.start();before=[copy.deepcopy(x.spec) for x in c.values()];hp=[x.hp for x in c.values()]
  raw={'kind':'no_action'};e.league_declare('a:trainer',raw);raw['kind']='use_move'
  self.assertEqual([x.spec for x in c.values()],before);self.assertEqual([x.hp for x in c.values()],hp)
  self.assertEqual(e.elapsed_seconds,0);self.assertEqual(e._ordinary_turn_rounds,{});self.assertEqual(e._turn_closures,[])
  self.assertTrue(all(getattr(x,'budget',None) is None for x in c.values()))
  self.assertEqual(e._league_runtime['intents']['a:trainer']['kind'],'no_action')
 def test_003_early_resolution_and_declaration_override_rejected(self):
  e,c=self.start()
  with self.assertRaises(ValueError):e.league_step()
  self.declarations(e)
  with self.assertRaises(ValueError):e.league_step(pokemon_intent=self.move())
  self.assertEqual(e._turn_closures,[])
 def test_004_direct_engine_bypass_blocked(self):
  e,c=self.start()
  for call in [lambda:e.start_of_turn(c['b:trainer']),lambda:e.end_round(),lambda:e.start_round(c.values()),lambda:e.advance_time(10),lambda:e.use_move(c['a:pokemon'],c['b:pokemon'],'struggle')]:
   with self.assertRaises(ValueError):call()
  self.assertEqual(e.elapsed_seconds,0);self.assertEqual(e._ordinary_turn_rounds,{})
 def test_005_pokemon_choice_only_at_its_phase(self):
  e,c=self.start();self.trainers(e)
  self.assertNotIn('a:pokemon',e._league_runtime['intents'])
  e.league_step(pokemon_intent=self.move())
  self.assertEqual(c['a:pokemon'].move_uses,{'struggle':1});self.assertEqual(c['a:pokemon'].budget['standard'],0)
 def test_006_trainer_unsupported_attack_holds_without_source_illegality_claim(self):
  e,c=self.start();r=e.league_declare('a:trainer',self.move())
  self.assertEqual(r['status'],'incomplete');self.assertEqual(e._turn_closures,[]);self.assertEqual(e.elapsed_seconds,0)
  self.assertIn('unsupported',r['pending']['reason']);self.assertEqual(c['a:trainer'].move_uses,{})
 def test_007_actual_close_required_before_ack(self):
  e,c=self.start();self.declarations(e)
  with mock.patch.object(e,'end_of_turn',return_value=None):r=e.league_step()
  self.assertEqual(r['status'],'incomplete');self.assertEqual(e._league_runtime['close_receipts'],[])
  self.assertEqual(len(e._league_runtime['agenda'].records),2)
 def test_008_speed_change_holds_before_turn(self):
  e,c=self.start();self.declarations(e);c['a:pokemon'].stages['spe']=1
  r=e.league_step();self.assertEqual(r['status'],'incomplete');self.assertEqual(e._turn_closures,[])
 def test_009_roster_change_holds_without_advancement(self):
  e,c=self.start();e.everyone.pop()
  self.assertEqual(e.league_declare('a:trainer',{'kind':'no_action'})['status'],'incomplete')
  self.assertEqual(e.elapsed_seconds,0)
 def test_010_new_faint_is_source_inability_but_unsupported_runtime_transition(self):
  e,c=self.start();self.declarations(e);c['b:trainer'].hp=0;c['b:trainer'].conditions.add('기절')
  r=e.league_step();self.assertEqual(r['status'],'incomplete')
  self.assertEqual(len(e._league_runtime['agenda'].turn_rights),4);self.assertEqual(e._turn_closures,[])
 def test_011_static_faint_trainer_keeps_partner_turn(self):
  e,c,pairs=self.fixture();c['b:trainer'].hp=0;c['b:trainer'].conditions.add('기절')
  e.start_league(pairs,mode='league');self.trainers(e)
  e.league_step(pokemon_intent={'kind':'no_action'});e.league_step(pokemon_intent={'kind':'no_action'})
  self.assertEqual(len(e._turn_closures),4);self.assertEqual(c['b:pokemon'].spec['frequency_state']['turn'],1)
  self.assertEqual(c['b:trainer'].move_uses,{})
 def test_012_static_faint_pokemon_has_no_action_but_partner_turn(self):
  e,c,pairs=self.fixture();c['b:pokemon'].hp=0;c['b:pokemon'].conditions.add('기절')
  e.start_league(pairs,mode='league');self.finish(e)
  self.assertEqual(c['b:trainer'].spec['frequency_state']['turn'],1)
  self.assertEqual(c['b:pokemon'].move_uses,{})
 def test_013_heavy_pending_preserves_damage_active_turn_agenda_and_time(self):
  e,c,pairs=self.fixture();c['b:pokemon'].hp=50;c['b:pokemon'].injuries=5
  e.start_league(pairs,mode='league');self.trainers(e)
  r=e.league_step(pokemon_intent=self.move())
  self.assertEqual(r['status'],'incomplete');self.assertTrue(e._heavy_pending);self.assertEqual(c['b:pokemon'].hp,39)
  self.assertIs(e._active_turn_actor,c['a:pokemon']);self.assertEqual(len(e._turn_closures),2)
  self.assertEqual(len(e._league_runtime['agenda'].records),4);self.assertEqual(e.elapsed_seconds,0)
  for call in [e.next_league_round,e.league_complete_round,lambda:e.end_of_turn(c['a:pokemon']),lambda:e.advance_time(10)]:
   with self.assertRaises(L.LeaguePending):call()
 def test_014_round_once_next_round_has_new_rights(self):
  e,c=self.start();self.finish(e)
  with self.assertRaises(ValueError):e.league_complete_round()
  self.assertEqual(e.elapsed_seconds,10)
  old=e._league_runtime['agenda'].turn_rights;e.next_league_round()
  self.assertEqual(e.elapsed_seconds,10);self.assertEqual(e.round_no,2);self.assertNotEqual(e._league_runtime['agenda'].turn_rights,old)
  self.finish(e);self.assertEqual(e.elapsed_seconds,20);self.assertEqual(len(e._turn_closures),8)
 def test_015_snapshot_restores_intents_turns_identity_and_last_target(self):
  e,c=self.start();self.trainers(e);e.gm.snapshot('before-pokemon')
  e.league_step(pokemon_intent=self.move());self.assertIs(c['a:pokemon'].last_target,c['b:pokemon'])
  e.gm.restore('before-pokemon')
  self.assertEqual(c['b:pokemon'].hp,110);self.assertIsNone(c['a:pokemon'].last_target)
  self.assertIs(e._league_runtime['actors']['a:pokemon'],c['a:pokemon']);self.assertEqual(len(e._turn_closures),2)
  self.assertIs(e._league_runtime['close_receipts'][0]['actor'],c['b:trainer'])
  self.assertNotIn('a:pokemon',e._league_runtime['intents']);self.assertIsNone(e._active_turn_actor)
 def test_016_pending_snapshot_restore_does_not_resume(self):
  e,c,pairs=self.fixture();c['b:pokemon'].hp=50;c['b:pokemon'].injuries=5
  e.start_league(pairs,mode='league');self.trainers(e);e.league_step(pokemon_intent=self.move());e.gm.snapshot('pending')
  event=e._heavy_pending;e.gm.restore('pending')
  self.assertIs(e._heavy_events[event]['target'],c['b:pokemon'])
  self.assertIs(e._active_turn_actor,c['a:pokemon'])
  with self.assertRaises(L.LeaguePending):e.league_step(pokemon_intent={'kind':'no_action'})
 def test_017_unknown_initiative_or_tie_does_not_start_engine_round(self):
  e,c,pairs=self.fixture();c['b:trainer'].stats['spe']=10
  r=e.start_league(pairs,mode='league');self.assertEqual(r['status'],'incomplete');self.assertEqual(e.round_no,0)
  self.assertIsNone(e.round_start_seconds)
 def test_018_mode_selection_explicit_and_no_arbitrary_speed_input(self):
  e,c,pairs=self.fixture()
  with self.assertRaises(ValueError):e.start_league(pairs,mode='full_contact')
  self.assertEqual(e.round_no,0)
  with self.assertRaises(TypeError):e.start_league(pairs,mode='league',initiative={'a':99})
 def test_019_trainer_status_hook_is_outside_phase_contract(self):
  e,c,pairs=self.fixture();c['a:trainer'].conditions.add('독')
  r=e.start_league(pairs,mode='league');self.assertEqual(r['status'],'incomplete');self.assertEqual(e.round_no,0)
 def test_020_damage_faint_keeps_unfinished_turn_and_no_winner(self):
  e,c,pairs=self.fixture();c['b:pokemon'].hp=8
  e.start_league(pairs,mode='league');self.trainers(e);r=e.league_step(pokemon_intent=self.move())
  self.assertEqual(r['status'],'incomplete');self.assertLessEqual(c['b:pokemon'].hp,0)
  self.assertEqual(len(e._turn_closures),2);self.assertEqual(e.elapsed_seconds,0);self.assertNotIn('winner',r)
 def test_021_native_miss_closes_once_and_consumes_one_move_use(self):
  e,c=self.start();e.rng.seed(31);self.trainers(e)
  r=e.league_step(pokemon_intent=self.move())
  self.assertEqual(r['status'],'ready');self.assertEqual(c['b:pokemon'].hp,110)
  self.assertEqual(c['a:pokemon'].move_uses,{'struggle':1});self.assertEqual(len(e._turn_closures),3)
 def test_022_restore_preleague_snapshot_removes_runtime_and_closures(self):
  e,c,pairs=self.fixture();e.everyone=e.gm.everyone=list(c.values());e.gm.snapshot('ordinary')
  e.start_league(pairs,mode='league');self.declarations(e);e.league_step()
  e.gm.restore('ordinary')
  self.assertIsNone(e._league_runtime);self.assertEqual(e._turn_closures,[]);self.assertEqual(e.round_no,0)
  self.assertEqual(e._ordinary_turn_rounds,{});self.assertIsNone(e._active_turn_actor)
  self.assertEqual(e.everyone,list(c.values()));self.assertEqual(e.gm.everyone,list(c.values()))
 def test_023_explicit_end_only_after_full_close_and_no_winner_inference(self):
  e,c=self.start()
  with self.assertRaises(ValueError):e.end_league()
  self.finish(e);r=e.end_league()
  self.assertEqual(r['status'],'encounter_ended_by_caller');self.assertIsNone(r['winner'])
  self.assertIsNone(e._league_runtime);self.assertFalse(e.encounter_active);self.assertEqual(e.elapsed_seconds,10)
 def test_024_pending_cannot_be_cleared_by_end_request(self):
  e,c=self.start();e.league_declare('a:trainer',self.move())
  before=copy.deepcopy(e._league_runtime['pending'])
  with self.assertRaises(L.LeaguePending):e.end_league()
  self.assertEqual(e._league_runtime['pending'],before)
 def test_025_self_and_fainted_target_are_unsupported_before_turn_cost(self):
  for target in ['a:pokemon','b:pokemon']:
   e,c,pairs=self.fixture()
   if target=='b:pokemon':c[target].hp=0;c[target].conditions.add('기절')
   e.start_league(pairs,mode='league');self.trainers(e)
   r=e.league_step(pokemon_intent=self.move(target))
   self.assertEqual(r['status'],'incomplete');self.assertEqual(c['a:pokemon'].move_uses,{})
   self.assertEqual(len(e._turn_closures),2)
 def test_026_source_phase_and_no_action_anchors(self):
  lines=(ROOT/'input/ch07-combat.md').read_text(encoding='utf8').splitlines()
  for n,text in [(21,'포켓몬의 턴은 그대로 유지'),(28,'선언'),(74,'알릴 필요는 없습니다'),(110,'아무')]:
   self.assertIn(text,lines[n-1])
 def test_027_public_area_helper_rejected_before_roster_or_frequency_mutation(self):
  e,c=self.start();roster=list(e.everyone);spec=copy.deepcopy(c['a:pokemon'].spec)
  with self.assertRaises(ValueError):e.use_move_on(c['a:pokemon'],c['b:pokemon'],'struggle',[c['a:pokemon'],c['b:pokemon']])
  self.assertEqual(e.everyone,roster);self.assertEqual(c['a:pokemon'].spec,spec)
  self.assertIsNone(e._league_runtime['pending'])
  self.assertEqual(e.league_declare('a:trainer',{'kind':'no_action'})['status'],'ready')
 def test_028_direct_damage_and_capture_producers_cannot_bypass_declaring_driver(self):
  e,c=self.start();before=[x.hp for x in c.values()];rng=e.rng.getstate()
  for call in [lambda:e.resolve_attack_damage(c['a:pokemon'],c['b:pokemon'],e.r.move('struggle'),set_damage=True),
               lambda:e.throw_ball(c['a:trainer'],c['b:pokemon'])]:
   with self.assertRaises(ValueError):call()
  self.assertEqual([x.hp for x in c.values()],before);self.assertEqual(e.rng.getstate(),rng)
  self.assertIsNone(e._league_runtime['pending'])
 def test_029_unattached_status_is_explicit(self):
  e,c,pairs=self.fixture();self.assertEqual(e.league_status()['status'],'not_attached')
  e.start_league(pairs,mode='league');self.finish(e);e.end_league()
  self.assertEqual(e.league_status()['status'],'not_attached')
 def test_030_closed_round_changed_roster_is_preserved_and_held(self):
  for field in ('everyone','gm.everyone'):
   for duplicate in (False,True):
    e,c=self.start();self.finish(e)
    owner=e.gm if field=='gm.everyone' else e
    altered=list(owner.everyone)
    if duplicate:altered.append(altered[0])
    else:altered.pop()
    owner.everyone=altered
    r=e.next_league_round()
    self.assertEqual(r['status'],'incomplete');self.assertEqual(e.round_no,1)
    self.assertEqual(e.elapsed_seconds,10);self.assertIs(owner.everyone,altered)
    self.assertEqual(len(e._turn_closures),4);self.assertIsNone(e.round_start_seconds)
    with self.assertRaises(L.LeaguePending):e.end_league()
 def test_031_explicit_end_does_not_discard_changed_roster(self):
  e,c=self.start();self.finish(e);e.everyone=e.everyone[:-1]
  roster=e.everyone;r=e.end_league()
  self.assertEqual(r['status'],'incomplete');self.assertIs(e.everyone,roster)
  self.assertTrue(e.encounter_active);self.assertEqual(e.elapsed_seconds,10)
class Results(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='LEAGUE-RUNTIME-'+t._testMethodName,status='pass'))
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='LEAGUE-RUNTIME-'+t._testMethodName,status='fail',detail=self._exc_info_to_string(e,t)))
 def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='LEAGUE-RUNTIME-'+t._testMethodName,status='error',detail=self._exc_info_to_string(e,t)))
if __name__=='__main__':
 def tracing(original):
  def opened(file,mode='r',*args,**kwargs):
   if 'r' in mode or '+' in mode:
    try:
     p=pathlib.Path(file).resolve()
     if p.is_relative_to(ROOT) and p.is_file():READ_INPUTS.add(p)
    except (ValueError,TypeError,OSError):pass
   return original(file,mode,*args,**kwargs)
  return opened
 original_open,original_io=builtins.open,io.open
 builtins.open,io.open=tracing(original_open),tracing(original_io)
 try:r=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 finally:builtins.open,io.open=original_open,original_io
 paths=list((ROOT/'engine').glob('*.py'))+[pathlib.Path(__file__).resolve(),ROOT/'input/ch07-combat.md',ROOT/'input/ch11-running-the-game.md']
 paths=list(set(paths)|READ_INPUTS|set((ROOT/'data/verification').glob('common-league*.json')))
 report=dict(tests_run=r.testsRun,results=r.rows,input_hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},semantic_closure=False,scope='Actual restricted League driver; source initiative/order, no-action trainer and Pokemon Struggle only')
 (ROOT/'output/league-runtime-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 sys.exit(not r.wasSuccessful())
