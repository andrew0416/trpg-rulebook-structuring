"""Source extraction corrections must reach actual effective state and revoke cleanly."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
import items,state_grants as G
from copy import deepcopy
import json
import state_codec as C
from encounter import usable_moves
READY_STATIC_GRANTS=[["FAN-118","feat/거미줄-쏘는-법",{"capabilities":["실날리기","벽타기"]}],["FAN-149","feat/불의-영혼",{"capabilities":["불쏘시개"],"status_immune":["화상"]}],["FAN-172","feat/대지-결합",{"capabilities":["진동감지","자연걸음 (동굴)","자연걸음 (산)","자연걸음 (사막)"]}],["FAN-187","feat/투명한-미라지",{"capabilities":["환영술사"]}],["FAN-194","feat/불쾌함의-부름",{"moves":["move/녹기","move/오물폭탄"]}],["FAN-208","feat/무기의-마스터",{"capabilities":["무기 부름","무한의 강제"]}]]
CASES={
 'feat/철벽':['철벽','방어'],
 'feat/선명한-그림자':['악의파동','깜짝베기'],
 'feat/심연의-심장':['나이트버스트','혼내기'],
 'feat/정열적인-하모니':['매지컬샤인','드레인키스'],
 'feat/럭키-클로버-그랜드-피날레':['문포스','아로마미스트'],
 'feat/반짝임':['트라이어택','웨더볼'],
 'feat/레인보우-서지':['파괴광선','아침햇살'],
 'feat/불쾌함-촉발':['오물웨이브','맹독'],
}
class OptionalGrantTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='fantasy')
 def test_every_sourced_move_is_effective_and_removal_preserves_independent_baseline(self):
  for uid,names in CASES.items():
   with self.subTest(source=uid):
    expected=[self.r.move_id(name) for name in names];self.assertTrue(all(expected))
    c=Combatant(self.r,dict(id='trainer',name='trainer',kind='trainer',level=30,stats=dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),moves=[expected[0]],feats=[uid],pos=(1,1)))
    c.spec['static_feature_choices']={uid:'atk'} if uid in ('feat/선명한-그림자','feat/심연의-심장') else {}
    e=Engine(self.r,17);e.everyone=e.gm.everyone=[c];items.register_feats(e,c)
    self.assertEqual(set(c.moves),set(expected));source='feature:trainer:'+uid
    self.assertEqual(set(c.spec[G.KEY]['sources'][source]['grants']['moves']),set(expected))
    c.spec['feats']=[];items.register_feats(e,c)
    G.revoke(c,source,engine=e);self.assertEqual(c.moves,[expected[0]])
 def test_native_fantasy_capability_and_immunity_consumers_follow_source_removal(self):
  from grid import Grid
  import movement_actions as MOVE
  for uid,terrain,capability in [('feat/녹빛-도로','초원','자연걸음 (초원)'),('feat/추위따위-아무것도-아니었으니','툰드라','자연걸음 (툰드라)')]:
   with self.subTest(source=uid):
    c=Combatant(self.r,dict(id='trainer',name='trainer',kind='trainer',level=30,stats=dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),feats=[uid],pos=(0,0)))
    e=Engine(self.r,17);e.everyone=e.gm.everyone=[c];e.grid=Grid(4,2);e.grid.slow={(1,0)}
    c.spec['static_feature_choices']={uid:'atk'} if uid=='feat/추위따위-아무것도-아니었으니' else {}
    import body_state as BODY
    BODY.observe(e,c,[(0,0)],reason='actual one-cell body for terrain consumer')
    MOVE.observe_cell_terrain(e,[(1,0)],[terrain],'actual source terrain');items.register_feats(e,c)
    self.assertIn(capability,G.effective_capabilities(c));self.assertEqual(MOVE.slow_terrain_penalty(e,c,(1,0),'육상'),0)
    if uid=='feat/녹빛-도로':
     self.assertIn('가루',c.keyword_immune)
     powder=self.r.move('move/독가루');self.assertFalse(e.accuracy_check(c,c,powder,fixed_roll=20)[0])
    else:
     import turn
     self.assertIn('얼음',c.status_immune);self.assertIn('싸라기눈',c.weather_immune)
     e.apply_status(c,'얼음');self.assertNotIn('얼음',c.conditions)
     e.weather='hail';hp=c.hp;turn.weather_turn_start(e,c);self.assertEqual(c.hp,hp)
    c.spec['feats']=[];items.register_feats(e,c)
    G.revoke(c,'feature:trainer:'+uid,engine=e)
    self.assertNotIn(capability,G.effective_capabilities(c));self.assertEqual(MOVE.slow_terrain_penalty(e,c,(1,0),'육상'),1)
    if uid=='feat/녹빛-도로':
     self.assertNotIn('가루',c.keyword_immune);self.assertTrue(e.accuracy_check(c,c,powder,fixed_roll=20)[0])
    else:
     self.assertNotIn('얼음',c.status_immune);self.assertNotIn('싸라기눈',c.weather_immune)
     e.apply_status(c,'얼음');self.assertIn('얼음',c.conditions)
     hp=c.hp;turn.weather_turn_start(e,c);self.assertLess(c.hp,hp)
 def static_fixture(self,uid):
  c=Combatant(self.r,dict(id='optional-static',name='optional-static',kind='trainer',level=30,stats=dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),abilities=[],moves=[],feats=[uid],pos=(0,0)))
  c.spec['static_feature_choices']={uid:'atk'} if uid=='feat/불의-영혼' else {}
  e=Engine(self.r,17);e.everyone=e.gm.everyone=[c];return e,c
 def static_available(self,e,c,field):
  if field=='capabilities':return G.effective_capabilities(c)
  if field=='moves':return usable_moves(e,c)
  return list(getattr(c,field,()))
 def assert_static_native_consumer(self,e,c,uid,enabled):
  if uid=='feat/불의-영혼':
   e.apply_status(c,'화상');self.assertEqual('화상' in c.conditions,not enabled)
  if uid=='feat/대지-결합':
   from grid import Grid
   import movement_actions as MOVE
   if e.grid is None:e.grid=Grid(4,2)
   import body_state as BODY
   BODY.observe(e,c,[(0,0)],reason='actual one-cell body for terrain consumer')
   e.grid.slow={(1,0)}
   for terrain in ['동굴','산','사막']:
    MOVE.observe_cell_terrain(e,[(1,0)],[terrain],'actual named terrain for Earthen Bond')
    self.assertEqual(MOVE.slow_terrain_penalty(e,c,(1,0),'육상'),0 if enabled else 1)
 def test_static_ready_sources_native_consumers_scene_restore_and_final_withdrawal(self):
  for cid,uid,fields in READY_STATIC_GRANTS:
   with self.subTest(clause=cid):
    e,c=self.static_fixture(uid);items.register_feats(e,c);source='feature:'+c.entity_id+':'+uid
    row=c.spec[G.KEY]['sources'][source];self.assertEqual((row['owner_id'],row['rule_id']),(c.entity_id,uid))
    for field,values in fields.items():
     self.assertTrue(set(values)<=set(self.static_available(e,c,field)))
     if field in ('moves','capabilities'):self.assertCountEqual(row['grants'][field],values)
    self.assertFalse(any(str(x).startswith('당신은') for x in G.effective_capabilities(c)))
    before=deepcopy(c.spec[G.KEY]);items.register_feats(e,c);self.assertEqual(c.spec[G.KEY],before)
    self.assert_static_native_consumer(e,c,uid,True);e.end_encounter();e.gm.snapshot('static-ready')
    c.spec['feats']=[];items.register_feats(e,c)
    G.revoke(c,source,engine=e);e.gm.restore('static-ready')
    loaded=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(e),ensure_ascii=False)));q=loaded.everyone[0]
    self.assertEqual(q.entity_id,c.entity_id);self.assertEqual(q.spec[G.KEY],c.spec[G.KEY])
    for field,values in fields.items():self.assertTrue(set(values)<=set(self.static_available(loaded,q,field)))
    self.assert_static_native_consumer(loaded,q,uid,True)
    q.spec['feats']=[];items.register_feats(loaded,q);G.revoke(q,source,engine=loaded)
    for field,values in fields.items():self.assertFalse(set(values)&set(self.static_available(loaded,q,field)))
    self.assert_static_native_consumer(loaded,q,uid,False);self.assertTrue(loaded.validate_state()['valid'])
 def test_static_ready_independent_baseline_and_actual_acquisition(self):
  for cid,uid,fields in READY_STATIC_GRANTS:
   with self.subTest(clause=cid):
    e,c=self.static_fixture(uid)
    for field,values in fields.items():
     if field in ('moves','capabilities'):G.set_baseline(c,field,values)
    items.register_feats(e,c);c.spec['feats']=[];items.register_feats(e,c);G.revoke(c,'feature:'+c.entity_id+':'+uid,engine=e)
    for field,values in fields.items():
     if field in ('moves','capabilities'):
      for value in values:self.assertEqual(self.static_available(e,c,field).count(value),1)
    self.assertTrue(e.validate_state()['valid']);e,c=self.static_fixture(uid);c.spec['feats']=[];items.register_feats(e,c)
    for field,values in fields.items():self.assertFalse(set(values)&set(self.static_available(e,c,field)))
    self.assertFalse(c.spec.get(G.KEY,{}).get('sources',{}))
if __name__=='__main__':unittest.main()
