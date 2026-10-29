"""Whole Hobbyist: real acquisitions, paired grants and existing native consumers.

No feature/class/edge ownership is injected. Scene helpers only create actual
actors, terrain, parties and declared skill observations.
"""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import test_book_juggler_full as FIX
import hobbyist as H,trainer_feature_acquisition as T,state_fields as F,state_grants as G
import acquired_features as A,skill_modifiers as S,world_entities as W,state_codec as CODEC
import action_points as AP,frequency as FREQ
from native_scenario_fixture import assert_rejected_unchanged


class HobbyistTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core+errata')
 actor=FIX.JugglerTests.actor
 begin=FIX.JugglerTests.begin
 close=FIX.JugglerTests.close
 move=FIX.JugglerTests.move
 action=FIX.JugglerTests.action
 schedule=FIX.JugglerTests.schedule
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
  self.world()
 def world(self,*,level=30,gen=3,perception=3,wild=False):
  FIX.JugglerTests.setup(self,wild=wild)
  self.e.gm.set_level(self.a,level,reason='actual observed Hobbyist starting level')
  skills=dict.fromkeys(self.e.r.skill_policy['skills'],2);skills.update({'general education':gen,'perception':perception})
  F.base_patch(self.a,{'skills':skills},reason='actual declared Hobbyist skill sheet')
 def reject(self,fn,pattern):return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  ids=[c.entity_id for c in (self.a,self.b,self.p,self.q,self.t)]
  self.e=CODEC.load_engine(self.e.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.a,self.b,self.p,self.q,self.t=[W.actor_index(self.e)[uid] for uid in ids];self.valid()
 def base(self,edition='core',edges=None):
  edges=edges or [{'id':'edge/숙련-스킬','choice':'일반 지식'},{'id':'edge/전문-스킬','choice':'일반 지식'},{'id':'edge/숙련-스킬','choice':'통찰'}]
  return self.e.acquire_hobbyist_feature(self.a,request_id='hobbyist/base',selection={'edition':edition,'edges':edges})
 def dilettante(self,edge='edge/패기',feature='feat/디펜더',*,rank=1,edge_options=None,options=None,substitute='통찰',edition='core',request=None):
  if H.acquired(self.a,H.CLASS)is None:self.base()
  if options is None:options={'selection':{'edition':'core'}} if feature=='feat/융통-명령' else {}
  return self.e.acquire_hobbyist_feature(self.a,H.DILETTANTE,request_id=request or 'dilettante/'+str(rank),rank=rank,
   selection={'edition':edition,'edge':{'id':edge,'options':edge_options or {},'substitute':substitute},'feature':{'id':feature,'options':options,'substitute':substitute}})
 def feature(self,uid):
  if H.acquired(self.a,H.CLASS)is None:self.base()
  return self.e.acquire_hobbyist_feature(self.a,uid,request_id='hobbyist/'+uid,selection={'edition':'core'})
 def printed_parent(self,child):
  parent={**H.SCENE,**H.AP_FEATURES}[child]
  edge='edge/브리더';general=parent if parent.startswith('feat/') else 'feat/디펜더'
  if parent.startswith('edge/'):edge=parent
  if general=='feat/지휘관의-목소리':
   self.ordinary_skills(athletics=3,intimidate=3)
   T.acquire_static(self.e,self.a,'feat/민첩성-훈련',acquisition_request_id='actual/agility')
   T.acquire_static(self.e,self.a,'feat/잔혹성-훈련',acquisition_request_id='actual/brutal')
  if general=='feat/몬스터볼-장인':
   self.ordinary_skills(**{'technology education':5})
   edge='edge/몬스터볼'
   if H.acquired(self.a,H.CLASS)is None:self.base()
   H.grant_qualified_edge(self.e,self.a,'edge/몬스터볼',None,H.source_id(self.a,'edge/몬스터볼'),H.source_id(self.a,H.CLASS))
   H.grant_qualified_edge(self.e,self.a,'edge/몬스터볼-수리',None,H.source_id(self.a,'edge/몬스터볼-수리'),H.source_id(self.a,H.CLASS))
   edge='edge/브리더'
  self.dilettante(edge,general)
  return parent
 def learned(self,child,*,edition='core',options=None):
  self.printed_parent(child)
  self.e.acquire_hobbyist_feature(self.a,H.LOOK,request_id='hobbyist/look',selection={'edition':edition})
  if child=='feat/포획-테크닉':options={'techniques':['거짓 타격','캐치 콤보']}
  if child=='feat/술책':options={'selection':{'source':'core'}}
  kwargs={} if edition=='local_csv' else {'seconds':60,'reason':'actual player learning observed for this printed choice'}
  return self.e.look_and_learn(self.a,child,request_id='learn/'+child,options=options or {},**kwargs)
 def ordinary_skills(self,**updates):
  values=deepcopy(self.a.spec['skills']);values.update(updates);F.base_patch(self.a,{'skills':values},reason='actual observed skill advancement')
 def simple_base(self):
  return self.base(edges=[{'id':'edge/기본-스킬','choice':s} for s in ('의학','기술학','오컬트학')])
 def milestone(self,level,option):
  return self.e.choose_trainer_milestone(self.a,level,option,reason='actual observed player milestone branch')
 def inventory(self,**items):
  self.a.spec.setdefault('items',{}).update(items)
 def decision(self,kind,value):self.e.rulings.add_answer(kind,value,reason='actual player response to native trigger')

 def test_basic_three_actual_rank_edges_perception_and_replay(self):
  row=self.base();self.assertEqual(S.rank(self.e.r,self.a,'일반 지식')[2],5);self.assertEqual(S.rank(self.e.r,self.a,'통찰')[2],4)
  self.assertEqual(S.rank(self.e.r,self.a,'직감')[2],2)
  self.assertEqual(len([r for r in G.state(self.a)['sources'].values() if 'hobbyist_skill_edge'in r]),3)
  self.assertEqual(self.base()['integrity'],row['integrity']);self.restore()

 def test_basic_missing_either_novice_and_unqualified_rank_grant_are_atomic(self):
  self.world(gen=2);self.reject(self.base,'Novice');self.world(perception=2);self.reject(self.base,'Novice')
  self.world(level=1);self.reject(self.base,'rank transition|level')

 def test_core_nonrank_skill_edges_have_actual_choices_and_modifiers(self):
  self.base(edges=[{'id':'edge/단정적인-경향','choice':'mind'},{'id':'edge/스킬-향상','choice':['일반 지식','통찰']},
   {'id':'edge/고난이도-스킬','choice':{'choice_id':'actual-study','skill':'일반 지식','use':'cataloguing dated historical manuscripts','reason':'GM approved narrow use','approved':True}}])
  self.assertEqual(S.modifiers(self.e.r,self.a,'일반 지식',0)['modifier'],3)
  self.assertEqual(len(__import__('skill_stunts').choices(self.e,self.a)),1);self.restore()

 def test_official_errata_is_actual_rank_only_not_virtual_playtest(self):
  self.base('official_errata');self.assertEqual(H.acquired(self.a,H.CLASS)['snapshot']['source']['span'],[446,446])
  self.world();self.reject(lambda:self.base('official_errata',edges=[{'id':'edge/스킬-향상','choice':['통찰','일반 지식']}]*3),'rank-increasing')
  self.reject(lambda:self.base('playtest'),'actual Core')

 def test_four_ranks_commit_both_independent_pair_grants_and_cap(self):
  pairs=[('edge/패기','feat/디펜더'),('edge/브리더','feat/뛰어들기'),('edge/약삭빠름','feat/팔방미인'),('edge/수영-선수','feat/기분전환')]
  for number,(edge,feat) in enumerate(pairs,1):
   self.dilettante(edge,feat,rank=number)
   self.assertEqual((A.owned_rule_count(self.a,edge),A.owned_rule_count(self.a,feat)),(1,1))
  self.assertEqual(A.owned_rule_count(self.a,H.DILETTANTE),4)
  self.reject(lambda:self.dilettante('edge/미용사','feat/내가-도와줄게',rank=5),'rank|four');self.restore()

 def test_all_twenty_two_edge_domains_acquire_actual_ownership_and_bound_provider(self):
  for edge in H.EDGE_SKILLS:
   with self.subTest(edge=edge):
    self.world();row=self.dilettante(edge)
    self.assertEqual(A.owned_rule_count(self.a,edge),1);self.assertEqual(H.provider(self.a,edge)[1]['parent'],row['request_id']);self.valid()

 def test_dilettante_skill_only_waiver_does_not_waive_edge_parents(self):
  self.base();self.reject(lambda:self.dilettante('edge/브리더','feat/응급-처치-전문지식'),'non-skill')
  self.reject(lambda:self.dilettante('edge/몬스터볼','feat/몬스터볼-장인'),'non-skill')
  self.dilettante('edge/메딕-훈련','feat/응급-처치-전문지식');self.assertTrue(H.skill_waived(self.a,'feat/응급-처치-전문지식'));self.restore()

 def test_dilettante_rank_order_duplicates_options_and_substitute_reject_atomically(self):
  self.base();self.reject(lambda:self.dilettante(rank=2),'next|rank')
  self.reject(lambda:self.dilettante(substitute='직감'),'General Education or Perception')
  self.reject(lambda:self.dilettante(edge_options={'pretend':True}),'no acquisition choices')
  self.dilettante();self.reject(lambda:self.dilettante(rank=2,feature='feat/뛰어들기'),'repeat|capacity')

 def test_each_direct_skill_consumer_mapping_is_child_specific_not_global(self):
  for edge in H.EDGE_SKILLS:
   with self.subTest(edge=edge):
    self.world();self.dilettante(edge,substitute='통찰')
    for named in H.DIRECT_SKILLS.get(edge,()):self.assertEqual(S.skill_id(self.e.r.skill_policy,H.direct_skill(self.a,edge,named)),'perception')
    allowed={S.skill_id(self.e.r.skill_policy,s,required=True) for s in H.DIRECT_SKILLS.get(edge,())}
    self.assertEqual(H.direct_skill(self.a,edge,'의학'),'통찰' if 'medical education' in allowed else '의학')
    self.assertEqual(S.rank(self.e.r,self.a,'직감')[2],2)

 def test_dynamism_swimmer_acrobat_and_move_grant_have_real_native_effects(self):
  self.dilettante('edge/패기');self.a.spec['initiative_basis']='base'
  self.assertEqual(__import__('trainer_capabilities').initiative_bonus(self.a),4)
  self.dilettante('edge/수영-선수','feat/뛰어들기',rank=2)
  caps=__import__('trainer_capabilities')
  self.assertEqual(caps.swimming(self.a,6),5);self.assertEqual(caps.breath_grace(self.a,'water'),240)
  self.dilettante('edge/기본-무술','feat/팔방미인',rank=3)
  self.assertIn('move/바위깨기',self.a.moves);self.restore()

 def test_all_eighteen_general_features_have_actual_acquisition_or_real_non_skill_gate(self):
  for feat in H.GENERAL_FEATURES:
   with self.subTest(feature=feat):
    self.world();self.base()
    if feat=='feat/지휘관의-목소리':
     self.ordinary_skills(athletics=3,intimidate=3)
     for uid in ('feat/민첩성-훈련','feat/잔혹성-훈련'):T.acquire_static(self.e,self.a,uid,acquisition_request_id='actual/'+uid)
    if feat=='feat/응급-처치-전문지식':edge='edge/메딕-훈련'
    else:edge='edge/브리더'
    if feat=='feat/몬스터볼-장인':
     self.ordinary_skills(**{'technology education':5})
     for uid in ('edge/몬스터볼','edge/몬스터볼-수리'):H.grant_qualified_edge(self.e,self.a,uid,None,H.source_id(self.a,uid),H.source_id(self.a,H.CLASS))
    if feat=='feat/종의-학자':
     self.reject(lambda:self.dilettante(edge,feat,options={'selected_species':'피카츄','prerequisite_ids':[self.p.entity_id,self.q.entity_id,self.t.entity_id]}),'Pokemon|family|species|owned')
     from builder import build_pokemon
     from engine import Combatant
     trio=[]
     for i in range(3):
      pet=Combatant(self.rules,build_pokemon(self.rules,'디그다',20,abilities=[],moves=[],extra={'trainer_id':self.a.entity_id}))
      self.e.gm.add_combatant(pet,reason='three actual owned members of the chosen evolution family');trio.append(pet)
     self.reject(lambda:self.dilettante(edge,feat,options={'selected_species':'디그다','prerequisite_ids':[p.entity_id for p in trio]}),'family is unresolved')
     for existing in (self.p,self.q,self.z):existing.spec['species']='피카츄'
     self.dilettante(edge,feat,options={'selected_species':'디그다','prerequisite_ids':[p.entity_id for p in trio]})
     self.assertEqual(A.owned_rule_count(self.a,feat),1)
     for pet in trio:self.assertEqual(pet.stats,{s:v+1 for s,v in pet.spec['stats'].items()})
     self.valid();continue
    options={'moves':list(self.a.moves[:3])} if feat=='feat/개인-지도' else None
    self.dilettante(edge,feat,options=options);self.assertEqual(A.owned_rule_count(self.a,feat),1);self.valid()

 def test_csv_dilettante_ranks_keep_four_real_record_identities(self):
  pairs=[('edge/패기','feat/디펜더'),('edge/브리더','feat/뛰어들기'),('edge/약삭빠름','feat/팔방미인'),('edge/수영-선수','feat/기분전환')]
  for number,(edge,feat) in enumerate(pairs,1):self.assertEqual(self.dilettante(edge,feat,rank=number,edition='local_csv')['snapshot']['source']['record'],97+number)
  self.restore()

 def test_provider_tamper_missing_pair_and_parent_loss_fail_native_validation(self):
  self.dilettante();sid=H.provider(self.a,'edge/패기')[0]
  self.a.spec['state_grants']['sources'][sid]['hobbyist_provider']['substitute']='직감'
  with self.assertRaises(ValueError):T.validate_actor(self.a)
  self.world();self.dilettante();del self.a.spec['state_grants']['sources'][H.source_id(self.a,'edge/패기')]
  with self.assertRaises(ValueError):T.validate_actor(self.a)

 def test_look_all_twelve_actual_qualified_choices_without_original_class(self):
  for child in {**H.SCENE,**H.AP_FEATURES}:
   with self.subTest(child=child):
    self.world();before=self.e.elapsed_seconds;self.learned(child)
    self.assertEqual(self.e.elapsed_seconds,before+60)
    self.assertIsNotNone(H.provider(self.a,child));self.valid()

 def test_look_two_lifetime_categories_not_scene_or_daily_reset(self):
  learned=self.learned('feat/코칭');before=self.e.elapsed_seconds
  self.assertEqual(self.e.look_and_learn(self.a,'feat/코칭',request_id='learn/feat/코칭',seconds=60,reason='actual player learning observed for this printed choice',options={}),learned)
  self.assertEqual(self.e.elapsed_seconds,before)
  self.reject(lambda:self.e.look_and_learn(self.a,'feat/빠른-체조',request_id='same-ap',seconds=60,reason='actual extended study'),'one Scene-list and one AP-list')
  self.e.look_and_learn(self.a,'feat/깡다구',request_id='second-scene-choice',seconds=60,reason='actual second Extended learning')
  self.assertEqual(len(self.a.spec['hobbyist_learning_requests']),2)
  self.e.end_scene();self.reject(lambda:self.e.look_and_learn(self.a,'feat/코칭',request_id='next-scene',seconds=60,reason='actual extended study'),'one Scene-list and one AP-list')
  self.restore()

 def test_look_csv_always_keeps_no_invented_extended_cost(self):
  before=self.e.elapsed_seconds;row=self.learned('feat/코칭',edition='local_csv');self.assertEqual(self.e.elapsed_seconds,before)
  self.assertEqual(row['feature_id'],'feat/코칭');self.restore()

 def test_look_missing_printed_prerequisite_and_duration_are_atomic(self):
  self.feature(H.LOOK)
  self.reject(lambda:self.e.look_and_learn(self.a,'feat/코칭',request_id='no-parent',seconds=60,reason='actual study'),'printed')
  self.reject(lambda:self.e.look_and_learn(self.a,'feat/코칭',request_id='no-duration'),'duration')

 def test_native_coaching_uses_one_ap_free_and_real_bonus_die(self):
  self.learned('feat/코칭');self.p.spec['movement']['power']=6;self.t.spec['movement']['power']=6
  self.e.gm.set_position(self.t,(4,1),reason='actual adjacent maneuver foe');self.begin(self.p)
  AT=__import__('athlete');AT.arm_coaching(self.e,self.a,self.p,branch='opposed',skill='육상');before=AP.available(self.a)
  self.assertTrue(self.e.push(self.p,self.t,challenger_skill='육상',defender_skill='전투',fixed_accuracy=20,challenger_options={'fixed':[6]*7},defender_options={'fixed':[1]*2}))
  self.assertEqual(AP.available(self.a),before-1);self.assertIsNone(AT.armed(self.p));self.valid()

 def test_native_nuanced_real_whole_move_miss_restores_frequency_for_one_ap(self):
  self.learned('feat/뉘앙스-공연');mid=next(uid for uid,row in self.e.r.moves.items() if FREQ.parse(row.get('frequency'))[0]=='scene' and row.get('class') in ('물리','특수') and type(row.get('ac'))is int and '자신' not in row.get('range',''))
  self.e.gm.set_move(self.p,mid,reason='actual learned Scene Move');C=__import__('coordinator');C.arm_nuanced(self.e,self.a,self.p,decision=lambda first:True)
  self.begin(self.p);before=AP.available(self.a)
  with patch.object(Engine,'d20',return_value=1):self.e.use_move(self.p,self.t,mid,set_damage=True)
  self.assertEqual(AP.available(self.a),before-1);self.assertTrue(FREQ.move_allowed(self.e,self.p,mid)[0]);self.valid()

 def test_native_round_trip_uses_completed_move_then_recall_release_one_ap(self):
  self.learned('feat/왕복-여행');self.begin(self.p);row=self.move();before=AP.available(self.a)
  self.action(__import__('juggler').ROUND,completion_id=row['id']);self.assertEqual(AP.available(self.a),before-1);self.assertTrue(self.q.on_field);self.valid()

 def test_native_capture_only_false_strike_catch_combo_not_full_class(self):
  self.world(wild=True)
  self.learned('feat/포획-테크닉');CS=__import__('capture_specialist')
  self.assertEqual(CS.technique(self.a,'거짓 타격'),CS.CORE);self.assertEqual(CS.technique(self.a,'캐치 콤보'),CS.CORE)
  self.assertIsNone(CS.technique(self.a,'커브볼'));self.assertEqual(A.owned_rule_count(self.a,'class/포획전문가'),0)
  self.e.gm.set_hp(self.t,1,reason='actual nearly defeated target');self.begin(self.p)
  CS.arm_knockout(self.e,self.a,self.t,choice='false_strike')
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.p,self.t,'move/물대포',set_damage=True)
  self.assertEqual(self.t.hp,1);self.assertFalse(self.t.fainted)
  self.assertEqual(self.t.spec['capture_knockout_history'][-1]['choice'],'false_strike');self.valid()

 def test_native_catch_combo_uses_actual_owned_pokemon_ko_and_free_inventory_ball(self):
  self.world(wild=True);self.learned('feat/포획-테크닉');CS=__import__('capture_specialist')
  self.inventory(**{'몬스터볼':2});self.e.gm.set_hp(self.t,1,reason='actual nearly defeated wild target');self.begin(self.p)
  CS.arm_knockout(self.e,self.a,self.t,choice='catch_combo',ball_options={'fixed_accuracy':20,'fixed_capture':1})
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.p,self.t,'move/물대포',set_damage=True)
  attempt=self.a.spec['capture_attempts']['capture-'+str(self.a.spec['capture_attempt_serial'])]
  self.assertEqual(self.a.spec['items']['몬스터볼'],1);self.assertEqual(attempt['action'],'free')
  self.assertFalse(attempt['captured']);self.assertTrue(self.t.fainted);self.valid()

 def test_native_staying_power_real_breather_no_retreat_trip_optional_reset(self):
  self.learned('feat/지구력');self.begin(self.p);self.e.change_stage(self.p,'atk',2);self.e.apply_status(self.p,'난동')
  before=self.p.pos
  result=self.e.take_breather(self.p,request_id='staying/native',staying_power={'trainer_id':self.a.entity_id,'reset_stages':False},save_dc=1,save_reason='actual GM permission save policy',save_cost='full',fixed_save=20)
  self.assertTrue(result['completed']);self.assertEqual(self.p.pos,before);self.assertNotIn('넘어짐',self.p.conditions);self.assertEqual(self.p.stages['atk'],2);self.assertNotIn('난동',self.p.conditions)
  self.assertEqual(FREQ.state(self.a)['activations']['feat/지구력']['used'],1);self.valid()

 def test_help_offer_requires_another_known_allied_trainer(self):
  cases=[('party','party',False,True),('party','foe',False,False),
         (None,None,False,False),('party',None,False,False),
         (None,'party',False,False),('party','party',True,False)]
  for helper_side,target_side,self_target,allowed in cases:
   with self.subTest(helper=helper_side,target=target_side,self_target=self_target):
    self.world();self.dilettante('edge/브리더','feat/내가-도와줄게',substitute='일반 지식')
    ally=self.actor('relation-checker','trainer',(2,3),40,skills={'의학':2})
    target=self.a if self_target else ally
    self.a.side,target.side=helper_side,target_side;self.begin(target)
    offer=lambda:self.e.offer_let_me_help(self.a,target,request_id='relation-help',decision=lambda first:True,payment='next',reroll_faces=[6,6])
    if not allowed:
     self.reject(offer,'another allied Trainer')
    else:
     offer();self.assertEqual(self.e.skill_check(target,'의학',15,fixed=[1,1],roll_id='relation-check'),(True,17))
     self.assertEqual(self.a._action_history,['full'])

 def test_help_rechecks_known_alliance_after_offer_before_failed_check(self):
  self.dilettante('edge/브리더','feat/내가-도와줄게',substitute='일반 지식')
  ally=self.actor('changed-relation-checker','trainer',(2,3),40,skills={'의학':2});self.begin(ally)
  self.e.offer_let_me_help(self.a,ally,request_id='relation-help',decision=lambda first:self.fail('unknown ally must not reach decision'),payment='next',reroll_faces=[6,6])
  self.a.side=ally.side=None
  history=list(getattr(self.a,'_action_history',[]))
  with self.assertRaisesRegex(ValueError,'another allied Trainer'):
   self.e.skill_check(ally,'의학',15,fixed=[1,1],roll_id='changed-relation-check')
  self.assertEqual(list(getattr(self.a,'_action_history',[])),history)
  self.assertFalse(__import__('action_resources').pending(self.a))

 def test_help_callback_relation_change_preserves_gm_change_without_reroll(self):
  import skill_feature_actions as HELP,action_resources as RES
  self.dilettante('edge/브리더','feat/내가-도와줄게',substitute='일반 지식')
  ally=self.actor('callback-checker','trainer',(2,3),40,skills={'의학':2});self.begin(ally)
  observed=[]
  def decision(first):
   observed.append(first.total)
   self.e.gm.add_combatant(self.a,side='foes',reason='separately authorized GM relationship change')
   self.assertEqual(self.a.side,'foes')
   return True
  self.e.offer_let_me_help(self.a,ally,request_id='callback-relation',decision=decision,payment='next',reroll_faces=[6,6])
  history=list(getattr(self.a,'_action_history',[]));outcome=None
  try:outcome=self.e.skill_check(ally,'의학',15,fixed=[1,1],roll_id='callback-relation-roll')
  except ValueError:pass
  self.assertEqual(observed,[2],'candidate must reach the real failed-check callback')
  self.assertEqual(self.a.side,'foes','separate authorized GM change must survive')
  self.assertEqual(list(getattr(self.a,'_action_history',[])),history,'stale helper must not pay Full action')
  self.assertFalse(RES.pending(self.a),'stale helper must not acquire next-turn debt')
  self.assertEqual(HELP.event(self.e,ally,'callback-relation-roll').first.total,2)
  if outcome is not None:self.assertEqual(outcome,(False,2),'only the original failed check remains authorized')

 def test_help_callback_skill_loss_preserves_gm_change_without_reroll(self):
  import skill_feature_actions as HELP,action_resources as RES
  self.dilettante('edge/브리더','feat/내가-도와줄게',substitute='일반 지식')
  ally=self.actor('callback-rank-checker','trainer',(2,3),40,skills={'의학':2});self.begin(ally)
  helping_skill=H.direct_skill(self.a,HELP.HELP,'의학');self.assertGreaterEqual(S.effective_rank(self.e.r,self.a,helping_skill),3)
  observed=[]
  def decision(first):
   observed.append(first.total)
   self.e.gm.set_skill(self.a,helping_skill,2,reason='separately authorized permanent skill correction',request_id='callback-skill-loss')
   self.assertEqual(S.effective_rank(self.e.r,self.a,helping_skill),2)
   return True
  self.e.offer_let_me_help(self.a,ally,request_id='callback-rank',decision=decision,payment='next',reroll_faces=[6,6])
  history=list(getattr(self.a,'_action_history',[]));outcome=None
  try:outcome=self.e.skill_check(ally,'의학',15,fixed=[1,1],roll_id='callback-rank-roll')
  except ValueError:pass
  self.assertEqual(observed,[2],'candidate must reach the real failed-check callback')
  self.assertEqual(S.effective_rank(self.e.r,self.a,helping_skill),2,'GM correction must not be rolled back')
  self.assertEqual(list(getattr(self.a,'_action_history',[])),history)
  self.assertFalse(RES.pending(self.a))
  self.assertEqual(HELP.event(self.e,ally,'callback-rank-roll').first.total,2)
  if outcome is not None:self.assertEqual(outcome,(False,2))

 def test_native_help_failed_trainer_check_rerolls_with_rank_and_full_interrupt(self):
  self.dilettante('edge/브리더','feat/내가-도와줄게',substitute='일반 지식')
  ally=self.actor('allied-checker','trainer',(2,3),40,skills={'의학':2});self.begin(ally)
  self.e.offer_let_me_help(self.a,ally,request_id='actual-help',decision=lambda first:first.total<20,payment='next',reroll_faces=[6,6])
  passed,total=self.e.skill_check(ally,'의학',15,fixed=[1,1],roll_id='failed-medical')
  self.assertTrue(passed);self.assertEqual(total,17);self.assertEqual(self.a._action_history,['full']);self.assertEqual(__import__('action_resources').pending(self.a),{'standard':1,'shift':1});self.valid()

 def test_native_slippery_defensive_push_substitutes_without_global_stealth(self):
  self.dilettante('edge/약삭빠름');self.a.spec['movement']['power']=6;self.b.spec['movement']['power']=6
  self.e.gm.set_position(self.b,(2,1),reason='actual adjacent attacker');self.begin(self.b)
  result=self.e.push(self.b,self.a,challenger_skill='육상',defender_skill='은신',fixed_accuracy=20,challenger_options={'fixed':[1]*6},defender_options={'fixed':[6]*4})
  self.assertFalse(result);self.assertEqual(S.rank(self.e.r,self.a,'은신')[2],2);self.valid()

 def test_dabbler_five_real_milestones_retroactive_edge_stat_composition_and_once(self):
  self.world(level=4,gen=5)
  self.e.award_trainer_progression(self.a,kind='experience',amount=460,request_id='actual-all-fifty',reason='actual earned Trainer progression')
  for level,option in ((5,'stats'),(10,'stats'),(20,'edges'),(30,'general_feat'),(40,'stats')):self.milestone(level,option)
  self.simple_base();self.feature(H.DABBLER);before=deepcopy(self.a.stats)
  first=self.e.claim_dabbler_reward(self.a,5,request_id='dab/5',edge='edge/숙련-스킬',choice='의학')
  self.assertEqual(S.rank(self.e.r,self.a,'의학')[2],4)
  self.reject(lambda:self.e.claim_dabbler_reward(self.a,10,request_id='dab/10',edge='edge/기본-무술'),'ordinary printed')
  self.ordinary_skills(**{'combat':3})
  self.e.claim_dabbler_reward(self.a,10,request_id='dab/10',edge='edge/기본-무술')
  self.assertIn('move/바위깨기',self.a.moves)
  self.e.claim_dabbler_reward(self.a,20,request_id='dab/20',stat='atk')
  self.e.claim_dabbler_reward(self.a,30,request_id='dab/30',stat='spa')
  self.e.claim_dabbler_reward(self.a,40,request_id='dab/40',edge='edge/스킬-향상',choice=['일반 지식','통찰'])
  self.assertEqual((self.a.stats['atk'],self.a.stats['spa']),(before['atk']+2,before['spa']+2))
  self.assertEqual(S.modifiers(self.e.r,self.a,'일반 지식',0)['modifier'],2)
  self.assertEqual(self.e.claim_dabbler_reward(self.a,5,request_id='dab/5',edge='edge/숙련-스킬',choice='의학'),first)
  self.reject(lambda:self.e.claim_dabbler_reward(self.a,5,request_id='dab/double',edge='edge/전문-스킬',choice='의학'),'one Dabbler')
  self.reject(lambda:self.e.claim_dabbler_reward(self.a,12,request_id='dab/invented',stat='atk'),'5/10/20/30/40')
  self.assertEqual(len(self.a.spec['hobbyist_dabbler_rewards']),5);self.restore()

 def test_dabbler_current_level_without_observed_choices_grants_nothing(self):
  self.feature(H.DABBLER)
  self.assertNotIn('hobbyist_dabbler_rewards',self.a.spec)
  self.reject(lambda:self.e.claim_dabbler_reward(self.a,5,request_id='unobserved',stat='atk'),'observed and chosen')
  self.world(level=4,gen=5);self.simple_base();self.feature(H.DABBLER)
  self.e.award_trainer_progression(self.a,kind='experience',amount=10,request_id='actual-five',reason='actual advancement')
  self.reject(lambda:self.e.claim_dabbler_reward(self.a,5,request_id='unchosen',edge='edge/기본-무술'),'observed and chosen')
  self.milestone(5,'general_feat');before=self.a.stats['atk']
  self.e.claim_dabbler_reward(self.a,5,request_id='dab/five',stat='atk');self.assertEqual(self.a.stats['atk'],before+2)
  self.a.spec['hobbyist_dabbler_rewards']['dab/five']['result']['delta']=3
  with self.assertRaises(ValueError):T.validate_actor(self.a)

 def test_actual_general_feature_milestone_acquires_hobbyist_class_exception_once(self):
  self.world(level=4);self.e.award_trainer_progression(self.a,kind='experience',amount=10,request_id='observed-five',reason='actual earned level five');self.milestone(5,'general_feat')
  self.reject(lambda:self.e.acquire_milestone_general_feature(self.a,5,'class/운동선수',request_id='wrong-class'),'General Feature')
  edges=[{'id':'edge/기본-스킬','choice':s} for s in ('의학','기술학','오컬트학')]
  result=self.e.acquire_milestone_general_feature(self.a,5,H.CLASS,request_id='milestone/Hobbyist',selection={'edition':'core','edges':edges})
  self.assertEqual(result['feature_id'],H.CLASS);self.assertEqual(A.owned_rule_count(self.a,H.CLASS),1)
  self.assertEqual(S.rank(self.e.r,self.a,'의학')[2],3)
  self.assertEqual(self.e.acquire_milestone_general_feature(self.a,5,H.CLASS,request_id='milestone/Hobbyist',selection={'edition':'core','edges':edges}),result)
  self.reject(lambda:self.e.acquire_milestone_general_feature(self.a,5,'feat/민첩성-훈련',request_id='double-spend'),'already spent');self.restore()

 def test_learning_ledger_and_actual_provider_cannot_be_separated_or_edited(self):
  self.learned('feat/코칭');self.a.spec['hobbyist_learning_requests']['learn/feat/코칭']['request']['feature']='feat/빠른-체조'
  with self.assertRaises(ValueError):T.validate_actor(self.a)
  self.world();self.learned('feat/코칭');self.a.spec.pop('hobbyist_learning_requests')
  with self.assertRaises(ValueError):T.validate_actor(self.a)

 def test_native_critical_moment_uses_actual_training_order_and_scene_two(self):
  self.learned('feat/결정적인-순간');TRAIN=__import__('training_features')
  self.e.train_pokemon(self.a,[(self.p,[TRAIN.AGILITY])],minutes=30,reason='actual single Training regime without Elite Trainer',request_id='actual-critical-training',safe=True)
  self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual audible Order')
  self.assertEqual(A.owned_rule_count(self.a,'class/에이스-트레이너'),0)
  for _ in range(2):
   self.e.start_round(self.e.everyone);before=AP.available(self.a);history=list(self.a._action_history)
   self.e.critical_moment(self.a,[self.p])
   self.assertEqual([TRAIN.bonus(self.p,f) for f in ('movement','initiative','critical','effect')],[3,12,0,0])
   self.assertEqual(AP.available(self.a),before);self.assertEqual(self.a._action_history,history)
   self.assertEqual(__import__('action_resources').pending(self.a),{'standard':1})
   self.e.start_of_turn(self.a,initiative_count=60);self.assertEqual(self.a.budget['standard'],0);self.close()
  self.e.start_round(self.e.everyone)
  self.reject(lambda:self.e.critical_moment(self.a,[self.p]),'frequency')
  self.assertEqual(FREQ.state(self.a)['activations']['feat/결정적인-순간']['used'],2);self.valid()

 def test_native_sleight_uses_pokemon_status_move_in_real_initiative_interrupt(self):
  self.learned('feat/술책');self.e.gm.set_move(self.p,'move/저리가루',reason='actual known Status Move')
  self.e.prepare_initiative_schedule(self.e.everyone,source='gm/hobbyist-actual-sleight-schedule')
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
  trigger={'kind':'turn','actor_id':self.a.entity_id,'serial':self.a.custom_conditions['combat_turn_serial'],'round':self.e.round_no}
  budget=deepcopy(self.a.budget)
  with patch.object(Engine,'d20',return_value=18):result=self.e.sleight(self.a,self.p,move_id='move/저리가루',target=self.t,trigger=trigger)
  self.assertEqual(result['status'],'applied');self.assertIn('마비',self.t.conditions);self.assertEqual(self.a.budget,budget)
  self.assertIs(self.e._active_turn_actor,self.a);self.assertTrue(self.e._initiative_interrupts['loans']);self.valid()

 def test_native_chemical_warfare_bursts_real_pester_ball_without_researcher_class(self):
  self.learned('feat/화학전');self.inventory(**{'item/오물탄-잠듦':2});self.ordinary_skills(**{'acrobatics':4})
  self.e.gm.set_position(self.t,(4,1),reason='actual Pester Ball center');self.e.gm.set_position(self.u,(5,2),reason='actual adjacent secondary target');self.u.on_field=True
  self.begin(self.a);R=__import__('researcher_fields');R.chemical_warfare(self.e,self.a)
  result=self.e.use_item(self.a,'item/오물탄-잠듦',self.t,fixed_accuracy=20)
  self.assertTrue(result['hit'] and result['status_applied']);self.assertIn(self.u.entity_id,[r['target_id'] for r in result['chemical_warfare']])
  self.assertIn('잠듦',self.t.conditions);self.assertIn('잠듦',self.u.conditions);self.assertEqual(A.owned_rule_count(self.a,'class/연구원'),0);self.valid()

 def test_native_mettle_responds_to_actual_massive_hit_and_reduces_attack_stage(self):
  self.learned('feat/깡다구');F.base_patch(self.t,{'stats':dict(self.t.spec['stats'],spa=250)},reason='actual powerful incoming attacker')
  self.e.gm.set_position(self.t,(4,1),reason='actual Water Gun range')
  self.begin(self.t);self.decision('mettle',True)
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.t,self.a,'move/물대포',set_damage=True)
  self.assertEqual(self.t.stages['spa'],-2);self.assertEqual(FREQ.state(self.a)['activations']['feat/깡다구']['used'],1)
  self.assertEqual(self.a._action_history,['extended','free']);self.valid()

 def test_native_hits_the_spot_real_food_trade_in_costs_one_ap_and_grants_temp_hp(self):
  self.learned('feat/이-맛이야');self.inventory(**{'초코바':1})
  meal=self.e.use_item(self.a,'초코바',self.p,duration_minutes=1,duration_reason='actual meal duration')
  self.begin(self.p);self.e.consume_food_buff(self.p,buff_id=meal['buff_id'],action_kind='free',action_reason='actual own Pokemon snack trade-in')
  offers=self.e.pending_class_actor_state_actions(self.a);self.assertEqual(len(offers),1);before=AP.available(self.a)
  result=self.e.resolve_class_actor_state_action(self.a,offers[0]['id'],use=True)
  self.assertEqual(result['temporary_hp_granted'],4);self.assertEqual(self.p.temp_hp,4);self.assertEqual(AP.available(self.a),before-1);self.valid()

 def test_native_style_is_eternal_preserves_real_held_instance_from_theft(self):
  self.learned('feat/스타일은-영원하다');I=__import__('items');HELD=__import__('held_equipment');FA=__import__('fashionista')
  W.register_object(self.e,'hobbyist-claw',location={'kind':'unknown'},reason='actual inspected owned Held Item',kind='item_instance',item_rule_id='item/선제공격손톱',owner_id=self.p.entity_id)
  I.equip_held(self.e,self.p,'item/선제공격손톱',source_instance_id='hobbyist-claw')
  self.e.gm.set_move(self.t,'move/도둑질',reason='actual learned theft Move');self.e.gm.set_position(self.t,(4,1),reason='actual adjacent thief')
  FA.arm_style(self.e,self.a,self.p);self.begin(self.t);before=AP.available(self.a)
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.t,self.p,'move/도둑질',set_damage=True)
  self.assertEqual(HELD.entries(self.p)[0]['instance_id'],'hobbyist-claw');self.assertEqual(HELD.entries(self.t),[])
  self.assertEqual(AP.available(self.a),before-1);self.assertIsNone(FA.armed(self.p));self.valid()

 def test_native_quick_gymnastics_real_hit_costs_one_ap_and_grants_immunity(self):
  self.learned('feat/빠른-체조');self.e.gm.set_position(self.t,(2,1),reason='actual adjacent Trainer attack target')
  self.begin(self.a);before=AP.available(self.a);self.decision('quick_gymnastics',True)
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.a,self.t,'move/몸통박치기',set_damage=True)
  self.assertEqual(AP.available(self.a),before-1);self.assertTrue(__import__('tumbler').immune(self.a));self.assertEqual(self.a._action_history,['standard','free']);self.valid()

 def test_native_instruction_uses_only_its_direct_helping_education_rank(self):
  self.dilettante('edge/설명');ally=self.actor('student','trainer',(2,3),40,skills={'의학':2})
  result=self.e.common_action(ally,mode='skill',skill='의학',dc=6,helper=self.a,helper_skill='의학',fixed=[1,1])
  self.assertTrue(result.check.passed);self.assertEqual(result.check.total,6);self.assertEqual(S.rank(self.e.r,self.a,'의학')[2],2)
  self.valid()

 def test_native_breeder_replaces_exact_check_and_advances_both_real_four_hours(self):
  self.dilettante('edge/브리더')
  first=self.e.pokemon_activity(self.a,'breed',pair=[self.p,self.q],task_id='actual-hobbyist-egg',phase='check',compatible=True,fixed=[3]*4)
  self.assertTrue(first['check'].passed);self.assertEqual(first['check'].total,12);self.assertEqual(self.e.elapsed_seconds,14400)
  result=self.e.pokemon_activity(self.a,'breed',pair=[self.p,self.q],task_id='actual-hobbyist-egg',phase='finish')
  self.assertEqual(self.e.elapsed_seconds,28800);self.assertFalse(result['egg']['hatched']);self.assertEqual(len(self.a.spec['eggs']),1)
  self.assertEqual(S.rank(self.e.r,self.a,'포켓몬학')[2],2);self.valid()

 def test_native_training_beast_groomer_reserves_use_source_local_rank_plans(self):
  self.dilettante('edge/비스트-마스터');TE=__import__('training_eligibility')
  for target in (self.p,self.q):target.spec['species']='디그다'
  for target in (self.p,self.q):__import__('pokemon_progression').observe_xp(self.e,target,total=self.e.r.mech('pokemon/experience-table')['exp_to_reach'][str(target.level)],reason='actual imported cumulative Pokemon XP')
  plan=TE.experience_plan(self.e,self.a,[self.p],use_intimidate=True,safe=True)
  self.assertEqual((plan['target_limit'],plan['xp_rank']),(4,4))
  before=self.p.spec['exp'];row=self.e.pokemon_activity(self.a,'experience_training',targets=[self.p],use_intimidate=True,safe=True)
  self.assertGreater(self.p.spec['exp'],before);self.assertEqual(self.p.spec['exp']-before,row['awards'][0]);self.assertEqual(self.p.spec['experience_training_history'][-1]['xp_rank'],4)
  self.dilettante('edge/예비-훈련','feat/뛰어들기',rank=2)
  plan=TE.experience_plan(self.e,self.a,[self.q],use_reserves=True,safe=True)
  self.assertEqual((plan['target_limit'],plan['xp_rank']),(8,2))
  before=self.q.spec['exp'];row=self.e.pokemon_activity(self.a,'experience_training',targets=[self.q],use_reserves=True,safe=True)
  self.assertEqual(self.q.spec['exp']-before,row['awards'][0]);self.assertEqual(self.q.spec['experience_training_history'][-1]['daily_target_limit'],8)
  self.dilettante('edge/미용사','feat/팔방미인',rank=3)
  for actor in (self.a,self.p,self.q):__import__('downtime').new_day(actor)
  self.inventory(**{'미용사 킷':1});self.e.pokemon_activity(self.a,'groom',targets=[self.p],safe=True)
  plan=TE.experience_plan(self.e,self.a,[self.p],from_grooming=True,bonus_skill='포켓몬학',safe=True)
  self.assertEqual(plan['xp_rank'],4);self.assertEqual(self.p.spec['grooming']['intro_dice'],1)
  before=self.p.spec['exp']
  row=self.e.pokemon_activity(self.a,'experience_training',targets=[self.p],from_grooming=True,bonus_skill='포켓몬학',safe=True)
  self.assertEqual(self.p.spec['exp']-before,row['awards'][0]);self.assertEqual(self.p.spec['experience_training_history'][-1]['xp_rank'],4);self.valid()

 def test_native_pokemaniac_exact_dc_ten_standard_action_uses_replaced_check(self):
  self.dilettante('edge/브리더','feat/포켓몬매니아');self.t.spec['nature']='대담';self.begin(self.a)
  result=self.e.pokemon_activity(self.a,'pokemaniac',target=self.t,fixed=[3]*4)
  self.assertTrue(result['check'].passed);self.assertEqual(result['information']['level'],30)
  self.assertEqual(self.a._action_history,['standard']);self.assertEqual(S.rank(self.e.r,self.a,'포켓몬학')[2],2);self.valid()

 def test_native_first_aid_keeps_tool_daily_target_limit_and_real_recovery(self):
  self.dilettante('edge/메딕-훈련','feat/응급-처치-전문지식');self.inventory(**{'item/응급치료키트':1})
  self.e.gm.set_hp(self.p,10,reason='actual injured patient health');self.e.apply_status(self.p,'독')
  result=self.e.emergency_care_expertise(self.a,self.p)
  self.assertGreater(result['healed'],0);self.assertNotIn('독',self.p.conditions);self.assertTrue(result['tool_retained'])
  self.reject(lambda:self.e.emergency_care_expertise(self.a,self.p),'daily limit');self.valid()

 def test_native_press_real_standard_hp_stage_and_direct_obedience_bonus(self):
  self.dilettante('edge/브리더','feat/압박');self.begin(self.a);before=self.p.hp;TM=__import__('taskmaster')
  TM.press(self.e,self.a,self.p,stats=['atk','spe'],obedience=True)
  self.assertEqual((self.p.stages['atk'],self.p.stages['spe']),(1,1));self.assertEqual(before-self.p.hp,max(1,self.p.base_max_hp//6))
  self.assertEqual(TM.obedience_bonus(self.e,self.a,{'purpose':'pokemon_obedience'},self.p),2)
  self.assertEqual(self.a._action_history,['standard']);self.valid()

 def test_native_skill_monkey_keeps_real_daily_free_reroll_not_skill_prerequisites(self):
  self.dilettante('edge/브리더','feat/팔방미인');self.begin(self.a)
  result=self.e.skill_roll(self.a,'의학',fixed=[1,1],roll_id='actual-monkey',feature='feat/팔방미인',feature_options={'decision':lambda first:True,'reroll_faces':[6,6]})
  self.assertEqual(result.total,14);self.assertEqual(self.a._action_history,['free']);self.assertEqual(FREQ.state(self.a)['activations']['feat/팔방미인']['used'],1);self.valid()

 def test_native_ball_crafter_all_nine_actual_outputs_cost_seven_hundred_and_tool(self):
  self.base();self.ordinary_skills(**{'technology education':3})
  for uid in ('edge/몬스터볼','edge/몬스터볼-수리'):H.grant_qualified_edge(self.e,self.a,uid,None,H.source_id(self.a,uid),H.source_id(self.a,H.CLASS))
  self.ordinary_skills(**{'technology education':2});self.dilettante('edge/브리더','feat/몬스터볼-장인');self.inventory(**{'몬스터볼 공구함':1});self.a.spec['money']=6300
  CA=__import__('crafting_activities')
  source='feat/몬스터볼-장인';effects,header=self.e.r.feat_effects(source)
  changed=deepcopy(self.e.r.feats_mech.get(source,{'coverage':'full','effects':effects or [],'header':header}))
  changed.setdefault('header',{})['frequency']={'action':'free','kind':'at_will','raw':'임의 - 자유 행동'}
  with patch.dict(self.e.r.feats_mech,{source:changed}):
   self.reject(lambda:self.e.pokemon_activity(self.a,'craft_item',item=CA.ADVANCED_BALLS[0],minutes=1,reason='actual changed-header rejection'),'changed Poké Ball Crafter')
  for name in CA.ADVANCED_BALLS:
   result=self.e.pokemon_activity(self.a,'craft_item',item=name,minutes=1,reason='actual GM-specified crafting duration')
   self.assertEqual(result['money_spent'],700);self.assertEqual(self.a.spec['items'][name],1)
  self.assertEqual(self.a.spec['money'],0);self.assertEqual(self.e.elapsed_seconds,540);self.valid()

 def test_native_defender_uses_actual_acquisition_not_legacy_stat_import(self):
  self.dilettante();P=__import__('intercept_profiles');result=P.profile(self.e,self.a,{},'maneuver/근접-가로채기')
  self.assertEqual(result['budget'],{'shift':1});self.assertEqual(result['action'],'shift')
  self.assertEqual(result['modifier_sources'][0]['acquisition']['kind'],'native_feature_acquisition')
  self.assertTrue(P.validate_profile(self.e,self.a,result,historical=False));self.assertNotIn('feature_stat_imports',self.a.spec);self.valid()

 def test_late_second_pair_failure_rolls_back_parent_edge_stat_and_native_registration(self):
  self.base();original=H.after_child
  def fail(*args,**kwargs):original(*args,**kwargs);raise ValueError('actual late paired native consumer failure')
  with patch.object(H,'after_child',side_effect=fail):self.reject(self.dilettante,'late paired native consumer failure')
  self.assertEqual(A.owned_rule_count(self.a,'edge/패기'),0);self.assertEqual(A.owned_rule_count(self.a,H.DILETTANTE),0)
  self.dilettante();self.restore()

 def test_personal_tutor_skill_only_waiver_keeps_three_permanent_known_moves(self):
  self.base();self.ordinary_skills(**{'general education':2})
  self.reject(lambda:self.dilettante('edge/브리더','feat/개인-지도',options={'moves':['move/몸통박치기']*3}),'three|distinct')
  self.dilettante('edge/브리더','feat/개인-지도',options={'moves':list(self.a.moves[:3])})
  row=next(r for r in self.a.spec[T.LEDGER_KEY].values() if r['feature_id']=='feat/개인-지도')
  self.assertEqual(len(row['selection']['values']),3);self.assertEqual(row['qualification']['checks'][1]['state'],'waived');self.restore()

 def test_native_grace_introduction_uses_declared_seven_rank_only_for_this_source(self):
  rank_doc=self.e.r.mech('gameplay/skill-rank-dice');old=deepcopy(rank_doc);self.addCleanup(lambda:(rank_doc.clear(),rank_doc.update(old)))
  rank_doc['by_rank_name']['확장7']={'rank':7,'dice':'7d6','eng':'Declared Seven'}
  self.ordinary_skills(**{'general education':7});self.simple_base();self.dilettante('edge/우아함',substitute='일반 지식')
  CON=__import__('contest');cr=CON.ContestRules(ROOT,ruleset='core+errata');ce=CON.ContestEngine(cr,seed=17)
  ring=cr.mech('contest/type-match')['ring'];skill=next(iter(cr.mech('contest/intro-stage')['skill_to_stat']))
  contestant=ce.contestant_from_combatants(self.e,self.p,self.a,skill,dict.fromkeys(ring,0),intro_stat=ring[-1])
  self.assertEqual(contestant.intro_rank_dice,7)
  with patch.object(CON.ContestEngine,'d6',side_effect=lambda n:[3]*n):ce.intro_stage([contestant],ring[-1])
  self.assertEqual(contestant.stat_dice[ring[-1]],7);self.assertEqual(S.rank(self.e.r,self.a,skill)[2],2)

 def test_help_decline_success_and_non_novice_preserve_native_observation_and_no_cost(self):
  self.dilettante('edge/브리더','feat/내가-도와줄게')
  ally=self.actor('declining-student','trainer',(2,3),40,skills={'의학':2});self.begin(ally);before=AP.available(self.a)
  self.e.offer_let_me_help(self.a,ally,request_id='declined',decision=lambda first:False,payment='next')
  self.assertEqual(self.e.skill_check(ally,'의학',15,fixed=[1,1],roll_id='declined-check'),(False,2));self.assertEqual(AP.available(self.a),before)
  self.e.offer_let_me_help(self.a,ally,request_id='already-successful',decision=lambda first:self.fail('successful check must not offer failed-check use'),payment='next')
  self.assertEqual(self.e.skill_check(ally,'의학',2,fixed=[1,1],roll_id='successful-check'),(True,2));self.assertEqual(AP.available(self.a),before);self.valid()

 def test_ordinary_unwaived_and_forged_provider_do_not_gain_hobbyist_exceptions(self):
  self.reject(lambda:T.acquire_static(self.e,self.a,'feat/디펜더',acquisition_request_id='ordinary-defender'),'printed General Feature skill')
  self.a.spec.setdefault('state_grants',{'version':1,'sources':{}})['sources']['fake-provider']={'kind':'feature','grants':{},'hobbyist_provider':{'child':'edge/패기'}}
  with self.assertRaises(ValueError):H.direct_rank(self.a,'edge/패기','교활')

 def test_u001_declared_seven_plus_stays_explicit_and_source_local(self):
  rank_doc=self.e.r.mech('gameplay/skill-rank-dice');old=deepcopy(rank_doc)
  self.addCleanup(lambda:(rank_doc.clear(),rank_doc.update(old)))
  rank_doc['by_rank_name']['확장7']={'rank':7,'dice':'7d6','eng':'Declared Seven'}
  self.ordinary_skills(**{'general education':7});self.base(edges=[{'id':'edge/기본-스킬','choice':'의학'},{'id':'edge/기본-스킬','choice':'기술학'},{'id':'edge/기본-스킬','choice':'오컬트학'}])
  self.dilettante('edge/패기',substitute='일반 지식');self.assertEqual(H.direct_rank(self.a,'edge/패기','교활'),7)
  self.assertEqual(S.rank(self.e.r,self.a,'교활')[2],2)
  result=self.e.skill_roll(self.a,'일반 지식',fixed=[1]*7);self.assertEqual(result.total,7)


if __name__=='__main__':unittest.main()
