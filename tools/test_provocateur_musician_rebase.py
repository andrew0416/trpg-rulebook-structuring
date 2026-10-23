"""New Musician/Provocateur seams: actual source acquisitions, Sonic immunity and cancellation."""
from pathlib import Path
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
from provocateur_fixture import ProvocateurScene
import provocateur as P
import musician as M
import trainer_feature_acquisition as TFA
import frequency as F
import move_completion as COMPLETE

class MusicianRebaseTests(ProvocateurScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def musical(self,actor,ability=None):
  TFA.acquire_static(self.e,actor,M.CLASS,acquisition_request_id=actor.entity_id+'/'+M.CLASS)
  if ability:TFA.acquire_static(self.e,actor,M.ABILITY,branch=ability,acquisition_request_id=actor.entity_id+'/'+M.ABILITY)
 def counter(self,ability):
  actor=self.add('actual Musician counter','trainer',(3,2),side='foes',classes=[],feats=[],edges=[],
   skills=dict(self.common['skills'],집중=6),speed=17)
  self.musical(actor,ability);return actor
 def test_two_actual_class_templates_and_native_ability_sources_survive_codec(self):
  speed=self.a.stats['spe'];special=self.a.stats['spa'];self.acquire(P.CLASS);self.musical(self.a,'방음')
  self.assertEqual(self.a.stats['spe'],speed+1);self.assertEqual(self.a.stats['spa'],special+2)
  self.assertTrue(set(P.MOVES[3:5])<=set(self.a.moves));self.assertIn('방음',self.a.abilities)
  self.assertIsNone(P.acquired(self.a,P.POWER));self.assertFalse(M.owns(self.a,M.CHORD))
  self.restore();self.assertEqual(self.a.stats['spe'],speed+1);self.assertEqual(self.a.stats['spa'],special+2)
  self.assertEqual(len(M._records(self.a,M.ABILITY)),1);self.valid()
 def test_native_soundproof_prevents_social_sonic_hit_and_push_refunds_only_move_quota(self):
  self.family(P.QUICK);self.acquire(P.PUSH);target=self.counter('방음');mid='move/울음소리'
  self.e.gm.set_move(self.a,mid,reason='actually learned Social Sonic Move');self.begin()
  with patch.object(Engine,'d20',return_value=20):self.e.quick_wit(self.a,target,move_id=mid)
  row=next(r for r in self.e._move_completions.values() if r['actor'] is self.a and r['move_id']==mid)
  result=COMPLETE.recipient_result(row,target)
  self.assertFalse(result['hit']);self.assertFalse(result['cancelled']);self.assertEqual(target.stages['atk'],0)
  self.assertEqual(target.hp,target.max_hp);self.assertNotIn(mid,self.a.move_uses)
  self.assertEqual(F.state(self.a)['activations'][P.QUICK]['used'],1)
  self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a.budget['standard'],1);self.valid()
 def test_native_drown_out_cancellation_spends_move_but_later_real_miss_is_refunded(self):
  self.family(P.QUICK);self.acquire(P.PUSH);target=self.counter('소리묻히기');mid='move/울음소리'
  self.e.gm.set_move(self.a,mid,reason='actually learned Social Sonic Move')
  M.request_drown_out(self.e,target,reason='actual player accepts next Sonic reaction');self.begin()
  with patch.object(Engine,'d20',return_value=5):self.e.quick_wit(self.a,target,move_id=mid)
  row=next(r for r in self.e._move_completions.values() if r['actor'] is self.a and r['move_id']==mid)
  self.assertTrue(row['drown_out']['cancelled']);self.assertTrue(COMPLETE.recipient_result(row,target)['cancelled'])
  self.assertEqual(self.a.move_uses[mid],1);self.assertFalse(P.refunded_latest(self.e,self.a,mid))
  self.assertEqual(F.state(self.a)['activations'][P.QUICK]['used'],1)
  self.assertFalse(F.activation_allowed(target,M.DROWN,'장면',engine=self.e));self.assertEqual(target.stages['atk'],0)
  self.next_round()
  with patch.object(Engine,'d20',return_value=1):self.e.quick_wit(self.a,target,move_id=mid)
  row=[r for r in self.e._move_completions.values() if r['actor'] is self.a and r['move_id']==mid][-1]
  result=COMPLETE.recipient_result(row,target)
  self.assertFalse(result['hit']);self.assertFalse(result['cancelled'])
  self.assertEqual(self.a.move_uses[mid],1);self.assertTrue(P.refunded_latest(self.e,self.a,mid))
  self.assertEqual(F.state(self.a)['activations'][P.QUICK]['used'],2);self.valid()
