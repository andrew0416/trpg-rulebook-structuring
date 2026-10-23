"""Additional CSV Poison Glands parsing applies only to that selected branch."""
import unittest
from unittest.mock import patch
import csv_item_capability_contracts as CAP
import custom_species
import frequency


class PoisonEligibilityScopeTests(unittest.TestCase):
    def test_unselected_homebrew_does_not_parse_nonprinted_poison_move(self):
        move={'name':'unrelated poison source','type':'독','range':'source-defined range','frequency':'source-defined frequency'}
        with patch.object(custom_species,'parse_range',side_effect=AssertionError('unselected parser')), patch.object(frequency,'parse',side_effect=AssertionError('unselected parser')):
            self.assertFalse(CAP.poison_glands_eligible(move,homebrew=False))

    def test_nonpoison_move_does_not_enter_selected_poison_parser(self):
        move={'name':'unrelated normal source','type':'노말','range':'source-defined range','frequency':'source-defined frequency'}
        with patch.object(custom_species,'parse_range',side_effect=AssertionError('foreign type parser')), patch.object(frequency,'parse',side_effect=AssertionError('foreign type parser')):
            self.assertFalse(CAP.poison_glands_eligible(move,homebrew=True))
        for name in CAP.POISON_MOVES:
            self.assertTrue(CAP.poison_glands_eligible({'name':name},homebrew=False))

