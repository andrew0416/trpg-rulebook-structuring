"""Run only the two canonical modules directly touched by the reveal overlay."""
from pathlib import Path
import sys,unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]

import ability_reveals,manual_effects
import engine

suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in (
 'test_foundation_perception_observe',
 'test_category2_manual_effects',
))
result=unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
