"""Optional fixed/ranked move grants through the common native source ledger."""
import json,unittest
from copy import deepcopy
from test_category2_class_move_grants import ROOT, Rules, Combatant, C, G, ITEMS, encounter, CODEC
import test_category2_class_move_grants as _fixture_test_category2_class_move_grants
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='all')
 setUp=_fixture_test_category2_class_move_grants.ClassMoveTests.setUp
 source=_fixture_test_category2_class_move_grants.ClassMoveTests.source
 register=_fixture_test_category2_class_move_grants.ClassMoveTests.register
 load=_fixture_test_category2_class_move_grants.ClassMoveTests.load
 expect=_fixture_test_category2_class_move_grants.ClassMoveTests.expect
 def own(self,uid):
  self.c.spec['feats']=[uid]+(['feat/불쾌한-몸'] if uid=='feat/불쾌함의-부름' else [])
  if uid=='feat/겨울의-예고':self.c.spec.update(feat_ranks={uid:1},feature_choices={uid:[['냉동빔','냉동펀치']]})
 def test_fixed_pairs_share_native_registration_persistence_and_independent_sources(self):
  for uid,names in [('feat/바위-파편',['스톤샤워','스텔스록'])]:
   with self.subTest(uid=uid):
    self.setUp();self.own(uid);self.register();self.register();ids=self.expect(self.c,names)
    self.assertTrue(set(ids)<=set(encounter.usable_moves(self.e,self.c)))
    self.e.gm.snapshot('moves');e,c=self.load()
    G.set_baseline(c,'moves',[ids[0]]);G.grant(c,'moves',ids[1],'independent/move','gm')
    c.spec['feats']=[];ITEMS.register_feats(e,c);self.expect(c,names)
    G.revoke(c,'independent/move',engine=e);self.assertNotIn(ids[1],c.moves);self.assertIn(ids[0],c.moves)
    self.c.spec['feats']=[];self.register();self.assertFalse(set(ids)&set(self.c.moves))
    self.e.gm.restore('moves',reason='restore acquired move sources');self.expect(self.c,names)
 def test_winter_full_table_rank_history_downgrade_and_retained_baseline(self):
  uid='feat/겨울의-예고';self.own(uid)
  rank1=['프리즈드라이','냉동펀치','냉동빔','고드름떨구기'];rank2=['눈사태','눈보라','얼음숨결','고드름침']
  for name in rank1:
   other=next(x for x in rank1 if x!=name);self.c.spec['feature_choices'][uid]=[[name,other]]
   self.assertIn(self.rules.move_id(name),C.plan(self.e,self.c,uid)['moves'])
  self.c.spec['feat_ranks'][uid]=2
  for name in rank2:
   other=next(x for x in rank2 if x!=name);self.c.spec['feature_choices'][uid]=[rank1[:2],[name,other]]
   self.assertIn(self.rules.move_id(name),C.plan(self.e,self.c,uid)['moves'])
  self.c.spec['feature_choices'][uid]=[rank1[:2],rank2[:2]];self.register();self.expect(self.c,rank1[:2]+rank2[:2])
  e,c=self.load();G.set_baseline(c,'moves',[self.rules.move_id(rank2[0])])
  c.spec['feat_ranks'][uid]=1;c.spec['feature_choices'][uid]=[rank1[:2]];ITEMS.register_feats(e,c)
  self.expect(c,rank1[:2]+[rank2[0]]);self.assertNotIn(self.rules.move_id(rank2[1]),c.moves)
  self.assertTrue(set(self.rules.move_id(n) for n in rank1[:2])<=set(encounter.usable_moves(e,c)))
 def test_exact_or_prerequisites_and_parent_are_required_before_grants(self):
  for uid,skills in [('feat/겨울의-예고',('육상','생존')),('feat/바위-파편',('전투','생존'))]:
   self.setUp();self.own(uid)
   for chosen in skills:
    self.c.spec['skills'].update({s:4 for s in skills});self.c.spec['skills'][chosen]=5
    C.plan(self.e,self.c,uid)
   self.c.spec['skills'].update({s:4 for s in skills});before=deepcopy(self.c.spec)
   with self.assertRaises(ValueError):self.register()
   self.assertEqual(self.c.spec,before)
 def test_winter_rejects_advanced_duplicate_reselection_and_insufficient_rank(self):
  uid='feat/겨울의-예고';self.own(uid)
  for choice in ([['눈보라','냉동빔']],[['냉동빔','냉동빔']],[],[['냉동빔']]):
   self.c.spec['feature_choices'][uid]=choice;before=deepcopy(self.c.spec)
   with self.assertRaises(ValueError):self.register()
   self.assertEqual(self.c.spec,before)
  self.c.spec['feature_choices'][uid]=[['냉동빔','냉동펀치']];self.register()
  self.c.spec['feature_choices'][uid]=[['冷凍ビーム','냉동펀치']]
  with self.assertRaises(ValueError):self.register()
  self.c.spec.update(feat_ranks={uid:2},feature_choices={uid:[['냉동빔','냉동펀치'],['눈보라','눈사태']]})
  self.c.spec['skills'].update(육상=5,생존=5)
  with self.assertRaises(ValueError):self.register()
 def test_actual_move_execution_consumes_the_learned_grant(self):
  for uid,move in [('feat/바위-파편','스톤샤워'),('feat/겨울의-예고','냉동빔')]:
   with self.subTest(uid=uid):
    self.setUp();self.own(uid);self.register()
    target=Combatant(self.rules,dict(name='target',kind='trainer',level=30,stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[]))
    self.e.everyone.append(target);self.e.rng.seed(5)
    self.e.start_of_turn(self.c);before=target.hp
    self.e.use_move(self.c,self.c if move=='녹기' else target,self.rules.move_id(move))
    if move=='녹기':self.assertEqual(self.c.stages['def'],2)
    else:self.assertLess(target.hp,before)
    self.e.end_of_turn(self.c)
