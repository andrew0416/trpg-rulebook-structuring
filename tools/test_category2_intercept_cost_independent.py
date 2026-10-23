"""Independent backward compatibility and proof boundaries for Intercept cost profiles."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import action_resources as RESOURCES
import state_codec as CODEC


class InterceptCostIndependentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='core')
        cls.legacy=json.loads((ROOT/'tools/fixtures/native-defense-before-cost-profiles.json').read_text(encoding='utf-8'))

    def restore_legacy(self,kind):
        record=deepcopy(self.legacy['records'][kind])
        # Preserve the actual old producer's graph, including its absent cost
        # profile. Reauthenticate this trusted test fixture against the current
        # corpus: publishing the new profile policy intentionally changes the
        # strict save fingerprint. Production does not bypass that check.
        record['state']['rules']=CODEC.rules_fingerprint(self.rules)
        engine=Engine.import_state(self.rules,record['state'])
        actors={a.entity_id:a for a in engine.everyone}
        return engine,record,{role:actors[uid] for role,uid in record['actor_ids'].items()}

    def test_published_full_receipt_without_profile_cold_restores_as_original_full_cost(self):
        engine,record,actors=self.restore_legacy('complete')
        row=next(iter(engine._move_completions.values()))
        attempt=row['defense'][actors['target'].entity_id]['attempts'][0]
        self.assertNotIn('cost_profile',attempt)
        self.assertEqual(actors['reactor']._action_history,['full'])
        self.assertEqual(RESOURCES.pending(actors['reactor']),{'standard':1,'shift':1})
        hp=actors['reactor'].hp
        again=Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(engine.export_state())))
        reactor=next(a for a in again.everyone if a.entity_id==actors['reactor'].entity_id)
        self.assertEqual(reactor.hp,hp)
        self.assertEqual(RESOURCES.pending(reactor),{'standard':1,'shift':1})

    def test_published_paid_prefix_without_profile_resumes_without_repayment_or_recheck(self):
        engine,record,actors=self.restore_legacy('paid_movement_pending')
        self.assertEqual(actors['reactor'].pos,(3,4))
        row=next(iter(engine._move_completions.values()))
        pending=row['defense'][actors['target'].entity_id]['active_attempt']['facts']
        self.assertNotIn('cost_profile',pending)
        rng=engine.rng.getstate()
        engine.grid.blocking.remove((3,3))
        with patch.object(engine,'skill_check',side_effect=AssertionError('legacy paid check must not repeat')):
            engine.deliver_passive_event(record['event_id'])
        self.assertIsNone(engine._passive_pending)
        self.assertEqual(actors['reactor'].pos,(3,2))
        self.assertEqual(actors['reactor']._action_history,['full'])
        self.assertEqual(RESOURCES.pending(actors['reactor']),{'standard':1,'shift':1})
        self.assertEqual(engine.rng.getstate(),rng)
        Engine.import_state(Rules(ROOT,ruleset='core'),json.loads(json.dumps(engine.export_state())))

    def test_legacy_full_cannot_be_relabelled_as_a_shift_without_owned_source_proof(self):
        engine,_,actors=self.restore_legacy('complete')
        row=next(iter(engine._move_completions.values()))
        attempt=row['defense'][actors['target'].entity_id]['attempts'][0]
        attempt['cost_profile']={'action':'shift','payment':'next','budget':{'shift':1},'modifier_sources':[]}
        with self.assertRaises(ValueError):engine.export_state()


if __name__=='__main__':unittest.main()
