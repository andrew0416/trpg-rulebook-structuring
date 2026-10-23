"""Finisher's exact target conditions share owned feature and damage consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import effects as FX,items as I,state_grants as G,state_codec as C,world_entities as W
import combat_damage as D

SOURCE='feat/피니셔'
STATUSES=('기절','풀죽음','잠듦','구속','둔화','수렁','넘어짐')

class FinisherTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
 def setUp(self):
  self.e=Engine(self.r,seed=1404)
  def trainer(name,feats=()):return Combatant(self.r,build_trainer(self.r,name,30,
   {'hp':20,'atk':20,'def':10,'spa':20,'spd':10,'spe':20},moves=['몸통박치기'],abilities=[],
   extra={'classes':['class/헌터'],'feats':list(feats),'skills':{'은신':'숙련','생존':'숙련'}}))
  self.a=trainer('Actual Finisher',[SOURCE]);self.b=trainer('Actual Other Owner');self.t=trainer('Actual Target')
  self.p=Combatant(self.r,build_pokemon(self.r,'브케인',50,moves=['몸통박치기'],abilities=[],extra={'trainer_id':self.a.entity_id}))
  self.foreign=Combatant(self.r,build_pokemon(self.r,'브케인',50,moves=['몸통박치기'],abilities=[],extra={'trainer_id':self.b.entity_id}))
  for actor,pos in [(self.a,(0,0)),(self.b,(3,0)),(self.t,(1,0)),(self.p,(1,1)),(self.foreign,(3,1))]:
   self.e.gm.add_combatant(actor,pos=pos,side='wild' if actor is self.t else 'party',reason='observed actual acquired sheet and ownership')
  self.register()
 def register(self):return I.register_feats(self.e,self.a,pokemon=[self.p,self.foreign])
 def bonus(self,actor):
  move=self.r.move('move/몸통박치기')
  return FX.passive_damage_mods(self.e,actor,self.t,move,{'attacker':actor,'target':self.t,'hit':True,'move':move,'engine':self.e})[1]
 def state(self):return deepcopy([(c.spec,c.modifiers,c.conditions,c.hp,c.stats) for c in self.e.everyone])
 def test_all_seven_actual_target_conditions_activate_once_for_owner_and_owned_pokemon(self):
  self.assertEqual((self.bonus(self.a),self.bonus(self.p),self.bonus(self.foreign)),(0,0,0))
  self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(self.a,initiative_count=20)
  for status in (*STATUSES[1:],STATUSES[0]):
   with self.subTest(status=status):
    self.e.apply_status(self.t,status,source='condition/'+status,applied_by=self.a)
    self.assertIn(status,self.t.conditions)
    self.assertEqual((self.bonus(self.a),self.bonus(self.p),self.bonus(self.foreign)),(5,5,0))
    if status!='기절':
     self.e.cure_status(self.t,status);self.assertEqual((self.bonus(self.a),self.bonus(self.p)),(0,0))
 def test_healthy_unrelated_and_attacker_conditions_do_not_grant_the_bonus(self):
  self.e.apply_status(self.a,'둔화',source='condition/둔화',applied_by=self.b)
  self.e.apply_status(self.t,'화상',source='condition/화상',applied_by=self.a)
  self.assertEqual((self.bonus(self.a),self.bonus(self.p)),(0,0))
  self.e.apply_status(self.t,'둔화',source='condition/둔화',applied_by=self.a)
  self.e.apply_status(self.t,'넘어짐',source='condition/넘어짐',applied_by=self.a)
  self.assertEqual((self.bonus(self.a),self.bonus(self.p)),(5,5))
  self.e.cure_status(self.t,'둔화');self.assertEqual(self.bonus(self.p),5)
  self.e.cure_status(self.t,'넘어짐');self.assertEqual(self.bonus(self.p),0)
 def test_native_owner_and_owned_pokemon_attacks_use_same_damage_modifier_and_cost(self):
  self.e.gm.observe_loyalty(self.p,6,reason='observed loyalty for actual owned attacker')
  self.e.apply_status(self.t,'둔화',source='condition/둔화',applied_by=self.a)
  for actor in (self.a,self.p):
   with self.subTest(actor=actor.kind):
    self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(actor,initiative_count=20)
    hp=self.t.hp
    with patch.object(self.e,'d20',return_value=15),patch.object(D,'defend',wraps=D.defend) as defend:
     self.e.use_move(actor,self.t,'move/몸통박치기',set_damage=True)
    self.assertEqual(defend.call_count,1);self.assertEqual(defend.call_args.kwargs['modifiers'],5)
    self.assertLess(self.t.hp,hp);self.assertEqual(actor.budget['standard'],0)
    self.assertEqual(actor.move_uses['move/몸통박치기'],1);self.e.end_of_turn(actor)
 def test_repeated_registration_keeps_source_single_and_foreign_pokemon_excluded(self):
  before=self.state();stats=deepcopy(self.a.stats)
  self.register();self.register();self.assertEqual(self.state(),before);self.assertEqual(self.a.stats,stats)
  for actor in (self.a,self.p):
   self.assertEqual(len([m for m in actor.modifiers if m.get('if_target_status_any')]),1)
   self.assertIn('feature:'+self.a.entity_id+':'+SOURCE,G.state(actor)['sources'])
  self.assertFalse(any(m.get('if_target_status_any') for m in self.foreign.modifiers))
  self.e.apply_status(self.t,'둔화',source='condition/둔화',applied_by=self.a)
  self.b.spec['feats']=[];I.register_feats(self.e,self.b,pokemon=[self.foreign])
  self.assertEqual((self.bonus(self.b),self.bonus(self.foreign)),(0,0))
 def test_native_default_registration_discovers_actual_owner_id_without_legacy_name(self):
  key='feature:'+self.a.entity_id+':'+SOURCE
  G.revoke(self.p,key,engine=self.e)
  self.assertNotIn('trainer',self.p.spec);self.assertNotIn(key,G.state(self.p)['sources'])
  self.e.register_abilities(self.a)
  self.assertIn(key,G.state(self.p)['sources'])
  self.assertNotIn(key,G.state(self.foreign)['sources'])
  self.e.apply_status(self.t,'둔화',source='condition/둔화',applied_by=self.a)
  self.assertEqual((self.bonus(self.a),self.bonus(self.p),self.bonus(self.foreign)),(5,5,0))
  before=self.state();self.e.register_abilities(self.a);self.assertEqual(self.state(),before)
 def test_both_restores_and_atomic_source_withdrawal_preserve_independent_modifier(self):
  for actor in (self.a,self.p):
   G.apply_owned(self.e,actor,'fixture:independent-damage',lambda c=actor:c.modifiers.append({'type':'bonus_damage','value':1}))
  self.e.apply_status(self.t,'둔화',source='condition/둔화',applied_by=self.a)
  snap=self.e.gm.snapshot();self.e.cure_status(self.t,'둔화');self.e.gm.restore(snap)
  self.e=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)))
  index=W.actor_index(self.e)
  self.a,self.p,self.t,self.foreign=[index[c.entity_id] for c in (self.a,self.p,self.t,self.foreign)]
  self.register();self.assertEqual((self.bonus(self.a),self.bonus(self.p)),(6,6))
  key='feature:'+self.a.entity_id+':'+SOURCE
  def withdraw(engine,owner,pokemon):
   owner.spec['feats'].remove(SOURCE)
   G.revoke(owner,key,engine=engine);G.revoke(pokemon,key,engine=engine)
  G.transition(self.e,self.a,withdraw,participants=(self.p,))
  self.assertEqual((self.bonus(self.a),self.bonus(self.p)),(1,1))
  self.assertIn('fixture:independent-damage',G.state(self.p)['effects'])
  self.assertTrue(self.e.validate_state()['valid'],self.e.validate_state())
 def test_malformed_status_alternatives_fail_closed_and_ownership_loss_ends_child_effect(self):
  ctx={'attacker':self.a,'target':self.t,'hit':True};before=self.state()
  for value in ('둔화',[],[None],['']):
   with self.subTest(value=value):self.assertFalse(FX.cond_ok(self.e,{'if_target_status_any':value},ctx)[0])
  self.assertEqual(self.state(),before)
  self.e.apply_status(self.t,'둔화',source='condition/둔화',applied_by=self.a)
  G.revoke_owner(self.e,self.p,self.a.entity_id,'actual old ownership ends')
  self.p.spec['trainer_id']=self.b.entity_id;self.register()
  self.assertEqual((self.bonus(self.a),self.bonus(self.p)),(5,0))

if __name__=='__main__':unittest.main()
