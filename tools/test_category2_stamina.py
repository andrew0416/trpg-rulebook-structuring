"""Actual damaging move -> complete action -> source-owned common temporary HP."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import unittest
from engine import Rules,Engine,Combatant
import stamina as STAMINA,action_lifecycle as ACTION,temporary_hp as TEMP
import state_grants as G,state_codec as CODEC,effects_ext as EXT,effects as FX
import common_checks as C

ROOT=Path(__file__).resolve().parents[1]

class StaminaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=5)
  def actor(identity,kind):
   return Combatant(self.r,{'id':identity,'name':identity,'kind':kind,'level':20,'size':'medium',
    'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),30),
    'skills':{'육상':5,'전투':5},'moves':['struggle'],'edges':[],'abilities':[],'types':[]})
  self.a,self.b=actor('pokemon/attacker','pokemon'),actor('trainer/defender','trainer')
  self.a.side='enemy';self.b.side='party'
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
 def own(self):return G.transition(self.e,self.b,lambda e,c:c.spec['edges'].append(STAMINA.SOURCE))
 def turn(self):self.e.start_round([self.a,self.b]);self.e.start_of_turn(self.a)
 def attack(self,**kw):return self.e.use_move(self.a,self.b,'struggle',set_damage=kw.pop('set_damage',True),**kw)
 def rows(self):return list(getattr(self.e,'_native_action_resolutions',{}).values())
 def test_ordinary_expert_either_skill_and_one_copy_are_actual_qualification(self):
  self.b.spec['skills']={'육상':4,'전투':4};before=CODEC.dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'Expert Athletics or Combat'):self.own()
  self.assertEqual(CODEC.dump_engine(self.e),before)
  self.b.spec['skills']['전투']=5;self.own()
  with self.assertRaises(ValueError):self.own()
  self.assertEqual(self.b.spec['edges'],[STAMINA.SOURCE])
 def test_critical_grants_only_after_native_effects_and_hit_reactions_return(self):
  self.own();self.turn();observed=[];original=EXT.after_move;fire=FX.fire_event
  def after(*args):observed.append(('after_move',self.b.temp_hp));return original(*args)
  def events(*args):
   if args[2].get('event')=='on_hit_received':observed.append(('hit_received',self.b.temp_hp))
   return fire(*args)
  with patch.object(EXT,'after_move',side_effect=after),patch.object(FX,'fire_event',side_effect=events),patch.object(TEMP,'grant',wraps=TEMP.grant) as grant:
   dealt=self.attack()
  self.assertGreater(dealt,0);self.assertEqual(observed,[('after_move',0),('hit_received',0)])
  self.assertEqual(self.b.temp_hp,5);self.assertEqual(grant.call_count,1)
  row=self.rows()[0];self.assertEqual(row['phase'],'producer_returned')
  trigger=row['triggers'][0];self.assertEqual(trigger['observations'][0]['event'],'critical_hit')
  self.assertEqual((trigger['source'],trigger['status']),(STAMINA.SOURCE,'completed'))
  receipt=self.e._effect_dispatch_receipts[trigger['effect_receipts'][0]]
  self.assertEqual((receipt['source_id'],receipt['status']),(STAMINA.SOURCE,'completed'))
  self.assertEqual((self.a.move_uses['struggle'],self.a.budget['standard']),(1,0))
 def test_native_move_on_joins_its_real_activation_instead_of_finishing_each_hit(self):
  self.own();self.turn()
  self.e.use_move_on(self.a,self.b,'struggle',[self.a,self.b])
  self.assertEqual((len(self.rows()),self.b.temp_hp),(1,5))
  self.assertEqual(self.rows()[0]['actor'],self.a)
 def test_noncritical_small_hit_and_miss_never_create_stamina(self):
  self.own();self.turn();self.e.rng.seed(0);self.attack()
  self.assertEqual((self.b.temp_hp,self.rows()),(0,[]))
  self.setUp();self.own();self.turn();self.e.rng.seed(31);self.attack()
  self.assertEqual((self.b.temp_hp,self.rows()),(0,[]))
 def test_massive_and_critical_from_same_action_grant_once_after_all_damage(self):
  self.own();self.a.stats['atk']=90;self.turn()
  with patch.object(TEMP,'grant',wraps=TEMP.grant) as grant:self.attack(set_damage=False)
  observations=self.rows()[0]['triggers'][0]['observations']
  self.assertEqual({row['event'] for row in observations},{'massive_damage','critical_hit'})
  self.assertEqual((self.b.temp_hp,grant.call_count),(5,1))
  massive=next(row for row in observations if row['event']=='massive_damage')
  self.assertGreaterEqual(massive['amount'],massive['maximum_hp']/2)
 def test_existing_greater_temporary_hp_does_not_stack_or_reset(self):
  self.own();TEMP.grant(self.e,self.b,30);self.turn();before=deepcopy(self.b.custom_conditions[TEMP.STATE])
  dealt=self.attack()
  self.assertEqual(self.b.temp_hp,30-dealt);self.assertGreater(self.b.temp_hp,5)
  self.assertEqual(self.b.custom_conditions[TEMP.STATE],before)
 def test_different_ranks_wait_for_actual_choice_without_assuming_maximum(self):
  self.b.spec['skills']['전투']=6;self.own();self.turn();self.attack()
  row=self.rows()[0];self.assertEqual(self.b.temp_hp,0)
  self.assertEqual(row['triggers'][0]['status'],'awaiting_skill')
  with self.assertRaises(ValueError):self.e.end_of_turn(self.a)
  with self.assertRaises(ValueError):self.e.preflight_advance_time(1)
  self.e.resolve_stamina(self.b,row['id'],skill='육상')
  self.assertEqual(self.b.temp_hp,5)
  with self.assertRaisesRegex(ValueError,'already resolved'):self.e.resolve_stamina(self.b,row['id'],skill='전투')
  self.assertEqual(self.b.temp_hp,5)
 def test_pending_choice_survives_native_save_restore_without_replaying_damage(self):
  self.b.spec['skills']['전투']=6;self.own();self.turn();self.attack()
  action_id=self.rows()[0]['id'];hp=self.b.hp;spent=self.a.move_uses['struggle']
  restored=CODEC.load_engine(self.r,CODEC.dump_engine(self.e))
  a,b=restored.everyone
  restored.resolve_stamina(b,action_id,skill='전투')
  self.assertEqual((b.hp,b.temp_hp,a.move_uses['struggle']),(hp,6,spent))
 def test_virtuoso_pending_choice_restores_effective_eight_without_changing_six_dice(self):
  import json,skill_modifiers as S
  self.b.spec['skills']={'육상':6,'전투':6};self.own()
  G.transition(self.e,self.b,lambda e,b:b.spec.update(
   edges=[*b.spec['edges'],'edge/거장'],edge_choices={'edge/거장':['육상']}))
  self.assertEqual(S.effective_rank(self.e.r,self.b,'육상'),8)
  self.turn();self.attack();row=self.rows()[0]
  self.assertEqual((self.b.temp_hp,row['triggers'][0]['status']),(0,'awaiting_skill'))
  action_id=row['id'];hp=self.b.hp;spent=self.a.move_uses['struggle']
  self.e=CODEC.load_engine(Rules(str(self.e.r.root),ruleset='core'),json.loads(json.dumps(CODEC.dump_engine(self.e))))
  self.a,self.b=self.e.everyone
  self.assertEqual((S.rank(self.e.r,self.b,'육상')[2],S.effective_rank(self.e.r,self.b,'육상')),(6,8))
  self.e.resolve_stamina(self.b,action_id,skill='육상')
  self.assertEqual((self.b.hp,self.b.temp_hp,self.a.move_uses['struggle']),(hp,8,spent))
  self.assertEqual(self.rows()[0]['triggers'][0]['rank'],8)
  CODEC.dump_engine(self.e)
 def test_plain_damage_component_cannot_claim_the_enclosing_action_finished(self):
  self.own();self.e.take_damage(self.b,self.b.base_max_hp//2+1)
  row=self.rows()[0];self.assertEqual((self.b.temp_hp,row['phase']),(0,'component_only'))
  with self.assertRaisesRegex(ValueError,'complete triggering action'):self.e.resolve_stamina(self.b,row['id'],skill='육상')
  with self.assertRaises(ValueError):self.e.resolve_stamina(self.b,'invented',skill='육상')
 def test_failure_after_observed_damage_retains_cost_and_never_grants_early(self):
  self.own();self.turn();hp=self.b.hp
  with patch.object(EXT,'after_move',side_effect=ValueError('actual late unresolved effect')):
   with self.assertRaisesRegex(ValueError,'late unresolved'):self.attack()
  self.assertLess(self.b.hp,hp);self.assertEqual((self.b.temp_hp,self.a.move_uses['struggle']),(0,1))
  self.assertEqual(self.rows()[0]['phase'],'interrupted')
  with self.assertRaisesRegex(ValueError,'complete triggering action'):self.e.resolve_stamina(self.b,self.rows()[0]['id'],skill='육상')
 def test_invalid_skill_choice_is_atomic_and_keeps_the_real_pending_action(self):
  self.b.spec['skills']['전투']=6;self.own();self.turn();self.attack();before=CODEC.dump_engine(self.e)
  with self.assertRaises(ValueError):self.e.resolve_stamina(self.b,self.rows()[0]['id'],skill='곡예')
  self.assertEqual(CODEC.dump_engine(self.e),before)
 def test_completed_stamina_save_restore_does_not_award_again(self):
  self.own();self.turn();self.attack();action_id=self.rows()[0]['id']
  restored=CODEC.load_engine(self.r,CODEC.dump_engine(self.e));b=restored.everyone[1]
  with self.assertRaises(ValueError):restored.resolve_stamina(b,action_id,skill='육상')
  self.assertEqual(b.temp_hp,5)
 def test_hp_loss_is_not_damage_and_does_not_create_massive_trigger(self):
  self.own();self.e.lose_hp(self.b,self.b.base_max_hp//2+1,source='actual direct HP loss')
  self.assertEqual((self.b.temp_hp,self.rows()),(0,[]))
 def test_temporary_hp_absorption_prevents_massive_real_hp_trigger(self):
  self.own();amount=self.b.base_max_hp//2+1;TEMP.grant(self.e,self.b,amount)
  hp=self.b.hp;self.e.take_damage(self.b,amount)
  self.assertEqual((self.b.hp,self.b.temp_hp,self.rows()),(hp,0,[]))
 def test_actual_unresolved_effect_receipt_defers_stamina_without_replaying_attack(self):
  self.own();self.turn()
  def unresolved(e,a,b,*args):
   FX.run_effects(e,a,b,[{'type':'unreviewed_test_suffix'}],{'hit':True},'struggle')
  with patch.object(EXT,'after_move',side_effect=unresolved):self.attack()
  row=self.rows()[0];self.assertTrue(ACTION.pending_resolution_effects(self.e,row))
  hp=self.b.hp;uses=deepcopy(self.a.move_uses)
  pending=self.e.resolve_stamina(self.b,row['id'],skill='육상')
  self.assertIsInstance(pending,C.PendingDecision)
  self.assertEqual((self.b.hp,self.b.temp_hp,self.a.move_uses),(hp,0,uses))
 def test_save_inside_executing_action_is_rejected_but_post_action_save_is_valid(self):
  self.own();self.turn();observed=[]
  def check(*args):
   with self.assertRaisesRegex(ValueError,'executing native action'):CODEC.dump_engine(self.e)
   observed.append(self.b.temp_hp)
  with patch.object(EXT,'after_move',side_effect=check):self.attack()
  self.assertEqual((observed,self.b.temp_hp),([0],5));CODEC.dump_engine(self.e)
 def test_native_nested_opportunity_attack_finishes_its_own_stamina_before_parent(self):
  from random import Random
  from grid import Grid
  import turn as TURN
  self.a=Combatant(self.r,dict(deepcopy(self.a.spec),id='trainer/attacker',kind='trainer',edges=[STAMINA.SOURCE]))
  self.a.side='enemy';self.a.pos=(0,0);self.b.pos=(0,1);self.e.grid=Grid(5,5)
  self.e.everyone=self.e.gm.everyone=[self.a,self.b];self.own();self.turn()
  seed=next(n for n in range(10000) if (lambda r:r.randint(1,20)==20 and r.randint(1,20)==20)(Random(n)))
  self.e.rng.seed(seed);observed=[];original=EXT.after_move
  def response(e,a,b,*args):
   if a is self.a:
    TURN.trigger_aoo(e,a,'actual movement provocation after primary hit',enemies=[self.b])
    observed.append((self.a.temp_hp,self.b.temp_hp))
   return original(e,a,b,*args)
  with patch.object(EXT,'after_move',side_effect=response):self.attack()
  self.assertEqual(observed,[(5,0)]);self.assertEqual((self.a.temp_hp,self.b.temp_hp),(5,5))
  self.assertEqual(len(self.rows()),2);self.assertTrue(self.b.aoo_used)
  self.assertEqual(self.b.move_uses,{})
 def test_native_post_hit_state_transaction_preserves_action_and_actor_identity(self):
  self.own();self.turn();hp=self.b.hp
  def heal(e,a,b,*args):G.transition(e,b,lambda staged,current:staged.heal(current,1,source_kind='feature'))
  with patch.object(EXT,'after_move',side_effect=heal):dealt=self.attack()
  self.assertEqual((self.b.hp,self.b.temp_hp),(hp-dealt+1,5))
  row=self.rows()[0];self.assertEqual(row['phase'],'producer_returned')
  self.assertIs(row['triggers'][0]['actor'],self.b)

if __name__=='__main__':unittest.main()
