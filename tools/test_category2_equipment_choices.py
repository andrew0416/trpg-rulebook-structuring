"""Full-source native equipment state projections: nine previously incomplete CSV clauses."""
from pathlib import Path
import sys,json,unittest,random
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'engine'))
import test_category2_csv_item_transfers as _fixture_test_category2_csv_item_transfers
from engine import Engine
import equipment_actions as E,items as I,world_entities as W,state_grants as G,turn as TURN
import frequency as FREQ
import common_checks as C

class EquipmentTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):_fixture_test_category2_csv_item_transfers.Tests.setUpClass();cls.f=_fixture_test_category2_csv_item_transfers.Tests()
 def accessory(self,e,actor,uid='accessory'):
  W.register_object(e,uid,location={'kind':'unknown'},reason='observed actual worn accessory',kind='item_instance',item_rule_id='item/달인의띠',owner_id=actor.entity_id)
  I.register_item(e,actor,'달인의띠',source_instance_id=uid)
  self.assertEqual(actor._item_reg['달인의띠']['slots'],['장신구'])
  return e._physical_objects[uid]
 def roundtrip(self,e):return Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
 def valid(self,e):self.assertTrue(e.validate_state()['valid'],e.validate_state()['issues'])
 def test_core_weapon_wr_move_matrix_uses_actual_equipped_range(self):
  import weapon_actions as WEAPONS
  cases=[('대형 근접무기','melee',1,1,2),('소형 근접무기','melee',1,0,1),
         ('발 무기','melee',1,1,1),('단거리 사격무기',4,4,0,0),
         ('장거리 사격무기',12,12,1,1)]
  for kind,origin,distance,ac,db in cases:
   with self.subTest(kind=kind):
    e,a,b,_=self.f.fixture(held=(None,None));a.side='party';b.side='wild'
    a.spec['skills']['전투']='숙련';a.pos=(0,0);b.pos=(distance+1,0)
    key=TURN.equip_weapon(e,a,{'name':'WR-'+kind,'kind':kind,'moves':['강타']})
    original=deepcopy(e.r.move('move/강타'))
    move=WEAPONS.prepare(e,a,e.r.move('move/강타'),key)
    self.assertEqual(WEAPONS.range_spec(e,move)['origin'],origin)
    self.assertEqual(move['id'],original['id'])
    self.assertEqual(move['ac'],original['ac']+ac)
    self.assertEqual(e.damage_base(a,move),original['damage_base']+db)
    e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
    before=deepcopy((a.budget,a.move_uses,e.rng.getstate(),b.hp))
    with self.assertRaisesRegex(ValueError,'outside selected weapon range'):
     e.use_move(a,b,'move/강타',set_damage=True,weapon_id=key)
    self.assertEqual((a.budget,a.move_uses,e.rng.getstate(),b.hp),before)
    b.pos=(distance,0);before=b.hp
    damage=e.use_move(a,b,'move/강타',set_damage=True,weapon_id=key)
    self.assertGreater(damage,0);self.assertEqual(before-b.hp,damage)
    self.assertEqual(a.move_uses['move/강타'],1);self.assertEqual(a.budget['standard'],0)
    self.assertEqual(e.r.move('move/강타'),original);self.valid(e)
 def test_core_weapon_shape_choice_is_explicit_and_recommendations_do_not_restrict(self):
  e,a,b,_=self.f.fixture(held=(None,None));a.side='party';b.side='wild'
  a.spec['skills']['전투']='숙련';b.pos=(12,0)
  weapon={'name':'납작한 추를 발사하는 장궁','kind':'장거리 사격무기','moves':['강타'],
          'shape':'활시위로 무거운 추를 발사하는 형태',
          'move_choice_reason':'GM이 외형에 맞는 강타를 선택했다. 무기 추천은 강제 제한이 아니다.'}
  key=TURN.equip_weapon(e,a,weapon)
  self.assertEqual(a.custom_conditions['equipped_weapons'][key]['weapon'],weapon)
  e.gm.snapshot('explicit-weapon-choice');TURN.unequip_weapon(e,a,key)
  e.gm.restore('explicit-weapon-choice');self.assertIs(W.actor_index(e)[a.entity_id],a)
  loaded=self.roundtrip(e);owner=W.actor_index(loaded)[a.entity_id];target=W.actor_index(loaded)[b.entity_id]
  self.assertEqual(owner.custom_conditions['equipped_weapons'][key]['weapon'],weapon)
  loaded.start_round([owner,target]);loaded.start_of_turn(owner,initiative_count=20)
  self.assertGreater(loaded.use_move(owner,target,'move/강타',set_damage=True,weapon_id=key),0)
  self.valid(loaded)
  e,a,_,_=self.f.fixture(held=(None,None));a.spec['skills']['전투']='숙련'
  before=e.export_state()
  with self.assertRaisesRegex(ValueError,'restricted to another weapon kind'):
   TURN.equip_weapon(e,a,{'name':'작은 도끼','kind':'소형 근접무기','moves':['백스윙']})
  self.assertEqual(e.export_state(),before)
  key=TURN.equip_weapon(e,a,{'name':'양손으로 휘두르는 거대한 금속 붓',
                           'kind':'대형 근접무기','moves':['백스윙']})
  self.assertIn('move/백스윙',a.custom_conditions['equipped_weapons'][key]['available_moves'])
  self.valid(e)
 def test_core_weapon_kind_matrix_reaches_actual_attacks(self):
  cases=[('대형 근접무기',['주요손','반대손'],1,2,1),
         ('소형 근접무기',['주요손'],0,1,1),
         ('발 무기',['발'],1,1,1),
         ('단거리 사격무기',['주요손'],0,0,4),
         ('장거리 사격무기',['주요손','반대손'],1,1,12)]
  for kind,slots,ac,db,distance in cases:
   with self.subTest(kind=kind):
    e,a,b,_=self.f.fixture(held=(None,None));a.side='party';b.side='wild'
    a.pos=(0,0);b.pos=(distance,0)
    key=TURN.equip_weapon(e,a,{'name':'core-'+kind,'kind':kind,'grade':'조잡'})
    record=a.custom_conditions['equipped_weapons'][key];base=e.r.mech('combat/struggle')
    self.assertEqual(record['slots'],slots);self.assertEqual(record['available_moves'],[key])
    self.assertEqual((e.r.move(key)['ac'],e.damage_base(a,e.r.move(key))),
                     (base['ac']+ac,base['damage_base']+db))
    e.start_round([a,b]);e.start_of_turn(a,initiative_count=20);before=b.hp
    damage=e.use_move(a,b,key,set_damage=True)
    self.assertGreater(damage,0);self.assertEqual(before-b.hp,damage)
    self.assertEqual(a.budget['standard'],0);self.valid(e)
 def test_core_weapon_grade_and_rank_matrix_preserves_independent_grants(self):
  cases=[('조잡','달인',0),('간단','미숙',0),('간단','숙련',1),
         ('간단','달인',1),('좋음','숙련',1),('좋음','달인',2)]
  for grade,rank,count in cases:
   with self.subTest(grade=grade,rank=rank):
    e,a,_,_=self.f.fixture(held=(None,None));a.spec['skills']['전투']=rank
    e.gm.set_move(a,'move/강타',True,reason='independently learned before equipment')
    key=TURN.equip_weapon(e,a,{'name':'grade-matrix','kind':'소형 근접무기',
                             'grade':grade,'moves':['강타','출혈']})
    self.assertEqual(len(a.custom_conditions['equipped_weapons'][key]['available_moves']),count+1)
    TURN.unequip_weapon(e,a,key);self.assertIn('move/강타',a.moves)
    self.assertNotIn(key,a.moves);self.assertNotIn('move/출혈',a.moves);self.valid(e)
  e,a,_,_=self.f.fixture(held=(None,None));a.spec['skills']['전투']='달인'
  key=TURN.equip_weapon(e,a,{'name':'master-off-hand','kind':'소형 근접무기',
                           'grade':'좋음','slot':'반대손','moves':['강타','출혈']})
  self.assertEqual(a.custom_conditions['equipped_weapons'][key]['available_moves'],[key,'move/강타'])
  self.assertNotIn('move/출혈',a.moves);self.valid(e)
 def test_fine_foot_weapon_keeps_rank_grants_and_actual_master_attack_after_restore(self):
  import weapon_actions as WEAPONS
  for rank,count in (('숙련',1),('달인',2)):
   with self.subTest(rank=rank):
    e,a,b,_=self.f.fixture(held=(None,None));a.side='party';b.side='wild'
    a.spec['skills']['전투']=rank
    e.gm.set_move(a,'move/강타',True,reason='independently learned before foot equipment')
    foot=TURN.equip_weapon(e,a,{'name':'fine-blade-shoes','kind':'발 무기',
                              'grade':'좋음','moves':['강타','출혈']})
    self.assertEqual(a.custom_conditions['equipped_weapons'][foot]['available_moves'],
                     [foot,'move/강타','move/출혈'][:count+1])
    e.gm.snapshot('fine-foot');TURN.unequip_weapon(e,a,foot)
    e.gm.restore('fine-foot');self.assertIs(W.actor_index(e)[a.entity_id],a)
    loaded=self.roundtrip(e);owner=W.actor_index(loaded)[a.entity_id];target=W.actor_index(loaded)[b.entity_id]
    self.assertEqual(owner.custom_conditions['equipped_weapons'][foot]['slots'],['발'])
    if rank=='달인':
     move=WEAPONS.prepare(loaded,owner,loaded.r.move('move/출혈'),foot)
     self.assertEqual(move['_weapon_attack']['accuracy_bonus'],0)
     self.assertEqual(move['ac'],loaded.r.move('move/출혈')['ac']+1)
     self.assertEqual(loaded.damage_base(owner,move),loaded.r.move('move/출혈')['damage_base']+1)
     loaded.start_round([owner,target]);loaded.start_of_turn(owner,initiative_count=20)
     before=target.hp;damage=loaded.use_move(owner,target,'move/출혈',set_damage=True,weapon_id=foot)
     self.assertGreater(damage,0);self.assertEqual(before-target.hp,damage)
     self.assertEqual(owner.move_uses['move/출혈'],1);self.assertEqual(owner.budget['standard'],0)
    TURN.unequip_weapon(loaded,owner,foot)
    self.assertIn('move/강타',owner.moves);self.assertNotIn('move/출혈',owner.moves)
    self.assertNotIn(foot,owner.moves);self.valid(loaded)
 def test_foot_weapon_shares_feet_slot_and_survives_gm_and_json_restore(self):
  e,a,b,_=self.f.fixture(held=(None,None))
  hand=TURN.equip_weapon(e,a,{'name':'hand','kind':'소형 근접무기','grade':'조잡'})
  foot=TURN.equip_weapon(e,a,{'name':'blade-shoes','kind':'발무기','grade':'조잡'})
  self.assertEqual(a.custom_conditions['equipped_weapons'][foot]['slots'],['발'])
  def equipment_state():return deepcopy((a.spec,a.custom_conditions,a.moves,a.stats,
                                        getattr(a,'_item_reg',{}),e.rng.getstate()))
  before=equipment_state()
  self.assertEqual(I.register_item(e,a,'러닝슈즈'),0)
  self.assertEqual(equipment_state(),before)
  before=e.export_state()
  for weapon in ({'name':'second-foot','kind':'발 무기'},
                 {'name':'wrong-foot','kind':'발 무기','slot':'주요손'},
                 {'name':'wrong-hand','kind':'소형 근접무기','slot':'발'}):
   with self.assertRaises(ValueError):TURN.equip_weapon(e,a,weapon)
  self.assertEqual(e.export_state(),before)
  with self.assertRaisesRegex(ValueError,'eligible hand'):
   TURN.disarm_equipment(e,a,'blade-shoes')
  self.assertEqual(TURN.disarm_equipment(e,a,'hand')[0],hand)
  e.gm.snapshot('foot-equipped');TURN.unequip_weapon(e,a,foot)
  e.gm.restore('foot-equipped');self.assertIs(W.actor_index(e)[a.entity_id],a)
  loaded=self.roundtrip(e);owner=W.actor_index(loaded)[a.entity_id]
  self.assertEqual(owner.custom_conditions['equipped_weapons'][foot]['slots'],['발'])
  self.assertIn(foot,owner.moves);self.assertIn(hand,owner.moves);self.valid(loaded)
  TURN.unequip_weapon(loaded,owner,foot)
  self.assertGreater(I.register_item(loaded,owner,'러닝슈즈'),0)
  before=loaded.export_state()
  with self.assertRaisesRegex(ValueError,'slot already occupied'):
   TURN.equip_weapon(loaded,owner,{'name':'blocked-foot','kind':'발 무기'})
  self.assertEqual(loaded.export_state(),before)
 def test_core_six_trainer_slots_share_item_weapon_capacity_after_restore(self):
  e,a,_,_=self.f.fixture(held=(None,None))
  worn=[('고고고글','머리'),('경갑','몸통'),('러닝슈즈','발'),('달인의띠','장신구')]
  for index,(name,slot) in enumerate(worn):
   uid='core-slot/'+str(index)
   W.register_object(e,uid,location={'kind':'unknown'},reason='observed ordinary equipment',kind='item_instance',item_rule_id='item/'+name,owner_id=a.entity_id)
   I.register_item(e,a,name,source_instance_id=uid)
   self.assertEqual(a._item_reg[name]['slots'],[slot]);self.assertEqual(e._physical_objects[uid]['equipped_by'],a.entity_id)
  for slot in ('주요손','반대손'):
   TURN.equip_weapon(e,a,{'name':'core-slot-'+slot,'kind':'소형 근접무기','slot':slot})
  def occupied(c):return [s for row in list(c._item_reg.values())+list(c.custom_conditions['equipped_weapons'].values()) for s in row['slots']]
  self.assertCountEqual(occupied(a),['머리','주요손','반대손','몸통','발','장신구']);self.valid(e)
  e.gm.snapshot('six-slots');head=a._item_reg['고고고글']['instance_id']
  I.unregister_item(e,a,'고고고글');self.assertNotIn('머리',occupied(a))
  e.gm.restore('six-slots');self.assertEqual(a._item_reg['고고고글']['instance_id'],head)
  loaded=self.roundtrip(e);c=W.actor_index(loaded)[a.entity_id]
  self.assertCountEqual(occupied(c),occupied(a));self.assertEqual(loaded._physical_objects[head]['equipped_by'],c.entity_id)
  def equipment_state():return deepcopy((c._item_reg,c.custom_conditions,c.spec,loaded._physical_objects,c.moves,c.stats,loaded.rng.getstate()))
  for name in ('방진고글','마찰저하복','스노우부츠','기합의띠','검은철구'):
   with self.subTest(name=name):
    uid='core-slot-conflict/'+name
    W.register_object(loaded,uid,location={'kind':'unknown'},reason='actual owned conflicting equipment',
                      kind='item_instance',item_rule_id=loaded.r.item_effects(name)[1]['id'],owner_id=c.entity_id)
    before=equipment_state();self.assertEqual(I.register_item(loaded,c,name,source_instance_id=uid),0);self.assertEqual(equipment_state(),before)
  for slot in ('주요손','반대손'):
   before=loaded.export_state()
   with self.assertRaisesRegex(ValueError,'slot already occupied'):TURN.equip_weapon(loaded,c,{'name':'blocked-'+slot,'kind':'소형 근접무기','slot':slot})
   self.assertEqual(loaded.export_state(),before)
  self.valid(loaded)
 def test_each_source_selects_one_actual_accessory_keeps_held_and_passives(self):
  for name in ('탁쳐서떨구기','도둑질','쪼아대기','탐내기'):
   with self.subTest(source=name):
    e,a,b,mid=self.f.fixture(name,held=(None,'선제공격손톱'));obj=self.accessory(e,b);owner=b.entity_id
    e.use_move(a,b,mid);rows=E.pending(e);self.assertEqual(len(rows),1);row=rows[0]
    self.assertEqual(b.item,'선제공격손톱');self.assertIs(e._physical_objects['accessory'],obj)
    self.assertEqual(len(row['options']),2)
    with self.assertRaises(ValueError):E.resolve(e,b,row['id'],selection='accessory')
    with self.assertRaises(ValueError):E.resolve(e,a,row['id'],selection='missing-instance')
    before_rng=e.rng.getstate();result=E.resolve(e,a,row['id'],selection='accessory')
    self.assertEqual(e.rng.getstate(),before_rng);self.assertEqual(b.item,'선제공격손톱');self.assertNotIn('달인의띠',b._item_reg)
    self.assertEqual(obj['owner_id'],owner);self.assertIs(e._physical_objects['accessory'],obj)
    if name=='탁쳐서떨구기':self.assertNotIn('equipped_by',obj);self.assertEqual(obj['location'],{'kind':'grid','cell':b.pos});self.assertIsNone(a.item)
    else:
     self.assertEqual(a.item,'달인의띠');self.assertEqual(obj['equipped_by'],a.entity_id)
     self.assertEqual(a._item_reg['달인의띠']['state_source'],'equipment:accessory');self.assertEqual(a._item_reg['달인의띠']['slots'],[])
    self.assertEqual(E.resolve(e,a,row['id'],selection='accessory'),result)
    with self.assertRaises(ValueError):E.resolve(e,a,row['id'],selection='physical/1')
    self.valid(e)
 def test_each_source_only_accessory_branch_and_empty_or_already_held(self):
  for name in ('탁쳐서떨구기','도둑질','쪼아대기','탐내기'):
   with self.subTest(source=name):
    e,a,b,mid=self.f.fixture(name,held=(None,None));obj=self.accessory(e,b);e.use_move(a,b,mid)
    self.assertFalse(E.pending(e));self.assertNotIn('달인의띠',b._item_reg)
    self.assertEqual(a.item,None if name=='탁쳐서떨구기' else '달인의띠');self.valid(e)
    e,a,b,mid=self.f.fixture(name,held=(None,None));e.use_move(a,b,mid);self.assertFalse(E.pending(e));self.assertIsNone(a.item)
    if name!='탁쳐서떨구기':
     e,a,b,mid=self.f.fixture(name,held=('선제공격손톱',None));obj=self.accessory(e,b);e.use_move(a,b,mid)
     self.assertFalse(E.pending(e));self.assertEqual(obj['equipped_by'],b.entity_id);self.assertEqual(a.item,'선제공격손톱')
 def test_pending_selection_gm_and_durable_restore_preserve_receipt_and_actor_identity(self):
  for name in ('탁쳐서떨구기','도둑질','쪼아대기','탐내기','불태우기'):
   with self.subTest(source=name):
    e,a,b,mid=self.f.fixture(name,held=(None,'선제공격손톱'));self.accessory(e,b);e.use_move(a,b,mid);row=E.pending(e)[0]
    e.gm.snapshot('choice');chooser=b if name=='불태우기' else a;options={'choice':'drop'} if name=='불태우기' else {'selection':'accessory'}
    with self.assertRaises(ValueError):e.advance_time(1)
    E.resolve(e,chooser,row['id'],**options);e.gm.restore('choice',reason='actual equipment choice rewind')
    loaded=self.roundtrip(e);index=W.actor_index(loaded);loaded_row=E.pending(loaded)[0]
    self.assertIs(loaded_row['actor'],index[a.entity_id]);self.assertIs(loaded_row['target'],index[b.entity_id])
    self.assertIs(loaded._effect_dispatch_receipts[loaded_row['receipt']]['receipt'],loaded_row['receipt'])
    E.resolve(loaded,index[chooser.entity_id],loaded_row['id'],**options);self.assertFalse(E.pending(loaded));self.valid(loaded)
 def test_changed_inventory_rejects_choice_without_partial_mutation(self):
  e,a,b,mid=self.f.fixture('도둑질',held=(None,'선제공격손톱'));self.accessory(e,b);e.use_move(a,b,mid);row=E.pending(e)[0]
  I.unregister_item(e,b,'달인의띠');before=deepcopy((a.item,b.item,e._physical_objects))
  with self.assertRaises(ValueError):E.resolve(e,a,row['id'],selection='accessory')
  self.assertEqual((a.item,b.item,e._physical_objects),before)
 def test_bestow_empty_occupied_and_no_item_use_swift_without_latent_modifier(self):
  for held,expected in [(('선제공격손톱',None),(None,'선제공격손톱')),(('선제공격손톱','예리한손톱'),('선제공격손톱','예리한손톱')),((None,None),(None,None))]:
   e,a,b,mid=self.f.fixture('기프트패스',held=held);e.use_move(a,b,mid)
   self.assertEqual((a.item,b.item),expected);self.assertFalse(E.pending(e));self.assertEqual(a._action_history[-1][0] if isinstance(a._action_history[-1],tuple) else a._action_history[-1], 'swift')
   self.assertFalse(any(row.get('type')=='action_type_change' for row in a.registry));self.assertTrue(all(row['status']=='completed' for row in getattr(e,'_effect_dispatch_receipts',{}).values()));self.valid(e)
 def test_incinerate_no_equipment_has_no_extra_tick(self):
  e,a,b,mid=self.f.fixture('불태우기',held=(None,None));before=b.hp;damage=e.use_move(a,b,mid)
  self.assertEqual(before-b.hp,damage);self.assertFalse(E.pending(e))
 def test_incinerate_hp_choice_exactly_once_ignores_number_and_preserves_items(self):
  for weapon_count in (0,1,2):
   e,a,b,mid=self.f.fixture('불태우기',held=(None,'선제공격손톱'))
   for i in range(weapon_count):TURN.equip_weapon(e,b,{'name':'observed-'+str(i),'kind':'소형 근접무기','slot':'주요손' if i==0 else '반대손'})
   damage=e.use_move(a,b,mid);row=E.pending(e)[0];before=b.hp;result=E.resolve(e,b,row['id'],choice='hp_loss')
   self.assertEqual(before-b.hp,e.tick(b));self.assertEqual(result['applications'],1);self.assertEqual(b.item,'선제공격손톱')
   self.assertEqual(len(b.custom_conditions.get('equipped_weapons',{})),weapon_count)
   E.resolve(e,b,row['id'],choice='hp_loss');self.assertEqual(before-b.hp,e.tick(b));self.valid(e)
 def test_incinerate_drop_releases_both_hands_and_held_preserves_accessory(self):
  e,a,b,mid=self.f.fixture('불태우기',held=(None,'선제공격손톱'));self.accessory(e,b)
  keys=[TURN.equip_weapon(e,b,{'name':'observed-'+str(i),'kind':'소형 근접무기','slot':'주요손' if i==0 else '반대손'}) for i in (0,1)]
  damage=e.use_move(a,b,mid);row=E.pending(e)[0];self.assertEqual(len(row['options']),3);before=b.hp
  E.resolve(e,b,row['id'],choice='drop');self.assertEqual(b.hp,before);self.assertIsNone(b.item);self.assertFalse(b.custom_conditions.get('equipped_weapons'))
  self.assertIn('달인의띠',b._item_reg);self.assertEqual(len(e.ground_items),2)
  self.assertFalse(set(keys).intersection(b.moves));self.assertEqual({x['former_equipment_key'] for x in e.ground_items},set(keys));self.assertEqual(e._physical_objects['physical/1']['location'],{'kind':'grid','cell':b.pos});self.valid(e)
 def test_incinerate_actual_line_finishes_all_hits_then_independent_choices_survive_save(self):
  from grid import Grid
  e,a,b,c,mid=self.f.fixture('불태우기',held=(None,'선제공격손톱','예리한손톱'));e.grid=Grid(10,10)
  total=e.use_move_on(a,b,mid,e.everyone);self.assertEqual(120-b.hp-c.hp,total)
  rows=E.pending(e);self.assertEqual(len(rows),2);self.assertEqual(a.move_uses[mid],1)
  loaded=self.roundtrip(e);index=W.actor_index(loaded);bb=index[b.entity_id];cc=index[c.entity_id]
  rows={row['target'].entity_id:row for row in E.pending(loaded)}
  E.resolve(loaded,bb,rows[bb.entity_id]['id'],choice='drop');before=cc.hp
  E.resolve(loaded,cc,rows[cc.entity_id]['id'],choice='hp_loss')
  self.assertIsNone(bb.item);self.assertEqual(cc.item,'예리한손톱');self.assertEqual(before-cc.hp,loaded.tick(cc));self.valid(loaded)
 def test_trick_completed_gm_codec_actual_pair_and_all_empty_case(self):
  for held in (('선제공격손톱','예리한손톱',None),(None,None,None)):
   e,a,b,c,mid=self.f.fixture('트릭',held=held);result=e.use_move_on(a,b,mid,e.everyone,equipment_options={'targets':[b,c]})
   expected=(a.item,b.item,c.item);e.gm.snapshot('trick');e.gm.restore('trick',reason='actual pair receipt')
   loaded=self.roundtrip(e);index=W.actor_index(loaded)
   self.assertEqual(tuple(index[x.entity_id].item for x in (a,b,c)),expected)
   self.assertEqual(index[a.entity_id].custom_conditions['_equipment_trick_history'][-1],result)
   self.valid(loaded)
 def test_trick_actual_pair_partial_hit_empty_slot_and_cost_rng_once(self):
  for seed,both in ((0,True),(10,False)):
   e,a,b,c,mid=self.f.fixture('트릭',held=('선제공격손톱','예리한손톱',None),seed=seed)
   expected_rng=random.Random(seed);faces=[expected_rng.randint(1,20),expected_rng.randint(1,20)]
   result=e.use_move_on(a,b,mid,e.everyone,equipment_options={'targets':[b,c]})
   self.assertEqual(all(result['hits'].values()),both);self.assertEqual(a.item,'선제공격손톱')
   self.assertEqual((b.item,c.item),(None,'예리한손톱') if both else ('예리한손톱',None));self.assertEqual(a.move_uses[mid],1)
   self.assertEqual(e.rng.getstate(),expected_rng.getstate());self.assertEqual(len(a._action_history),1);self.assertFalse(getattr(e,'_action_grants',[]));self.valid(e)
 def test_trick_self_and_explicit_ally_consent_no_rng_unknown_or_enemy_not_assumed(self):
  e,a,b,mid=self.f.fixture('트릭');a.side=b.side='party';before=e.rng.getstate()
  result=e.use_move_on(a,a,mid,e.everyone,equipment_options={'targets':[a,b],'consenting':[b]})
  self.assertEqual(e.rng.getstate(),before);self.assertTrue(all(result['hits'].values()));self.assertEqual((a.item,b.item),('예리한손톱','선제공격손톱'))
  e,a,b,mid=self.f.fixture('트릭');a.side='a';b.side='b';before=e.rng.getstate()
  with self.assertRaises(ValueError):e.use_move_on(a,a,mid,e.everyone,equipment_options={'targets':[a,b],'consenting':[b]})
  self.assertEqual(e.rng.getstate(),before);self.assertFalse(a.move_uses)
  e,a,b,mid=self.f.fixture('트릭');self.assertIsInstance(e.use_move_on(a,b,mid,e.everyone),C.PendingDecision)
  with self.assertRaises(ValueError):e.use_move(a,b,mid)
  self.assertFalse(a.move_uses)
 def reaction(self,name,move='몸통박치기',seed=0,occupied=False):
  held=(None,'선제공격손톱') if name=='매지션' else ('선제공격손톱',None)
  if occupied:held=('선제공격손톱','예리한손톱')
  e,a,b,mid=self.f.fixture(move,held=held,seed=seed);holder=a if name=='매지션' else b;G.replace_baseline(e,holder,'abilities',[name])
  e.gm.add_combatant(a,side='party',reason='observed reaction attacker side')
  e.gm.add_combatant(b,side='foe',reason='observed reaction target side')
  e.use_move(a,b,mid);return e,a,b,holder
 def test_each_actual_hit_reaction_accepts_declines_and_charges_scene_once(self):
  for name in ('나쁜손버릇','매지션'):
   for accept in (True,False):
    e,a,b,holder=self.reaction(name);rows=E.pending(e);self.assertEqual(len(rows),1);row=rows[0]
    self.assertEqual(row['native_trigger']['event'],E.REACTIONS['ability/'+name]);before=deepcopy(holder.spec.get('frequency_state',{}))
    E.resolve(e,holder,row['id'],accept=accept);self.assertFalse(E.pending(e));E.resolve(e,holder,row['id'],accept=accept)
    self.assertEqual(holder.item,'선제공격손톱' if accept else None)
    self.assertEqual(FREQ.activation_allowed(holder,'ability/'+name,e.r.ability_freq[name],engine=e),not accept)
    if not accept:self.assertEqual(holder.spec.get('frequency_state',{}),before)
    self.valid(e)
 def test_reaction_false_trigger_miss_ranged_area_and_occupied_do_not_offer(self):
  for name in ('나쁜손버릇','매지션'):
   e,a,b,holder=self.reaction(name,seed=2);self.assertFalse(E.pending(e))
   e,a,b,holder=self.reaction(name,occupied=True);self.assertFalse(E.pending(e))
  e,a,b,holder=self.reaction('나쁜손버릇',move='물대포');self.assertFalse(E.pending(e))
  e,a,b,holder=self.reaction('매지션',move='불태우기');self.assertFalse(any(x['mode']=='reaction' for x in E.pending(e)))
 def test_each_reaction_pending_gm_and_codec_then_source_removal_rejects(self):
  for name in ('나쁜손버릇','매지션'):
   e,a,b,holder=self.reaction(name);row=E.pending(e)[0];e.gm.snapshot('reaction')
   E.resolve(e,holder,row['id'],accept=True);e.gm.restore('reaction',reason='restore hit-owned free choice')
   loaded=self.roundtrip(e);who=W.actor_index(loaded)[holder.entity_id];newrow=E.pending(loaded)[0]
   E.resolve(loaded,who,newrow['id'],accept=True);self.assertEqual(who.item,'선제공격손톱');self.valid(loaded)
   e,a,b,holder=self.reaction(name);row=E.pending(e)[0];G.replace_baseline(e,holder,'abilities',[])
   with self.assertRaises(ValueError):E.resolve(e,holder,row['id'],accept=True)
   self.assertIsNone(holder.item)

if __name__=='__main__':unittest.main(verbosity=2)
