"""Source/profile selection contract tests; no individual rule behavior claims."""
import itertools,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from ruleset import RuleFilter,classify

def unit(id='move/example',variant=None,file='db/moves.csv',tags=None):
    return dict(id=id,title='Example'+(' ['+variant+']' if variant else ''),source=dict(file=file),tags=tags or [])

class SelectionTests(unittest.TestCase):
    def test_unknown_source_is_not_core(self):
        self.assertEqual(classify(unit(file='unmapped-supplement.md'))[0],'unknown')
        self.assertFalse(RuleFilter({'sources':['core'],'variants':'*'}).allows(unit(file=''))[0])
    def test_prefix_collision_is_not_core(self):
        self.assertEqual(classify(unit(file='ch-invalid-source'))[0],'unknown')
        self.assertEqual(classify(unit(file='db-unregistered.txt'))[0],'unknown')
    def test_unknown_source_has_unresolved_decision(self):
        result=RuleFilter({'sources':'*','variants':'*'}).decision(unit(file='mystery.md'))
        self.assertEqual(result['status'],'unresolved')
        self.assertEqual(result['reason'],'unknown_source')
    def test_decision_normalizes_once_and_public_classify_accepts_raw_records(self):
        from unittest.mock import patch
        from ruleset import source_unit
        record=unit(variant='Playtest',tags=['homebrew'])
        expected=classify(record)
        self.assertEqual(classify(source_unit(record)),expected)
        with patch('ruleset.source_unit', wraps=source_unit) as normalized:
            result=RuleFilter({'sources':'*','variants':'*'}).decision(record)
        self.assertEqual(normalized.call_count,1)
        self.assertEqual(result,{'status':'unresolved','reason':'conflicting_variant_markers:playtest,홈브류'})
    def test_profile_allow_formula_all_16_combinations(self):
        for source,variant,identity,tag in itertools.product([False,True],repeat=4):
            rf=RuleFilter(dict(sources=['core'] if source else [],variants=['playtest'] if variant else [],exclude_units=[] if identity else ['move/example'],exclude_tags=[] if tag else ['test']))
            actual=rf.allows(unit(variant='Playtest',tags=['test']))[0]
            self.assertEqual(actual,source and variant and identity and tag,(source,variant,identity,tag))
    def test_no_variant_is_allowed_when_variant_list_empty(self):
        self.assertTrue(RuleFilter({'sources':['core'],'variants':[]}).allows(unit())[0])
    def test_malformed_profile_rejected(self):
        for profile in [{'sources':'core'},{'variants':'playtest'},{'sources':['missing']},{'variants':['missing']},{'variant_replaces_core':'false'},{'exclude_tags':'homebrew'}]:
            with self.assertRaises((ValueError,TypeError),msg=str(profile)):RuleFilter(profile)
    def fixture(self):
        return [unit(),unit('move/example-playtest','Playtest'),unit('move/example-홈브류','홈브류')]
    def test_ambiguous_replacements_never_depend_on_input_order(self):
        for rows in itertools.permutations(self.fixture()):
            rf=RuleFilter({'sources':'*','variants':'*','variant_replaces_core':True});kept,excluded,alias=rf.split(list(rows))
            self.assertNotIn('move/example',alias)
            self.assertEqual(rf.alias_conflicts,{'move/example':['move/example-playtest','move/example-홈브류']})
            self.assertNotIn('move/example',{u['id'] for u in kept})
            self.assertTrue(any(u['id']=='move/example' and why.startswith('unresolved_variant:') for u,why in excluded))
    def test_explicit_variant_choice_resolves_ambiguity(self):
        for rows in itertools.permutations(self.fixture()):
            rf=RuleFilter({'sources':'*','variants':'*','variant_replaces_core':True,'variant_choices':{'move/example':'move/example-홈브류'}})
            self.assertEqual(rf.split(list(rows))[2],{'move/example':'move/example-홈브류'})
            self.assertEqual(rf.alias_conflicts,{})
    def test_variant_choice_cannot_select_excluded_candidate(self):
        rf=RuleFilter({'sources':'*','variants':['playtest'],'variant_replaces_core':True,'variant_choices':{'move/example':'move/example-홈브류'}})
        with self.assertRaises(ValueError):rf.split(self.fixture())
    def test_single_candidate_preserves_alias(self):
        rf=RuleFilter({'sources':'*','variants':['playtest'],'variant_replaces_core':True})
        self.assertEqual(rf.split(self.fixture())[2],{'move/example':'move/example-playtest'})
    def test_no_replacement_means_no_alias_conflict(self):
        rf=RuleFilter({'sources':'*','variants':'*'})
        self.assertEqual(rf.split(self.fixture())[2],{});self.assertEqual(rf.alias_conflicts,{})
    def test_excluded_base_is_not_reintroduced_by_alias(self):
        rf=RuleFilter({'sources':'*','variants':'*','variant_replaces_core':True,'exclude_units':['move/example']})
        self.assertEqual(rf.split(self.fixture())[2],{})
    def test_duplicate_rule_identity_rejected(self):
        with self.assertRaises(ValueError):RuleFilter({}).split([unit(),unit()])
    def test_missing_selected_version_rejected(self):
        rf=RuleFilter({'unit_versions':{'rule/a':'old'}})
        with self.assertRaises(ValueError):rf.mech_version('rule/a',{'x':1})
    def test_nonmapping_selected_version_rejected(self):
        rf=RuleFilter({'unit_versions':{'rule/a':'old'}})
        with self.assertRaises(ValueError):rf.mech_version('rule/a',{'old':'not a rule'})
    def test_selected_version_does_not_mutate_input(self):
        rf=RuleFilter({'unit_versions':{'rule/a':'old'}});data={'x':2,'old':{'x':1}}
        result=rf.mech_version('rule/a',data)
        self.assertEqual(result['x'],1);self.assertEqual(data,{'x':2,'old':{'x':1}})

    def test_runtime_move_ambiguity_precedes_state_or_rng_access(self):
        from copy import deepcopy
        from engine import Rules,Engine,Combatant
        from ruleset import UnresolvedRuleSelection
        rules=Rules(str(ROOT),ruleset='core');engine=Engine(rules)
        actor=Combatant(rules,deepcopy(rules.creatures['pokemon/archie']))
        engine.everyone=engine.gm.everyone=[actor]
        rules.unresolved_moves['move/막치기']=['move/a','move/b']
        before=deepcopy(actor.__dict__,{id(rules):rules});rng=engine.rng.getstate()
        for action in [lambda:engine.use_move(actor,actor,'move/막치기'),
                       lambda:engine.use_move_on(actor,actor,'move/막치기',[actor])]:
            with self.assertRaises(UnresolvedRuleSelection) as result:action()
            self.assertEqual(result.exception.candidates,('move/a','move/b'))
            self.assertEqual(actor.__dict__,before);self.assertEqual(engine.rng.getstate(),rng)
            self.assertFalse(engine.log_lines)
    def test_runtime_ability_ambiguity_precedes_passive_application(self):
        from copy import deepcopy
        from engine import Rules,Engine,Combatant
        from ruleset import UnresolvedRuleSelection
        rules=Rules(str(ROOT),ruleset='core');engine=Engine(rules)
        actor=Combatant(rules,deepcopy(rules.creatures['pokemon/archie']))
        actor.abilities=['Example'];engine.everyone=engine.gm.everyone=[actor]
        rules.unresolved_abilities['Example']=['a','b']
        before=deepcopy(actor.__dict__,{id(rules):rules});rng=engine.rng.getstate()
        with self.assertRaises(UnresolvedRuleSelection):engine.register_abilities_one(actor,'Example')
        self.assertEqual(actor.__dict__,before);self.assertEqual(engine.rng.getstate(),rng)
        self.assertFalse(engine.log_lines)
    def test_runtime_name_fallback_does_not_reintroduce_conflict(self):
        import tempfile
        from engine import Rules
        from ruleset import UnresolvedRuleSelection
        with tempfile.TemporaryDirectory(prefix='rule-selection-test-') as tmp:
            root=Path(tmp);(root/'output/entities').mkdir(parents=True)
            rows=[{'id':'ability/example','name':'Example'},{'id':'ability/example-playtest','name':'Example [Playtest]'}, {'id':'ability/example-playtest-2','name':'Example [Playtest]'}]
            (root/'output/entities/abilities.json').write_text(json.dumps(rows),encoding='utf-8')
            rules=Rules.__new__(Rules);rules.root=tmp;rules.moves={};rules.core_abilities={}
            rules.ruleset=RuleFilter({'sources':'*','variants':'*','variant_replaces_core':True})
            rules._apply_ruleset()
            self.assertNotIn('Example',rules.ability_alias)
            self.assertEqual(rules.unresolved_abilities['Example'],['ability/example-playtest','ability/example-playtest-2'])
    def test_id_choice_cannot_hide_name_keyed_dispatch_ambiguity(self):
        import tempfile
        from engine import Rules
        with tempfile.TemporaryDirectory(prefix='rule-selection-test-') as tmp:
            root=Path(tmp);(root/'output/entities').mkdir(parents=True)
            rows=[{'id':'ability/example','name':'Example'}, {'id':'ability/example-playtest','name':'Example [Playtest]'}, {'id':'ability/example-playtest-2','name':'Example [Playtest]'}]
            (root/'output/entities/abilities.json').write_text(json.dumps(rows),encoding='utf-8')
            rules=Rules.__new__(Rules);rules.root=tmp;rules.moves={};rules.core_abilities={}
            rules.ruleset=RuleFilter({'sources':'*','variants':'*','variant_replaces_core':True,'variant_choices':{'ability/example':'ability/example-playtest'}})
            rules._apply_ruleset()
            self.assertNotIn('Example',rules.ability_alias)
            self.assertEqual(rules.unresolved_abilities['Example'],['ability/example-playtest','ability/example-playtest-2'])
    def test_name_fallback_with_duplicate_target_ids_stays_unresolved(self):
        import tempfile
        from engine import Rules
        with tempfile.TemporaryDirectory(prefix='rule-selection-test-') as tmp:
            root=Path(tmp);(root/'output/entities').mkdir(parents=True)
            rows=[{'id':'ability/base','name':'Example'},{'id':'ability/variant-a','name':'Example [Playtest]'}, {'id':'ability/variant-b','name':'Example [Playtest]'}]
            (root/'output/entities/abilities.json').write_text(json.dumps(rows),encoding='utf-8')
            rules=Rules.__new__(Rules);rules.root=tmp;rules.moves={};rules.core_abilities={}
            rules.ruleset=RuleFilter({'sources':'*','variants':'*','variant_replaces_core':True});rules._apply_ruleset()
            self.assertNotIn('Example',rules.ability_alias)
            self.assertEqual(rules.unresolved_abilities['Example'],['ability/variant-a','ability/variant-b'])
    def test_runtime_distinct_name_candidates_remain_unresolved(self):
        import tempfile
        from engine import Rules
        with tempfile.TemporaryDirectory(prefix='rule-selection-test-') as tmp:
            root=Path(tmp);(root/'output/entities').mkdir(parents=True)
            rows=[{'id':'ability/base','name':'Example'},{'id':'ability/variant-a','name':'Example [Playtest]'},{'id':'ability/variant-b','name':'Example [홈브류]'}]
            (root/'output/entities/abilities.json').write_text(json.dumps(rows),encoding='utf-8')
            rules=Rules.__new__(Rules);rules.root=tmp;rules.moves={};rules.core_abilities={}
            rules.ruleset=RuleFilter({'sources':'*','variants':'*','variant_replaces_core':True});rules._apply_ruleset()
            self.assertNotIn('Example',rules.ability_alias)
            self.assertEqual(set(rules.unresolved_abilities['Example']),{'Example [Playtest]','Example [홈브류]'})

    def test_default_and_explicit_all_honor_declared_profile(self):
        import tempfile
        profile={'sources':['core'],'variants':[],'rulings_files':['data/selected-ruling.json']}
        with tempfile.TemporaryDirectory(prefix='rule-profile-test-') as tmp:
            root=Path(tmp);(root/'data').mkdir()
            (root/'data/rulesets.json').write_text(json.dumps({'rulesets':{'all':profile}}),encoding='utf-8')
            for name in [None,'all']:
                loaded=RuleFilter.load(tmp,name)
                self.assertEqual(loaded.sources,{'core'})
                self.assertEqual(loaded.variants,set())
                self.assertEqual(loaded.rulings_files,['data/selected-ruling.json'])


    def test_source_metadata_is_not_rewritten_as_core(self):
        from ruleset import source_unit
        for record in [dict(id='move/x',name='X',_source={'file':'supp-polygon.md'}),
                       dict(id='ability/x',name='X',source={'file':'unmapped.md'})]:
            normalized=source_unit(record,'db/moves.csv')
            self.assertFalse(RuleFilter({'sources':['core']}).allows(normalized)[0])
    def test_explicit_empty_provenance_does_not_get_default(self):
        from ruleset import source_unit
        for field in ('source','_source'):
            u=source_unit(dict(id='move/x',name='X',**{field:{}}),'db/moves.csv')
            self.assertEqual(RuleFilter({}).decision(u)['status'],'unresolved')
    def test_custom_source_label_is_not_core(self):
        self.assertEqual(classify(dict(id='move/x',name='X',source='custom'))[0],'custom')
    def test_chapter_metadata_and_all_dependencies_are_checked(self):
        from ruleset import source_unit
        rf=RuleFilter({'sources':['core']})
        self.assertTrue(rf.allows(source_unit(dict(id='rule/x',chapter='ch07-combat')))[0])
        self.assertFalse(rf.allows(source_unit(dict(id='rule/x',chapter='ch07-combat + supp-polygon')))[0])
    def test_homebrew_field_cannot_be_lost(self):
        from ruleset import source_unit
        self.assertFalse(RuleFilter({'variants':[]}).allows(source_unit(dict(id='move/x',name='X',homebrew=True,_source={'file':'db/moves.csv'})))[0])
    def test_wrong_name_suffix_is_not_a_replacement_identity(self):
        rows=[unit(),dict(unit('move/example-playtest','Playtest'),title='Different [Playtest]')]
        self.assertEqual(RuleFilter({'variant_replaces_core':True}).split(rows)[2],{})
    def test_wrong_kind_suffix_is_not_a_replacement_identity(self):
        rows=[dict(unit(),kind='entity:move'),dict(unit('move/example-playtest','Playtest'),kind='entity:feat')]
        self.assertEqual(RuleFilter({'variant_replaces_core':True}).split(rows)[2],{})
    def test_every_catalogued_kind_uses_same_exclusion_gate(self):
        from ruleset import RuleSelection,ExcludedRuleSelection
        for kind in ['entity:move','entity:ability','entity:item','entity:feat','entity:edge','entity:species','definition:condition','procedure','table','entity:recipe','entity:class','definition:capability']:
            with self.subTest(kind=kind):
                row=dict(unit('rule/x',file='supp-polygon.md'),kind=kind)
                selection=RuleSelection(RuleFilter({'sources':['core']}),[row])
                with self.assertRaises(ExcludedRuleSelection):selection.resolve('rule/x')
    def test_direct_name_query_cannot_restore_excluded_identity(self):
        from ruleset import RuleSelection,ExcludedRuleSelection
        selection=RuleSelection(RuleFilter({'exclude_units':['item/a']}),[unit('item/a')])
        with self.assertRaises(ExcludedRuleSelection):selection.resolve_name('Example',('item/',))
    def test_name_keyed_registry_cannot_hide_excluded_overwrite(self):
        from ruleset import RuleSelection,UnresolvedRuleSelection
        rows=[unit('ability/a'),unit('ability/b',file='supp-polygon.md')]
        selection=RuleSelection(RuleFilter({'sources':['core']}),rows)
        with self.assertRaises(UnresolvedRuleSelection):selection.resolve_name('Example',('ability/',))
    def test_missing_identity_is_unresolved_not_an_empty_rule(self):
        from ruleset import RuleSelection,UnresolvedRuleSelection
        with self.assertRaises(UnresolvedRuleSelection):RuleSelection(RuleFilter({}),[]).resolve('rule/missing')
    def test_unhandled_version_cannot_silently_use_default_reader(self):
        from ruleset import RuleSelection,UnresolvedRuleSelection
        selection=RuleSelection(RuleFilter({'unit_versions':{'feat/a':'old'}}),[unit('feat/a')])
        with self.assertRaises(UnresolvedRuleSelection):selection.require_supported_version('feat/a')
        self.assertEqual(selection.require_supported_version('feat/a',True),'feat/a')
    def test_alias_cannot_discard_version_choice_on_original_identity(self):
        from ruleset import RuleSelection,UnresolvedRuleSelection
        selection=RuleSelection(RuleFilter({'variant_replaces_core':True,'unit_versions':{'move/example':'old'}}),self.fixture()[:2])
        with self.assertRaises(UnresolvedRuleSelection):selection.resolve('move/example')
    def test_global_catalog_rejects_unknown_choice_identity(self):
        from ruleset import RuleSelection
        for profile in [{'unit_versions':{'rule/typo':'old'}},{'variant_replaces_core':True,'variant_choices':{'rule/typo':'rule/x'}}]:
            with self.assertRaises(ValueError):RuleSelection(RuleFilter(profile),[unit()]).validate_choices()
    def test_runtime_core_supplement_feature_is_rejected(self):
        from engine import Rules
        from ruleset import ExcludedRuleSelection
        with self.assertRaises(ExcludedRuleSelection):Rules(str(ROOT),ruleset='core').feat_effects('feat/분노의-힘')
    def test_runtime_core_custom_definitions_do_not_enter_registry(self):
        from engine import Rules
        rules=Rules(str(ROOT),ruleset='core')
        self.assertNotIn('pokemon/실험체',rules.species)
        self.assertNotIn('move/오버로드',rules.moves)
        self.assertNotIn('정전기Ω',rules.ability_effects)
    def test_runtime_direct_move_readers_reject_excluded_rule(self):
        from engine import Rules
        from ruleset import ExcludedRuleSelection
        rules=Rules(str(ROOT),ruleset='no-ohko')
        for getter in [rules.move,rules.move_mech,rules.move_id,rules._move_mech]:
            with self.subTest(getter=getter.__name__),self.assertRaises(ExcludedRuleSelection):getter('move/절대영도')
    def test_runtime_mech_exclusion_is_applied(self):
        from engine import Rules
        from ruleset import ExcludedRuleSelection
        rules=Rules(str(ROOT),ruleset='core')
        rules.ruleset=RuleFilter({'sources':['core'],'exclude_units':['combat/evasion']})
        rules._apply_ruleset()
        with self.assertRaises(ExcludedRuleSelection):rules.mech('combat/evasion')
    def test_runtime_condition_class_uses_selected_version(self):
        from engine import Rules
        rules=Rules(str(ROOT),ruleset='core')
        rules.units['condition/화상']['mech']['data']['test_version']={'class':'independent-version-marker'}
        rules.ruleset=RuleFilter({'sources':['core'],'unit_versions':{'condition/화상':'test_version'}})
        rules._apply_ruleset()
        self.assertEqual(rules.condition_class('화상'),'independent-version-marker')
    def test_runtime_all_preserves_custom_and_base_ability_identities(self):
        from engine import Rules
        rules=Rules(str(ROOT),ruleset='all')
        self.assertEqual(rules.move_mech('move/오버로드')[1],'reviewed')
        self.assertNotEqual(rules.selection.resolve_name('정전기Ω',('ability/',)),rules.selection.resolve_name('정전기',('ability/',)))
    def test_runtime_explicit_feature_version_is_not_ignored(self):
        from engine import Rules
        from ruleset import UnresolvedRuleSelection
        rules=Rules(str(ROOT),ruleset='core')
        rules.ruleset=RuleFilter({'sources':['core'],'unit_versions':{'feat/융통-명령':'missing-version'}})
        rules._apply_ruleset()
        with self.assertRaises(UnresolvedRuleSelection):rules.feat_effects('feat/융통-명령')


    def test_derived_identity_requires_every_parent_and_cannot_overwrite(self):
        from ruleset import RuleSelection,ExcludedRuleSelection
        rows=[unit('rule/general'),unit('rule/weapon')]
        selection=RuleSelection(RuleFilter({'exclude_units':['rule/weapon']}),rows)
        with self.assertRaises(ExcludedRuleSelection):selection.register_derived(unit('move/derived'),['rule/general','rule/weapon'])
        self.assertNotIn('move/derived',selection.units)
        selection=RuleSelection(RuleFilter({}),rows)
        with self.assertRaises(ValueError):selection.register_derived(unit('rule/general'),['rule/weapon'])
    def test_runtime_weapon_inherits_source_and_survives_index_rebuild(self):
        from engine import Rules
        from ruleset import require_runtime_weapon,ExcludedRuleSelection
        rules=Rules(str(ROOT),ruleset='core')
        mid='move/무기-독립검사'
        rules.moves[mid]={'id':mid,'name':'독립검사 발버둥','source':'weapon'}
        self.assertEqual(require_runtime_weapon(rules,mid),mid)
        self.assertEqual(rules.move(mid)['id'],mid)
        rules._apply_ruleset()
        self.assertEqual(rules.move(mid)['id'],mid)
        rules.ruleset=RuleFilter({'sources':['core'],'exclude_units':['ch09-equipment/장비/무기']})
        rules._apply_ruleset()
        with self.assertRaises(ExcludedRuleSelection):rules.move(mid)


    def test_classification_does_not_require_runtime_identity(self):
        self.assertEqual(classify({'title':'Example [Playtest]','source':{'file':'db/abilities.csv'}}),('core','playtest'))
    def test_runtime_catalog_does_require_nonempty_identity(self):
        from ruleset import RuleSelection
        for uid in (None,'',42):
            with self.assertRaises(ValueError):RuleSelection(RuleFilter({}),[unit(uid)])


    def test_missing_bare_ability_is_not_silently_bound_to_playtest(self):
        from copy import deepcopy
        from engine import Rules,Engine,Combatant
        from ruleset import RuleSelection,UnresolvedRuleSelection
        rules=Rules(str(ROOT),ruleset='core')
        # Chlorophyll now has a reviewed core source. Use a genuinely absent
        # base identity instead of asserting an obsolete corpus omission.
        name='Missing base fixture'
        alternate=unit('ability/missing-base-playtest','Playtest',file='db/abilities.csv')
        alternate['title']=name+' [Playtest]'
        rules.selection=RuleSelection(rules.ruleset,[*rules.selection.units.values(),alternate])
        self.assertNotIn(name,rules.selection.names)
        self.assertIn(name+' [Playtest]',rules.selection.names)
        engine=Engine(rules);actor=Combatant(rules,deepcopy(rules.creatures['pokemon/archie']))
        actor.abilities=[name];engine.everyone=engine.gm.everyone=[actor]
        before=deepcopy(actor.__dict__,{id(rules):rules})
        with self.assertRaises(UnresolvedRuleSelection):engine.register_abilities_one(actor,name)
        self.assertEqual(actor.__dict__,before)
    def test_explicit_playtest_identity_remains_excluded_from_core(self):
        from engine import Rules
        from ruleset import ExcludedRuleSelection
        rules=Rules(str(ROOT),ruleset='core')
        with self.assertRaises(ExcludedRuleSelection):rules.selection.resolve_name('엽록소 [Playtest]',('ability/',))


    def test_synthetic_ball_checks_both_capture_and_accuracy_sources(self):
        from engine import Rules
        from ruleset import ExcludedRuleSelection
        rules=Rules(str(ROOT),ruleset='core')
        self.assertEqual(rules.move_mech('ball'),({},'none'))
        for uid in ('pokemon/capture-rate','combat/accuracy-roll'):
            rules.ruleset=RuleFilter({'sources':['core'],'exclude_units':[uid]})
            rules._apply_ruleset()
            with self.assertRaises(ExcludedRuleSelection):rules.move_mech('ball')


    def test_ability_attack_preserves_origin_and_rejects_excluded_origin(self):
        from copy import deepcopy
        from engine import Rules,Engine,Combatant
        from ruleset import bind_rule_identity,ExcludedRuleSelection,UnresolvedRuleSelection
        from effects_ext import h_attack
        rules=Rules(str(ROOT),ruleset='core')
        uid=rules.selection.resolve_name('현혹',('ability/',))
        effect=bind_rule_identity({'type':'attack','on_hit':{'apply_status':'잠듦'}},uid)
        calls=[]
        def accuracy(a,t,m):
            calls.append(m['id']);self.assertEqual(rules.move_mech(m['id']),({},'none'));return True,20,False
        engine=Engine(rules);engine.accuracy_check=accuracy;engine.apply_status=lambda t,s:calls.append(s)
        actor=Combatant(rules,deepcopy(rules.creatures['pokemon/archie']))
        target_spec=deepcopy(rules.creatures['pokemon/archie']);target_spec['id']='pokemon/selection-target'
        target=Combatant(rules,target_spec)
        engine.everyone=engine.gm.everyone=[actor,target]
        h_attack(engine,actor,target,effect,{})
        self.assertEqual(calls,['derived/ability-attack/'+uid,'잠듦'])
        rules.ruleset=RuleFilter({'sources':['core'],'exclude_units':[uid]});rules._apply_ruleset();calls.clear()
        with self.assertRaises(ExcludedRuleSelection):h_attack(engine,actor,target,effect,{})
        self.assertEqual(calls,[])
        with self.assertRaises(UnresolvedRuleSelection):h_attack(engine,actor,target,{'type':'attack'},{})
    def test_nested_effect_source_binding_copies_without_retagging_data(self):
        from ruleset import bind_rule_identity
        data={'type':'connection','effect':{'type':'attack','ac':4}}
        result=bind_rule_identity(data,'ability/test')
        self.assertEqual(result['effect']['_rule_id'],'ability/test')
        self.assertNotIn('_rule_id',data)
        self.assertNotIn('_rule_id',data['effect'])


    def audit_fixture(self, rows, profiles):
        import tempfile
        from audit_rule_selection import audit
        with tempfile.TemporaryDirectory(prefix='selection-audit-test-') as tmp:
            root=Path(tmp)
            # These fixtures test audit aggregation, not saved-source authority.
            for rel in ['tools/audit_rule_selection.py','engine/ruleset.py','engine/engine.py']:
                path=root/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture',encoding='utf-8')
            (root/'data').mkdir();(root/'output').mkdir()
            (root/'data/rulesets.json').write_text(json.dumps({'rulesets':profiles}),encoding='utf-8')
            (root/'output/ruleunits.jsonl').write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
            return audit(root)

    def test_audit_marker_and_lineage_ambiguity_are_incomplete_per_profile(self):
        rows=[dict(unit('ability/conflict','Playtest'),keyword='홈브류'),
              dict(unit('poke_edge/lineage'),source_group='기타/홈브류')]
        report=self.audit_fixture(rows,{'core':{'sources':['core'],'variants':[]},'all':{'sources':'*','variants':'*'}})
        self.assertEqual(report['status'],'incomplete');self.assertEqual(report['errors'],[])
        expected=[{'id':'ability/conflict','reason':'conflicting_variant_markers:playtest,홈브류'},
                  {'id':'poke_edge/lineage','reason':'unknown_variant_lineage:기타/홈브류'}]
        for profile in report['profiles']:
            self.assertEqual(profile['unresolved_units'],expected)
            self.assertEqual(profile['unresolved_variant_families'],{})
            self.assertTrue(profile['partition_ok']);self.assertTrue(profile['order_independent'])

    def test_audit_resolved_variant_and_explicit_exclusion_are_not_unresolved(self):
        rows=[unit('ability/explicit','Playtest'),dict(unit('ability/conflict','Playtest'),keyword='홈브류')]
        report=self.audit_fixture(rows,{
            'core':{'sources':['core'],'variants':[],'exclude_units':['ability/conflict']},
            'all':{'sources':'*','variants':'*','exclude_units':['ability/conflict']}})
        self.assertEqual(report['status'],'checks_passed');self.assertEqual(report['errors'],[])
        profiles={p['profile']:p for p in report['profiles']}
        self.assertEqual(profiles['core']['kept'],0);self.assertEqual(profiles['all']['kept'],1)
        for profile in profiles.values():self.assertEqual(profile['unresolved_units'],[])

