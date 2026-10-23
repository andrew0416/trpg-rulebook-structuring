"""Missing producer-to-consumer witnesses for the seven frozen clauses only."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from engine import Combatant, Rules
from grid import Grid
import items as ITEMS
import movement_actions as MOVEMENT
import state_codec as CODEC
import state_grants as GRANTS
import survivalist_features as V
import test_category2_survivalist_csv as CSV
import test_category2_static_feature_state_grants as STATIC_FIXTURE


class CompletedSurvivalistObligations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CSV.SurvivalistCSVTests.setUpClass()
        STATIC_FIXTURE.StaticFeatureStateGrantTests.setUpClass()
        cls.r = CSV.SurvivalistCSVTests.r

    def markdown(self):
        f = CSV.SurvivalistCSVTests()
        e, a, b = f.fixture()
        for n in range(3):
            e.survivalist_activity(a, 'observe_environment', terrains=['forest'], light='normal', reason='observed actual forest night')
            e.survivalist_activity(a, 'begin_night', night_id='forest:'+str(n), terrain_name='forest', reason='actual night began')
            e.advance_time(60, [a])
            e.survivalist_activity(a, 'finish_night', night_id='forest:'+str(n), reason='actual night completed')
        e.survivalist_activity(a, 'select_terrain', terrain_name='forest', minutes=2, reason='actual Markdown Extended selection')
        GRANTS.grant(a, 'capabilities', 'Naturewalk(cave)', 'independent:cave', 'fixture')
        e.grid = Grid(1, 8, slow={(0,1),(0,2),(0,3)}, rough={(0,6)})
        MOVEMENT.observe_cell_terrain(e, [(0,y) for y in range(1,7)], ['forest'], 'actual observed forest corridor')
        e.gm.everyone = e.everyone
        return e, a, b

    def consumers(self, e, a, b, *, owns):
        self.assertEqual(MOVEMENT.naturewalk_terrains(e,a), frozenset({'forest','cave'} if owns else {'cave'}))
        self.assertEqual(MOVEMENT.ordinary_terrain(e,a,(0,1)), owns)
        self.assertFalse(MOVEMENT.ordinary_terrain(e,a,(0,7)))
        move = self.r.move('move/물대포')
        face = move['ac'] + b.evasion('특수')
        self.assertEqual(e.accuracy_check(a,b,move,fixed_roll=face)[0], owns)
        if owns:
            self.assertEqual(e.skill_roll(a,'생존',fixed=[1]*6).total, 8)
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        e.start_of_turn(a)
        e.approach(a,b)
        self.assertEqual(a.pos, (0,3) if owns else (0,1))

    def test_markdown_three_night_producer_reaches_actual_shift_accuracy_and_both_restores(self):
        e, a, b = self.markdown()
        self.assertEqual(V.selected(e,a), ('forest',))
        self.assertEqual((len(a.spec['_survivalist_nights']),e.elapsed_seconds), (3,300))
        self.assertNotIn(V.CSV_STATE,a.spec)
        payload = CODEC.dump_engine(e)
        e.gm.snapshot('Markdown-source-consumers')
        self.consumers(e,a,b,owns=True)
        e.gm.restore('Markdown-source-consumers')
        loaded = CODEC.load_engine(self.r,json.loads(json.dumps(payload)))
        self.consumers(loaded,loaded.everyone[0],loaded.everyone[1],owns=True)
        e.gm.restore('Markdown-source-consumers')
        a.spec['classes']=[]
        self.consumers(e,a,b,owns=False)
        # The independently granted cave source survives class withdrawal.
        self.assertIn('cave',MOVEMENT.naturewalk_terrains(e,a))

    def test_survivalist_producers_reject_replaced_naturewalk_before_native_shift_or_accuracy(self):
        for clause in (None, *V.CSV_CLAUSES):
            with self.subTest(source=clause or 'C04-090'):
                if clause is None:
                    e,a,b=self.markdown()
                    GRANTS.revoke(a,'independent:cave',engine=e)
                else:
                    f=CSV.SurvivalistCSVTests();e,a,b=f.fixture()
                    f.select(e,a,clause=clause);f.env(e,a,'forest')
                    e.grid=Grid(1,8,slow={(0,1),(0,2),(0,3)},rough={(0,6)})
                    MOVEMENT.observe_cell_terrain(e,[(0,y) for y in range(1,7)],['forest'],'actual forest corridor')
                e.begin_encounter(e.everyone);e.start_round(e.everyone);e.start_of_turn(a)
                original=e.r._selected_rule
                before=(a.pos,deepcopy(a.budget),e.rng.getstate())
                with patch.object(e.r,'_selected_rule',side_effect=lambda uid,**kw:'replacement/Naturewalk' if uid=='capability/자연걸음' else original(uid,**kw)):
                    with self.assertRaisesRegex(ValueError,'Naturewalk variant'):
                        MOVEMENT.naturewalk_terrains(e,a)
                    with self.assertRaisesRegex(ValueError,'Naturewalk variant'):
                        e.approach(a,b)
                    with self.assertRaisesRegex(ValueError,'Naturewalk variant'):
                        e.accuracy_check(a,b,e.r.move('move/물대포'),fixed_roll=10)
                self.assertEqual((a.pos,a.budget,e.rng.getstate()),before)

        # Owning the class alone does not produce Naturewalk or require its gate.
        f=CSV.SurvivalistCSVTests();e,a,b=f.fixture();original=e.r._selected_rule
        with patch.object(e.r,'_selected_rule',side_effect=lambda uid,**kw:'replacement/Naturewalk' if uid=='capability/자연걸음' else original(uid,**kw)):
            self.assertEqual(MOVEMENT.naturewalk_terrains(e,a),frozenset())

    def test_cold_csv_invalid_selection_preserves_durable_fingerprint_but_policy_override_does_not(self):
        f=CSV.SurvivalistCSVTests();f.r=Rules(CSV.ROOT,ruleset='all')
        e,a,b=f.fixture()
        self.assertNotIn('_survivalist_csv_policy',vars(e.r))
        before=CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError,'capacity'):
            f.select(e,a,terrains=('forest','cave'))
        self.assertIn('_survivalist_csv_policy',vars(e.r))
        self.assertEqual(CODEC.dump_engine(e),before)
        same=CODEC.rules_fingerprint(e.r)
        e.r._survivalist_csv_policy=deepcopy(V.csv_policy(e.r))
        e.r._survivalist_csv_policy['contract']['skill_bonus']=99
        self.assertNotEqual(CODEC.rules_fingerprint(e.r),same)

    def test_greenway_both_terrains_and_powder_hit_immunity_share_live_source_and_restores(self):
        f = STATIC_FIXTURE.StaticFeatureStateGrantTests()
        cid = 'C2CSV/input/db/feats.csv:R644:main'
        e,a,row,owner,field = f.fixture(cid)
        a.spec['size']='중형';a.pos=(0,0)
        stats=dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10)
        b=Combatant(e.r,dict(id='trainer/powder-source',name='Powder source',kind='trainer',size='중형',level=20,stats=stats,skills={'육상':4},movement={'land':3},moves=[]))
        b.pos=(0,3);e.everyone.append(b);e.gm.everyone=e.everyone
        e.grid=Grid(1,5,slow={(0,1),(0,2)})
        ITEMS.register_feats(e,a)
        MOVEMENT.observe_cell_terrain(e,[(0,1)],['forest'],'actual forest')
        MOVEMENT.observe_cell_terrain(e,[(0,2)],['grassland'],'actual grassland')
        MOVEMENT.observe_cell_terrain(e,[(0,4)],['wetland'],'actual unrelated wetland')
        self.assertEqual(MOVEMENT.naturewalk_terrains(e,a),frozenset({'grassland','forest'}))
        self.assertTrue(MOVEMENT.ordinary_terrain(e,a,(0,1)))
        self.assertTrue(MOVEMENT.ordinary_terrain(e,a,(0,2)))
        self.assertFalse(MOVEMENT.ordinary_terrain(e,a,(0,4)))
        payload=CODEC.dump_engine(e);e.gm.snapshot('greenway')
        for world in (e,CODEC.load_engine(self.r,json.loads(json.dumps(payload)))):
            target,attacker=world.everyone
            powder=self.r.move('move/독가루')
            self.assertFalse(world.accuracy_check(attacker,target,powder,fixed_roll=20)[0])
            water=self.r.move('move/물대포')
            self.assertTrue(world.accuracy_check(attacker,target,water,fixed_roll=20)[0])
        # A second owner of the same keyword is independent of the feature.
        GRANTS._source(a,'independent:powder','fixture')
        GRANTS.set_member(a,'keyword_immune','가루','independent:powder')
        a.spec[field].remove(owner);ITEMS.register_feats(e,a)
        self.assertEqual(MOVEMENT.naturewalk_terrains(e,a),frozenset())
        self.assertFalse(e.accuracy_check(b,a,self.r.move('move/독가루'),fixed_roll=20)[0])
        GRANTS.revoke(a,'independent:powder',engine=e)
        self.assertTrue(e.accuracy_check(b,a,self.r.move('move/독가루'),fixed_roll=20)[0])
        e.gm.restore('greenway')
        self.assertEqual(MOVEMENT.naturewalk_terrains(e,a),frozenset({'grassland','forest'}))
        self.assertFalse(e.accuracy_check(b,a,self.r.move('move/독가루'),fixed_roll=20)[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
