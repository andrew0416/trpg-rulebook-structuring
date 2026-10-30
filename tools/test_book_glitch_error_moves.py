"""Printed Error Moves: edition table, timed statuses, disables, random stages, Pain Swap, Teleport Crash.

Source declarations only; not locally run. Reuses the Glitch Bender fixture:
a homebrew teacher, a 폴리곤 pupil taught the Move, and real native use.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_book_glitch_bender_full as _fixture
from engine import Engine
import glitch_bender as B,glitch_moves as M,combat_timing as TIME,condition_instances as CONDITIONS
import roll_pools as POOLS


class ErrorMoveTests(unittest.TestCase):
 setUpClass=classmethod(_fixture.GlitchBenderFullTests.setUpClass.__func__)
 setUp=_fixture.GlitchBenderFullTests.setUp
 scene=_fixture.GlitchBenderFullTests.scene
 acquire=_fixture.GlitchBenderFullTests.acquire
 family=_fixture.GlitchBenderFullTests.family
 begin=_fixture.GlitchBenderFullTests.begin
 turn=_fixture.GlitchBenderFullTests.turn
 native=_fixture.GlitchBenderFullTests.native
 restore=_fixture.GlitchBenderFullTests.restore
 valid=_fixture.GlitchBenderFullTests.valid
 reject=_fixture.GlitchBenderFullTests.reject
 tamper=_fixture.GlitchBenderFullTests.tamper
 pupil=_fixture.GlitchBenderFullTests.pupil

 FEATURE={name:feature for feature,names in B.TEACHING.items() for name in names}

 def select_edition(self,mid,edition):
  """Select an Error Move edition like existing version tests: a fresh Rules whose profile carries unit_versions.

  Named select_edition because scene() stores the lesson edition string in self.edition."""
  cls=type(self)
  self.addCleanup(lambda:(setattr(self,'rules',cls.rules),setattr(self,'base_rulings',cls.base_rulings)))
  if edition=='glitch-csv':
   self.rules,self.base_rulings=cls.rules,cls.base_rulings;return
  cache=cls.__dict__.get('_edition_rules') or {};key=(mid,edition)
  if key not in cache:
   from ruleset import RuleFilter
   rules=_fixture.Rules(_fixture.ROOT,ruleset='polygon');profile=deepcopy(rules.ruleset.profile)
   profile['unit_versions']={**profile.get('unit_versions',{}),mid:edition}
   rules.ruleset=RuleFilter(profile);rules._apply_ruleset();cache[key]=(rules,deepcopy(rules.rulings));cls._edition_rules=cache
  self.rules,self.base_rulings=cache[key][0],deepcopy(cache[key][1])

 def learner(self,name,*,pos=(2,6)):
  """Teach one printed Error Move to a real pupil through the actual homebrew lesson."""
  self.scene(edition='homebrew');self.family(self.FEATURE[name])
  p=self.pupil(points=2);B.teach(self.e,self.a,p,self.FEATURE[name],name,seconds=30,reason='actual native taught reference')
  self.e.gm.set_position(p,pos,reason='actual Error Move user');self.e.gm.set_position(self.b,(3,6),reason='actual recipient');self.e.gm.set_position(self.c,(4,6),reason='second recipient')
  return p,self.rules.move_id(name)

 def rows(self,actor,source):
  return [r for r in TIME.records(actor) if r.get('glitch_move',{}).get('source')==source]

 def test_edition_table_follows_selected_csv_or_supplement_source(self):
  table={M.DRAIN:(('damage_base',9,10),('frequency','턴1회','턴1회')),M.REND:(('frequency','턴1회','임의'),),
         M.PULSE:(('damage_base',5,8),),M.STRIKE:(('damage_base',7,8),)}
  for mid,fields in table.items():
   for edition,column in (('glitch-csv',1),('glitch-supplement',2)):
    with self.subTest(move=mid,edition=edition):
     self.select_edition(mid,edition);move=self.rules.move(mid)
     for field,*values in fields:self.assertEqual(move[field],values[column-1])
     self.assertEqual(move['_glitch_move_source']['edition'],edition)
  self.select_edition(M.ACCESS,'glitch-supplement')
  with self.assertRaisesRegex(ValueError,'no printed supplement definition'):self.rules.move(M.ACCESS)

 def test_access_denied_one_round_slow_and_at_will_only_then_exact_expiry(self):
  p,mid=self.learner('액세스 거부');self.begin(p,count=50)
  self.native(p,self.b,mid)
  self.assertIn('둔화',self.b.conditions);self.assertEqual(len(self.rows(self.b,M.ACCESS)),1)
  self.assertFalse(B.frequency_allowed(self.b,'scene'));self.assertTrue(B.frequency_allowed(self.b,'at_will'))
  self.turn(self.b,count=40);uses=deepcopy(self.b.move_uses);budget=deepcopy(self.b.budget)
  self.assertEqual(self.native(self.b,self.b,'move/칼춤'),0);self.assertEqual((self.b.move_uses,self.b.budget),(uses,budget))  # the ordinary admission declines a non-At-Will action without cost or use
  self.restore();self.valid()
  self.e.end_of_turn(self.b);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(51)
  self.assertTrue(self.rows(self.b,M.ACCESS));self.e.at_initiative_count(50)
  self.assertFalse(self.rows(self.b,M.ACCESS));self.assertNotIn('둔화',self.b.conditions);self.assertTrue(B.frequency_allowed(self.b,'scene'));self.valid()

 def test_polygon_shock_blind_and_vulnerable_one_round_keeps_preexisting_blind(self):
  p,mid=self.learner('폴리곤 쇼크');self.e.apply_status(self.b,'실명',source='gm/earlier independent Blind');self.begin(p,count=50)
  self.native(p,self.b,mid)
  self.assertIn('취약',self.b.conditions);self.assertIn('실명',self.b.conditions);self.restore();self.valid();p=self.people[-1]  # restore() rebinds actors
  self.e.end_of_turn(p);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(50)
  self.assertNotIn('취약',self.b.conditions);self.assertIn('실명',self.b.conditions);self.assertFalse(self.rows(self.b,M.SHOCK));self.valid()

 def test_blue_screen_disables_each_recipient_last_move_in_the_blast(self):
  p,mid=self.learner('블루 스크린',pos=(2,2))
  self.begin(self.b);self.native(self.b,self.a,'move/울음소리');self.turn(self.c,count=45)
  self.native(self.c,self.c,'move/칼춤')  # its own last Move (a Self Move: no melee reach needed; Blast 2 is a two-cell square at the aim)
  self.turn(p,count=40)
  with patch.object(Engine,'d20',return_value=20):self.e.use_move_on(p,self.b,mid,[p,self.b,self.c],aim=self.b.pos,set_damage=True)
  self.assertEqual([r['effect']['move_id'] for r in CONDITIONS.records(self.b,'사슬묶기')],['move/울음소리'])
  self.assertEqual([r['effect']['move_id'] for r in CONDITIONS.records(self.c,'사슬묶기')],['move/칼춤'])
  self.restore();self.valid()

 def test_threshold_moves_apply_only_on_selected_edition_faces(self):
  cases=((M.DRAIN,'데이터 드레인','억압',17,19),(M.STRIKE,'버그 스트라이크','억압',19,18),(M.PULSE,'버그 파동','사슬묶기',18,19))
  for mid,name,condition,csv_face,supplement_face in cases:
   for edition,threshold in (('glitch-csv',csv_face),('glitch-supplement',supplement_face)):
    for face in (threshold-1,threshold):
     with self.subTest(move=name,edition=edition,face=face):
      self.select_edition(mid,edition);p,mid_=self.learner(name)  # pupil (2,6) is adjacent to the recipient (3,6) for the melee Strike
      self.begin(self.b);self.native(self.b,self.a,'move/울음소리');self.turn(p,count=40)
      self.native(p,self.b,mid_,accuracy=face)
      self.assertEqual(condition in self.b.conditions,face>=threshold)
      self.restore();self.valid()

 def test_glitch_pulse_csv_keeps_one_disabled_move_while_supplement_accumulates(self):
  for edition,expected in (('glitch-csv',1),('glitch-supplement',2)):
   with self.subTest(edition=edition):
    self.select_edition(M.PULSE,edition);p,mid=self.learner('버그 파동')
    self.begin(self.b);self.native(self.b,self.a,'move/울음소리');self.turn(p,count=45);self.native(p,self.b,mid,accuracy=20)
    self.begin(self.b,count=44);self.e.gm.set_position(self.b,(3,4),reason='adjacent to its melee target, still within six metres of the user');self.native(self.b,self.a,'move/몸통박치기');self.turn(p,count=43);self.native(p,self.b,mid,accuracy=20)  # a new round: one ordinary turn per actor per round
    moves={r['effect']['move_id'] for r in CONDITIONS.records(self.b,'사슬묶기')}
    self.assertEqual(len(moves),expected);self.assertIn('move/몸통박치기',moves);self.restore();self.valid()

 def test_disruption_wave_lowers_two_distinct_random_stages_per_recipient(self):
  p,mid=self.learner('방해 웨이브');self.begin(p,count=40);before=deepcopy((self.b.stages,self.c.stages))
  with patch.object(Engine,'d20',return_value=20):self.e.use_move_on(p,self.b,mid,[p,self.b,self.c],aim=self.b.pos,set_damage=True)
  for target,old in zip((self.b,self.c),before):
   lowered=[s for s in M.STATS if target.stages[s]==old[s]-1]
   self.assertEqual(len(lowered),2);self.assertEqual(sum(old[s]-target.stages[s] for s in M.STATS),2)
  receipts=[r for r in self.e._effect_dispatch_receipts.values() if r.get('source_id')==mid and 'glitch_random_stats' in r]
  self.assertEqual(len(receipts),2);self.assertTrue(all(len(set(r['glitch_random_stats']))==2 for r in receipts))
  self.restore();self.valid()

 def test_pain_swap_exchanges_plain_and_parameterized_afflictions_once_and_refuses_unowned_history(self):
  p,mid=self.learner('고통 교환')
  self.e.apply_status(self.b,'화상',source='gm/actual burn');self.e.apply_status(self.c,'마비',source='gm/actual paralysis')
  self.begin(self.c);self.native(self.c,self.a,'move/울음소리');self.e.apply_status(self.c,'사슬묶기',source='gm/actual disable',parameters={'move_id':'move/울음소리'},applied_by=self.a)
  self.turn(p,count=40)
  with patch.object(Engine,'d20',return_value=20):self.e.use_move_on(p,self.b,mid,[p,self.b,self.c],set_damage=True)  # 대상 2: no aim cell
  self.assertEqual(('마비' in self.b.conditions,'사슬묶기' in self.b.conditions,'화상' in self.b.conditions),(True,True,False))
  self.assertEqual(('화상' in self.c.conditions,'마비' in self.c.conditions,'사슬묶기' in self.c.conditions),(True,False,False))
  self.assertEqual([r['effect']['move_id'] for r in CONDITIONS.records(self.b,'사슬묶기')],['move/울음소리'])
  swaps=[r['pain_swap'] for r in self.e._effect_dispatch_receipts.values() if r.get('source_id')==mid and 'pain_swap' in r]
  self.assertEqual(len(swaps),1);self.assertTrue(swaps[0]['swapped'])
  self.restore();self.valid()
  # A Badly Poisoned recipient has a round history this source does not transfer: refused before cost.
  p,mid=self.learner('고통 교환')
  self.e.apply_status(self.c,'맹독',source='gm/actual toxic');self.begin(p,count=40);uses=deepcopy(p.move_uses)
  budget=deepcopy(p.budget)
  with self.assertRaisesRegex(ValueError,'Pain Swap|variant|GM'):self.e.use_move_on(p,self.c,mid,[p,self.c,self.b],set_damage=True)  # the primary recipient is inspected before any cost (the multi-target entry opens its completion row first)
  self.assertEqual((p.move_uses,p.budget),(uses,budget));self.valid()

 def test_pain_swap_needs_both_actual_hits_and_named_distinct_recipients(self):
  p,mid=self.learner('고통 교환');self.e.apply_status(self.b,'화상',source='gm/actual burn');self.begin(p,count=40)
  with self.assertRaisesRegex(ValueError,'distinct'):self.e.use_move_on(p,self.b,mid,[p,self.b,self.b],set_damage=True)  # refused at recipient selection, before the single daily use is spent
  self.assertNotIn(mid,p.move_uses)
  faces=iter([20,1])
  with patch.object(Engine,'d20',side_effect=lambda *a,**k:next(faces)):self.e.use_move_on(p,self.b,mid,[p,self.b,self.c],set_damage=True)
  self.assertIn('화상',self.b.conditions);self.assertNotIn('화상',self.c.conditions)
  swaps=[r['pain_swap'] for r in self.e._effect_dispatch_receipts.values() if r.get('source_id')==mid and 'pain_swap' in r]
  self.assertEqual([s['swapped'] for s in swaps],[False])
  self.restore();self.valid()

 def test_teleport_crash_moves_recipient_declared_direction_by_three_plus_d6(self):
  p,mid=self.learner('순간이동 충격');self.e.gm.set_position(p,(3,6),reason='adjacent actual user');self.e.gm.set_position(self.b,(4,6),reason='adjacent recipient')
  self.begin(p,count=40);uses=deepcopy(p.move_uses)
  self.reject(lambda:self.native(p,self.b,mid),reason='declared direction');self.assertEqual(p.move_uses,uses)
  M.declare_tele_crash(self.e,p,(1,0),reason='actual declared landing direction')
  with patch.object(POOLS,'die',return_value=4):self.native(p,self.b,mid)
  self.assertEqual(tuple(self.b.pos),(11,6));self.assertNotIn(M.TELE_DIRECTION,p.spec)
  receipt=next(r['tele_crash'] for r in self.e._effect_dispatch_receipts.values() if r.get('source_id')==mid and 'tele_crash' in r)
  self.assertEqual((receipt['roll'],receipt['distance'],receipt['to']),(4,7,[11,6]))
  self.restore();self.valid();p=self.people[-1]  # restore() rebinds actors
  # A blocked or off-map landing is not invented; the GM adjudicates.
  self.begin(self.b,count=35);self.turn(p,count=33);self.begin(self.b,count=32);self.turn(p,count=30)  # a Scene Move may not repeat on the user's consecutive turns: one idle own turn between
  M.declare_tele_crash(self.e,p,(1,0),reason='second declared direction')
  self.e.gm.set_position(self.b,(4,6),reason='back adjacent');self.e.gm.set_position(self.c,(11,6),reason='occupied landing cell')
  with patch.object(POOLS,'die',return_value=4):self.native(p,self.b,mid)
  self.assertEqual(tuple(self.b.pos),(4,6));self.assertEqual(tuple(self.c.pos),(11,6))
  row=[r for r in self.e._effect_dispatch_receipts.values() if r.get('source_id')==mid and 'tele_crash' in r][-1]
  self.assertFalse(row['tele_crash']['teleported']);self.assertIn('adjudicate',row['tele_crash']['reason']);self.assertNotEqual(row['status'],'completed');self.valid()

 def test_full_class_test30_obligation_is_reached_by_native_error_move_effects(self):
  for feature in B.TEACHING:
   for name in B.TEACHING[feature]:
    with self.subTest(move=name):
     p,mid=self.learner(name)
     if mid==M.TELE:M.declare_tele_crash(self.e,p,(1,0),reason='actual declared landing direction')
     self.begin(self.b);self.native(self.b,self.a,'move/울음소리');self.turn(p,count=40);before=set(self.e._effect_dispatch_receipts)
     with patch.object(Engine,'d20',return_value=20),patch.object(POOLS,'die',return_value=4):
      if name in ('방해 웨이브','블루 스크린','고통 교환'):self.e.use_move_on(p,self.b,mid,[p,self.b,self.c],aim=None if name=='고통 교환' else self.b.pos,set_damage=True)
      else:self.e.use_move(p,self.b,mid,set_damage=True)
     actual=[r for token,r in self.e._effect_dispatch_receipts.items() if token not in before and r['source_id']==mid]
     self.assertTrue(actual);self.assertTrue(all(r['status']=='completed' for r in actual));self.restore();self.valid()


if __name__=='__main__':unittest.main()
