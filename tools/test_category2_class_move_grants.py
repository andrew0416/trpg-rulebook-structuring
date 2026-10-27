"""Independent printed class-move selections through native registration and state persistence."""
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path
import json, sys, unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules, Engine, Combatant
from builder import build_trainer
import class_move_grants as C
import state_grants as G
import state_codec as CODEC
import items as ITEMS
import encounter
import ability_transitions as ABILITY
import trainer_feature_acquisition as FEATURE_ACQUISITION

class ClassMoveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.rules,seed=74)
  spec=build_trainer(self.rules,'acquired-class-owner',30,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[])
  spec.update(skills={'곡예':6,'육상':6,'전투':6,'은신':6,'오컬트학':6,'직감':6,'집중':6,'매력':6,'교활':6,'협박':6},classes=[],feats=[],edges=[],feature_choices={})
  self.c=Combatant(self.rules,spec);self.e.everyone=self.e.gm.everyone=[self.c]
 def source(self,uid):return 'feature:'+self.c.entity_id+':'+uid
 def register(self):return ITEMS.register_feats(self.e,self.c)
 def load(self):
  e=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  return e,e.everyone[0]
 def expect(self,actor,names):
  ids=[self.rules.move_id(x) for x in names]
  self.assertTrue(all(x in actor.moves for x in ids));return ids
 def test_fixed_full_pairs_native_consumer_snapshot_durable_and_independent_sources(self):
  fixtures=[('class/선동가',{'classes':['class/선동가'],'edges':['edge/호감인']},['천사의키스','도발']),
            ('class/로그',{'classes':['class/로그']},['속여때리기','도둑질']),
            ('feat/금술',{'feats':['feat/금술','feat/독극-무기']},['대타출동','맹독']),
            ('feat/pk-알파',{'classes':['class/염동력자'],'feats':['feat/pk-알파']},['숟가락휘기','배리어']),
            ('feat/정신공격',{'classes':['class/텔레파시능력자'],'feats':['feat/정신공격']},['신통력','사이코쇼크'])]
  for uid,fields,names in fixtures:
   with self.subTest(source=uid):
    self.setUp();self.c.spec.update(fields)
    permanent=self.rules.move_id(names[0]);G.set_baseline(self.c,'moves',[permanent])
    G.grant(self.c,'moves',self.rules.move_id(names[1]),'equipment:separate-copy','equipment')
    self.register();self.register();ids=self.expect(self.c,names)
    self.assertTrue(set(ids).issubset(encounter.usable_moves(self.e,self.c)))
    self.assertEqual([self.c.moves.count(x) for x in ids],[1,1])
    row=self.c.spec[G.KEY]['sources'][self.source(uid)]
    self.assertEqual((row['owner_id'],row['lifetime'],row['tutor_points']),(self.c.entity_id,'while_owned',0))
    self.e.gm.snapshot('class-moves');G.revoke(self.c,self.source(uid),engine=self.e);self.expect(self.c,names)
    self.e.gm.restore('class-moves');self.expect(self.c,names)
    e,c=self.load();G.revoke(c,self.source(uid),engine=e);self.expect(c,names)
    G.revoke(c,'equipment:separate-copy',engine=e)
    self.assertIn(ids[0],c.moves);self.assertNotIn(ids[1],c.moves)
 def test_actual_class_skill_domains(self):
  self.c.spec.update(classes=['class/로그','class/선동가'],edges=['edge/호감인']);self.register()
  self.assertEqual(C.skill_domain(self.c,'Rogue'),('곡예','육상','은신'))
  self.assertEqual(C.skill_domain(self.c,'Provocateur'),('매력','교활','협박'))
  self.c.spec['classes'].remove('class/로그');self.register()
  self.assertNotIn(self.rules.move_id('도둑질'),self.c.moves)
  with self.assertRaises(ValueError):C.skill_domain(self.c,'Rogue')
 def test_mental_assault_markdown_and_csv_are_explicit_independent_sources(self):
  import static_feature_state_grants as STATIC
  uid='feat/정신공격';csv='C2CSV/input/db/feats.csv:R507:main'
  common=self.rules.move_id('신통력');md=self.rules.move_id('사이코쇼크');sheet=self.rules.move_id('어시스트파워')
  self.assertIsNone(STATIC.identity(self.rules,uid));self.assertEqual(STATIC.identity(self.rules,csv),csv)
  for alias in (uid,'정신공격','Mental Assault'):
   with self.subTest(markdown_alias=alias):
    self.setUp();self.c.spec['feats']=[alias];self.register()
    self.assertTrue({common,md}.issubset(encounter.usable_moves(self.e,self.c)))
    self.assertNotIn(sheet,self.c.moves)
  self.setUp();self.c.spec['feats']=[csv];self.register()
  self.assertTrue({common,sheet}.issubset(encounter.usable_moves(self.e,self.c)));self.assertNotIn(md,self.c.moves)
  self.assertEqual(self.c.stats['spd'],11)
  csv_source='static-feature:'+self.c.entity_id+':'+csv
  row=self.c.spec[G.KEY]['sources'][csv_source]
  self.assertEqual((row['clause_id'],row['owner_id'],row['lifetime']),(csv,self.c.entity_id,'while_owned'))
  for first in (uid,csv):
   with self.subTest(remove_first=first):
    self.setUp();G.set_baseline(self.c,'moves',['struggle',common]);self.c.spec['feats']=[uid,csv]
    csv_source='static-feature:'+self.c.entity_id+':'+csv
    self.register();self.register();self.assertEqual(self.c.moves.count(common),1)
    self.assertTrue({common,md,sheet}.issubset(encounter.usable_moves(self.e,self.c)))
    self.e.gm.snapshot('mental-variants');e,c=self.load()
    self.assertIn(self.source(uid),c.spec[G.KEY]['sources']);self.assertIn(csv_source,c.spec[G.KEY]['sources'])
    c.spec['feats'].remove(first);ITEMS.register_feats(e,c)
    kept,removed=(sheet,md) if first==uid else (md,sheet)
    self.assertIn(kept,encounter.usable_moves(e,c));self.assertNotIn(removed,c.moves)
    self.assertEqual(c.stats['spd'],11 if first==uid else 10)
    c.spec['feats']=[];ITEMS.register_feats(e,c)
    self.assertCountEqual(c.moves,['struggle',common]);self.assertEqual(c.stats['spd'],10)
    self.assertTrue(e.validate_state()['valid'])
    G.revoke(self.c,self.source(uid),engine=self.e)
    self.e.gm.restore('mental-variants');self.assertTrue({common,md,sheet}.issubset(self.c.moves))
 def test_aura_exact_two_choice_source_survives_codec_then_owner_removal(self):
  self.c.spec.update(classes=['class/파동술사'],edges=['edge/원소-교감'],edge_choices={'edge/원소-교감':'격투'},feature_choices={C.AURA:['판별','발경']})
  self.register();self.expect(self.c,['판별','발경']);self.assertNotIn(self.rules.move_id('진공파'),self.c.moves)
  self.e.gm.snapshot('aura');e,c=self.load();self.assertEqual(c.spec['feature_choices'][C.AURA],['판별','발경'])
  c.spec['classes']=[];ITEMS.register_feats(e,c);self.assertFalse(set(self.rules.move_id(x) for x in ['판별','발경','진공파']) & set(c.moves))
 def test_invalid_selection_and_prerequisite_fail_before_any_mutation_or_rng(self):
  self.c.spec.update(classes=[C.AURA],edges=['edge/원소-교감'],edge_choices={'edge/원소-교감':'격투'})
  for choice in (None,['판별'],['판별','판별'],['판별','맹독'],['판별','진공파','발경']):
   self.c.spec['feature_choices']={C.AURA:choice};before=deepcopy(self.c.spec);rng=self.e.rng.getstate()
   with self.assertRaises(ValueError):self.register()
   self.assertEqual(self.c.spec,before);self.assertEqual(self.e.rng.getstate(),rng)
  self.c.spec.update(feature_choices={C.AURA:['판별','발경']},edge_choices={'edge/원소-교감':'불꽃'})
  with self.assertRaisesRegex(ValueError,'Fighting'):self.register()
 def ranked(self,uid,base,choices):
  self.c.spec.update(classes=[base],feats=[uid],feat_ranks={uid:len(choices)},feature_choices={uid:choices})
 def test_athletic_rank_history_progress_and_removal_preserves_other_sources(self):
  uid='feat/육상-기술';self.ranked(uid,'class/운동선수',[['블록','괴력']]);self.register()
  self.c.spec['feat_ranks'][uid]=3;self.c.spec['feature_choices'][uid].extend([['누르기','신속'],['메가톤킥','원수갚기']]);self.register();self.register()
  wanted=['블록','괴력','누르기','신속','메가톤킥','원수갚기'];self.expect(self.c,wanted)
  self.assertTrue(set(self.rules.move_id(x) for x in wanted).issubset(encounter.usable_moves(self.e,self.c)))
  e,c=self.load();c.spec['feat_ranks'][uid]=1;c.spec['feature_choices'][uid]=[['블록','괴력']];ITEMS.register_feats(e,c)
  self.expect(c,['블록','괴력']);self.assertNotIn(self.rules.move_id('메가톤킥'),c.moves)
  c.spec['feats']=[];ITEMS.register_feats(e,c);self.assertEqual(c.moves,['struggle'])
 def test_weightless_step_complete_dynamic_ability_consumers_allow_scene_end(self):
  uid='feat/무중력-스텝';name='틈새포착';aid=ABILITY.ability_id(self.rules,name)
  self.register();self.assertNotIn(aid,ABILITY.known(self.c))
  self.c.spec.update(classes=['class/닌자'],feats=[uid]);self.register();self.register()
  self.assertEqual(ABILITY.known(self.c).count(aid),1)
  source=self.source(uid);row=self.c.spec[G.KEY]['sources'][source]
  self.assertEqual((row['rule_id'],row['owner_id'],row['grants']['abilities']),(uid,self.c.entity_id,[name]))
  self.e.end_encounter();self.assertIn(name,self.c.abilities)
  self.assertEqual(self.e.skill_roll(self.c,'은신',fixed=[1]*6).total,8)
 def test_available_athletic_table_moves_restore_and_missing_source_is_atomic(self):
  # All printed choices are learned; static Bind is excluded from active use.
  printed={1:['조이기','블록','힘껏치기','괴력'],2:['누르기','돌진','신속'],3:['메가톤킥','객기','원수갚기']}
  uid='feat/육상-기술'
  for rank,names in printed.items():
   for name in names:
    with self.subTest(rank=rank,move=name):
     self.setUp();earlier=[['블록','괴력'],['누르기','돌진']][:rank-1]
     companion=next(x for x in names if x!=name);choices=earlier+[[name,companion]]
     self.ranked(uid,'class/운동선수',choices);self.register();self.register()
     expected=[self.rules.move_id(x) for pair in choices for x in pair]
     active=[mid for mid in expected if self.rules.move(mid)['class']!='항상']
     self.assertTrue(set(expected).issubset(self.c.moves))
     self.assertTrue(set(active).issubset(encounter.usable_moves(self.e,self.c)))
     self.assertNotIn('move/조이기',encounter.usable_moves(self.e,self.c))
     self.assertCountEqual(self.c.spec[G.KEY]['sources'][self.source(uid)]['grants']['moves'],expected)
     e,c=self.load();self.assertEqual(c.spec['feature_choices'][uid],choices)
     self.assertTrue(set(expected).issubset(c.moves))
     self.assertTrue(set(active).issubset(encounter.usable_moves(e,c)))
     G.revoke(c,self.source(uid),engine=e);self.assertEqual(c.moves,['struggle'])
     # The acquired HP tag still requires its while-owned receipt until the
     # actual Feature is withdrawn and its remaining projections reconcile.
     c.spec['feats'].remove(uid);ITEMS.register_feats(e,c)
     self.assertNotIn(self.source(uid),c.spec[G.KEY]['sources'])
     self.assertTrue(e.validate_state()['valid'])
  self.setUp();self.assertEqual(self.rules.move_id('조이기'),'move/조이기')
  self.ranked(uid,'class/운동선수',[['조이기','블록']]);before=deepcopy((self.c.spec,self.c.moves,self.e.rng.getstate()))
  with patch.dict(self.rules.moves):
   self.rules.moves.pop('move/조이기')
   with self.assertRaisesRegex(ValueError,'printed rank/domain'):self.register()
  self.assertEqual((self.c.spec,self.c.moves,self.e.rng.getstate()),before)
 def test_rank_choices_are_per_acquired_rank_not_six_highest_rank_moves(self):
  uid='feat/육상-기술';self.ranked(uid,'class/운동선수',[['메가톤킥','원수갚기'],['누르기','신속'],['블록','괴력']])
  before=deepcopy(self.c.spec)
  with self.assertRaises(ValueError):self.register()
  self.assertEqual(self.c.spec,before)
  self.ranked(uid,'class/운동선수',[['블록','괴력']]);self.register()
  self.c.spec['feature_choices'][uid]=[['블록','힘껏치기']]
  with self.assertRaisesRegex(ValueError,'silently'):self.register()
  self.expect(self.c,['블록','괴력']);self.assertNotIn(self.rules.move_id('힘껏치기'),self.c.moves)
 def test_martial_full_rank_domain_and_ability_condition(self):
  uid='feat/무술-훈련';self.c.spec['edges']=['edge/기본-무술']
  FEATURE_ACQUISITION.acquire_martial_artist(self.e,self.c,acquisition_request_id='martial/iron-fist',selected_ability='철주먹',lifecycle_policy=FEATURE_ACQUISITION.LIFECYCLE_WHILE_OWNED)
  self.ranked(uid,'class/무술가',[['두번차기','마하펀치'],['깨트리기','연속펀치'],['인파이트','스카이어퍼']])
  clean=deepcopy(self.c.spec)
  self.c.spec[FEATURE_ACQUISITION.PROJECTION_KEY][FEATURE_ACQUISITION.MARTIAL_ARTIST]['class/무술가:1']['values']=['ability/근성']
  before=deepcopy(self.c.spec)
  with self.assertRaisesRegex(ValueError,'integrity|projection'):self.register()
  self.assertEqual(self.c.spec,before)
  self.c.spec.clear();self.c.spec.update(clean);self.register()
  self.expect(self.c,['두번차기','마하펀치','깨트리기','연속펀치','인파이트','스카이어퍼'])
  self.e.gm.snapshot('martial');e,c=self.load();self.assertEqual(c.spec['feat_ranks'][uid],3)
  G.revoke(c,self.source(uid),engine=e)
  self.assertFalse(set(self.rules.move_id(x) for x in ['두번차기','마하펀치','깨트리기','연속펀치','인파이트','스카이어퍼']) & set(c.moves))
 def test_hex_all_six_moves_rank3_only_hex_and_rank2_unchanged_domain(self):
  uid='feat/오컬트-마니아-연구';choices=[['이상한빛','저주'],['최면술','원한'],['도깨비불','병상첨병']]
  self.ranked(uid,'class/오컬트마니아',choices);self.register();self.expect(self.c,[x for pair in choices for x in pair])
  e,c=self.load();self.assertEqual(len([x for x in c.moves if x!='struggle']),6)
  self.setUp();self.ranked(uid,'class/오컬트마니아',[['이상한빛','저주'],['병상첨병','원한']])
  with self.assertRaises(ValueError):self.register()
 def test_hex_curse_native_ghost_effect_frequency_and_source_revocation_only(self):
  import frequency as F
  import effects_ext as EXT
  import effect_contracts as CONTRACT
  uid='feat/오컬트-마니아-연구';self.ranked(uid,'class/오컬트마니아',[['이상한빛','저주']])
  self.register();mid=self.rules.move_id('저주');mv=self.rules.move(mid)
  G.set_baseline(self.c,'moves',[mid])
  self.assertNotIn('고스트',self.c.types);self.assertEqual(F.move_frequency(self.e,mid,self.c),('scene',1))
  target=Combatant(self.rules,build_trainer(self.rules,'curse-target',30,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)))
  target.side='enemy';target.pos=(1,0);self.c.pos=(0,0);self.e.everyone=self.e.gm.everyone=[self.c,target]
  ctx={'attacker':self.c,'target':target,'move':mv,'hit':True,'nat':None,'engine':self.e}
  self.assertTrue(CONTRACT.condition_text(self.e,self.c,target,'user is 고스트',ctx))
  self.assertTrue(EXT._eval_cond(self.e,self.c,target,'user is ghost',ctx))
  self.assertFalse(CONTRACT.condition_text(self.e,self.c,target,'user is 고스트',dict(ctx,move=self.rules.move('move/이상한빛'))))
  hp=self.c.hp;stats=deepcopy(self.c.stages)
  self.e.use_move(self.c,target,mid)
  self.assertEqual(self.c.hp,hp-self.c.max_hp//3)
  self.assertIn('저주',target.conditions);self.assertEqual(self.c.stages,stats)
  self.assertNotIn('고스트',self.c.types);self.assertFalse(F.move_allowed(self.e,self.c,mid)[0])
  self.e.gm.snapshot('ghost-exception');e,c=self.load();self.assertEqual(F.move_frequency(e,mid,c),('scene',1))
  G.revoke(c,'feature:'+c.entity_id+':'+uid,engine=e)
  self.assertIn(mid,c.moves);self.assertEqual(F.move_frequency(e,mid,c),('every_other_turn',1))
  self.assertNotIn('고스트',c.types)
 def test_hex_curse_range_boundary_and_area_entry_keep_the_actual_enemy_target(self):
  from grid import Grid
  uid='feat/오컬트-마니아-연구';self.ranked(uid,'class/오컬트마니아',[['이상한빛','저주']]);self.register()
  target=Combatant(self.rules,build_trainer(self.rules,'range-target',30,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)))
  self.c.pos=(0,0);target.pos=(9,0);target.side='enemy';self.e.grid=Grid(20,3);self.e.everyone=self.e.gm.everyone=[self.c,target]
  before=(self.c.hp,deepcopy(self.c.move_uses),self.e.rng.getstate(),deepcopy(getattr(self.c,"budget",None)))
  with self.assertRaisesRegex(ValueError,'eight metres'):self.e.use_move(self.c,target,'move/저주')
  self.assertEqual((self.c.hp,self.c.move_uses,self.e.rng.getstate(),getattr(self.c,"budget",None)),before)
  target.pos=(8,0);hp=self.c.hp
  self.e.use_move_on(self.c,target,'move/저주',self.e.everyone)
  self.assertIn('저주',target.conditions);self.assertNotIn('저주',self.c.conditions)
  self.assertEqual(self.c.pos,(0,0));self.assertEqual(self.c.hp,hp-self.c.max_hp//3)
  original=self.rules.move_mech('move/저주')[0]
  branch=next(x for x in original['effects_exec'] if x.get('if')=='user is 고스트')
  self.assertEqual(next(x for x in branch['then'] if x['type']=='apply_status')['range'],'8m')
 def test_duplicate_ownership_and_choice_aliases_do_not_mutate(self):
  self.c.spec.update(feats=['feat/pk-알파','PK Alpha'],classes=['class/염동력자'])
  before=deepcopy(self.c.spec)
  with self.assertRaisesRegex(ValueError,'duplicate'):self.register()
  self.assertEqual(self.c.spec,before)
  self.c.spec.update(feats=[],classes=[C.AURA],edges=['edge/원소-교감'],edge_choices={'edge/원소-교감':'격투'},feature_choices={C.AURA:['판별','발경'],'Aura Guardian':['판별','발경']})
  with self.assertRaisesRegex(ValueError,'duplicate'):self.register()

if __name__=='__main__':unittest.main()
