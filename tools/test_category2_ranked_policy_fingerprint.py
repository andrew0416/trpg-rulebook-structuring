"""Loading exact ranked source tables is not a selected-rules change."""
from copy import deepcopy
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine')]
from engine import Rules,Engine
import class_move_grants as MOVES
import state_codec as CODEC

class RankedPolicyFingerprintTests(unittest.TestCase):
 def test_exact_ranked_cache_is_cold_equivalent_but_overrides_stay_fingerprinted(self):
  rules=Rules(ROOT,ruleset='all')
  self.assertNotIn('_ranked_class_move_tables',vars(rules))
  cold=CODEC.rules_fingerprint(rules)
  loaded=MOVES._ranked_tables(rules)
  self.assertEqual(set(loaded),set(MOVES.TABLED_RANKED))
  self.assertEqual(CODEC.rules_fingerprint(rules),cold)
  rules._ranked_class_move_tables=deepcopy(loaded)
  rules._ranked_class_move_tables['feat/해류의-부름']['minimum_skill_rank'][1]=5
  self.assertNotEqual(CODEC.rules_fingerprint(rules),cold)
 def test_cold_saved_state_loads_with_exact_warm_cache_and_rejects_changed_cache(self):
  rules=Rules(ROOT,ruleset='all');engine=Engine(rules,seed=1225)
  payload=CODEC.dump_engine(engine)
  MOVES._ranked_tables(rules)
  restored=CODEC.load_engine(rules,payload)
  self.assertEqual(restored.rng.getstate(),engine.rng.getstate())
  rules._ranked_class_move_tables=deepcopy(rules._ranked_class_move_tables)
  rules._ranked_class_move_tables['feat/스톰-위자드']['skills']=['직감']
  with self.assertRaisesRegex(ValueError,'fingerprint mismatch'):
   CODEC.load_engine(rules,payload)

if __name__=='__main__':unittest.main()
