"""The chosen Chef bonus lifetime survives only the non-ending native boundaries."""
from copy import deepcopy
from pathlib import Path
import unittest
from engine import Rules
import book_chef_fixture as FIX
from tools import test_book_chef_taste as BASE
import chef_cooking as CHEF
import food_effects as FOOD
import combat_timing as TIMING

ROOT=Path(__file__).resolve().parents[1]


class ChefBonusBoundaryTests(unittest.TestCase):
    def test_native_haze_recall_and_encounter_respect_actual_scene_or_encounter_choice(self):
        for boundary in ('scene_end','encounter_end'):
            with self.subTest(boundary=boundary):
                rules=Rules(ROOT,ruleset='all')
                world=FIX.scene(rules,seed=11,pokemon_nature=FIX.nature_for(rules,'신맛','liked'))
                e,chef,partner,foe=[world[key] for key in ('engine','chef','partner','foe')]
                served=FIX.serve(e,chef,FIX.cook(e,chef,recipe='tasty_snack',snack='신맛 캔디')['batch_id'],partner)
                payload=FOOD.get_buff(partner,served['buff_id'])['effect']
                attacker,target=(partner,foe) if payload['trigger']=='attack' else (foe,partner)
                FIX.battle(e,attacker);FIX.ruling(e,boundary)
                helper=BASE.ChefTasteTests();helper.rules=rules
                helper.trade_in(e,partner,served['buff_id'],attacker=attacker,target=target)
                record=deepcopy(next(row for row in TIMING.records(partner) if CHEF.BONUS in row))
                self.assertEqual(CHEF.evasion_bonus(partner,'물리'),1)
                FIX.decline_all(e,chef)
                e.end_of_turn(e._active_turn_actor);e.start_round(e.everyone)
                e.gm.set_move(foe,'move/흑안개',reason='actual known Haze source')
                e.start_of_turn(foe,initiative_count=20)
                e.use_move_on(foe,foe,'move/흑안개',e.everyone)
                self.assertEqual(next(row for row in TIMING.records(partner) if CHEF.BONUS in row),record)
                self.assertEqual(CHEF.evasion_bonus(partner,'물리'),1)
                position=partner.pos
                e.gm.recall(partner,reason='actual recall retains the adjudicated taste lifetime')
                self.assertEqual(next(row for row in TIMING.records(partner) if CHEF.BONUS in row),record)
                e.gm.send_out(partner,pos=position,reason='actual return before selected lifetime ends')
                self.assertEqual(CHEF.evasion_bonus(partner,'물리'),1)
                e.end_of_turn(foe);e.end_encounter(round_elapsed_seconds=10)
                remaining=[row for row in TIMING.records(partner) if CHEF.BONUS in row]
                self.assertEqual(remaining,[record] if boundary=='scene_end' else [])
                e.end_scene();self.assertEqual([row for row in TIMING.records(partner) if CHEF.BONUS in row],[])
                self.assertEqual(CHEF.evasion_bonus(partner,'물리'),0)
                self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
