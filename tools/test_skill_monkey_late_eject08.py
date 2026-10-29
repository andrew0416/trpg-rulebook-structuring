"""Unexecuted native diagnostic for late Skill Monkey option validation."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import action_points as AP
import csv_item_physical_contracts as PHYSICAL
import skill_feature_actions as SKILL
import test_category3_skill_feature_actions as MONKEY_FIX
import test_category2_csv_remaining_item_contracts as ITEMS_FIX


class SkillMonkeyLateEjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT)

    def fixture(self):
        case=MONKEY_FIX.Tests();case.r=self.rules;case.fixture()
        items=ITEMS_FIX.RemainingCsvItemContractTests();items.r=case.e.r
        holder=items.pokemon('late-reroll-eject-holder')
        case.e.gm.add_combatant(holder,reason='actual unrelated held-reaction participant')
        obj=items.equip(case.e,holder,'late08/eject-pack','item/탈출팩')
        available=AP.available(case.t)
        case.e.boost_roll(case.t,case.t,roll_id='r',kind='skill')
        self.assertEqual(AP.available(case.t),available-1)
        self.assertNotIn('eject_pack',holder.spec.get(PHYSICAL.PENDING,{}))
        return case,holder,obj

    def open_window(self,case,holder):
        before=holder.stages['atk']
        case.e.change_stage(holder,'atk',-1)
        self.assertEqual(holder.stages['atk'],before-1)
        pending=deepcopy(holder.spec[PHYSICAL.PENDING]['eject_pack'])
        self.assertEqual(pending['instance_id'],'late08/eject-pack')
        return pending

    def test_late_faces_mutation_keeps_eject_window_first_roll_pending_cost_and_rng(self):
        case,holder,obj=self.fixture()
        history=list(getattr(case.t,'_action_history',[]))
        initial_rng=case.e.rng.getstate();observed={}
        options={'reroll_faces':[2]*4}
        def choose(first):
            observed['first']=first
            observed['window']=self.open_window(case,holder)
            observed['object']=deepcopy(obj)
            observed['rng']=case.e.rng.getstate()
            observed['ap']=AP.available(case.t)
            options['reroll_faces']=[2]
            return True
        options['decision']=choose
        with self.assertRaisesRegex(ValueError,'dice count mismatch'):
            case.roll(fixed=None,feature_options=options)
        self.assertEqual(len(observed['first'].faces),4,'callback must see the actual valid first roll')
        self.assertNotEqual(observed['rng'],initial_rng,'first random roll remains observed')
        event=SKILL.event(case.e,case.t,'r')
        self.assertIs(event.first,observed['first'])
        self.assertEqual(event.state,'pending');self.assertIsNone(event.final)
        self.assertEqual(case.e._ap_rolls['r']['state'],'resolved','original AP-backed roll stays resolved')
        self.assertEqual(holder.spec.get(PHYSICAL.PENDING,{}).get('eject_pack'),observed['window'],
            'late rejection before a committed reroll must preserve the actual reaction window')
        self.assertEqual(obj,observed['object']);self.assertNotIn('consumed',obj)
        self.assertTrue(holder.on_field)
        self.assertEqual(list(getattr(case.t,'_action_history',[])),history)
        self.assertEqual(case.used(),0)
        self.assertEqual(AP.available(case.t),observed['ap'])
        self.assertEqual(case.e.rng.getstate(),observed['rng'])

    def test_valid_accepted_reroll_expires_window_once_and_replay_keeps_new_window(self):
        case,holder,obj=self.fixture()
        history=list(getattr(case.t,'_action_history',[]));observed={}
        def choose(first):
            observed['first']=first
            observed['window']=self.open_window(case,holder)
            observed['rng']=case.e.rng.getstate()
            observed['ap']=AP.available(case.t)
            return True
        result=case.roll(fixed=None,feature_options={'decision':choose,'reroll_faces':[2]*4})
        event=SKILL.event(case.e,case.t,'r')
        self.assertIs(event.first,observed['first'])
        self.assertIs(event.final,result);self.assertEqual(event.state,'final')
        self.assertEqual(result.faces,(2,2,2,2))
        self.assertEqual(result.modifier,observed['first'].modifier+2)
        self.assertNotIn('eject_pack',holder.spec.get(PHYSICAL.PENDING,{}))
        self.assertEqual(case.t._action_history,history+['free']);self.assertEqual(case.used(),1)
        self.assertEqual(AP.available(case.t),observed['ap'])
        self.assertEqual(case.e.rng.getstate(),observed['rng'],'fixed replacement faces require no new RNG draw')
        self.assertNotIn('consumed',obj)
        fresh=self.open_window(case,holder);rng=case.e.rng.getstate()
        with self.assertRaises(ValueError):
            case.roll(fixed=None,feature_options={'decision':lambda first:True,'reroll_faces':[2]*4})
        self.assertEqual(holder.spec[PHYSICAL.PENDING]['eject_pack'],fresh)
        self.assertEqual(case.t._action_history,history+['free']);self.assertEqual(case.used(),1)
        self.assertEqual(case.e.rng.getstate(),rng)