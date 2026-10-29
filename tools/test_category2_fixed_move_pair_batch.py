"""Twenty-four pure fixed move-pair feature receipts use one owned projection."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from builder import build_trainer
from engine import Combatant, Engine, Rules
import class_move_grants as CLASS_MOVES
import encounter
import items
import state_codec as CODEC
import state_grants as GRANTS


CASES = {
    "feat/달맞이산-블루스": ("C2CSV/input/db/feats.csv:R413:main", ("노래하기", "초음파")),
    "feat/불협화음": ("C2CSV/input/db/feats.csv:R414:main", ("싫은소리", "금속음")),
    "feat/소음-신고": ("C2CSV/input/db/feats.csv:R415:main", ("소란피기", "하이퍼보이스")),
    "feat/엇갈린-메시지": ("C2CSV/input/db/feats.csv:R421:main", ("악마의키스", "트집")),
    "feat/불시의-공격": ("C2CSV/input/db/feats.csv:R428:main", ("따라가때리기", "기습")),
    "feat/거리의-싸움꾼": ("C2CSV/input/db/feats.csv:R430:main", ("승부굳히기", "보복")),
    "feat/악감정": ("C2CSV/input/db/feats.csv:R442:main", ("검은눈빛", "야금야금")),
    "feat/잔혹한-응시": ("C2CSV/input/db/feats.csv:R444:main", ("뱀눈초리", "박치기")),
    "feat/굳건함": ("C2CSV/input/db/feats.csv:R445:main", ("버티기", "게으름피우기")),
    "feat/위에서-내려온-죽음": ("C2CSV/input/db/feats.csv:R450:main", ("애크러뱃", "뛰어오르기")),
    "feat/신성-방패": ("C2CSV/input/db/feats.csv:R489:main", ("리플렉터", "주술")),
    "feat/신비의-방어": ("C2CSV/input/db/feats.csv:R490:main", ("빛의장막", "신비의부적")),
    "feat/pk-오메가": ("C2CSV/input/db/feats.csv:R497:main", ("텔레키네시스", "사이코키네시스")),
    "feat/연마된-정신": ("C2CSV/input/db/feats.csv:R503:main", ("마음의눈", "명상")),
    "feat/공간-왜곡": ("C2CSV/input/db/feats.csv:R510:main", ("순간이동", "사이드체인지")),
    "feat/지면-뒤틀기": ("C2CSV/input/db/feats.csv:R511:main", ("중력", "트릭")),
    "feat/이상한-힘": ("C2CSV/input/db/feats.csv:R512:main", ("회복봉인", "매직코트")),
    "feat/철벽": ("C2CSV/input/db/feats.csv:R570:main", ("철벽", "방어")),
    "feat/선명한-그림자": ("C2CSV/input/db/feats.csv:R597:main", ("악의파동", "깜짝베기")),
    "feat/심연의-심장": ("C2CSV/input/db/feats.csv:R598:main", ("나이트버스트", "혼내기")),
    "feat/정열적인-하모니": ("C2CSV/input/db/feats.csv:R617:main", ("매지컬샤인", "드레인키스")),
    "feat/럭키-클로버-그랜드-피날레": ("C2CSV/input/db/feats.csv:R618:main", ("문포스", "아로마미스트")),
    "feat/불쾌함의-부름": ("C2CSV/input/db/feats.csv:R675:main", ("녹기", "오물폭탄")),
    "feat/불쾌함-촉발": ("C2CSV/input/db/feats.csv:R676:main", ("오물웨이브", "맹독")),
}


class FixedMovePairBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset="fantasy")

    def fixture(self):
        engine = Engine(self.rules, seed=2413)
        spec = build_trainer(
            self.rules,
            "fixed-pair-owner",
            30,
            dict.fromkeys(("hp", "atk", "def", "spa", "spd", "spe"), 10),
            moves=[],
        )
        spec.update(classes=[], feats=list(CASES), edges=[], feature_choices={})
        actor = Combatant(self.rules, spec)
        engine.everyone = engine.gm.everyone = [actor]
        return engine, actor

    @staticmethod
    def source(actor, uid):
        return "feature:" + actor.entity_id + ":" + uid

    def all_move_ids(self):
        return {
            self.rules.move_id(name)
            for _, pair in CASES.values()
            for name in pair
        }

    def test_all_24_declarations_match_selected_source_and_executable_moves(self):
        expected = {uid: pair for uid, (_, pair) in CASES.items()}
        self.assertEqual(CLASS_MOVES.FIXED_CSV_PAIRS, expected)
        for uid, (clause_id, pair) in CASES.items():
            with self.subTest(clause=clause_id):
                self.assertEqual(self.rules._selected_rule(uid), uid)
                effects, _ = self.rules.feat_effects(uid)
                grants = [effect for effect in effects if effect.get("type") == "grant_move"]
                self.assertEqual(len(grants), 1)
                self.assertEqual(
                    [self.rules.move_id(value) for value in grants[0]["moves"]],
                    [self.rules.move_id(value) for value in pair],
                )
                for name in pair:
                    move_id = self.rules.move_id(name)
                    self.assertEqual(self.rules._selected_rule(move_id), move_id)
                    self.assertIn(move_id, self.rules.moves)

    def test_one_registration_projects_all_pairs_to_native_move_consumer(self):
        engine, actor = self.fixture()
        items.register_feats(engine, actor)
        stable = deepcopy((actor.spec, actor.moves))
        items.register_feats(engine, actor)
        self.assertEqual((actor.spec, actor.moves), stable)
        wanted = self.all_move_ids()
        self.assertTrue(wanted.issubset(set(actor.moves)))
        self.assertTrue(wanted.issubset(set(encounter.usable_moves(engine, actor))))
        sources = actor.spec[GRANTS.KEY]["sources"]
        for uid, (_, pair) in CASES.items():
            row = sources[self.source(actor, uid)]
            self.assertEqual(
                (row["kind"], row["owner_id"], row["lifetime"], row["rule_id"], row["tutor_points"]),
                ("feature", actor.entity_id, "while_owned", uid, 0),
            )
            self.assertCountEqual(row["grants"]["moves"], [self.rules.move_id(value) for value in pair])
            self.assertEqual(row["class_move_selection"], [[self.rules.move_id(value) for value in pair]])

    def test_owner_loss_withdraws_only_lost_sources_and_preserves_baseline(self):
        engine, actor = self.fixture()
        baseline_name = CASES["feat/달맞이산-블루스"][1][0]
        baseline_id = self.rules.move_id(baseline_name)
        GRANTS.set_baseline(actor, "moves", [baseline_id])
        items.register_feats(engine, actor)
        lost = list(CASES)[::2]
        kept = set(CASES) - set(lost)
        actor.spec["feats"] = list(kept)
        items.register_feats(engine, actor)
        sources = actor.spec[GRANTS.KEY]["sources"]
        for uid in lost:
            self.assertNotIn(self.source(actor, uid), sources)
        for uid in kept:
            self.assertIn(self.source(actor, uid), sources)
        self.assertIn(baseline_id, actor.moves)
        for uid in lost:
            for name in CASES[uid][1]:
                move_id = self.rules.move_id(name)
                if move_id != baseline_id and all(move_id not in [self.rules.move_id(x) for x in CASES[k][1]] for k in kept):
                    self.assertNotIn(move_id, actor.moves)

    def test_snapshot_and_codec_restore_owned_receipts_then_reconcile_removal(self):
        engine, actor = self.fixture()
        items.register_feats(engine, actor)
        engine.gm.snapshot("all-fixed-pairs")
        actor.spec["feats"] = []
        items.register_feats(engine, actor)
        self.assertFalse(self.all_move_ids() & set(actor.moves))
        engine.gm.restore("all-fixed-pairs")
        self.assertTrue(self.all_move_ids().issubset(set(actor.moves)))
        loaded = CODEC.load_engine(
            self.rules,
            json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False)),
        )
        restored = loaded.everyone[0]
        self.assertTrue(self.all_move_ids().issubset(set(encounter.usable_moves(loaded, restored))))
        restored.spec["feats"] = []
        items.register_feats(loaded, restored)
        self.assertFalse(self.all_move_ids() & set(restored.moves))
        self.assertTrue(loaded.validate_state()["valid"])

    def test_late_invalid_pair_fails_before_any_source_move_or_rng_mutation(self):
        engine, actor = self.fixture()
        late_uid = list(CASES)[-1]
        before = deepcopy((actor.spec, actor.moves, engine.rng.getstate()))
        with patch.dict(CLASS_MOVES.FIXED, {late_uid: ("오물웨이브", "존재하지않는기술")}):
            with self.assertRaises(ValueError):
                items.register_feats(engine, actor)
        self.assertEqual((actor.spec, actor.moves, engine.rng.getstate()), before)


if __name__ == "__main__":
    unittest.main()
