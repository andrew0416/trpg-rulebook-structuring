"""Bounded safety tests; unconnected dynamic/optional slot policies remain open."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import items as I
import state_grants as G
import state_codec as C
import move_state as M
import pokemon_teaching as T
import downtime as D
from encounter import usable_moves

class MoveQuotaSafetyTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=536)
  self.a=self.add(build_trainer(self.r,'owner',20,dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),abilities=[]))
 def add(self,spec):
  c=Combatant(self.r,spec);self.e.gm.add_combatant(c,pos=(1,1),side='party',reason='actual current sheet observation');return c
 def pokemon(self,species='브케인',level=5,moves=None,**extra):
  return self.add(build_pokemon(self.r,species,level,moves=moves or [],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':5,**extra}))
 def state(self):return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),[(c.spec,c.moves,c.abilities) for c in self.e.everyone]))
 def mids(self):return [self.r.move_id(n) for n in ['몸통박치기','울음소리','덩굴채찍','씨뿌리기','잎날가르기','성장','수면가루','독가루']]
 def feature(self,uid):
  self.a.spec.setdefault('feats',[]).append(uid);I.register_feats(self.e,self.a)
 def key(self,uid):return 'feature:'+self.a.entity_id+':'+uid
 def observe(self,p,mid,method='feature',paid_tp=0,replace=None):
  return M.observe_learning(self.e,p,mid,method=method,source=T.MACHINES if method=='tm' else M.SOURCE if method in ('level_up','egg','n_tutor') else 'feat/기술-가르침',paid_tp=paid_tp,replace=replace,reason='observed completed acquisition and exact paid points')
 def test_builder_and_gm_seventh_move_reject_and_actual_six_are_read(self):
  mids=self.mids()
  with self.assertRaisesRegex(ValueError,'capacity'):build_pokemon(self.r,'이상해씨',50,moves=mids[:7],abilities=[])
  p=self.pokemon('이상해씨',50,mids[:6]);before=self.state()
  with self.assertRaisesRegex(ValueError,'capacity'):self.e.gm.set_move(p,mids[6],reason='observed conflicting seventh move')
  self.assertEqual(self.state(),before);self.assertEqual(set(usable_moves(self.e,p)),set(mids[:6]+['struggle']))
 def test_guidance_seventh_source_repeated_registration_storage_and_safe_end(self):
  mids=self.mids();p=self.pokemon('이상해씨',50,mids[:6]);self.feature(M.GUIDANCE);I.register_feats(self.e,self.a)
  self.e.gm.set_move(p,mids[6],reason='seventh known move with actual Guidance')
  self.assertEqual(M.describe(self.r,p.spec)['total'],7);self.assertEqual(len(usable_moves(self.e,p)),8)
  before=self.state()
  with self.assertRaises(ValueError):self.e.gm.set_move(p,mids[7],reason='conflicting eighth move')
  with self.assertRaises(ValueError):G.revoke(p,self.key(M.GUIDANCE),engine=self.e)
  self.assertEqual(self.state(),before)
  e=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)));q=next(c for c in e.everyone if c.entity_id==p.entity_id)
  self.assertEqual(M.describe(self.r,q.spec)['total'],7)
  e.gm.set_move(q,mids[6],add=False,reason='explicit chosen forgotten move');G.revoke(q,self.key(M.GUIDANCE),engine=e)
  self.assertEqual(M.describe(self.r,q.spec)['total'],6)
 def test_native_mentor_two_skills_level_allowance_and_n_tutor_remain_natural_after_restore(self):
  self.e=Engine(self.r,seed=536)
  self.a=self.add(build_trainer(self.r,'actual Mentor',20,dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),abilities=[],extra={'feats':[T.MENTOR],'skills':{'매력':3,'포켓몬학':3}}))
  p=self.pokemon('이상해씨',5);before=self.state()
  for invalid in (['매력','매력'],['육상','포켓몬학']):
   with self.assertRaises(ValueError):T.select_mentor_skills(self.e,self.a,invalid,reason='invalid Mentor selection')
   self.assertEqual(self.state(),before)
  T.select_mentor_skills(self.e,self.a,['매력','포켓몬학'],reason='two actual Novice Mentor skills')
  before=self.state()
  with self.assertRaises(ValueError):T.select_mentor_skills(self.e,self.a,['매력','협박'],reason='cannot replace acquired skills')
  self.assertEqual(self.state(),before)
  def teach(target,name):return T.teach_feature(self.e,self.a,target=target,move_id=self.r.move_id(name),feature=T.MENTOR,seconds=60,reason='actual Extended Mentor teaching')
  with self.assertRaisesRegex(ValueError,'level allowance'):teach(p,'수면가루')
  self.assertEqual(self.state(),before)
  with self.assertRaisesRegex(ValueError,'frequency'):teach(p,'씨뿌리기')
  self.assertEqual(self.state(),before)
  result=teach(p,'덩굴채찍');self.assertEqual((result['point_cost'],result['classification']),(1,'natural'))
  self.assertEqual(p.spec['tutor_points'],4);self.assertEqual(self.e.elapsed_seconds,60)
  record=p.spec['move_learning']['move/덩굴채찍']
  self.assertEqual((record['teacher_id'],record['mentor_skills'],record['mentor_skill_ranks']),(self.a.entity_id,['매력','포켓몬학'],[3,3]))
  before=self.state()
  with self.assertRaisesRegex(ValueError,'already learned'):teach(p,'덩굴채찍')
  self.assertEqual(self.state(),before)
  n=self.pokemon('리자몽',30);result=teach(n,'에어슬래시')
  self.assertEqual((result['point_cost'],result['classification']),(1,'natural'));self.assertEqual(n.spec['tutor_points'],4)
  for pupil in (p,n):self.assertEqual(M.describe(self.r,pupil.spec)['taught_count'],0)
  self.e.gm.snapshot('mentor');self.e.gm.set_move(p,'덩굴채찍',add=False,reason='observed forgetting');self.e.gm.restore('mentor')
  loaded=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)));actors={x.entity_id:x for x in loaded.everyone}
  self.assertEqual(actors[self.a.entity_id].spec['mentor_skills'],['매력','포켓몬학'])
  for pupil,mid in [(p,'move/덩굴채찍'),(n,'move/에어슬래시')]:
   q=actors[pupil.entity_id];self.assertIn(mid,usable_moves(loaded,q));self.assertEqual(q.spec['tutor_points'],4)
   self.assertEqual(M.describe(self.r,q.spec)['classifications'][mid],'natural')
   self.assertEqual(q.spec['move_learning'][mid]['teacher_id'],self.a.entity_id)
  self.assertTrue(loaded.validate_state()['valid'])
 def test_lifelong_combined_tm_tutor_paid_feature_four_and_natural_exemption(self):
  p=self.pokemon();names=['화염방사','열풍','10만볼트','냉동빔'];mids=[self.r.move_id(x) for x in names]
  for mid,method in zip(mids[:3],['tm','tutor','feature']):self.observe(p,mid,method,1)
  self.assertEqual(M.describe(self.r,p.spec)['taught_count'],3);before=self.state()
  with self.assertRaisesRegex(ValueError,'TM/Tutor'):self.observe(p,mids[3],'tutor',1)
  self.assertEqual(self.state(),before);self.feature(M.LIFELONG);self.observe(p,mids[3],'tutor',1)
  self.assertEqual(M.describe(self.r,p.spec)['taught_count'],4);before=self.state()
  with self.assertRaisesRegex(ValueError,'TM/Tutor'):G.revoke(p,self.key(M.LIFELONG),engine=self.e)
  self.assertEqual(self.state(),before)
  # A zero-point independent feature is not a Tutor Move; a natural move is not one either.
  self.observe(p,self.r.move_id('성장'),'feature',0,replace=mids[3]);G.revoke(p,self.key(M.LIFELONG),engine=self.e)
  self.observe(p,self.r.move_id('몸통박치기'),'level_up',0)
  state=M.describe(self.r,p.spec);self.assertEqual(state['taught_count'],3);self.assertEqual(state['classifications']['move/성장'],'granted')
  self.assertEqual(state['classifications']['move/몸통박치기'],'natural');self.assertEqual(len(state['counted']),5)
 def test_foiling_one_selected_grass_status_choice_and_invalid_changes_atomic(self):
  mids=self.mids();p=self.pokemon('이상해씨',50,mids[:6]);self.a.spec['feats']=[M.FOILING]
  M.select_foiling(self.e,self.a,p,'씨뿌리기',reason='observed completed Foiling Foliage')
  self.e.gm.set_move(p,mids[6],reason='known move with one selected exempt slot')
  M.select_foiling(self.e,self.a,p,'수면가루',reason='explicit different selected move')
  out=M.describe(self.r,p.spec);self.assertEqual(list(out['exempt']),['move/수면가루']);self.assertIn('move/씨뿌리기',out['counted']);self.assertEqual(len(out['counted']),6)
  before=self.state()
  for bad in ['몸통박치기','덩굴채찍','없는기술']:
   with self.subTest(bad=bad),self.assertRaises(ValueError):M.select_foiling(self.e,self.a,p,bad,reason='invalid selection observation')
  with self.assertRaises(ValueError):G.revoke(p,self.key(M.FOILING),engine=self.e)
  self.assertEqual(self.state(),before)
 def test_feature_multi_target_preflight_leaves_earlier_target_untouched(self):
  p=self.pokemon();q=self.pokemon();q.spec['trainer_id']='someone-else';self.a.spec['feats']=[M.GUIDANCE];before=self.state()
  with self.assertRaises(ValueError):I.register_feats(self.e,self.a,[p,q])
  self.assertEqual(self.state(),before)
 def test_actual_machine_preserves_independent_grant_and_revoke_preserves_new_baseline(self):
  p=self.pokemon();G.grant(p,'moves','move/울음소리','temporary:observed','fixture');self.a.spec.setdefault('items',{})['TM35']=1
  T.register_machine(self.e,self.a,instance_id='real-tm',code='TM35')
  out=T.teach_machine(self.e,self.a,target=p,instance_id='real-tm')
  self.assertEqual((out['point_cost'],self.e.elapsed_seconds,p.spec['tutor_points']),(1,3600,4))
  self.assertIn('move/울음소리',p.moves);self.assertNotIn('move/울음소리',p.spec['moves']);G.revoke(p,'temporary:observed',engine=self.e)
  self.assertNotIn('move/울음소리',p.moves);self.assertIn('move/화염방사',usable_moves(self.e,p))
 def test_growth_over_capacity_preserves_spec_exp_log_then_explicit_forget_allows_retry(self):
  mids=self.mids();p=self.pokemon('브케인',39,mids[:6]);before=self.state();log=[]
  with self.assertRaisesRegex(ValueError,'capacity'):D.gain_exp(self.r,p.spec,D.exp_for_level(self.r,40)-D.exp_for_level(self.r,39),log)
  self.assertEqual(log,[]);self.assertEqual(self.state(),before)
  self.e.gm.set_move(p,mids[5],add=False,reason='explicit choice before retrying growth');D.gain_exp_combatant(self.e,p,'to next level')
  self.assertEqual(p.level,40);self.assertIn('move/화염방사',p.moves);self.assertTrue(set(mids[:5]).issubset(p.moves));self.assertEqual(len(M.known(self.r,p.spec)),6)
 def test_tm_and_tutor_remain_taught_until_actual_natural_opportunity_then_survive_evolution(self):
  for method in ('tm','tutor'):
   with self.subTest(method=method):
    p=self.pokemon('브케인',39);self.observe(p,'화염방사',method,1)
    self.assertEqual(M.describe(self.r,p.spec)['classifications']['move/화염방사'],'taught')
    D.gain_exp_combatant(self.e,p,'to next level')
    self.assertEqual(M.describe(self.r,p.spec)['classifications']['move/화염방사'],'natural')
    before=deepcopy(p.spec[M.HISTORY]['move/화염방사']);self.assertTrue(D.evolve(self.r,p.spec,'마그케인'))
    self.assertNotIn('move/화염방사',M.current_natural_evidence(self.r,p.spec))
    self.assertEqual(M.describe(self.r,p.spec)['classifications']['move/화염방사'],'natural')
    self.assertEqual(p.spec[M.HISTORY]['move/화염방사'],before)
    self.assertEqual(p.spec['move_learning']['move/화염방사']['method'],method)
 def test_source_owned_and_observed_legacy_learning_keep_natural_history_but_overlay_only_does_not(self):
  for authority in ('paid_source','legacy_route','overlay_only','hidden_baseline','free_source_old_record','legacy_unknown'):
   with self.subTest(authority=authority):
    p=self.pokemon('브케인',39)
    if authority=='paid_source':G.grant(p,'moves','move/화염방사','feature:observed-teaching','feature',tutor_points=2,rule_id='feat/기술-가르침')
    elif authority=='legacy_route':
     G.state(p)['legacy']['moves']=['move/화염방사'];G.materialize(p,'moves')
     p.spec['move_learning']={'move/화염방사':{'method':'tutor','source':'feat/기술-가르침','paid_tp':1}}
    elif authority=='hidden_baseline':
     self.observe(p,'화염방사','tm',1);G.overlay(p,'temporary:transform',moves=['move/몸통박치기','struggle'])
    elif authority=='free_source_old_record':
     G.grant(p,'moves','move/화염방사','feature:independent-free-grant','feature',tutor_points=0)
     p.spec['move_learning']={'move/화염방사':{'method':'tutor','source':'feat/기술-가르침','paid_tp':1}}
    elif authority=='legacy_unknown':
     G.state(p)['legacy']['moves']=['move/화염방사'];G.materialize(p,'moves')
    else:G.overlay(p,'temporary:transform',moves=['move/화염방사','struggle'])
    before=M.describe(self.r,p.spec)
    if authority in ('paid_source','legacy_route'):
     self.assertEqual((before['classifications']['move/화염방사'],before['taught_count']),('taught',1))
     self.assertEqual(T.classifications(self.r,p.spec)['move/화염방사'],'taught')
    elif authority=='hidden_baseline':self.assertEqual(M.classifications(self.r,p.spec)['move/화염방사'],'taught')
    elif authority=='overlay_only':
     self.assertNotIn('move/화염방사',before['classifications'])
     self.assertEqual(before['effective_classifications']['move/화염방사'],'permission')
     self.assertEqual(before['taught_count'],0)
    else:
     self.assertEqual(before['classifications']['move/화염방사'],'granted' if authority=='free_source_old_record' else 'unknown')
     self.assertEqual(before['taught_count'],0)
    self.e.gm.set_level(p,40,reason='actual level opportunity while each ownership form exists')
    self.e.gm.set_level(p,39,reason='subsequent observed level decrease')
    events=p.spec.get(M.HISTORY,{}).get('move/화염방사',[])
    if authority in ('overlay_only','free_source_old_record','legacy_unknown'):self.assertEqual(events,[])
    else:
     self.assertEqual(len(events),1);self.assertTrue(events[0]['observation_provenance'])
     if authority!='hidden_baseline':self.assertEqual(M.describe(self.r,p.spec)['classifications']['move/화염방사'],'natural')
  e=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)))
  for p in e.everyone[1:]:M.validate_actor(p)
 def test_import_unknown_route_is_visible_and_blocks_native_teaching_without_cost(self):
  p=self.pokemon(moves=['move/냉동빔']);self.assertEqual(M.describe(self.r,p.spec)['unknown_routes'],['move/냉동빔'])
  self.a.spec.setdefault('items',{})['TM35']=1;T.register_machine(self.e,self.a,instance_id='m',code='TM35');before=self.state()
  with self.assertRaisesRegex(ValueError,'provenance'):T.teach_machine(self.e,self.a,target=p,instance_id='m')
  self.assertEqual(self.state(),before)

if __name__=='__main__':unittest.main()
