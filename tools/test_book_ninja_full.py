"""Seven native Ninja acquisitions and their actual shared-owner consequences."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import ninja as N,trainer_feature_acquisition as A,state_grants as G,state_codec as CODEC
import world_entities as WORLD,turn as TURN,action_points as AP,frequency as F
import substitute as SUB,illusion_state as I,perception_observe as P,scene_lighting as LIGHT


class NinjaTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
  self.setup()
 def setup(self,stealth=6,combat=3,types=None,money=1000):
  self.e=Engine(self.rules,seed=29672978);self.e.grid=Grid(24,14)
  common=dict(level=30,size='중형',stats={'hp':100,'atk':30,'def':30,'spa':30,'spd':30,'spe':30},
   moves=['move/몸통박치기','move/째려보기','move/용의분노','move/엄청난힘','move/하이퍼보이스','move/위액'],
   abilities=[],types=['노말'],movement={'land':10,'swim':4,'sky':4,'power':4},
   skills={'은신':stealth,'전투':combat,'육상':4,'곡예':4,'집중':4,'오컬트학':4,'직감':4},
   gender='수컷',weight_class=3,weight_kg=30)
  self.a=Combatant(self.rules,dict(deepcopy(common),types=types or ['노말'],name='actual Ninja',kind='trainer',classes=[],feats=[],exp_bank=100,
   money=money,items={item:3 for item in N.TOOLS}))
  self.b=Combatant(self.rules,dict(deepcopy(common),name='actual enemy',kind='trainer',classes=[],feats=[],exp_bank=100,items={item:3 for item in N.TOOLS}))
  self.c=Combatant(self.rules,dict(deepcopy(common),name='actual observer',kind='trainer',classes=[],feats=[],capabilities=['파동 감지']))
  for actor,pos,side in ((self.a,(2,2),'party'),(self.b,(3,2),'enemy'),(self.c,(3,3),'enemy')):
   self.e.gm.add_combatant(actor,pos=pos,side=side,reason='actual native Ninja participant')
   prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='actual body observation')
 def acquire(self,uid=N.CLASS,actor=None,request=None,**kw):
  actor=actor or self.a
  return A.acquire_static(self.e,actor,uid,acquisition_request_id=request or actor.entity_id+'/'+uid,**kw)
 def family(self,uid=N.KINJUTSU,actor=None):
  actor=actor or self.a;parent=N.DEFINITIONS[uid]['parent']
  if parent and not N.acquired(actor,parent):self.family(parent,actor)
  if not N.acquired(actor,uid):self.acquire(uid,actor)
 def combat(self,actor=None):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=30)
 def next(self,actor=None):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_round();self.combat(actor)
 def use(self,actor,target,mid,face=19,**kw):
  with patch.object(Engine,'d20',return_value=face):result=self.e.use_move(actor,target,mid,set_damage=True,**kw)
  rows=[row for row in self.e._move_completions.values() if row['actor'] is actor and row['move_id']==mid]
  self.assertTrue(rows,str(self.e.log_lines[-8:]));self.assertEqual(rows[-1]['phase'],'complete',str(self.e.log_lines[-12:]))
  return result,rows[-1]
 def reject(self,fn,pattern):return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  ids=[a.entity_id for a in (self.a,self.b,self.c)]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.a,self.b,self.c=[WORLD.actor_index(self.e)[uid] for uid in ids]
 def event(self,actor=None):
  actor=actor or self.a
  return [ev['id'] for ev in self.e._passive_events.values() if ev['target'] is actor and ev['producer']=='Engine.use_move'][-1]
 def decoy(self):
  self.family();self.combat();hp=self.a.hp;self.use(self.a,self.a,SUB.SOURCE)
  self.assertEqual(self.a.hp,hp-self.a.max_hp//4);return SUB.live(self.a)[0]
 def hit_listener(self):
  import hex_maniac as H
  self.acquire(H.CLASS,selection={'ability':H.BODY})
 def paid_shift(self,destination):
  import movement_actions as MOVE
  self.assertTrue(TURN.spend(self.e,self.a,'shift','이동',movement=True))
  return MOVE.follow_paid_path(self.e,self.a,[destination],mode='land',maximum_distance=MOVE.distance_budget(self.e,self.a,'land'),action_owner=self.a)
 def drop(self,item='item/연막탄',path=None,**kw):
  self.family(N.UTILITY);self.combat()
  return self.e.utility_drop_shift(self.a,path or [(2,y) for y in range(3,13)],item,**kw)
 def sensory(self,provider='entity',mode='visual'):
  source=__import__('aura_state').SOURCE if provider=='aura' else N.GENJUTSU
  information=('presence',) if provider=='aura' else ('presence','identity','shape')
  return P.observe(self.e,self.c,self.a,P.native(source,[],provider=provider,information=information,mode=mode))

 def test_base_actual_receipt_independent_children_speed_and_two_real_moves(self):
  before=self.a.stats['spe'];self.acquire()
  self.assertEqual(self.a.stats['spe'],before+1);self.assertEqual(set(N.records(self.a)[0]['snapshot']),{'stealth','combat','parents'})
  self.assertTrue({'move/그림자분신','move/독가루'}<=set(self.a.moves));self.assertFalse(N.acquired(self.a,N.ARSENAL))
  self.reject(lambda:self.e.use_genjutsu(self.a,appearance='plain stone'),'acquired')
  self.valid()

 def test_all_seven_separate_receipts_speed_tags_and_kinjutsu_pair_restore(self):
  before=self.a.stats['spe']
  for uid in N.FEATURES:self.family(uid)
  self.assertEqual(len(N.records(self.a,active=True)),7);self.assertEqual(self.a.stats['spe'],before+7)
  self.assertTrue({'move/대타출동','move/맹독'}<=set(self.a.moves));self.assertIn('틈새포착',self.a.abilities)
  __import__('class_move_grants').register_all(self.e,self.a);self.assertEqual(self.a.stats['spe'],before+7)
  self.restore();self.valid();self.assertEqual(self.a.stats['spe'],before+7)

 def test_parent_and_novice_stealth_combat_prerequisites_are_atomic(self):
  self.reject(lambda:self.acquire(N.GENJUTSU),'parent')
  for stealth,combat in ((2,3),(3,2)):
   self.setup(stealth,combat);self.reject(lambda:self.acquire(),'Stealth|Combat|prerequisite')

 def test_child_rank_domains_and_no_csv_choice_or_acquisition_replay_credit(self):
  self.setup(3);self.acquire();self.reject(lambda:self.acquire(N.POISON),'Stealth|prerequisite')
  self.reject(lambda:self.acquire(N.ARSENAL,selection={'moves':['연막']}),'choice|selection|choices')
  self.setup();self.acquire();speed=self.a.stats['spe'];self.acquire();self.assertEqual(self.a.stats['spe'],speed)
  self.setup(5);self.family(N.POISON);self.reject(lambda:self.acquire(N.KINJUTSU),'Stealth|prerequisite')

 def test_arsenal_all_four_100_currency_extended_real_time_and_physical_products(self):
  self.family(N.ARSENAL)
  for number,item in enumerate(('item/해독제',*N.TOOLS)):
   money=self.a.spec['money'];time=self.e.elapsed_seconds
   result=self.e.craft_ninja_tool(self.a,item,event_id='tool/'+str(number),reason='observed five-minute Extended craft',instance_id='ninja-tool-'+str(number),seconds=300)
   self.assertEqual(self.a.spec['money'],money-100);self.assertEqual(self.e.elapsed_seconds,time+300)
   self.assertIsNotNone(result['job_id']);obj=self.e._physical_objects['ninja-tool-'+str(number)]
   self.assertEqual(obj['item_rule_id'],item);self.assertEqual(obj['owner_id'],self.a.entity_id)
  self.valid();self.restore();self.valid()

 def test_arsenal_insufficient_money_short_duration_unprinted_product_are_atomic(self):
  self.setup(money=99);self.family(N.ARSENAL)
  kw=dict(event_id='tool',reason='actual craft observation',instance_id='tool',seconds=300)
  self.reject(lambda:self.e.craft_ninja_tool(self.a,'item/연막탄',**kw),'money|insufficient')
  self.reject(lambda:self.e.craft_ninja_tool(self.a,'item/연막탄',**dict(kw,seconds=0)),'duration|seconds')
  self.reject(lambda:self.e.craft_ninja_tool(self.a,'item/상처약',**kw),'four')

 def test_poison_weapons_native_16_hit_one_ap_free_and_poison_type_choice(self):
  self.family(N.POISON);weapon=TURN.equip_weapon(self.e,self.a,{'name':'actual knife','kind':'소형 근접무기','grade':'조잡','moves':[],'slot':'주요손'})
  self.combat();before=AP.available(self.a)
  with patch.object(Engine,'d20',return_value=16):self.e.use_poison_weapon(self.a,self.b,weapon,weapon_id=weapon,poison_type=True,set_damage=True)
  self.assertIn('독',self.b.conditions);self.assertEqual(AP.available(self.a),before-1);self.assertIn('free',self.a._action_history)
  row=list(self.e._move_completions.values())[-1];self.assertEqual(row['move']['type'],'독');self.valid()

 def test_poison_weapons_15_miss_and_nonweapon_keep_exact_boundaries(self):
  self.family(N.POISON);weapon=TURN.equip_weapon(self.e,self.a,{'name':'actual knife','kind':'소형 근접무기','grade':'조잡','moves':[],'slot':'주요손'})
  self.combat();self.reject(lambda:self.e.use_poison_weapon(self.a,self.b,'move/몸통박치기'),'Weapon|weapon')
  for face in (15,1):
   with patch.object(Engine,'d20',return_value=face):self.e.use_poison_weapon(self.a,self.b,weapon,weapon_id=weapon,set_damage=True)
   self.assertNotIn('독',self.b.conditions);self.assertEqual(list(self.e._move_completions.values())[-1]['move']['type'],'노말');self.next()

 def test_genjutsu_standard_plain_object_and_current_aura_concealment(self):
  self.family(N.GENJUTSU);self.combat();self.e.use_genjutsu(self.a,appearance='ordinary wooden crate')
  self.assertEqual(self.a.budget['standard'],0);self.assertTrue(I.genjutsu_active(self.a))
  visual=self.sensory();self.assertEqual(visual['values']['shape'],'ordinary wooden crate');self.assertIsNone(visual['values']['identity'])
  aura=self.sensory(provider='aura',mode='mental');self.assertEqual(aura['status'],'absent');self.valid();self.restore();self.valid()

 def test_genjutsu_darkness_requires_current_darkness_and_light_changes_visual_only(self):
  self.family(N.GENJUTSU);self.combat();self.reject(lambda:self.e.use_genjutsu(self.a,darkness=True),'darkness')
  LIGHT.configure(self.e,darkness=True,reason='actual dark room');self.e.use_genjutsu(self.a,darkness=True)
  self.assertEqual(self.sensory()['status'],'absent')
  LIGHT.configure(self.e,darkness=False,reason='actual room lights switched on')
  self.assertIn(self.sensory()['status'],('observed','partial'));self.assertEqual(self.sensory(provider='aura',mode='mental')['status'],'absent')

 def test_genjutsu_direct_nonphysical_occult_and_intuition_dc10_plus_rank(self):
  for skill in ('오컬트학','직감'):
   self.setup();self.family(N.GENJUTSU);self.combat();self.e.use_genjutsu(self.a,appearance='ordinary barrel')
   fail=self.e.interact_with_genjutsu(self.c,self.a,skill,interaction='directly address and inspect the apparent object',reason='actual interaction',fixed=[1]*4)
   self.assertEqual(fail['dc'],16);self.assertFalse(fail['success']);self.assertTrue(I.genjutsu_active(self.a))
   success=self.e.interact_with_genjutsu(self.c,self.a,skill,interaction='directly question and examine the apparent object',reason='actual second interaction',fixed=[4]*4)
   self.assertTrue(success['success']);self.assertFalse(I.genjutsu_active(self.a));self.valid()

 def test_genjutsu_any_action_including_actual_shift_breaks_and_wrong_skill_atomic(self):
  self.family(N.GENJUTSU);self.combat();self.e.use_genjutsu(self.a,appearance='ordinary stone')
  self.reject(lambda:self.e.interact_with_genjutsu(self.c,self.a,'은신',interaction='look closely',reason='actual'),'Occult|Intuition')
  self.e.disengage(self.a,(2,3));self.assertFalse(I.genjutsu_active(self.a));self.assertEqual(self.a.pos,(2,3));self.valid()

 def test_utility_smoke_actual_departed_cells_origin_in_arrival_out_eight_cap_one_item(self):
  result=self.drop();self.assertEqual(result['utility_cells'],[[2,y] for y in range(2,10)])
  self.assertEqual(self.a.pos,(2,12));self.assertEqual(self.a.spec['items']['item/연막탄'],2)
  self.assertEqual(set(self.e.zone_cells),{(2,y) for y in range(2,10)});self.assertNotIn((2,12),self.e.zone_cells)
  self.assertEqual(self.a.budget['standard'],1);self.assertEqual(self.a.budget['swift'],0);self.assertEqual(self.a.budget['shift'],0)
  self.assertNotIn('move/연막',self.a.moves);self.assertNotIn('move/연막',self.a.move_uses);self.valid();self.restore();self.valid()
  self.setup();path=[(3,1),(4,2),(5,3),(6,4),(7,5),(8,6),(9,7)]
  result=self.drop(path=path);self.assertEqual(result['utility_cells'],[[2,2],*[list(p) for p in path[:5]]]);self.assertNotIn((8,6),self.e.zone_cells)

 def test_utility_both_caltrops_actual_hazards_single_item_internal_move_frequency(self):
  for item,mid in list(N.TOOLS.items())[1:]:
   self.setup();result=self.drop(item,path=[(2,3),(2,4)])
   cells={tuple(row['cell']) for env in self.e.hazards.values() for row in env['instances']}
   self.assertEqual(cells,{(2,2),(2,3)});self.assertEqual(self.a.spec['items'][item],2)
   self.assertEqual(self.a.move_uses[mid],1);self.assertNotIn(mid,self.a.moves);self.valid()

 def test_utility_blocked_first_step_consumes_no_item_and_partial_stops_at_real_wall(self):
  self.family(N.UTILITY);self.e.grid.blocking.add((2,3));self.combat()
  result=self.e.utility_drop_shift(self.a,[(2,3),(2,4)],'item/연막탄')
  self.assertEqual(result['utility_cells'],[]);self.assertEqual(self.a.spec['items']['item/연막탄'],3)
  self.setup();self.family(N.UTILITY);self.e.grid.blocking.add((2,5));self.combat()
  result=self.e.utility_drop_shift(self.a,[(2,3),(2,4),(2,5),(2,6)],'item/연막탄')
  self.assertEqual(result['utility_cells'],[[2,2],[2,3]]);self.assertEqual(self.a.pos,(2,4));self.assertNotIn((2,4),self.e.zone_cells)

 def test_utility_swim_shift_actual_mode_allowance_not_land(self):
  result=self.drop(path=[(2,y) for y in range(3,9)],mode='swim')
  self.assertEqual(self.a.pos,(2,6));self.assertEqual(result['utility_cells'],[[2,y] for y in range(2,6)]);self.valid()

 def test_utility_only_items_and_free_item_cannot_escape_real_shift_authority(self):
  self.family(N.UTILITY);self.combat()
  self.reject(lambda:self.e.utility_drop_shift(self.a,[(2,3)],'move/연막'),'item|Item')
  self.reject(lambda:self.e.use_item(self.a,'item/마름쇠',free=True,aim=[(2,2)]),'Standard')
  self.reject(lambda:self.e.utility_drop_shift(self.a,[(2,5)],'item/연막탄'),'continuous')

 def test_utility_late_item_failure_rolls_back_path_actions_stock_and_rng(self):
  self.family(N.UTILITY);self.combat()
  with patch('smoke_regions.apply',side_effect=ValueError('actual late smoke failure')):
   self.reject(lambda:self.e.utility_drop_shift(self.a,[(2,3),(2,4)],'item/연막탄'),'late smoke')

 def test_weightless_step_actual_ability_plus_two_stealth_and_blessing_block(self):
  before=self.e.skill_roll(self.a,'은신',fixed=[1]*6).total;self.family(N.STEP)
  self.assertTrue(__import__('ability_transitions').active(self.a,'ability/틈새포착'))
  self.assertEqual(self.e.skill_roll(self.a,'은신',fixed=[1]*6).total,before+2)
  self.assertTrue(__import__('blessing_effects').reaction_blocked(self.e,self.a,self.rules.move('move/몸통박치기')));self.valid()

 def test_weightless_step_no_hazard_entry_trigger_and_suppression_restores_consumer(self):
  self.family(N.STEP);self.combat(self.b)
  self.e.use_item(self.b,'item/마름쇠',aim=[(2,3),(1,3),(1,4),(1,5),(2,5),(3,5),(3,4),(4,4)])
  self.next();hp=self.a.hp;self.paid_shift((2,3));self.assertEqual(self.a.hp,hp)
  self.next(self.b);self.use(self.b,self.a,'move/위액')
  self.assertFalse(__import__('ability_transitions').active(self.a,'ability/틈새포착'))
  self.assertIn('ability/틈새포착',__import__('ability_transitions').known(self.a))
  self.assertFalse(__import__('blessing_effects').reaction_blocked(self.e,self.a,self.rules.move('move/몸통박치기')))
  self.next();self.paid_shift((2,4));self.next();self.paid_shift((2,3));self.assertLess(self.a.hp,hp)

 def test_substitute_quarter_equal_allowed_below_rejected_and_temp_hp_cannot_pay(self):
  self.family();self.e.gm.set_hp(self.a,value=self.a.max_hp//4-1,reason='actual observed previous HP');self.combat()
  self.reject(lambda:self.e.use_move(self.a,self.a,SUB.SOURCE),'quarter')
  self.setup();self.family();maximum=self.a.max_hp;quarter=(maximum+3)//4
  self.e.gm.set_hp(self.a,value=quarter,reason='actual observed quarter HP')
  __import__('temporary_hp').grant(self.e,self.a,50,provenance={'source':'actual earlier temporary HP grant'})
  self.combat();self.use(self.a,self.a,SUB.SOURCE);self.assertEqual(self.a.hp,quarter-maximum//4)
  self.assertEqual(self.a.temp_hp,50)
  self.assertEqual(SUB.live(self.a)[0]['hp'],maximum//4+1)
  # The exact-quarter cost also bypasses an actually acquired HP replacement.
  import test_book_keep_fighting as KF,state_fields as SF,keep_fighting as K
  fixture=KF.KeepFightingTests();fixture.rules=self.rules;fixture.setup(combat=False)
  self.e,self.a,self.b,self.c=fixture.e,fixture.a,fixture.b,fixture.c
  skills=dict(self.a.spec['skills'],은신=6,전투=3)
  SF.base_patch(self.a,{'skills':skills},reason='observed Master Stealth and Novice Combat')
  self.family()
  while self.a.max_hp%4:
   stats=dict(self.a.spec['stats']);stats['hp']+=1
   SF.base_patch(self.a,{'stats':stats},reason='observed HP stat before exact-quarter boundary')
  maximum=self.a.max_hp;self.e.gm.set_hp(self.a,value=maximum//4,reason='actual exact-quarter HP')
  self.e.gm.set_temp_hp(self.a,50,reason='actual earlier temporary HP')
  self.combat();self.use(self.a,self.a,SUB.SOURCE)
  self.assertEqual(self.a.hp,0);self.assertEqual(self.a.temp_hp,50);self.assertEqual(K._uses(self.a),[])

 def test_substitute_actual_attack_status_immunity_breakage_and_normal_next_hit(self):
  row=self.decoy();hp=self.a.hp;self.next(self.b);self.use(self.b,self.a,'move/째려보기')
  self.assertEqual(self.a.stages['def'],0);self.assertEqual(SUB.live(self.a)[0]['hp'],row['hp'])
  self.next(self.b);self.use(self.b,self.a,'move/엄청난힘');self.assertEqual(self.a.hp,hp)
  for _ in range(8):
   if not SUB.live(self.a):break
   self.next(self.b);self.use(self.b,self.a,'move/몸통박치기');self.assertEqual(self.a.hp,hp)
  self.assertFalse(SUB.live(self.a));self.next(self.b);self.use(self.b,self.a,'move/몸통박치기');self.assertLess(self.a.hp,hp);self.valid()

 def test_substitute_fixed_direct_hp_damage_uses_native_effect_and_self_effects_continue(self):
  row=self.decoy();before=row['hp'];hp=self.a.hp;self.next(self.b);self.use(self.b,self.a,'move/용의분노')
  self.assertEqual(SUB.live(self.a)[0]['hp'],before-15);self.assertEqual(self.a.hp,hp)
  self.assertTrue(any('substitute_hp_loss' in receipt for receipt in self.e._effect_dispatch_receipts.values()))
  self.next(self.b);self.use(self.b,self.a,'move/엄청난힘');self.assertEqual(self.b.stages['atk'],-1);self.assertEqual(self.b.stages['def'],-1);self.assertEqual(self.a.hp,hp);self.valid()

 def test_substitute_actual_accuracy_is_hit_but_holder_spite_and_cursed_body_reject(self):
  self.hit_listener()
  self.decoy();self.next(self.b);_,row=self.use(self.b,self.a,'move/몸통박치기')
  event=self.event();self.assertTrue(self.e._passive_events[event]['hit']);self.assertFalse(row['results'][self.a.entity_id]['hit'])
  self.assertTrue(row['results'][self.a.entity_id]['hit_prevented'])
  self.reject(lambda:__import__('spite').trigger(self.e,self.a,event),'Spite|recipient')
  self.reject(lambda:__import__('move_completion').require_hit_return(self.e,event,self.a),'successful|recipient')
  self.valid();self.restore();self.valid()

 def test_substitute_sonic_bypass_hits_holder_and_leaves_decoy(self):
  self.hit_listener();row=self.decoy();before=row['hp'];hp=self.a.hp;self.next(self.b)
  with patch.object(Engine,'d20',return_value=19):self.e.use_move_on(self.b,self.a,'move/하이퍼보이스',self.e.everyone,aim=(2,2),set_damage=True)
  completion=list(self.e._move_completions.values())[-1]
  self.assertLess(self.a.hp,hp);self.assertEqual(SUB.live(self.a)[0]['hp'],before)
  self.assertTrue(completion['results'][self.a.entity_id]['hit']);self.assertTrue(__import__('move_completion').require_hit_return(self.e,self.event(),self.a))

 def test_weightless_step_substitute_bypass_uses_actual_attacker_identity(self):
  row=self.decoy();self.family(N.STEP,self.b);hp=self.a.hp;self.next(self.b);self.use(self.b,self.a,'move/몸통박치기')
  self.assertLess(self.a.hp,hp);self.assertEqual(SUB.live(self.a)[0]['hp'],row['hp']);self.valid()

 def test_poison_powder_native_powder_immunity_and_range_do_not_borrow_toxic(self):
  self.setup(types=['풀']);self.acquire();self.combat();hp=self.b.hp
  self.use(self.a,self.b,'move/독가루',face=19);self.assertIn('독',self.b.conditions)
  self.setup(types=['풀']);self.acquire();self.combat(self.b);self.acquire(actor=self.b)
  self.use(self.b,self.a,'move/독가루',face=19);self.assertNotIn('독',self.a.conditions)
  self.next(self.b);self.e.gm.set_position(self.a,(15,2),reason='actual beyond range four')
  before=(deepcopy(self.b.budget),deepcopy(self.b.move_uses),list(self.b._action_history),self.e.rng.getstate())
  self.assertEqual(self.e.use_move(self.b,self.a,'move/독가루'),0)
  self.assertEqual((self.b.budget,self.b.move_uses,self.b._action_history,self.e.rng.getstate()),before)
  self.assertNotIn('독',self.a.conditions)

 def test_toxic_never_miss_only_actual_poison_type_user(self):
  for poison in (False,True):
   self.setup(types=['독'] if poison else ['노말']);self.family();self.combat();self.use(self.a,self.b,'move/맹독',face=1)
   self.assertEqual('독' in self.b.conditions,poison)
   self.assertEqual(bool(__import__('condition_instances').records(self.b,'독')),poison)

 def test_utility_real_physical_smoke_ball_consumed_once_over_multiple_departures(self):
  self.family(N.UTILITY)
  WORLD.register_object(self.e,'held-smoke',location={'kind':'unknown'},reason='actual held Smoke Ball',kind='item_instance',item_rule_id='item/연막탄',owner_id=self.a.entity_id)
  __import__('items').equip_held(self.e,self.a,'item/연막탄',source_instance_id='held-smoke')
  self.combat();self.e.utility_drop_shift(self.a,[(2,3),(2,4)],'item/연막탄',held_selection='held-smoke')
  self.assertEqual(set(self.e.zone_cells),{(2,2),(2,3)});self.assertEqual(self.a.spec['items']['item/연막탄'],3)
  self.assertTrue(self.e._physical_objects['held-smoke']['consumed']);self.valid()

 def test_native_retraining_ends_only_weightless_source_speed_and_dynamic_effects(self):
  for uid in (N.ARSENAL,N.GENJUTSU,N.STEP):self.family(uid)
  import trainer_retraining as RETRAIN
  sources={uid:RETRAIN.owned_source(self.e,self.a,uid) for uid in (N.CLASS,N.ARSENAL,N.GENJUTSU,N.STEP)}
  retained={sid:([sources[N.CLASS]] if uid!=N.CLASS else []) for uid,sid in sources.items() if uid!=N.STEP}
  speed=self.a.stats['spe'];self.e.retrain_trainer_source(self.a,N.STEP,request_id='retire-weightless',reason='actual retraining consultation',gm_decision={'allowed':True,'reason':'actual approved retraining'},retained_dependencies=retained)
  self.assertEqual(self.a.stats['spe'],speed-1);self.assertFalse(__import__('ability_transitions').active(self.a,'ability/틈새포착'))
  self.assertTrue(N.acquired(self.a,N.GENJUTSU));self.restore();self.valid()

if __name__=='__main__':unittest.main()
