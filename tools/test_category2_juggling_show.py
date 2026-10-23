"""Juggling Show uses native introduction dice, ownership and atomic resolution."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon,build_trainer
from engine import Rules,Engine,Combatant
from contest import ContestRules,ContestEngine,Contestant
import contest_features as FEATURES
import items as ITEMS
import world_entities as WORLD

SOURCE=FEATURES.JUGGLING_SHOW

class Sequence:
    def __init__(self,faces):self.faces=list(faces)
    def randint(self,a,b):
        value=self.faces.pop(0)
        if not a<=value<=b:raise ValueError('invalid supplied face')
        return value

class JugglingShowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='all')
        cls.contest_rules=ContestRules(ROOT)

    def setUp(self):self.fixture()

    def fixture(self,rank=5,alias=SOURCE,rules=None):
        rules=rules or self.rules
        self.e=Engine(rules,seed=149)
        self.t=Combatant(rules,build_trainer(rules,'Juggling trainer',30,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),moves=[],abilities=[],
            extra={'feats':[alias],'skills':{'매력':3,'곡예':rank}}))
        self.p=Combatant(rules,build_pokemon(rules,'브케인',20,moves=['몸통박치기'],
            abilities=[],extra={'trainer_id':self.t.entity_id}))
        self.e.gm.add_combatant(self.t)
        self.e.gm.add_combatant(self.p)
        self.c=ContestEngine(self.contest_rules,seed=150)

    def declare(self,stat='슬기로움',choices=None):
        if choices is None:choices={SOURCE:stat}
        return self.c.contestant_from_combatants(self.e,self.p,self.t,'매력',{},bonus_stats=choices)

    def before(self,contestant):
        return deepcopy(vars(contestant)),list(self.c.log_lines),self.c.rng.getstate()

    def test_all_five_bonus_stats_are_independent_of_the_introduction_skill(self):
        for stat in FEATURES.STATS:
            with self.subTest(stat=stat):
                self.fixture()
                c=self.declare(stat)
                self.c.rng=Sequence([1,1,1,3,6])
                self.c.intro_stage([c],'귀여움')
                expected={'귀여움':0}
                expected[stat]=expected.get(stat,0)+2
                self.assertEqual(c.stat_dice,expected)
                self.assertEqual(c.appeal,2)
                self.assertTrue(c.intro_completed)

    def test_actual_acrobatics_rank_is_halved_with_floor_for_all_six_ranks(self):
        for rank in range(1,7):
            with self.subTest(rank=rank):
                self.fixture(rank)
                c=self.declare()
                self.c.rng=Sequence([1]*3+[3]*(rank//2))
                self.c.intro_stage([c],'귀여움')
                self.assertEqual(c.stat_dice,{'귀여움':0,'슬기로움':rank//2})
                self.assertEqual(self.c.rng.faces,[])

    def test_virtuoso_acrobatics_recomputes_four_real_introduction_dice_after_restore(self):
        import skill_modifiers as SKILL,state_grants as GRANTS
        self.fixture(rank=6)
        GRANTS.transition(self.e,self.t,lambda e,t:t.spec.update(
            edges=[*t.spec.get("edges",[]),"edge/거장"],edge_choices={"edge/거장":["곡예"]}))
        self.assertEqual(SKILL.effective_rank(self.e.r,self.t,"곡예"),8)
        ids=self.t.entity_id,self.p.entity_id
        self.e=Engine.import_state(Rules(str(self.e.r.root),ruleset="all"),json.loads(json.dumps(self.e.export_state())))
        actors=WORLD.actor_index(self.e);self.t,self.p=[actors[uid] for uid in ids]
        self.assertEqual(SKILL.rank(self.e.r,self.t,"곡예")[2],6)
        contestant=self.declare()
        self.c.rng=Sequence([1]*3+[3]*4);self.c.intro_stage([contestant],"귀여움")
        self.assertEqual(contestant.stat_dice,{"귀여움":0,"슬기로움":4})
        self.assertEqual(self.c.rng.faces,[])

    def test_bonus_can_be_declined_without_changing_ordinary_introduction(self):
        c=self.declare(choices={})
        self.c.rng=Sequence([3,2,6])
        self.c.intro_stage([c],'귀여움')
        self.assertEqual(c.stat_dice,{'귀여움':2})
        self.assertNotIn(SOURCE,c.intro_sources)

    def test_real_acquired_aliases_share_one_source_and_one_bonus(self):
        for alias in (SOURCE,'저글링 쇼','Juggling Show'):
            with self.subTest(alias=alias):
                self.fixture(alias=alias)
                c=self.declare()
                self.assertEqual(c.intro_sources,{SOURCE})
                self.c.rng=Sequence([1,1,1,2,3])
                self.c.intro_stage([c],'귀여움')
                self.assertEqual(c.stat_dice,{'귀여움':0,'슬기로움':1})

    def test_unowned_wrong_owner_and_invalid_stat_reject_before_randomness(self):
        for change in ('unowned','foreign','invalid_stat'):
            with self.subTest(change=change):
                self.fixture()
                if change=='unowned':self.t.spec['feats'].clear()
                if change=='foreign':self.p.spec['trainer_id']='foreign'
                before=self.c.rng.getstate()
                with self.assertRaises(ValueError):
                    c=self.declare('공격' if change=='invalid_stat' else '슬기로움')
                    self.c.intro_stage([c],'귀여움')
                self.assertEqual(self.c.rng.getstate(),before)

    def test_withdrawal_rank_and_owner_changes_invalidate_prepared_roll_atomically(self):
        for change in ('withdrawal','rank','owner'):
            with self.subTest(change=change):
                self.fixture()
                c=self.declare()
                if change=='withdrawal':self.t.spec['feats'].clear()
                if change=='rank':self.t.spec['skills']['곡예']=6
                if change=='owner':self.p.spec['trainer_id']='foreign'
                before=self.before(c)
                with self.assertRaises(ValueError):self.c.intro_stage([c],'귀여움')
                self.assertEqual(self.before(c),before)

    def test_forged_bonus_and_inflated_native_dice_reject_without_state_change(self):
        for native in (False,True):
            with self.subTest(native=native):
                self.fixture()
                if native:
                    c=self.declare();c.intro_bonuses[0]['dice']=99
                else:
                    c=Contestant('forged',{},['move/몸통박치기'],'매력',3,'귀여움',
                        intro_sources=[SOURCE],intro_bonuses=[{'source_id':SOURCE,'stat':'슬기로움','dice':2}])
                before=self.before(c)
                with self.assertRaises(ValueError):self.c.intro_stage([c],'귀여움')
                self.assertEqual(self.before(c),before)

    def test_equipped_item_bonus_keeps_its_own_dice_and_destination(self):
        ITEMS.register_item(self.e,self.p,'콘테스트 장신구')
        c=self.declare(choices={SOURCE:'슬기로움','item/콘테스트-장신구':'강인함'})
        self.c.rng=Sequence([1,1,1,3,1,3,6])
        self.c.intro_stage([c],'귀여움')
        self.assertEqual(c.stat_dice,{'귀여움':0,'강인함':1,'슬기로움':2})

    def test_gm_and_json_restore_preserve_real_owners_and_rank_before_introduction(self):
        ids=self.t.entity_id,self.p.entity_id
        snapshot=self.e.gm.snapshot()
        self.e.gm.restore(snapshot)
        self.e=Engine.import_state(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        actors=WORLD.actor_index(self.e)
        self.t,self.p=[actors[uid] for uid in ids]
        c=self.declare()
        self.c.rng=Sequence([1,1,1,3,4])
        self.c.intro_stage([c],'귀여움')
        self.assertEqual(c.stat_dice,{'귀여움':0,'슬기로움':2})

    def test_introduction_is_consumed_once_and_later_withdrawal_keeps_earned_dice(self):
        c=self.declare()
        self.c.rng=Sequence([1,1,1,3,6])
        self.c.intro_stage([c],'귀여움')
        self.t.spec['feats'].clear()
        earned=deepcopy(c.stat_dice)
        with self.assertRaises(ValueError):self.c.intro_stage([c],'귀여움')
        self.assertEqual(c.stat_dice,earned)
        self.c=ContestEngine(self.contest_rules,seed=151)
        future=self.declare(choices={})
        self.assertNotIn(SOURCE,future.intro_sources)

if __name__=='__main__':unittest.main()
