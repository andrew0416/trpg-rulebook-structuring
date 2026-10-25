"""Actual alternate Poke Edge producers retain their own source guards."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import poke_edge_variants as VARIANTS
import pokemon_capability_edges as CAPABILITIES
import advanced_connection as CONNECTION
import test_book_mentor_full as MENTOR_FIXTURE
import test_connection_birth as BIRTH_FIXTURE


class NativeProducerHistoryTests(unittest.TestCase):
    def test_actual_mentor_lesson_preserves_waiver_but_rejects_forged_history_sources(self):
        case=MENTOR_FIXTURE.MentorFullTests('runTest')
        case.r=Rules(ROOT,ruleset='core');case.setUp()
        case.lessons();pupil=case.pupil(level=5,tp=1)
        result=case.lesson(pupil,'empowered',edges=case.edges(pupil))
        self.assertEqual((result['point_cost'],pupil.spec['tutor_points']), (1,0))
        receipt=next(row for row in pupil.spec['learned_poke_edges'] if row['source']==CAPABILITIES.MOBILITY)
        VARIANTS.validate_receipt(case.r,receipt,history=True,minimum_level=20)
        before=case.e.export_state()
        for changes in ({'training_source':'invented'}, {'mentor_source_id':'forged'}, {'point_cost':1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                VARIANTS.validate_receipt(case.r,dict(deepcopy(receipt),**changes),history=True,minimum_level=20)
        ordinary=deepcopy(receipt);ordinary.pop('mentor_source_id')
        ordinary['training_source']='input/ch05-pokemon.md:274'
        with self.assertRaises(ValueError):
            VARIANTS.validate_receipt(case.r,ordinary,history=True,minimum_level=20)
        self.assertEqual(case.e.export_state(),before)
        self.assertTrue(case.e.validate_state()['valid'])

    def test_actual_connection_birth_keeps_paid_immediate_source_and_rejects_other_edges(self):
        case=BIRTH_FIXTURE.ConnectionBirthTests('runTest')
        case.r=Rules(ROOT,ruleset='core');case.setUp();self.addCleanup(case.doCleanups)
        egg=case.create(True)
        def choose(prompt):
            if prompt.get('type')==CONNECTION.PROMPT:
                return {'actor_id':prompt['actor_id'],'ability':prompt['ability'],'advanced_connection':True}
        case.r.rulings.provider=choose
        before_seconds=case.e.elapsed_seconds
        child=case.hatch(egg,True);receipt=CONNECTION.records(child.spec)[0]
        self.assertEqual((receipt['training_source'],receipt['point_cost'],child.spec['tutor_points']),
                         (CONNECTION.KEYWORD,1,0))
        self.assertEqual(case.e.elapsed_seconds,before_seconds)
        VARIANTS.validate_receipt(case.r,receipt,history=True,minimum_level=1)
        before=case.e.export_state()
        for changes in ({'source':CAPABILITIES.TRAINING},{'point_cost':0},{'ability':'ability/not-a-source'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                VARIANTS.validate_receipt(case.r,dict(deepcopy(receipt),**changes),history=True,minimum_level=1)
        self.assertEqual(case.e.export_state(),before)
        self.assertTrue(case.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
