"""Native regressions for the five growth/permanent source-audit duties."""
from copy import deepcopy
from pathlib import Path
import json, sys, unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_skill_edge_state as SKILL_FIX
import test_category2_ranged_struggle as RANGED_FIX
import test_foundation_egg_creation as EGG_FIX
import test_book_researcher_fields_crafting as RESEARCH_FIX
import baby_templates as BABY, csv_item_form_contracts as FORMS
import creation_egg as EGGS, growth_milestones as MILESTONES, downtime as D
import move_state as MOVES, pokemon_skill_edges as SKILLS, researcher_features as RF
import researcher_fields as RESEARCH, ranged_struggle as RANGED
from builder import build_pokemon
from native_scenario_fixture import assert_rejected_unchanged
from state_codec import dump_engine, load_engine


class PermanentSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):SKILL_FIX.SkillEdgeStateTests.setUpClass()
    def setUp(self):
        self.f=SKILL_FIX.SkillEdgeStateTests();self.f.setUp()
    def test_baby_projection_is_not_the_permanent_pool_or_receipt(self):
        f=self.f;c=f.pokemon('리오르',5)
        before=f.rank(c,'육상')
        BABY.apply(f.e,c,stat_reduction=2,reason='actual optional Baby Template')
        f.e.pokemon_activity(f.a,'teach_edge',target=c,edge='C2CSV/input/db/poke-edges.csv:R4:main',safe=True)
        self.assertEqual(f.rank(c,'육상'),(before[0]+1,before[1]))
        self.assertEqual(RF.native_plan(f.e,c,'육상')['rank'],before[0])
        receipt=SKILLS.active(c.spec)[0]
        self.assertEqual(receipt['rank_before'],before[0]);self.assertEqual(c.spec['tutor_points'],5)
        self.assertEqual(receipt['definition_origin']['clause_id'],'C2CSV/input/db/poke-edges.csv:R4:main')
    def test_baby_cannot_hide_a_permanent_pool_above_species_default(self):
        f=self.f;c=f.pokemon('리오르',5);base=f.rank(c,'육상')[0]
        f.e.gm.set_skill(c,'육상',str(base+1)+'d6+2',reason='actual permanent reward')
        BABY.apply(f.e,c,stat_reduction=2,reason='actual optional Baby Template')
        assert_rejected_unchanged(f.e,lambda:f.teach(c,'육상'),reason_pattern='species default')
    def test_fusion_partner_pool_cannot_be_written_to_the_individual(self):
        f=self.f;c=f.pokemon('네크로즈마',35);partner=f.pokemon('루나아라',35)
        f.e.gm.set_skill(partner,'육상','1d6+5',reason='actual partner permanent pool')
        before=f.rank(c,'육상')
        FORMS.merge_necrozma(f.e,c,partner,willing=True)
        self.assertEqual(RF.native_plan(f.e,c,'육상')['modifier'],5)
        f.teach(c,'육상')
        expected=(before[0]+1,before[1]) if before[0]<6 else before
        self.assertEqual(f.rank(c,'육상'),expected)
        FORMS.release_necrozma(f.e,c)
        self.assertEqual(f.rank(c,'육상'),expected)


class RangedWhitelistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):RANGED_FIX.RangedTests.setUpClass()
    def setUp(self):
        self.f=RANGED_FIX.RangedTests();self.f.setUp()
    def test_poison_glands_remains_melee_and_cannot_buy_native_or_csv_range(self):
        f=self.f;scene=f.f
        for edge in (RANGED.SOURCE,'C2CSV/input/db/poke-edges.csv:R43:main'):
            assert_rejected_unchanged(scene.e,lambda edge=edge:f.teach(edge,'독샘'),reason_pattern='six printed capabilities')
        import weapon_actions as W
        self.assertEqual(W.range_spec(scene.e,f.prepared('독샘'))['origin'],'melee')
    def test_changed_saved_receipt_cannot_enable_unlisted_capability(self):
        f=self.f;f.teach();scene=f.f
        row=RANGED.records(scene.p)[0];row['choice']='독샘'
        with self.assertRaisesRegex(ValueError,'ranged Struggle capability'):RANGED.validate(scene.p)
        self.assertFalse(scene.e.validate_state()['valid'])


class InheritanceGrowthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):EGG_FIX.EggTests.setUpClass()
    def setUp(self):
        self.f=EGG_FIX.EggTests();self.f.setUp()
    def child(self,level=19):
        f=self.f;policy=f.policy();policy['hatch']['level']=level
        row=f.create(policy)
        return f.hatch(row)['pokemon']
    def test_both_declared_birth_modes_keep_inheritance_unlearned(self):
        f=self.f
        for index,mode in enumerate(('natural_and_inherited','observed')):
            policy=f.policy();policy['hatch']['known_moves']=mode
            row=f.create(policy,request_id='birth-'+str(index));choices=f.choices();choices['moves']=['move/뿌리박기']
            assert_rejected_unchanged(f.e,lambda:f.hatch(row,choices=choices),reason_pattern='outside natural|inheritance list')
            child=f.hatch(row)['pokemon']
            self.assertEqual(child.spec['inheritance_moves'],['move/뿌리박기'])
            self.assertNotIn('move/뿌리박기',child.moves)
            self.assertNotIn('move/뿌리박기',child.spec.get('move_learning',{}))
    def test_twenty_offers_one_choice_and_restore_replay_does_not_learn_twice(self):
        f=self.f;c=self.child();reason='choose actual inherited growth Move'
        assert_rejected_unchanged(f.e,lambda:f.e.choose_growth_inheritance(c,20,'move/뿌리박기',reason=reason),reason_pattern='attained')
        D.gain_exp_combatant(f.e,c,'to next level')
        self.assertIsNone(c.spec[MILESTONES.KEY]['inheritance:20']['selection'])
        self.assertNotIn('move/뿌리박기',c.moves)
        before=c.spec['tutor_points'];out=f.e.choose_growth_inheritance(c,20,'move/뿌리박기',reason=reason)
        self.assertFalse(out['replayed']);self.assertEqual(c.spec['tutor_points'],before)
        self.assertEqual(MOVES.classifications(f.r,c.spec)['move/뿌리박기'],'natural')
        receipt=c.spec['move_learning']['move/뿌리박기']
        self.assertEqual((receipt['method'],receipt['learned_at_level'],receipt['paid_tp']),('level_up',20,0))
        loaded=load_engine(f.r,json.loads(json.dumps(dump_engine(f.e),ensure_ascii=False)))
        actor=next(x for x in loaded.gm.everyone if x.entity_id==c.entity_id);before=dump_engine(loaded)
        self.assertTrue(loaded.choose_growth_inheritance(actor,20,'move/뿌리박기',reason=reason)['replayed'])
        self.assertEqual(before,dump_engine(loaded))
        assert_rejected_unchanged(loaded,lambda:loaded.choose_growth_inheritance(actor,20,'move/망각술',reason=reason),reason_pattern='already recorded')
    def test_thirty_is_an_independent_right_and_nineteen_twenty_nine_are_not(self):
        f=self.f;c=self.child(29)
        self.assertNotIn('inheritance:20',c.spec.get(MILESTONES.KEY,{}))
        assert_rejected_unchanged(f.e,lambda:f.e.choose_growth_inheritance(c,29,'move/뿌리박기',reason='invalid milestone'),reason_pattern='recorded inheritance')
        D.gain_exp_combatant(f.e,c,'to next level')
        f.e.choose_growth_inheritance(c,30,'move/뿌리박기',reason='actual level30 choice')
        self.assertIn('move/뿌리박기',c.moves)
        self.assertEqual(c.spec['move_learning']['move/뿌리박기']['inheritance_milestone'],'inheritance:30')
    def test_pending_right_survives_evolution_and_forgetting_does_not_reopen_it(self):
        f=self.f;c=self.child(20);offered=deepcopy(c.spec[MILESTONES.KEY]['inheritance:20']['offered'])
        self.assertTrue(D.evolve_combatant(f.e,c,'이상해풀')['evolved'])
        self.assertEqual(c.spec[MILESTONES.KEY]['inheritance:20']['offered'],offered)
        reason='choose inherited Move after evolution'
        f.e.choose_growth_inheritance(c,20,'move/뿌리박기',reason=reason)
        history=deepcopy(c.spec['move_learning_log'])
        f.e.gm.set_move(c,'move/뿌리박기',False,reason='explicitly forget an already learned Move')
        self.assertTrue(f.e.choose_growth_inheritance(c,20,'move/뿌리박기',reason=reason)['replayed'])
        self.assertNotIn('move/뿌리박기',c.moves);self.assertEqual(c.spec['move_learning_log'],history)
    def test_old_imported_learning_is_not_retroactively_removed_or_relabelled(self):
        f=self.f;c=self.child()
        f.e.gm.set_move(c,'move/뿌리박기',True,reason='observe a Move learned before this repair')
        saved=deepcopy(c.spec.get('move_learning',{}));history=deepcopy(c.spec.get('move_learning_log',[]))
        D.gain_exp_combatant(f.e,c,'to next level')
        self.assertIn('move/뿌리박기',c.moves)
        self.assertEqual(c.spec.get('move_learning',{}).get('move/뿌리박기'),saved.get('move/뿌리박기'))
        self.assertEqual(c.spec.get('move_learning_log',[])[:len(history)],history)
        assert_rejected_unchanged(f.e,lambda:f.e.choose_growth_inheritance(c,20,'move/뿌리박기',reason='cannot relearn known'),reason_pattern='currently available')
    def test_capacity_failure_keeps_the_pending_right_and_source_exclusion_is_atomic(self):
        f=self.f;c=self.child(20)
        for mid in ('move/몸통박치기','move/울음소리','move/덩굴채찍','move/성장','move/잎날가르기','move/달콤한향기'):
            f.e.gm.set_move(c,mid,True,reason='observed existing known Move')
        assert_rejected_unchanged(f.e,lambda:f.e.choose_growth_inheritance(c,20,'move/뿌리박기',reason='full pool'),reason_pattern='capacity|slot|six|6|limit')
        self.assertIsNone(c.spec[MILESTONES.KEY]['inheritance:20']['selection'])
        f.e.gm.set_move(c,'move/몸통박치기',False,reason='explicitly forget one Move')
        previous=deepcopy(f.r.selection.excluded)
        try:
            f.r.selection.excluded[MILESTONES.INHERITANCE_SOURCE]='exclude_units'
            assert_rejected_unchanged(f.e,lambda:f.e.choose_growth_inheritance(c,20,'move/뿌리박기',reason='excluded source'),reason_pattern='inheritance source|excluded|제외')
        finally:f.r.selection.excluded.clear();f.r.selection.excluded.update(previous)
        f.e.choose_growth_inheritance(c,20,'move/뿌리박기',reason='choose after making room')
    def test_species_distribution_rejects_impossible_gender_before_birth(self):
        f=self.f
        for index,(species,mother,gender,invalid) in enumerate((('켄타로스','밀탱크','male','female'),('럭키','럭키','female','male'))):
            f.parents=[f.add(build_pokemon(f.r,mother,5,moves=[],abilities=[],extra={'trainer_id':f.a.entity_id,'gender':'female'})),
                       f.add(build_pokemon(f.r,'켄타로스',5,moves=[],abilities=[],extra={'trainer_id':f.a.entity_id,'gender':'male'}))]
            row=f.create(species=species,inheritance_moves=[],request_id='sex-'+str(index))
            ability=MILESTONES.ability_options(f.r,{'species':row['species'],'abilities':[]},'creation')[0]
            choices=dict(gender=invalid,nature='노력',abilities=[ability],moves=[],special_appearance=False,inheritance_moves=[])
            for wrong in (invalid,'xyz','genderless'):
                choices['gender']=wrong
                assert_rejected_unchanged(f.e,lambda:f.hatch(row,choices=choices),reason_pattern='birth gender')
            choices['gender']=gender;child=f.hatch(row,choices=choices)['pokemon']
            self.assertEqual(child.spec['gender'],gender)


class ArtificialInheritanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):RESEARCH_FIX.ResearcherFieldsCraftingTests.setUpClass()
    def setUp(self):
        self.f=RESEARCH_FIX.ResearcherFieldsCraftingTests();self.f.setUp()
        self.addCleanup(self.f.doCleanups)
    def test_tutor_list_upgrade_waits_until_growth_and_then_counts_as_natural(self):
        f=self.f;f.t.spec['items']['화학 세트']=1
        upgrades=[{'kind':'inheritance_move','move':'move/저주'}]+[{'kind':'base_stat','stat':stat} for stat in ('hp','atk','def','spa','spd')]
        args=dict(species='코일',nature='노력',ability='옹골참',upgrades=upgrades,seconds=60,reason='actual artificial egg',request_id='growth-egg')
        for gender in ('male','female','xyz'):
            assert_rejected_unchanged(f.e,lambda gender=gender:RESEARCH.playing_god(f.e,f.t,gender=gender,**args),reason_pattern='birth gender')
        row=RESEARCH.playing_god(f.e,f.t,gender='무성',**args);f.e.advance_time(86400,[f.t])
        c=RESEARCH.hatch_artificial(f.e,f.t,row['egg_entity_id'],name='native artificial child',reason='observed ready')['pokemon']
        self.assertNotIn('move/저주',c.moves);self.assertEqual(c.spec['inheritance_moves'],['move/저주'])
        self.assertEqual(c.spec['gender'],'무성')
        f.e.gm.set_level(c,19,reason='observed current level before native twentieth growth')
        D.gain_exp_combatant(f.e,c,'to next level')
        f.e.choose_growth_inheritance(c,20,'move/저주',reason='actual inherited Tutor-list choice')
        self.assertEqual(MOVES.classifications(f.rules,c.spec)['move/저주'],'natural')
        self.assertEqual(c.spec['move_learning']['move/저주']['method'],'level_up')
        self.assertTrue(f.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
