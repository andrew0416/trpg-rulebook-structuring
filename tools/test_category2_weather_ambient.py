"""Selected ambient weather removal, separate from retained conditional sources."""
import unittest
from copy import deepcopy
from unittest.mock import patch
import test_category2_homebrew_weather as _fixture_test_category2_homebrew_weather
import turn as T,effects as F,effects_ext as X
from engine import Engine,Combatant

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_homebrew_weather.Tests.setUpClass.__func__)
 fixture=_fixture_test_category2_homebrew_weather.Tests.fixture
 restored=_fixture_test_category2_homebrew_weather.Tests.restored
 def test_all_four_weathers_remove_intrinsic_damage_tick_and_save_for_both_actor_kinds(self):
  for weather in ('sunny','rain','hail','sandstorm'):
   with self.subTest(weather=weather):
    e,a,b=self.fixture();e.gm.observe_loyalty(b,6,reason='known obedience')
    moves=[e.r.move('move/불꽃세례'),e.r.move('move/물대포')]
    baseline=[e.roll_damage(a,b,m,set_damage=True) for m in moves]
    e.gm.set_weather(weather,rounds=None,reason='observed independent weather')
    for actor in (a,b):
     for move in moves:self.assertEqual(T.weather_damage_mod(e,actor,move),0)
     hp=actor.hp;e.start_round([a,b]);e.start_of_turn(actor,initiative_count=12)
     self.assertEqual(actor.hp,hp);e.end_of_turn(actor)
    self.assertEqual([e.roll_damage(a,b,m,set_damage=True) for m in moves],baseline)
    for condition in ('화상','얼음','마비','수면'):self.assertEqual(T.weather_save_mod(e,condition),0)
    self.assertTrue(F.weather_matches(e,weather));self.restored(e)

 def test_native_weather_conditioned_healing_keeps_its_own_source_values(self):
  for move,favored in [('아침햇살','sunny'),('모래모으기','sandstorm')]:
   for weather in (None,'sunny','rain','hail','sandstorm'):
    with self.subTest(move=move,weather=weather):
     e,a,b=self.fixture();e.gm.set_move(a,'move/'+move,reason='known conditional healing')
     if weather:e.gm.set_weather(weather,rounds=None,reason='conditional weather')
     a.hp=1;e.start_round([a,b]);e.start_of_turn(a,initiative_count=12)
     num,den=(1,2) if weather is None else (2,3) if weather==favored else (1,4)
     e.use_move(a,a,'move/'+move)
     self.assertEqual(a.hp,1+a.max_hp*num//den)
     e.end_of_turn(a);self.restored(e)

 def test_weather_predicate_state_and_native_blizzard_accuracy_survive_both_restores(self):
  e,a,b=self.fixture();e.gm.set_move(a,'move/눈보라',reason='known weather attack')
  e.gm.set_weather('hail',rounds=None,reason='hail condition');e.gm.snapshot('hail')
  e.gm.set_weather('rain',rounds=None,reason='replace');e.gm.restore('hail')
  n=self.restored(e);aa,bb=n.gm.everyone
  self.assertEqual(n.weather,'hail');self.assertTrue(F.weather_matches(n,'rain|hail'))
  self.assertFalse(F.weather_matches(n,'rain'))
  n.start_round([aa,bb]);n.start_of_turn(aa,initiative_count=12)
  with patch.object(n,'d20',return_value=2):self.assertTrue(n.accuracy_check(aa,bb,n.r.move('move/눈보라'))[0])
  n.gm.set_weather('rain',rounds=None,reason='compare condition')
  with patch.object(n,'d20',return_value=2):self.assertFalse(n.accuracy_check(aa,bb,n.r.move('move/눈보라'))[0])

 def test_source_exclusion_restores_core_intrinsics_without_changing_weather_identity(self):
  e,a,b=self.fixture();e.gm.set_weather('sunny',rounds=None,reason='same weather')
  self.assertEqual(T.weather_damage_mod(e,a,e.r.move('move/불꽃세례')),0)
  e.r.selection.excluded['hb-weather']='explicit test exclusion'
  try:
   self.assertEqual(T.weather_damage_mod(e,a,e.r.move('move/불꽃세례')),5)
   self.assertEqual(T.weather_damage_mod(e,a,e.r.move('move/물대포')),-5)
   self.assertEqual(e.weather,'sunny')
  finally:e.r.selection.excluded.pop('hb-weather',None)

 def test_homebrew_blizzard_condition_changes_actual_area_without_mutating_definition(self):
  import weapon_actions as RANGE,body_state as BODY
  from grid import Grid
  e,a,b=self.fixture()
  far=Combatant(e.r,dict(b.spec,id='weather/far',name='Far',trainer_id=a.entity_id))
  a.pos=(0,0);b.pos=(2,0);far.pos=(4,2)
  e.everyone=e.gm.everyone=[a,b,far];e.grid=Grid(12,12)
  for c in (a,b,far):BODY.observe(e,c,[(0,0)],reason='known complete one-cell body')
  move=e.r.move('move/눈보라');self.assertEqual(move['id'],'move/눈보라-홈브류')
  definition=deepcopy(e.r.moves_reviewed[move['id']])
  for weather,size in [('rain',2),('hail',4),('sunny',2),('sandstorm',2)]:
   e.gm.set_weather(weather,rounds=None,reason='conditional area test')
   self.assertEqual(RANGE.range_spec(e,move)['size'],size)
   targets=e.targets_in_range(a,move,[a,b,far],b)
   self.assertEqual(far in targets,weather=='hail')
   self.assertEqual(e.r.moves_reviewed[move['id']],definition)
  core=Engine(self.core);core.gm.set_weather('hail')
  self.assertEqual(RANGE.range_spec(core,self.core.move('move/눈보라'))['size'],2)
