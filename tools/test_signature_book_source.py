"""The same native consumer contract, explicitly acquired from C03-141."""
from copy import deepcopy
import unittest
from unittest.mock import patch

import test_category2_signature_moves as fixture
import signature_moves as S
import trainer_feature_acquisition as A


class SignatureBookSourceTests(fixture.SignatureMoveTests):
    def acquire(self, *args, **kwargs):
        kwargs.setdefault("source_clause_id", S.BOOK_SOURCE)
        return super().acquire(*args, **kwargs)

    def test_exact_book_and_csv_requests_cannot_relabel_one_acquisition(self):
        row = self.acquire()
        self.assertEqual(row["source"], {"clause_id": "C03-141",
            "file": S.BOOK_FILE, "sha256": S.BOOK_SHA256, "version": 1})
        before = self.state()
        with self.assertRaisesRegex(ValueError, "replay"):
            super().acquire(source_clause_id=S.SOURCE)
        self.assertEqual(self.state(), before)
        changed = deepcopy(row)
        changed["source"] = S.source(self.rules, S.SOURCE)
        changed = A._seal({k: v for k, v in changed.items() if k != "integrity"})
        self.actor.spec[A.LEDGER_KEY]["signature/1"] = changed
        with self.assertRaises(ValueError):
            S.receipt(self.actor)

    def test_unreviewed_book_version_and_catalog_binding_refuse_before_mutation(self):
        before = self.state()
        with patch.dict(self.rules.ruleset.unit_versions, {S.BOOK_SOURCE: "different"}):
            with self.assertRaisesRegex(ValueError, "profile|version"):
                self.acquire()
        unit = self.rules.selection.units[S.FEATURE]
        with patch.dict(unit["source"], {"lines": [856, 861]}):
            with self.assertRaisesRegex(ValueError, "profile|binding"):
                self.acquire()
        self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main()
