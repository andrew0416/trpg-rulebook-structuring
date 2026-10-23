"""Sourced global weather, actual round/count boundaries and persistence."""
import json
from copy import deepcopy
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from state_codec import StateCodecError
import weather_state as W, combat_timing as TIMING, effects_ext as EXT, turn as TURN
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def fixture(self):
  e=Engine(self.r,58);base=dict(level=25,stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),moves=['move/'+name for name in ('비바라기','쾌청','모래바람','싸라기눈')])
  a=Combatant(self.r,dict(base,id='weather/trainer',name='T',kind='trainer'))
  b=Combatant(self.r,dict(base,id='weather/pokemon',name='P',kind='pokemon',trainer_id=a.entity_id))
  e.everyone=e.gm.everyone=[a,b];return e,a,b
 def restore(self,e):return Engine.import_state(self.r,json.loads(json.dumps(e.export_state())))
 def test_native_moves_replace_one_battlefield_weather_with_actual_source(self):
  e,a,b=self.fixture()
  for move,weather in [('비바라기','rain'),('쾌청','sunny'),('모래바람','sandstorm'),('싸라기눈','hail')]:
   e.start_round([a,b]);e.start_of_turn(a,initiative_count=12)
   e.use_move(a,a,'move/'+move)
   e.end_of_turn(a);e.end_round()
   self.assertEqual((e.weather,e.weather_rounds),(weather,5))
   active=e._weather_state['active'];self.assertEqual(active['source_id'],self.r.move('move/'+move)['id']);self.assertEqual(active['actor_id'],a.entity_id)
   for actor in (a,b):self.assertEqual(TURN.weather_damage_mod(e,actor,self.r.move('move/불꽃세례')),{'rain':-5,'sunny':5,'sandstorm':0,'hail':0}[weather])
  self.assertEqual(len(e._weather_state['history']),3)
  self.assertTrue(all(r['end_reason']=='replaced' for r in e._weather_state['history']))
  self.restore(e)
 def test_move_lasts_five_rounds_until_its_original_initiative_count(self):
  e,a,b=self.fixture();e.start_round([a,b]);TIMING.at_count(e,12)
  e.start_of_turn(a,initiative_count=12);e.use_move(a,a,'move/비바라기');e.end_of_turn(a)
  for _ in range(5):e.start_round([a,b])
  self.assertEqual(e.round_no,6);self.assertEqual(e.weather,'rain')
  TIMING.at_count(e,13);self.assertEqual(e.weather,'rain')
  n=self.restore(e);TIMING.at_count(n,12)
  self.assertIsNone(n.weather);self.assertIsNone(n.weather_rounds)
  self.assertEqual(n._weather_state['history'][-1]['end_reason'],'duration expired')
 def test_pre_encounter_weather_survives_five_completed_rounds_not_five_calls(self):
  e,a,b=self.fixture();e.gm.set_weather('sunny')
  for rnd in range(1,6):
   e.start_round([a,b]);self.assertEqual((e.weather,e.weather_rounds),('sunny',6-rnd))
   for _ in range(3):TURN.weather_round_tick(e)
   self.assertEqual(e.weather,'sunny');e.end_round()
   self.assertEqual(e.weather,None if rnd==5 else 'sunny')
 def test_natural_observation_is_not_mechanical_without_explicit_gm_classification(self):
  e,a,b=self.fixture()
  for description in ('sunny','rain','비바라기 같은 비'):
   e.gm.observe_natural_weather(description);self.assertIsNone(e.weather)
  before=deepcopy(e._weather_state)
  with self.assertRaises(ValueError):e.gm.observe_natural_weather('tropical storm',treat_as='rain')
  self.assertEqual(e._weather_state,before)
  e.gm.observe_natural_weather('tropical storm',treat_as='rain',reason='GM classifies severe tropical rain')
  for _ in range(7):e.start_round([a,b])
  self.assertEqual((e.weather,e.weather_rounds),('rain',None))
  n=self.restore(e);n.gm.observe_natural_weather('ordinary drizzle')
  self.assertIsNone(n.weather);self.assertIsNone(n._weather_state['natural']['equivalent'])
 def test_new_move_replaces_natural_equivalence_without_restoring_old_effect(self):
  e,a,b=self.fixture();e.gm.observe_natural_weather('tropical storm',treat_as='rain',reason='severe natural rain')
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12);e.use_move(a,a,'move/쾌청');e.end_of_turn(a)
  self.assertEqual(e.weather,'sunny')
  e.gm.observe_natural_weather('rain continues')
  self.assertEqual(e.weather,'sunny')
  for _ in range(5):e.start_round([a,b]);e.end_round()
  self.assertIsNone(e.weather);self.assertEqual(e._weather_state['natural']['description'],'rain continues')
 def test_invalid_duration_or_missing_count_is_rejected_before_cost(self):
  e,a,b=self.fixture()
  for duration in (0,-1,True,2.5):
   with self.assertRaises(ValueError):e.gm.set_weather('rain',rounds=duration)
   self.assertIsNone(e.weather);self.assertFalse(hasattr(e,'_weather_state'))
  e.start_round([a,b]);e.start_of_turn(a);before=(deepcopy(a.budget),deepcopy(a.move_uses),e.rng.getstate())
  with self.assertRaises(ValueError):e.use_move(a,a,'move/비바라기')
  self.assertEqual((a.budget,a.move_uses,e.rng.getstate()),before);self.assertIsNone(e.weather)
 def test_snapshot_and_codec_preserve_provenance_and_reject_desynchronization(self):
  e,a,b=self.fixture();e.gm.set_weather('sunny',reason='test active source');e.gm.snapshot('sun')
  e.gm.set_weather('rain');e.gm.restore('sun',reason='restore original weather')
  self.assertEqual((e.weather,e._weather_state['active']['reason']),('sunny','test active source'))
  n=self.restore(e);self.assertEqual(n._weather_state,e._weather_state)
  n.weather='rain'
  with self.assertRaises(StateCodecError):n.export_state()
  n.weather='sunny';deadline=n._weather_state['active']['deadline_round']
  n._weather_state['active']['deadline_round']=deadline+10
  with self.assertRaises(StateCodecError):n.export_state()
  n._weather_state['active']['deadline_round']=deadline
  n._weather_state['active']['duration']=-1
  with self.assertRaises(StateCodecError):n.export_state()
 def test_clearing_field_removes_timer_and_source_together(self):
  e,a,b=self.fixture();e.gm.set_weather('hail')
  EXT.h_clear_field(e,a,b,{'remove':['weather']},{'source_id':'gm/clear'})
  self.assertEqual((e.weather,e.weather_rounds,e._weather_state['active']),(None,None,None))
  self.assertEqual(e._weather_state['history'][-1]['end_source'],'gm/clear');self.restore(e)

 def test_actor_turn_cannot_skip_weather_deadline_or_take_expired_hail_damage(self):
  e,a,b=self.fixture();e.start_round([a,b]);TIMING.at_count(e,12)
  e.gm.set_weather('hail',rounds=1)
  e.start_round([a,b]);before=(b.hp,deepcopy(b.custom_conditions))
  with self.assertRaises(ValueError):e.start_of_turn(b)
  self.assertEqual((b.hp,b.custom_conditions),before)
  e.start_of_turn(b,initiative_count=12)
  self.assertIsNone(e.weather);self.assertEqual(b.hp,before[0]);e.end_of_turn(b)
  self.restore(e)
