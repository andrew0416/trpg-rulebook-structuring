"""Source-field preservation, native script reads, and source-selection boundaries."""
from pathlib import Path
import sys, json, unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from copy import copy
from contextlib import contextmanager
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'engine'))
from engine import Rules
import source_catalog

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rules = Rules(ROOT)
  cls.entries = json.loads((ROOT/'data/source-catalog.json').read_text(encoding='utf-8'))['entries']
 def test_all_native_reads_preserve_every_source_line_and_cell(self):
  self.assertEqual(len(self.entries), 28)
  for entry in self.entries:
   with self.subTest(clause=entry['id']):
    result = self.rules.catalog_definition(entry['id'])
    source = (ROOT/entry['source_file']).read_text(encoding='utf-8').splitlines()
    first,last = entry['lines']
    self.assertEqual([r['text'] for r in result['records']], source[first-1:last])
    self.assertEqual([r['line'] for r in result['records']], list(range(first,last+1)))
    actual = []
    for table in result['tables']:
     if table['columns']: actual.append([c['label'] for c in table['columns']])
     actual.extend(r['cells'] for r in table['rows'])
    expected = [[c.strip() for c in line.strip()[1:-1].split('|')]
                for line in source[first-1:last] if line.strip().startswith('|')]
    self.assertEqual(actual, expected)
    self.assertFalse(result['effect_execution_certified'])
 def test_duplicate_headers_headerless_rows_and_missing_number_are_preserved(self):
  tm = self.rules.catalog_definition('C09-147')['tables'][0]
  self.assertEqual([c['label'] for c in tm['columns']], ['기술머신','가격']*4)
  self.assertEqual(len(tm['rows']),25)
  self.assertEqual(tm['rows'][3]['cells'][2:4], ['사이코키네시스','3000원'])
  hm = self.rules.catalog_definition('C09-148')['tables'][0]
  self.assertEqual(hm['columns'],[])
  self.assertEqual(len(hm['rows']),6)
  self.assertEqual(hm['rows'][0]['cells'],['HM1:풀베기','75원'])
  balls = self.rules.catalog_definition('C09-090')['tables'][0]
  self.assertEqual(len(balls['rows']),25)
  self.assertEqual(balls['rows'][3]['cells'][1],'-100')
 def test_returned_records_cannot_mutate_later_reads(self):
  a=self.rules.catalog_definition('C09-090');a['tables'][0]['rows'].clear();a['source']['lines'][0]=0
  b=self.rules.catalog_definition('C09-090')
  self.assertEqual(len(b['tables'][0]['rows']),25)
  self.assertEqual(b['source']['lines'],[31,58])
 def test_selection_is_checked_on_each_read_including_cached_source(self):
  self.rules.catalog_definition('C09-090')
  with patch.object(self.rules,'_selected_rule',side_effect=ValueError('excluded')):
   with self.assertRaisesRegex(ValueError,'excluded'):self.rules.catalog_definition('C09-090')
  with patch.object(self.rules,'_selected_rule',return_value='another/version'):
   with self.assertRaisesRegex(ValueError,'replacement'):self.rules.catalog_definition('C09-090')
 def test_changed_source_is_rejected_before_publishing_partial_catalog(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);(root/'data').mkdir();(root/'input').mkdir()
   (root/'data/source-catalog.json').write_bytes((ROOT/'data/source-catalog.json').read_bytes())
   (root/'input/ch09-equipment.md').write_bytes((ROOT/'input/ch09-equipment.md').read_bytes()+b'changed')
   rules=SimpleNamespace(root=root)
   with self.assertRaisesRegex(ValueError,'source changed'):source_catalog.definition(rules,'C09-090')
   self.assertFalse(hasattr(rules,'_source_catalog'))
 @contextmanager
 def isolated_catalog(self):
  with TemporaryDirectory() as directory:
   root=Path(directory);(root/'data').mkdir();(root/'input').mkdir()
   (root/'data/source-catalog.json').write_bytes((ROOT/'data/source-catalog.json').read_bytes())
   for name in {e['source_file'] for e in self.entries}:
    (root/name).parent.mkdir(parents=True,exist_ok=True)
    (root/name).write_bytes((ROOT/name).read_bytes())
   rules=copy(self.rules);rules.root=root
   rules.__dict__.pop('_source_catalog',None)
   rules.__dict__.pop('_source_catalog_identity',None)
   yield rules,root
 def test_cached_read_rejects_changed_source_and_recovers_only_matching_bytes(self):
  with self.isolated_catalog() as (rules,root):
   first=rules.catalog_definition('C09-090')
   source=root/'input/ch09-equipment.md';original=source.read_bytes()
   source.write_bytes(original+b'changed')
   with self.assertRaisesRegex(ValueError,'source changed'):
    rules.catalog_definition('C09-090')
   source.write_bytes(original)
   self.assertEqual(rules.catalog_definition('C09-090'),first)
 def test_cached_read_rejects_catalog_edit_even_when_source_unchanged(self):
  with self.isolated_catalog() as (rules,root):
   rules.catalog_definition('C09-090')
   path=root/'data/source-catalog.json';doc=json.loads(path.read_text(encoding='utf-8'))
   doc['entries'][0]['title']='changed definition'
   path.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'definition or root changed'):
    rules.catalog_definition('C09-090')
 def test_cached_read_rejects_rebinding_rules_to_other_root(self):
  with self.isolated_catalog() as (rules,root):
   rules.catalog_definition('C09-090')
   rules.root=ROOT
   with self.assertRaisesRegex(ValueError,'definition or root changed'):
    rules.catalog_definition('C09-090')
 def test_unknown_identity_has_no_name_fallback(self):
  with self.assertRaises(KeyError):self.rules.catalog_definition('몬스터볼')

if __name__=='__main__':unittest.main()
