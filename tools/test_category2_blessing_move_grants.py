"""Complete acquired static gift Move state, with native availability and provenance."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import items,state_grants as G
from encounter import usable_moves
from state_codec import dump_engine,load_engine
import ability_transitions as ABILITY
READY_NAMED_GRANTS=[
 ["C2ADD/supp-blessings:638","feat/메이저-기프트-새싹돋움","capabilities","새싹돋움"],
 ["C2ADD/supp-blessings:757","feat/메이저-기프트-새싹돋움-1","capabilities","새싹돋움"],
 ["C2ADD/supp-blessings:940","feat/가이오가의-메이저-기프트-웨이브크래셔","capabilities","물줄기"],
 ["C2ADD/supp-blessings:966","feat/레쿠쟈의-메이저-기프트-공기-적응","capabilities","세찬바람"],
 ["C2ADD/supp-blessings:1096","feat/메이저-기프트-진동감지","capabilities","진동감지"],
 ["C2ADD/supp-blessings:1375","feat/메이저-기프트-부정형","capabilities","부정형"],
 ["C2ADD/supp-blessings:1380","feat/메이저-기프트-페이징","capabilities","페이징"],
 ["C2ADD/supp-blessings:1385","feat/메이저-기프트-정신봉인","capabilities","정신봉인"],
 ["C2ADD/supp-blessings:1198","feat/레시라무의-약속된-기프트-푸른불꽃","moves","move/푸른불꽃"],
 ["C2ADD/supp-polygon:1871","feat/버그-타락자","abilities","싱크로"],
]
CASES=[
 ('feat/메이저-기프트-파멸의소원','파멸의소원',671),
 ('feat/라티아스의-메이저-기프트-미스트볼','미스트볼',688),
 ('feat/라티오스의-메이저-기프트-러스터퍼지','러스터퍼지',693),
 ('feat/마나피의-메이저-기프트-하트스왑','하트스왑',741),
 ('feat/메이저-기프트-시드플레어','시드플레어',762),
 ('feat/메이저-기프트-성스러운칼','성스러운칼',773),
 ('feat/메이저-기프트-옛노래','옛노래',812),
 ('feat/메이저-기프트-다이아스톰','다이아스톰',828),
 ('feat/칠색조의-약속된-기프트-성스러운불꽃','성스러운불꽃',886),
 ('feat/루기아의-약속된-기프트-에어로블라스트','에어로블라스트',897),
 ('feat/그란돈의-약속된-기프트-분화','분화',925),
 ('feat/가이오가의-약속된-기프트-해수스파우팅','해수스파우팅',951),
 ('feat/레쿠쟈의-마이너-기프트-맑은-하늘','안개제거',956),
 ('feat/레쿠쟈의-약속된-기프트-파괴광선','파괴광선',977),
 ('feat/디아루가의-약속된-기프트-시간의-포효','시간의포효',1005),
 ('feat/펄기아의-약속된-기프트-공간절단','공간절단',1026),
 ('feat/기타리나의-약속된-기프트-섀도다이브','섀도다이브',1047),
 ('feat/크레세리아의-약속된-기프트-초승달춤','초승달춤',1075),
 ('feat/다크라이의-약속된-기프트-다크홀','다크홀',1085),
 ('feat/약속된-기프트-마그마스톰','마그마스톰',1112),
 ('feat/약속된-기프트-묵사발','묵사발',1142),
 ('feat/약속된-기프트-v제너레이트','V제너레이트',1169),
 ('feat/제크로무의-약속된-기프트-뇌격','뇌격',1219),
 ('feat/큐레무의-약속된-기프트-얼어붙은세계','얼어붙은세계',1240),
 ('feat/큐레무의-약속된-기프트-프리즈볼트','프리즈볼트',1245),
 ('feat/큐레무의-약속된-기프트-콜드플레어','콜드플레어',1250),
 ('feat/제나르에스-약속된-기프트-지오컨트롤','지오컨트롤',1279),
 ('feat/이벨타르의-약속된-기프트-데스윙','데스윙',1300),
 ('feat/약속된-기프트-그라운드포스','그라운드포스',1328),
]
class GiftMoveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='all')
 def fixture(self,uid,baseline=None):
  r=self.rules;e=Engine(r,37)
  c=Combatant(r,dict(id='gift-holder',name='gift-holder',kind='trainer',level=30,stats=dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),feats=[uid],abilities=[],moves=[] if baseline is None else [baseline],pos=(0,0)))
  e.everyone=e.gm.everyone=[c]
  return e,c
 def test_each_exact_source_native_availability_codec_and_last_source_removal(self):
  for uid,name,line in CASES:
   with self.subTest(source=uid):
    mid=self.rules.move_id(name);self.assertIsNotNone(mid)
    e,c=self.fixture(uid);self.assertNotIn(mid,usable_moves(e,c));self.assertEqual(items.register_feats(e,c),1)
    source='feature:'+c.entity_id+':'+uid
    self.assertEqual(c.moves,[mid]);self.assertEqual(c.spec[G.KEY]['sources'][source]['grants']['moves'],[mid]);self.assertEqual(c.spec[G.KEY]['sources'][source]['rule_id'],uid)
    self.assertIn(self.rules.resolve_move(mid),usable_moves(e,c))
    before=deepcopy(c.spec[G.KEY]);items.register_feats(e,c);self.assertEqual(c.spec[G.KEY],before)
    e.end_encounter();self.assertIn(mid,c.moves)
    n=load_engine(self.rules,json.loads(json.dumps(dump_engine(e),ensure_ascii=False)));a=n.everyone[0]
    self.assertIs(a,n.gm.everyone[0]);self.assertEqual(a.moves,[mid]);self.assertEqual(a.spec[G.KEY],c.spec[G.KEY]);self.assertIn(self.rules.resolve_move(mid),usable_moves(n,a))
    G.revoke(a,source,engine=n);self.assertNotIn(mid,a.moves);self.assertNotIn(self.rules.resolve_move(mid),usable_moves(n,a))
 def test_each_baseline_and_snapshot_preserve_independent_move_ownership(self):
  for uid,name,line in CASES:
   with self.subTest(source=uid):
    mid=self.rules.move_id(name);e,c=self.fixture(uid,mid);items.register_feats(e,c);source='feature:'+c.entity_id+':'+uid
    e.gm.snapshot('gift');G.revoke(c,source,engine=e);self.assertEqual(c.moves,[mid]);self.assertIn(self.rules.resolve_move(mid),usable_moves(e,c))
    e.gm.restore('gift',reason='restore actual acquired gift')
    self.assertIn(source,c.spec[G.KEY]['sources']);self.assertEqual(c.moves,[mid])
    G.revoke(c,source,engine=e);self.assertEqual(c.moves,[mid]);self.assertNotIn(source,c.spec[G.KEY]['sources'])
 def test_each_absent_gift_cannot_produce_its_move(self):
  for uid,name,line in CASES:
   with self.subTest(source=uid):
    mid=self.rules.move_id(name);e,c=self.fixture(uid);c.spec['feats']=[];self.assertEqual(items.register_feats(e,c),0)
    self.assertNotIn(mid,c.moves);self.assertNotIn(self.rules.resolve_move(mid),usable_moves(e,c));self.assertNotIn('feature:'+c.entity_id+':'+uid,c.spec.get(G.KEY,{}).get('sources',{}))
 def test_psystrike_gift_native_availability_restore_and_final_source_removal(self):
  uid='feat/약속된-기프트-사이코브레이크';mid='move/사이코브레이크'
  effects,header=self.rules.feat_effects(uid)
  self.assertEqual(header['id'],uid);self.assertEqual(header['prereq'],'두개의 영혼, 범위 확대, 정신 제안')
  self.assertEqual(self.rules.move_id('사이코브레이크'),mid)
  e,c=self.fixture(uid);source='feature:'+c.entity_id+':'+uid
  self.assertNotIn(mid,usable_moves(e,c));self.assertEqual(items.register_feats(e,c),1)
  row=c.spec[G.KEY]['sources'][source]
  self.assertEqual(row['grants']['moves'],[mid]);self.assertEqual(row['rule_id'],uid)
  self.assertEqual(row['owner_id'],c.entity_id);self.assertEqual(c.moves,[mid])
  self.assertIn(self.rules.resolve_move(mid),usable_moves(e,c))
  state=deepcopy(c.spec[G.KEY]);items.register_feats(e,c);self.assertEqual(c.spec[G.KEY],state)
  e.end_encounter();self.assertIn(mid,c.moves);self.assertEqual(c.move_uses,{})
  e.gm.snapshot('psystrike-gift');G.revoke(c,source,engine=e)
  self.assertNotIn(mid,c.moves);self.assertNotIn(self.rules.resolve_move(mid),usable_moves(e,c))
  e.gm.restore('psystrike-gift');self.assertIs(c,e.everyone[0]);self.assertIn(mid,c.moves)
  loaded=load_engine(self.rules,json.loads(json.dumps(dump_engine(e),ensure_ascii=False)))
  actual=loaded.everyone[0];self.assertIs(actual,loaded.gm.everyone[0]);self.assertEqual(actual.entity_id,c.entity_id)
  self.assertEqual(actual.spec[G.KEY],c.spec[G.KEY]);self.assertIn(self.rules.resolve_move(mid),usable_moves(loaded,actual))
  G.revoke(actual,source,engine=loaded);self.assertNotIn(mid,actual.moves)
  self.assertNotIn(self.rules.resolve_move(mid),usable_moves(loaded,actual));self.assertTrue(loaded.validate_state()['valid'])
 def test_psystrike_gift_preserves_independent_move_and_requires_owned_feature(self):
  uid='feat/약속된-기프트-사이코브레이크';mid='move/사이코브레이크'
  e,c=self.fixture(uid,mid);source='feature:'+c.entity_id+':'+uid
  self.assertEqual(items.register_feats(e,c),1);self.assertEqual(c.moves.count(mid),1)
  G.revoke(c,source,engine=e);self.assertEqual(c.moves,[mid]);self.assertIn(self.rules.resolve_move(mid),usable_moves(e,c))
  e,c=self.fixture(uid);c.spec['feats']=[]
  self.assertEqual(items.register_feats(e,c),0);self.assertNotIn(mid,c.moves)
  self.assertNotIn(self.rules.resolve_move(mid),usable_moves(e,c))
 def named_available(self,e,c,field):
  if field=='moves':return usable_moves(e,c)
  if field=='abilities':return ABILITY.known(c)
  return G.effective_capabilities(c)
 def named_value(self,field,value):
  if field=='moves':return self.rules.resolve_move(value)
  if field=='abilities':return ABILITY.ability_id(self.rules,value)
  return value
 def test_ready_named_grants_use_native_consumers_restore_and_final_withdrawal(self):
  for cid,uid,field,value in READY_NAMED_GRANTS:
   with self.subTest(clause=cid):
    e,c=self.fixture(uid);expected=self.named_value(field,value);source='feature:'+c.entity_id+':'+uid
    self.assertNotIn(expected,self.named_available(e,c,field));self.assertEqual(items.register_feats(e,c),1)
    self.assertIn(expected,self.named_available(e,c,field));row=c.spec[G.KEY]['sources'][source]
    self.assertEqual(row['grants'][field],[value]);self.assertEqual(row['rule_id'],uid);self.assertEqual(row['owner_id'],c.entity_id)
    state=deepcopy(c.spec[G.KEY]);items.register_feats(e,c);self.assertEqual(c.spec[G.KEY],state)
    self.assertFalse(any(str(x).startswith('당신은') for x in G.effective_capabilities(c)))
    e.end_encounter();self.assertIn(expected,self.named_available(e,c,field));e.gm.snapshot('named-grant')
    G.revoke(c,source,engine=e);self.assertNotIn(expected,self.named_available(e,c,field));e.gm.restore('named-grant')
    loaded=load_engine(self.rules,json.loads(json.dumps(dump_engine(e),ensure_ascii=False)));actual=loaded.everyone[0]
    self.assertIs(actual,loaded.gm.everyone[0]);self.assertEqual(actual.entity_id,c.entity_id)
    self.assertEqual(actual.spec[G.KEY],c.spec[G.KEY]);self.assertIn(expected,self.named_available(loaded,actual,field))
    G.revoke(actual,source,engine=loaded);self.assertNotIn(expected,self.named_available(loaded,actual,field));self.assertTrue(loaded.validate_state()['valid'])
 def test_ready_named_grants_preserve_independent_baselines_and_require_actual_gift(self):
  for cid,uid,field,value in READY_NAMED_GRANTS:
   with self.subTest(clause=cid):
    expected=self.named_value(field,value);e,c=self.fixture(uid);G.set_baseline(c,field,[value]);items.register_feats(e,c)
    self.assertEqual(self.named_available(e,c,field).count(expected),1)
    G.revoke(c,'feature:'+c.entity_id+':'+uid,engine=e);self.assertIn(expected,self.named_available(e,c,field));self.assertTrue(e.validate_state()['valid'])
    e,c=self.fixture(uid);c.spec['feats']=[];self.assertEqual(items.register_feats(e,c),0)
    self.assertNotIn(expected,self.named_available(e,c,field));self.assertFalse(c.spec.get(G.KEY,{}).get('sources',{}))
if __name__=='__main__':unittest.main()
