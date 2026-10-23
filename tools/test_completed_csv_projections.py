"""Pure source-rights projections whose N2 consumer is the returned view."""
import unittest
import json
from engine import Engine
import world_entities as WORLD
import csv_item_capability_contracts as CAP
import state_grants as GRANTS
import test_category2_csv_remaining_item_contracts as _fixture_test_category2_csv_remaining_item_contracts


class CompletedCsvProjectionTests(unittest.TestCase):
    setUpClass = classmethod(_fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.setUpClass.__func__)
    pokemon = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.pokemon
    fixture = _fixture_test_category2_csv_remaining_item_contracts.RemainingCsvItemContractTests.fixture

    def test_toxicity_all_steps_precedence_and_live_source_revocation(self):
        actor=self.pokemon('actual-toxic-observer')
        e=self.fixture(actor)
        effects={'low':['irritation'],'middle':['breath difficulty'],'high':['severe poison exposure']}
        def project(expected):
            for toxicity,negatives in zip(('low','middle','high'),expected):
                self.assertEqual(CAP.toxic_environment(actor,toxicity,effects)['negative_effects'],negatives)
        project([effects['low'],effects['middle'],effects['high']])
        GRANTS.grant(actor,'capabilities','함정내성','csv/toxic-resistance','capability',
                     rule_id='C2CSV/item-data:26:5',lifetime='owned')
        project([[],effects['low'],effects['middle']])
        GRANTS.grant(actor,'capabilities','함정면역','csv/toxic-immunity','capability',
                     rule_id='C2CSV/item-data:25:5',lifetime='owned')
        project([[],[],[]])
        e=Engine.import_state(self.r,json.loads(json.dumps(e.export_state())))
        actor=WORLD.actor_index(e)[actor.entity_id]
        project([[],[],[]])
        GRANTS.revoke(actor,'csv/toxic-immunity',engine=e)
        project([[],effects['low'],effects['middle']])
        GRANTS.revoke(actor,'csv/toxic-resistance',engine=e)
        project([effects['low'],effects['middle'],effects['high']])
        self.assertEqual(effects,{'low':['irritation'],'middle':['breath difficulty'],'high':['severe poison exposure']})
        with self.assertRaises(ValueError):
            CAP.toxic_environment(actor,'unknown',effects)
        with self.assertRaises(ValueError):
            CAP.toxic_environment(actor,'high',None)

    def test_language_two_independent_sources_do_not_erase_each_others_rights(self):
        actor=self.pokemon('actual-language-user')
        e=self.fixture(actor)
        self.assertIsNone(CAP.language(actor))
        for source in ('csv/language-a','csv/language-b'):
            GRANTS.grant(actor,'capabilities','언어',source,'capability',
                         rule_id='C2CSV/item-data:81:5',lifetime='owned')
        e=Engine.import_state(self.r,json.loads(json.dumps(e.export_state())))
        actor=WORLD.actor_index(e)[actor.entity_id]
        GRANTS.revoke(actor,'csv/language-a',engine=e)
        result=CAP.language(actor)
        self.assertTrue(result['understands_human'])
        self.assertTrue(result['speaks_human'])
        self.assertEqual(result['source'],'C2CSV/item-data:81:5')
        GRANTS.revoke(actor,'csv/language-b',engine=e)
        self.assertIsNone(CAP.language(actor))
