import pathlib,sys,unittest,copy,json,hashlib,importlib.util,builtins,io
READ_INPUTS=set()
from datetime import datetime,timezone
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import heavy_injury_adapter as H
import heavy_standard_adapter as S
import turn as TURN
import temporary_hp as TEMP_HP
import effects as FX

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules=Rules(str(ROOT),ruleset='core')
  spec=importlib.util.spec_from_file_location('historical_attack_engine',ROOT/'tests/fixtures/heavy_standard_historical_engine.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);cls.BaselineEngine=module.Engine
 def pair(self,seed=0,inj=5,engine_cls=Engine):
  e=engine_cls(self.rules,seed)
  def actor(n):return Combatant(e.r,dict(name=n,kind='trainer',level=10,stats={x:30 for x in ['hp','atk','def','spa','spd','spe']},types=[],abilities=[],moves=['struggle']))
  a,b=actor('actor'),actor('target');a.hp=50;a.injuries=inj;b.hp=110
  e.everyone=e.gm.everyone=[a,b];e.start_round([a,b]);e.start_of_turn(a)
  return e,a,b
 def standard(self,e):return [p for p in e._heavy_events.values() if p['producer']=='Engine.use_move.native_standard']
 def grant_temp(self,e,c,value):
  FX.run_effects(e,c,c,[dict(type='temp_hp',value=value)],
                dict(hit=True,attacker=c,target=c,engine=e,round_offset_seconds=0),'condition/임시-체력')
  self.assertEqual(c.temp_hp,value)
  self.assertEqual(c.custom_conditions[TEMP_HP.STATE]['minimum_seconds'],300)
 def test_001_native_hit_is_one_actual_standard_and_one_loss(self):
  e,a,b=self.pair();self.assertEqual(e.use_move(a,b,'struggle',set_damage=True),11)
  self.assertEqual((a.hp,b.hp,a.injuries),(45,99,5));self.assertEqual(a.move_uses,{'struggle':1})
  p,=self.standard(e);self.assertEqual(p['status'],'applied');self.assertEqual(p['actual_action_count'],1)
  self.assertTrue(p['outcome']['hit']);self.assertEqual(p['heavy_consequence']['amount'],5)
  self.assertEqual(a.budget['standard'],0);self.assertFalse(e._heavy_standard_receipts)
 def test_002_native_miss_still_is_one_standard(self):
  e,a,b=self.pair(seed=31);self.assertEqual(e.use_move(a,b,'struggle',set_damage=True),0)
  self.assertEqual((a.hp,b.hp),(45,110));p,=self.standard(e)
  self.assertFalse(p['outcome']['hit']);self.assertEqual(p['actual_action_count'],1)
  self.assertEqual(a.move_uses,{'struggle':1});self.assertEqual(len(e._heavy_events),1)
 def test_003_temporary_hp_consumed_first(self):
  for temp,want in [(3,(48,0)),(8,(50,3))]:
   e,a,b=self.pair();self.grant_temp(e,a,temp);e.use_move(a,b,'struggle',set_damage=True)
   self.assertEqual((a.hp,a.temp_hp),want);self.assertEqual(a.injuries,5)
 def test_004_seven_stable_injuries_lose_seven(self):
  e,a,b=self.pair(inj=7);a.hp=30;e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(a.hp,23);self.assertEqual(self.standard(e)[0]['heavy_consequence']['amount'],7)
 def test_005_reservation_alone_does_not_prove_action(self):
  e,a,b=self.pair();self.assertTrue(TURN.spend(e,a,'standard','test-only reservation'))
  self.assertEqual(a.hp,50);self.assertFalse(self.standard(e));self.assertFalse(a.move_uses)
 def test_006_no_budget_request_does_not_trigger(self):
  e,a,b=self.pair();a.budget['standard']=0;self.assertEqual(e.use_move(a,b,'struggle'),0)
  self.assertEqual(a.hp,50);self.assertFalse(self.standard(e));self.assertFalse(a.move_uses)
 def test_007_out_of_turn_request_does_not_trigger(self):
  e,a,b=self.pair();b.injuries=5;self.assertEqual(e.use_move(b,a,'struggle'),0)
  self.assertEqual(b.hp,110);self.assertFalse(self.standard(e));self.assertFalse(b.move_uses)
 def test_008_frequency_refusal_does_not_trigger(self):
  e,a,b=self.pair();a.move_uses['move/파괴광선']=999
  self.assertEqual(e.use_move(a,b,'move/파괴광선'),0);self.assertEqual(a.hp,50)
  self.assertFalse(self.standard(e));self.assertEqual(a.move_uses['move/파괴광선'],999)
 def test_009_preuse_rejection_has_no_certified_standard_occurrence(self):
  e,a,b=self.pair();a.registry.append({'type':'usage_restriction','only_if':'asleep'})
  self.assertEqual(e.use_move(a,b,'struggle'),0);self.assertEqual(a.hp,50)
  self.assertFalse(self.standard(e));self.assertFalse(a.move_uses);self.assertEqual(a.budget['standard'],0)
 def test_010_ungranted_free_or_count_bypass_does_not_trigger(self):
  for kwargs in [{'free_action':True},{'count_use':False}]:
   e,a,b=self.pair();self.assertEqual(e.use_move(a,b,'struggle',**kwargs),0)
   self.assertEqual(a.hp,50);self.assertFalse(self.standard(e));self.assertFalse(a.move_uses)
 def test_011_loss_marker_faint_and_cap_are_pending_not_auto(self):
  for field,value in [('hp',63),('hp',5),('damage_cap',{'value':'max_hp/2','applies_to':'damage and hp loss'})]:
   e,a,b=self.pair();setattr(a,field,value);hp=a.hp;rng=e.rng.getstate()
   with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
   self.assertEqual((a.hp,b.hp),(hp,110));self.assertEqual(e.rng.getstate(),rng)
   p,=self.standard(e);self.assertIsNone(p['actual_action_count']);self.assertFalse(p['semantic_commit_proven'])
   self.assertEqual(p['kind'],'activation_observed');self.assertEqual(a.move_uses,{'struggle':1})
 def test_012_unknown_effects_preserve_unresolved_activation_evidence(self):
  e,a,b=self.pair();a.modifiers.append({'type':'test_only_unknown'})
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle')
  p,=self.standard(e);self.assertEqual(p['status'],'pending');self.assertIn('attacker:modifiers',p['issues'])
  self.assertFalse(p['semantic_commit_proven']);self.assertEqual((a.hp,b.hp),(50,110))
 def test_013_target_injury_or_boundary_not_certified(self):
  for change in [lambda b:setattr(b,'injuries',1),lambda b:setattr(b,'hp',65)]:
   e,a,b=self.pair();change(b);before=b.hp
   with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle')
   self.assertEqual((a.hp,b.hp),(50,before));self.assertFalse(self.standard(e)[0]['semantic_commit_proven'])
 def test_014_public_diagnostic_is_not_authority(self):
  e,a,b=self.pair();diagnostic=S.diagnose(e,a,b,e.r.move('struggle'),{},True)
  with self.assertRaises((ValueError,TypeError)):S.finish(e,diagnostic,hit=True,dealt=11)
  self.assertEqual(a.hp,50);self.assertFalse(self.standard(e))
 def test_015_finished_event_cannot_be_replayed(self):
  e,a,b=self.pair();e.use_move(a,b,'struggle',set_damage=True)
  with self.assertRaises(ValueError):S.finish(e,object(),hit=True,dealt=11)
  self.assertEqual(a.hp,45);self.assertEqual(len(self.standard(e)),1)
 def test_016_snapshot_restores_event_and_identity_without_second_loss(self):
  e,a,b=self.pair();e.use_move(a,b,'struggle',set_damage=True);e.gm.snapshot('applied')
  a.hp=1;e.gm.restore('applied');p,=self.standard(e)
  self.assertIs(p['target'],a);self.assertIs(p['action_target'],b);self.assertEqual(a.hp,45)
  self.assertEqual(e.use_move(a,b,'struggle'),0);self.assertEqual(a.hp,45);self.assertEqual(len(self.standard(e)),1)
 def test_017_pending_snapshot_blocks_boundary_without_loss(self):
  e,a,b=self.pair();a.hp=63
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle')
  event=e._heavy_pending;e.gm.snapshot('pending');a.hp=10;e.gm.restore('pending')
  self.assertEqual(a.hp,63);self.assertEqual(e._heavy_pending,event)
  with self.assertRaises(H.HeavyPending):e.end_of_turn(a)
  self.assertEqual(e.elapsed_seconds,0)
 def test_018_under_five_is_unchanged(self):
  e,a,b=self.pair(inj=4);e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(a.hp,50);self.assertFalse(self.standard(e))
 def test_019_no_rng_provider_callback_certification(self):
  e,a,b=self.pair();e.d20=lambda:20
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle')
  self.assertEqual((a.hp,b.hp),(50,110));self.assertIn('overridden_engine_method:d20',self.standard(e)[0]['issues'])
 def test_020_seeded_both_orders_agree_in_resources_frequency_and_rng(self):
  for seed in range(40):
   e,a,b=self.pair(seed);f,c,d=self.pair(seed,engine_cls=self.BaselineEngine)
   e.use_move(a,b,'struggle',set_damage=False)
   # Historical pre-Standard Engine is an independent native-use oracle.
   # The actor retains the same five injuries; only HP is reduced first.
   c.hp-=5
   f.use_move(c,d,'struggle',set_damage=False)
   self.assertEqual((a.hp,a.injuries,b.hp,b.injuries,a.move_uses,e.rng.getstate()),(c.hp,c.injuries,d.hp,d.injuries,c.move_uses,f.rng.getstate()))
 def test_021_same_named_engine_subclass_is_not_certified(self):
  Impostor=type('Engine',(Engine,),{})
  e,a,b=self.pair(engine_cls=Impostor)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual((a.hp,b.hp),(50,110));self.assertIn('noncanonical_runtime_type',self.standard(e)[0]['issues'])
 def test_022_same_named_actor_subclass_is_not_certified(self):
  e,a,b=self.pair();Impostor=type('Combatant',(Combatant,),{})
  a.__class__=Impostor
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual((a.hp,b.hp),(50,110));self.assertIn('noncanonical_runtime_type',self.standard(e)[0]['issues'])
 def test_023_log_callback_is_not_certified(self):
  e,a,b=self.pair();records=[];e.log=lambda *args:records.append(a.hp)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual((a.hp,b.hp),(50,110));self.assertIn('overridden_engine_method:log',self.standard(e)[0]['issues'])
 def test_024_real_receipt_consumed_once_before_return(self):
  e,a,b=self.pair();original=S.finish;seen=[]
  def finish_once(engine,token,**kwargs):
   seen.append(token);original(engine,token,**kwargs)
   with self.assertRaises(ValueError):original(engine,token,**kwargs)
  with mock.patch.object(S,'finish',finish_once):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(len(seen),1);self.assertEqual(a.hp,45)
  with self.assertRaises(ValueError):original(e,seen[0],hit=True,dealt=11)
  self.assertEqual(a.hp,45)
 def test_025_rng_instance_hp_callback_is_not_certified(self):
  e,a,b=self.pair();calls=[]
  def dependent_randint(lo,hi):
   calls.append(a.hp);return 20 if a.hp>47 else 1
  e.rng.randint=dependent_randint
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(calls,[]);self.assertEqual((a.hp,b.hp),(50,110))
  p,=self.standard(e);self.assertFalse(p['semantic_commit_proven'])
  self.assertIn('rng_instance_state_not_native',p['issues'])
 def test_026_log_list_subclass_hp_observer_is_not_certified(self):
  e,a,b=self.pair();seen=[]
  class HPLog(list):
   def append(self,line):
    if '명중 d20' in line:
     seen.append(a.hp)
     if a.hp>47:b.stats['def']=0
    super().append(line)
  e.log_lines=HPLog(e.log_lines)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(seen,[]);self.assertEqual((a.hp,b.hp,b.stats['def']),(50,110,30))
  p,=self.standard(e);self.assertFalse(p['semantic_commit_proven'])
  self.assertIn('noncanonical_log_sink',p['issues'])
 def test_027_noncallable_rng_method_shadow_is_held_before_rng_use(self):
  e,a,b=self.pair();e.rng.getrandbits=17
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual((a.hp,b.hp),(50,110))
  self.assertIn('rng_instance_state_not_native',self.standard(e)[0]['issues'])
 def test_028_stats_dictionary_hp_observer_is_not_certified(self):
  e,a,b=self.pair();seen=[]
  class HPStats(dict):
   def __getitem__(self,key):
    if key=='atk':
     seen.append(a.hp)
     if a.hp<=47:return 0
    return super().__getitem__(key)
  a.stats=HPStats(a.stats)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(seen,[]);self.assertEqual((a.hp,b.hp),(50,110))
  self.assertIn('actor:nonplain_stats',self.standard(e)[0]['issues'])
 def test_029_stats_numeric_subclass_hp_observer_is_not_certified(self):
  e,a,b=self.pair();seen=[]
  class HPNumber(int):
   def __mul__(self,value):
    seen.append(a.hp);return (30 if a.hp>47 else 0)*value
  a.stats['atk']=HPNumber(30)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(seen,[]);self.assertEqual((a.hp,b.hp),(50,110))
  self.assertIn('actor:nonplain_stats',self.standard(e)[0]['issues'])
 def test_030_situational_numeric_subclass_is_not_certified(self):
  e,a,b=self.pair();seen=[]
  class HPAccuracy(int):
   def __radd__(self,value):
    seen.append(a.hp);return value+(20 if a.hp>47 else -20)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',situational=HPAccuracy(0),set_damage=True)
  self.assertEqual(seen,[]);self.assertEqual((a.hp,b.hp),(50,110))
  self.assertIn('nonplain_public_move_inputs',self.standard(e)[0]['issues'])
 def test_031_nonboolean_public_flags_do_not_certify(self):
  for kwargs in [{'count_use':1},{'free_action':0}]:
   e,a,b=self.pair()
   with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',**kwargs)
   self.assertEqual((a.hp,b.hp),(50,110))
   self.assertIn('nonplain_public_move_inputs',self.standard(e)[0]['issues'])
  e,a,b=self.pair();before=(a.hp,b.hp,dict(a.budget),list(a._action_history),dict(a.move_uses),e.rng.getstate())
  with self.assertRaisesRegex(ValueError,'boolean Set Damage'):e.use_move(a,b,'struggle',set_damage=1)
  self.assertEqual((a.hp,b.hp,a.budget,a._action_history,a.move_uses,e.rng.getstate()),before)
  self.assertFalse(e._heavy_events);self.assertFalse(e._heavy_pending)
 def test_032_stages_dictionary_observer_is_not_certified(self):
  e,a,b=self.pair();seen=[]
  class HPStages(dict):
   def __getitem__(self,key):
    seen.append(a.hp);return 6 if a.hp>47 else 0
  a.stages=HPStages(a.stages)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(seen,[]);self.assertEqual((a.hp,b.hp),(50,110))
  self.assertIn('actor:nonplain_stages',self.standard(e)[0]['issues'])
 def test_033_budget_hp_observer_is_not_certified(self):
  e,a,b=self.pair()
  class HPBudget(dict):
   def get(self,key,default=None):
    if key=='standard' and a.hp<=47:return 0
    return super().get(key,default)
  a.budget=HPBudget(a.budget)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual((a.hp,b.hp),(50,110))
  self.assertIn('actor:nonpassive_state:budget',self.standard(e)[0]['issues'])
 def test_034_name_format_observer_is_not_certified(self):
  e,a,b=self.pair();seen=[]
  class HPName(str):
   def __format__(self,fmt):
    seen.append(a.hp)
    if a.hp>47:b.stats['def']=0
    return str.__format__(self,fmt)
  a.name=HPName(a.name)
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(a.hp,50);self.assertEqual(seen,[]);self.assertEqual(b.stats['def'],30)
  self.assertFalse(self.standard(e)[0]['semantic_commit_proven'])
  self.assertIn('actor:nonpassive_state:spec',self.standard(e)[0]['issues'])
 def test_035_prefix_passive_contract_checks_container_families(self):
  for owner,field,make in [
   ('actor','registry',lambda v:type('SequenceObserver',(list,),{})(v)),
   ('actor','custom_conditions',lambda v:type('MappingObserver',(dict,),{})(v)),
   ('actor','_action_history',lambda v:type('HistoryObserver',(list,),{})(v)),
   ('actor','pending_action_loss',lambda v:type('PendingObserver',(dict,),{})(standard=1)),
   ('engine','zones',lambda v:type('ZonesObserver',(dict,),{})(v)),
   ('engine','effect_stats',lambda v:type('StatsObserver',(dict,),{})(v))]:
   e,a,b=self.pair();obj=a if owner=='actor' else e
   setattr(obj,field,make(getattr(obj,field,None)))
   d=S.diagnose(e,a,b,e.r.move('struggle'),{},True,public_inputs=dict(situational=0,set_damage=True,count_use=True,free_action=False))
   self.assertIn(owner+':nonpassive_state:'+field,d['failures'])
 def test_036_changed_damage_bound_semantics_are_not_certified(self):
  for uid,key,value in [('combat/damage-formula','attack_stat_by_class',{'물리':'spa'}),
                         ('combat/combat-stage-multipliers','multiplier_by_stage',{'0':2})]:
   e,a,b=self.pair();table=e.r.mech(uid);old=copy.deepcopy(table[key])
   try:
    table[key].update(value)
    with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
    self.assertIn('native_damage_bound_semantics_changed',self.standard(e)[0]['issues'])
    self.assertEqual((a.hp,b.hp),(50,110))
   finally:table[key]=old
 def test_037_passive_normal_reference_and_pending_debt_are_supported_data(self):
  e,a,b=self.pair();a.last_target=b;a.pending_action_loss={'shift':1}
  self.assertEqual(H.passive_prefix_failures(e,a,b,require_actor_budget=True),[])
  # This debt is a turn-start input; current native use does not consume it.
  e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual((a.hp,b.hp,a.pending_action_loss),(45,99,{'shift':1}))
 def test_038_gained_or_unexpected_struggle_keywords_remain_pending(self):
  import musician as MUSIC
  for kind in ('gained','unexpected'):
   with self.subTest(kind=kind):
    e,a,b=self.pair();original=MUSIC.project_move
    if kind=='gained':
     FX.run_effects(e,a,a,[{'type':'gain_keyword','keyword':'소리','target':'self'}],
                    {'attacker':a,'target':a,'engine':e,'hit':True},'gm/keyword-negative')
     self.assertIn('소리',MUSIC.project_move(e,a,e.r.move('struggle'))['keywords'])
    def projected(engine,actor,move):
     actual=original(engine,actor,move)
     return dict(actual,keywords=['unreviewed']) if kind=='unexpected' else actual
    with mock.patch.object(MUSIC,'project_move',projected):
     with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
    self.assertEqual((a.hp,b.hp),(50,110))
    packet=self.standard(e)[0]
    self.assertFalse(packet['semantic_commit_proven']);self.assertEqual(packet['status'],'pending')
    self.assertIn('not_empty_mech_native_struggle',packet['issues'])
class Results(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='HEAVY-STANDARD-'+t._testMethodName,status='pass'))
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='HEAVY-STANDARD-'+t._testMethodName,status='fail',detail=self._exc_info_to_string(e,t)))
 def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='HEAVY-STANDARD-'+t._testMethodName,status='error',detail=self._exc_info_to_string(e,t)))