class SelectionFreshnessTests(unittest.TestCase):
    def fixture(self):
        from ruleset import RuleSelection
        rows=[unit(),unit('move/example-playtest','Playtest'),unit('move/example-홈브류','홈브류')]
        rf=RuleFilter({'variant_replaces_core':True,'variant_choices':{'move/example':'move/example-playtest'}})
        return rf,RuleSelection(rf,rows),rows

    def test_cached_admission_rejects_changed_effective_settings(self):
        from ruleset import UnresolvedRuleSelection
        changes=[lambda rf:rf.sources.clear(),lambda rf:rf.variants.clear(),
                 lambda rf:rf.exclude_units.add('move/example'),lambda rf:rf.exclude_tags.add('new-tag'),
                 lambda rf:rf.variant_choices.update({'move/example':'move/example-홈브류'}),
                 lambda rf:setattr(rf,'replaces',False),lambda rf:rf.unit_versions.update({'move/example-playtest':'other'}),
                 lambda rf:rf.rulings_files.append('data/gm-rulings-new.json')]
        for change in changes:
            rf,selection,_=self.fixture()
            self.assertEqual(selection.resolve('move/example'),'move/example-playtest')
            change(rf)
            with self.subTest(change=change),self.assertRaisesRegex(UnresolvedRuleSelection,'selection_profile_changed'):
                selection.resolve('move/example')

    def test_declared_profile_drift_and_restoration(self):
        from ruleset import UnresolvedRuleSelection
        rf,selection,_=self.fixture()
        rf.profile['variant_choices']['move/example']='move/example-홈브류'
        with self.assertRaisesRegex(UnresolvedRuleSelection,'selection_profile_changed'):
            selection.resolve('move/example')
        rf.profile['variant_choices']['move/example']='move/example-playtest'
        self.assertEqual(selection.resolve('move/example'),'move/example-playtest')

    def test_rebuilding_selects_new_variant_without_mutating_old_index(self):
        from ruleset import RuleSelection,UnresolvedRuleSelection
        rf,old,rows=self.fixture()
        rf.variant_choices['move/example']='move/example-홈브류'
        new=RuleSelection(rf,rows)
        self.assertEqual(new.resolve('move/example'),'move/example-홈브류')
        with self.assertRaisesRegex(UnresolvedRuleSelection,'selection_profile_changed'):
            old.resolve('move/example')

if __name__=='__main__':
    import hashlib
    from datetime import datetime,timezone
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='SELECTION-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='SELECTION-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='SELECTION-'+t._testMethodName,status='error'))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    paths=[Path(__file__),ROOT/'tools/audit_rule_selection.py',ROOT/'engine/ruleset.py',ROOT/'engine/engine.py',ROOT/'engine/effects_ext.py',ROOT/'data/rulesets.json',ROOT/'data/verification/rule-selection-semantics.json']
    paths += [ROOT/rel for rel in ['output/ruleunits.jsonl','output/entities/moves.json','output/entities/abilities.json','data/core-rules.json','data/conditions.json','data/lookup-tables.json','data/progression-rules.json','data/feats-mech.json','data/feats-llm.json','data/custom/species/silheomche.json'] if (ROOT/rel).exists()]
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Profile selection, all-kind catalog admission, and public runtime reader regressions. Raw dictionaries, source authority, and every external mutation path remain uncertified.',results=result.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/rule-selection-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
