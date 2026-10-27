"""Only real local-CSV differences; reuse the Book's native fixture by composition."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_book_telekinetic_full as book
from engine import Rules,Engine
from ruleset import RuleFilter
import telekinetic as TK,trainer_feature_acquisition as ACQ,state_grants as G
import action_points as AP,combat_move_reactions as REACTIONS,combat_timing as TIME
import trainer_retraining as RETRAIN,weapon_actions as WA

class CSVTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')
 def setUp(self):
  self.f=book.TelekineticTests();self.f.rules=self.rules;self.f.setUp();self.addCleanup(self.f.doCleanups)
 def family(self,u):
  f=self.f
  for parent in TK.PARENTS[u]:
   if not TK.acquired(f.a,parent):self.family(parent)
  if not TK.acquired(f.a,u):f.acquire(u,selection={'edition':'local_csv'} if u in TK.CSV_VARIANTS else TK.LEVITATE if u==TK.POWER else None)

 def test_whole_seven_source_choices_grants_immutable_replay_and_restore(self):
  f=self.f;before=f.a.stats['spa'];self.family(TK.CLASS)
  self.assertIn(TK.KINESIS,f.a.moves);self.assertFalse(TK.acquired(f.a,TK.ALPHA));self.assertEqual(f.a.stats['spa'],before+1)
  self.family(TK.ALPHA);self.assertIn(TK.PSYSHOCK,f.a.moves);self.assertIn(TK.BARRIER,f.a.moves)
  for u in TK.FEATURES:self.family(u)
  self.assertEqual(len(TK.records(f.a,active=True)),7);self.assertEqual(f.a.stats['spa'],before+7)
  for u in TK.CSV_VARIANTS:self.assertEqual(TK.acquired(f.a,u)['snapshot']['source'],TK.csv_source(self.rules,u))
  f.reject(lambda:f.acquire(TK.OVERLOAD,selection={'edition':'core'}),'selection')
  f.restore();f.valid();self.assertTrue(TK.local_csv(f.a,TK.OVERLOAD));self.assertIn(TK.PSYSHOCK,f.a.moves)

 def test_csv_combat_capability_without_class_actual_remote_use_and_withdrawal(self):
  f=self.f
  G.transition(f.e,f.a,lambda e,a:G.grant(a,'capabilities','염력','actual:innate-telekinetic','feature',rule_id='capability/염력',owner_id=a.entity_id,lifetime='permanent'))
  f.reject(lambda:f.acquire(TK.COMBAT),'parent')
  f.acquire(TK.COMBAT,selection={'edition':'local_csv'});self.assertFalse(TK.acquired(f.a,TK.CLASS))
  f.begin();f.e.activate_pk_combat(f.a,instance_id='csv-bound');uid,key=f.weapon();f.begin()
  with patch.object(Engine,'d20',return_value=18):f.e.use_telekinetic_weapon(f.a,f.b,key,key,use_spa=True,set_damage=True)
  self.assertLess(f.b.hp,f.b.max_hp);self.assertEqual(f.completion(f.a,key)['move']['class'],'물리');self.assertNotIn(TK.COMBAT,RETRAIN._native_dependencies(f.e,f.a,RETRAIN._owned(f.a)))
  f.restore();f.valid();f.begin()
  owned=RETRAIN._owned(f.a);sources={u:RETRAIN.owned_source(f.e,f.a,u) for u in owned};required=RETRAIN._native_dependencies(f.e,f.a,owned)
  deps={sid:[sources[p] for p in required.get(u,[])] for u,sid in sources.items() if u!=TK.COMBAT}
  f.e.retrain_trainer_source(f.a,TK.COMBAT,request_id='csv-combat-withdraw',reason='actual retraining',gm_decision={'allowed':True,'reason':'approved'},retained_dependencies=deps)
  self.assertFalse(TK.active_combat(f.a));self.assertFalse(f.a.custom_conditions.get('equipped_weapons'));f.restore();f.valid()

 def test_csv_missing_capability_and_core_exclusion_are_atomic(self):
  f=self.f;f.reject(lambda:f.acquire(TK.COMBAT,selection={'edition':'local_csv'}),'parent')
  profile=deepcopy(self.rules.ruleset.profile);profile['exclude_units']=['C2CSV/input/db/feats.csv:R495:main']
  with patch.object(RuleFilter,'load',return_value=RuleFilter(profile,'csv-class-excluded')):f.rules=Rules(ROOT,ruleset='all')
  f.setup();f.reject(lambda:f.acquire(TK.CLASS,selection={'edition':'local_csv'}),'exclude_units')
  f.rules=Rules(ROOT,ruleset='core');f.setup();f.acquire();self.assertNotIn(TK.KINESIS,f.a.moves);f.family(TK.ALPHA);self.assertIn(TK.KINESIS,f.a.moves);self.assertNotIn(TK.PSYSHOCK,f.a.moves);f.valid()

 def test_csv_burst_two_ap_swift_actual_trip(self):
  f=self.f;self.family(TK.BURST);f.begin();before=AP.available(f.a)
  self.assertTrue(f.e.telekinetic_burst(f.a,f.b,'trip',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*2}))
  self.assertIn('넘어짐',f.b.conditions);self.assertEqual(AP.available(f.a),before-2);self.assertEqual(f.a.budget['standard'],1);self.assertEqual(f.a.budget['swift'],0);f.restore();f.valid()

 def test_csv_overload_existing_three_branches_each_one_ap(self):
  f=self.f
  for mid in (TK.BARRIER,TK.PSYCHIC,TK.LIFT):
   with self.subTest(move=mid):
    f.setup();self.family(TK.OVERLOAD);before=AP.available(f.a)
    f.cast(mid,overload=True,segments=[((3+i,5),(3+i,6)) for i in range(6)] if mid==TK.BARRIER else None)
    self.assertEqual(AP.available(f.a),before-1);self.assertEqual(f.a.budget['swift'],0)
    if mid==TK.BARRIER:self.assertEqual(len(f.e.grid.walls),6)
    if mid==TK.PSYCHIC:self.assertIn('취약',f.b.conditions)
    if mid==TK.LIFT:self.assertTrue(TK.lifted(f.b));f.close();f.turn(f.b);hp=f.b.hp;f.close();self.assertEqual(f.b.hp,hp-f.e.tick(f.b))
    f.restore();f.valid()

 def test_csv_kinesis_original_attacker_confusion_one_ap_once(self):
  f=self.f;self.family(TK.OVERLOAD);REACTIONS.arm(f.e,f.a,TK.KINESIS,protect=f.c,overload=True);f.begin();before=AP.available(f.a)
  with patch.object(Engine,'d20',return_value=18):f.e.use_move(f.a,f.c,'move/물대포',set_damage=True)
  event=next(r for r in f.a.spec[REACTIONS.EVENTS].values() if r['source']==TK.KINESIS)
  self.assertTrue(event['overload_spent']);self.assertIn('혼란',f.a.conditions);self.assertNotIn('혼란',f.c.conditions);self.assertEqual(AP.available(f.a),before-1);self.assertEqual(f.a.budget['swift'],0);f.restore();f.valid()

 def test_csv_psyshock_blast_two_actual_recipients_one_activation_payment(self):
  f=self.f;self.family(TK.OVERLOAD);f.e.gm.set_position(f.c,(6,3),reason='second actual Psyshock recipient');f.begin();before=AP.available(f.a);hp=(f.b.hp,f.c.hp)
  with patch.object(Engine,'d20',return_value=18):f.e.use_telekinetic_move(f.a,f.b,TK.PSYSHOCK,overload=True,aim=(6,2))
  rows=[r for r in f.e._move_completions.values() if r['actor'] is f.a and r['move_id']==TK.PSYSHOCK]
  self.assertEqual({t.entity_id for r in rows for t in r['targets']},{f.b.entity_id,f.c.entity_id});self.assertTrue(all(WA.range_spec(f.e,r['move'],f.a)['origin']==4 and WA.range_spec(f.e,r['move'],f.a)['size']==2 for r in rows))
  self.assertLess(f.b.hp,hp[0]);self.assertLess(f.c.hp,hp[1]);self.assertEqual(AP.available(f.a),before-1);self.assertEqual(f.a.budget['standard'],0);self.assertEqual(f.a.budget['swift'],0);f.restore();f.valid()

 def test_csv_psyshock_miss_consumes_once_range_refusal_and_late_rollback(self):
  f=self.f;self.family(TK.OVERLOAD);f.begin()
  f.reject(lambda:f.e.use_telekinetic_move(f.a,f.b,TK.PSYSHOCK,overload=True,aim=(7,2)),'outside')
  original=TK.pay
  def late(*args,**kwargs):original(*args,**kwargs);raise ValueError('late CSV Overload payment')
  with patch.object(TK,'pay',late),patch.object(Engine,'d20',return_value=18):f.reject(lambda:f.e.use_telekinetic_move(f.a,f.b,TK.PSYSHOCK,overload=True,aim=(6,2)),'late CSV')
  before=AP.available(f.a);hp=f.b.hp
  with patch.object(Engine,'d20',return_value=1):f.e.use_telekinetic_move(f.a,f.b,TK.PSYSHOCK,overload=True,aim=(6,2))
  self.assertEqual(f.b.hp,hp);self.assertEqual(AP.available(f.a),before-1);self.assertEqual(f.a.budget['swift'],0);f.restore();f.valid()

 def test_core_overload_cannot_invent_csv_psyshock_branch(self):
  f=self.f;f.family(TK.OVERLOAD);f.e.gm.set_move(f.a,TK.PSYSHOCK,reason='independently learned ordinary Psyshock');f.begin()
  f.reject(lambda:f.e.use_telekinetic_move(f.a,f.b,TK.PSYSHOCK,overload=True,aim=(6,2)),'CSV acquisition')
  with patch.object(Engine,'d20',return_value=18):f.e.use_move(f.a,f.b,TK.PSYSHOCK,set_damage=True)
  self.assertEqual(AP.available(f.a),AP.maximum(f.a));self.assertEqual(f.a.budget['swift'],1);f.valid()

 def test_declared_seven_plus_focus_native_acquisition_and_restore_preserve_strict_rank_membership(self):
  import trainer_feature_acquisition as T
  f=self.f
  f.reject(lambda:f.e.gm.set_skill(f.a,'집중',7,reason='undeclared ordinary Focus rank'),'ordinary|rank')
  for name,rank,dice in (('초월',7,'7d6'),('전설',9,'9d6'),('신화',10,'7d6')):
   self.rules.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.'+name,
    {'rank':rank,'dice':dice},reason='actual U-001 campaign rank declaration',scope='campaign',rules=self.rules)
  for edition in ('core','local_csv'):
   for rank in (7,9,10):
    with self.subTest(edition=edition,rank=rank):
     f.setup();f.e.gm.set_skill(f.a,'집중',rank,reason='actual declared ordinary Focus')
     if edition=='local_csv':self.family(TK.OVERLOAD)
     else:f.family(TK.OVERLOAD)
     self.assertEqual(TK.acquired(f.a,TK.OVERLOAD)['snapshot']['rank'],rank)
     f.restore();T.validate_actor(f.a);f.valid()
     self.assertEqual(TK.acquired(f.a,TK.OVERLOAD)['snapshot']['rank'],rank)
     observed=TK.acquisition_snapshot(f.e,f.a,TK.CLASS,None,{'edition':'local_csv'} if edition=='local_csv' else None)
     for bad in (True,7.0,8):
      damaged=deepcopy(observed);damaged['rank']=bad
      with self.assertRaises(ValueError):TK.qualification(f.a,TK.CLASS,damaged,None)
