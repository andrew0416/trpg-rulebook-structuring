"""Survivalist class template: actual static acquisition of the class and its five Features."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from native_scenario_fixture import assert_rejected_unchanged
import book_survivalist_fixture as FIX
import acquired_features as ACQUIRED
import survivalist_class as SC
import survivalist_features as V
import trainer_feature_acquisition as ACQUIRE
import items as I


class SurvivalistAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        SC.definitions(self.rules)

    def rejected(self, engine, operation, pattern):
        return assert_rejected_unchanged(engine, operation, reason_pattern=pattern)

    def test_template_binds_six_definitions_to_the_printed_clauses_and_class_acquisition_grants_no_feature(self):
        data = SC.definitions(self.rules)
        lines = (ROOT / 'input/ch04-trainer-classes.md').read_text(encoding='utf-8-sig').split('\n')
        self.assertEqual(hashlib.sha256((ROOT / 'input/ch04-trainer-classes.md').read_bytes()).hexdigest(), data['source_sha256'])
        expected = {SC.CLASS: (2142, 2144, 'C04-090'), SC.NATURAL: (2146, 2154, 'C04-091'), SC.TRAPPER: (2156, 2164, 'input/ch04-trainer-classes.md:2156-2164'),
                    SC.GUIDE: (2166, 2175, 'input/ch04-trainer-classes.md:2166-2175'), SC.TALENT: (2177, 2185, 'C04-092'), SC.ADAPTIVE: (2187, 2193, 'C04-093')}
        for uid, (start, end, clause) in expected.items():
            row = SC.STATIC_DEFINITIONS[uid]
            self.assertEqual((tuple(row['span']), row['clause_id']), ((start, end), clause))
            excerpt = '\n'.join(lines[start - 1:end])
            self.assertEqual(hashlib.sha256(excerpt.encode('utf-8')).hexdigest(), row['excerpt_sha256'])
            self.assertEqual(self.rules.selection.units[uid]['source']['lines'], row['catalog_span'])
            self.assertIn(uid, ACQUIRE.STATIC_FEATURES)
            self.assertEqual(ACQUIRE.STATIC_FEATURES[uid]['class_template'], SC.CLASS)
        self.assertTrue(ACQUIRE.STATIC_FEATURES[SC.TALENT]['ranked'])
        table = data['talents']
        self.assertEqual((tuple(table['span']), table['clause_id']), ((2195, 2197), 'C04-094'))
        self.assertEqual(hashlib.sha256('\n'.join(lines[2194:2197]).encode('utf-8')).hexdigest(), table['excerpt_sha256'])
        self.assertEqual(set(table['effects']), set(SC.TERRAINS))
        self.assertEqual(SC.CYCLE, ('grassland', 'forest', 'wetland', 'ocean', 'tundra', 'mountain', 'cave', 'urban', 'desert'))
        self.assertTrue(SC.adjacent('desert', 'grassland') and SC.adjacent('wetland', 'forest') and SC.adjacent('wetland', 'ocean'))
        self.assertFalse(SC.adjacent('wetland', 'cave'))
        world = FIX.scene(self.rules, feats=(SC.CLASS,))
        trainer = world['trainer']
        self.assertEqual(trainer.spec['feats'], [SC.CLASS])
        self.assertEqual(ACQUIRED.owned_rule_count(trainer, SC.CLASS), 1)
        for uid in expected:
            if uid != SC.CLASS:
                self.assertEqual(ACQUIRED.owned_rule_count(trainer, uid), 0)
        self.assertEqual(V.feature_count(world['engine'], trainer), 1)
        I.register_feats(world['engine'], trainer)
        self.assertTrue(world['engine'].validate_state()['valid'])

    def test_prerequisites_use_survival_ranks_parent_receipts_mastered_terrains_and_four_features(self):
        world = FIX.scene(self.rules, feats=(), survival=2)
        engine, trainer = world['engine'], world['trainer']
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.CLASS), 'printed Survival rank required')
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.TRAPPER), 'actual acquired class')
        engine.gm.set_skill(trainer, '생존', 3, reason='actual Novice Survival')
        receipt = FIX.acquire(engine, trainer, SC.CLASS)
        self.assertEqual((receipt['status'], receipt['snapshot']), ('acquired', {'survival': 3, 'parents': []}))
        self.rejected(engine, lambda: ACQUIRE.acquire_static(engine, trainer, SC.CLASS, acquisition_request_id='second'), 'already acquired')
        self.assertEqual(FIX.acquire(engine, trainer, SC.NATURAL)['snapshot']['parents'], ['survivalist/' + trainer.entity_id + '/' + SC.CLASS])
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.TRAPPER), 'printed Survival rank required')
        engine.gm.set_skill(trainer, '생존', 4, reason='actual Adept Survival')
        FIX.acquire(engine, trainer, SC.TRAPPER)
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.GUIDE), 'printed Survival rank required')
        engine.gm.set_skill(trainer, '생존', 5, reason='actual Expert Survival')
        FIX.acquire(engine, trainer, SC.GUIDE)
        self.assertEqual(V.feature_count(engine, trainer), 4)
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.ADAPTIVE), 'printed Survival rank required')
        engine.gm.set_skill(trainer, '생존', 6, reason='actual Master Survival')
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.TALENT, rank=2), 'next actual rank')
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.TALENT), 'explicit acquired rank')
        FIX.master(engine, trainer, 'cave')
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.TALENT, rank=1), 'requires 2 mastered terrains')
        FIX.master(engine, trainer, 'forest')
        first = FIX.acquire(engine, trainer, SC.TALENT, rank=1)
        self.assertEqual((first['snapshot']['rank_number'], first['snapshot']['previous'], sorted(first['snapshot']['mastered_terrains'])), (1, None, ['cave', 'forest']))
        self.assertEqual(trainer.spec['feat_ranks'][SC.TALENT], 1)
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.TALENT, rank=2), 'requires 4 mastered terrains')
        adaptive = FIX.acquire(engine, trainer, SC.ADAPTIVE)
        self.assertEqual(len(adaptive['snapshot']['survivalist_features']), 5)
        self.assertEqual(V.feature_count(engine, trainer), 6)
        FIX.master(engine, trainer, 'mountain')
        self.rejected(engine, lambda: FIX.acquire(engine, trainer, SC.TALENT, rank=2), 'requires 4 mastered terrains')
        FIX.master(engine, trainer, 'urban')
        second = FIX.acquire(engine, trainer, SC.TALENT, rank=2)
        self.assertEqual((second['snapshot']['rank_number'], second['snapshot']['previous']), (2, first['request_id']))
        self.assertEqual(trainer.spec['feat_ranks'][SC.TALENT], 2)
        self.assertEqual(V.feature_count(engine, trainer), 7)
        other = Combatant(self.rules, FIX.trainer_spec(self.rules, 'three', survival=6))
        engine.gm.add_combatant(other, pos=(9, 6), side='party', reason='trainer with three Survivalist Features')
        for uid in (SC.CLASS, SC.NATURAL, SC.TRAPPER):
            FIX.acquire(engine, other, uid)
        self.rejected(engine, lambda: FIX.acquire(engine, other, SC.ADAPTIVE), 'four acquired Survivalist Features required')
        self.assertTrue(engine.validate_state()['valid'])

    def test_acquired_receipts_feed_the_existing_terrain_thresholds_and_survive_both_restores(self):
        world = FIX.scene(self.rules, feats=(SC.CLASS,))
        engine, trainer = world['engine'], world['trainer']
        FIX.master(engine, trainer, 'cave')
        for n in range(3):
            FIX.night(engine, trainer, 'forest', 'forest-night-' + str(n))
        self.rejected(engine, lambda: engine.survivalist_activity(trainer, 'select_terrain', terrain_name='forest', minutes=1, reason='GM'), 'two, four or six acquired features')
        FIX.acquire(engine, trainer, SC.NATURAL)
        engine.survivalist_activity(trainer, 'select_terrain', terrain_name='forest', minutes=1, reason='GM second terrain')
        FIX.acquire(engine, trainer, SC.TRAPPER)
        for n in range(3):
            FIX.night(engine, trainer, 'urban', 'urban-night-' + str(n))
        self.rejected(engine, lambda: engine.survivalist_activity(trainer, 'select_terrain', terrain_name='urban', minutes=1, reason='GM'), 'two, four or six acquired features')
        FIX.acquire(engine, trainer, SC.GUIDE)
        engine.survivalist_activity(trainer, 'select_terrain', terrain_name='urban', minutes=1, reason='GM third terrain')
        self.assertEqual(V.selected(engine, trainer), ('cave', 'forest', 'urban'))
        FIX.talents(engine, trainer, 'cave', 'forest')
        self.assertEqual(V.talents(engine, trainer), ('cave', 'forest'))
        self.assertEqual(V.feature_count(engine, trainer), 5)
        FIX.acquire(engine, trainer, SC.ADAPTIVE)
        self.assertEqual(V.feature_count(engine, trainer), 6)
        FIX.master(engine, trainer, 'mountain')
        self.assertEqual(len(V.selected(engine, trainer)), 4)
        receipts = deepcopy(trainer.spec['state_grants'])
        engine.gm.snapshot('acquired')
        trainer.spec['feats'].remove(SC.GUIDE)
        self.assertFalse(engine.validate_state()['valid'])
        engine.gm.restore('acquired')
        self.assertTrue(engine.validate_state()['valid'])
        loaded, index = FIX.restore(self.rules, engine)
        again = index[trainer.entity_id]
        self.assertEqual(again.spec['state_grants'], receipts)
        self.assertEqual(V.selected(loaded, again), ('cave', 'forest', 'urban', 'mountain'))
        self.assertEqual(V.talents(loaded, again), ('cave', 'forest'))
        self.assertEqual(V.feature_count(loaded, again), 6)
        self.assertTrue(loaded.validate_state()['valid'])


if __name__ == '__main__':
    unittest.main()
