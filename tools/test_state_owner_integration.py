"""Actual source selection and declared/native training consumption witnesses."""
from copy import copy,deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import patch

import test_foundation_source_selection as SOURCE
import test_foundation_training_rewards as REWARDS
import test_category2_partial_entities as PARTIAL_FIXTURE
from ruleset import RuleFilter,RuleSelection
from state_codec import dump_engine,load_engine
import source_context
import training_features as TRAINING
import world_entities as WORLD


class SourceOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):SOURCE.SourceSelectionTests.setUpClass()

    def fixture(self):
        f=SOURCE.SourceSelectionTests();f.setUp();return f

    def test_each_native_public_selection_reads_pinned_source_once_without_later_cache(self):
        f=self.fixture();uid='C2CSV/input/db/edges.csv:R24:main'
        source=f.rules.selection.units[uid]['source']
        path='input/'+source['file'].removeprefix('input/')
        with patch.object(source_context,'verified_source',wraps=source_context.verified_source) as observed:
            f.rules.select_source_definition(uid)
            self.assertEqual(sum(call.args[1]['file']==path for call in observed.call_args_list),1)
            f.rules.select_source_definition(uid)
            self.assertEqual(sum(call.args[1]['file']==path for call in observed.call_args_list),2)
        original=Path.read_bytes
        def changed(candidate):
            raw=original(candidate)
            return raw+b'\nchanged after first selection' if candidate.name=='edges.csv' else raw
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'source changed'):f.rules.select_source_definition(uid)

    def test_overridden_native_hook_is_called_and_cannot_lend_freshness_evidence(self):
        f=self.fixture();uid='C2CSV/input/db/edges.csv:R24:main';native=f.rules._selected_rule
        changed=False;calls=[];original=Path.read_bytes
        def reader(requested,*args,**kwargs):
            nonlocal changed
            result=native(requested,*args,**kwargs);calls.append(requested);changed=True
            return result
        def read(candidate):
            raw=original(candidate)
            return raw+b'\nchanged inside overridden reader' if changed and candidate.name=='edges.csv' else raw
        f.rules._selected_rule=reader
        with patch.object(Path,'read_bytes',read):
            with self.assertRaisesRegex(ValueError,'source changed'):f.rules.select_source_definition(uid)
        self.assertEqual(calls,[uid])

    def test_foreign_bound_native_reader_keeps_its_original_admission_authority(self):
        f=self.fixture();uid=f.uid;foreign=copy(f.rules)
        foreign.ruleset=RuleFilter({'exclude_units':[uid]})
        foreign.selection=RuleSelection(foreign.ruleset,list(f.rules.selection.units.values()))
        f.rules._selected_rule=foreign._selected_rule
        with self.assertRaises(ValueError):f.rules.select_source_definition(uid)

    def test_native_dependency_chain_reuses_exact_reference_and_checks_next_call(self):
        f=self.fixture()
        with patch.object(source_context,'verified_source',wraps=source_context.verified_source) as observed:
            f.rules.select_source_definition('ball')
        files=[call.args[1]['file'] for call in observed.call_args_list]
        self.assertCountEqual(files,['input/ch05-pokemon.md','input/ch07-combat.md'])
        original=Path.read_bytes
        def changed(candidate):
            raw=original(candidate)
            return raw+b'\nchanged dependency' if candidate.name=='ch05-pokemon.md' else raw
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaisesRegex(ValueError,'source changed'):f.rules.select_source_definition('ball')

    def test_native_chapter_dependencies_keep_different_digest_and_file_checks(self):
        f=self.fixture();f.rules.selection=deepcopy(f.rules.selection)
        uid='audit/source-chapter-dependencies';base='ch09-equipment/장비/무기'
        origin=deepcopy(f.rules.selection.units[base]['source'])
        f.rules.selection.register_derived({'id':uid,'title':'source dependency fixture','source':origin},(base,'combat/struggle'))
        with patch.object(source_context,'verified_source',wraps=source_context.verified_source) as observed:
            f.rules.select_source_definition(uid)
        self.assertCountEqual([call.args[1]['file'] for call in observed.call_args_list],
                              ['input/ch09-equipment.md','input/ch07-combat.md'])
        # A dependency with the same file but a different digest is not the
        # same evidence. Nor is a different file that claims an equal digest.
        dependency=f.rules.selection.units[base]['source']
        dependency['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'source changed'):f.rules.select_source_definition(uid)
        dependency['sha256']=origin['sha256'];dependency['file']='ch07-combat.md'
        with self.assertRaisesRegex(ValueError,'source changed'):f.rules.select_source_definition(uid)


class TrainingOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):REWARDS.RewardTests.setUpClass()

    def fixture(self):
        f=REWARDS.RewardTests();f.setUp();return f

    def test_declared_training_reaches_actual_initiative_and_restored_expiry(self):
        f=self.fixture();p=f.ps[0];before=f.e.initiative_value(p)
        self.assertEqual(before.unresolved,())
        receipt=f.execute();value=f.e.initiative_value(p)
        self.assertEqual(value.unresolved,())
        self.assertEqual(value.value,before.value+2)
        rows=[row for row in value.derivation['initiative_contributions'] if row['id'].startswith('training:')]
        self.assertEqual([(row['source'],row['value']) for row in rows],[('ch05-pokemon/포켓몬-훈련',2)])
        self.assertEqual(TRAINING.bonus(p,'initiative'),2)
        restored=load_engine(f.r,json.loads(json.dumps(dump_engine(f.e),ensure_ascii=False)))
        index=WORLD.actor_index(restored);owner=index[f.a.entity_id];target=index[p.entity_id]
        self.assertEqual(restored.initiative_value(target).value,value.value)
        snapshot=dump_engine(restored)
        restored.apply_training_rewards(owner,[index[x.entity_id] for x in f.ps],f.policy(),safe=True,request_id='reward')
        self.assertEqual(dump_engine(restored),snapshot)
        TRAINING.extended_rest(restored,owner)
        self.assertEqual(restored.initiative_value(target).value,before.value)
        self.assertFalse(TRAINING.active(target))
        self.assertEqual(receipt['trainer_id'],f.a.entity_id)

    def test_native_training_replaces_declared_bonus_and_keeps_native_source_receipt(self):
        f=self.fixture();p=f.ps[0];base=f.e.initiative_value(p).value
        f.execute();self.assertEqual(f.e.initiative_value(p).value,base+2)
        f.e.train_pokemon(f.a,[(p,[TRAINING.AGILITY])],minutes=30,reason='native regime replaces prior training',request_id='replacement',safe=True)
        current=f.e.initiative_value(p)
        self.assertEqual(current.unresolved,());self.assertEqual(current.value,base+4)
        rows=TRAINING.active(p);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['rule_id'],TRAINING.AGILITY)
        self.assertNotIn('training_reward_definition',rows[0])
        self.assertEqual(TRAINING.bonus(p,'initiative'),4)


class PartialOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):PARTIAL_FIXTURE.Tests.setUpClass()

    def test_public_damage_and_heal_reject_partial_before_projection_or_mutation(self):
        f=PARTIAL_FIXTURE.Tests();f.setUp()
        view=f.e.gm.observe_partial_entity(name='partial witness',actor_kind='trainer',reason='no combat facts observed')
        row=f.e._partial_entities[view['entity_id']]
        before=dump_engine(f.e);rng=f.e.rng.getstate()
        with patch('ability_state_projection.hp_change_interested',side_effect=AssertionError('projection reached before partial admission')):
            for action in (lambda:f.e.take_damage(row,5),lambda:f.e.heal(row,5)):
                with self.subTest(action=action):
                    with self.assertRaisesRegex(ValueError,'missing stats are unknown'):action()
                    self.assertEqual(dump_engine(f.e),before)
                    self.assertEqual(f.e.rng.getstate(),rng)


if __name__=='__main__':unittest.main()
