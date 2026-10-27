"""C10-082: full shared Baby Template on actual native Marsupial births."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools'),str(ROOT/'examples')]
from engine import Rules
from builder import STATS,nature_base
import baby_templates as BABY
import marsupial_state as M
import body_state as BODY
import capability_actions as CAP
import movement_actions as MOVE
import growth_stats as GS
import downtime as D
import skill_modifiers as SKILLS
import state_codec as CODEC
import world_entities as W
import pokemon_entities as ENT
import turn as TURN
import test_core_marsupial as FIXTURE
from native_scenario_fixture import assert_rejected_unchanged


class MarsupialBabyTemplateSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    setUp=FIXTURE.MarsupialTests.setUp
    policy=FIXTURE.MarsupialTests.policy
    egg=FIXTURE.MarsupialTests.egg
    hatch=FIXTURE.MarsupialTests.hatch
    born=FIXTURE.MarsupialTests.born
    grow=FIXTURE.MarsupialTests.grow
    snap=FIXTURE.MarsupialTests.snap
    valid=FIXTURE.MarsupialTests.valid

    def physical(self,height=.5,weight=.5,*,mass=80,weight_class=None):
        return {'height_base_m':2,'weight_base_kg':mass,'height_reduction':height,
            'weight_reduction':weight,'weight_class':weight_class,
            'reason':'explicit actual birth reference dimensions and selected reductions'}

    def reload(self,baby):
        ids=[a.entity_id for a in (self.a,self.mother,self.father,self.enemy,baby)]
        self.e=CODEC.load_engine(self.r,json.loads(self.snap()))
        index=W.actor_index(self.e)
        self.a,self.mother,self.father,self.enemy,baby=[index[uid] for uid in ids]
        self.valid();return baby

    def legacy_birth(self):
        # Exact old serialized format at level one: the actual birth/parentage,
        # five-point allocation and custody are unchanged; the old producer did
        # not write a shared Template or a physical-choice hatch receipt.
        baby=self.born();baby.spec.pop(BABY.KEY)
        egg=ENT.egg_index(self.e)[baby.spec[M.KEY]['egg_id']][1]
        egg['gm_hatch_details'].pop('baby_template')
        self.valid()
        return self.reload(baby)

    def test_actual_birth_uses_shared_skill_capability_body_and_single_floor_source(self):
        baby=self.born(physical_choice=self.physical())
        row=baby.spec[BABY.KEY];base=self.r.species[M.SPECIES]['base_stats']
        self.assertEqual((row['source'],row['selected_stat_reduction'],row['stat_penalty_remaining']),
                         (BABY.NATIVE_SOURCE,5,5))
        self.assertEqual(GS.project(self.r,baby.spec)['nature_base'],{s:max(1,base[s]-5) for s in STATS})
        self.assertEqual([r['source'] for r in GS.project(self.r,baby.spec)['base_sources']],[M.STAT_SOURCE])
        skill=max(self.mother.spec['skills'],key=lambda name:SKILLS.rank(self.r,self.mother,name)[2])
        rank=SKILLS.rank(self.r,self.mother,skill)[2]
        self.assertEqual(self.e.plan_skill_check(baby,skill,purpose='native Baby skill projection')['ordinary_rank'],max(1,rank-1))
        self.assertEqual(CAP.power(baby),max(1,CAP.power(self.mother)-2))
        adult_move=MOVE.capabilities(self.e,self.mother,environment=False)
        baby_move=MOVE.capabilities(self.e,baby,environment=False)
        for field in ('land','swim','high_jump','long_jump'):
            if field in adult_move:self.assertEqual(baby_move[field],max(0,adult_move[field]-2))
        body=BODY.projection(baby)
        self.assertEqual((body['height_m'],body['weight_kg'],baby.weight_class),(1,40,3))
        self.assertEqual(body['baby_template']['source'],BABY.NATIVE_SOURCE)
        self.assertTrue(M.in_pouch(baby));self.assertFalse(TURN.can_act(self.e,baby));self.valid()

    def test_fifth_level_physical_growth_is_explicit_and_cold_restore_keeps_receipts(self):
        baby=self.born(physical_choice=self.physical());self.grow(baby,5)
        row=baby.spec[BABY.KEY]
        self.assertEqual((row['stat_penalty_remaining'],row['level_recoveries'],row['pending_growth_levels']),(4,[5],[5]))
        self.assertEqual((BODY.projection(baby)['height_m'],BODY.weight_kg(baby)),(1,40))
        assert_rejected_unchanged(self.e,lambda:BABY.record_growth(self.e,baby,level=5,
            height_reduction=.5,weight_reduction=.5,reason='unchanged observation'),reason_pattern='increase height or weight')
        BABY.record_growth(self.e,baby,level=5,height_reduction=.25,weight_reduction=.25,
                           reason='actual observed growth at the fifth level')
        self.assertEqual((BODY.projection(baby)['height_m'],BODY.weight_kg(baby),baby.weight_class),(1.5,60,4))
        before=deepcopy(baby.spec[BABY.KEY]);baby=self.reload(baby)
        self.assertEqual(baby.spec[BABY.KEY],before)
        self.assertEqual(baby.spec[BABY.KEY]['physical_growth'][0]['level'],5);self.valid()

    def test_all_five_boundaries_restore_native_source_before_real_pouch_exit(self):
        import nature_state as N
        nature=next(name for name in self.r.mech('pokemon/natures')['by_name']
                    if N.describe(self.r,name)['up_stat']=='spa' and not N.describe(self.r,name)['neutral'])
        baby=self.born(nature=nature,physical_choice=self.physical());base=self.r.species[M.SPECIES]['base_stats']
        initial=GS.project(self.r,baby.spec);initial_points=sum(initial['investment'].values())
        skill=max(self.mother.spec['skills'],key=lambda name:SKILLS.rank(self.r,self.mother,name)[2])
        ordinary_rank=SKILLS.rank(self.r,self.mother,skill)[2];ordinary_power=CAP.power(self.mother)
        self.assertEqual(base['spa'],4)
        for level,remaining in ((5,4),(10,3),(15,2),(20,1)):
            self.grow(baby,level)
            self.assertEqual(baby.spec[BABY.KEY]['stat_penalty_remaining'],remaining)
            recovered={s:min(base[s],max(1,base[s]-5)+5-remaining) for s in STATS}
            self.assertEqual(recovered['spa'],{5:2,10:3,15:4,20:4}[level])
            self.assertEqual(GS.project(self.r,baby.spec)['nature_base'],nature_base(recovered,nature,self.r))
            self.assertTrue(M.in_pouch(baby));self.assertFalse(TURN.can_act(self.e,baby))
        self.grow(baby,25)
        row=baby.spec[BABY.KEY];after=GS.project(self.r,baby.spec)
        self.assertEqual((row['stat_penalty_remaining'],row['level_recoveries']),(0,[5,10,15,20,25]))
        self.assertEqual(after.get('base_sources',[]),[]);self.assertEqual(after['nature_base'],nature_base(base,nature,self.r))
        self.assertEqual(sum(after['investment'].values()),initial_points+24)
        self.assertEqual(SKILLS.rank(self.r,baby,skill)[2],ordinary_rank);self.assertEqual(CAP.power(baby),ordinary_power)
        self.assertFalse(M.active(baby));self.assertFalse(M.in_pouch(baby));self.assertTrue(TURN.can_act(self.e,baby))
        self.assertFalse(BODY.projection(baby)['baby_template']['active'])
        # Exit does not invent a new body size or backfill four missed observations.
        self.assertEqual((BODY.projection(baby)['height_m'],BODY.weight_kg(baby)),(1,40))
        self.assertEqual(row['physical_growth'],[]);self.assertEqual(row['pending_growth_levels'],[5,10,15,20,25])
        BABY.record_growth(self.e,baby,level=25,height_reduction=0,weight_reduction=0,
                           reason='actual observed mature dimensions at native Template exit')
        self.assertEqual((BODY.projection(baby)['height_m'],BODY.weight_kg(baby),baby.weight_class),(2,80,4))
        self.assertTrue(BABY.projection(self.r,baby.spec)['fully_recovered'])
        self.grow(baby,30)
        self.assertEqual(baby.spec[BABY.KEY]['level_recoveries'],[5,10,15,20,25]);self.valid()

    def test_birth_requires_explicit_physical_choice_and_shared_mass_boundary(self):
        egg=self.egg()
        choices={'gender':'female','nature':'노력','abilities':['배짱'],'moves':[],
                 'special_appearance':False,'inheritance_moves':[]}
        assert_rejected_unchanged(self.e,lambda:self.e.hatch_declared_egg(self.a,egg['entity_id'],
            name='missing actual physical choice',ready=True,reason='observed hatch readiness',choices=choices),
            reason_pattern='explicit native Baby Template physical choice')
        assert_rejected_unchanged(self.e,lambda:self.hatch(egg,physical_choice=self.physical(mass=100)),
            reason_pattern='shared Weight Class boundary')
        baby=self.hatch(egg,physical_choice=self.physical(mass=100,weight_class=3))
        self.assertEqual((baby.spec['weight_kg'],baby.weight_class),(50,3));self.valid()

    def test_explicit_zero_physical_reductions_and_duplicate_optional_template_are_distinct(self):
        baby=self.born(physical_choice=self.physical(0,0))
        self.assertEqual((BODY.projection(baby)['height_m'],BODY.weight_kg(baby)),(2,80))
        self.assertEqual(baby.spec[BABY.KEY]['selected_stat_reduction'],5)
        assert_rejected_unchanged(self.e,lambda:BABY.apply(self.e,baby,stat_reduction=2,
            reason='duplicate named Template'),reason_pattern='already applied')
        BABY.apply(self.e,self.mother,stat_reduction=2,permanent_stat_reduction=2,
                   reason='independent explicit optional permanent Template')
        self.assertEqual((self.mother.spec[BABY.KEY]['source'],self.mother.spec[BABY.KEY]['permanent_stat_reduction']),
                         (BABY.SOURCE,2));self.assertEqual(baby.spec[BABY.KEY]['permanent_stat_reduction'],0)
        self.valid()

    def test_legacy_import_requires_explicit_upgrade_and_never_backfills_history(self):
        baby=self.legacy_birth();old_birth=deepcopy(baby.spec[M.KEY])
        old_history=deepcopy(baby.spec['stat_history']);old_initial=deepcopy(baby.spec['initial_allocation'])
        self.assertTrue(M.projection(baby,engine=self.e)['template_upgrade_required'])
        assert_rejected_unchanged(self.e,lambda:D.gain_exp_combatant(self.e,baby,'to next level'),reason_pattern='explicit upgrade')
        assert_rejected_unchanged(self.e,lambda:BABY.upgrade_native(self.e,baby,physical_choice=None,
            reason='upgrade without observation'),reason_pattern='explicit native Baby Template physical choice')
        BABY.upgrade_native(self.e,baby,physical_choice=self.physical(.25,.25),reason='explicit legacy source repair with current measured body')
        row=baby.spec[BABY.KEY]
        self.assertEqual(row['native_origin']['kind'],'legacy_upgrade')
        self.assertEqual((row['level_recoveries'],row['physical_growth'],row['pending_growth_levels']),([],[],[]))
        self.assertEqual(baby.spec[M.KEY],old_birth);self.assertEqual(baby.spec['initial_allocation'],old_initial)
        self.assertEqual(baby.spec['stat_history'][:len(old_history)],old_history)
        self.assertEqual(baby.spec['allocation_migrations'][-1]['kind'],'native_baby_template_upgrade')
        baby=self.reload(baby);self.assertFalse(M.projection(baby,engine=self.e)['template_upgrade_required'])
        self.grow(baby,5);self.assertEqual(baby.spec[BABY.KEY]['level_recoveries'],[5]);self.valid()

    def test_native_source_permanence_and_actual_birth_physical_receipt_tamper_reject(self):
        baby=self.born(physical_choice=self.physical());original=deepcopy(baby.spec[BABY.KEY])
        for change in ({'source':BABY.SOURCE},{'selected_stat_reduction':4},
                       {'permanent_stat_reduction':1},{'applied_species':'pokemon/메타몽'}):
            with self.subTest(change=change):
                baby.spec[BABY.KEY].update(change)
                with self.assertRaises(ValueError):M.validate_world(self.e)
                baby.spec[BABY.KEY]=deepcopy(original)
        baby.spec[BABY.KEY]['native_origin']['physical_choice']['reason']='changed producing choice'
        baby.spec[BABY.KEY]['selection_reason']='changed producing choice'
        with self.assertRaisesRegex(ValueError,'actual birth receipt'):M.validate_world(self.e)
        baby.spec[BABY.KEY]=deepcopy(original);self.valid()

    def test_declared_seventh_skill_rank_survives_native_penalty_recovery_and_human_consumer(self):
        from declared_skill_ranks import configure
        with patch.object(self.r,'rulings',deepcopy(self.r.rulings)):
            configure(self.r)
            baby=self.born()
            self.e.gm.set_skill(self.a,'명령',7,reason='actual sheet under declared future seventh rank')
            self.e.gm.set_skill(baby,'육상',7,reason='actual imported native baby skill under same declared rank')
            human=self.e.plan_skill_check(self.a,'명령',purpose='future declared human rank')
            reduced=self.e.plan_skill_check(baby,'육상',purpose='native Template subtracts one declared rank')
            self.assertEqual((human['ordinary_rank'],human['dice_count']),(7,7))
            self.assertEqual((reduced['ordinary_rank'],reduced['dice_count']),(6,6))
            self.grow(baby,25)
            restored=self.e.plan_skill_check(baby,'육상',purpose='full native Template recovery')
            self.assertEqual((restored['ordinary_rank'],restored['dice_count']),(7,7))
            roll=self.e.skill_roll(baby,'육상',fixed=[2]*7)
            self.assertEqual((roll.rank,len(roll.faces),roll.total),(7,7,14))
            self.assertEqual(self.e.plan_skill_check(self.a,'명령',purpose='human declaration remains seventh')['ordinary_rank'],7)
            self.assertEqual(baby.spec['skills'][SKILLS.skill_id(self.r.skill_policy,'육상')],7);self.valid()


if __name__=='__main__':unittest.main()
