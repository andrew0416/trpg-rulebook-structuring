"""Real non-Move attacks share one Confusion consequence at actual completion."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,unittest
from engine import Rules
import state_codec as CODEC,confusion_attacks as CONFUSION,control_mount as MOUNT
import test_category3_pokemon_activities as CAPTURE
import test_category3_maneuver_features as MANEUVER
import test_foundation_maneuvers_opposed as OPPOSED
import test_foundation_maneuvers_grapple as GRAPPLE
import test_category2_dream_mist as MIST
import test_category3_net_capsule as NET
import test_category2_precise_threadings as THREAD

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  root=CAPTURE.ROOT
  cls.r=Rules(root);cls.errata=Rules(root,ruleset='core+errata')
 def fixture(self,typ,errata=False):
  f=typ();f.r=f.rules=self.errata if errata else self.r;f.setUp();return f
 def confuse(self,f,actor=None):
  actor=actor or f.a;f.e.apply_status(actor,'혼란');f.e.rng.seed(1);return actor.hp
 def rows(self,e):
  return [(r,t) for r in getattr(e,'_native_action_resolutions',{}).values() for t in r['triggers'] if t['source']==CONFUSION.SOURCE]
 def finished(self,e,a,hp,amount=None):
  rows=self.rows(e);self.assertEqual(len(rows),1);r,t=rows[0]
  self.assertEqual(t['status'],'completed');self.assertEqual(t['confusion']['face'],1)
  self.assertEqual(hp-a.hp,2*e.tick(a) if amount is None else amount)
  self.assertEqual(t['confusion']['result']['amount'],hp-a.hp)
  return r['id']
 def capture(self):
  f=self.fixture(CAPTURE.PokemonActivityTests);f.a.spec['items']['몬스터볼']=2
  f.e.everyone=f.e.gm.everyone;f.e.start_round(f.e.everyone);f.e.start_of_turn(f.a);return f
 def test_capture_hit_miss_and_refusal_use_actual_ball_once(self):
  for face in (1,20):
   f=self.capture();hp=self.confuse(f)
   out=f.e.throw_ball(f.a,f.p,fixed_accuracy=face,fixed_capture=20)
   self.assertEqual(bool(out),face==20);self.finished(f.e,f.a,hp)
   self.assertEqual(f.a.spec['items']['몬스터볼'],1)
   state=(f.e.rng.getstate(),f.a.hp,deepcopy(f.a.budget),len(self.rows(f.e)))
   self.assertFalse(f.e.throw_ball(f.a,f.p,fixed_accuracy=20,fixed_capture=20))
   self.assertEqual(state,(f.e.rng.getstate(),f.a.hp,f.a.budget,len(self.rows(f.e))))
 def test_item_attack_and_net_apply_their_real_results_before_self_loss(self):
  f=self.fixture(MIST.Tests);f.prepare();hp=self.confuse(f);out=f.use(accepted=False)
  self.assertTrue(out['status_applied']);self.assertIn('잠듦',f.t.conditions);self.finished(f.e,f.a,hp)
  f=self.fixture(NET.NetTests,True)
  for a in f.e.gm.everyone:f.e.gm.set_footprint(a,[(0,0)],reason='actual one-cell body')
  hp=self.confuse(f);out=f.fire()
  self.assertEqual(out['status'],'attached');self.assertEqual(f.a.spec['items']['네트캡슐'],4);self.finished(f.e,f.a,hp)
 def test_threaded_attack_and_willing_movement_are_distinct(self):
  for willing in (False,True):
   f=self.fixture(THREAD.PreciseThreadingsTests);f.round();hp=self.confuse(f,f.p)
   out=f.use(willing=willing,**({} if willing else {'fixed_accuracy':20}))
   self.assertTrue(out['hit']);self.assertEqual(f.t.pos,(5,1))
   if willing:self.assertEqual(self.rows(f.e),[]);self.assertEqual(f.p.hp,hp)
   else:self.finished(f.e,f.p,hp)
 def test_native_maneuver_and_declared_automatic_attack_share_classes(self):
  for damage_class in ('물리','특수','변화'):
   f=self.fixture(OPPOSED.OpposedTests);hp=self.confuse(f);policy=f.policy();policy['accuracy_class']=damage_class
   out=f.run_maneuver(policy);self.assertTrue(out['success']);self.assertIn('넘어짐',f.b.conditions)
   loss=2*f.e.tick(f.a) if damage_class=='변화' else f.a.staged('atk' if damage_class=='물리' else 'spa')//2
   self.finished(f.e,f.a,hp,loss)
  f=self.fixture(OPPOSED.OpposedTests);f.grant();hp=self.confuse(f)
  out=f.e.opposed_maneuver(f.a,f.b,f.policy(1));self.assertTrue(out['success']);self.finished(f.e,f.a,hp)
  f=self.fixture(GRAPPLE.GrappleTests);hp=self.confuse(f);self.assertTrue(f.enter());self.finished(f.e,f.a,hp)
 def test_featured_disarm_and_dirty_trick_wait_then_resume_without_new_attack(self):
  for kind in ('disarm','dirty'):
   f=self.fixture(MANEUVER.Tests);f.w.pos=(7,7);hp=self.confuse(f)
   with self.assertRaises(ValueError):getattr(f,kind)(options=f.options(True))
   r,t=self.rows(f.e)[0];self.assertEqual(r['phase'],'interrupted');self.assertIsNone(t['confusion']['result']);self.assertEqual(f.a.hp,hp)
   before_rng=f.e.rng.getstate();before_budget=deepcopy(f.a.budget)
   f.e.gm.snapshot('pending confusion maneuver')
   restored=CODEC.load_engine(self.r,json.loads(json.dumps(f.e.export_state())))
   self.assertEqual(self.rows(restored)[0][1]['confusion'],t['confusion'])
   with self.assertRaises(ValueError):f.e.end_of_turn(f.a)
   self.assertTrue(getattr(f,kind)());self.finished(f.e,f.a,hp)
   self.assertEqual(f.e.rng.getstate(),before_rng);self.assertEqual(f.a.budget,before_budget)
   f.e.gm.restore('pending confusion maneuver');self.assertTrue(getattr(f,kind)());self.finished(f.e,f.a,hp)
   f.e=restored;f.a,f.b,f.w=[next(c for c in restored.everyone if c.spec['name']==n) for n in ('A','B','W')]
   self.assertTrue(getattr(f,kind)());self.finished(f.e,f.a,hp)
 def test_late_consequence_failure_restores_hp_and_resumes_only_consequence(self):
  f=self.capture();hp=self.confuse(f);original=MOUNT.confusion_loss
  def fail(*args,**kw):original(*args,**kw);raise ValueError('late native consequence')
  with patch.object(MOUNT,'confusion_loss',fail):
   with self.assertRaisesRegex(ValueError,'late native'):f.e.throw_ball(f.a,f.p,fixed_accuracy=1)
  r,t=self.rows(f.e)[0];self.assertEqual(r['phase'],'producer_returned');self.assertEqual(f.a.hp,hp)
  self.assertEqual(f.a.spec['items']['몬스터볼'],1)
  rng=f.e.rng.getstate();budget=deepcopy(f.a.budget);token=r['id']
  with self.assertRaises(ValueError):f.e.throw_ball(f.a,f.p,fixed_accuracy=1)
  f.e.resume_confusion_completion(token);self.finished(f.e,f.a,hp)
  self.assertEqual(f.e.rng.getstate(),rng);self.assertEqual(f.a.budget,budget)
  f.e.resume_confusion_completion(token);self.finished(f.e,f.a,hp)
  for e in (f.e,CODEC.load_engine(self.r,json.loads(json.dumps(f.e.export_state())))):
   before=deepcopy(self.rows(e)[0][1]['confusion']);e.resume_confusion_completion(token);self.assertEqual(self.rows(e)[0][1]['confusion'],before)
 def test_native_record_tampering_is_rejected_on_restore(self):
  f=self.capture();self.confuse(f);f.e.throw_ball(f.a,f.p,fixed_accuracy=1)
  r,t=self.rows(f.e)[0];t['attack']['class']='물리'
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,json.loads(json.dumps(f.e.export_state())))
 def test_actual_manipulation_and_ability_attack_complete_their_status_first(self):
  f=self.fixture(OPPOSED.OpposedTests)
  for a in (f.a,f.b):a.spec['skills']['교활']=4
  hp=self.confuse(f)
  self.assertTrue(f.e.manipulate(f.a,f.b,'bon_mot',defender_skill='교활',fixed_accuracy=20,
      challenger_options={'fixed':[6]*4},defender_options={'fixed':[1]*4}))
  self.assertIn('난동',f.b.conditions);self.finished(f.e,f.a,hp)
  import effects_ext as EXT
  from ruleset import bind_rule_identity
  f=self.fixture(OPPOSED.OpposedTests);f.e.gm.set_ability(f.a,'현혹',reason='actual acquired attack ability')
  uid=self.r.selection.resolve_name('현혹',('ability/',));effects=bind_rule_identity(self.r.ability_effects['현혹'],uid)
  hp=self.confuse(f)
  with patch.object(f.e,'d20',return_value=20):EXT.h_attack(f.e,f.a,f.b,effects[0],{'attacker':f.a,'target':f.b})
  self.assertIn('잠듦',f.b.conditions);self.finished(f.e,f.a,hp)
 def test_sleep_during_native_attack_blocks_its_pending_self_loss(self):
  f=self.fixture(MANEUVER.Tests);f.w.pos=(7,7);hp=self.confuse(f)
  with self.assertRaises(ValueError):f.disarm(options=f.options(True))
  f.e.apply_status(f.a,'잠듦');self.assertTrue(f.disarm())
  self.assertEqual(f.a.hp,hp);self.assertEqual(self.rows(f.e)[0][1]['confusion']['result']['reason'],'asleep')
 def test_opposed_resume_and_source_granted_free_attack_have_distinct_observations(self):
  f=self.fixture(MANEUVER.Tests);f.w.pos=(7,7)
  for a in (f.a,f.b):a.spec.update(weight_kg=30,movement={'land':4,'power':4})
  hp=self.confuse(f)
  options=dict(challenger_skill='전투',defender_skill='전투',**f.options(True))
  with self.assertRaises(ValueError):f.e.push(f.a,f.b,**options)
  rng=f.e.rng.getstate();self.assertEqual(f.a.hp,hp)
  options.update(f.options());self.assertTrue(f.e.push(f.a,f.b,**options));self.finished(f.e,f.a,hp)
  self.assertEqual(f.e.rng.getstate(),rng);self.assertEqual(f.b.pos,(3,1))
  import test_upper_maneuver_grants as UPPER,maneuver_grants as MG
  f=self.fixture(UPPER.Tests);self.confuse(f)
  f.e.use_move(f.a,f.b,'move/돌진');grant=next(iter(f.a.custom_conditions[MG.RECORDS].values()))
  self.assertTrue(f.e.resolve_maneuver_grant(f.a,grant['id'],**f.opts()).result)
  self.assertEqual(len(self.rows(f.e)),1)
  child=self.rows(f.e)[0][1];self.assertEqual(child['status'],'completed')
  self.assertEqual(child['confusion']['result']['amount'],2*f.e.tick(f.a))
  row=list(f.e._move_completions.values())[-1];self.assertEqual(row['phase'],'complete')
  self.assertEqual(row['confusion']['result']['amount'],f.a.staged('atk')//2)

if __name__=='__main__':unittest.main()