if __name__=='__main__':
 def tracing(original):
  def read(file,mode='r',*args,**kwargs):
   if 'r' in mode or '+' in mode:
    try:
     path=pathlib.Path(file).resolve()
     if path.is_relative_to(ROOT) and path.is_file():READ_INPUTS.add(path)
    except (TypeError,ValueError,OSError):pass
   return original(file,mode,*args,**kwargs)
  return read
 original_open,original_io=builtins.open,io.open
 builtins.open,io.open=tracing(original_open),tracing(original_io)
 try:result=unittest.TextTestRunner(verbosity=2,resultclass=Results).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 finally:builtins.open,io.open=original_open,original_io
 paths=sorted(READ_INPUTS | set((ROOT/'engine').glob('*.py')) | {pathlib.Path(__file__).resolve(),ROOT/'input/ch07-combat.md',ROOT/'tests/fixtures/heavy_standard_historical_engine.py',ROOT/'data/verification/common-standard-action-heavy-contract.json'})
 report=dict(generated_at=datetime.now(timezone.utc).isoformat(),tests_run=result.testsRun,results=result.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},semantic_closure=False,scope='Restricted actual native Standard-use confluence only; unknown activation commit is pending')
 (ROOT/'output/heavy-standard-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 sys.exit(0 if result.wasSuccessful() else 1)
