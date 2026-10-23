"""Original CSV boundary regressions through actual acquired-Gift consumers."""
from pathlib import Path
from copy import deepcopy
import json, sys, unittest
ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from grid import Grid
import blessing_observations as O
import blessing_skill_features as B
import class_passive_combat as C
import items
import perception_observe as P
import state_codec as CODEC
import effects_ext as EXT
import test_category2_blessing_context_skill_batch as CONTEXT_TESTS
import test_category2_gift_purpose as PURPOSE_TESTS
import tools.test_category2_blessing_skill_rules_ten as SKILL_TESTS
import tools.test_category2_blessing_observation_batch as OBSERVATION_TESTS
import test_category2_static_feature_state_grants as STATIC_TESTS
import tools.test_category2_class_passive_combat_bulk as RESILIENCE_TESTS

class ContextTests(CONTEXT_TESTS.BlessingContextSkillBatchTests):
 pass

class PurposeTests(PURPOSE_TESTS.Tests):
 pass

class SkillTests(SKILL_TESTS.BlessingSkillRuleTests):
 pass

class ObservationTests(OBSERVATION_TESTS.Tests):
 pass

class StaticTests(STATIC_TESTS.StaticFeatureStateGrantTests):
 pass

class ResilienceTests(RESILIENCE_TESTS.ClassPassiveCombatBulkTests):
 pass


