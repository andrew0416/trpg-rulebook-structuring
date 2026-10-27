"""Independent active-combat lifecycle contracts. Draft until parent API binding review.
Not a certification of Priority/Interrupt, all reactions, or outside-combat helpers.
"""
import argparse,copy,hashlib,json,pathlib,sys,tempfile,unittest
from datetime import datetime,timezone
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[1]
if not (ROOT/'data').is_dir() or not (ROOT/'output').is_dir():ROOT=pathlib.Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')

class ActionLifecycleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  sys.path.insert(0,str(ROOT/'engine'))
  from engine import Rules,Engine,Combatant
  import turn,frequency
  cls.rules=Rules(str(ROOT),ruleset='core');cls.Engine=Engine;cls.Combatant=Combatant;cls.turn=turn;cls.freq=frequency
 def pair(self):
  def actor(name):
   return self.Combatant(self.rules,dict(name=name,kind='trainer',size='medium',level=1,stats={s:20 for s in ('hp','atk','def','spa','spd','spe')},types=[],moves=['struggle'],abilities=[],pos=(0,0),movement={'land':2}))
  e=self.Engine(self.rules);a,b=actor('a'),actor('b');e.everyone=[a,b];e.gm.everyone=[a,b];e.d20=lambda:1
  return e,a,b
 def state(self,e,c):
  return copy.deepcopy({'budget':getattr(c,'budget',None),'frequency':c.spec.get('frequency_state',{}),'uses':c.move_uses,'hp':c.hp,'conditions':sorted(c.conditions),'turns_taken':c.turns_taken,'movement_used':getattr(c,'_regular_shift_movement_used',False),'pending_action_loss':getattr(c,'pending_action_loss',None),'elapsed':e.elapsed_seconds})
 def denied_or_inert(self,callback):
  # Source constrains lack of activation, not a Python return type. Unexpected
  # programming errors still fail, rather than counting as valid rejection.
  try:return callback()
  except ValueError:return None
 def test_001_active_encounter_without_round_no_ordinary_payment(self):
  e,a,b=self.pair();e.begin_encounter([a,b]);result=self.denied_or_inert(lambda:self.turn.spend(e,a,'standard'))
  self.assertFalse(result)
 def test_002_open_round_before_turn_no_ordinary_activation(self):
  e,a,b=self.pair();e.start_round([a,b]);self.denied_or_inert(lambda:e.use_move(a,b,'struggle'));self.assertEqual(a.move_uses,{})
 def test_003_other_actor_budget_is_not_own_turn_authority(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);b.budget={'standard':1,'shift':1,'swift':1}
  before=copy.deepcopy(b.budget);self.denied_or_inert(lambda:e.use_move(b,a,'struggle'));self.assertEqual(b.move_uses,{});self.assertEqual(b.budget,before)
 def test_004_closed_turn_cannot_use_remaining_swift(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);e.end_of_turn(a);before=copy.deepcopy(a.budget)
  result=self.denied_or_inert(lambda:self.turn.spend(e,a,'swift'));self.assertFalse(result);self.assertEqual(a.budget,before)
 def test_005_duplicate_start_has_no_refresh(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);self.assertTrue(self.turn.spend(e,a,'standard'));before=self.state(e,a)
  self.denied_or_inert(lambda:e.start_of_turn(a));self.assertEqual(self.state(e,a),before)
 def test_006_closed_actor_no_second_ordinary_turn_same_round(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);self.turn.spend(e,a,'standard');e.end_of_turn(a);before=self.state(e,a)
  self.denied_or_inert(lambda:e.start_of_turn(a));self.assertEqual(self.state(e,a),before)
 def test_007_duplicate_end_does_not_repeat_sleep_save(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);a.conditions.add('잠듦');rolls=[]
  def die():rolls.append(1);return 1
  e.d20=die;e.end_of_turn(a);self.assertEqual(len(rolls),1);before=self.state(e,a)
  self.denied_or_inert(lambda:e.end_of_turn(a));self.assertEqual(len(rolls),1);self.assertEqual(self.state(e,a),before)
 def test_008_wrong_actor_end_does_not_fire_effects(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);b.conditions.add('잠듦');rolls=[]
  def die():rolls.append(1);return 1
  e.d20=die;self.denied_or_inert(lambda:e.end_of_turn(b));self.assertEqual(rolls,[])
  self.assertTrue(self.turn.spend(e,a,'standard'))
 def test_009_sequential_turns_and_successor_round(self):
  e,a,b=self.pair();e.start_round([a,b])
  for c in [a,b]:e.start_of_turn(c);self.assertTrue(self.turn.spend(e,c,'standard'));e.end_of_turn(c)
  e.end_round();e.start_round([a,b]);e.start_of_turn(a);self.assertTrue(self.turn.spend(e,a,'standard'))
  self.assertEqual(self.freq.state(a)['turn'],2);self.assertEqual(self.freq.state(b)['turn'],1)
 def test_011_snapshot_preserves_active_owner_and_spent_state(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);self.turn.spend(e,a,'standard');e.gm.snapshot('active');before=self.state(e,a)
  e.end_of_turn(a);e.start_of_turn(b);e.gm.restore('active');self.assertEqual(self.state(e,a),before)
  self.denied_or_inert(lambda:e.start_of_turn(a));self.assertEqual(self.state(e,a),before)
  self.assertFalse(self.denied_or_inert(lambda:self.turn.spend(e,b,'standard')))
  self.assertTrue(self.turn.spend(e,a,'swift'))
 def test_012_snapshot_preserves_completed_turn(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);e.end_of_turn(a);e.gm.snapshot('closed');e.start_of_turn(b);e.gm.restore('closed');before=self.state(e,a)
  self.denied_or_inert(lambda:e.start_of_turn(a));self.assertEqual(self.state(e,a),before)
 def test_013_paralysis_save_at_start_not_auto_cure(self):
  for n in [10,11]:
   with self.subTest(roll=n):
    e,a,b=self.pair();e.start_round([a,b]);a.conditions.add('마비');rolls=[]
    def die():rolls.append(n);return n
    e.d20=die;e.start_of_turn(a,initiative_count=__import__('initiative').value(self.rules,a,engine=e).value);self.assertEqual(rolls,[n]);self.assertIn('마비',a.conditions);e.end_of_turn(a);self.assertEqual(rolls,[n]);self.assertIn('마비',a.conditions)
 def test_014_failed_paralysis_allows_only_one_standard_or_shift(self):
  for first,second in [('standard','shift'),('shift','standard')]:
   with self.subTest(first=first):
    e,a,b=self.pair();e.start_round([a,b]);a.conditions.add('마비');e.d20=lambda:10;e.start_of_turn(a,initiative_count=__import__('initiative').value(self.rules,a,engine=e).value)
    self.assertTrue(self.turn.spend(e,a,first));self.assertFalse(self.denied_or_inert(lambda:self.turn.spend(e,a,second)))
    self.assertTrue(self.turn.spend(e,a,'free'));self.assertTrue(self.turn.spend(e,a,'swift'))
 def test_015_successful_paralysis_permits_both_actions_without_cure(self):
  e,a,b=self.pair();e.start_round([a,b]);a.conditions.add('마비');e.d20=lambda:11;e.start_of_turn(a,initiative_count=__import__('initiative').value(self.rules,a,engine=e).value)
  self.assertTrue(self.turn.spend(e,a,'standard'));self.assertTrue(self.turn.spend(e,a,'shift'));self.assertIn('마비',a.conditions)
 def test_016_sleep_blocks_ordinary_attack(self):
  e,a,b=self.pair();e.start_round([a,b]);a.conditions.add('잠듦');e.start_of_turn(a);before=copy.deepcopy(a.budget)
  self.denied_or_inert(lambda:e.use_move(a,b,'struggle'));self.assertEqual(a.move_uses,{});self.assertEqual(a.budget,before)
 def test_018_standard_item_counts_for_curse(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);a.conditions.add('저주');a.spec['items']={'상처약':1};b.hp=1;before=a.hp
  result=e.use_item(a,'상처약',b);self.assertGreater(result[0],0);e.end_of_turn(a);self.assertEqual(before-a.hp,2*e.tick(a))
 def test_020_sleep_inability_still_ticks_burn(self):
  e,a,b=self.pair();e.start_round([a,b]);a.conditions.update(['잠듦','화상']);e.start_of_turn(a);before=a.hp;e.end_of_turn(a);self.assertEqual(before-a.hp,e.tick(a))
 def test_021_real_encounter_loop_respects_sleep(self):
  import encounter
  observations=[];armed=False
  def hook(e,c,rnd):
   nonlocal armed
   if armed:return
   armed=True;c.conditions.add('잠듦');e.d20=lambda:1;original=e.use_move
   def wrapped(actor,target,mid,*args,**kwargs):
    asleep='잠듦' in actor.conditions;before=dict(actor.move_uses);value=original(actor,target,mid,*args,**kwargs)
    if asleep and actor.move_uses!=before:observations.append(mid)
    return value
   e.use_move=wrapped
  # This sample explicitly selects CSV295 Chlorophyll [Playtest], not a core definition.
  # Its initial tie needs an explicit fixture policy before the real hook can run.
  with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
   policy=pathlib.Path(folder)/'sleep-loop-initiative-policy.json'
   policy.write_text(json.dumps({'rulings':[{'kind':'answer','key':'initiative_tie_order','scope':'campaign',
    'reason':'explicit lifecycle fixture tie policy; not a source rule',
    'answer':{'policy':'highest_d20','same_face':'reroll','max_rounds':100,'reason':'allow the actual sleep hook to run'}}]}),encoding='utf-8')
   e,_,_=encounter.run_encounter(str(ROOT),'data/encounters/lakeside.json',seed=1,ruleset='all',rulings_path=str(policy),hook=hook,write=False)
  self.assertTrue(armed);self.assertGreater(e.round_no,0)
  self.assertEqual(observations,[])

 def test_026_start_without_open_round_value_error_no_effects(self):
  e,a,b=self.pair();e.begin_encounter([a,b]);before=self.state(e,a)
  with self.assertRaises(ValueError):e.start_of_turn(a)
  self.assertEqual(self.state(e,a),before)
 def test_027_start_other_actor_while_turn_active_value_error(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);before=self.state(e,b)
  with self.assertRaises(ValueError):e.start_of_turn(b)
  self.assertEqual(self.state(e,b),before);self.assertTrue(self.turn.spend(e,a,'standard'))
 def test_028_duplicate_start_and_completed_reentry_value_error(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a)
  with self.assertRaises(ValueError):e.start_of_turn(a)
  e.end_of_turn(a)
  with self.assertRaises(ValueError):e.start_of_turn(a)
 def test_029_wrong_actor_and_duplicate_end_value_error(self):
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a)
  with self.assertRaises(ValueError):e.end_of_turn(b)
  e.end_of_turn(a)
  with self.assertRaises(ValueError):e.end_of_turn(a)

 def contract_move(self,e,action,effects):
  # Explicitly synthetic identity. This isolates ch07 common permission semantics
  # and does not prove acquisition/admission of any real named move or ability.
  sys.path.insert(0,str(ROOT/'tools'));from synthetic_rule_fixture import register_synthetic
  n=len(e.r.selection.units);mid='test-only/action-lifecycle/'+str(n);register_synthetic(e.r,mid,name=mid)
  text={'free':'자유 행동','swift':'신속 행동','standard':'','full':'완전 행동'}[action]
  e.r.moves[mid]=dict(id=mid,name=mid,type='노말',frequency='임의',range='자신 '+text,ac=None,damage_base=None,**{'class':'변화'},effect='',mech_auto={})
  e.r.moves_mech[mid]=dict(name=mid,coverage='full',header=dict(frequency=dict(kind='at_will'),range=dict(origin='self',parsed=True)),effects=effects)
  return mid
 def test_030_sleep_cure_free_and_swift_contract(self):
  for action in ('free','swift'):
   with self.subTest(action=action):
    e,a,b=self.pair();mid=self.contract_move(e,action,[dict(type='cure_status',status='잠듦',target='self')]);e.start_round([a,b]);a.conditions.add('잠듦');e.start_of_turn(a);before=copy.deepcopy(a.budget)
    e.use_move(a,a,mid);self.assertNotIn('잠듦',a.conditions);self.assertEqual(a.move_uses[mid],1);self.assertEqual(a.budget['standard'],before['standard']);self.assertEqual(a.budget['swift'],before['swift']-(action=='swift'))
 def test_031_sleep_cure_standard_still_forbidden(self):
  e,a,b=self.pair();mid=self.contract_move(e,'standard',[dict(type='cure_status',status='잠듦',target='self')]);e.start_round([a,b]);a.conditions.add('잠듦');e.start_of_turn(a)
  e.use_move(a,a,mid);self.assertIn('잠듦',a.conditions);self.assertNotIn(mid,a.move_uses)
 def test_032_sleep_free_unrelated_or_ally_cure_not_exception(self):
  for effect in [dict(type='cure_status',status='독',target='self'),dict(type='cure_status',status='잠듦',target='target')]:
   with self.subTest(effect=effect):
    e,a,b=self.pair();mid=self.contract_move(e,'free',[effect]);target=a
    if effect['target']=='target':
     # The ally cure must reach its actual ally to test the sleep permission.
     target=b;e.r.moves[mid]['range']='원거리 6 자유 행동'
     e.r.moves_mech[mid]['header']['range']=dict(origin='ranged',size=6,parsed=True)
    e.start_round([a,b]);a.conditions.add('잠듦');b.conditions.add('잠듦');e.start_of_turn(a);e.use_move(a,target,mid)
    self.assertIn('잠듦',a.conditions);self.assertIn('잠듦',b.conditions);self.assertNotIn(mid,a.move_uses)
 def test_033_unfulfilled_conditional_sleep_cure_does_not_grant(self):
  for gate in [dict(if_weather='sunny'),dict(on_ko=True),dict(on_natural_roll_min=20),dict(on_miss=True)]:
   with self.subTest(gate=gate):
    e,a,b=self.pair();effects=[dict(type='cure_status',status='잠듦',target='self',**gate),dict(type='stage_change',stat='atk',delta=1,target='self')];mid=self.contract_move(e,'free',effects);e.start_round([a,b]);a.conditions.add('잠듦');e.start_of_turn(a)
    # A natural-face predicate needs an actual accuracy roll in the synthetic source.
    if 'on_natural_roll_min' in gate:e.r.moves[mid]['ac']=2
    before=copy.deepcopy(a.budget);rng=e.rng.getstate()
    e.use_move(a,a,mid);self.assertIn('잠듦',a.conditions);self.assertNotIn(mid,a.move_uses);self.assertEqual(a.stages['atk'],0)
    self.assertEqual(a.budget,before);self.assertEqual(e.rng.getstate(),rng)
 def test_034_bare_flags_do_not_authorize_combat_bypass(self):
  for flags in [dict(free_action=True),dict(count_use=False),dict(count_use=False,free_action=True)]:
   with self.subTest(flags=flags):
    e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);before=copy.deepcopy(a.budget);e.use_move(a,b,'struggle',**flags)
    self.assertEqual(a.move_uses,{});self.assertEqual(a.budget,before);self.assertFalse(a.took_standard)
 def test_035_aoo_before_own_turn_source_path_once_per_round(self):
  from grid import Grid
  e,a,b=self.pair();far=self.Combatant(self.rules,dict(copy.deepcopy(b.spec),id='fixture/far',name='far'));a.pos=(0,0);b.pos=(0,1);far.pos=(8,0);a.side='party';b.side=far.side='wild';e.everyone=e.gm.everyone=[a,b,far];e.grid=Grid(10,3)
  e.start_round([a,b,far]);e.start_of_turn(a);e.approach(a,far,1);self.assertTrue(b.aoo_used);self.assertFalse(b.took_standard);self.assertIsNone(getattr(b,'budget',None));self.assertEqual(b.move_uses,{})
  count=sum('[기회 공격]' in line for line in e.log_lines);self.assertEqual(count,1);self.turn.trigger_aoo(e,a,'same round second trigger',enemies=[b]);self.assertEqual(sum('[기회 공격]' in line for line in e.log_lines),1)
  e.end_of_turn(a);e.start_of_turn(b);self.assertTrue(b.aoo_used);self.assertTrue(self.turn.spend(e,b,'standard'))
 def area_contract(self,paralyzed=False):
  e,a,b=self.pair();c=self.Combatant(self.rules,dict(copy.deepcopy(b.spec),id='fixture/second',name='second'));e.everyone=e.gm.everyone=[a,b,c]
  mid=self.contract_move(e,'standard',[dict(type='injury',value=1,target='target')]);e.r.moves[mid]['range']='파열 1';e.r.moves_mech[mid]['header']['range']={'shape':'burst','size':1,'parsed':True};e.targets_in_range=lambda *args:[b,c];e.start_round([a,b,c])
  if paralyzed:a.conditions.add('마비')
  e.d20=lambda:10;e.start_of_turn(a,initiative_count=__import__('initiative').value(self.rules,a,engine=e).value if paralyzed else None);e.d20=lambda:20
  return e,a,b,c,mid
 def test_036_area_continuation_one_action_and_frequency(self):
  e,a,b,c,mid=self.area_contract();e.use_move_on(a,b,mid,[a,b,c]);self.assertEqual((b.injuries,c.injuries),(1,1));self.assertEqual(a.move_uses[mid],1);self.assertEqual(a.budget['standard'],0);self.assertEqual(a._action_history,['standard'])
 def test_037_paralysis_one_standard_preserves_same_activation_targets(self):
  e,a,b,c,mid=self.area_contract(True);e.use_move_on(a,b,mid,[a,b,c]);self.assertEqual((b.injuries,c.injuries),(1,1));self.assertEqual(a.move_uses[mid],1);self.assertEqual(a._action_history,['standard'])
 def test_038_sleep_cure_end_save_does_not_erase_burn_inability(self):
  e,a,b=self.pair();e.start_round([a,b]);a.conditions.update(['잠듦','화상']);e.start_of_turn(a);before=a.hp;e.d20=lambda:20;e.end_of_turn(a)
  self.assertNotIn('잠듦',a.conditions);self.assertEqual(before-a.hp,e.tick(a))

 def test_039_sleep_disallows_rage_save_until_sleep_cured(self):
  e,a,b=self.pair();e.start_round([a,b]);a.conditions.update(['잠듦','난동']);e.start_of_turn(a);rolls=[]
  def die():rolls.append(15);return 15
  e.d20=die;e.end_of_turn(a);self.assertIn('잠듦',a.conditions);self.assertIn('난동',a.conditions);self.assertEqual(rolls,[15])
 def test_040_unresolved_trigger_effect_refunds_matching_action_history(self):
  # Existing engine transactional hold policy: if payment is rolled back,
  # lifecycle attribution must be rolled back too. Not a universal game refund rule.
  import effects as FX
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);before=copy.deepcopy(a.budget)
  a.ability_triggers=[{'name':'test-only/unresolved-trigger','_feat':True,'spec':{'event':'test-only-event'},'frequency':{'kind':'at_will'},'activation_header':{'frequency':{'kind':'at_will','action':'standard'}},'effects':[{'type':'test_only_unresolved_effect'}]}]
  FX.fire_event(e,a,{'event':'test-only-event'},b);self.assertEqual(a.budget,before);self.assertFalse(a.took_standard);self.assertEqual(a._action_history,[]);self.assertFalse(a._restricted_action_taken)

 def test_041_turn_start_action_held_until_paralysis_decision(self):
  import effects as FX
  e,a,b=self.pair();a.conditions.add('마비');e.start_round([a,b]);e.d20=lambda:10
  a.ability_triggers=[{'name':'test-only/turn-start-cost','_feat':True,'spec':{'event':'turn_start'},'frequency':{'kind':'at_will'},'activation_header':{'frequency':{'kind':'at_will','action':'standard'}},'effects':[{'type':'injury','value':1,'target':'self'}]}]
  e.start_of_turn(a,initiative_count=__import__('initiative').value(self.rules,a,engine=e).value);self.assertEqual(a.injuries,0);self.assertEqual(a.budget['standard'],1);self.assertEqual(a._action_history,[])
  self.assertTrue(self.turn.spend(e,a,'shift'));self.assertFalse(self.turn.spend(e,a,'standard'))
 def test_042_standard_acted_evidence_survives_end_not_next_round(self):
  import effects as FX
  e,a,b=self.pair();e.start_round([a,b]);e.start_of_turn(a);self.turn.spend(e,a,'standard');e.end_of_turn(a)
  ctx={'engine':e,'attacker':b,'target':a,'hit':True};self.assertIs(FX.KNOWN_IF['target already acted this round'](ctx),True)
  self.assertFalse(FX.KNOWN_IF['target initiative lower and has not acted'](ctx))
  e.start_of_turn(b);e.end_of_turn(b);e.end_round();e.start_round([a,b])
  self.assertIsNot(FX.KNOWN_IF['target already acted this round'](ctx),True)
  self.assertFalse(FX.cond_ok(e,{'if':'target already acted this round'},ctx)[0])
 def test_043_unsupported_sleep_alias_does_not_authorize(self):
  for payload in [dict(status='Sleep'),dict(status='asleep'),dict(statuses=['잠듦']),dict(status=['잠듦','Sleep'])]:
   with self.subTest(payload=payload):
    e,a,b=self.pair();mid=self.contract_move(e,'free',[dict(type='cure_status',target='self',**payload),dict(type='stage_change',stat='atk',delta=1,target='self')]);e.start_round([a,b]);a.conditions.add('잠듦');e.start_of_turn(a)
    before=copy.deepcopy(a.budget)
    if 'statuses' in payload:
     from effect_contracts import EffectContractError
     with self.assertRaises(EffectContractError) as caught:e.use_move(a,a,mid)
     self.assertEqual(caught.exception.issue.category,'unsupported_execution');self.assertEqual(caught.exception.issue.field,'statuses')
    else:e.use_move(a,a,mid)
    self.assertIn('잠듦',a.conditions);self.assertEqual(a.stages['atk'],0);self.assertNotIn(mid,a.move_uses);self.assertEqual(a.budget,before)

