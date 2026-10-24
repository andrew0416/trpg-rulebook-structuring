"""FAN117: the real ranked Swarmlord identity reaches native stat projection."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest

from engine import Rules
from ruleset import ExcludedRuleSelection
import ability_transitions as ABILITIES
import acquired_features as ACQUIRED
import items as ITEMS
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import state_grants as G
import static_feature_state_grants as STATIC

ROOT=Path(__file__).resolve().parents[1]
OWNER='supp-fantasy/벌레-원소술사-무리군주'
FEATURE='feat/강화된-포용'
BROOD='feat/무리어미'
CID='C2CSV/input/db/feats.csv:R587:main'
BRANCHES={'거미의 포용':'atk','군주의 포용':'spa'}


class StrengthenedEmbraceSourceRevisionTests(unittest.TestCase):
    def world(self,branch='거미의 포용',*,rank=2,alias=FEATURE,brood=True,baseline=False):
        self.branch=branch;self.stat=BRANCHES[branch]
        extra={'feats':[OWNER,alias]+([BROOD] if brood else []),
               'feat_ranks':{FEATURE:rank},'static_feature_choices':{OWNER:branch},
               'skills':{'명령':5,'생존':5},
               'edges':['edge/원소-교감'],'edge_choices':{'edge/원소-교감':'벌레'},
               'movement':{'land':4,'power':2},'movement_basis':'current'}
        sheet={'name':'actual Swarmlord','level':40,
               'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
               'moves':['move/몸통박치기'],'abilities':['긴장감'] if baseline else [],
               'pos':(2,2),'side':'party','extra':extra}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='all',seed=117121,
            grid={'width':12,'height':10},actors=[{'key':'swarmlord','kind':'trainer','sheet':sheet,
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual declared Swarmlord body'}}])
        self.a=actors['swarmlord']

    def assert_count(self,count):
        self.assertEqual(self.a.stats[self.stat],10+count)
        self.assertEqual(self.a.stats['spa' if self.stat=='atk' else 'atk'],10)
        self.assertEqual(STATIC.class_branch(self.a,OWNER),self.branch)
        source='static-feature:'+self.a.entity_id+':'+CID
        receipt=self.a.spec[G.KEY]['stat_sources'][self.stat]['sources'][source]
        self.assertEqual(receipt['feature_count'],{'delta':count,'minimum':None})
        self.assertTrue(STATIC.validate(self.a))

    def test_source_identity_aliases_rank_three_and_fantasy_admission(self):
        self.world();unit=self.e.r.selection.units[FEATURE]
        self.assertEqual((unit['title'],unit['eng'],unit['kind']),
                         ('강화된 포용','Enhanced Embrace','entity:feat'))
        self.assertIn('랭크 3',unit['tags'])
        self.assertEqual(unit['source']['lines'],[923,939])
        self.assertEqual(unit['source']['path'][-1],'벌레 원소술사: 무리군주')
        self.assertEqual(unit['source']['sha256'],
                         'a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266')
        self.assertEqual(self.e.r._selected_rule(FEATURE),FEATURE)
        core=Rules(str(ROOT),ruleset='core')
        with self.assertRaises(ExcludedRuleSelection):core._selected_rule(FEATURE)

    def test_each_real_acquired_rank_counts_for_both_native_embrace_stats(self):
        for branch in BRANCHES:
            for rank in (1,2,3):
                with self.subTest(branch=branch,rank=rank):
                    self.world(branch,rank=rank)
                    self.assertEqual(ACQUIRED.feature_rank(self.a,FEATURE),rank)
                    self.assert_count(1+rank+1)
                    before=deepcopy((self.a.stats,self.a.spec[G.KEY],self.e.rng.getstate()))
                    ITEMS.register_feats(self.e,self.a)
                    self.assertEqual((self.a.stats,self.a.spec[G.KEY],self.e.rng.getstate()),before)
                    self.assertTrue(self.e.validate_state()['valid'])

    def test_korean_english_and_canonical_aliases_reach_the_same_owned_rank(self):
        for branch in BRANCHES:
            for alias in (FEATURE,'강화된 포용','Enhanced Embrace'):
                with self.subTest(branch=branch,alias=alias):
                    self.world(branch,alias=alias)
                    self.assertEqual(ACQUIRED.owned_rule_count(self.a,FEATURE),2)
                    self.assert_count(4)

    def test_rank_changes_and_withdrawal_reconcile_without_retaining_extra_tags(self):
        for branch in BRANCHES:
            with self.subTest(branch=branch):
                self.world(branch,rank=1,brood=False)
                for rank in (3,2,1):
                    self.a.spec['feat_ranks'][FEATURE]=rank
                    ITEMS.register_feats(self.e,self.a);self.assert_count(1+rank)
                self.a.spec['feats'].remove(FEATURE)
                ITEMS.register_feats(self.e,self.a);self.assert_count(1)
                self.a.spec['feats'].remove(OWNER)
                ITEMS.register_feats(self.e,self.a)
                self.assertEqual(self.a.stats[self.stat],10)
                self.assertIsNone(STATIC.class_branch(self.a,OWNER))
                self.assertTrue(self.e.validate_state()['valid'])

    def test_duplicate_aliases_bad_ranks_and_unselected_variant_cannot_mutate_projection(self):
        for invalid in ('duplicate',0,4,True,1.5):
            with self.subTest(invalid=invalid):
                self.world()
                if invalid=='duplicate':self.a.spec['feats'].append('Enhanced Embrace')
                else:self.a.spec['feat_ranks'][FEATURE]=invalid
                before=deepcopy((self.a.spec,self.a.stats,self.a.abilities,self.e.rng.getstate()))
                with self.assertRaises(ValueError):ITEMS.register_feats(self.e,self.a)
                self.assertEqual((self.a.spec,self.a.stats,self.a.abilities,self.e.rng.getstate()),before)
        self.world();selected=self.e.r._selected_rule
        before=deepcopy((self.a.spec,self.a.stats,self.a.abilities,self.e.rng.getstate()))
        with patch.object(self.e.r,'_selected_rule',side_effect=lambda uid: 'other' if uid==FEATURE else selected(uid)):
            with self.assertRaisesRegex(ValueError,'selected feature variant'):
                ITEMS.register_feats(self.e,self.a)
        self.assertEqual((self.a.spec,self.a.stats,self.a.abilities,self.e.rng.getstate()),before)

    def test_gm_and_json_restore_preserve_ranked_tags_and_independent_ability(self):
        for branch in BRANCHES:
            with self.subTest(branch=branch):
                self.world(branch,rank=3,brood=False,baseline=True);self.assert_count(4)
                self.e.gm.snapshot('embrace');self.a.hp-=1
                self.e.gm.restore('embrace',reason='restore actual ranked Swarmlord')
                self.e=CODEC.load_engine(self.e.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
                self.a=self.e.everyone[0];self.assert_count(4)
                self.a.spec['feats'].remove(FEATURE)
                ITEMS.register_feats(self.e,self.a);self.assert_count(1)
                self.a.spec['feats'].remove(OWNER)
                ITEMS.register_feats(self.e,self.a)
                self.assertEqual(self.a.stats[self.stat],10)
                self.assertIn('ability/긴장감',ABILITIES.known(self.a))
                self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main(verbosity=2)