class SourceBoundaries(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')
 def setUp(self):
  self.e=Engine(self.rules,seed=3289);self.e.grid=Grid(40,40)
  self.a=Combatant(self.rules,build_trainer(self.rules,'actual observer',30,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'직감':3},extra={'feats':['supp-blessings/계약자'],'gifts':[],'gift_patrons':{},'gift_choices':{}}))
  self.t=Combatant(self.rules,build_pokemon(self.rules,'잉어킹',10,moves=[],abilities=[],extra={'size':'Medium','height_m':1.237}))
  self.e.gm.add_combatant(self.a,pos=(2,2),side='party',reason='actual GM registered observer')
  self.e.gm.add_combatant(self.t,pos=(5,6),side='foe',reason='actual GM registered target')
 def own(self,gift,patron,choice=None,configuration=None):
  self.assertEqual(self.rules._selected_rule(gift),gift)
  self.a.spec['gifts'].append(gift);self.a.spec['gift_patrons'][gift]=patron
  if choice is not None:self.a.spec['gift_choices'][gift]=deepcopy(choice)
  return self.e.confirm_blessing_gift(self.a,gift,reason='GM authorizes this exact acquired Gift from '+patron,configuration=configuration)
 def fact(self,gift,value,target=None):
  if gift=='gift/마이너-기프트-이단자-탐지':value={'basis':'same scene and GM sensing criterion',**value}
  return P.record_blessing_fact(self.e,self.a,gift,value,target=target,reason='GM establishes this exact current campaign fact')
 def begin(self):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

 def test_three_static_immunities_accept_actual_gifts_and_native_permission(self):
  for gift,patron,status,move in (
   ('gift/마이너-기프트-로얄-하트','라티아스','헤롱헤롱',None),
   ('gift/메이저-기프트-순수-호흡','쉐이미',None,'move/분노가루'),
   ('gift/마이너-기프트-드림-마스터리','크레세리아',None,'move/최면술')):
   with self.subTest(gift=gift):
    self.setUp()
    if gift=='gift/메이저-기프트-순수-호흡':self.own('gift/마이너-기프트-식물-직감',patron)
    self.own(gift,patron);items.register_feats(self.e,self.a)
    if status:
     self.e.apply_status(self.a,status,applied_by=self.t);self.assertNotIn(status,self.a.conditions)
    if move:
     self.assertFalse(self.e.accuracy_check(self.t,self.a,self.rules.move(move),fixed_roll=20)[0])

 def test_unaligned_target_and_no_weakness_do_not_invent_affiliation(self):
  gift='gift/위대한-존재의-통찰력'
  self.own('gift/고대의-지혜','뮤',configuration={'role':'contractor'})
  self.own(gift,'뮤',{'role':'계약자'})
  self.fact(gift,{'allegiance':'','weaknesses':[],'goals':'구조','motives':'연민','harms_patron_followers':False},self.t)
  self.begin();out=P.observe_blessing(self.e,self.a,gift,target=self.t)
  self.assertEqual(out['values'],{'weakness':None,'aligned':False,'harms_patron_followers':False})

 def test_no_nearby_legend_is_a_valid_finite_serpent_result(self):
  gift='gift/마이너-기프트-세계뱀의-포옹';self.own(gift,'지가르데')
  self.fact(gift,{'legendary_presence':False,'approximate_locations':[]})
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'legendary_presence':False,'approximate_locations':[]})

 def test_spatial_awareness_measures_native_length_to_nearest_centimetre(self):
  gift='gift/마이너-기프트-공간인식';self.own(gift,'펄기아')
  out=P.observe_blessing(self.e,self.a,gift,target=self.t)['values']
  self.assertEqual(out['distance_cm'],500)
  self.assertEqual(out['dimensions_cm'],{'height':124})

 def test_resilience_rejects_a_type_outside_actual_patron_resistance(self):
  gift=C.BLESSED_RESILIENCE
  patron=Combatant(self.rules,build_pokemon(self.rules,'리자몽',30,moves=[],abilities=[]))
  self.e.gm.add_combatant(patron,pos=(9,9),side='party',reason='actual divine patron manifestation')
  self.a.spec['gifts']=['gift/축복받은-힘',gift];self.a.spec['gift_patrons'][gift]=patron.entity_id
  self.a.spec['class_passive_choices']={gift:{'role':'messiah','patron_id':patron.entity_id,'eligible_types':['물','불꽃'],'selected_types':['물','불꽃']}}
  with self.assertRaisesRegex(ValueError,'patron|eligible|resistan'):
   self.e.confirm_blessing_gift(self.a,gift,reason='GM confirms only a real eligible patron domain')

 def test_resilience_actual_domain_uses_unconditional_typed_effects_only(self):
  gift=C.BLESSED_RESILIENCE
  patron=Combatant(self.rules,build_pokemon(self.rules,'스이쿤',30,moves=[],abilities=[]))
  self.e.gm.add_combatant(patron,pos=(9,9),side='party',reason='actual Water patron with actual passive state')
  base=['강철','물','불꽃','얼음']
  self.assertEqual(C._patron_resistance_domain(self.e,self.a,patron),base)
  patron.modifiers.extend([
   {'type':'resistance_step','types':['노말'],'value':1},
   {'type':'immunity','to':'땅'},
   {'type':'absorb','move_type':'독'},
   {'type':'resistance_step','types':['전기'],'value':3,'if':'unestablished campaign condition'},
   {'type':'immunity','to':'격투','if':'hp full'},
   {'type':'absorb','move_type':'드래곤','while_status':'잠듦'},
   {'type':'resistance_step','types':['에스퍼'],'value':2,'vs':'physical'},
   {'type':'resistance_step','types':['악'],'value':2,'if_weather':'sun'},
  ])
  self.e.weather='sun'
  expected=sorted(base+['노말','땅','독'])
  self.assertEqual(C._patron_resistance_domain(self.e,self.a,patron),expected)
  self.a.spec['gifts']=['gift/축복받은-힘',gift];self.a.spec['gift_patrons'][gift]=patron.entity_id
  self.a.spec['class_passive_choices']={gift:{'role':'messiah','patron_id':patron.entity_id,'eligible_types':expected,'selected_types':['노말','땅']}}
  record=self.e.confirm_blessing_gift(self.a,gift,reason='actual unconditional typed patron domain')
  self.assertEqual(record['configuration']['eligible_types'],expected)
  self.e.register_abilities(self.a);self.assertEqual(C.resistance_steps(self.e,self.a,'노말'),1)
  patron.abilities_suppressed=True
  self.assertEqual(C._patron_resistance_domain(self.e,self.a,patron),base)

 def test_elemental_soul_all_six_patrons_types_and_ten_metre_boundary(self):
  gift='gift/마이너-기프트-엘리멘탈-소울'
  for patron,element in [('프리져','얼음'),('파이어','불꽃'),('썬더','전기'),('앤테이','불꽃'),('라이코','전기'),('스이쿤','물')]:
   with self.subTest(patron=patron):
    self.setUp();self.own(gift,patron,{'patron':patron});self.t._types=[element]
    self.t.pos=(12,2);self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':True})
    self.t.pos=(13,2);self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':False})
    self.t.pos=(3,2);self.t._types=['노말'];self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':False})

 def test_clock_and_spatial_pair_measurements_use_actual_world_state(self):
  clock='gift/마이너-기프트-완벽한-타이밍';space='gift/마이너-기프트-공간인식'
  self.own(clock,'디아루가');self.e.advance_time(73)
  self.assertEqual(P.observe_blessing(self.e,self.a,clock,selection={'started_at':13})['values'],{'world_seconds':73,'stopwatch_seconds':60})
  self.own(space,'펄기아');self.t.pos=(8,6)
  other=Combatant(self.rules,build_pokemon(self.rules,'잉어킹',10,moves=[],abilities=[]))
  self.e.gm.add_combatant(other,pos=(5,2),side='party',reason='actual starting object')
  self.assertEqual(P.observe_blessing(self.e,self.a,space,target=self.t,selection={'from_id':other.entity_id})['values']['distance_cm'],500)
  self.t.pos=(20,2)
  with self.assertRaisesRegex(ValueError,'ten-metre'):P.observe_blessing(self.e,self.a,space,target=self.t)

 def test_heretic_range_requires_signed_actual_count_judgment_and_remains_anonymous(self):
  gift='gift/마이너-기프트-이단자-탐지';self.own(gift,'미싱노 (타락한 창조주)')
  other=Combatant(self.rules,build_trainer(self.rules,'other actual gifted trainer',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'gifts':['gift/마이너-기프트-진실된-영웅'],'gift_patrons':{'gift/마이너-기프트-진실된-영웅':'레시라무'}}))
  self.e.gm.add_combatant(other,pos=(8,2),side='foe',reason='actual target Gift acquisition')
  self.e.confirm_blessing_gift(other,'gift/마이너-기프트-진실된-영웅',reason='GM confirms this actual acquired Gift')
  with self.assertRaisesRegex(ValueError,'GM gift-count sensing radius'):P.observe_blessing(self.e,self.a,gift)
  self.fact(gift,{'range_cm':300},other)
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':False})
  other.pos=(5,2);self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':True})
  other.spec['gifts'].append('gift/마이너-기프트-이상적-영웅');other.spec['gift_patrons']['gift/마이너-기프트-이상적-영웅']='제크로무'
  self.e.confirm_blessing_gift(other,'gift/마이너-기프트-이상적-영웅',reason='actual second acquired Gift changes sensing facts')
  with self.assertRaisesRegex(ValueError,'count.*changed'):P.observe_blessing(self.e,self.a,gift)
  with self.assertRaisesRegex(ValueError,'monotonic'):self.fact(gift,{'range_cm':200},other)
  self.fact(gift,{'range_cm':1200},other);other.pos=(14,2)
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':True})
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  la=next(x for x in loaded.everyone if x.entity_id==self.a.entity_id)
  self.assertEqual(P.observe_blessing(loaded,la,gift)['values'],{'presence':True})
  self.fact(gift,{'range_cm':200,'basis':'new environment and independently adjudicated criterion'},other)
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':False})
  self.fact(gift,{'range_cm':1200},other)
  other.pos=(18,2);self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':False})
  other.pos=(5,2);missing='gift/마이너-기프트-외계인-얼굴'
  other.spec['gifts']=[missing];other.spec['gift_patrons']={missing:'미싱노 (코즈믹 호러)'}
  self.e.confirm_blessing_gift(other,missing,reason='actual MissingNo Gift only; excluded by source')
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':False})

 def test_heretic_usual_range_and_explicit_signed_gm_exception(self):
  gift='gift/마이너-기프트-이단자-탐지';self.own(gift,'미싱노 (타락한 창조주)')
  actual='gift/마이너-기프트-진실된-영웅'
  other=Combatant(self.rules,build_trainer(self.rules,'actual gifted target',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'gifts':[actual],'gift_patrons':{actual:'레시라무'}}))
  self.e.gm.add_combatant(other,pos=(17,2),side='foe',reason='actual fifteen-metre target')
  self.e.confirm_blessing_gift(other,actual,reason='actual approved non-MissingNo Gift')
  self.fact(gift,{'range_cm':1500},other)
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':True})
  other.pos=(18,2)
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':False})
  before=deepcopy(self.a.spec)
  with self.assertRaisesRegex(ValueError,'explicit GM exception'):self.fact(gift,{'range_cm':1501},other)
  self.assertEqual(self.a.spec,before)
  value={'range_cm':1501,'exception_reason':'GM explicitly allows this unusually strong current Gift signal beyond the usual fifteen metres'}
  record=self.fact(gift,value,other);self.assertEqual(record['value']['range_cm'],1501)
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':False})
  self.fact(gift,{**value,'range_cm':1600},other)
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'presence':True})
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  la=next(x for x in loaded.everyone if x.entity_id==self.a.entity_id)
  self.assertEqual(P.observe_blessing(loaded,la,gift)['values'],{'presence':True})

 def test_darkrai_omen_selects_danger_and_rejects_other_patron_tone_atomically(self):
  gift='gift/메이저-기프트-꿈의-전조';self.own('gift/마이너-기프트-드림-마스터리','다크라이')
  self.own(gift,'다크라이',{'patron':'다크라이'})
  self.fact(gift,{'tone':'유리함','hint':'틀린 후원자 힌트'})
  before=deepcopy(self.a.spec)
  with self.assertRaisesRegex(ValueError,'patron'):P.observe_blessing(self.e,self.a,gift)
  self.assertEqual(self.a.spec,before)
  self.fact(gift,{'tone':'위험/슬픔','hint':'오는 폭풍'})
  self.assertEqual(P.observe_blessing(self.e,self.a,gift)['values'],{'tone':'위험/슬픔','hint':'오는 폭풍'})

 def test_royal_heart_native_status_codec_and_source_removal(self):
  gift='gift/마이너-기프트-로얄-하트';self.own(gift,'라티오스');items.register_feats(self.e,self.a)
  self.e.apply_status(self.a,'헤롱헤롱',applied_by=self.t);self.assertNotIn('헤롱헤롱',self.a.conditions)
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
  a=next(v for v in loaded.everyone if v.entity_id==self.a.entity_id);t=next(v for v in loaded.everyone if v.entity_id==self.t.entity_id)
  loaded.apply_status(a,'헤롱헤롱',applied_by=t);self.assertNotIn('헤롱헤롱',a.conditions)
  a.spec['gifts'].remove(gift);items.register_feats(loaded,a)
  loaded.apply_status(a,'헤롱헤롱',applied_by=t);self.assertIn('헤롱헤롱',a.conditions)

 def test_resilience_actual_damage_two_roles_reselection_scene_and_receipt(self):
  helper=ResilienceTests('test_blessed_resilience_roles_selection_failure_atomicity_and_scene_end');helper.rules=self.rules
  gift=C.BLESSED_RESILIENCE
  e,t,p,q=helper.fixture(gifts=[gift],choices={gift:{'role':'messiah','selected_types':['불꽃','물']}})
  move=self.rules.move('move/화염방사')
  reduced=e.roll_damage(q,t,move,set_damage=True)
  t.spec['gifts'].clear();e.register_abilities(t)
  ordinary=e.roll_damage(q,t,move,set_damage=True)
  self.assertLess(reduced,ordinary)
  e,t,p,q=helper.fixture(gifts=[gift],choices={gift:{'role':'contractor'}})
  e.start_round(e.everyone);e.start_of_turn(t)
  self.assertEqual(e.activate_blessed_resilience(t,'불꽃'),(1,0));self.assertEqual(C.resistance_steps(e,t,'불꽃'),1)
  e.end_of_turn(t);e.end_round();e.start_round(e.everyone);e.start_of_turn(t)
  self.assertEqual(e.activate_blessed_resilience(t,'물'),(1,0));self.assertEqual(C.resistance_steps(e,t,'불꽃'),0);self.assertEqual(C.resistance_steps(e,t,'물'),1)
  loaded=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False)))
  lt=next(v for v in loaded.everyone if v.entity_id==t.entity_id);self.assertEqual(C.resistance_steps(loaded,lt,'물'),1)
  loaded.end_scene(loaded.everyone);self.assertEqual(C.resistance_steps(loaded,lt,'물'),0)

 def test_all_six_shard_colors_and_optional_mind_replacements_preserve_exact_scope(self):
  for color,skill in [('빨강','협박'),('주황','명령'),('노랑','매력'),('초록','직감'),('파랑','협박'),('보라','집중')]:
   with self.subTest(color=color):
    helper=SkillTests('test_dazzling_stage_and_royal_privilege_keep_exact_csv_sources');helper.rules=self.rules;helper.setUp()
    helper.own(B.ADVANCED.ROYAL_PRIVILEGE)
    helper.a.spec.setdefault('items',{})[color+'조각']=1;items.register_item(helper.e,helper.a,color+'조각')
    rank={'협박':4,'명령':3,'매력':3,'직감':3,'집중':3}[skill]
    self.assertEqual(helper.e.skill_roll(helper.a,skill,fixed=[2]*rank).modifier,2)
    self.assertEqual(helper.e.skill_roll(helper.a,'생존',fixed=[2]*3).modifier,0)
  for gift,skill,purpose in [(B.ADVANCED.SPIRIT_OF_JUSTICE,'전투','resist_disarm'),(B.ADVANCED.ALIEN_FACE,'협박',None)]:
   helper=SkillTests('test_spirit_of_justice_replaces_body_and_adds_disarm_bonus');helper.rules=self.rules;helper.setUp();helper.own(gift)
   context=None if purpose is None else {'purpose':purpose,'reason':'actual resistance to disarming'}
   result=helper.e.skill_roll(helper.a,skill,mods=2,fixed=[2]*4,skill_context=context)
   self.assertEqual(result.modifier,4 if purpose else 2)

 def test_paragon_category_choices_and_source_scene_end_invalidate_projection(self):
  for category,positive,negative in [('physical','전투','매력'),('mental','기술학','매력'),('spirit','매력','전투')]:
   helper=SkillTests('test_paragon_permanent_and_scene_roles_with_atomic_shift_failure');helper.rules=self.rules;helper.setUp()
   helper.own(B.ADVANCED.PARAGON,configuration={'role':'messiah','category':category})
   for skill,rank,expected in [(positive,4 if positive=='전투' else 3,2),(negative,4 if negative=='전투' else 3,0)]:
    self.assertEqual(helper.e.skill_roll(helper.a,skill,fixed=[2]*rank).modifier,expected)
  helper=SkillTests('test_paragon_permanent_and_scene_roles_with_atomic_shift_failure');helper.rules=self.rules;helper.setUp()
  helper.own(B.ADVANCED.PARAGON,configuration={'role':'contractor','category':'mental'})
  import turn
  turn.reset_budget(helper.e,helper.a);helper.e.activate_blessing_skill_rule(helper.a,B.ADVANCED.PARAGON,reason='actual category scene activation')
  helper.e.end_scene(helper.e.everyone)
  self.assertEqual(helper.e.skill_roll(helper.a,'기술학',fixed=[2]*3).modifier,0)

 def test_spatial_gm_measurements_bind_actual_geometry_without_guessing_category_lengths(self):
  gift='gift/마이너-기프트-공간인식';self.own(gift,'펄기아');self.t.spec.pop('height_m',None)
  with self.assertRaisesRegex(ValueError,'GM measured object dimensions'):P.observe_blessing(self.e,self.a,gift,target=self.t)
  self.fact(gift,{'dimensions_cm':{'length':235,'width':118}},self.t)
  self.assertEqual(P.observe_blessing(self.e,self.a,gift,target=self.t)['values']['dimensions_cm'],{'length':235,'width':118})
  self.t.spec['height_m']=1.0
  with self.assertRaisesRegex(ValueError,'geometry changed'):P.observe_blessing(self.e,self.a,gift,target=self.t)


if __name__=='__main__':unittest.main()

