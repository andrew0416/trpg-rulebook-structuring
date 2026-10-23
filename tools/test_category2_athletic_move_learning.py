"""Athletic learning/table clauses, separate from static Bind's Move effects."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules, Engine
import class_move_grants as C
import encounter
import items as ITEMS
import state_grants as G
import test_category2_class_move_grants as FIXTURE

UID='feat/육상-기술'
BIND='move/조이기'


class AthleticMoveLearningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='core')

    setUp=FIXTURE.ClassMoveTests.setUp
    ranked=FIXTURE.ClassMoveTests.ranked
    register=FIXTURE.ClassMoveTests.register
    source=FIXTURE.ClassMoveTests.source

    def select(self, choices):
        self.ranked(UID,'class/운동선수',choices)

    def state(self):
        return deepcopy((self.c.spec,self.c.moves,self.c.move_uses,
            getattr(self.c,'budget',None),getattr(self.c,'_action_history',None),
            self.e.rng.getstate(),self.e.round_no,self.e.elapsed_seconds))

    def assert_atomic_rejection(self):
        before=self.state()
        with self.assertRaises(ValueError):self.register()
        self.assertEqual(self.state(),before)

    def test_later_ranks_allow_lower_choices_and_keep_exact_six_distinct_pairs(self):
        choices=[['조이기','블록'],['힘껏치기','괴력'],['누르기','돌진']]
        self.select(choices);self.register()
        expected=[[self.rules.move_id(name) for name in pair] for pair in choices]
        row=self.c.spec[G.KEY]['sources'][self.source(UID)]
        self.assertEqual(row['class_move_selection'],expected)
        self.assertCountEqual(row['grants']['moves'],[m for pair in expected for m in pair])
        self.assertEqual((row['owner_id'],row['lifetime'],row['tutor_points']),
                         (self.c.entity_id,'while_owned',0))
        before=self.state();self.register();self.assertEqual(self.state(),before)
        self.assertIn(BIND,self.c.moves)
        self.assertNotIn(BIND,encounter.usable_moves(self.e,self.c))

    def test_progression_downgrade_and_removal_preserve_permanent_and_independent_copies(self):
        G.set_baseline(self.c,'moves',['struggle',BIND])
        G.grant(self.c,'moves','move/블록','equipment:independent-block','equipment')
        self.select([['조이기','블록']]);self.register()
        self.c.spec['feat_ranks'][UID]=3
        self.c.spec['feature_choices'][UID]+=[['누르기','신속'],['메가톤킥','원수갚기']]
        self.register();self.register()
        self.assertEqual(self.c.moves.count(BIND),1)
        self.assertEqual(self.c.moves.count('move/블록'),1)
        self.assertIn('move/메가톤킥',self.c.moves)
        self.c.spec['feat_ranks'][UID]=1
        self.c.spec['feature_choices'][UID]=[['조이기','블록']]
        self.register()
        self.assertNotIn('move/메가톤킥',self.c.moves)
        self.c.spec['feats']=[];self.register()
        self.assertCountEqual(self.c.moves,['struggle',BIND,'move/블록'])
        self.assertNotIn(self.source(UID),self.c.spec[G.KEY]['sources'])
        G.revoke(self.c,'equipment:independent-block',engine=self.e)
        self.assertCountEqual(self.c.moves,['struggle',BIND])
        self.assertTrue(self.e.validate_state()['valid'])

    def test_invalid_pair_rank_history_prerequisites_and_silent_replacement_are_atomic(self):
        invalid=[[],[['조이기']],[['조이기','블록','괴력']],
            [['조이기','조이기']],[['조이기','맹독']],[['조이기','누르기']],
            [['조이기','블록'],['조이기','괴력']],
            [['조이기','블록'],['메가톤킥','누르기']]]
        for choices in invalid:
            with self.subTest(choices=choices):
                self.setUp();self.select(choices);self.assert_atomic_rejection()
        for rank, skill in ((2,4),(3,5)):
            with self.subTest(rank=rank,skill=skill):
                self.setUp()
                self.select([['조이기','블록'],['누르기','돌진'],['메가톤킥','객기']][:rank])
                self.c.spec['skills']['육상']=skill
                self.assert_atomic_rejection()
        self.setUp();self.select([['조이기','블록']]);self.c.spec['classes']=[]
        self.assert_atomic_rejection()
        self.setUp();self.select([['조이기','블록']]);self.register()
        self.c.spec['feature_choices'][UID]=[['조이기','괴력']]
        self.assert_atomic_rejection()
        self.assertIn('move/블록',self.c.moves)
        self.assertNotIn('move/괴력',self.c.moves)

    def test_missing_catalog_and_stale_or_missing_selected_source_are_atomic(self):
        for defect in ('catalog','source_hash','source_file'):
            with self.subTest(defect=defect):
                self.setUp();self.select([['조이기','블록']])
                if defect=='catalog':
                    with patch.dict(self.rules.moves):
                        self.rules.moves.pop(BIND)
                        self.assert_atomic_rejection()
                else:
                    origin=self.rules.selection.units[BIND]['source']
                    bad={'sha256':'0'*64} if defect=='source_hash' else {'file':'db/no-such-bind-source.csv'}
                    with patch.dict(origin,bad):self.assert_atomic_rejection()
                self.assertEqual(self.rules.move_id('조이기'),BIND)
                self.assertNotIn(self.source(UID),self.c.spec.get(G.KEY,{}).get('sources',{}))

    def test_fresh_rules_restore_keeps_ranked_static_identity_then_revokes_only_feature(self):
        choices=[['조이기','블록'],['누르기','돌진'],['메가톤킥','객기']]
        G.set_baseline(self.c,'moves',['struggle',BIND])
        self.select(choices);self.register()
        saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        e=Engine.import_state(Rules(ROOT,ruleset='core'),saved);c=e.everyone[0]
        self.assertEqual(c.spec['feature_choices'][UID],choices)
        self.assertEqual(e.r.move_id('조이기'),BIND)
        self.assertEqual(e.r.move(BIND)['class'],'항상')
        self.assertIn(BIND,c.moves);self.assertNotIn(BIND,encounter.usable_moves(e,c))
        source='feature:'+c.entity_id+':'+UID
        self.assertEqual(c.spec[G.KEY]['sources'][source]['class_move_selection'],
                         [[e.r.move_id(x) for x in pair] for pair in choices])
        before=(c.moves.copy(),c.move_uses.copy(),e.rng.getstate())
        ITEMS.register_feats(e,c)
        self.assertEqual(before,(c.moves,c.move_uses,e.rng.getstate()))
        c.spec['feats']=[];ITEMS.register_feats(e,c)
        self.assertCountEqual(c.moves,['struggle',BIND])
        self.assertTrue(e.validate_state()['valid'])

    def test_actually_learned_bind_cannot_be_activated_or_consume_costs(self):
        self.select([['조이기','블록']]);self.register()
        self.assertIn(BIND,self.c.spec[G.KEY]['sources'][self.source(UID)]['grants']['moves'])
        self.e.start_round([self.c]);self.e.start_of_turn(self.c,initiative_count=10)
        before=self.e.export_state()
        with self.assertRaisesRegex(ValueError,'static learned Move'):
            self.e.use_move(self.c,self.c,BIND)
        self.assertEqual(self.e.export_state(),before)
        self.assertNotIn(BIND,encounter.usable_moves(self.e,self.c))


if __name__=='__main__':unittest.main()
