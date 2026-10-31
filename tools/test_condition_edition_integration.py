"""Source-derived editions compose with the modern failed-save owner."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
from native_scenario_fixture import assert_rejected_unchanged
import test_paralysis_failed_action_source_revision as MODERN
import condition_editions as EDITIONS
import combat_timing as CLOCK
import paralysis_state as PARALYSIS
import turn as TURN


class ConditionEditionIntegrationTests(unittest.TestCase):
    scene=MODERN.ParalysisFailedActionSourceRevisionTests.scene
    begin=MODERN.ParalysisFailedActionSourceRevisionTests.begin

    def setUp(self):
        self.r=Rules(ROOT,ruleset='core')

    def test_exact_auxiliary_csv_metadata_keeps_modern_dc11_fingerprint_and_children(self):
        data=self.r.units['condition/마비']['mech']['data']
        base={key:deepcopy(value) for key,value in data.items() if key!=EDITIONS.CSV_VERSION}
        with patch.dict(data,{EDITIONS.CSV_VERSION:EDITIONS.edition('마비')}):
            self.r.touch('units')   # edit inside an existing unit declared
            e,a,_=self.scene()
            self.begin(e,a,face=10)
            child=next(row for row in CLOCK.records(a) if 'paralysis_failed_save' in row)
            self.assertEqual(child['paralysis_failed_save']['check']['base_dc'],11)
            self.assertEqual(child['paralysis_failed_save']['source'],PARALYSIS.SOURCE)
            self.assertEqual(PARALYSIS.DEFINITION,'fac3ee002d5cd74477a195a75a3813f26e2e96b0c2849a996d288435cacc2495')
            self.assertIn('취약',a.conditions)
            self.assertIn('attack_of_opportunity',child['forbidden_actions'])
            self.assertTrue(TURN.spend(e,a,'swift'))
            self.assertTrue(TURN.spend(e,a,'standard'))
            self.assertFalse(TURN.spend(e,a,'shift'))
        self.assertEqual({key:value for key,value in data.items() if key!=EDITIONS.CSV_VERSION},base)

    def test_unreviewed_auxiliary_metadata_and_changed_base_refuse_before_save_or_turn(self):
        data=self.r.units['condition/마비']['mech']['data']
        changed=EDITIONS.edition('마비');changed['effects'][1]['dc']=6
        for metadata,change_base in ((changed,False),(EDITIONS.edition('마비'),True)):
            with self.subTest(change_base=change_base):
                with patch.dict(data,{EDITIONS.CSV_VERSION:metadata}):
                    self.r.touch('units')   # edit inside an existing unit declared
                    effects=deepcopy(data['effects'])
                    if change_base:next(effect for effect in effects if effect['type']=='save')['dc']=12
                    with patch.dict(data,{'effects':effects}):
                        self.r.touch('units')
                        e,a,_=self.scene();e.apply_status(a,'마비');e.start_round(e.everyone)
                        with patch.object(Engine,'d20',return_value=10) as rolled:
                            assert_rejected_unchanged(e,lambda:e.start_of_turn(a,initiative_count=20),
                                reason_pattern='unreviewed CSV Paralysis|modern Paralysis selected definition changed')
                        self.assertEqual(rolled.call_count,0)
                        self.assertFalse(CLOCK.records(a));self.assertIsNone(e._active_turn_actor)

    def test_selected_csv_dc5_has_no_modern_failed_save_children_and_keeps_free_action(self):
        self.r=Rules(ROOT,ruleset='core-csv-status-1.05')
        e,a,_=self.scene();self.begin(e,a,face=4)
        self.assertNotIn('취약',a.conditions)
        self.assertFalse(any('paralysis_failed_save' in row for row in CLOCK.records(a)))
        for kind in ('standard','shift','swift','full'):self.assertFalse(TURN.spend(e,a,kind))
        self.assertTrue(TURN.spend(e,a,'free'))
        self.assertTrue(e.validate_state()['valid'])

    def test_derivation_requires_actual_authenticated_sources_and_exact_existing_metadata(self):
        with patch.dict(EDITIONS.TM,{'sha256':'0'*64}):
            with self.assertRaisesRegex(ValueError,'source changed; review required'):
                Rules(ROOT,ruleset='core-csv-status-1.05')
        with patch.dict(EDITIONS.CORE,{'sha256':'0'*64}):
            with self.assertRaisesRegex(ValueError,'source changed; review required'):
                Rules(ROOT,ruleset='core-csv-frozen-homebrew')
        rules=Rules(ROOT,ruleset='core-csv-frozen-homebrew')
        data=rules.units['condition/얼음']['mech']['data']
        altered=deepcopy(data['csv-homebrew']);altered['effects'][0]['type']='unreviewed_no_actions'
        with patch.dict(data,{'csv-homebrew':altered}):
            rules.touch('units')   # edit inside an existing unit declared
            with self.assertRaisesRegex(ValueError,'reviewed CSV condition edition changed'):
                EDITIONS.install(rules)
        malformed=deepcopy(data['csv-homebrew']);malformed['effects'][0]['type']='no_actions';malformed['effects'][0]['value']=True
        with patch.dict(data,{'csv-homebrew':malformed}):
            with self.assertRaisesRegex(ValueError,'reviewed CSV condition edition changed'):
                EDITIONS.install(rules)


if __name__=='__main__':unittest.main()
