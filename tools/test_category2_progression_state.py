"""Actual XP/TP/training transitions, atomic failure, identity and persistence."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
import downtime as D,pokemon_progression as P,pokemon_teaching as T
import state_codec as CODEC,pokemon_party as PARTY

class ProgressionStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=701)
  self.a=self.add(build_trainer(self.r,'trainer',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':4,'포켓몬학':4,'생존':4},extra={'items':{},'edges':[]}))
 def add(self,spec):
  c=Combatant(self.r,spec);self.e.gm.add_combatant(c,pos=(0,0),side='party',reason='actual state');return c
 def pokemon(self,level=5,**extra):
  return self.add(build_pokemon(self.r,'잉어킹',level,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,**extra}))
 def train(self,*targets,**kw):return self.e.pokemon_activity(self.a,'experience_training',targets=list(targets),**kw,safe=True)
 def snap(self):return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[vars(x) for x in self.e.gm.everyone],self.e.log_lines),{id(self.r):self.r})
 def restored(self):return CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
 def test_cumulative_threshold_multilevel_and_maximum_are_actual_native_state(self):
  c=self.pokemon(1)
  D.gain_exp_combatant(self.e,c,9);self.assertEqual((c.spec['exp'],c.level),(9,1))
  D.gain_exp_combatant(self.e,c,1);self.assertEqual((c.spec['exp'],c.level),(10,2))
  D.gain_exp_combatant(self.e,c,30);self.assertEqual((c.spec['exp'],c.level,c.spec['tutor_points']),(40,5,2))
  c=self.pokemon(99)
  D.gain_exp_combatant(self.e,c,D.exp_for_level(self.r,100)-D.exp_for_level(self.r,99))
  self.assertEqual((c.level,c.spec['tutor_points']),(100,21))
  points=c.spec['tutor_points'];stats=deepcopy(c.stats);old=c.spec['exp']
  D.gain_exp_combatant(self.e,c,1000000)
  self.assertEqual((c.level,c.stats,c.spec['tutor_points'],c.spec['exp']),(100,stats,points,old+1000000))
 def test_invalid_xp_or_balance_reject_before_any_native_mutation(self):
  c=self.pokemon(4)
  for bad in (-1,True,float('inf'),float('nan')):
   before=self.snap()
   with self.assertRaises(ValueError):D.gain_exp_combatant(self.e,c,bad)
   self.assertEqual(self.snap(),before)
  c.spec['tutor_points']=False;before=self.snap()
  with self.assertRaises(ValueError):D.gain_exp_combatant(self.e,c,10)
  self.assertEqual(self.snap(),before)
 def test_new_creation_and_fifth_levels_keep_actual_unspent_balance(self):
  c=self.pokemon(1);self.assertEqual(c.spec['tutor_points'],1)
  D.gain_exp_combatant(self.e,c,D.exp_for_level(self.r,10))
  self.assertEqual((c.level,c.spec['tutor_points']),(10,3))
  self.assertEqual([x['level'] for x in c.spec[P.LEVEL_STATE]['awards']],[5,10])
  c.spec['tutor_points']=0
  D.gain_exp_combatant(self.e,c,'to next level');self.assertEqual(c.spec['tutor_points'],0)
  self.e.gm.set_level(c,4,reason='observed GM correction')
  D.gain_exp_combatant(self.e,c,0)
  self.assertEqual(c.spec['tutor_points'],0) # reaching already-awarded levels never pays twice
 def test_imported_unknown_balance_retains_new_awards_until_actual_observation(self):
  c=self.pokemon(4);c.spec.pop('tutor_points');c.spec.pop(P.LEVEL_STATE)
  D.gain_exp_combatant(self.e,c,'to next level')
  view=P.projection(c.spec)['tutor_points']
  self.assertFalse(view['known']);self.assertEqual(view['level_awards']['pending_points'],1)
  self.assertEqual(self.restored().gm.everyone[-1].spec[P.LEVEL_STATE],c.spec[P.LEVEL_STATE])
  out=self.e.pokemon_activity(self.a,'observe_tutor_points',target=c,balance=4,reason='GM checked current sheet including new award')
  self.assertEqual((out['balance'],out['pending_included']),(4,1))
  self.assertEqual(c.spec[P.LEVEL_STATE]['pending_points'],0)
 def test_unknown_imported_xp_is_not_fabricated_from_its_current_level(self):
  c=self.pokemon(4);c.spec.pop('exp');before=self.snap()
  with self.assertRaisesRegex(ValueError,'XP is unknown'):D.gain_exp_combatant(self.e,c,7)
  self.assertEqual(self.snap(),before);self.assertFalse(P.projection(c.spec)['xp']['known'])
  self.e.pokemon_activity(self.a,'observe_pokemon_xp',target=c,total=35,reason='GM checked actual cumulative experience')
  D.gain_exp_combatant(self.e,c,7);self.assertEqual((c.level,c.spec['exp']),(5,42))
 def test_pending_awards_cannot_disappear_without_reconciliation(self):
  c=self.pokemon(4);c.spec.pop('tutor_points');c.spec.pop(P.LEVEL_STATE)
  D.gain_exp_combatant(self.e,c,'to next level');c.spec[P.LEVEL_STATE]['pending_points']=0
  with self.assertRaisesRegex(ValueError,'reconciliation'):P.projection(c.spec)
 def test_hour_training_records_real_targets_once_per_day_and_sourced_bonus(self):
  targets=[self.pokemon(5) for _ in range(5)]
  before=self.e.elapsed_seconds
  out=self.train(*targets[:4]);self.assertEqual(out['awards'],[7]*4)
  self.assertEqual(self.e.elapsed_seconds-before,3600)
  self.assertEqual(self.a.spec['experience_training']['target_ids'],[c.entity_id for c in targets[:4]])
  for c in targets[:4]:
   self.assertEqual(c.spec['exp'],47);self.assertEqual(c.spec['experience_training_day'],0)
   self.assertEqual(c.spec['experience_training_history'][0]['trainer_id'],self.a.entity_id)
  for c in (targets[0],targets[4]):
   before=self.snap()
   with self.assertRaises(ValueError):self.train(c)
   self.assertEqual(self.snap(),before)
  self.e.advance_time(24*3600)
  for c in self.e.time_actors():D.new_day(c)
  self.train(targets[0]);self.assertEqual(self.a.spec['experience_training']['count'],1)
  self.assertEqual(self.a.spec['experience_training']['target_ids'],[targets[0].entity_id])
 def test_new_owner_cannot_repeat_same_day_and_gm_restore_keeps_daily_identity(self):
  c=self.pokemon();self.train(c)
  other=self.add(build_trainer(self.r,'new owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':4}))
  PARTY.configure(self.e,self.a,mode='unlimited',reason='actual party',roster=[c])
  PARTY.configure(self.e,other,mode='unlimited',reason='actual party',roster=[])
  PARTY.transfer(self.e,self.a,target=c,new_owner=other,reason='actual trade',request_id='training-trade')
  before=self.snap()
  with self.assertRaises(ValueError):self.e.pokemon_activity(other,'experience_training',targets=[c],safe=True)
  self.assertEqual(before,self.snap())
  saved=self.e.gm.snapshot();c.spec['experience_training_day']=100;self.e.gm.restore(saved)
  current={x.entity_id:x for x in self.e.gm.everyone}
  self.assertEqual(current[c.entity_id].spec['experience_training_day'],0)
  loaded=self.restored();current={x.entity_id:x for x in loaded.gm.everyone}
  with self.assertRaises(ValueError):loaded.pokemon_activity(current[other.entity_id],'experience_training',targets=[current[c.entity_id]],safe=True)
 def test_second_target_runtime_failure_rolls_back_time_first_target_and_ledgers(self):
  a=self.pokemon();b=self.pokemon();before=self.snap();native=D.gain_exp_combatant
  def fail_second(e,c,amount):
   if c.entity_id==b.entity_id:raise ValueError('simulated second native registration failure')
   return native(e,c,amount)
  with patch.object(D,'gain_exp_combatant',side_effect=fail_second):
   with self.assertRaisesRegex(ValueError,'second native'):self.train(a,b)
  self.assertEqual(before,self.snap())
 def test_invalid_daily_counts_and_duplicate_persistent_actors_reject_atomically(self):
  c=self.pokemon()
  for bad in (-1,True,1.5):
   self.a.spec['experience_training']={'day':0,'count':bad};before=self.snap()
   with self.assertRaises(ValueError):self.train(c)
   self.assertEqual(self.snap(),before)
  self.a.spec.pop('experience_training')
  duplicate=Combatant(self.r,deepcopy(c.spec));before=self.snap()
  with self.assertRaises(ValueError):self.train(c,duplicate)
  self.assertEqual(self.snap(),before)
 def test_tp_awards_daily_ledgers_and_cumulative_xp_survive_durable_restore(self):
  c=self.pokemon(4);self.train(c);D.gain_exp_combatant(self.e,c,'to next level')
  expected=P.projection(c.spec);saved=self.e.gm.snapshot()
  self.e.gm.set_level(c,30,reason='temporary correction');self.e.gm.restore(saved)
  current={x.entity_id:x for x in self.e.gm.everyone};self.assertEqual(P.projection(current[c.entity_id].spec),expected)
  loaded=self.restored();current={x.entity_id:x for x in loaded.gm.everyone}
  self.assertEqual(P.projection(current[c.entity_id].spec),expected)
  self.assertEqual(P.projection(current[self.a.entity_id].spec)['training']['target_ids'],[c.entity_id])
  current[c.entity_id].spec[P.LEVEL_STATE]['awards'].append(deepcopy(current[c.entity_id].spec[P.LEVEL_STATE]['awards'][0]))
  self.assertFalse(loaded.validate_state()['valid'])
  with self.assertRaises(ValueError):CODEC.dump_engine(loaded)
 def test_real_fossil_hatch_receives_fresh_budget_and_no_repeat_hatch(self):
  self.a.spec['edges']=['edge/고생물학자'];self.a.spec['items']={'복원기':1}
  self.a.spec['fossils']={'f1':{'species':'pokemon/암나이트','status':'fossil'}}
  self.e.pokemon_activity(self.a,'fossil',phase='restore',fossil_id='f1')
  egg=self.a.spec['eggs'][0]
  args=dict(egg_id=egg['id'],name='hatched',ready=True,reason='GM confirmed readiness',details=dict(gender='female',nature='노력',abilities=['조가비갑옷'],moves=[],special_appearance=False,inheritance_moves=[]))
  c=self.e.pokemon_activity(self.a,'hatch_fossil',**args)['pokemon']
  self.assertEqual((c.level,c.spec['tutor_points'],c.spec[P.LEVEL_STATE]['initial_level']),(10,3,10))
  self.assertEqual(c.abilities,['조가비갑옷'])
  before=self.snap()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'hatch_fossil',**args)
  self.assertEqual(self.snap(),before)
  loaded=self.restored();self.assertEqual(next(x for x in loaded.gm.everyone if x.entity_id==c.entity_id).spec['tutor_points'],3)

if __name__=='__main__':unittest.main()
