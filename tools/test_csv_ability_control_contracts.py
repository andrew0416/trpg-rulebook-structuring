"""Six independent source contracts through native producers and consumers."""
from copy import deepcopy
from pathlib import Path
import csv,hashlib,json,sys,unittest
STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]
import ability_control_contracts as CONTROL
import body_state as BODY
import combat_timing as TIME
import forced_movement as FORCED
import initiative_interrupts as INTERRUPTS
import state_grants as G
import struggle_capabilities as STRUGGLE
import test_category2_ability_native_actions as FIX
from native_scenario_fixture import assert_rejected_unchanged
from engine import Rules,Engine


class CsvAbilityControlTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='all')
 def pokemon(self,*args,**kw):return FIX.AbilityNativeActionTests.pokemon(self,*args,**kw)
 def engine(self,*args,**kw):return FIX.AbilityNativeActionTests.engine(self,*args,**kw)
 def turn(self,*args,**kw):return FIX.AbilityNativeActionTests.turn(self,*args,**kw)
 def valid(self,e):return FIX.AbilityNativeActionTests.valid(self,e)
 def fresh(self,e):
  restored=Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
  self.valid(restored);return restored
 def pair(self,source,*,pos=(5,5),target_pos=(6,5),target_extra=None,moves=()):
  user=self.pokemon('control-user',source,pos=pos,moves=moves)
  target=self.pokemon('control-target',None,pos=target_pos,side='wild',extra=target_extra,moves=('전광석화','몸통박치기'))
  return self.engine(user,target),user,target
 def reject(self,e,fn,pattern):return assert_rejected_unchanged(e,fn,reason_pattern=pattern)

 def test_exact_eight_rows_six_parents_and_copy_registry_share_identity(self):
  with (ROOT/'input/db/abilities.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.reader(f))
  self.assertEqual(hashlib.sha256((ROOT/'input/db/abilities.csv').read_bytes()).hexdigest(),CONTROL.CSV_SHA)
  for uid,n in CONTROL.ROWS.items():
   reg=CONTROL.registration(self.r,uid)
   self.assertEqual(reg['source_id'],uid)
   self.assertEqual(reg['name'],rows[n-1][0])
   self.assertEqual(reg['equivalent_source_ids'][0],CONTROL.COPIES.get(uid,uid))
  ledger=json.loads((ROOT/'data/verification/category2-csv-abilities-moves-status.json').read_text(encoding='utf8'))
  selected=[r for r in ledger['rows'] if r['row_id'] in {'C2CSV-ABILITY-R'+str(n).zfill(4) for n in CONTROL.ROWS.values()}]
  self.assertEqual(sum(r['denominator_contribution'] for r in selected if r['category2_included']),6)

 def test_arena_playtest_native_aura_slows_traps_and_free_end_preserves_independent_slow(self):
  e,u,t=self.pair(CONTROL.ARENA)
  e.apply_status(t,'둔화');self.turn(e,u)
  e.activate_ability(u,CONTROL.ARENA,u)
  self.assertTrue({'둔화','수렁'}<=t.conditions)
  import condition_recovery as RECOVERY
  self.assertFalse(RECOVERY.permits_recall(t))
  e.activate_ability(u,CONTROL.ARENA,(u,{'mode':'end'}))
  self.assertIn('둔화',t.conditions);self.assertNotIn('수렁',t.conditions)
  self.reject(e,lambda:e.activate_ability(u,CONTROL.ARENA,u),'frequency exhausted')
  self.valid(e)

 def test_arena_actual_source_movement_faint_recall_and_suppression_boundaries(self):
  for ending in ('move','faint','recall','suppress'):
   with self.subTest(ending=ending):
    e,u,t=self.pair(CONTROL.ARENA);self.turn(e,u);e.activate_ability(u,CONTROL.ARENA,u)
    if ending=='move':
     FORCED.displace(e,u,t,direction=(1,0),distance=5,source=CONTROL.ARENA)
    elif ending=='faint':
     u.hp=0;e.check_fainted(u)
    elif ending=='recall':e.gm.recall(u,reason='actual aura owner recall')
    else:G.transition(e,u,lambda staged,actual:setattr(actual,'abilities_suppressed',True))
    self.assertNotIn('수렁',t.conditions);self.valid(e)

 def test_arena_immunities_and_both_actual_edition_selections(self):
  cases=[({'types':['비행']},True,True),({'movement':{'land':4,'sky':1}},True,False),
         ({'movement':{'land':4,'levitate':1}},True,False),({'movement':{'land':4,'burrow':4}},True,True),
         ({'movement':{'land':4,'sky':4}},True,True),({'movement':{'land':4,'burrow':3}},False,False)]
  for extra,playtest_immune,core_immune in cases:
   for selected,immune in (('csv-playtest',playtest_immune),('core-1.05',core_immune)):
    with self.subTest(extra=extra,selected=selected):
     e,u,t=self.pair(CONTROL.ARENA,target_extra=extra)
     e.activate_ability(u,CONTROL.ARENA,(u,{'mode':'edition','edition':selected}))
     self.turn(e,u);e.activate_ability(u,CONTROL.ARENA,u)
     self.assertEqual('둔화' in t.conditions,not immune)
     self.assertEqual('수렁' in t.conditions,selected=='csv-playtest' and not immune)
     self.valid(e)

 def test_shadow_actual_forced_movement_stops_at_five_from_original_point(self):
  e,u,t=self.pair(CONTROL.SHADOW);self.turn(e,u);e.activate_ability(u,CONTROL.SHADOW,t)
  row=CONTROL._live(t,'shadow')[0]
  self.assertEqual(row['turn_deadline'],5)
  result=FORCED.displace(e,u,t,direction=(1,0),distance=9,source=CONTROL.SHADOW)
  self.assertEqual(result['moved'],5);self.assertEqual(t.pos,(11,5))
  self.assertFalse(BODY.can_place(e,t,(12,5),origin=t.pos))
  self.assertEqual(row[CONTROL.TAG]['payload']['cell'],[6,5]);self.valid(e)

 def test_shadow_five_real_target_turns_expire_without_curing_independent_status(self):
  e,u,t=self.pair(CONTROL.SHADOW);e.apply_status(t,'둔화');self.turn(e,u);e.activate_ability(u,CONTROL.SHADOW,t);e.end_of_turn(u)
  for number in range(1,6):
   if number>1:e.start_round([u,t])
   e.start_of_turn(t,initiative_count=10);e.end_of_turn(t)
   self.assertEqual('수렁' in t.conditions,number<5)
   if number<5:e.end_round()
  self.assertIn('둔화',t.conditions);self.valid(e)

 def test_shadow_target_validation_rejects_atomically(self):
  e,u,t=self.pair(CONTROL.SHADOW,target_pos=(8,5));self.turn(e,u)
  self.reject(e,lambda:e.activate_ability(u,CONTROL.SHADOW,t),'adjacent')
  self.reject(e,lambda:e.activate_ability(u,CONTROL.SHADOW,u),'adjacent')

 def test_magnet_playtest_choose_two_weight_bound_and_actual_push(self):
  e,u,t=self.pair(CONTROL.MAGNET,target_pos=(8,5),target_extra={'types':['강철'],'weight_class':2})
  self.turn(e,u)
  self.reject(e,lambda:e.activate_ability(u,CONTROL.MAGNET,(t,{'choices':['maximum']})),'exact distinct')
  self.reject(e,lambda:e.activate_ability(u,CONTROL.MAGNET,(t,{'choices':['displace','maximum'],'direction':'away','distance':5})),'weight bound')
  e.activate_ability(u,CONTROL.MAGNET,(t,{'choices':['displace','maximum'],'direction':'away','distance':2}))
  self.assertEqual(t.pos,(10,5));self.assertEqual(u.budget['swift'],0)
  self.assertTrue(BODY.can_place(e,t,(11,5),origin=t.pos));self.assertFalse(BODY.can_place(e,t,(12,5),origin=t.pos))
  self.valid(e)

 def test_magnet_both_edition_distance_and_user_next_turn_expiry(self):
  for selected,limit in (('csv-playtest',6),('core-1.05',8)):
   with self.subTest(selected=selected):
    e,u,t=self.pair(CONTROL.MAGNET,target_pos=(9,5),target_extra={'types':['강철']})
    e.activate_ability(u,CONTROL.MAGNET,(u,{'mode':'edition','edition':selected}));self.turn(e,u)
    e.activate_ability(u,CONTROL.MAGNET,(t,{'choices':['maximum','minimum']}))
    self.assertFalse(BODY.can_place(e,t,(7,5),origin=t.pos));self.assertTrue(BODY.can_place(e,t,(5+limit,5),origin=t.pos))
    self.assertFalse(BODY.can_place(e,t,(6+limit,5),origin=t.pos));e.end_of_turn(u);e.end_round();e.start_round([u,t]);e.start_of_turn(u,initiative_count=20)
    self.assertTrue(CONTROL._live(t,'magnet'));e.end_of_turn(u)
    self.assertFalse(CONTROL._live(t,'magnet'));self.valid(e)

 def test_magnet_rejects_nonsteel_range_invalid_core_options_and_editions(self):
  e,u,t=self.pair(CONTROL.MAGNET,target_pos=(12,5),target_extra={'types':['강철']});self.turn(e,u)
  self.reject(e,lambda:e.activate_ability(u,CONTROL.MAGNET,(t,{'choices':['maximum','minimum']})),'source range')
  self.reject(e,lambda:e.activate_ability(u,CONTROL.MAGNET,(u,{'mode':'edition','edition':'core-1.05'})),'before encounter')
  e,u,t=self.pair(CONTROL.MAGNET);self.turn(e,u)
  self.reject(e,lambda:e.activate_ability(u,CONTROL.MAGNET,(t,{'choices':['maximum','minimum']})),'Steel')

 def test_dazzling_native_initiative_and_priority_before_payment_then_scene_expiry(self):
  e,u,t=self.pair(CONTROL.DAZZLING,moves=('몸통박치기',));u.initiative_bonus=100
  e.prepare_initiative_schedule([u,t],source='gm/control-schedule');e.start_round([u,t]);e.start_of_turn(u)
  before=e.initiative_value(t).value;e.activate_ability(u,CONTROL.DAZZLING,t)
  self.assertEqual(t.initiative_bonus,-10);self.assertEqual(e.initiative_value(t).value,before-10)
  e.use_move(u,t,'move/몸통박치기',set_damage=True)
  self.assertEqual((u.budget['swift'],u.budget['standard']),(0,0))
  self.reject(e,lambda:e.activate_ability(u,CONTROL.DAZZLING,t),'action unavailable')
  self.assertEqual(t.initiative_bonus,-10)
  e.end_of_turn(u)
  self.reject(e,lambda:e.use_priority_move(t,u,'move/전광석화'),'Dazzling prohibits')
  e.end_scene([u,t],round_elapsed_seconds=0)
  self.assertEqual(t.initiative_bonus,0);self.valid(e)

 def test_dazzling_copy_alias_uses_same_twice_per_scene_quota(self):
  e,u,t=self.pair(CONTROL.DAZZLING);self.turn(e,u)
  e.activate_ability(u,'ability/비비드바디-2',t);e.end_of_turn(u);e.end_round()
  e.start_round([u,t]);e.start_of_turn(u,initiative_count=20);e.activate_ability(u,CONTROL.DAZZLING,t);e.end_of_turn(u);e.end_round()
  e.start_round([u,t]);e.start_of_turn(u,initiative_count=20)
  self.reject(e,lambda:e.activate_ability(u,'ability/비비드바디-2',t),'frequency exhausted')
  self.assertEqual(t.initiative_bonus,-20);self.valid(e)

 def test_dazzling_actual_ability_interrupt_is_asymmetric_and_decline_remains_available(self):
  import passive_events as PASSIVE
  for same_user,defense in ((True,'shell'),(False,'shell'),(True,'dodge'),(False,'dodge')):
   with self.subTest(same_user=same_user,defense=defense):
    e,u,t=self.pair(CONTROL.DAZZLING,moves=('물대포',))
    third=self.pokemon('other-attacker',None,pos=(6,6),moves=('물대포',));e.gm.add_combatant(third)
    e.gm.set_ability(t,'테라셸' if defense=='shell' else '회피',reason='actual recipient ability');self.turn(e,u)
    e.activate_ability(u,CONTROL.DAZZLING,t)
    attacker=u
    if not same_user:
     e.end_of_turn(u);e.start_of_turn(third,initiative_count=10);attacker=third
    if defense=='shell':e.watch_ability_interrupt(t,'ability/테라셸',reason='actual native recipient Interrupt')
    else:e.watch_move_defense(t,[{'actor_id':t.entity_id,'source':'ability/회피'}],reason='actual native Dodge Interrupt')
    e.rng.seed(530)
    with self.assertRaises(PASSIVE.PassiveEventPending):e.use_move(attacker,t,'move/물대포',set_damage=True)
    event=e._passive_pending
    def choose(use):
     if defense=='shell':return e.choose_ability_interrupt(event,t,use=use,options={'chosen_type':'물'} if use else None,reason='actual source response')
     return e.choose_move_defense(event,t,use=use,reason='actual native Dodge response')
    if same_user:
     self.reject(e,lambda:choose(True),'Dazzling prohibits')
     choose(False)
    else:choose(True)
    self.assertIsNone(e._passive_pending);self.valid(e)

 def test_tail_native_fixed_blast_blocks_priority_until_successor_count(self):
  e,u,t=self.pair(CONTROL.TAIL,target_pos=(9,5));u.initiative_bonus=100
  e.prepare_initiative_schedule([u,t],source='gm/control-schedule');e.start_round([u,t]);e.start_of_turn(u,initiative_count=e.initiative_value(u).value)
  count=TIME.current(e);e.activate_ability(u,CONTROL.TAIL,(u,{'aim':[9,5]}));e.end_of_turn(u)
  self.reject(e,lambda:e.use_priority_move(t,u,'move/전광석화'),'Armor Tail prohibits')
  e.start_of_turn(t,initiative_count=e.initiative_value(t).value);e.end_of_turn(t);e.end_round()
  e.prepare_initiative_schedule([u,t],source='gm/control-successor-schedule');e.start_round([u,t]);e.at_initiative_count(count+1)
  self.assertTrue(CONTROL._live(u,'tail'));e.at_initiative_count(count)
  self.assertFalse(CONTROL._live(u,'tail'));self.valid(e)

 def test_tail_native_entry_aoo_ignores_range_but_shared_once_round_limit_remains(self):
  e,u,t=self.pair(CONTROL.TAIL,target_pos=(7,5));self.turn(e,u)
  e.activate_ability(u,CONTROL.TAIL,(u,{'aim':[9,5]}))
  self.assertFalse(e.adjacent(u,t));FORCED.displace(e,u,t,direction=(1,0),distance=1,source=CONTROL.MAGNET)
  self.assertTrue(u.aoo_used)
  rows=[r for r in getattr(e,'_move_completions',{}).values() if r['actor'] is u and r['move_id']=='struggle']
  self.assertEqual(len(rows),1)
  FORCED.displace(e,u,t,direction=(-1,0),distance=1,source=CONTROL.MAGNET)
  self.assertEqual(len([r for r in e._move_completions.values() if r['actor'] is u and r['move_id']=='struggle']),1)
  self.valid(e)

 def test_tail_other_aoo_incapacitation_limit_is_not_bypassed(self):
  e,u,t=self.pair(CONTROL.TAIL,target_pos=(7,5));self.turn(e,u)
  e.activate_ability(u,CONTROL.TAIL,(u,{'aim':[9,5]}));e.apply_status(u,'마비')
  FORCED.displace(e,u,t,direction=(1,0),distance=1,source=CONTROL.MAGNET)
  self.assertFalse(u.aoo_used);self.assertFalse(getattr(e,'_move_completions',{}));self.valid(e)

 def test_tail_optional_psychic_struggle_native_move_retains_class_and_shared_definition(self):
  e,u,t=self.pair(CONTROL.TAIL);self.turn(e,u)
  baseline=deepcopy(self.r.move('struggle'))
  e.use_move(u,t,'struggle',struggle_choice={'ability':CONTROL.TAIL,'type':'에스퍼'},set_damage=True)
  row=next(r for r in e._move_completions.values() if r['actor'] is u)
  self.assertEqual((row['move']['type'],row['move']['class']),('에스퍼','물리'))
  self.assertEqual(self.r.move('struggle'),baseline);self.valid(e)

 def test_anchor_real_token_is_medium_noncover_nontargetable_and_immovable(self):
  e,u,t=self.pair(CONTROL.ANCHOR)
  obj=CONTROL._anchor(e,u)
  self.assertEqual(obj[CONTROL.TAG]['size'],'medium');self.assertFalse(obj[CONTROL.TAG]['cover'])
  result=FORCED.displace(e,t,obj,direction=(1,0),distance=2,source=CONTROL.MAGNET)
  self.assertEqual(result['moved'],0)
  import physical_object_attacks as OBJECTS
  self.reject(e,lambda:OBJECTS.configure(e,t,obj['id'],max_hp=20,reduction=0,minimum_damage=0,source='gm/control-object',reason='attempted actual target'),'source-owned control token cannot be targeted')
  self.assertTrue(BODY.can_place(e,t,(5,5),origin=t.pos,ignore_actors=(u,)));self.valid(e)

 def test_anchor_native_forced_tether_and_swift_relocation_are_same_source(self):
  e,u,t=self.pair('ability/닻-2',target_pos=(5,7));self.turn(e,u)
  moved=FORCED.displace(e,t,u,direction=(1,0),distance=5,source=CONTROL.MAGNET)
  self.assertEqual(moved['moved'],3);self.assertEqual(u.pos,(8,5))
  self.reject(e,lambda:e.activate_ability(u,CONTROL.ANCHOR,(u,{'cell':[12,5]})),'3m')
  e.activate_ability(u,CONTROL.ANCHOR,(u,{'cell':[10,5]}))
  self.assertEqual(CONTROL._anchor(e,u)['pos'],(10,5));self.assertEqual(u.budget['swift'],0)
  self.assertTrue(BODY.can_place(e,u,(13,5),origin=u.pos));self.assertFalse(BODY.can_place(e,u,(14,5),origin=u.pos));self.valid(e)

 def test_anchor_immediate_native_attack_origin_physical_damage_bonus_and_no_scope_leak(self):
  e,u,t=self.pair(CONTROL.ANCHOR,target_pos=(9,5),moves=('물대포',));self.turn(e,u)
  baseline=deepcopy(self.r.move('move/물대포'))
  e.activate_ability(u,CONTROL.ANCHOR,(u,{'cell':[8,5],'move_id':'move/물대포','target_id':t.entity_id}))
  rows=[r for r in e._move_completions.values() if r['actor'] is u]
  self.assertEqual(len(rows),1);move=rows[0]['move']
  self.assertEqual(move['class'],'물리');self.assertEqual(move['_class_move_range']['origin'],1)
  self.assertEqual(move['_ability_control_attack']['cell'],[8,5]);self.assertEqual(u.budget['standard'],0)
  self.assertEqual(u.spec[CONTROL.ATTACK]['status'],'closed');self.assertEqual(self.r.move('move/물대포'),baseline)
  self.reject(e,lambda:STRUGGLE.prepare(e,u,move),'scope has ended');self.valid(e)

 def test_anchor_actual_pending_recipient_interrupt_commits_once_then_closes_scope(self):
  import passive_events as PASSIVE
  e,u,t=self.pair(CONTROL.ANCHOR,target_pos=(9,5),moves=('물대포',));e.gm.set_ability(t,'테라셸',reason='actual native recipient ability');self.turn(e,u)
  e.watch_ability_interrupt(t,'ability/테라셸',reason='actual source interrupt');e.rng.seed(530)
  with self.assertRaises(PASSIVE.PassiveEventPending):e.activate_ability(u,CONTROL.ANCHOR,(u,{'cell':[8,5],'move_id':'move/물대포','target_id':t.entity_id}))
  self.assertEqual(CONTROL._anchor(e,u)['pos'],(8,5));self.assertEqual(u.budget['swift'],0)
  self.assertEqual(u.spec[CONTROL.ATTACK]['status'],'open')
  e=self.fresh(e);index={a.entity_id:a for a in e.everyone};u=index[u.entity_id];t=index[t.entity_id]
  e.choose_ability_interrupt(e._passive_pending,t,use=False,reason='actual native decline and resume')
  self.assertIsNone(e._passive_pending);self.assertEqual(u.spec[CONTROL.ATTACK]['status'],'closed')
  self.assertEqual(u.move_uses['move/물대포'],1);self.assertEqual(u.budget['standard'],0);self.valid(e)

 def test_anchor_forged_unpaid_scope_is_rejected_at_actual_registration(self):
  e=self.engine()
  fake={'source':CONTROL.ANCHOR,'kind':'anchor','move_id':'move/물대포','target_id':'other','cell':[5,5],'round':0,'status':'open','action_index':0,'turn_serial':0}
  user=self.pokemon('unpaid-anchor',CONTROL.ANCHOR,pos=(5,5),extra={CONTROL.ATTACK:fake})
  self.reject(e,lambda:e.gm.add_combatant(user),'paid Anchored relocation')

 def test_cold_restore_retains_actual_control_effects_clocks_sources_and_anchor_object(self):
  for source,options in ((CONTROL.SHADOW,None),(CONTROL.DAZZLING,None),(CONTROL.MAGNET,{'choices':['maximum','minimum']}),
                         (CONTROL.TAIL,{'aim':[9,5]}),(CONTROL.ANCHOR,{'cell':[7,5]}),(CONTROL.ARENA,None)):
   with self.subTest(source=source):
    e,u,t=self.pair(source,target_extra={'types':['강철']});self.turn(e,u)
    target=u if source in (CONTROL.TAIL,CONTROL.ANCHOR,CONTROL.ARENA) else t
    e.activate_ability(u,source,(target,options) if options is not None else target)
    restored=self.fresh(e);index={a.entity_id:a for a in restored.everyone}
    # Cold import intentionally advances the root-resolution epoch. Compare
    # actual domain facts, clocks and resources, not that process-local epoch.
    for original in e.everyone:
     actual=index[original.entity_id]
     self.assertEqual(actual.spec,original.spec)
     self.assertEqual(hasattr(actual,'budget'),hasattr(original,'budget'))
     self.assertEqual((actual.conditions,actual.pos,actual.initiative_bonus,getattr(actual,'budget',None)),(original.conditions,original.pos,original.initiative_bonus,getattr(original,'budget',None)))
     def timers(c):return [{k:(v.entity_id if k=='turn_owner' else deepcopy(v)) for k,v in row.items()} for row in TIME.records(c)]
     self.assertEqual(timers(actual),timers(original))
    self.assertEqual(getattr(restored,'_physical_objects',{}),getattr(e,'_physical_objects',{}))
    self.assertEqual(restored.round_no,e.round_no);self.assertEqual(restored._initiative_cursor,e._initiative_cursor)

 def test_tampered_control_producer_is_rejected_by_native_cold_restore(self):
  e,u,t=self.pair(CONTROL.SHADOW);self.turn(e,u);e.activate_ability(u,CONTROL.SHADOW,t)
  state=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
  encoded=json.dumps(state,ensure_ascii=False)
  self.assertIn('control-user:control:1',encoded)
  # Corrupting both clock-facing effect and independent original receipt is not
  # an authorized action; a changed owner must still resolve to its producer.
  changed=0
  def corrupt(value):
   nonlocal changed
   if isinstance(value,list):
    if value==['owner_id',u.entity_id]:value[1]='missing-owner';changed+=1
    else:
     for child in value:corrupt(child)
   elif isinstance(value,dict):
    for child in value.values():corrupt(child)
  corrupt(state);self.assertGreater(changed,0)
  with self.assertRaises(ValueError):Engine.import_state(self.r,state)


if __name__=='__main__':unittest.main()
