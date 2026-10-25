"""Native Fantasy class owners reuse the existing CSV branch projection."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from builder import build_trainer
from engine import Combatant, Engine, Rules
import ability_transitions as ABILITIES
import acquired_feature_projections as PROJECTIONS
import items
import state_codec as CODEC
import state_grants as GRANTS
import static_feature_state_grants as STATIC

CASES = {
    "FAN-117": ("C2CSV/input/db/feats.csv:R587:main",
                "supp-fantasy/벌레-원소술사-무리군주", "feat/거미줄-쏘는-법"),
    "FAN-166": ("C2CSV/input/db/feats.csv:R643:main",
                "supp-fantasy/풀-원소술사-드루이드", "feat/자연의-포용"),
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
 'input/ch04-trainer-classes.md:3136-3138': ('input/ch04-trainer-classes.md:3136-3138',
                                             'class/염동력자',
                                             'input/ch04-trainer-classes.md',
                                             '52e660820ba5588e8288a3461ef416da8afb7be15a720d837af22363dcde08b3',
                                             None,
                                             (),
                                             (3136, 3138))}

class FantasyClassBranchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="all")

    def fixture(self, clause, branch):
        cid, owner, _ = CASES[clause]
        spec = build_trainer(
            self.rules, "branch-owner", 30,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            moves=[], abilities=[], extra={
                "classes": [], "edges": [], "feats": [owner],
                "static_feature_choices": {owner: branch}, "feature_choices": {},
            },
        )
        actor = Combatant(self.rules, spec)
        engine = Engine(self.rules, seed=1192)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor, STATIC.rules(self.rules)[cid]

    def test_five_branches_use_native_registration_and_ranked_class_stat_counts(self):
        branches = 0
        for clause, (cid, owner, child) in CASES.items():
            for branch, result in STATIC.rules(self.rules)[cid]["branches"].items():
                with self.subTest(clause=clause, branch=branch):
                    engine, actor, _ = self.fixture(clause, branch)
                    self.assertEqual(STATIC.identity(self.rules, owner), cid)
                    self.assertEqual(items.register_feats(engine, actor), 1)
                    self.assertEqual(STATIC.class_branch(actor, owner), branch)
                    self.assertEqual(actor.stats[result["stat"]], 11)
                    self.assertEqual(ABILITIES.known(actor), [result["abilities"][0]["id"]])
                    self.assertEqual(items.register_feats(engine, actor), 0)
                    actor.spec["feats"].append(child)
                    rank = 3 if clause == "FAN-166" else 1
                    actor.spec["feat_ranks"] = {child: rank}
                    STATIC.register_all(engine, actor)
                    self.assertEqual(actor.stats[result["stat"]], 11 + rank)
                    actor.spec["feat_ranks"][child] = 1
                    STATIC.register_all(engine, actor)
                    self.assertEqual(actor.stats[result["stat"]], 12)
                    actor.spec["feats"].remove(child)
                    STATIC.register_all(engine, actor)
                    self.assertEqual(actor.stats[result["stat"]], 11)
                    STATIC.validate(actor)
                    actor.spec["feats"].remove(owner)
                    STATIC.register_all(engine, actor)
                    self.assertEqual(actor.stats[result["stat"]], 10)
                    self.assertEqual(ABILITIES.known(actor), [])
                    self.assertIsNone(STATIC.class_branch(actor, owner))
                    branches += 1
        self.assertEqual(branches, 5)

    def test_gm_and_json_restore_preserve_branch_and_independent_ability_baseline(self):
        for clause, branch in (("FAN-117", "거미의 포용"), ("FAN-166", "꽃의 맹약")):
            with self.subTest(clause=clause):
                cid, owner, _ = CASES[clause]
                result = STATIC.rules(self.rules)[cid]["branches"][branch]
                engine, actor, _ = self.fixture(clause, branch)
                GRANTS.set_baseline(actor, "abilities", [result["abilities"][0]["title"]])
                items.register_feats(engine, actor)
                engine.gm.snapshot("class-branch")
                actor.hp -= 1
                engine.gm.restore("class-branch", reason="restore class branch")
                restored = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(engine))))
                copy = restored.everyone[0]
                self.assertEqual(STATIC.class_branch(copy, owner), branch)
                self.assertEqual(copy.stats[result["stat"]], 11)
                copy.spec["feats"].remove(owner)
                items.register_feats(restored, copy)
                self.assertEqual(copy.stats[result["stat"]], 10)
                self.assertEqual(ABILITIES.known(copy), [result["abilities"][0]["id"]])

    def test_owned_parent_drives_broodlord_without_a_second_choice(self):
        for branch in ("거미의 포용", "군주의 포용"):
            with self.subTest(branch=branch):
                engine, actor, _ = self.fixture("FAN-117", branch)
                actor.spec["feats"].append("feat/무리어미")
                expected = PROJECTIONS.plan(engine, actor, "feat/무리어미")
                items.register_feats(engine, actor)
                self.assertEqual(expected["selection"], [branch])
                self.assertTrue(set(expected["ability_ids"]).issubset(ABILITIES.known(actor)))
                stat = "atk" if branch == "거미의 포용" else "spa"
                self.assertEqual(actor.stats[stat], 12)

    def test_conflicting_descendant_or_replacement_choice_cannot_mutate_state(self):
        engine, actor, _ = self.fixture("FAN-117", "거미의 포용")
        items.register_feats(engine, actor)
        actor.spec["feats"].append("feat/무리어미")
        actor.spec["feature_choices"] = {CASES["FAN-117"][1]: "군주의 포용"}
        before = deepcopy((actor.spec, actor.stats, actor.abilities, engine.rng.getstate()))
        with self.assertRaisesRegex(ValueError, "disagrees"):
            PROJECTIONS.register_all(engine, actor)
        self.assertEqual((actor.spec, actor.stats, actor.abilities, engine.rng.getstate()), before)
        actor.spec["feature_choices"] = {}
        actor.spec["feats"].remove("feat/무리어미")
        actor.spec["static_feature_choices"][CASES["FAN-117"][1]] = "군주의 포용"
        before = deepcopy((actor.spec, actor.stats, actor.abilities))
        with self.assertRaises(ValueError):
            STATIC.register_all(engine, actor)
        self.assertEqual((actor.spec, actor.stats, actor.abilities), before)
        with self.assertRaisesRegex(ValueError, "silently replaced"):
            STATIC.class_branch(actor, CASES["FAN-117"][1])

    def test_missing_invalid_and_duplicate_owner_choices_fail_before_registration(self):
        for clause in CASES:
            cid, owner, _ = CASES[clause]
            branch = next(iter(STATIC.rules(self.rules)[cid]["branches"]))
            for error in ("missing", "invalid", "duplicate"):
                with self.subTest(clause=clause, error=error):
                    engine, actor, _ = self.fixture(clause, branch)
                    if error == "missing":
                        actor.spec["static_feature_choices"] = {}
                    elif error == "invalid":
                        actor.spec["static_feature_choices"][owner] = "unprinted branch"
                    else:
                        actor.spec["feats"].append(cid)
                    before = deepcopy((actor.spec, actor.stats, actor.abilities))
                    with self.assertRaises(ValueError):
                        items.register_feats(engine, actor)
                    self.assertEqual((actor.spec, actor.stats, actor.abilities), before)

    def test_two_source_bindings_are_hash_pinned_inside_the_existing_37_contracts(self):
        policy = json.loads((Path(self.rules.root) / STATIC.POLICY_PATH).read_text(encoding="utf-8"))
        self.assertTrue(set(RETAINED_STATIC_SOURCE_BINDINGS) <= set(policy["rules"]))
        self.assertEqual({cid: (policy["rules"][cid]["id"],
                               policy["rules"][cid].get("owner_id"),
                               policy["rules"][cid]["source_file"],
                               policy["rules"][cid].get("cell_sha256", policy["rules"][cid].get("excerpt_sha256")),
                               policy["rules"][cid].get("csv_record"),
                               tuple(policy["rules"][cid].get("columns", ())),
                               tuple(policy["rules"][cid].get("lines", ())))
                          for cid in RETAINED_STATIC_SOURCE_BINDINGS}, RETAINED_STATIC_SOURCE_BINDINGS)
        self.assertEqual(STATIC.rules(self.rules), policy["rules"])
        for clause, (cid, owner, _) in CASES.items():
            self.assertEqual(policy["rules"][cid]["equivalent_sources"][clause]["owner_id"], owner)
        policy["rules"][CASES["FAN-117"][0]]["equivalent_sources"]["FAN-117"]["excerpt_sha256"] = "0" * 64
        with TemporaryDirectory() as temp:
            path = Path(temp) / "policy.json"
            path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
            rules = Rules(str(ROOT), ruleset="all")
            with patch.object(STATIC, "_path", return_value=path):
                with self.assertRaisesRegex(ValueError, "equivalent Static Feature source changed"):
                    STATIC.rules(rules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
