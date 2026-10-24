"""Real native attacks select one weather charge for one actual target."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_category2_homebrew_weather as _fixture_test_category2_homebrew_weather
import blessing_effects as B,weather_blessings as W,effect_instances as E
from engine import Combatant
from grid import Grid
from state_codec import StateCodecError

class Tests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_homebrew_weather.Tests.setUpClass.__func__)
 fixture=_fixture_test_category2_homebrew_weather.Tests.fixture
 cast=_fixture_test_category2_homebrew_weather.Tests.cast
 restored=_fixture_test_category2_homebrew_weather.Tests.restored
 resources=_fixture_test_category2_homebrew_weather.Tests.resources
 def setup_weather(self,weather):
  e,a,b=self.fixture();a.side='party';b.side='wild'
  e.gm.observe_loyalty(b,6,reason='known obedience')
  self.cast(e,a,b,'move/'+weather)
  return e,a,b,next(r for r in B.live(a) if W.is_weather(r))
 def attack(self,e,actor,target,name,answer=True,roll=18):
  e.gm.set_move(actor,'move/'+name,reason='actual learned attack')
  e.rulings.answers=[r for r in e.rulings.answers if r['key']!='weather_blessing']
  if answer is not None:e.rulings.add_answer('weather_blessing',answer,reason='explicit target choice')
  e.start_round(e.gm.everyone);e.start_of_turn(actor,initiative_count=12)
  with patch.object(e,'d20',return_value=roll):result=e.use_move(actor,target,'move/'+name,set_damage=True)
  e.end_of_turn(actor)
  return result
 def test_all_eight_offensive_types_use_one_net_step_and_preserve_dice(self):
  for weather,names in [('싸라기눈',('얼음뭉치','바람일으키기')),('비바라기',('물대포','전기쇼크')),
                        ('모래바람',('돌떨구기','진흙뿌리기')),('쾌청',('불꽃세례','덩굴채찍'))]:
   for name in names:
    with self.subTest(weather=weather,attack=name):
     e,a,b,r=self.setup_weather(weather)
     with patch.object(e,'roll_expr',wraps=e.roll_expr) as dice:
      damage=self.attack(e,a,b,name)
     self.assertEqual(dice.call_count,0);self.assertEqual(B.remaining(r),1)
     d=r['decisions'][-1]
     self.assertEqual(d['direction'],'offense');self.assertTrue(d['selected'])
     self.assertEqual((d['multiplier_before'],d['multiplier_after']),(1,1.5))
     self.assertEqual(damage,d['damage_after']);self.assertEqual(d['target_id'],b.entity_id)
     self.assertTrue(e.validate_state()['valid']);self.restored(e)

 def test_all_four_defensive_uses_share_capacity_and_exhaust_without_ending_weather(self):
  for weather,boost,reduced in [('싸라기눈','바람일으키기','불꽃세례'),('비바라기','물대포','불꽃세례'),
                                ('모래바람','돌떨구기','물대포'),('쾌청','불꽃세례','물대포')]:
   with self.subTest(weather=weather):
    e,a,b,r=self.setup_weather(weather);identity=r['id']
    self.attack(e,a,b,boost);self.attack(e,b,a,reduced)
    self.assertFalse(any(x['id']==identity for x in B.live(a)))
    closed=next(x for x in a.spec[B.HISTORY] if x['id']==identity)
    self.assertEqual(B.remaining(closed),0);self.assertEqual(closed[E.KEY]['state'],'consumed')
    self.assertEqual([d['direction'] for d in closed['decisions']],['offense','defense'])
    self.assertEqual(closed['decisions'][-1]['multiplier_after'],0.5)
    self.assertIsNotNone(e.weather);self.restored(e)
    e.gm.set_weather(None);self.restored(e)

 def test_decline_absence_miss_wrong_type_preview_and_immunity_do_not_spend(self):
  for mode in ['decline','absent','miss','wrong_type','immune','preview']:
   with self.subTest(mode=mode):
    e,a,b,r=self.setup_weather('비바라기')
    if mode=='immune':b._types=['땅']
    name='불꽃세례' if mode=='wrong_type' else '전기쇼크'
    if mode=='preview':
     e.roll_damage(a,b,e.r.move('move/'+name),set_damage=True)
    else:self.attack(e,a,b,name,answer=False if mode=='decline' else None if mode=='absent' else True,roll=1 if mode=='miss' else 18)
    self.assertEqual(B.remaining(r),2)
    if mode in ('decline','absent'):
     self.assertEqual(len(r['decisions']),1);self.assertFalse(r['decisions'][0]['selected'])
    else:self.assertFalse(r['decisions'])

 def test_actual_type_override_and_duplicate_callback_never_spend_twice(self):
  e,a,b,r=self.setup_weather('비바라기');a.type_override_next='물'
  original=W.select_damage
  def repeated(engine,event,context):
   first=original(engine,event,context);before=deepcopy(r['decisions'])
   second=original(engine,event,context)
   self.assertEqual(first,second);self.assertEqual(r['decisions'],before)
   return second
  with patch.object(W,'select_damage',side_effect=repeated):self.attack(e,a,b,'불꽃세례')
  self.assertEqual(B.remaining(r),1);self.assertEqual(r['decisions'][0]['move_type'],'물')

 def test_native_area_choice_is_bound_to_one_target_and_one_shared_activation(self):
  e,a,b,r=self.setup_weather('비바라기')
  c=Combatant(e.r,dict(b.spec,id='weather/second',name='Second',kind='pokemon',trainer_id=a.entity_id))
  c.side='wild';e.everyone=e.gm.everyone=[a,b,c];e.gm.observe_loyalty(c,6,reason='known participant')
  a.pos=(0,0);b.pos=(1,0);c.pos=(1,1);e.grid=Grid(8,8)
  import body_state as BODY
  for actor in (a,b,c):BODY.observe(e,actor,[(0,0)],reason='observed one-cell body')
  e.gm.set_move(a,'move/거품',reason='known area attack')
  selected=[]
  def decide(prompt):
   if prompt.get('type')=='weather_blessing':selected.append(prompt);return prompt['target_id']==b.entity_id
   return None
  e.rulings.provider=decide
  e.start_round([a,b,c]);e.start_of_turn(a,initiative_count=12)
  with patch.object(e,'d20',return_value=18):e.use_move_on(a,b,'move/거품',[a,b,c])
  self.assertEqual({d['target_id'] for d in r['decisions']},{b.entity_id,c.entity_id})
  self.assertEqual(len({d['activation_id'] for d in r['decisions']}),1)
  self.assertEqual([d['target_id'] for d in r['decisions'] if d['selected']],[b.entity_id])
  self.assertEqual(B.remaining(r),1);e.rulings.provider=None;self.restored(e)

 def test_native_area_two_real_charges_apply_to_two_targets_of_one_shared_activation(self):
  e,a,b,r=self.setup_weather('비바라기');identity=r['id']
  c=Combatant(e.r,dict(b.spec,id='weather/second',name='Second',kind='pokemon',trainer_id=a.entity_id))
  c.side='wild';e.everyone=e.gm.everyone=[a,b,c];e.gm.observe_loyalty(c,6,reason='known participant')
  a.pos=(0,0);b.pos=(1,0);c.pos=(1,1);e.grid=Grid(8,8)
  import body_state as BODY
  for actor in (a,b,c):BODY.observe(e,actor,[(0,0)],reason='observed one-cell body')
  move='move/거품';e.gm.set_move(a,move,reason='known actual native area attack')
  prompts=[]
  def decide(prompt):
   if prompt.get('type')=='weather_blessing':prompts.append(dict(prompt));return True
   return None
  e.rulings.provider=decide
  e.start_round([a,b,c]);e.start_of_turn(a,initiative_count=12)
  hp={target.entity_id:target.hp for target in (b,c)};uses=a.move_uses.get(move,0)
  self.assertEqual(B.remaining(r),2)
  with patch.object(e,'d20',return_value=18) as accuracy:e.use_move_on(a,b,move,[a,b,c],set_damage=True)
  closed=next(row for row in a.spec[B.HISTORY] if row['id']==identity)
  self.assertEqual(len(prompts),2);self.assertEqual([p['remaining'] for p in prompts],[2,1])
  self.assertEqual({p['target_id'] for p in prompts},{b.entity_id,c.entity_id})
  self.assertEqual(len(closed['decisions']),2)
  self.assertTrue(all(d['selected'] and d['direction']=='offense' for d in closed['decisions']))
  self.assertEqual({d['target_id'] for d in closed['decisions']},{b.entity_id,c.entity_id})
  self.assertEqual(len({d['activation_id'] for d in closed['decisions']}),1)
  self.assertEqual({p['activation_id'] for p in prompts},{d['activation_id'] for d in closed['decisions']})
  for target in (b,c):
   decision=next(d for d in closed['decisions'] if d['target_id']==target.entity_id)
   self.assertGreater(decision['damage_after'],decision['damage_before'])
   self.assertEqual((decision['multiplier_before'],decision['multiplier_after']),(1,1.5))
   self.assertEqual(target.hp,hp[target.entity_id]-decision['damage_after'])
  self.assertEqual((accuracy.call_count,a.budget['standard'],a.move_uses[move]),(1,0,uses+1))
  self.assertEqual(B.remaining(closed),0);self.assertEqual(closed[E.KEY]['state'],'consumed')
  self.assertFalse(any(row['id']==identity for row in B.live(a)))
  self.assertEqual(e.weather,'rain');e.rulings.provider=None
  self.assertTrue(e.validate_state()['valid']);self.restored(e)

 def test_consumption_survives_both_restore_paths_and_forged_formula_rejects(self):
  e,a,b,r=self.setup_weather('비바라기');self.attack(e,a,b,'물대포');e.gm.snapshot('one-charge')
  self.attack(e,b,a,'불꽃세례');e.gm.restore('one-charge')
  n=self.restored(e);owner=next(x for x in n.gm.everyone if x.entity_id==a.entity_id)
  pool=next(x for x in B.live(owner) if W.is_weather(x));self.assertEqual(B.remaining(pool),1)
  before=deepcopy(pool['decisions']);pool['decisions'][0]['multiplier_after']=3
  self.assertFalse(n.validate_state()['valid'])
  with self.assertRaises(StateCodecError):n.export_state()
  pool['decisions']=before;self.restored(n)

 def test_final_hook_nullification_and_zero_cap_preserve_charges(self):
  for mode in ('hook','cap'):
   with self.subTest(mode=mode):
    e,a,b,r=self.setup_weather('비바라기')
    hp=b.hp
    with patch.dict(e.rulings.hooks,{'before_damage':[]}):
     if mode=='hook':e.rulings.add_hook('before_damage',lambda value,ctx:0,reason='explicit nullification')
     else:b.damage_cap={'value':0}
     self.attack(e,a,b,'물대포')
    self.assertEqual(b.hp,hp);self.assertEqual(B.remaining(r),2);self.assertFalse(r['decisions'])

 def test_unsupported_multi_roll_holds_before_resources_or_rng(self):
  # Preserve the historical exact ID while correcting its blanket-rejection expectation.
  e,a,b,r=self.setup_weather('비바라기')
  e.gm.set_move(a,'move/물대포',reason='known attack')
  e.rule_effect('move/물대포','add',{'type':'multi_roll','rolls':2},reason='explicit multi-roll variant')
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12)
  e.rulings.add_answer('weather_blessing',True,reason='actual selected combined attack charge')
  with patch.object(e,'d20',return_value=18) as rolls:
   damage=e.use_move(a,b,'move/물대포',set_damage=True)
  self.assertEqual(rolls.call_count,2);self.assertGreater(damage,0)
  self.assertEqual((a.budget['standard'],a.move_uses['move/물대포'],B.remaining(r)),(0,1,1))
  self.assertEqual(len(r['decisions']),1);self.assertTrue(r['decisions'][0]['selected'])
  self.assertEqual(damage,r['decisions'][0]['damage_after']);self.restored(e)

 def test_native_five_strike_keyword_holds_without_consuming_type_override(self):
  e,a,b,r=self.setup_weather('비바라기');a.type_override_next='물'
  e.gm.set_move(a,'move/물수리검',reason='actual ranged five-strike Move')
  e.start_round([a,b]);e.start_of_turn(a,initiative_count=12)
  e.rulings.add_answer('weather_blessing',True,reason='actual selected combined attack charge')
  with patch.object(e,'d20',return_value=18),patch.object(e,'roll_expr',return_value=(7,[7])) as dice:
   damage=e.use_move(a,b,'move/물수리검',set_damage=True)
  self.assertEqual(dice.call_count,1);self.assertGreater(damage,0)
  self.assertEqual(a.spec['five_strike_history'][-1]['hits'],4)
  self.assertIsNone(a.type_override_next)
  self.assertEqual((a.budget['standard'],a.move_uses['move/물수리검'],B.remaining(r)),(0,1,1))
  self.assertEqual(len(r['decisions']),1);self.assertEqual(r['decisions'][0]['move_type'],'물')
  self.assertEqual(damage,r['decisions'][0]['damage_after']);self.restored(e)
