"""Q50/C04-101: mandatory original Edge and actual current source-owned adoption."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Combatant,Rules
from provocateur_fixture import ProvocateurScene
from ruleset import RuleFilter
import provocateur as P
import skill_modifiers as SKILLS
import state_codec as CODEC
import state_grants as G
import trainer_feature_acquisition as T
import trainer_retraining as RETRAIN
import world_entities as WORLD


class PushButtonsMandatoryDemoralizeTests(ProvocateurScene,unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def holder(self,*,demoralize=False):
        self.common['skills']=dict(self.common['skills'],협박=4 if demoralize else 1)
        self.a=self.add('actual imported current Push owner','trainer',(3,2),
            feats=[P.PUSH],classes=[P.CLASS],edges=['edge/호감인']+([P.DEMO] if demoralize else []),exp_bank=100)
        self.assertEqual(P.records(self.a),[])
        self.assertEqual(self.e.r._selected_rule(P.PUSH),P.PUSH)
        return self.a

    def adopt(self,request='push/current-demoralize'):
        return P.adopt_demoralize(self.e,self.a,adoption_request_id=request)

    def withdraw(self):
        sources={uid:RETRAIN.owned_source(self.e,self.a,uid) for uid in RETRAIN._owned(self.a)}
        removed=G._revocation_sources(self.a,[sources[P.PUSH]])
        dependencies={source:[] for source in sources.values() if source not in removed}
        return RETRAIN.retrain(self.e,self.a,P.PUSH,request_id='push/actual-current-retraining',
            reason='actual current source withdrawal',gm_decision={'allowed':True,'reason':'actual consultation'},
            retained_dependencies=dependencies)

    def cold_restore(self):
        ids={key:getattr(self,key).entity_id for key in ('a','t','b','u')}
        payload=json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False))
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),payload)
        index=WORLD.actor_index(self.e)
        for key,uid in ids.items():setattr(self,key,index[uid])

    def test_new_missing_demoralize_decline_refuses_and_real_grant_waives_low_rank_once(self):
        self.skills(협박=1);self.acquire(P.CLASS)
        before=self.a.stats['spe']
        self.reject(lambda:self.acquire(P.PUSH,selection={'edge':None}),'must grant Demoralize')
        self.assertIsNone(P.acquired(self.a,P.PUSH));self.assertNotIn(P.DEMO,self.a.spec['edges'])
        receipt=self.acquire(P.PUSH)
        self.assertEqual(receipt['snapshot']['selection'],{'edge':P.DEMO})
        self.assertEqual(self.a.stats['spe'],before+1)
        self.assertEqual(self.a.spec['edges'].count(P.DEMO),1);self.assertTrue(P.waive_demoralize(self.a))
        saved=deepcopy(P.acquired(self.a,P.PUSH))
        self.acquire(P.PUSH)
        self.assertEqual(P.acquired(self.a,P.PUSH),saved);self.assertEqual(self.a.stats['spe'],before+1)
        self.begin();row=self.use(self.a,self.t,'move/째려보기',face=18)
        self.assertTrue(row['results'][self.t.entity_id]['hit']);self.assertLess(self.t.hp,self.t.max_hp)
        self.valid()

    def test_existing_independent_demoralize_may_decline_replacement_and_survives_source_loss(self):
        self.setup(edges=['edge/호감인',P.DEMO]);self.acquire(P.CLASS)
        receipt=self.acquire(P.PUSH,selection={'edge':None})
        self.assertTrue(receipt['snapshot']['demoralize_already_owned'])
        self.assertEqual(self.a.spec['edges'].count(P.DEMO),1);self.assertFalse(P.waive_demoralize(self.a))
        before=self.a.stats['spe']
        self.reject(lambda:self.adopt(),'independent Demoralize')
        self.withdraw();self.assertIn(P.DEMO,self.a.spec['edges'])
        self.assertEqual(self.a.stats['spe'],before-1);self.assertFalse(P.waive_demoralize(self.a));self.valid()

    def test_actual_current_import_grant_has_no_fabricated_history_or_replayed_stat_and_restores(self):
        self.holder();before=self.a.stats['spe']
        receipt=self.adopt();source=receipt['source_id']
        self.assertIsNone(receipt['parent_acquisition_request']);self.assertEqual(P.records(self.a),[])
        self.assertNotIn('static_acquisition',G.state(self.a)['sources'][source])
        self.assertEqual(self.a.stats['spe'],before);self.assertEqual(self.a.spec['edges'].count(P.DEMO),1)
        self.assertTrue(P.waive_demoralize(self.a));self.assertEqual(self.adopt(),receipt)
        self.reject(lambda:self.adopt('push/different-current-request'),'replay')
        self.begin();row=self.use(self.a,self.t,'move/째려보기',face=19)
        self.assertTrue(row['results'][self.t.entity_id]['hit']);self.assertIn('취약',self.t.conditions)
        self.cold_restore();self.assertEqual(self.adopt(),receipt);self.assertTrue(P.waive_demoralize(self.a))
        self.assertEqual(P.records(self.a),[]);self.assertEqual(self.a.stats['spe'],before);self.valid()
        # Cold saves omit GM checkpoint history; create this checkpoint in the restored world.
        self.e.gm.snapshot('actual current Demoralize grant')
        self.withdraw();self.assertNotIn(P.DEMO,self.a.spec['edges']);self.assertFalse(P.waive_demoralize(self.a))
        self.assertEqual(self.a.stats['spe'],before)
        self.e.gm.restore('actual current Demoralize grant',reason='restore the actual present source-owned grant')
        index=WORLD.actor_index(self.e);self.a=index[self.a.entity_id];self.t=index[self.t.entity_id]
        self.assertEqual(self.adopt(),receipt);self.assertTrue(P.waive_demoralize(self.a))
        self.assertEqual(P.records(self.a),[]);self.valid()

    def test_unowned_foreign_ended_unselected_and_disconnected_current_sources_refuse_atomically(self):
        self.reject(lambda:self.adopt(),'current Push Buttons owner')
        self.holder()
        stranger=Combatant(self.e.r,dict(deepcopy(self.a.spec),name='unregistered current sheet'))
        self.reject(lambda:P.adopt_demoralize(self.e,stranger,adoption_request_id='push/unregistered'),'registered|actual|native')
        source=RETRAIN.owned_source(self.e,self.a,P.PUSH)
        row=G.state(self.a)['sources'][source];owner=row['owner_id'];row['owner_id']=self.b.entity_id
        self.reject(lambda:self.adopt(),'provenance changed');row['owner_id']=owner
        previous=self.e.r.ruleset;before=self.e.export_state()
        self.e.r.ruleset=RuleFilter({'sources':['core'],'variants':[],'exclude_units':[P.PUSH]});self.e.r._apply_ruleset()
        try:
            with self.assertRaisesRegex(ValueError,'selected static Feature'):self.adopt()
        finally:self.e.r.ruleset=previous;self.e.r._apply_ruleset()
        self.assertEqual(self.e.export_state(),before)
        G.revoke(self.a,source,engine=self.e)
        self.reject(lambda:self.adopt(),'ended Push Buttons')
        self.setup();self.holder();receipt=self.adopt()
        parent=G.state(self.a)['sources'][receipt['source_id']]
        before=self.e.export_state();sources=list(parent['effect_sources'])
        child='feature:'+self.a.entity_id+':'+P.DEMO;parent['effect_sources'].remove(child)
        corrupt=list(parent['effect_sources'])
        try:
            with self.assertRaisesRegex(ValueError,'connected owned sources'):self.adopt()
            self.assertEqual(parent['effect_sources'],corrupt)
        finally:parent['effect_sources'][:]=sources
        self.assertEqual(self.e.export_state(),before);self.valid()

    def test_actual_declared_seven_and_ten_acquire_and_restore_without_a_local_upper_cap(self):
        for name,rank,dice,english in (('초월',7,7,'Epic'),('신화',10,7,'Mythic')):
            self.rules.rulings.set_mech('gameplay/skill-rank-dice','by_rank_name.'+name,
                {'rank':rank,'dice':str(dice)+'d6','eng':english},
                reason='actual campaign ordinary rank declaration',scope='campaign',rules=self.rules)
        self.skills(매력=7,교활='Epic',협박=10)
        self.acquire(P.CLASS);self.acquire(P.PUSH);self.acquire(P.QUICK)
        receipt=deepcopy(P.acquired(self.a,P.PUSH))
        self.assertEqual(receipt['snapshot']['skills'],{'매력':7,'교활':7,'협박':10})
        self.assertEqual(SKILLS.rank(self.e.r,self.a,'협박'),('신화','7d6',10));self.valid()
        self.cold_restore();self.assertEqual(P.acquired(self.a,P.PUSH),receipt)
        self.assertEqual(SKILLS.rank(self.e.r,self.a,'협박'),('신화','7d6',10));T.validate_actor(self.a);self.valid()


if __name__=='__main__':unittest.main(verbosity=2)
