"""Native armed-but-unreached Help controls; Root executes after composition."""
from copy import deepcopy
from pathlib import Path
import os
import sys
import unittest

ROOT=Path(os.environ.get('PTK_EXPERIMENT_ROOT') or Path(__file__).resolve().parents[1]).resolve()
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_adversarial_review04 as REVIEW
import skill_feature_actions as SF
import blessing_skill_rules as B
import hobbyist


class ArmedHelpPrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        REVIEW.AdversarialReview04.setUpClass()

    def test_scoped_and_authored_team_unreached_help_keep_private_group_before_native_refusal(self):
        for route in ('scoped','policy'):
            with self.subTest(route=route):
                case=REVIEW.AdversarialReview04('runTest')
                fixture,engine,first,second=case.team()
                helper=fixture.trainer(engine,'private-group-helper-'+route,(4,2),feats=(SF.HELP,))
                help_seen=[];probability_seen=[]
                engine.offer_let_me_help(helper,second,request_id='unreached-'+route,payment='next',
                    decision=lambda roll:help_seen.append(roll) or False)
                def invalid_probability(roll):
                    probability_seen.append(roll)
                    return 'invalid native choice'
                engine.arm_probability_control(first,second,purpose='skill',decision=invalid_probability)
                purpose='actual private group '+route
                requests=[]
                for actor in (first,second):
                    if route=='scoped':
                        plan=engine.plan_skill_check(actor,'오컬트학',purpose=purpose,target=actor,provider=actor)
                        requests.append({'actor':actor,'target':actor,'provider':actor,'skill':'오컬트학',
                            'purpose':purpose,'replacement':None,'options':{},'expected_plan':plan})
                    else:
                        document={'schema':1,'id':'unreached-help-policy/'+actor.entity_id,'variants':[{
                            'rule_id':SF.HELP,
                            'source':{'file':'input/ch03-skills-edges-feats.md','sha256':hobbyist.GENERAL},
                            'values':{'roll_plan':{'skill':'오컬트학','purpose':purpose,'provider_id':helper.entity_id,
                                'provider_requirement':{'source_id':SF.HELP,'minimum_count':1},'options':{}}},
                            'inputs':{}}]}
                        requests.append({'actor':actor,'target':actor,'document':document,'purpose':purpose})
                actors=(first,second,helper)
                before=case.team_state(engine,actors)
                procedure={'kind':'team','dc':10,'required_people':2}
                with self.assertRaisesRegex(ValueError,'observed native reroll choice'):
                    if route=='scoped':engine.resolve_roll_context(requests,procedure,request_id='unreached/scoped')
                    else:engine.execute_source_policy_rolls(requests,procedure,request_id='unreached/policy')
                self.assertEqual(len(probability_seen),1)
                self.assertEqual(help_seen,[])
                self.assertEqual(case.team_state(engine,actors),before)
                self.assertEqual(first.spec[B.STATE]['activations'][B.ANCIENT_WISDOM]['status'],'pending')
                records=getattr(engine,'_roll_context_requests' if route=='scoped' else '_roll_policy_requests',{})
                self.assertNotIn('unreached/'+route,records)


    def test_unordered_multiple_offers_reject_before_any_private_group_roll(self):
        case=REVIEW.AdversarialReview04('runTest')
        fixture,engine,first,second=case.team()
        helper=fixture.trainer(engine,'unordered-group-helper',(4,2),feats=(SF.HELP,))
        seen=[]
        for target in (first,second):
            engine.offer_let_me_help(helper,target,request_id='unordered/'+target.entity_id,payment='next',
                                    decision=lambda roll:seen.append(roll) or False)
        before=case.team_state(engine,(first,second,helper))
        with self.assertRaisesRegex(ValueError,'multiple Let Me Help reactions'):
            engine.common_action(skill='오컬트학',dc=10,mode='team',participants=[first,second],
                                 required_people=2,equal_contribution=True,no_main_actor=True)
        self.assertEqual(seen,[])
        self.assertEqual(case.team_state(engine,(first,second,helper)),before)
        self.assertEqual(first.spec[B.STATE]['activations'][B.ANCIENT_WISDOM]['status'],'pending')


if __name__=='__main__':
    unittest.main()