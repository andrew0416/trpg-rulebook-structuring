"""Run canonical related suites with this stage's three overlay modules loaded first."""
from pathlib import Path
import sys,unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]

# engine.py deliberately promotes its own directory. Cache the stage-owned
# modules first so the integrated runtime exercises this candidate patch.
import effect_instances,food_effects,gm_state
import engine

MODULES=(
 'test_category2_food_instances',
 'test_category2_food_scene_history',
 'test_category2_temporary_hp_state',
 'test_category2_temporary_hp_lifetime',
 'test_category2_state_codec',
 'test_category3_food_effects',
)
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in MODULES)
result=unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
