"""Actual team-shared Blessing production, damage choices and durable state.

The three source adapters remain partial where same-source composition and
other Blessing feature operators have no reviewed execution contract.
"""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_gem_effects as _fixture_test_category2_gem_effects
import blessing_effects as B,effect_instances as E,state_codec as CODEC

# The Aurora Veil creation gate and the world validation read the sourced weather registry
# (effects.weather_matches / weather_state.validate), so fixtures place and end hail through
# engine.gm.set_weather(..., rounds=None) instead of assigning engine.weather directly.
class TeamBlessingTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_gem_effects.GemEffectTests.setUpClass.__func__)
 known=_fixture_test_category2_gem_effects.GemEffectTests.known
 snap=_fixture_test_category2_gem_effects.GemEffectTests.snap
 valid=_fixture_test_category2_gem_effects.GemEffectTests.valid
 restored=_fixture_test_category2_gem_effects.GemEffectTests.restored
 add=_fixture_test_category2_gem_effects.GemEffectTests.add
 def setUp(self):
  _fixture_test_category2_gem_effects.GemEffectTests.setUp(self);self.e.gm.observe_loyalty(self.other,6,reason='actual Move attacker');self.other.side='wild'
  self.known(self.other,'물대포','몸통박치기','코트체인지')
 def begin(self,actor):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(actor,initiative_count=20)
 def cast(self,name='빛의장막',actor=None):
  actor=actor or self.a;self.known(actor,name);self.begin(actor)
  self.e.use_move(actor,actor,'move/'+name)
  return next(r for r in B.live(actor) if r['source']=='move/'+name)
 def answer(self,value):
  self.e.rulings.answers=[a for a in self.e.rulings.answers if a['key']!='team_blessing']
  self.e.rulings.add_answer('team_blessing',value,reason='actual beneficiary activation choice')
 def attack(self,target=None,name='물대포',*,roll=18,set_damage=True):
  target=target or self.p;self.begin(self.other)
  with patch.object(self.e,'d20',return_value=roll):return self.e.use_move(self.other,target,'move/'+name,set_damage=set_damage)
 def test_all_three_sources_and_both_creator_kinds_use_one_team_pool(self):
  for name in ['빛의장막','리플렉터','오로라베일']:
   for role in ['a','p']:
    with self.subTest(name=name,role=role):
     self.setUp();self.e.gm.set_weather('hail',rounds=None,reason='actual sourced hail for the Aurora Veil creation gate');actor=getattr(self,role);r=self.cast(name,actor)
     self.assertEqual(sum(len(B.live(c)) for c in self.e.gm.everyone),1)
     self.assertEqual(B.remaining(r),2);self.assertEqual(B.side(r),'party')
     self.assertEqual(actor.budget['standard'],0);self.assertEqual(actor.move_uses['move/'+name],1)
     self.assertEqual(r[E.KEY]['applied_by_actor_id'],actor.entity_id);self.valid()
 def test_trainer_and_pokemon_spend_same_two_uses_then_end_once(self):
  r=self.cast();uid=r['id'];self.answer(True)
  self.attack(self.a);self.assertEqual(B.remaining(r),1)
  self.attack(self.p);self.assertFalse(B.live(self.a));self.assertFalse(self.p.blessings)
  closed=self.a.spec[B.HISTORY][-1];self.assertEqual(closed['id'],uid)
  self.assertEqual({x['target_id'] for x in closed['decisions']},{self.a.entity_id,self.p.entity_id})
  self.assertEqual(closed[E.KEY]['state'],'consumed');self.assertEqual(B.remaining(closed),0)
  self.attack(self.p);self.assertEqual(len([x for x in self.a.spec[B.HISTORY] if x['id']==uid]),1);self.valid()
 def test_decline_wrong_class_miss_and_preview_preserve_capacity(self):
  r=self.cast();self.answer(False)
  preview=self.e.roll_damage(self.other,self.p,self.r.move('move/물대포'),set_damage=True)
  self.assertGreater(preview,0);self.assertFalse(r['decisions'])
  actual=self.attack();self.assertEqual(actual,preview);self.assertEqual(B.remaining(r),2)
  self.assertEqual(len(r['decisions']),1);self.assertFalse(r['decisions'][0]['selected'])
  self.answer(True);self.attack(name='몸통박치기');self.attack(roll=1)
  self.assertEqual(B.remaining(r),2);self.assertEqual(len(r['decisions']),1);self.valid()
 def test_actual_choice_changes_only_resistance_not_the_original_dice(self):
  r=self.cast();self.answer(True)
  with patch.object(self.e,'roll_expr',wraps=self.e.roll_expr) as roll:
   actual=self.attack(set_damage=False)
  self.assertEqual(roll.call_count,1);obs=r['decisions'][0]
  self.assertTrue(obs['selected']);self.assertEqual(obs['damage_after'],actual)
  self.assertEqual(obs['multiplier_before'],1);self.assertEqual(obs['multiplier_after'],0.5)
  self.assertEqual(B.remaining(r),1);self.valid()
 def test_hail_is_creation_gate_only_and_same_source_recast_rejects_before_cost(self):
  self.known(self.a,'오로라베일');self.begin(self.a);before=self.snap()
  with self.assertRaisesRegex(ValueError,'hail'):self.e.use_move(self.a,self.a,'move/오로라베일')
  self.assertEqual(self.snap(),before)
  self.e.gm.set_weather('hail',rounds=None,reason='actual sourced hail for the Aurora Veil creation gate');r=self.cast('오로라베일');self.e.gm.set_weather(None,rounds=None,reason='actual sourced hail end after creation');self.answer(True);self.attack();self.assertEqual(B.remaining(r),1)
  self.e.end_of_turn(self.other);self.e.end_scene();self.e.gm.set_weather('hail',rounds=None,reason='actual sourced hail for the same-source recast');self.begin(self.a);before=self.snap()
  with self.assertRaisesRegex(ValueError,'composition'):self.e.use_move(self.a,self.a,'move/오로라베일')
  self.assertEqual(self.snap(),before);self.assertEqual(B.remaining(r),1);self.valid()
 def test_creator_recall_faint_and_scene_end_do_not_remove_team_benefit(self):
  r=self.cast(actor=self.p);self.e.end_of_turn(self.p)
  self.e.gm.recall(self.p,reason='actual creator recall');self.e.gm.faint(self.p,reason='actual creator faint')
  self.e.end_encounter();self.e.end_scene();self.assertEqual(B.remaining(B.live(self.p)[0]),2)
  self.answer(True);self.attack(self.a);self.assertEqual(B.remaining(r),1);self.valid()
 def test_native_side_exchange_preserves_storage_identity_and_spent_count(self):
  r=self.cast();self.answer(True);self.attack(self.p);uid=r['id'];self.begin(self.other)
  self.e.use_move(self.other,self.other,'move/코트체인지')
  self.assertIs(B.live(self.a)[0],r);self.assertEqual(r['id'],uid);self.assertEqual(B.side(r),'wild');self.assertEqual(B.remaining(r),1)
  self.attack(self.p);self.assertEqual(B.remaining(r),1)
  self.known(self.a,'물대포');self.begin(self.a)
  with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.a,self.other,'move/물대포',set_damage=True)
  self.assertFalse(B.live(self.a));self.assertEqual(self.a.spec[B.HISTORY][-1]['decisions'][-1]['target_id'],self.other.entity_id);self.valid()
 def test_native_defog_clears_all_sides_with_source_ending_history(self):
  first=self.cast();second=self.cast('리플렉터',self.other)
  self.known(self.a,'안개제거');self.begin(self.a);self.e.use_move(self.a,self.a,'move/안개제거')
  self.assertFalse(B.live(self.a));self.assertFalse(B.live(self.other))
  for owner,record in [(self.a,first),(self.other,second)]:
   closed=next(x for x in owner.spec[B.HISTORY] if x['id']==record['id'])
   self.assertEqual(closed[E.KEY]['end_event'],{'kind':'blessing_removed','source':'move/안개제거','actor_id':self.a.entity_id});self.assertEqual(B.remaining(closed),2)
  self.valid()
 def test_both_restore_paths_keep_one_pool_and_remaining_use(self):
  r=self.cast();self.answer(True);self.attack();uid=r['id'];self.e.gm.snapshot('one-use')
  self.attack(self.a);self.assertFalse(B.live(self.a));self.e.gm.restore('one-use')
  restored=self.restored();byid={c.entity_id:c for c in restored.gm.everyone}
  caster=byid[self.a.entity_id];target=byid[self.p.entity_id];foe=byid[self.other.entity_id]
  self.assertEqual(B.live(caster)[0]['id'],uid);self.assertEqual(B.remaining(B.live(caster)[0]),1)
  restored.end_of_turn(restored._active_turn_actor);restored.start_round(restored.gm.everyone);restored.start_of_turn(foe,initiative_count=20)
  with patch.object(restored,'d20',return_value=18):restored.use_move(foe,target,'move/물대포',set_damage=True)
  self.assertFalse(B.live(caster));self.assertTrue(restored.validate_state()['valid'])
  self.assertEqual(B.remaining(B.live(self.a)[0]),1)
 def test_reflect_and_aurora_apply_to_their_actual_damage_classes(self):
  for name,attack in [('리플렉터','몸통박치기'),('오로라베일','몸통박치기'),('오로라베일','물대포')]:
   with self.subTest(name=name,attack=attack):
    self.setUp();self.e.gm.set_weather('hail',rounds=None,reason='actual sourced hail for the Aurora Veil creation gate');r=self.cast(name);self.e.gm.set_weather(None,rounds=None,reason='actual sourced hail end after creation');self.answer(True)
    dealt=self.attack(name=attack);obs=r['decisions'][0]
    self.assertEqual(dealt,obs['damage_after']);self.assertEqual(obs['multiplier_after'],0.5);self.assertEqual(B.remaining(r),1);self.valid()
 def test_immunity_and_ordinary_hp_loss_cannot_spend_a_blessing(self):
  r=self.cast('리플렉터');self.answer(True);self.e.gm.set_types(self.p,['고스트'],reason='actual type observation')
  self.assertEqual(self.attack(name='몸통박치기'),0);self.e.lose_hp(self.p,1,source='observed ordinary HP loss')
  self.assertEqual(B.remaining(r),2);self.assertFalse(r['decisions']);self.valid()
 def test_one_native_area_move_shares_two_uses_across_actual_targets(self):
  r=self.cast();uid=r['id'];self.answer(True);self.known(self.other,'거품');self.begin(self.other)
  from grid import Grid
  self.e.grid=Grid(8,8);self.a.pos=(0,0);self.p.pos=(0,1);self.other.pos=(1,1)
  with patch.object(self.e,'d20',return_value=18):self.e.use_move_on(self.other,self.p,'move/거품',[self.a,self.p,self.other])
  self.assertFalse(B.live(self.a));closed=next(x for x in self.a.spec[B.HISTORY] if x['id']==uid)
  self.assertEqual({x['target_id'] for x in closed['decisions']},{self.a.entity_id,self.p.entity_id})
  self.assertEqual(self.other.move_uses['move/거품'],1);self.assertEqual(B.remaining(closed),0);self.valid()
 def test_zero_damage_from_actual_false_swipe_floor_does_not_spend(self):
  r=self.cast('리플렉터');self.answer(True);self.known(self.other,'칼등치기')
  from grid import Grid
  from native_scenario_fixture import prepare_body
  self.e.grid=Grid(8,8)
  import items as ITEMS
  self.assertTrue(ITEMS.drop_item(self.e,self.p,selection='berry')['changed'])
  self.assertEqual(tuple(self.e._physical_objects['berry']['location']['cell']),(0,0))
  for actor,pos in ((self.a,(6,6)),(self.other,(1,1)),(self.p,(2,1))):
   self.e.gm.set_position(actor,pos,reason='observed actual Pass path')
   prepare_body(self.e,actor,size=actor.spec['size'],offsets=[(0,0)],reason='observed complete Pass body')
  self.e.gm.set_hp(self.p,value=1,reason='actual False Swipe floor recipient');self.begin(self.other)
  with patch.object(type(self.e),'d20',return_value=18):
   row=self.e.use_pass_move(self.other,'move/칼등치기',(3,1),event_id='blessing/false-swipe',
    object_adjudications={},source='gm/observed-pass',reason='actual False Swipe path through the recipient')
  self.assertEqual(row['targets'],[['creature',self.p.entity_id]])
  self.assertEqual(row['results'][0]['dealt'],0);self.assertEqual(self.p.hp,1)
  self.assertEqual(B.remaining(r),2);self.assertFalse(r['decisions']);self.valid()
 def test_corrupt_capacity_history_scope_and_damage_observation_reject(self):
  for corruption in ['capacity','lifetime','target','damage','scope','duplicate']:
   with self.subTest(corruption=corruption):
    self.setUp();r=self.cast();self.answer(True);self.attack()
    if corruption=='capacity':r[E.KEY]['capacity']['limit']=3
    elif corruption=='lifetime':r[E.KEY]['lifetime']['boundary']='scene'
    elif corruption=='target':r['decisions'][0]['target_id']='absent'
    elif corruption=='damage':r['decisions'][0]['damage_after']+=1
    elif corruption=='scope':r['scope_history'][0]['source']='move/리플렉터'
    else:self.p.blessings.append(deepcopy(r))
    with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
    before=self.snap()
    with self.assertRaises(ValueError):self.e.roll_damage(self.other,self.p,self.r.move('move/물대포'),set_damage=True)
    self.assertEqual(before,self.snap())

if __name__=='__main__':unittest.main()
