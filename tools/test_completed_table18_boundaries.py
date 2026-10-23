"""Source-specific consumers absent from the historical clause-to-case mapping."""
import unittest
from engine import Rules,Engine,Combatant
import survivalist_features as SURVIVALIST
import test_category2_class_passive_combat_bulk as PASSIVE
import items as ITEMS


class Table18Boundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=Rules('D:/trpg-rulebook-structuring/ptk-structure-experiment',ruleset='all')
        PASSIVE.ClassPassiveCombatBulkTests.setUpClass()

    def mountain(self):
        e=Engine(self.r,seed=1711)
        a=Combatant(self.r,{'id':'trainer/mountain18','name':'Mountain','kind':'trainer','size':'중형','level':20,
            'stats':{'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},
            'skills':{'생존':6,'육상':4,'곡예':4,'은신':3,'통찰':3},
            'classes':[SURVIVALIST.SURVIVALIST],'feats':['feat/내추럴-파이터'],
            'edges':[],'movement':{'land':6},'weight_kg':70,'weight_class':4})
        e.everyone=[a]
        for terrain in ('grassland','mountain'):
            for n in range(3):
                SURVIVALIST.observe_environment(e,a,terrains=[terrain],light='normal',reason='actual assigned talent terrain')
                SURVIVALIST.begin_night(e,a,night_id=terrain+str(n),terrain_name=terrain,reason='actual night')
                e.advance_time(60,[a])
                SURVIVALIST.finish_night(e,a,night_id=terrain+str(n),reason='completed actual night')
            SURVIVALIST.select_terrain(e,a,terrain_name=terrain,minutes=1,reason='Extended selection')
        a.spec['feats'].append(SURVIVALIST.TALENT)
        a.spec['feat_ranks']={SURVIVALIST.TALENT:1}
        SURVIVALIST.choose_talents(e,a,terrains=['grassland','mountain'])
        SURVIVALIST.observe_environment(e,a,terrains=['urban'],light='normal',reason='talents apply in every terrain')
        return e,a

    def test_mountain_native_climb_balance_footing_push_and_trip_resistance(self):
        e,a=self.mountain()
        for purpose,skill in [('climb','육상'),('balance','곡예'),('maintain_footing','곡예'),
                              ('resist_push','육상'),('resist_trip','곡예')]:
            with self.subTest(purpose=purpose):
                self.assertEqual(e.skill_roll(a,skill,fixed=[1]*4,
                    skill_context={'purpose':purpose,'reason':'actual assigned mountain skill check'}).total,6)
        for purpose in ('push','trip'):
            self.assertEqual(e.skill_roll(a,'육상',fixed=[1]*4,
                skill_context={'purpose':purpose,'reason':'offensive maneuver is outside the printed resistance'}).total,4)
        a.spec['feats'].remove(SURVIVALIST.TALENT)
        a.spec.pop('_survivalist_talents');a.spec['feat_ranks'].pop(SURVIVALIST.TALENT)
        self.assertEqual(e.skill_roll(a,'육상',fixed=[1]*4,
            skill_context={'purpose':'climb','reason':'talent withdrawn'}).total,4)

    def test_equipment_talents_reach_native_damage_with_crit_and_nonstack(self):
        f=PASSIVE.ClassPassiveCombatBulkTests()
        e,t,p,q=f.fixture(techniques=[PASSIVE.C.HAT_TRICK,PASSIVE.C.REINFORCED_CLOTHING])
        physical=self.r.move('move/기가임팩트');special=self.r.move('move/파괴광선')
        crit=e.roll_damage(q,t,physical,crit=True,set_damage=True)
        regular=e.roll_damage(q,t,physical,crit=False,set_damage=True)
        ITEMS.register_item(e,t,'item/선글라스')
        self.assertEqual(e.roll_damage(q,t,physical,crit=True,set_damage=True),max(1,crit-15))
        self.assertEqual(e.roll_damage(q,t,physical,crit=False,set_damage=True),regular)
        before_special=e.roll_damage(q,t,special,set_damage=True)
        ITEMS.register_item(e,t,'item/경갑')
        self.assertEqual(e.roll_damage(q,t,special,set_damage=True),max(1,before_special-5))
        # Light armor's actual physical DR remains 5; Reinforced Clothing must not stack another 5.
        self.assertEqual(e.roll_damage(q,t,physical,set_damage=True),max(1,regular-5))


if __name__=='__main__':unittest.main(verbosity=2)