class Results(unittest.TextTestResult):
 def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':'ACTION-LIFECYCLE-'+t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':'ACTION-LIFECYCLE-'+t._testMethodName,'status':'fail','detail':self._exc_info_to_string(e,t)})
 def addError(self,t,e):super().addError(t,e);self.rows.append({'id':'ACTION-LIFECYCLE-'+t._testMethodName,'status':'error','detail':self._exc_info_to_string(e,t)})
 def addSubTest(self,t,sub,err):
  super().addSubTest(t,sub,err)
  if err is not None:self.rows.append({'id':'ACTION-LIFECYCLE-'+t._testMethodName+'-'+str(sub.params),'status':'fail','detail':self._exc_info_to_string(err,t)})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1]);p.add_argument('--output',type=pathlib.Path);args=p.parse_args();ROOT=args.root
 if args.output is None:args.output=ROOT/'output/common-action-lifecycle-independent-tests.json'
 result=unittest.TextTestRunner(resultclass=Results,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ActionLifecycleTests))
 paths=['engine/action_lifecycle.py','engine/effects.py','tools/synthetic_rule_fixture.py','engine/engine.py','engine/turn.py','engine/frequency.py','engine/gm_state.py','engine/encounter.py','engine/items.py','data/conditions.json','input/ch07-combat.md']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'test_script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'results':result.rows,'tests_run':result.testsRun,'input_hashes':{x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in paths},'semantic_closure':False,'scope':'Partial active-combat ordinary-turn contracts, common sleep-cure component fixtures, actual AoO producer and same-activation continuations. Priority/Interrupt debt and all leaf permissions remain open.'}
 report['input_hashes']['tools/test_common_action_lifecycle_independent.py']=report['test_script_sha256']
 args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');sys.exit(0 if result.wasSuccessful() else 1)
