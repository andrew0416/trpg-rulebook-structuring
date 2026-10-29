"""Selected hb-weather foundation: native producer, lifetime and restoration."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from ruleset import build_runtime_selection
from state_codec import StateCodecError
import test_category2_weather_state as _fixture_test_category2_weather_state
import homebrew_weather as H,weather_state as W,turn as TURN,effects as FX

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=Rules(ROOT,ruleset='homebrew')
  cls.core=Rules(ROOT,ruleset='core');cls.errata=Rules(ROOT,ruleset='core+errata')
  cls._weather_fixture_rulings=deepcopy(cls.r.rulings)
 def fixture(self):
  self.r.rulings=deepcopy(self._weather_fixture_rulings)
  return _fixture_test_category2_weather_state.Tests.fixture(self)
 def restored(self,e):return Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
 def cast(self,e,actor,other,move):
  e.start_round([actor,other]);e.start_of_turn(actor,initiative_count=12)
  e.use_move(actor,actor,move);e.end_of_turn(actor)
 def resources(self,e,actor):
  return deepcopy((getattr(actor,'budget',None),actor.move_uses,e.rng.getstate(),
                   getattr(e,W.KEY,None),e.weather,e.weather_rounds,actor.hp))
 def test_four_native_moves_and_both_actor_kinds_keep_metadata_and_real_costs(self):
  for move,row in H.policy(self.r)['moves'].items():
   for kind in ('trainer','pokemon'):
    with self.subTest(move=move,kind=kind):
     e,a,b=self.fixture();user=a if kind=='trainer' else b;other=b if user is a else a
     if user is b:e.gm.observe_loyalty(b,6,reason='actual known obedience')
     raw=deepcopy(self.r.moves[move]);native=self.r.move(move)
     self.assertEqual(tuple(native[key] for key in ('frequency','ac','class','range')),('하루 x2',None,'변화','필드, 날씨, 축복'))
     self.assertEqual(native['keywords'],['날씨','축복']);self.assertEqual(native['type'],row['type'])
     self.assertEqual(native['_weather_policy']['source_id'],'hb-weather')
     self.assertEqual(self.r.moves[move],raw)
     self.cast(e,user,other,move)
     self.assertEqual(user.budget['standard'],0);self.assertEqual(user.move_uses[move],1)
     self.assertEqual((e.weather,e.weather_rounds),(row['weather'],None))
     active=e._weather_state['active'];self.assertEqual(active['source_id'],move)
     self.assertEqual(active['actor_id'],user.entity_id);self.assertEqual(active['policy'],H.provenance(move))
     self.assertEqual(active['started_seconds'],e.round_start_seconds)
     self.assertIsNone(active['duration']);self.assertIsNone(active['deadline_round'])
     import blessing_effects as B
     import weather_blessings as WB
     pools=[r for c in (a,b) for r in B.live(c) if WB.is_weather(r)]
     self.assertEqual(len(pools),1);pool=pools[0]
     self.assertIn(pool,user.blessings);self.assertEqual(B.remaining(pool),2)
     self.assertEqual(B.side(pool),user.side)
     self.assertEqual(pool['weather_occurrence_id'],active['id'])
     self.assertEqual(pool['effect'],{'kind':'weather_effectiveness',
                      'boost_types':row['boost_types'],'reduce_type':row['reduce_type']})
     self.assertTrue(e.validate_state()['valid']);self.restored(e)
 def test_actual_source_admission_and_exclusion_do_not_depend_on_profile_name(self):
  r=Rules(ROOT,ruleset='core');r.ruleset.sources.add('hb-weather');r.selection=build_runtime_selection(r)
  self.assertEqual(r.ruleset.name,'core');self.assertTrue(H.enabled(r))
  self.assertIsNone(r.move_mech('move/비바라기')[0]['effects_exec'][0]['rounds'])
  r.selection.excluded['hb-weather']='exclude_units'
  self.assertFalse(H.enabled(r));self.assertEqual(r.move_mech('move/비바라기')[0]['effects_exec'][0]['rounds'],5)
 def test_core_and_core_errata_keep_finite_weather_and_ambient_effects(self):
  for r in (self.core,self.errata):
   with self.subTest(profile=r.ruleset.name):
    e=Engine(r,58);e.gm.set_weather('sunny')
    self.assertFalse(H.enabled(r));self.assertEqual(r.move_mech('move/쾌청')[0]['effects_exec'][0]['rounds'],5)
    self.assertNotIn('축복',r.move('move/쾌청')['keywords'])
    c=Combatant(r,dict(id='core/check',name='C',kind='trainer',level=25,stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),20)))
    e.everyone=e.gm.everyone=[c]
    self.assertEqual(TURN.weather_damage_mod(e,c,r.move('move/불꽃세례')),5)
    e.gm.set_weather('hail');before=c.hp;TURN.weather_turn_start(e,c);self.assertLess(c.hp,before)
    e.end_encounter();self.assertEqual(e.weather,'hail');self.restored(e)
 def test_source_and_declarative_policy_drift_are_rejected_without_rule_cache_mutation(self):
  original=Path.read_bytes;before=set(vars(self.r))
  for relative in ('input/hb-weather.md','data/homebrew-weather-policy.json'):
   with self.subTest(file=relative):
    target=ROOT/relative
    def read(path):return original(path)+(b'\n' if path==target else b'')
    with patch.object(Path,'read_bytes',read):
     with self.assertRaisesRegex(ValueError,'changed'):self.r.move('move/비바라기')
  self.assertEqual(set(vars(self.r)),before)
 def test_weather_survives_more_than_five_rounds_then_actual_encounter_end(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/비바라기')
  for _ in range(7):e.start_round([a,b]);self.assertEqual((e.weather,e.weather_rounds),('rain',None))
  e.end_encounter();self.assertIsNone(e.weather);self.assertIsNone(e._weather_state['active'])
  self.assertEqual(e._weather_state['history'][-1]['end_reason'],'encounter ended');self.restored(e)
 def test_replacement_gm_clear_and_independent_finite_weather_have_distinct_lifetimes(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/비바라기');self.cast(e,a,b,'move/쾌청')
  self.assertEqual(e.weather,'sunny');self.assertEqual(e._weather_state['history'][-1]['end_reason'],'replaced')
  self.assertEqual(e._weather_state['history'][-1]['source_id'],'move/비바라기')
  e.gm.set_weather('hail',rounds=3,reason='independent GM weather')
  self.assertNotIn('policy',e._weather_state['active']);e.end_encounter()
  self.assertEqual((e.weather,e.weather_rounds),('hail',3));self.restored(e)
  e.gm.set_weather(None);self.assertIsNone(e.weather);self.restored(e)
 def test_native_daily_two_limit_uses_actual_activations(self):
  e,a,b=self.fixture()
  self.cast(e,a,b,'move/비바라기');self.cast(e,a,b,'move/쾌청')
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12);before=self.resources(e,a)
  self.assertEqual(e.use_move(a,a,'move/비바라기'),0)
  self.assertEqual(self.resources(e,a),before);self.assertEqual(a.move_uses['move/비바라기'],1)
  e.end_of_turn(a);e.end_scene();self.cast(e,a,b,'move/비바라기');e.end_scene()
  self.assertEqual(a.move_uses['move/비바라기'],2)
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12);before=self.resources(e,a)
  self.assertEqual(e.use_move(a,a,'move/비바라기'),0)
  self.assertEqual(self.resources(e,a),before);self.assertIsNone(e.weather)
 def test_same_weather_no_ruling_rejects_before_cost_or_rng(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/비바라기')
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12);before=self.resources(e,a)
  with self.assertRaisesRegex(ValueError,'same-weather'):e.use_move(a,a,'move/비바라기')
  self.assertEqual(self.resources(e,a),before)
 def test_missing_encounter_and_unregistered_actor_reject_before_native_cost(self):
  e,a,b=self.fixture();before=self.resources(e,a)
  with self.assertRaisesRegex(ValueError,'open encounter'):e.use_move(a,a,'move/비바라기')
  self.assertEqual(self.resources(e,a),before)
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12)
  stranger=Combatant(self.r,dict(a.spec,id='weather/stranger'))
  before=self.resources(e,stranger)
  with self.assertRaises(ValueError):e.use_move(stranger,a,'move/비바라기')
  self.assertEqual(self.resources(e,stranger),before)
 def test_intrinsic_damage_tick_and_save_removed_but_actual_solarbeam_condition_retained(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/쾌청')
  self.assertTrue(FX.weather_matches(e,'sunny'));self.assertEqual(TURN.weather_damage_mod(e,a,self.r.move('move/불꽃세례')),0)
  self.assertEqual(TURN.weather_damage_mod(e,a,self.r.move('move/물대포')),0)
  e.gm.set_move(a,'move/솔라빔',reason='actual learned Move')
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12)
  self.assertGreater(e.use_move(a,b,'move/솔라빔',set_damage=True),0);self.assertIsNone(a.setup_move)
  e.end_of_turn(a);e.gm.set_weather('hail',rounds=2);before=b.hp
  TURN.weather_turn_start(e,b);self.assertEqual(b.hp,before)
  self.assertEqual(TURN.weather_save_mod(e,'얼음'),0);self.assertTrue(FX.weather_matches(e,'hail'))
 def test_existing_explicit_gm_effect_override_is_applied_after_policy_overlay(self):
  r=Rules(ROOT,ruleset='homebrew');e=Engine(r,58)
  e.rule_effect('move/비바라기','set',{'effects_exec':[{'type':'set_weather','weather':'sunny','rounds':2}]},reason='explicit table weather override',scope='scene')
  mm,confidence=r.move_mech('move/비바라기')
  self.assertEqual(mm['effects_exec'],[{'type':'set_weather','weather':'sunny','rounds':2}]);self.assertIn('+gm',confidence)
  e.everyone=e.gm.everyone=[Combatant(r,dict(id='gm/native',name='GM actor',kind='trainer',level=25,
                                          moves=['move/비바라기'],stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),20)))]
  actor=e.gm.everyone[0];self.cast(e,actor,actor,'move/비바라기')
  self.assertEqual((e.weather,e.weather_rounds),('sunny',2));self.restored(e)
  e.end_scene();self.assertNotIn('move/비바라기',r.rulings.effects)
  self.assertEqual((e.weather,e.weather_rounds),('sunny',2));self.restored(e)
  e.gm.set_weather('hail');self.assertIn('policy_override',e._weather_state['history'][-1]);self.restored(e)

 def test_unmarked_native_policy_mismatch_rejects_before_replacing_existing_weather(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/쾌청');before=self.resources(e,a)
  with self.assertRaisesRegex(ValueError,'differs from selected'):
   W.set_weather(e,'rain',rounds=5,source_id='move/비바라기',origin='move',actor=a)
  self.assertEqual(self.resources(e,a),before)
 def test_snapshot_codec_wrong_profile_and_tampering_reject_atomically(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/비바라기');e.gm.snapshot('weather')
  self.cast(e,a,b,'move/쾌청');e.gm.restore('weather')
  self.assertEqual(e.weather,'rain');n=self.restored(e);self.assertEqual(n._weather_state,e._weather_state)
  with self.assertRaises(StateCodecError):Engine.import_state(self.core,e.export_state())
  saved=e.gm.snapshots['weather'];saved['engine'][W.KEY]['active']['policy']['source_id']='forged'
  before=self.resources(e,a)
  with self.assertRaises(ValueError):e.gm.restore('weather')
  self.assertEqual(self.resources(e,a),before)
  for field,value in (('duration',5),('actor_id','missing/actor'),('source_id','move/박치기'),('manual_end',True),('policy',None)):
   with self.subTest(field=field):
    payload=e.export_state()
    node=next(row for row in payload['nodes'].values() if row['kind']=='dict' and any(pair[0]=='started_seconds' for pair in row['items']))
    node['items']=[pair for pair in node['items'] if pair[0]!=field];node['items'].append([field,value])
    with self.assertRaises(StateCodecError):Engine.import_state(e.r,json.loads(json.dumps(payload,ensure_ascii=False)))

 def test_four_same_weather_native_recasts_use_recorded_gm_replace_and_real_costs(self):
  for move in H.policy(self.r)['moves']:
   with self.subTest(move=move):
    e,a,b=self.fixture();e.gm.observe_loyalty(b,6,reason='known obedience')
    self.cast(e,a,b,move);old=deepcopy(e._weather_state['active'])
    e.rule_mech('hb-weather','same_weather_reapplication','replace',reason='GM chooses a new occurrence on recast',scope='scene')
    self.cast(e,b,a,move)
    active=e._weather_state['active']
    self.assertEqual(active['id'],old['id']+1)
    self.assertEqual(active['reapplication'],{'previous_occurrence_id':old['id'],'ruling':{
     'value':'replace','scope':'scene','reason':'GM chooses a new occurrence on recast'}})
    self.assertEqual(active['actor_id'],b.entity_id)
    self.assertEqual(b.move_uses[move],1);self.assertEqual(b.budget['standard'],0)
    self.assertEqual(e._weather_state['history'][-1]['end_reason'],'replaced')
    self.assertIsNone(e.weather_rounds)
    e.gm.snapshot('recast');e.gm.set_weather(None);e.gm.restore('recast')
    n=self.restored(e);self.assertEqual(n._weather_state,e._weather_state)
    n.end_scene();self.assertNotIn('hb-weather',n.rulings.mech)
    self.assertIsNone(n.weather);self.assertEqual(n._weather_state['history'][-1]['reapplication'],active['reapplication'])
    self.restored(n)

 def test_same_weather_invalid_rulings_preserve_all_native_resources(self):
  for value,reason,scope in [('replace','','scene'),('retain','explicit','scene'),
                             ('replace','explicit','once'),(True,'explicit','campaign')]:
   with self.subTest(value=value,reason=reason,scope=scope):
    e,a,b=self.fixture();e.gm.observe_loyalty(b,6,reason='known obedience')
    self.cast(e,a,b,'move/비바라기')
    e.rule_mech('hb-weather','same_weather_reapplication',value,reason=reason,scope=scope)
    e.start_round([a,b]);e.start_of_turn(b,initiative_count=12);before=self.resources(e,b)
    with self.assertRaisesRegex(ValueError,'same-weather'):e.use_move(b,b,'move/비바라기')
    self.assertEqual(self.resources(e,b),before)

 def test_reapplication_receipt_cannot_be_removed_or_relinked_on_restore(self):
  e,a,b=self.fixture();e.gm.observe_loyalty(b,6,reason='known obedience')
  self.cast(e,a,b,'move/모래바람')
  e.rule_mech('hb-weather','same_weather_reapplication','replace',reason='explicit replacement',scope='campaign')
  self.cast(e,b,a,'move/모래바람');baseline=deepcopy(e._weather_state)
  mutations=[lambda r:r.pop('reapplication'),
             lambda r:r['reapplication'].__setitem__('previous_occurrence_id',999),
             lambda r:r['reapplication'].__setitem__('previous_occurrence_id',True),
             lambda r:r['reapplication']['ruling'].__setitem__('value','retain'),
             lambda r:r['reapplication']['ruling'].__setitem__('reason','')]
  for mutate in mutations:
   e._weather_state=deepcopy(baseline);e.gm.snapshot('candidate')
   mutate(e.gm.snapshots['candidate']['engine'][W.KEY]['active'])
   with self.assertRaises(ValueError):e.gm.restore('candidate')
   self.assertEqual(e._weather_state,baseline)
   mutate(e._weather_state['active'])
   self.assertFalse(e.validate_state()['valid'])
   with self.assertRaises(StateCodecError):e.export_state()
  e._weather_state=baseline;self.restored(e)

 def test_different_weather_does_not_apply_same_weather_ruling(self):
  e,a,b=self.fixture();self.cast(e,a,b,'move/비바라기')
  e.rule_mech('hb-weather','same_weather_reapplication','replace',reason='only same weather',scope='campaign')
  self.cast(e,a,b,'move/쾌청')
  self.assertNotIn('reapplication',e._weather_state['active']);self.restored(e)
