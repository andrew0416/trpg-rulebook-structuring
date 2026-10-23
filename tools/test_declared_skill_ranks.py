"""Selected GM declarations extend ordinary ranks through existing native paths."""
from copy import copy, deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools'),str(ROOT/'examples')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from rulings import Rulings
from state_codec import dump_engine,load_engine,StateCodecError
import skill_modifiers as S
import common_checks as C
import state_fields as F
import trainer_capabilities as CAP
import skill_stunts as ST
import skill_feature_actions as SF
from native_scenario_fixture import assert_rejected_unchanged
from declared_skill_ranks import configure

TABLE='gameplay/skill-rank-dice'

class DeclaredSkillRankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.r=copy(self.base)
        self.r.rulings=Rulings()
        self.e=Engine(self.r,73)
        self.a=Combatant(self.r,build_trainer(self.r,'extended-rank',20,
            dict.fromkeys(F.STATS,10),abilities=[]))
        self.e.gm.add_combatant(self.a)

    def sheet(self,rank,**skills):
        F.base_patch(self.a,{'skills':{'Athletics':rank,**skills}},reason='Observed campaign skill sheet')

    def rejected_roll(self,pattern):
        # Invalid sheets/declarations cannot be exported; inspect live state directly.
        def state():
            return (deepcopy(vars(self.a),{id(self.r):self.r}),self.e.rng.getstate(),
                    deepcopy(self.e._ap_rolls,{id(self.a):self.a,id(self.r):self.r}),list(self.e.log_lines),deepcopy(vars(self.r.rulings)))
        before=state()
        with self.assertRaisesRegex(ValueError,pattern):
            self.e.skill_roll(self.a,'Athletics',roll_id='invalid-rank')
        self.assertEqual(state(),before)

    def test_default_ptu_sheet_accepts_one_to_six_and_rejects_undeclared_seven(self):
        for rank in range(1,7):
            self.sheet(rank)
            result=self.e.skill_roll(self.a,'Athletics',fixed=[2]*rank)
            self.assertEqual((result.rank,len(result.faces),result.total),(rank,rank,2*rank))
        assert_rejected_unchanged(self.e,lambda:self.sheet(7),reason_pattern='unresolved ordinary numeric')
        self.e.start_round([self.a]);self.e.start_of_turn(self.a)
        self.e.boost_roll(self.a,self.a,roll_id='invalid-rank',kind='skill')
        self.assertEqual(self.e._ap_rolls['invalid-rank']['state'],'prepared')
        for bad in (7,9,10,True,False,0,-1,3.0,'거장'):
            with self.subTest(bad=bad):
                self.a.spec['skills']={'Athletics':bad}
                self.rejected_roll('unresolved')

    def test_public_declarations_named_numeric_english_and_multi_digit_dice(self):
        configure(self.r)
        self.r.rulings.set_mech(TABLE,'by_rank_name.천상',{'rank':12,'dice':'12d6','eng':'Celestial'},
            reason='Additional declared multi-digit pool',rules=self.r)
        for rank,name,english,count in [(7,'초월','Epic',7),(9,'전설','Legendary',9),
                                        (10,'신화','Mythic',7),(12,'천상','Celestial',12)]:
            for stored in (rank,name,english,english.lower()):
                with self.subTest(stored=stored):
                    self.sheet(stored)
                    self.assertEqual(S.rank(self.r,self.a,'육상'),(name,str(count)+'d6',rank))
                    self.assertEqual(S.effective_rank(self.r,self.a,'Athletics'),rank)
                    result=self.e.skill_roll(self.a,'Athletics',fixed=[2]*count)
                    self.assertIsInstance(result,C.AdjustedSkillRoll)
                    self.assertEqual((result.rank,result.dice_count,result.total),(rank,count,2*count))
        self.assertEqual(set(self.base.mech(TABLE)['by_rank_name']),{'불능','미숙','초보','숙련','전문','달인'})
        self.assertFalse(self.base.rulings.mech)

    def test_rank_plan_actual_dice_capability_and_json_restore_stay_separate(self):
        configure(self.r)
        for rank,count in ((7,7),(10,7)):
            self.sheet(rank,Acrobatics=rank)
            before=dump_engine(self.e)
            plan=self.e.plan_skill_check(self.a,'Athletics',purpose='campaign climb',fixed=[2]*count)
            formula=self.e.plan_rank_context(self.a,'Athletics',purpose='campaign capacity',
                targets=[self.a],source='combat/struggle')
            self.assertEqual((plan['ordinary_rank'],plan['effective_rank'],plan['dice_count']),(rank,rank,count))
            self.assertEqual((formula['ordinary_rank'],formula['effective_rank'],formula['dice_count']),(rank,rank,None))
            self.assertEqual(CAP.values(self.a)['land'],rank+3)
            self.assertEqual(dump_engine(self.e),before)
            result=self.e.skill_roll(self.a,'Athletics',fixed=[2]*count,roll_id='rank-'+str(rank))
            saved=json.loads(json.dumps(dump_engine(self.e),ensure_ascii=False))
            fresh=load_engine(self.base,saved)
            actor=fresh.everyone[0]
            self.assertEqual(S.rank(fresh.r,actor,'Athletics')[2],rank)
            self.assertEqual(SF.event(fresh,actor,'rank-'+str(rank)).first,result)
            self.assertEqual(fresh.skill_roll(actor,'Athletics',fixed=[3]*count).total,3*count)
            restored=fresh.plan_rank_context(actor,'Athletics',purpose='restored capacity',targets=[actor],source='combat/struggle')
            self.assertEqual(restored['effective_rank'],rank)
        self.assertFalse(self.base.rulings.mech)

    def test_virtuoso_keeps_effect_eight_and_six_dice_under_extended_table(self):
        configure(self.r);self.sheet(6,Acrobatics=6)
        self.a.spec['edges']=['edge/거장'];self.a.spec['edge_choices']={'edge/거장':['육상']}
        plan=self.e.plan_skill_check(self.a,'Athletics',purpose='master check')
        self.assertEqual((plan['ordinary_rank'],plan['effective_rank'],plan['dice_count']),(6,8,6))
        self.assertEqual(self.e.skill_roll(self.a,'Athletics',fixed=[1]*6).total,6)
        fresh=load_engine(self.base,dump_engine(self.e))
        self.assertEqual(S.effective_rank(fresh.r,fresh.everyone[0],'Athletics'),8)

    def test_stunt_and_skill_monkey_use_declared_pool_without_changing_rank(self):
        configure(self.r);self.sheet(10,Acrobatics=4,Perception=4)
        self.a.spec['edges']=[ST.SOURCE];self.a.spec['feats']=[SF.MONKEY]
        self.e.approve_skill_stunt(self.a,choice_id='climb',skill='Athletics',use='wet cliff climbing',
            reason='Narrow campaign skill use',approved=True)
        stunt={'choice_id':'climb','apply':True,'matches_approved_use':True,'reason':'Actual wet cliff'}
        plan=self.e.plan_skill_check(self.a,'Athletics',purpose='wet cliff climbing',skill_stunt=stunt,fixed=[1]*6)
        self.assertEqual((plan['ordinary_rank'],plan['effective_rank'],plan['dice_count'],plan['modifier']),(10,10,6,6))
        self.e.start_round([self.a]);self.e.start_of_turn(self.a)
        out=self.e.skill_roll(self.a,'Athletics',skill_stunt=stunt,fixed=[1]*6,roll_id='stunt',
            feature=SF.MONKEY,feature_options={'decision':lambda first:True,'reroll_faces':[2]*6})
        self.assertEqual((out.rank,out.dice_count,out.total),(10,6,20))
        first=SF.event(self.e,self.a,'stunt').first
        self.assertEqual((first.rank,first.dice_count,first.total),(10,6,12))
        fresh=load_engine(self.base,dump_engine(self.e))
        self.assertEqual(SF.event(fresh,fresh.everyone[0],'stunt').final,out)

    def test_conflicting_skill_aliases_and_wrong_dice_count_reject_before_observation(self):
        configure(self.r);self.sheet(10)
        assert_rejected_unchanged(self.e,
            lambda:self.e.skill_roll(self.a,'Athletics',fixed=[1]*10,roll_id='bad-count'),
            reason_pattern='dice count mismatch')
        self.a.spec['skills']['육상']=7
        self.rejected_roll('conflicting skill aliases')

    def test_malformed_definitions_reject_at_consumer_without_rng_ap_or_state_change(self):
        original=deepcopy(self.r.mech(TABLE)['by_rank_name'])
        bad_rows=[{'rank':value,'dice':'7d6'} for value in (True,0,-1,7.0,None)]
        bad_rows += [{'rank':7,'dice':value} for value in ('0d6','-1d6','7d8','7d6+2','7d6junk',7,None)]
        bad_rows += [{'rank':7},None,{'rank':6,'dice':'7d6'},
                     {'rank':7,'dice':'7d6','eng':'Master'}, {'rank':7,'dice':'7d6','eng':''}]
        for row in bad_rows:
            with self.subTest(row=row):
                table=deepcopy(original);table['extension']=row
                self.r.rulings.set_mech(TABLE,'by_rank_name',table,reason='Invalid declaration boundary',rules=self.r)
                self.rejected_roll('declared|conflicting')
        for table in ({},[],None):
            self.r.rulings.set_mech(TABLE,'by_rank_name',table,reason='Invalid table boundary',rules=self.r)
            self.rejected_roll('nonempty declared')

    def test_revoked_scene_definition_is_not_cached_and_unrelated_core_rank_still_works(self):
        configure(self.r,scope='scene');self.sheet(7)
        self.assertEqual(self.e.skill_roll(self.a,'Athletics',fixed=[1]*7).rank,7)
        self.r.rulings.end_scene()
        self.rejected_roll('unresolved ordinary numeric')
        self.sheet(6)
        self.assertEqual(self.e.skill_roll(self.a,'Athletics',fixed=[1]*6).rank,6)
        assert_rejected_unchanged(self.e,lambda:self.sheet(7),reason_pattern='unresolved ordinary numeric')

    def test_pokemon_species_pool_above_six_and_constant_remain_valid_without_declaration(self):
        pokemon=Combatant(self.r,build_pokemon(self.r,'Pikachu',20,abilities=[]))
        self.e.gm.add_combatant(pokemon)
        F.base_patch(pokemon,{'skills':{'Athletics':'10d6+2'}},reason='Observed species pool')
        self.assertEqual(S.rank(self.r,pokemon,'Athletics'),('포켓몬 스킬','10d6',10))
        out=self.e.skill_roll(pokemon,'Athletics',fixed=[1]*10)
        self.assertEqual((out.rank,out.dice_count,out.modifier,out.total),(10,10,2,12))

    def test_adjusted_primitive_does_not_authorize_an_undeclared_engine_rank(self):
        out=C.AdjustedSkillRoll(7,(1,)*7,dice_count=7)
        self.assertEqual(out.total,7)
        self.a.spec['skills']={'Athletics':7}
        self.rejected_roll('unresolved ordinary numeric')
        for bad in (True,0,-1):
            with self.assertRaises(ValueError):C.AdjustedSkillRoll(bad,(1,),dice_count=1)
        with self.assertRaises(ValueError):C.SkillRoll(7,(1,)*7)

    def test_invalid_saved_definition_rejects_without_mutating_supplied_rules(self):
        configure(self.r);self.sheet(10)
        saved=dump_engine(self.e)
        changed=0
        for node in saved['nodes'].values():
            if node['kind']=='dict' and ['rank',10] in node['items'] and ['dice','7d6'] in node['items']:
                node['items'][node['items'].index(['rank',10])]=['rank',0]
                changed+=1
        self.assertGreater(changed,0)
        before=deepcopy(vars(self.base.rulings))
        with self.assertRaisesRegex(StateCodecError,'invalid declared skill rank'):
            load_engine(self.base,saved)
        self.assertEqual(vars(self.base.rulings),before)
        self.assertEqual(set(self.base.mech(TABLE)['by_rank_name']),{'불능','미숙','초보','숙련','전문','달인'})

if __name__=='__main__':unittest.main()
