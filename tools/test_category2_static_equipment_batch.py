"""Current public-path checks for four static equipment rows and Ultra Ball."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0]=[str(STAGE/"engine"),str(ROOT/"engine"),str(ROOT/"tools")]

from builder import build_pokemon,build_trainer
from engine import Combatant,Engine,Rules
import effects as FX
import effects_ext as EXT
import field_effects as FIELD
import items as ITEMS
import native_scenario_fixture as NATIVE
import static_equipment_contracts as STATIC
import world_entities as WORLD

CLAUSES={"C2CSV/inventory:109:17","C2CSV/inventory:110:17","C2CSV/inventory:126:10","C2CSV/inventory:138:10","C2CSV/inventory:57:13"}

class StaticEquipmentBatchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset="core")
 def fixture(self,pokemon=False,moves=()):
  e=Engine(self.r,seed=57109110126138)
  if pokemon:spec=build_pokemon(self.r,"피카츄",30,name="Holder",moves=list(moves),abilities=["정전기"])
  else:
   stats=dict.fromkeys(("hp","atk","def","spa","spd","spe"),25)
   spec=build_trainer(self.r,"Holder",30,stats,moves=list(moves),abilities=[])
  holder=Combatant(self.r,spec)
  target=Combatant(self.r,build_pokemon(self.r,"이상해씨",30,name="Target",moves=["move/몸통박치기"],abilities=["심록"],side="wild"))
  e.gm.add_combatant(holder);e.gm.add_combatant(target)
  return e,holder,target
 def equip(self,e,actor,item_id,suffix):
  uid="static-equipment/"+suffix
  WORLD.register_object(e,uid,kind="item_instance",item_rule_id=item_id,owner_id=actor.entity_id,location={"kind":"unknown"},reason="actual reviewed CSV equipment fixture")
  ITEMS.register_item(e,actor,item_id,source_instance_id=uid,as_held=actor.kind=="pokemon")
  self.assertTrue(any(row.get("instance_id")==uid for row in actor._item_reg.values()));return uid
 def restored(self,e):return Engine.import_state(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))

 def test_trainer_only_equipment_rejects_pokemon_before_registration(self):
  for item_id in ("item/클리어참","item/특성가드"):
   for as_held in (False,True):
    with self.subTest(item_id=item_id,as_held=as_held):
     e,holder,_=self.fixture(pokemon=True);uid="static-equipment/wrong-wearer"
     WORLD.register_object(e,uid,kind="item_instance",item_rule_id=item_id,owner_id=holder.entity_id,location={"kind":"unknown"},reason="actual owned equipment before rejected Pokemon wearer choice")
     NATIVE.assert_rejected_unchanged(e,lambda:ITEMS.register_item(e,holder,item_id,source_instance_id=uid,as_held=as_held),reason_pattern="requires a trainer wearer$")
     self.assertTrue(e.validate_state()["valid"])

 def test_exact_source_provenance_and_current_denominator(self):
  policy=STATIC.policy(self.r);self.assertEqual({row["clause_id"] for row in policy["rows"].values()},CLAUSES-{"C2CSV/inventory:57:13"})
  status=json.loads((ROOT/"data/verification/category2-item-table-status.json").read_text(encoding="utf-8"));indexed={row["clause_id"]:row for row in status["new_clauses"]}
  for clause in CLAUSES:
   with self.subTest(clause=clause):self.assertIn(indexed[clause]["status"],{"incomplete","implemented"})
  for row in policy["rows"].values():self.assertEqual(indexed[row["clause_id"]]["source"][0]["raw_cells_sha256"],row["source_row_sha256"])

 def test_clear_amulet_and_ability_shield_native_handlers_and_revocation(self):
  e,holder,enemy=self.fixture();self.equip(e,holder,"item/클리어참","amulet")
  effect={"type":"stage_change","stat":"atk","delta":-1,"on":"target"}
  e.apply_effect(enemy,holder,effect,2,True,0,"move/울음소리");self.assertEqual(holder.stages["atk"],0)
  e.apply_effect(enemy,holder,effect,2,True,0,"condition/test");self.assertEqual(holder.stages["atk"],-1)
  ITEMS.unregister_item(e,holder,"item/클리어참");e.apply_effect(enemy,holder,{**effect,"stat":"def"},2,True,0,"ability/test");self.assertEqual(holder.stages["def"],-1)
  self.equip(e,holder,"item/특성가드","shield");e.apply_effect(enemy,holder,{"type":"suppress_ability","on":"target"},2,True,0,"move/위액");self.assertFalse(holder.abilities_suppressed)
  e.apply_effect(enemy,holder,{"type":"ability_change","on":"target","set_ability":"괴력집게"},2,True,0,"move/심플빔");self.assertNotEqual(holder.abilities,["괴력집게"])
  loaded=self.restored(e);loaded_holder=next(c for c in loaded.everyone if c.name==holder.name);loaded_enemy=next(c for c in loaded.everyone if c.name==enemy.name)
  loaded.apply_effect(loaded_enemy,loaded_holder,{"type":"suppress_ability","on":"target"},2,True,0,"move/위액");self.assertFalse(loaded_holder.abilities_suppressed)
  ITEMS.unregister_item(loaded,loaded_holder,"item/특성가드");loaded.apply_effect(loaded_enemy,loaded_holder,{"type":"suppress_ability","on":"target"},2,True,0,"move/위액");self.assertTrue(loaded_holder.abilities_suppressed)

 def test_heavy_duty_boots_skip_actual_hazard_then_unregistered_path_consumes(self):
  e,holder,_=self.fixture(pokemon=True);self.equip(e,holder,"item/통굽부츠","boots");cell=(0,0)
  e.hazards[cell]={"owner":"Enemy","name":"spikes","effects":[{"type":"hp_loss","value":3}]};before=holder.hp
  EXT.on_enter_cell(e,holder,cell);self.assertEqual(holder.hp,before);self.assertIn(cell,e.hazards);self.assertNotIn("hz:spikes",holder.counters)
  ITEMS.unregister_item(e,holder,"item/통굽부츠");EXT.on_enter_cell(e,holder,cell);self.assertEqual(holder.hp,before-3);self.assertNotIn(cell,e.hazards)

 def test_terrain_extender_actual_field_receipt_survives_unequip_and_restore(self):
  e,holder,_=self.fixture(moves=["move/일렉트릭필드"]);self.equip(e,holder,"item/그라운드코트","terrain")
  effect=self.r.move_mech("move/일렉트릭필드")[0]["effects_exec"][0];state=FIELD.install(e,holder,effect,"move/일렉트릭필드")
  self.assertEqual((state["rounds"],state["duration_source"]["bonus_rounds"]),(7,2));receipt=deepcopy(state["duration_source"])
  ITEMS.unregister_item(e,holder,"item/그라운드코트");self.assertEqual(e.field["duration_source"],receipt)
  loaded=self.restored(e);self.assertEqual(FIELD.validate(loaded)["rounds"],7)

 def test_ultra_ball_native_capture_modifier_attempt_and_restore(self):
  modifiers=[]
  for ultra in (True,False):
   e,holder,target=self.fixture()
   import species_classification as CLASSIFICATION
   CLASSIFICATION.declare(e,target,ultra,source='explicit homebrew GM classification',reason='observed species in this campaign')
   holder.spec.setdefault("items",{})["울트라볼"]=1
   e.start_round([holder,target]);e.start_of_turn(holder,initiative_count=20);e.throw_ball(holder,target,"울트라볼",fixed_accuracy=20,fixed_capture=1)
   attempt=holder.spec["capture_attempts"]["capture-1"];modifiers.append(attempt["resolution"]["modifiers"]["ball"])
   loaded=self.restored(e);loaded_holder=next(c for c in loaded.everyone if c.name==holder.name);self.assertEqual(loaded_holder.spec["capture_attempts"]["capture-1"],attempt)
  self.assertEqual(modifiers,[0,-4])

if __name__=="__main__":unittest.main()
