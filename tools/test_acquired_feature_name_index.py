"""Live acquisition aliases stay live when only immutable ID prefixes are indexed."""
from pathlib import Path
from types import SimpleNamespace
from collections import UserDict
import sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
import acquired_features as A


def original_names(actor,prefix):
    result={}
    for uid,unit in actor.r.selection.units.items():
        if not uid.startswith(prefix):continue
        for name in (uid,unit.get('title'),unit.get('eng')):
            if name:result.setdefault(name,[]).append(uid)
    return result


class AcquiredFeatureNameIndexTests(unittest.TestCase):
    def actor(self,units):
        return SimpleNamespace(r=SimpleNamespace(selection=SimpleNamespace(units=units)))

    def setUp(self):A._prefix_ids.cache_clear()

    def assert_same(self,actor,prefix='feat/'):
        self.assertEqual(list(A._names(actor,prefix).items()),list(original_names(actor,prefix).items()))

    def test_alias_values_are_live_and_duplicate_ambiguity_is_preserved(self):
        actor=self.actor({'feat/a':{'title':'same','eng':'same'},'feat/b':{'title':'B'}})
        self.assert_same(actor)
        self.assertEqual(A._names(actor,'feat/')['same'],['feat/a','feat/a'])
        actor.r.selection.units['feat/a'].update(title='changed',eng=None)
        self.assert_same(actor)
        self.assertNotIn('same',A._names(actor,'feat/'))

    def test_add_remove_reorder_and_catalog_replacement_are_immediately_visible(self):
        units={'feat/a':{'title':'A'},'class/c':{'title':'C'}};actor=self.actor(units)
        self.assert_same(actor)
        units['feat/b']={'title':'B'};self.assert_same(actor)
        del units['feat/a'];self.assert_same(actor)
        units['feat/a']={'title':'new A'};self.assert_same(actor)
        actor.r.selection.units=dict(reversed(list(units.items())));self.assert_same(actor)
        actor.r.selection.units={key:{'title':'new '+key} for key in units};self.assert_same(actor)

    def test_custom_mapping_items_and_custom_unit_get_keep_original_callbacks(self):
        calls=[]
        class Mapping(UserDict):
            def items(self):calls.append('items');return super().items()
        class Unit(dict):
            def get(self,key,default=None):calls.append(key);return super().get(key,default)
        actor=self.actor(Mapping({'feat/a':Unit(title='A',eng='English')}))
        actual=A._names(actor,'feat/');actual_calls=list(calls);calls.clear()
        self.assertEqual(actual,original_names(actor,'feat/'))
        self.assertEqual(actual_calls,calls)
        self.assertEqual(A._prefix_ids.cache_info().currsize,0)

    def test_exact_catalog_with_custom_unit_retains_get_side_effects(self):
        calls=[]
        class Unit(dict):
            def get(self,key,default=None):calls.append(key);return super().get(key,default)
        actor=self.actor({'feat/a':{'title':'A'},'feat/b':Unit(title='B',eng='Bee')})
        actual=A._names(actor,'feat/');actual_calls=list(calls);calls.clear()
        self.assertEqual(actual,original_names(actor,'feat/'));self.assertEqual(actual_calls,calls)

    def test_non_exact_keys_use_original_dynamic_startswith(self):
        calls=[]
        class Key(str):
            def startswith(self,prefix):calls.append(prefix);return super().startswith(prefix)
        actor=self.actor({Key('feat/a'):{'title':'A'},'class/b':{'title':'B'}})
        actual=A._names(actor,'feat/');actual_calls=list(calls);calls.clear()
        self.assertEqual(actual,original_names(actor,'feat/'));self.assertEqual(actual_calls,calls)
        self.assertEqual(A._prefix_ids.cache_info().currsize,0)

    def test_custom_alias_truth_and_hash_callbacks_are_not_cached(self):
        calls=[]
        class Alias(str):
            def __bool__(self):calls.append('bool');return True
            def __hash__(self):calls.append('hash');return super().__hash__()
        actor=self.actor({'feat/a':{'title':Alias('A'),'eng':None}})
        A._names(actor,'feat/');actual_calls=list(calls);calls.clear()
        original_names(actor,'feat/');self.assertEqual(actual_calls,calls)

    def test_malformed_rows_and_aliases_keep_original_errors(self):
        for unit in (None,{'title':[]},{'eng':{'x':1}}):
            actor=self.actor({'feat/a':unit})
            try:original_names(actor,'feat/')
            except Exception as exc:expected=(type(exc),str(exc))
            else:expected=None
            try:A._names(actor,'feat/')
            except Exception as exc:actual=(type(exc),str(exc))
            else:actual=None
            self.assertEqual(actual,expected)

    def test_prefix_types_and_errors_keep_original_semantics(self):
        class Prefix(str):pass
        actor=self.actor({'feat/a':{'title':'A'}})
        self.assert_same(actor,Prefix('feat/'));self.assert_same(actor,('feat/','class/'))
        for prefix in (None,1):
            with self.assertRaises(TypeError):A._names(actor,prefix)

    def test_cache_is_bounded_and_does_not_change_rule_or_selection_state(self):
        actor=self.actor({'feat/a':{'title':'A'}})
        before=(dict(vars(actor.r)),dict(vars(actor.r.selection)))
        for index in range(40):self.assert_same(actor,str(index))
        self.assertEqual(A._prefix_ids.cache_info().maxsize,16)
        self.assertEqual(A._prefix_ids.cache_info().currsize,16)
        self.assertEqual((vars(actor.r),vars(actor.r.selection)),before)

    def test_resolve_still_calls_current_admission_after_each_name_lookup(self):
        actor=self.actor({'feat/a':{'title':'A'}});calls=[]
        def selected(uid,**kwargs):calls.append((uid,kwargs));return uid
        actor.r._selected_rule=selected
        self.assertEqual(A._resolve(actor,'A','feat/'),'feat/a')
        self.assertEqual(A._resolve(actor,'A','feat/'),'feat/a')
        self.assertEqual(len(calls),2)
        def denied(uid,**kwargs):raise ValueError('current admission denied')
        actor.r._selected_rule=denied
        with self.assertRaisesRegex(ValueError,'current admission denied'):A._resolve(actor,'A','feat/')


if __name__=='__main__':unittest.main()
