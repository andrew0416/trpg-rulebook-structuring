"""Already-counted Fantasy ranked Features: exact +Speed stat consumers.

These fixtures describe approved current acquired ownership. They do not
authorize acquisition, retraining, or an individual learned Move's execution.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]
from builder import build_trainer
from engine import Rules, Engine, Combatant
from state_codec import dump_engine, load_engine
import class_move_grants as MOVES
import items
import state_fields as FIELDS
import state_grants as GRANTS
import static_feature_state_grants as STATIC

SOURCES = {
    "FAN-140": ("feat/스톰-위자드", [1074, 1088],
                [["차지빔", "스파크"], ["충전", "괴전파"], ["번개", "전기자석파"]]),
    "FAN-158": ("feat/휘몰아치는-바람", [1231, 1244],
                [["제비반환", "에어커터"], ["바람일으키기", "안개제거"], ["폭풍", "따라하기"]]),
    "FAN-216": ("feat/해류의-부름", [1701, 1713],
                [["아쿠아제트", "아쿠아링"], ["물의파동", "거품광선"], ["파도타기", "비바라기"]]),
}


# Historical source obligations, not a ceiling on later valid policy additions.
RETAINED_STATIC_SOURCE_BINDINGS = {'C2CSV/input/db/class-data.csv:R30:blessing': ('C2CSV/input/db/class-data.csv:R30:blessing',
                                                'gift/마이너-기프트-로얄-하트',
                                                'input/db/class-data.csv',
                                                '052deccefd5581813a9d53c0001f3dafa9c6f517342970ae1d96baf5e905a3ad',
                                                30,
                                                (12, 13, 14, 15, 16),
                                                ()),
 'C2CSV/input/db/class-data.csv:R44:blessing': ('C2CSV/input/db/class-data.csv:R44:blessing',
                                                'gift/메이저-기프트-순수-호흡',
                                                'input/db/class-data.csv',
                                                'f6da5ce21ca841acc274972f19b5691c7b74f3d224a854f82b638c267b2b5765',
                                                44,
                                                (12, 13, 14, 15, 16),
                                                ()),
 'C2CSV/input/db/class-data.csv:R97:blessing': ('C2CSV/input/db/class-data.csv:R97:blessing',
                                                'gift/마이너-기프트-드림-마스터리',
                                                'input/db/class-data.csv',
                                                '3c269a01072e43d61f0f2611ddfb290339ba9a9dd099d7ec5a321dd1c89c02f9',
                                                97,
                                                (12, 13, 14, 15, 16),
                                                ()),
 'C2CSV/input/db/feats.csv:R404:main': ('C2CSV/input/db/feats.csv:R404:main',
                                        'class/무술가',
                                        'input/db/feats.csv',
                                        '7ffde01f75690a46df1178a316deb272b6c562559c60ac2c4d35744ba1e2c47d',
                                        404,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R413:main': ('C2CSV/input/db/feats.csv:R413:main',
                                        'feat/달맞이산-블루스',
                                        'input/db/feats.csv',
                                        'fa5d5ca138846e775fc555742516bc7081fab3da31024d81054063c44353f83b',
                                        413,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R414:main': ('C2CSV/input/db/feats.csv:R414:main',
                                        'feat/불협화음',
                                        'input/db/feats.csv',
                                        'a50a96fa25167c5cb662df0709d56ff77fc3168514927787599ec71357680ff8',
                                        414,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R415:main': ('C2CSV/input/db/feats.csv:R415:main',
                                        'feat/소음-신고',
                                        'input/db/feats.csv',
                                        '527983cc0f784ad21eb612db21458fac7d7e16c94a67b8503391be0924d644f6',
                                        415,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R421:main': ('C2CSV/input/db/feats.csv:R421:main',
                                        'feat/엇갈린-메시지',
                                        'input/db/feats.csv',
                                        '9c352c71f487f92582b401e3e81ad74fc67167605b635503379600b3d9bf53dd',
                                        421,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R428:main': ('C2CSV/input/db/feats.csv:R428:main',
                                        'feat/불시의-공격',
                                        'input/db/feats.csv',
                                        'c6c245ce2403fccb306ac8ff2d7afb14f52a5671b1a3d9234397535d355ac456',
                                        428,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R430:main': ('C2CSV/input/db/feats.csv:R430:main',
                                        'feat/거리의-싸움꾼',
                                        'input/db/feats.csv',
                                        '62aa11b1865325ba3e2c134a032946e6b01970d405e109b59f1e3905632c2c2f',
                                        430,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R442:main': ('C2CSV/input/db/feats.csv:R442:main',
                                        'feat/악감정',
                                        'input/db/feats.csv',
                                        '57f1ac1e61c73e6a490a5eaf182447f85a483148864eb5839819b2cfe74bdfb2',
                                        442,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R444:main': ('C2CSV/input/db/feats.csv:R444:main',
                                        'feat/잔혹한-응시',
                                        'input/db/feats.csv',
                                        '9b9f528155259c8a681c64c77faaa9e3e3f31b7bc80961b4b3125e9bf2952250',
                                        444,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R445:main': ('C2CSV/input/db/feats.csv:R445:main',
                                        'feat/굳건함',
                                        'input/db/feats.csv',
                                        '914e68c974a59dce0a411baf32e71852e99816f1fe7c697cba46520e8aa8da29',
                                        445,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R450:main': ('C2CSV/input/db/feats.csv:R450:main',
                                        'feat/위에서-내려온-죽음',
                                        'input/db/feats.csv',
                                        '69481e93025a0cc22eb7338ab456e4ed1335ab3563f7c21014af47f98b3de797',
                                        450,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R489:main': ('C2CSV/input/db/feats.csv:R489:main',
                                        'feat/신성-방패',
                                        'input/db/feats.csv',
                                        '2e559cc268bb6790bb1f038ee8df9289cbf3a3c944a64f038050bb3ecaa41ca8',
                                        489,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R490:main': ('C2CSV/input/db/feats.csv:R490:main',
                                        'feat/신비의-방어',
                                        'input/db/feats.csv',
                                        '1cd496a4be1ed232ef8fa0bf0107369171ece8aa05d5c5fbf7d7d251be8ff060',
                                        490,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R497:main': ('C2CSV/input/db/feats.csv:R497:main',
                                        'feat/pk-오메가',
                                        'input/db/feats.csv',
                                        '7492ca803557171d8b50e5c95454638e34fc8c9b5636cafbe4bcbf80bcfd0611',
                                        497,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R503:main': ('C2CSV/input/db/feats.csv:R503:main',
                                        'feat/연마된-정신',
                                        'input/db/feats.csv',
                                        '59fc48d0eb910075f747548ac08059d1e507b1102ae20d1abc4758a2b02fa2f1',
                                        503,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R507:main': ('C2CSV/input/db/feats.csv:R507:main',
                                        'feat/정신공격',
                                        'input/db/feats.csv',
                                        '695b1d6128ca6b1558114be36bac21a552665e10bc8a0a2ccbb6a4e8ebf5c7fb',
                                        507,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R510:main': ('C2CSV/input/db/feats.csv:R510:main',
                                        'feat/공간-왜곡',
                                        'input/db/feats.csv',
                                        '63c2bc124e2d4c0d11a5a6261e82c1b0db12bc705aa5806e53430eea91bd5360',
                                        510,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R511:main': ('C2CSV/input/db/feats.csv:R511:main',
                                        'feat/지면-뒤틀기',
                                        'input/db/feats.csv',
                                        'ad5438c6ce4f38f24cb25c5cdac57b6c326661b2872a34240342286179fccf99',
                                        511,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R512:main': ('C2CSV/input/db/feats.csv:R512:main',
                                        'feat/이상한-힘',
                                        'input/db/feats.csv',
                                        '08640dbf4cd9d11a76b85d48fe2b6ec7602e89965511439020dab97e7c8ad193',
                                        512,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R513:main': ('C2CSV/input/db/feats.csv:R513:main',
                                        'feat/파캐스트',
                                        'input/db/feats.csv',
                                        'bb600dc18ebf3eb0157043953c5e4dd83d3727b9b5a7fdadce3b5e04bdf90ad4',
                                        513,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R570:main': ('C2CSV/input/db/feats.csv:R570:main',
                                        'feat/철벽',
                                        'input/db/feats.csv',
                                        '43a18c42eab80e1b91724f08f8e270920f7746583f93dfe7768350227f281f4b',
                                        570,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R587:main': ('C2CSV/input/db/feats.csv:R587:main',
                                        None,
                                        'input/db/feats.csv',
                                        'acc21c286d5906a6e6dc4fe3046207b860c0579e8d0c06b95b5bb46c5c3b602f',
                                        587,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R597:main': ('C2CSV/input/db/feats.csv:R597:main',
                                        'feat/선명한-그림자',
                                        'input/db/feats.csv',
                                        'c86a10b5f5c12824a34900be6ec23af4faa74cf33f79174418308b2cdd41b9ce',
                                        597,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R598:main': ('C2CSV/input/db/feats.csv:R598:main',
                                        'feat/심연의-심장',
                                        'input/db/feats.csv',
                                        '9136a59df18302241dfe7234bcbf87be008395e50b682584a7c509ee5bef503e',
                                        598,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R617:main': ('C2CSV/input/db/feats.csv:R617:main',
                                        'feat/정열적인-하모니',
                                        'input/db/feats.csv',
                                        'e7b7b153bba5d200304f240e8b1f2b523b9252646d858a127307e2b15541183b',
                                        617,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R618:main': ('C2CSV/input/db/feats.csv:R618:main',
                                        'feat/럭키-클로버-그랜드-피날레',
                                        'input/db/feats.csv',
                                        'dbc9f8997222fec1e921aaf6cdb21dad31feadaca1445fed5990990a3010f21c',
                                        618,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R623:main': ('C2CSV/input/db/feats.csv:R623:main',
                                        'feat/불의-영혼',
                                        'input/db/feats.csv',
                                        'a57383ef4aa51e59202e31e6a5e8d244d95ffcd352cfe75968125c171913872d',
                                        623,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R643:main': ('C2CSV/input/db/feats.csv:R643:main',
                                        None,
                                        'input/db/feats.csv',
                                        'bcd3f353c955fea3a9062a5401409f2ff89540aedd99a1d0c31f988a7c2f67ca',
                                        643,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R644:main': ('C2CSV/input/db/feats.csv:R644:main',
                                        'feat/녹빛-도로',
                                        'input/db/feats.csv',
                                        '5534167cb1b4dab995811551ee12ad9ec42a857acf8756857f9e42e483873ab2',
                                        644,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R651:main': ('C2CSV/input/db/feats.csv:R651:main',
                                        'feat/대지-결합',
                                        'input/db/feats.csv',
                                        '7d270ef4f1ec06fd037dc146ca88c8564d7b456d7fc7be080978372e057a891f',
                                        651,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R658:main': ('C2CSV/input/db/feats.csv:R658:main',
                                        'feat/추위따위-아무것도-아니었으니',
                                        'input/db/feats.csv',
                                        'fabf303518bd31dea32850bb4f3c5b3d3b417feb82dbb0a3cfd91a1b29906b26',
                                        658,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R675:main': ('C2CSV/input/db/feats.csv:R675:main',
                                        'feat/불쾌함의-부름',
                                        'input/db/feats.csv',
                                        '871ea014dd831595801c6de78c7214dff5f384323dc63e9fc4b28d3be33dfafb',
                                        675,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'C2CSV/input/db/feats.csv:R676:main': ('C2CSV/input/db/feats.csv:R676:main',
                                        'feat/불쾌함-촉발',
                                        'input/db/feats.csv',
                                        'f4a64ef94655672df6921c4081d0c5385fcd959b0208450e5cd61d47fb37ef6a',
                                        676,
                                        (1, 2, 3, 4, 5),
                                        ()),
 'FAN-140': ('FAN-140',
             'feat/스톰-위자드',
             'input/supp-fantasy.md',
             'aa586fcb10a9f36accfc8ae8a71df0f14c37c752ac2abccea1f386594a05ec2c',
             None,
             (),
             (1074, 1088)),
 'FAN-158': ('FAN-158',
             'feat/휘몰아치는-바람',
             'input/supp-fantasy.md',
             '046de8abd22a57504a8275dcff1bd479f4004cd61ddbd15e463d368e7d9a131e',
             None,
             (),
             (1231, 1244)),
 'FAN-216': ('FAN-216',
             'feat/해류의-부름',
             'input/supp-fantasy.md',
             '1959d0025045d61b3287aa269b54c2b45ccdf180056ac44fe8d5dff4fcd1c408',
             None,
             (),
             (1701, 1713)),
 'input/ch04-trainer-classes.md:2247-2253': ('input/ch04-trainer-classes.md:2247-2253',
                                             'feat/육상-기술',
                                             'input/ch04-trainer-classes.md',
                                             '86547ba1f7cba96e88882d87161f1ea0a93b5ab94b1baad01a4c718e944c30aa',
                                             None,
                                             (),
                                             (2247, 2253)),
 'input/ch04-trainer-classes.md:2294-2299': ('input/ch04-trainer-classes.md:2294-2299',
                                             'feat/댄스-연습',
                                             'input/ch04-trainer-classes.md',
                                             'f49a11b0024f5c08bda584a34c6fc11e8d71f781251012b50802c881ba1cea74',
                                             None,
                                             (),
                                             (2294, 2299)),
 'input/ch04-trainer-classes.md:2340-2345': ('input/ch04-trainer-classes.md:2340-2345',
                                             'feat/집단-전술',
                                             'input/ch04-trainer-classes.md',
                                             '48a00ea2597066805ce9a5378a8a410aceaa749997af72989c581470d0e494be',
                                             None,
                                             (),
                                             (2340, 2345)),
 'input/ch04-trainer-classes.md:3136-3138': ('input/ch04-trainer-classes.md:3136-3138',
                                             'class/염동력자',
                                             'input/ch04-trainer-classes.md',
                                             '52e660820ba5588e8288a3461ef416da8afb7be15a720d837af22363dcde08b3',
                                             None,
                                             (),
                                             (3136, 3138))}

class FantasyRankedStatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")
        cls.tables = MOVES._ranked_tables(cls.rules)

    def fixture(self, cid, rank=1):
        uid, _, pairs = SOURCES[cid]
        parent = self.tables[uid]["parent"]
        spec = build_trainer(self.rules, "fantasy-rank-stat", 30,
                             dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
                             moves=[], abilities=[])
        spec.update(classes=[], edges=[], feats=[parent, uid],
                    feat_ranks={uid: rank},
                    skills={"곡예": 6, "집중": 6, "통찰": 6, "육상": 6},
                    feature_choices={uid: deepcopy(pairs[:rank])})
        actor = Combatant(self.rules, spec)
        engine = Engine(self.rules, seed=1225)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor

    @staticmethod
    def source(actor, cid):
        return "feature:" + actor.entity_id + ":" + SOURCES[cid][0]

    @staticmethod
    def rank(actor, cid, rank):
        uid, _, pairs = SOURCES[cid]
        actor.spec["feat_ranks"][uid] = rank
        actor.spec["feature_choices"][uid] = deepcopy(pairs[:rank])

    @staticmethod
    def state(engine, actor):
        return deepcopy((actor.spec, actor.stats, actor.moves, actor.abilities,
                         actor.hp, actor.move_uses, engine.rng.getstate(), engine.log_lines))

    def assert_projection(self, actor, cid, rank, *, baseline=10, independent=0):
        uid, _, pairs = SOURCES[cid]
        self.assertEqual(actor.spec["stats"]["spe"], baseline)
        self.assertEqual(actor.stats["spe"], baseline + rank + independent)
        source = self.source(actor, cid)
        row = actor.spec[GRANTS.KEY]["sources"][source]
        self.assertEqual((row["owner_id"], row["rule_id"], row["lifetime"], row["clause_id"]),
                         (actor.entity_id, uid, "while_owned", cid))
        expected = [[actor.r.move_id(name) for name in pair] for pair in pairs[:rank]]
        self.assertEqual(row["class_move_selection"], expected)
        self.assertCountEqual(row["grants"]["moves"], sum(expected, []))
        self.assertTrue(set(sum(expected, [])).issubset(actor.moves))
        self.assertEqual(actor.spec[GRANTS.KEY]["stat_sources"]["spe"]["sources"][source],
                         {"feature_count": {"delta": rank, "minimum": None}})
        self.assertTrue(STATIC.validate(actor))

    def test_exact_three_source_rows_reuse_printed_speed_rank_and_existing_move_contract(self):
        policy = STATIC._policy(self.rules)
        self.assertTrue(set(RETAINED_STATIC_SOURCE_BINDINGS) <= set(policy["rules"]))
        self.assertEqual({cid: (policy["rules"][cid]["id"],
                               policy["rules"][cid].get("owner_id"),
                               policy["rules"][cid]["source_file"],
                               policy["rules"][cid].get("cell_sha256", policy["rules"][cid].get("excerpt_sha256")),
                               policy["rules"][cid].get("csv_record"),
                               tuple(policy["rules"][cid].get("columns", ())),
                               tuple(policy["rules"][cid].get("lines", ())))
                          for cid in RETAINED_STATIC_SOURCE_BINDINGS}, RETAINED_STATIC_SOURCE_BINDINGS)
        source = ROOT / "input/supp-fantasy.md"
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         "a51f5d6592bc1ff12b380f47398db93426b53c58c210810f5041b29eb64b2266")
        lines = source.read_text(encoding="utf-8").splitlines()
        for cid, (uid, bounds, _) in SOURCES.items():
            with self.subTest(source=cid):
                row = policy["rules"][cid]
                self.assertEqual((row["id"], row["owner_id"], row["mode"], row["stat"], row["tag"]),
                                 (cid, uid, "ranked_stat", "spe", "+스피드"))
                text = "\n".join(lines[bounds[0]-1:bounds[1]])
                self.assertEqual((row["lines"], row["excerpt"]), (bounds, text))
                self.assertEqual(row["excerpt_sha256"], hashlib.sha256(text.encode()).hexdigest())
                self.assertEqual(row["excerpt_sha256"], self.tables[uid]["excerpt_sha256"])
        self.assertEqual(self.tables[SOURCES["FAN-140"][0]]["minimum_skill_rank"], [0, 5, 6])
        self.assertEqual(self.tables[SOURCES["FAN-158"][0]]["skills"], ["곡예", "통찰"])
        self.assertEqual(self.tables[SOURCES["FAN-216"][0]]["minimum_skill_rank"], [0, 4, 5])
        self.assertNotIn("항상", policy["rules"]["FAN-216"]["excerpt"])

    def test_all_sources_rank_one_two_three_and_repeated_registration_share_move_stat_source(self):
        for cid, (uid, _, _) in SOURCES.items():
            with self.subTest(source=cid):
                engine, actor = self.fixture(cid)
                other_stats = {k: v for k, v in actor.stats.items() if k != "spe"}
                for rank in (1, 2, 3):
                    self.rank(actor, cid, rank)
                    # Exercise the printed alternate skill at its exact threshold.
                    table = self.tables[uid]
                    actor.spec["skills"] = {table["skills"][-1]: max(1, table["minimum_skill_rank"][rank-1])}
                    items.register_feats(engine, actor)
                    self.assert_projection(actor, cid, rank)
                    self.assertEqual({k: v for k, v in actor.stats.items() if k != "spe"}, other_stats)
                    # Existing unimplemented parent Effects may repeat an
                    # informational log; idempotence concerns gameplay state.
                    before = self.state(engine, actor)[:-1]
                    items.register_feats(engine, actor)
                    self.assertEqual(self.state(engine, actor)[:-1], before)

    def test_rank_reduction_and_removal_preserve_base_growth_independent_speed_and_move(self):
        for cid, (uid, _, pairs) in SOURCES.items():
            with self.subTest(source=cid):
                engine, actor = self.fixture(cid, 3)
                baseline_move = self.rules.move_id(pairs[0][0])
                GRANTS.set_baseline(actor, "moves", [baseline_move])
                separate = "gm/independent-speed"
                GRANTS._source(actor, separate, "gm", owner_id=actor.entity_id,
                               lifetime="permanent", rule_id="gm/observed-stat", tutor_points=0)
                GRANTS.stat(actor, "spe", 2, separate)
                proposed = dict(actor.spec["stats"], spe=12)
                FIELDS.base_patch(actor, {"stats": proposed}, source="gm/state",
                                  reason="approved baseline growth")
                for rank in (3, 2, 1):
                    self.rank(actor, cid, rank)
                    items.register_feats(engine, actor)
                    self.assert_projection(actor, cid, rank, baseline=12, independent=2)
                actor.spec["feats"].remove(uid)
                actor.spec["feat_ranks"].pop(uid)
                actor.spec["feature_choices"].pop(uid)
                items.register_feats(engine, actor)
                self.assertEqual(actor.stats["spe"], 14)
                self.assertNotIn(self.source(actor, cid), actor.spec[GRANTS.KEY]["sources"])
                self.assertEqual(actor.moves, [baseline_move])
                GRANTS.revoke(actor, separate, engine=engine)
                self.assertEqual(actor.stats["spe"], 12)
                self.assertTrue(engine.validate_state()["valid"])

    def test_all_sources_gm_and_fresh_rules_restore_exact_speed_and_move_receipts(self):
        for cid in SOURCES:
            with self.subTest(source=cid):
                engine, actor = self.fixture(cid, 3)
                items.register_feats(engine, actor)
                expected = deepcopy((actor.stats, actor.spec[GRANTS.KEY], actor.moves))
                engine.gm.snapshot("fantasy-ranked-speed")
                self.rank(actor, cid, 1)
                items.register_feats(engine, actor)
                self.assert_projection(actor, cid, 1)
                engine.gm.restore("fantasy-ranked-speed", reason="restore approved ranked state")
                self.assertEqual((actor.stats, actor.spec[GRANTS.KEY], actor.moves), expected)
                payload = json.loads(json.dumps(dump_engine(engine), ensure_ascii=False))
                restored = load_engine(Rules(str(ROOT), ruleset="all"), payload)
                copy = restored.everyone[0]
                self.assertEqual((copy.stats, copy.spec[GRANTS.KEY], copy.moves), expected)
                self.assert_projection(copy, cid, 3)
                before = self.state(restored, copy)[:-1]
                items.register_feats(restored, copy)
                self.assertEqual(self.state(restored, copy)[:-1], before)
                self.assertTrue(restored.validate_state()["valid"])

    def test_actual_native_initiative_reads_each_sources_reconciled_speed(self):
        for cid in SOURCES:
            with self.subTest(source=cid):
                engine, actor = self.fixture(cid)
                self.assertEqual(engine.initiative_value(actor).value, 10)
                for rank in (1, 3, 2):
                    self.rank(actor, cid, rank)
                    items.register_feats(engine, actor)
                    self.assertEqual(actor.staged("spe"), 10 + rank)
                    result = engine.initiative_value(actor)
                    self.assertEqual(result.value, 10 + rank)
                    self.assertEqual(result.unresolved, ())
                    self.assertEqual(result.derivation["speed_actor_id"], actor.entity_id)

    def test_rank_skill_parent_and_move_failure_leave_speed_receipts_and_rng_unchanged(self):
        for cid, (uid, _, pairs) in SOURCES.items():
            for defect in ("skill", "parent", "rank", "move"):
                with self.subTest(source=cid, defect=defect):
                    engine, actor = self.fixture(cid)
                    items.register_feats(engine, actor)
                    self.rank(actor, cid, 2)
                    table = self.tables[uid]
                    if defect == "skill":
                        actor.spec["skills"] = {key: table["minimum_skill_rank"][1]-1 for key in table["skills"]}
                    elif defect == "parent":
                        actor.spec["feats"].remove(table["parent"])
                    elif defect == "rank":
                        actor.spec["feat_ranks"][uid] = 4
                    else:
                        actor.spec["feature_choices"][uid][1] = [pairs[0][0], "맹독"]
                    before = self.state(engine, actor)
                    with self.assertRaises(ValueError):
                        items.register_feats(engine, actor)
                    self.assertEqual(self.state(engine, actor), before)
        # Insight is printed; Intuition never substitutes for it.
        engine, actor = self.fixture("FAN-158", 2)
        actor.spec["skills"] = {"직감": 6}
        before = self.state(engine, actor)
        with self.assertRaises(ValueError):
            items.register_feats(engine, actor)
        self.assertEqual(self.state(engine, actor), before)


if __name__ == "__main__":
    unittest.main()
