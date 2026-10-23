"""Actual paid roster actions, replay, round restrictions and prepaid costs."""
from pathlib import Path
from copy import deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
import pokemon_party as PARTY
import party_actions as ACTIONS
from state_codec import dump_engine,load_engine

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setup_world(self,mode='full_contact',start='trainer'):
  self.e=Engine(self.r,37);self.e.grid=Grid(20,5)
  def actor(name,kind,pos):
   spec={'id':kind+'/'+name,'name':name,'kind':kind,'level':20,'pos':pos,'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),'skills':{},'items':{},'edges':[],'feats':[]}
   return Combatant(self.r,spec)
  self.a=actor('owner','trainer',(0,0));self.p=actor('one','pokemon',(2,0));self.q=actor('two','pokemon',(3,0));self.z=actor('third','pokemon',(4,0))
  for p in (self.p,self.q,self.z):p.spec['trainer_id']=self.a.spec['id']
  self.q.on_field=self.z.on_field=False
  self.e.everyone=self.e.gm.everyone=[self.a,self.p,self.q,self.z]
  for actor in self.e.everyone:self.e.gm.set_footprint(actor,[(0,0)],reason='actual one-cell body')
  PARTY.configure(self.e,self.a,mode='standard',reason='actual roster',roster=[self.p,self.q,self.z],storage={'kind':'center','id':'actual-center'})
  self.e.configure_party_combat(self.a,battle_mode=mode,reason='actual encounter rules')
  self.e.start_round(self.e.everyone)
  if start:self.e.start_of_turn(self.a if start=='trainer' else self.p,initiative_count=20)
 def switch(self,request='switch-1'):
  return self.e.act_on_party(self.a,recall=[self.p],send=[(self.q,(2,0))],request_id=request,reason='actual switch')
 def test_native_switch_pays_standard_and_preserves_actual_identity(self):
  self.setup_world();budget=self.a.budget
  row=self.switch()
  self.assertEqual((self.p.on_field,self.q.on_field,self.a.budget['standard']),(False,True,0))
  self.assertIs(self.e.everyone[2],self.q);self.assertIs(self.a.budget,budget)
  self.assertEqual((row['counts_as_switch'],row['payment']['funded']),(True,{'standard':1}))
 def test_fainted_switch_uses_shift_and_keeps_standard(self):
  self.setup_world();self.p.hp=0
  row=self.switch()
  self.assertEqual((row['payment']['kind'],self.a.budget['standard'],self.a.budget['shift']),('shift',1,0))
 def test_individual_actions_count_as_switch_and_same_pokemon_cannot_return(self):
  self.setup_world('league')
  self.e.act_on_party(self.a,recall=[self.p],request_id='recall',reason='actual recall')
  before=dump_engine(self.e)
  with self.assertRaisesRegex(ValueError,'same Pokemon'):
   self.e.act_on_party(self.a,send=[(self.p,(2,0))],request_id='invalid-send',reason='invalid same round')
  self.assertEqual(dump_engine(self.e),before)
  row=self.e.act_on_party(self.a,send=[(self.q,(2,0))],request_id='send',reason='actual new Pokemon')
  self.assertTrue(row['counts_as_switch']);self.assertEqual(self.a.budget['standard'],0)
  self.e.end_of_turn(self.a)
  with self.assertRaisesRegex(ValueError,'voluntary League'):
   self.e.start_of_turn(self.q,initiative_count=10)
 def test_replay_after_json_does_not_pay_twice_and_changed_intent_is_rejected(self):
  self.setup_world();row=self.switch();e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
  a,p,q=e.everyone[:3];before=dump_engine(e)
  self.assertEqual(e.act_on_party(a,recall=[p],send=[(q,(2,0))],request_id='switch-1',reason='actual switch'),row)
  self.assertEqual(dump_engine(e),before)
  with self.assertRaisesRegex(ValueError,'changed'):
   e.act_on_party(a,recall=[p],send=[(q,(3,0))],request_id='switch-1',reason='actual switch')
 def test_invalid_distance_ownership_destination_and_cost_are_atomic(self):
  self.setup_world()
  for mutate,restore in ((lambda:setattr(self.p,'pos',(10,0)),lambda:setattr(self.p,'pos',(2,0))),
                         (lambda:self.q.spec.update(trainer_id='other'),lambda:self.q.spec.update(trainer_id=self.a.spec['id'])),
                         (lambda:self.e.grid.blocking.add((2,0)),lambda:self.e.grid.blocking.clear()),
                         (lambda:self.a.budget.update(standard=0),lambda:self.a.budget.update(standard=1))):
   def state():return deepcopy((self.a.spec,self.p.spec,self.q.spec,self.a.budget,self.p.on_field,self.q.on_field,self.e.rng.getstate(),self.e.log_lines))
   mutate();before=state()
   with self.assertRaises(ValueError):self.switch()
   self.assertEqual(state(),before);restore()
 def test_gm_placement_creates_no_paid_action_history(self):
  self.setup_world();self.e.gm.recall(self.p,reason='GM placement');self.e.gm.send_out(self.q,(2,0),reason='GM placement')
  self.assertNotIn(ACTIONS.KEY,self.a.spec);self.assertEqual(self.a.budget['standard'],1)
 def test_pokemon_initiative_prepaid_cost_survives_json_and_budget_reset(self):
  self.setup_world(start='pokemon');row=self.switch()
  self.assertEqual(row['payment']['phase'],'reserved')
  e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
  a,p,q=e.everyone[:3];e.end_of_turn(p);e.start_of_turn(a,initiative_count=10)
  self.assertEqual(a.budget['standard'],0)
  self.assertEqual(a.spec[ACTIONS.KEY]['switch-1']['result']['payment']['phase'],'paid')
  e.end_of_turn(a)
  with self.assertRaisesRegex(ValueError,'already used the Pokemon'):
   e.start_of_turn(q,initiative_count=5)
 def test_two_send_costs_one_standard_and_round_limit_expires(self):
  self.setup_world('league');self.p.on_field=False
  row=self.e.act_on_party(self.a,send=[(self.q,(2,0)),(self.z,(3,0))],request_id='send-two',reason='actual paired release')
  self.assertEqual(row['payment']['kind'],'standard');self.assertEqual(self.a.budget['shift'],1)
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.q,initiative_count=10);self.e.end_of_turn(self.q)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.z,initiative_count=20)
  self.assertIs(self.e._active_turn_actor,self.z)

if __name__=='__main__':unittest.main()
