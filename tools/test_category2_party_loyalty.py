"""Whole source state projections for ch05 party policy and private loyalty."""
from pathlib import Path
from copy import deepcopy
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine,Combatant
from builder import build_trainer
import pokemon_party as PARTY,pokemon_entities as PE,effects as FX
import test_category3_batch13_pokemon as _fixture_test_category3_batch13_pokemon

class Tests(_fixture_test_category3_batch13_pokemon.Tests):
 def test_complete_six_custom_unlimited_sale_and_statless_egg_state_survive_codec(self):
  roster=[self.p,self.q,*[self.pokemon(str(n)) for n in range(5)]];self.e.everyone=self.e.gm.everyone=[self.a,*roster]
  registry=self.policy(roster=roster)
  self.assertEqual(sum(row['location']=='carried' for row in registry.values()),6)
  self.assertEqual(registry[roster[-1].entity_id]['destination'],{'kind':'center','id':'PC1'})
  for n in range(8):
   row=PE.prepare_egg(self.e,self.a,{'id':f'egg-{n}','source':'GM established transported egg','hatched':False});self.a.spec.setdefault('eggs',[]).append(row)
  self.assertEqual(PARTY._carried(self.a),6)
  for uid,where in [('reserve','storage'),('sale','sale_transport')]:
   self.act('register_owned_reserve',pokemon_id=uid,species='브케인',location=where,reason='GM observes reserve ownership and sale purpose')
  self.assertEqual(PARTY._carried(self.a),6)
  view=self.act('party_registry');self.assertTrue(all('stats' not in row for row in view['eggs']))
  self.assertTrue(all('stats' not in view['pokemon'][uid] for uid in ('reserve','sale')))
  n=Engine.import_state(self.r,self.e.export_state());owner=next(x for x in n.everyone if x.entity_id==self.a.entity_id)
  self.assertEqual(PARTY.registry(n,owner),view)
  last=next(x for x in n.everyone if x.entity_id==roster[-1].entity_id)
  with self.assertRaises(ValueError):n.use_move(last,n.everyone[1],'struggle')
  self.policy(roster=roster,exceptions={roster[-1].entity_id:{'kind':'sale','reason':'explicit individual sale transport'}})
  self.assertEqual(PARTY._carried(self.a),6);self.assertTrue(all(t.spec['party_location']['location']=='carried' for t in roster))
  # A storage reserve still needs its actual destination even in unlimited campaigns.
  self.policy(roster=roster,mode='unlimited');self.assertIsNone(self.a.spec['pokemon_party_policy']['limit'])
  self.assertEqual(PARTY._carried(self.a),7)
 def test_actual_overflow_capture_and_professor_storage_restore(self):
  self.policy(mode='custom',limit=2,storage={'kind':'professor','id':'associated-professor'})
  wild=self.pokemon('wild');wild.spec.pop('trainer_id');wild.spec.update(wild=True,side='wild');wild.side='wild';self.e.gm.everyone.append(wild)
  self.assertTrue(self.e.throw_ball(self.a,wild,fixed_accuracy=20,fixed_capture=20))
  row=self.act('party_registry')['pokemon'][wild.entity_id]
  self.assertEqual(row['owner_id'],self.a.entity_id);self.assertEqual(row['destination'],{'kind':'professor','id':'associated-professor'});self.assertFalse(wild.on_field)
  self.e.gm.snapshot('stored');self.act('party_place',target=wild,location='carried',swap=self.p)
  self.e.gm.restore('stored');self.assertEqual(wild.spec['party_location']['location'],'storage');self.assertFalse(wild.on_field)
 def test_loyalty_all_seven_gm_observations_are_private_and_native_readers_follow(self):
  for grade in range(7):
   out=self.e.gm.observe_loyalty(self.p,grade,reason='GM judges actual relationship',request_id='grade-'+str(grade))
   self.assertEqual(out['after'],grade);self.assertEqual(PE.loyalty_value(self.p,required=True),grade)
   player=self.e.gm.describe_actor(self.p);gm=self.e.gm.describe_actor(self.p,viewer='gm')
   self.assertNotIn('loyalty',player);self.assertEqual(player['loyalty_state'],{})
   self.assertEqual(gm['loyalty_state']['value'],grade);self.assertEqual(gm['loyalty_state']['meaning'],PE.LOYALTY_MEANINGS[grade])
   self.assertEqual(FX.evaluate('3 + user.loyalty',{'attacker':self.p}),3+grade)
   if grade>=2:self.assertTrue(self.act('command_loyalty',target=self.p)['obeys'])
  self.e.gm.observe_loyalty(self.p,3,reason='private reason not public',hint='seems at ease',request_id='hint')
  self.assertEqual(self.e.gm.describe_actor(self.p)['loyalty_state'],{'hint':'seems at ease'})
  self.assertFalse(any('private reason not public' in str(x) for x in self.e.log_lines))
  self.e.advance_time(7200);self.assertEqual(PE.loyalty_value(self.p),3)
  self.e.gm.snapshot('loyalty');self.e.gm.observe_loyalty(self.p,1,reason='GM adjudicated a change');self.e.gm.restore('loyalty')
  self.assertEqual(PE.loyalty_value(self.p),3)
  n=Engine.import_state(self.r,self.e.export_state());other=next(x for x in n.everyone if x.entity_id==self.p.entity_id)
  self.assertEqual(PE.loyalty_projection(other,viewer='gm'),PE.loyalty_projection(self.p,viewer='gm'));self.assertEqual(PE.loyalty_projection(other),{'hint':'seems at ease'})
 def test_loyalty_unknown_invalid_atomicity_and_observation_replay(self):
  self.assertIsNone(PE.loyalty_value(self.p));self.assertIsNone(FX.evaluate('3 + user.loyalty',{'attacker':self.p}))
  with self.assertRaises(ValueError):self.act('command_loyalty',target=self.p)
  for value in [-1,7,True,1.5]:
   before=deepcopy(self.p.spec)
   with self.assertRaises(ValueError):self.e.gm.observe_loyalty(self.p,value,reason='invalid')
   self.assertEqual(self.p.spec,before)
  before=deepcopy(self.p.spec)
  with self.assertRaises(ValueError):self.e.gm.observe_loyalty(self.p,3,reason='')
  self.assertEqual(self.p.spec,before)
  receipt=self.e.gm.observe_loyalty(self.p,3,reason='actual relationship',request_id='once');before=deepcopy(self.p.spec)
  self.assertEqual(self.e.gm.observe_loyalty(self.p,3,reason='actual relationship',request_id='once'),receipt);self.assertEqual(self.p.spec,before)
  with self.assertRaises(ValueError):self.e.gm.observe_loyalty(self.p,4,reason='actual relationship',request_id='once')
  self.assertEqual(self.p.spec,before)
  with self.assertRaises(ValueError):self.e.gm.observe_loyalty(self.p,4,reason='stale edit',expected_revision=0)
  self.assertEqual(self.p.spec,before)
 def test_native_unknown_command_is_pending_before_cost_or_movement(self):
  import common_checks as C
  import pokemon_requests as REQUEST
  self.policy();self.intelligence()
  state=lambda:deepcopy((self.e.rng.getstate(),{k:v for k,v in self.p.__dict__.items() if k!='r'},{k:v for k,v in self.q.__dict__.items() if k!='r'},self.e.elapsed_seconds))
  before=state()
  result=self.e.use_move(self.p,self.q,'struggle');self.assertIsInstance(result,C.PendingDecision)
  self.assertEqual(before,state())
  result=self.e.use_move_on(self.p,self.q,'struggle',self.e.everyone);self.assertIsInstance(result,C.PendingDecision)
  self.assertEqual(before,state())
  self.e.gm.observe_loyalty(self.p,4,reason='private observation')
  response=REQUEST.request(self.e,self.a,target=self.p,request_id='help',intent='help with a safe task')
  self.assertNotIn('loyalty_at_submission',response['request'])
  legacy=dict(response['request'],loyalty_at_submission=4);self.assertNotIn('loyalty_at_submission',REQUEST._public(legacy))
 def test_transfer_preserves_each_observed_relationship_and_never_invents_new_affection(self):
  self.policy();second=Combatant(self.r,build_trainer(self.r,'other',5,dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10)));self.e.gm.add_combatant(second)
  PARTY.configure(self.e,second,mode='standard',reason='campaign',roster=[],storage={'kind':'center','id':'PC2'})
  self.e.gm.observe_loyalty(self.p,5,reason='old owner actual friendship',hint='trusts the old owner')
  PARTY.transfer(self.e,self.a,target=self.p,new_owner=second,reason='observed gift',request_id='out')
  self.assertIsNone(self.p.spec['loyalty']);self.assertEqual(PE.loyalty_projection(self.p),{})
  self.assertEqual(self.p.spec['loyalty_relations'][self.a.entity_id]['value'],5)
  self.e.gm.observe_loyalty(self.p,2,reason='new owner actual relationship')
  self.e.advance_time(1000)
  PARTY.transfer(self.e,second,target=self.p,new_owner=self.a,reason='observed return',request_id='back')
  self.assertEqual(self.p.spec['loyalty'],5);self.assertEqual(self.p.spec['loyalty_relations'][second.entity_id]['value'],2)
  self.assertEqual(PE.loyalty_projection(self.p),{'hint':'trusts the old owner'})

if __name__=='__main__':
 names=[n for n in Tests.__dict__ if n.startswith('test_')]
 result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(n) for n in names));sys.exit(not result.wasSuccessful())
