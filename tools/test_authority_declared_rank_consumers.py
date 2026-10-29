"""Declared skill domains across actual acquisition, effects and native checks."""
from copy import copy, deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools'),str(ROOT/'examples')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from declared_skill_ranks import configure
import skill_modifiers as SK
import state_fields as F
import state_codec as CODEC
import world_entities as W
import trainer_feature_acquisition as TFA
import common_checks as C
import skill_feature_actions as SF
from native_scenario_fixture import assert_rejected_unchanged
import test_book_sage_full as SAGE_FIX
import test_book_ninja_full as NINJA_FIX
import test_book_captured_momentum as MOMENTUM_FIX
import test_book_capture_specialist as CAPTURE_FIX

STATS=dict.fromkeys(('hp','atk','def','spa','spd','spe'),10)


class DeclaredRankConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=Rules(ROOT,ruleset='core')
        cls.errata=Rules(ROOT,ruleset='core+errata')

    def rules(self,base=None):
        result=copy(self.base if base is None else base)
        result.rulings=deepcopy(result.rulings)
        return result

    def fixture(self,rank=9,*,declare=True,scope='campaign',family=None):
        rules=self.rules()
        if declare:configure(rules,scope=scope)
        engine=Engine(rules,73)
        extra={'classes':[],'feats':[],'edges':[],'exp_bank':100,
               'skills':{row['aliases'][0]:rank for row in rules.skill_policy['skills'].values()}}
        if family=='coordinator':extra['edges']=['edge/우아함']
        if family=='oracle':extra['edges']=['edge/신비한-감각']
        if family=='telepath':
            extra.update(edges=['edge/원소-교감','edge/강철의-정신'],
                         edge_choices={'edge/원소-교감':'에스퍼'})
        if family=='roughneck':extra['edges']=['edge/협박하는-존재']
        actor=Combatant(rules,build_trainer(rules,'declared consumer',30,STATS,abilities=[],extra=extra))
        engine.gm.add_combatant(actor,reason='observed campaign character')
        return engine,actor

    def roundtrip(self,engine,actor,base=None):
        restored=CODEC.load_engine(self.base if base is None else base,
            json.loads(json.dumps(CODEC.dump_engine(engine),ensure_ascii=False)))
        return restored,W.actor_index(restored)[actor.entity_id]

    def test_sparse_domains_default_rejection_effect_eight_and_rule_isolation(self):
        rules=self.rules()
        for value in (7,9,True,0,-1,7.0):
            with self.subTest(value=value),self.assertRaises(ValueError):
                SK.validate_rank_value(rules,value)
        self.assertEqual(SK.validate_rank_value(rules,8,kind='effective'),8)
        configure(rules)
        for value in (7,9,10):self.assertEqual(SK.validate_rank_value(rules,value),value)
        with self.assertRaisesRegex(ValueError,'policy conflict'):SK.validate_rank_value(rules,8)
        isolated_policy=dict(rules.skill_policy,rank_effects={
            'ability/unselected-rank-nine':{'effective_rank':9},
            'ability/unselected-rank-six':{'effective_rank':6}})
        with patch.object(rules,'skill_policy',isolated_policy):
            self.assertEqual(SK.validate_rank_value(rules,9,kind='effective'),9)
            self.assertEqual(SK.validate_rank_value(rules,6,kind='effective'),6)
        with self.assertRaisesRegex(ValueError,'policy conflict'):SK.validate_rank_value(self.base,9)
        with self.assertRaises(ValueError):C.SkillRoll(7,(1,)*7)
        with self.assertRaises(ValueError):C.extended([],10,2,7,True)
        self.assertEqual(C.AdjustedSkillRoll(7,(1,)*7,dice_count=7).total,7)

    def test_public_family_acquisitions_keep_historical_rank_nine_through_restore(self):
        import capture_techniques as CT
        families=('trickster','oracle','hex_maniac','sage','ninja','musician','telepath',
                  'mentor','roughneck','capture','walk_it_off','breather','coordinator')
        for name in families:
            with self.subTest(family=name):
                engine,actor=self.fixture(family=name)
                if name=='capture':
                    CT.acquire(engine,actor,CT.CLASS,acquisition_request_id='rank/class',
                        selected_techniques=[CAPTURE_FIX.choice('작업 도구'),CAPTURE_FIX.choice('커브볼')],
                        rank=0,lifecycle_policy=TFA.LIFECYCLE_WHILE_OWNED)
                elif name=='mentor':
                    engine.acquire_mentor_feature(actor,request_id='rank/class',
                        skills=['매력','포켓몬학'],variant='core',tutoring_policy='core')
                else:
                    module=__import__(name)
                    feature=module.FEATURE if name=='walk_it_off' else module.CLASS
                    options={'selection':{'ability':module.OMEN}} if name=='hex_maniac' else {}
                    TFA.acquire_static(engine,actor,feature,acquisition_request_id='rank/class',**options)
                original=[deepcopy(row['snapshot']) for _,row in TFA.static_acquisitions(actor)]
                ledger=deepcopy(actor.spec.get(TFA.LEDGER_KEY))
                self.assertTrue(original or ledger,'actual acquisition receipt required')
                F.base_patch(actor,{'skills':dict.fromkeys(actor.spec['skills'],6)},
                             reason='current rank changes without rewriting historical qualification')
                fresh,restored=self.roundtrip(engine,actor)
                self.assertEqual([row['snapshot'] for _,row in TFA.static_acquisitions(restored)],original)
                self.assertEqual(restored.spec.get(TFA.LEDGER_KEY),ledger)
                self.assertTrue(fresh.validate_state()['valid'])
        engine,actor=self.fixture(2,declare=False)
        import sage
        assert_rejected_unchanged(engine,lambda:TFA.acquire_static(
            engine,actor,sage.CLASS,acquisition_request_id='too-low'),reason_pattern='rank|prerequisite')

    def test_narrowed_declaration_reports_history_conflict_without_rewriting_state(self):
        import sage
        engine,actor=self.fixture(scope='scene')
        TFA.acquire_static(engine,actor,sage.CLASS,acquisition_request_id='scene-sage')
        F.base_patch(actor,{'skills':dict.fromkeys(actor.spec['skills'],6)},reason='current ordinary sheet')
        engine.r.rulings.end_scene()
        before=deepcopy((actor.spec,actor.stats,engine.rng.getstate(),engine.log_lines))
        with self.assertRaisesRegex(ValueError,'policy conflict'):CODEC.dump_engine(engine)
        self.assertEqual((actor.spec,actor.stats,engine.rng.getstate(),engine.log_lines),before)
        configure(engine.r)
        fresh,restored=self.roundtrip(engine,actor)
        self.assertEqual(sage.acquired(restored)['snapshot']['rank'],9)
        self.assertEqual(SK.rank(fresh.r,restored,'오컬트학')[2],6)

    def test_sage_and_genjutsu_issued_rank_is_not_recomputed_from_current_skill(self):
        import sage,illusion_state,combat_timing,ninja
        sage_case=SAGE_FIX.SageTests()
        sage_case.rules=self.rules();configure(sage_case.rules);sage_case.setup()
        sage_case.acquire()
        F.base_patch(sage_case.a,{'skills':dict(sage_case.a.spec['skills'],오컬트학=7)},reason='declared cast rank')
        sage_case.begin();sage_case.e.use_sage(sage_case.a,sage_case.p)
        amount=max(14,sage_case.e.tick(sage_case.p))
        self.assertEqual(sage.reduction(sage_case.p),amount)
        F.base_patch(sage_case.a,{'skills':dict(sage_case.a.spec['skills'],오컬트학=6)},reason='later current rank')
        sage_case.restore()
        rows=[row for row in combat_timing.records(sage_case.p) if row.get('effect',{}).get('kind')=='sage_dr']
        self.assertEqual(rows[0]['effect']['rank'],7)
        self.assertEqual(sage.reduction(sage_case.p),amount)
        sage_case.close();sage_case.e.end_round();sage_case.e.start_round(sage_case.e.everyone)
        sage_case.e.at_initiative_count(60)
        self.assertEqual(sage.reduction(sage_case.p),0)
        ninja_case=NINJA_FIX.NinjaTests()
        ninja_case.rules=self.rules();configure(ninja_case.rules);ninja_case.setup()
        ninja_case.family(ninja.GENJUTSU)
        F.base_patch(ninja_case.a,{'skills':dict(ninja_case.a.spec['skills'],은신=7)},reason='declared illusion rank')
        ninja_case.combat();ninja_case.e.use_genjutsu(ninja_case.a,appearance='ordinary stone')
        F.base_patch(ninja_case.a,{'skills':dict(ninja_case.a.spec['skills'],은신=6)},reason='later current rank')
        ninja_case.restore()
        self.assertEqual(illusion_state.genjutsu_active(ninja_case.a)['stealth_rank'],7)
        self.assertEqual(SK.rank(ninja_case.e.r,ninja_case.a,'은신')[2],6)
        ninja_case.valid()

    def test_actual_trainer_and_pokemon_helpers_use_their_separate_rank_domains(self):
        engine,actor=self.fixture(6,declare=False)
        pokemon=Combatant(engine.r,build_pokemon(engine.r,'Pikachu',20,abilities=[]))
        engine.gm.add_combatant(pokemon,reason='actual Pokemon helper')
        F.base_patch(pokemon,{'skills':{'Athletics':'10d6+2'}},reason='actual species pool')
        out=engine.common_action(actor,'Athletics',10,mode='skill',helper=pokemon,fixed=[1]*6)
        self.assertEqual(out.check.total,11)
        source={'actor_id':pokemon.entity_id,'skill':'Athletics'}
        passed,total=engine.skill_check(actor,'Athletics',10,helper_rank=10,helper_bonus=5,
            helper_source=source,fixed=[1]*6)
        self.assertTrue(passed);self.assertEqual(total,11)
        options={'helper_rank':10,'helper_bonus':5,'helper_source':source,'fixed':[1]*6}
        plan=engine.plan_skill_check(actor,'Athletics',purpose='actual helper',**options)
        scoped=engine.resolve_roll_context([{'actor':actor,'target':actor,'provider':actor,
            'skill':'Athletics','purpose':'actual helper','replacement':None,
            'options':options,'expected_plan':plan}],{'kind':'dc','dc':10})
        self.assertEqual(scoped['result']['total'],11)
        self.assertEqual(scoped['plans'][0]['request_options']['helper_source'],source)
        assert_rejected_unchanged(engine,lambda:engine.skill_roll(
            actor,'Athletics',helper_rank=10,fixed=[1]*6),reason_pattern='policy conflict')
        for bad in ({'actor_id':pokemon.entity_id,'skill':'Athletics','pokemon':True},
                    {'actor_id':'missing','skill':'Athletics'},
                    {'actor_id':actor.entity_id,'skill':'Athletics'}):
            assert_rejected_unchanged(engine,lambda bad=bad:engine.skill_roll(actor,'Athletics',
                helper_rank=10,helper_bonus=5,helper_source=bad,fixed=[1]*6),reason_pattern='helper')
        F.base_patch(pokemon,{'skills':{'Athletics':'9d6+2'}},reason='helper changed before roll')
        assert_rejected_unchanged(engine,lambda:engine.skill_roll(actor,'Athletics',helper_rank=10,
            helper_bonus=5,helper_source=source,fixed=[1]*6),reason_pattern='helper rank')
        configure(engine.r)
        helper=Combatant(engine.r,build_trainer(engine.r,'actual trainer helper',30,STATS,abilities=[],
            extra={'skills':{'Athletics':7}}))
        engine.gm.add_combatant(helper,reason='declared trainer helper')
        out=engine.common_action(actor,'Athletics',9,mode='skill',helper=helper,fixed=[1]*6)
        self.assertEqual(out.check.total,9)

    def test_helper_source_survives_feature_wrapper_and_consumed_history_restore(self):
        engine,actor=self.fixture(6,declare=False)
        pokemon=Combatant(engine.r,build_pokemon(engine.r,'Pikachu',20,abilities=[]))
        engine.gm.add_combatant(pokemon,reason='actual helper')
        F.base_patch(pokemon,{'skills':{'Athletics':'10d6+2'}},reason='actual species pool')
        source={'actor_id':pokemon.entity_id,'skill':'Athletics'}
        actor.spec['feats'].append(SF.MONKEY)
        engine.start_round([actor,pokemon]);engine.start_of_turn(actor)
        options={'fixed':[1]*6,'helper_rank':10,'helper_bonus':5,'helper_source':source,
                 'roll_id':'helper-feature','feature':SF.MONKEY}
        with self.assertRaisesRegex(ValueError,'boolean'):
            engine.skill_roll(actor,'Athletics',**options,feature_options={'decision':lambda first:None})
        self.assertEqual(SF.event(engine,actor,'helper-feature').request[-1],source)
        assert_rejected_unchanged(engine,lambda:engine.skill_roll(actor,'Athletics',
            **dict(options,helper_source={'actor_id':actor.entity_id,'skill':'Athletics'}),
            feature_options={'decision':lambda first:False}),reason_pattern='observed skill declaration')
        F.base_patch(pokemon,{'skills':{'Athletics':'9d6+2'}},reason='after first observed helper roll')
        result=engine.skill_roll(actor,'Athletics',**options,feature_options={'decision':lambda first:False})
        self.assertEqual((result.rank,result.helper_rank,result.total),(6,10,11))
        fresh,restored=self.roundtrip(engine,actor)
        record=SF.event(fresh,restored,'helper-feature')
        self.assertEqual(record.request[-1],source)
        self.assertEqual(record.final.helper_rank,10)

    def test_declared_extended_rank_and_dice_count_resume_once_after_restore(self):
        engine,actor=self.fixture(10)
        options={'mode':'extended','task_id':'declared-task','interval_id':'one',
                 'interval':{'amount':1,'unit':'second'},'interval_completed':True,
                 'complexity':2,'limited':True,'fixed':[1]*7}
        first=engine.common_action(actor,'Athletics',20,**options)
        self.assertEqual((first.result.total,first.result.attempt_limit,first.result.status),(7,5,'in_progress'))
        engine,actor=self.roundtrip(engine,actor)
        final=engine.common_action(actor,'Athletics',20,**dict(options,interval_id='two',fixed=[6]*7))
        self.assertEqual((final.result.total,final.result.attempts_used,final.result.status),(49,2,'complete'))
        self.assertEqual(engine.elapsed_seconds,2)
        assert_rejected_unchanged(engine,lambda:engine.common_action(actor,'Athletics',20,
            **dict(options,interval_id='two',fixed=[6]*7)),reason_pattern='terminal')

    def test_captured_momentum_preserves_issued_and_actual_roll_rank_observations(self):
        import captured_momentum as CM,capture_techniques as CT
        for value in (7,9):
            with self.subTest(rank=value):
                case=MOMENTUM_FIX.CapturedMomentumTests()
                case.rules=self.rules(self.errata);case.core=self.base;case.setup()
                configure(case.e.r)
                F.base_patch(case.a,{'skills':dict.fromkeys(CT.SKILLS,value)},reason='declared capture ranks')
                case.grant('capture')
                self.assertEqual(CM.live(case.a)[0]['effect']['capture_plan']['book_modifier'],-value)
                F.base_patch(case.a,{'skills':dict.fromkeys(CT.SKILLS,6)},reason='later capture rank')
                ids=[x.entity_id for x in (case.a,case.p,case.q,case.pet)]
                case.e=CODEC.load_engine(self.errata,json.loads(json.dumps(CODEC.dump_engine(case.e))))
                case.a,case.p,case.q,case.pet=[W.actor_index(case.e)[uid] for uid in ids]
                self.assertEqual(CM.live(case.a)[0]['effect']['capture_plan']['book_modifier'],-value)
                case.next_turn();self.assertTrue(case.capture(case.q))
                case.e.choose_captured_momentum(case.a,attempt_id='capture-2',choice='decline')
                consumed=CM.history(case.a)[-1]
                self.assertEqual(consumed['effect']['capture_plan']['book_modifier'],-value)
                self.assertEqual(consumed['applications'][0]['capture_plan']['book_modifier'],-6)
                self.assertFalse(CM.live(case.a))
                CODEC.load_engine(self.errata,CODEC.dump_engine(case.e))

    def test_capture_withdrawal_keeps_printed_growth_but_accepts_declared_gm_result(self):
        import capture_techniques as CT
        case=CAPTURE_FIX.BookCaptureSpecialistTests();case.rules=self.rules();configure(case.rules)
        engine,actor=case.fixture(skills={'곡예':3,'교활':3,'은신':1})
        case.acquire(engine,actor,[CAPTURE_FIX.skill(),CAPTURE_FIX.choice('작업 도구')])
        F.base_patch(actor,{'skills':dict(actor.spec['skills'],은신=9)},reason='independent declared growth')
        options=case.decisions(engine,actor,CT.CLASS,granted_skill_edge_policy={
            'mode':'withdraw','reason':'explicit GM preserves independent growth',
            'skills_before':{'은신':9},'skills_after':{'은신':7}})
        engine.retrain_trainer_source(actor,CT.CLASS,**options)
        self.assertEqual(SK.rank(engine.r,actor,'은신')[2],7)
        self.assertEqual(CT.selected(actor),())
        fresh,restored=self.roundtrip(engine,actor)
        self.assertEqual(SK.rank(fresh.r,restored,'은신')[2],7)

    def test_declared_gm_knowledge_threshold_does_not_grant_or_disclose_knowledge(self):
        engine,actor=self.fixture(9)
        pokemon=Combatant(engine.r,build_pokemon(engine.r,'Pikachu',20,abilities=[]))
        engine.gm.add_combatant(pokemon,reason='actual knowledge subject')
        topic=engine.difficulty_guidance()['knowledge']['specific_topics'][0]
        options={'method':'known','reason':'explicit GM knowledge decision','high_rank_requirement':9,
                 'responses':{'success':'GM supplied fact'}}
        result=engine.pokemon_knowledge(actor,pokemon,topic,**options)
        self.assertEqual(result.description,'GM supplied fact')
        F.base_patch(actor,{'skills':dict.fromkeys(actor.spec['skills'],6)},reason='actual lower knowledge rank')
        before=engine.rng.getstate()
        result=engine.pokemon_knowledge(actor,pokemon,topic,**options)
        self.assertIsInstance(result,C.PendingDecision);self.assertIsNone(result.check)
        self.assertEqual(engine.rng.getstate(),before)
        assert_rejected_unchanged(engine,lambda:engine.pokemon_knowledge(
            actor,pokemon,topic,**dict(options,high_rank_requirement=11)),reason_pattern='policy conflict')


if __name__=='__main__':
    unittest.main()
