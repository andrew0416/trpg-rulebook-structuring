"""Full Capture Specialist native source choices and actual event consumers.

Fixture observations create no class, technique, feature, action budget or hit.
Every class/Feature below is acquired through the native receipt producer.
"""
from copy import deepcopy
from pathlib import Path
import sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import native_scenario_fixture as N
import capture_specialist as CS,capture_techniques as CT
import trainer_feature_acquisition as TFA,capture_resolution as CR
import captured_momentum as CM,action_points as AP
import wild_equipment as WILD,condition_recovery as RECOVERY
import state_codec as CODEC,world_entities as W,frequency as F
import pokemon_activities as ACTIVITIES,party_actions as PARTY,items

SKILLS=dict.fromkeys(CT.SKILLS,5)
STATS=dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)
BODY={'size':'소형','offsets':[(0,0)],'reason':'observed actual one-cell body'}

class CaptureSpecialistFullTests(unittest.TestCase):
 def scene(self,techniques=(),*,variants=None,ranks=None,ruleset='core+errata',start=True):
  rows=[{'key':'trainer','kind':'trainer','body':dict(BODY,size='중형'),
   'sheet':{'name':'Capture owner','level':20,'stats':STATS,'skills':SKILLS,'moves':[],'abilities':[],
    'pos':(2,2),'items':{'몬스터볼':12},'extra':{'id':'trainer/full-capture','classes':[],'feats':[],'edges':[],'exp_bank':50}}},
   {'key':'wild','kind':'pokemon','body':BODY,'sheet':{'species':'Pikachu','name':'Wild target','level':20,
    'moves':['move/몸통박치기'],'abilities':[],'pos':(3,2),'wild':True,'side':'wild','extra':{'evolutions_remaining':1}}},
   {'key':'pet','kind':'pokemon','body':BODY,'sheet':{'species':'Magikarp','name':'Owned partner','level':30,
    'moves':['move/스피드스타'],'abilities':[],'pos':(2,3),'side':'party','extra':{'trainer_id':'trainer/full-capture'}}}]
  e,p=N.prepare_scene(str(ROOT),actors=rows,grid={'width':20,'height':15},seed=375,ruleset=ruleset)
  a,t,pet=p['trainer'],p['wild'],p['pet']
  variants=variants or {};selected=list(techniques)
  defaults=['작업 도구','커브볼','약화 투척','빠른 투구','덫','캐치 콤보','거짓 타격','끝없는 추격']
  for name in defaults:
   if name not in selected:selected.append(name)
  count=max(1,(len(techniques)+1)//2) if ranks is None else ranks+1
  for rank in range(count):
   pair=[{'technique':name,**({'source_variant':variants[name]} if name in variants else {})} for name in selected[rank*2:rank*2+2]]
   CT.acquire(e,a,CT.CLASS if rank==0 else CT.ADVANCED,acquisition_request_id='full/capture/'+str(rank),
    selected_techniques=pair,rank=rank,lifecycle_policy=TFA.LIFECYCLE_WHILE_OWNED)
  if start:self.start(e,a)
  return e,a,t,pet

 def start(self,e,a):
  e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)

 def next_turn(self,e,a):
  e.end_of_turn(e._active_turn_actor);e.end_round();e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)

 def acquire_feature(self,e,a,feature,variant):
  return TFA.acquire_static(e,a,feature,acquisition_request_id='full/'+feature,
   selection={'source_variant':variant})

 def throw(self,e,a,t,**kw):
  return e.throw_ball(a,t,fixed_accuracy=kw.pop('fixed_accuracy',20),fixed_capture=kw.pop('fixed_capture',20),**kw)

 def attempt(self,a):return a.spec['capture_attempts']['capture-'+str(a.spec['capture_attempt_serial'])]

 def real_ball(self,e,a,uid='real-ball'):
  import missed_ball_body as B
  return N.prepare_object(e,uid,kind='item_instance',item_rule_id=B.ball_rule(e,'몬스터볼'),owner_id=a.entity_id,
   location=W.location_of(a),reason='observed distinct possessed physical ball')

 def tool(self,e,a,kind):
  obj=N.prepare_object(e,'capture-tool',owner_id=a.entity_id,location=W.location_of(a),reason='actual two-handed capture tool')
  CS.observe_tool(e,a,obj['id'],tool=kind,reason='observed actual tool in both free hands',
   **({'hp':50} if kind in ('hand_net','weighted_net') else {'shots':3} if kind=='glue_cannon' else {}))
  return obj['id']

 def test_source_choices_replay_tamper_and_actual_receipts(self):
  e,a,t,_=self.scene(('커브볼','약화 투척'),variants={'커브볼':CS.CSV,'약화 투척':CS.CSV})
  self.assertEqual(CS.technique(a,'커브볼'),CS.CSV)
  self.assertEqual(CS.technique(a,'약화 투척'),CS.CSV)
  self.assertTrue(e.validate_state()['valid'])
  changed=a.spec[TFA.LEDGER_KEY]['full/capture/0']['selection']['proofs'][0]['choice']
  changed['source_variant']='invented'
  with self.assertRaises(ValueError):CS.technique(a,'커브볼')
  with self.assertRaises(CODEC.StateCodecError):e.export_state()

 def test_core_capture_p214_examples_and_exclusive_hp_bands(self):
  e,a,t,_=self.scene(('작업 도구','덫'))
  def observe(level,hp_fraction,evolutions,**extra):
   e.gm.set_level(t,level,reason='actual source example level')
   t.spec.update(dict(evolutions_remaining=evolutions,shiny=False,legendary=False));t.spec.update(extra)
   e.gm.set_hp(t,1 if hp_fraction==1 else max(2,int(t.base_max_hp*hp_fraction)),reason='actual source example health')
  observe(10,.7,1);e.apply_status(t,'혼란',source='gm/source-example',applied_by=a)
  self.assertEqual(CR.rate(e,t,source_variant=CS.CORE)[0],70)
  e.cure_status(t,'혼란')
  observe(30,.4,2,shiny=True);e.gm.set_injuries(t,1,reason='source Caterpie example injury')
  self.assertEqual(CR.rate(e,t,source_variant=CS.CORE)[0],45)
  observe(80,1,0);e.apply_status(t,'화상',source='gm/source-example',applied_by=a);e.apply_status(t,'독',source='gm/source-example',applied_by=a)
  self.assertEqual(CR.rate(e,t,source_variant=CS.CORE)[0],-15)
  e,a,t,_=self.scene();e.gm.set_level(t,10,reason='actual HP-band example level')
  maximum=t.base_max_hp
  for hp,expected in ((maximum,50),(maximum*3//4,65),(maximum//2,80),(maximum//4,95),(1,110)):
   e.gm.set_hp(t,hp,reason='actual observed mutually exclusive HP band')
   self.assertEqual(CR.rate(e,t,source_variant=CS.CORE)[0],expected)

 def test_core_die_trainer_crit_ball_modifier_automatic100_and_zero_hp_admission(self):
  e,a,t,_=self.scene(('작업 도구','덫'))
  self.assertTrue(self.throw(e,a,t,capture_source=CS.CORE,fixed_capture=100))
  row=self.attempt(a);self.assertEqual(row['resolution']['sides'],100)
  self.assertTrue(row['resolution']['automatic']);self.assertEqual(row['resolution']['modifiers']['trainer'],-20)
  self.assertEqual(row['resolution']['modifiers']['accuracy_natural20'],-10)
  e,a,t,_=self.scene();e.gm.set_hp(t,0,reason='actual fainted wild target')
  before=a.spec['items']['몬스터볼'];self.assertFalse(self.throw(e,a,t,capture_source=CS.CORE,fixed_capture=100))
  self.assertEqual(a.spec['items']['몬스터볼'],before)
  for source,expected in ((CS.CORE,-15),(CS.SEPT,3)):
   procedure,_=CR.bind_native(e.r,source)
   self.assertEqual(CR.ball_modifier(e,'하이퍼볼',a,t,procedure)[0],expected)

 def test_csv_momentum_exact_fixed_two_on_next_real_capture_only_once(self):
  e,a,t,_=self.scene(ranks=2)
  self.acquire_feature(e,a,CM.FEATURE,CS.CSV)
  self.assertTrue(self.throw(e,a,t));e.choose_captured_momentum(a,attempt_id='capture-1',choice='capture')
  row=CM.live(a)[0];self.assertEqual(row['effect']['amount'],2)
  self.assertEqual(row['effect']['capture_plan']['basis']['kind'],'csv_fixed')
  self.next_turn(e,a)
  from builder import build_pokemon
  from engine import Combatant
  q=Combatant(e.r,build_pokemon(e.r,'Pikachu',20,name='second wild',moves=[],abilities=[],wild=True,side='wild',pos=(3,3),extra={'size':'소형','evolutions_remaining':1}))
  e.gm.add_combatant(q);N.prepare_body(e,q,**BODY)
  self.throw(e,a,q,fixed_capture=1)
  self.assertEqual(self.attempt(a)['resolution']['modifiers']['captured_momentum'],2)
  self.assertFalse(CM.live(a));self.assertEqual(len(CM.history(a)[-1]['applications']),1)

 def test_momentum_core_original_and_csv_procedure_rejection_are_atomic(self):
  for variant,source,expected in ((CS.CORE,CS.CORE,-5),(CS.CSV,None,2)):
   e,a,t,_=self.scene(ranks=2);self.acquire_feature(e,a,CM.FEATURE,variant)
   self.assertTrue(self.throw(e,a,t,capture_source=source,fixed_capture=100 if source else 20))
   if variant==CS.CSV:
    N.assert_rejected_unchanged(e,lambda:e.choose_captured_momentum(a,attempt_id='capture-1',choice='capture',capture_source=CS.CORE),reason_pattern='fixed')
   e.choose_captured_momentum(a,attempt_id='capture-1',choice='capture',capture_source=source)
   self.assertEqual(CM.live(a)[0]['effect']['amount'],expected)
   self.assertTrue(e.validate_state()['valid'])

 def test_curve_optional_hit_miss_damage_before_capture_and_physical_identity(self):
  for curve,accuracy in ((True,20),(False,20),(True,1)):
   e,a,t,_=self.scene(('커브볼','덫'),variants={'커브볼':CS.CSV})
   ball=self.real_ball(e,a);before=t.hp
   self.throw(e,a,t,curve_ball=curve,fixed_accuracy=accuracy,fixed_capture=1,physical_instance_id=ball['id'])
   row=self.attempt(a);self.assertEqual(row['physical_instance_id'],ball['id'])
   self.assertEqual('curve_damage' in row,curve and accuracy==20)
   if curve and accuracy==20:
    self.assertLess(t.hp,before);self.assertEqual(row['curve_damage']['applications'],1)
    self.assertEqual(row['capture_dc'],e.capture_rate(t)[0])
   else:self.assertEqual(t.hp,before)

 def test_suppression_case_single_electric_damage_and_shared_csv_turn_quota(self):
  e,a,t,_=self.scene(('커브볼','작업 도구'),variants={'커브볼':CS.CSV})
  ball=self.real_ball(e,a)
  case_id=next(uid for uid,r in e.r.items_mech.items() if '제압' in r.get('name',''))
  case=N.prepare_object(e,'case',kind='item_instance',item_rule_id=case_id,owner_id=a.entity_id,location=W.location_of(a),reason='actual Suppression Case')
  CS.attach_case(e,a,case['id'],ball['id'],reason='actual case attached to selected ball')
  self.throw(e,a,t,curve_ball=True,suppression_case=case['id'],physical_instance_id=ball['id'],fixed_capture=1)
  damage=self.attempt(a)['curve_damage'];self.assertEqual(damage['type'],'전기')
  self.assertEqual(damage['applications'],1);self.assertGreaterEqual(damage['technical_bonus'],2)
  N.assert_rejected_unchanged(e,lambda:CS.ball_plan(e,a,curve_ball=True),reason_pattern='frequency exhausted')

 def test_curve_source_static_vs_csv_standard_gate_and_release_damage_before_send(self):
  e,a,t,pet=self.scene(('커브볼','작업 도구'),variants={'커브볼':CS.CSV},start=False)
  PARTY.configure(e,a,battle_mode='full_contact',reason='actual combat policy')
  e.gm.recall(pet,reason='actual contained owned Pokemon')
  ball=self.real_ball(e,a);CS.observe_release_ball(e,a,pet,ball['id'],reason='observed actual containing ball')
  self.start(e,a);before=t.hp
  result=PARTY.act(e,a,send=[(pet,(4,2))],request_id='release-ball',reason='actual release throw',
   release_throw={'ball_id':ball['id'],'target_id':t.entity_id,'curve_ball':True,'fixed_accuracy':20})
  self.assertEqual(result['payment']['kind'],'standard');self.assertTrue(pet.on_field)
  self.assertLess(t.hp,before);self.assertEqual(result['release_throw']['function_order'],['accuracy','damage','release'])
  snapshot=(t.hp,dict(a.budget),e.rng.getstate())
  replay=PARTY.act(e,a,send=[(pet,(4,2))],request_id='release-ball',reason='actual release throw',
   release_throw={'ball_id':ball['id'],'target_id':t.entity_id,'curve_ball':True,'fixed_accuracy':20})
  self.assertEqual(replay,result);self.assertEqual((t.hp,dict(a.budget),e.rng.getstate()),snapshot)
  e,a,t,_=self.scene(('커브볼','덫'),variants={'커브볼':CS.CSV})
  N.assert_rejected_unchanged(e,lambda:CS.ball_plan(e,a,curve_ball=True,standard=False),reason_pattern='Standard')
  e,a,t,_=self.scene(('커브볼','덫'))
  self.assertIsNone(CS.ball_plan(e,a,curve_ball=True,standard=False)['quota'])

 def escaped(self,choice,**options):
  e,a,t,_=self.scene(('약화 투척','작업 도구'),variants={'약화 투척':CS.CSV})
  self.assertFalse(self.throw(e,a,t,fixed_capture=1));before=AP.available(a)
  result=e.devitalizing_throw(a,attempt_id='capture-1',choice=choice,**options)
  self.assertEqual(AP.available(a),before-1);self.assertEqual(result['state'],'used')
  return e,a,t

 def test_devitalizing_three_alternatives_actual_escape_payment_and_once(self):
  for choice in ('slowed','stat','save'):
   e,a,t=self.escaped(choice,**({'stat':'def'} if choice=='stat' else {}))
   if choice=='slowed':self.assertIn('둔화',t.conditions);self.assertEqual(t.stages['def'],0)
   if choice=='stat':self.assertEqual(t.stages['def'],-1);self.assertNotIn('둔화',t.conditions)
   if choice=='save':
    first=RECOVERY.saving_check(e,t,None,10,fixed=12)
    second=RECOVERY.saving_check(e,t,None,10,fixed=12)
    self.assertFalse(first['passed']);self.assertEqual(first['capture_penalty'],-3)
    self.assertTrue(second['passed']);self.assertNotIn('capture_penalty',second)
   N.assert_rejected_unchanged(e,lambda:e.devitalizing_throw(a,attempt_id='capture-1',choice='slowed'),reason_pattern='actual current escape')

 def test_devitalizing_missing_stale_success_miss_and_choice_reject_before_cost(self):
  for accuracy,capture in ((1,1),(20,20)):
   e,a,t,_=self.scene(('약화 투척','작업 도구'),variants={'약화 투척':CS.CSV})
   self.throw(e,a,t,fixed_accuracy=accuracy,fixed_capture=capture)
   N.assert_rejected_unchanged(e,lambda:e.devitalizing_throw(a,attempt_id='capture-1',choice='slowed'),reason_pattern='actual current escape')
  e,a,t,_=self.scene(('약화 투척','작업 도구'))
  self.throw(e,a,t,fixed_capture=1)
  N.assert_rejected_unchanged(e,lambda:e.devitalizing_throw(a,attempt_id='capture-1',choice='stat'),reason_pattern='exactly one')
  self.next_turn(e,a)
  N.assert_rejected_unchanged(e,lambda:e.devitalizing_throw(a,attempt_id='capture-1',choice='slowed'),reason_pattern='actual current escape')

 def test_next_save_overlap_requires_explicit_composition_and_native_restore(self):
  e,a,t=self.escaped('save');self.next_turn(e,a)
  self.throw(e,a,t,fixed_capture=1)
  N.assert_rejected_unchanged(e,lambda:e.devitalizing_throw(a,attempt_id='capture-2',choice='save'),reason_pattern='explicit GM')
  e.devitalizing_throw(a,attempt_id='capture-2',choice='save',composition={'mode':'add','reason':'GM adds concurrent next Save penalties'})
  restored=CODEC.load_engine(e.r,e.export_state())
  target=W.actor_index(restored)[t.entity_id]
  self.assertEqual(RECOVERY.saving_check(restored,target,None,10,fixed=15)['capture_penalty'],-6)

 def test_gotta_core_daily_swift_d100_and_one_does_not_become100(self):
  for natural,changed in ((1,10),(10,1),(29,92),(100,100)):
   e,a,t,_=self.scene(ranks=3);self.acquire_feature(e,a,CS.GOTTA,CS.CORE)
   before=a.budget['swift'];self.throw(e,a,t,capture_source=CS.CORE,fixed_capture=natural,gotta_swap=True)
   row=self.attempt(a);self.assertEqual(row['capture_natural'],changed)
   self.assertEqual(a.budget['swift'],before-1)
   self.assertEqual(row['resolution']['automatic'],natural==100)
  e,a,t,_=self.scene(ranks=3);self.acquire_feature(e,a,CS.GOTTA,CS.CORE)
  for number in range(3):
   if number:self.next_turn(e,a);t=self.add_wild(e,'Pikachu','daily-'+str(number))
   self.assertTrue(self.throw(e,a,t,capture_source=CS.CORE,fixed_capture=100,gotta_swap=True))
  self.next_turn(e,a);t=self.add_wild(e,'Pikachu','daily-exhausted')
  N.assert_rejected_unchanged(e,lambda:self.throw(e,a,t,capture_source=CS.CORE,fixed_capture=100,gotta_swap=True),reason_pattern='frequency exhausted')

 def test_gotta_csv_inversion_always_three_scene_free_face_one(self):
  for natural,changed in ((1,1),(2,19),(10,11),(19,2)):
   e,a,t,_=self.scene(ranks=3);self.acquire_feature(e,a,CS.GOTTA,CS.CSV)
   swift=a.budget['swift'];self.throw(e,a,t,fixed_capture=natural,gotta_swap=True)
   row=self.attempt(a);self.assertEqual(row['capture_natural'],changed)
   self.assertEqual(row['resolution']['modifiers']['gotta'],3);self.assertEqual(a.budget['swift'],swift)
   N.assert_rejected_unchanged(e,lambda:CS.gotta_preflight(e,a,CR.bind_native(e.r)[0],True),reason_pattern='frequency exhausted')

 def test_official_collector_actual_acquisition_current_family_and_stack_choice(self):
  e,a,t,_=self.scene(ranks=3);self.acquire_feature(e,a,CS.GOTTA,CS.SEPT)
  self.assertTrue(ACTIVITIES.collector_eligible(e,a,True))
  self.assertTrue(self.throw(e,a,t,capture_source=CS.SEPT))
  self.assertEqual(a.spec['collector_stacks'],1)
  same_family=self.add_wild(e,'Pikachu','current-family-target',(4,2))
  self.assertFalse(ACTIVITIES.collector_new_family(e,a,same_family))
  self.assertEqual(ACTIVITIES.collector_choice({'kind':'bonus','stacks':1},1),{'kind':'bonus','cost':1})
  N.assert_rejected_unchanged(e,lambda:ACTIVITIES.collector_choice({'kind':'reroll'},1),reason_pattern='insufficient')
  e,a,t,_=self.scene(ranks=3);self.acquire_feature(e,a,CS.GOTTA,CS.CSV)
  N.assert_rejected_unchanged(e,lambda:ACTIVITIES.collector_eligible(e,a,True),reason_pattern='official September')

 def add_wild(self,e,species,name,pos=(3,3)):
  from builder import build_pokemon
  from engine import Combatant
  p=Combatant(e.r,build_pokemon(e.r,species,20,name=name,moves=[],abilities=[],wild=True,side='wild',pos=pos,
   extra={'size':'소형','evolutions_remaining':0}))
  e.gm.add_combatant(p);N.prepare_body(e,p,**BODY)
  return p

 def test_collector_actual_three_earned_stacks_bonus_or_complete_reroll(self):
  for choice in ({'kind':'bonus','stacks':3},{'kind':'reroll'}):
   e,a,t,_=self.scene(ranks=3);self.acquire_feature(e,a,CS.GOTTA,CS.SEPT)
   for number,species in enumerate(('Pikachu','Machop','Geodude')):
    target=t if number==0 else self.add_wild(e,species,'earned-'+str(number))
    if number:self.next_turn(e,a)
    self.assertTrue(self.throw(e,a,target,capture_source=CS.SEPT))
   self.assertEqual(a.spec['collector_stacks'],3)
   self.next_turn(e,a);target=self.add_wild(e,'Pikachu','same-family',(4,2))
   self.throw(e,a,target,capture_source=CS.SEPT,fixed_capture=1,collector_choice=choice,
    **({'fixed_reroll':20} if choice['kind']=='reroll' else {}))
   row=self.attempt(a);self.assertEqual(row['collector']['spent'],3);self.assertEqual(a.spec['collector_stacks'],0)
   self.assertEqual(row['capture_natural'],20 if choice['kind']=='reroll' else 1)
   self.assertEqual(row['collector']['bonus'],0 if choice['kind']=='reroll' else 3)

 def test_may_tools_loaded_cap_cannon_uses_same_real_projectile(self):
  import csv_item_physical_contracts as P
  for variant,expected in ((CS.MAY,2),(CS.CSV,0)):
   e,a,t,_=self.scene(('작업 도구','덫'),variants={'작업 도구':variant})
   cannon=N.prepare_object(e,'cannon',kind='item_instance',item_rule_id='item/몬스터볼-캐논',owner_id=a.entity_id,
    location=W.location_of(a),reason='actual owned Cannon')
   items.register_item(e,a,'item/몬스터볼-캐논',source_instance_id=cannon['id'],as_held=False)
   ball=self.real_ball(e,a);P.load_cannon(e,a,cannon['id'],ball['id'])
   self.throw(e,a,t,cannon_instance_id=cannon['id'],fixed_capture=1)
   row=self.attempt(a);self.assertEqual(row['physical_instance_id'],ball['id'])
   self.assertEqual(row['tools_accuracy'],expected)
   self.assertIsNone(e._physical_objects[cannon['id']][P.OBJECT_STATE]['loaded_ball_instance_id'])

 def test_tools_actual_hand_net_weighted_net_glue_and_lasso_source_paths(self):
  for kind in ('hand_net','weighted_net','glue_cannon','lasso'):
   e,a,t,_=self.scene(('작업 도구','덫'),variants={'작업 도구':CS.CSV,'덫':CS.CSV})
   uid=self.tool(e,a,kind)
   if kind=='lasso':CS.observe_lasso(e,a,t,uid,reason='actual target already physically lassoed')
   else:
    event=e.use_capture_tool(a,t,uid,fixed_accuracy=20,**({'aim':{'reachable':True,'reason':'observed actual reachable throw'}} if kind!='hand_net' else {}))
    self.assertTrue(event['hit'])
    if kind=='glue_cannon':self.assertIn('구속',t.conditions);self.assertIn('수렁',t.conditions)
   self.assertTrue(CS.snared(e,a,t))
   self.assertEqual(WILD.snare_bonus(e,a,t,source_variant=CS.CORE),-10)
   self.assertEqual(CS.tools_accuracy(e,a,kind),2)
   if kind in ('hand_net','weighted_net'):self.assertEqual(CS.net_modifier(e,t,CR.bind_native(e.r,CS.CORE)[0]),-20)
   self.assertTrue(e.validate_state()['valid'])

 def test_tools_reach_empty_hands_missing_source_and_snare_conversion_boundaries(self):
  e,a,t,_=self.scene(('작업 도구','덫'),variants={'덫':CS.SEPT})
  uid=self.tool(e,a,'weighted_net')
  N.assert_rejected_unchanged(e,lambda:e.use_capture_tool(a,t,uid,fixed_accuracy=20),reason_pattern='no metric range')
  self.assertEqual(WILD.snare_bonus(e,a,t,source_variant=CS.CORE),0)
  e.use_capture_tool(a,t,uid,fixed_accuracy=20,aim={'reachable':True,'reason':'actual throw reach'})
  self.assertEqual(WILD.snare_bonus(e,a,t,source_variant=CS.SEPT),2)
  e,a,t,_=self.scene(('작업 도구','덫'),variants={'작업 도구':CS.MAY})
  self.assertEqual(CS.tools_accuracy(e,a,'cap_cannon'),2)
  e,a,t,_=self.scene(('작업 도구','덫'),variants={'작업 도구':CS.CSV})
  self.assertEqual(CS.tools_accuracy(e,a,'cap_cannon'),0)

 def test_catch_combo_native_owned_pokemon_ko_free_ball_hp1_rate_failure_retains_faint(self):
  for face in (1,20):
   e,a,t,pet=self.scene(('캐치 콤보','작업 도구'),variants={'캐치 콤보':CS.CSV},start=False)
   e.gm.set_hp(t,1,reason='observed weak wild target')
   e.gm.observe_loyalty(pet,3,reason='GM observes actual cooperative current-owner relationship before command')
   self.start(e,pet)
   CS.arm_knockout(e,a,t,choice='catch_combo',ball_options={'fixed_accuracy':20,'fixed_capture':face})
   balls=a.spec['items']['몬스터볼']
   e.use_move(pet,t,'move/스피드스타',set_damage=True)
   row=self.attempt(a);self.assertEqual(a.spec['items']['몬스터볼'],balls-1)
   self.assertEqual(row['action'],'free');self.assertLessEqual(t.hp,0)
   self.assertEqual(row['capture_dc'],CR.rate(e,t,hp=1)[0]);self.assertEqual(row['captured'],face==20)
   if face==1:self.assertTrue(t.fainted)
   self.assertTrue(e.validate_state()['valid'])

 def test_false_strike_native_ko_replacement_and_isolated_damage_no_trigger(self):
  e,a,t,pet=self.scene(('거짓 타격','작업 도구'),start=False)
  e.gm.observe_loyalty(pet,3,reason='GM observes actual cooperative current-owner relationship before command')
  e.gm.set_hp(t,1,reason='observed weak wild target');self.start(e,pet)
  CS.arm_knockout(e,a,t,choice='false_strike');e.use_move(pet,t,'move/스피드스타',set_damage=True)
  self.assertEqual(t.hp,1);self.assertFalse(t.fainted)
  self.assertEqual(t.spec['capture_knockout_history'][-1]['choice'],'false_strike')
  e,a,t,pet=self.scene(('거짓 타격','작업 도구'),start=False)
  e.gm.set_hp(t,1,reason='observed weak wild target');CS.arm_knockout(e,a,t,choice='false_strike')
  e.take_damage(t,10);self.assertTrue(t.fainted)
  self.assertNotIn('capture_knockout_history',t.spec)

 def test_fast_pitch_current_turn_one_standard_one_ap_one_ball(self):
  e,a,t,_=self.scene(('빠른 투구','작업 도구'))
  before=(AP.available(a),a.budget['standard'],a.spec['items']['몬스터볼'])
  result=e.fast_pitch(a,t,fixed_accuracy=20,fixed_capture=1)
  self.assertIsNone(result['loan'])
  self.assertEqual((AP.available(a),a.budget['standard'],a.spec['items']['몬스터볼']),tuple(v-1 for v in before))

 def test_fast_pitch_actual_between_turn_advanced_borrow_and_future_settlement(self):
  e,a,t,_=self.scene(('빠른 투구','작업 도구'),start=False)
  e.prepare_initiative_schedule(e.everyone,source='gm/capture-scheduled-round')
  e.start_round(e.everyone);before=AP.available(a)
  result=e.fast_pitch(a,t,fixed_accuracy=20,fixed_capture=1)
  self.assertIsNotNone(result['loan']);self.assertEqual(e._active_turn_actor,a)
  self.assertEqual(a.budget['standard'],0);self.assertEqual(AP.available(a),before-1)
  e.finish_initiative_reaction()
  self.assertTrue(e.initiative_reaction_status()['owed_turns'])
  self.assertTrue(e.validate_state()['valid'])

 def flee_scene(self,*,blocked=False):
  import movement_actions as MOVE
  e,a,t,pet=self.scene(('끝없는 추격','작업 도구'),start=False)
  e.gm.set_position(t,(6,2),reason='actual flee origin away from trainer')
  e.gm.set_position(pet,(4,3),reason='actual owned on-field pursuer one land Shift from melee reach')
  e.gm.observe_loyalty(pet,3,reason='GM observes actual cooperative current-owner relationship before command')
  MOVE.set_capabilities(e,t,{'land':4,'swim':0},basis='current',reason_text='observed fastest land flee')
  a.spec['items']['item/실버스프레이']=1
  e.use_item(a,'item/실버스프레이',aim={'reason':'actual sprayed trainer'})
  e.observe_repel_approach(a,t,nearby=True,reason='actual close exposure in this encounter')
  e.observe_relative_directions(t,directions={'away':(1,0)},quickly_trip_placement='before_entry',reason='actual understood retreat direction')
  e.observe_repel_flee(t,movement={'direction':'away','distance':4,'pace':'quickly','movement_id':'real-flee'},reason='actual fastest feasible retreat')
  if blocked:e.apply_status(pet,'구속',source='gm/physical-restraint',applied_by=a)
  self.start(e,t)
  CS.arm_pursuit(e,a,pet,t,set_damage=True)
  return e,a,t,pet

 def test_relentless_actual_flee_shift_struggle_trip_before_departure(self):
  e,a,t,pet=self.flee_scene();before=(AP.available(a),tuple(t.pos),tuple(pet.pos))
  e.rulings.add_situational('accuracy',100,who=pet.name,reason='GM actual favorable Struggle circumstances')
  result=e.resolve_repel_flee(t)
  history=a.spec['capture_pursuit_history'][-1]
  self.assertEqual(AP.available(a),before[0]-2)
  self.assertEqual(history['origin'],before[1]);self.assertNotEqual(tuple(pet.pos),before[2])
  self.assertEqual(history['phase'],'complete')
  self.assertTrue(history['hit']);self.assertIn('넘어짐',t.conditions)
  self.assertEqual(tuple(t.pos),before[1]);self.assertTrue(t.on_field)
  self.assertTrue(e.validate_state()['valid'])

 def test_relentless_native_miss_or_blocked_shift_does_not_trip_or_charge_twice(self):
  for blocked in (False,True):
   e,a,t,pet=self.flee_scene(blocked=blocked);before=AP.available(a)
   e.rulings.add_situational('accuracy',-100,who=pet.name,reason='GM actual very poor Struggle circumstances')
   e.resolve_repel_flee(t)
   self.assertNotIn('넘어짐',t.conditions)
   self.assertEqual(AP.available(a),before if blocked else before-2)
   self.assertEqual(len(a.spec.get('capture_pursuit_history',[])),0 if blocked else 1)

 def test_pursuit_requires_owned_on_field_and_actual_flee_event(self):
  e,a,t,pet=self.scene(('끝없는 추격','작업 도구'))
  N.assert_rejected_unchanged(e,lambda:CS.arm_pursuit(e,a,t,t),reason_pattern='on-field Pokemon')
  CS.arm_pursuit(e,a,pet,t)
  N.assert_rejected_unchanged(e,lambda:CS.before_escape(e,t,t,'item/벌레회피스프레이',kind='repel',request_id='fake-flee'),reason_pattern='actual retained Repel')

 def test_late_relentless_attack_rejection_keeps_actual_shift_and_two_ap(self):
  e,a,t,pet=self.flee_scene();before=(AP.available(a),tuple(pet.pos))
  native_use_move=e.use_move
  def reject_actual_pursuit(*args,**options):
   if getattr(e,'_capture_pursuit',{}).get('phase')=='attack':
    raise ValueError('actual attack permission lost after Shift')
   return native_use_move(*args,**options)
  with patch.object(e,'use_move',side_effect=reject_actual_pursuit):
   e.resolve_repel_flee(t)
  self.assertEqual(AP.available(a),before[0]-2);self.assertNotEqual(tuple(pet.pos),before[1])
  self.assertEqual(a.spec['capture_pursuit_history'][-1]['result'],'rejected_after_payment')
  self.assertNotIn('넘어짐',t.conditions)

 def test_curve_knockout_uses_explicit_false_strike_before_pending_ball_function(self):
  e,a,t,_=self.scene(('커브볼','거짓 타격'))
  e.gm.set_hp(t,1,reason='actual weak wild ball target')
  CS.arm_knockout(e,a,t,choice='false_strike')
  self.throw(e,a,t,curve_ball=True,fixed_capture=1)
  self.assertEqual(self.attempt(a)['curve_damage']['after_hp'],1)
  self.assertIn('resolution',self.attempt(a));self.assertEqual(t.hp,1)
  e,a,t,_=self.scene(('커브볼','거짓 타격'))
  e.gm.set_hp(t,1,reason='actual weak wild target without False Strike choice')
  self.assertFalse(self.throw(e,a,t,capture_source=CS.CORE,curve_ball=True,fixed_capture=100))
  self.assertTrue(t.fainted);self.assertNotIn('resolution',self.attempt(a))

 def test_csv_tools_actual_bait_lure_and_reel_consume_native_checks(self):
  e,a,t,_=self.scene(('작업 도구','덫'),variants={'작업 도구':CS.CSV},start=False)
  a.spec['items'].update({'미끼':1,'대단한낚싯대':1,'루어':1})
  e.pokemon_activity(a,'attract_bait',phase='place',bait_id='actual-bait',
   habitat={'region':'observed local habitat','species':[t.spec['species']],'reason':'actual species encountered here'})
  bait=e.pokemon_activity(a,'attract_bait',phase='wait',bait_id='actual-bait',fixed=11)
  self.assertEqual((bait['checks'][-1]['bonus'],bait['checks'][-1]['total']),(4,15))
  e.pokemon_activity(a,'fishing',phase='start',rod='대단한낚싯대',attachment='루어')
  bite=e.pokemon_activity(a,'fishing',phase='wait',roll_d20=11)
  self.assertEqual((bite['bite_bonus'],bite['bite_total']),(4,15))
  reel=e.pokemon_activity(a,'fishing',phase='reel',target=t,fixed=[1]*5,escape_d20=20)
  self.assertEqual(reel['check'].total,7)
  self.assertEqual(a.spec['items']['루어'],1)

 def test_core_snare_actual_bait_encounter_is_excluded_from_csv_predicate(self):
  for variant,expected in ((CS.CORE,-10),(CS.CSV,0)):
   e,a,t,pet=self.scene(('덫','작업 도구'),variants={'덫':variant},start=False)
   a.spec['items']['미끼']=1;e.gm.set_level(pet,20,reason='actual comparable encounter party')
   options=dict(phase='place',bait_id='actual-bait',habitat={'region':'observed habitat',
    'species':[t.spec['species']],'reason':'actual regional target'})
   e.pokemon_activity(a,'attract_bait',**options)
   e.pokemon_activity(a,'attract_bait',phase='wait',bait_id='actual-bait',fixed=15)
   e.pokemon_activity(a,'attract_bait',phase='select',bait_id='actual-bait')
   e.pokemon_activity(a,'attract_bait',phase='encounter',bait_id='actual-bait',target=t,party=[pet],level_match_reason='actual equal level party')
   self.start(e,a);self.throw(e,a,t,capture_source=CS.CORE,fixed_capture=1)
   self.assertEqual(self.attempt(a)['snare_bonus'],expected)

 def test_lasso_actual_accuracy_uses_tools_and_explicit_gm_procedure(self):
  e,a,t,_=self.scene(('작업 도구','덫'),variants={'작업 도구':CS.CSV})
  uid=self.tool(e,a,'lasso')
  N.assert_rejected_unchanged(e,lambda:e.use_capture_tool(a,t,uid,fixed_accuracy=20),reason_pattern='actual tool reach')
  result=e.use_capture_tool(a,t,uid,fixed_accuracy=20,
   aim={'reachable':True,'ac':6,'reason':'explicit GM Lasso attack procedure; the class prints no AC or metric range'})
  self.assertTrue(result['hit']);self.assertEqual(result['tools_accuracy'],2)
  self.assertTrue(CS.restraints(e,t));self.assertTrue(e.validate_state()['valid'])

if __name__=='__main__':unittest.main()
