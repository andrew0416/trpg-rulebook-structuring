"""Executable-row restoration; these tests add no source-clause certification."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine')]
from engine import Rules,Engine,Combatant
from state_codec import dump_engine,load_engine
import items as I
import state_grants as G

GIFT='feat/이벨타르의-메이저-기프트-박피사의-접촉'
TRIGGER='feat/강철의-챔피언'

class FeatureRegistrationRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='all')

    def fixture(self,feat=GIFT):
        e=Engine(self.rules,seed=19)
        def actor(name,feats):
            return Combatant(self.rules,dict(id='trainer/'+name,name=name,kind='trainer',level=10,
                stats={s:20 for s in ['hp','atk','def','spa','spd','spe']},
                types=[],abilities=[],feats=feats))
        a,b=actor('registration-holder',[feat]),actor('registration-target',[])
        e.everyone=e.gm.everyone=[a,b]
        I.register_feats(e,a)
        return e,a,b

    def test_partial_daily_usage_survives_sheet_restore_and_repeated_registration(self):
        e,a,b=self.fixture()
        self.assertEqual(I.manual_feat(e,a,GIFT,b),(1,0))
        restored=Combatant(self.rules,json.loads(json.dumps(a.spec,ensure_ascii=False)))
        before=deepcopy(restored.spec)
        for _ in range(3):I.register_feats(e,restored)
        self.assertEqual(restored.spec,before)
        self.assertEqual(len(restored.registry),1)
        self.assertEqual(b.injuries,1)
        self.assertEqual([I.manual_feat(e,restored,GIFT,b) for _ in range(3)],[(1,0),(1,0),(0,1)])
        self.assertEqual(b.injuries,3)

    def test_durable_restore_retains_live_row_identity_and_source_revocation(self):
        e,a,b=self.fixture()
        self.assertEqual(I.manual_feat(e,a,GIFT,b),(1,0))
        restored=load_engine(self.rules,json.loads(json.dumps(dump_engine(e),ensure_ascii=False)))
        a,b=restored.everyone
        row=a.registry[0];before=deepcopy(a.spec)
        I.register_feats(restored,a);I.register_feats(restored,a)
        self.assertIs(a.registry[0],row)
        self.assertEqual(len(a.registry),1);self.assertEqual(a.spec,before)
        self.assertEqual([I.manual_feat(restored,a,GIFT,b) for _ in range(3)],[(1,0),(1,0),(0,1)])
        source=next(k for k in G.state(a)['sources'] if k.startswith('feature:'))
        G.revoke(a,source,engine=restored)
        self.assertFalse(a.registry)
        self.assertIsNone(I.manual_feat(restored,a,GIFT,b))

    def test_trigger_row_restored_once_and_remains_source_owned(self):
        e,a,b=self.fixture(TRIGGER)
        self.assertEqual(len(a.ability_triggers),1)
        expected=deepcopy(a.ability_triggers)
        restored=Combatant(self.rules,json.loads(json.dumps(a.spec,ensure_ascii=False)))
        for _ in range(3):I.register_feats(e,restored)
        self.assertEqual(restored.ability_triggers,expected)
        source=next(k for k in G.state(restored)['sources'] if k.startswith('feature:'))
        G.revoke(restored,source,engine=e)
        self.assertFalse(restored.ability_triggers)

    def test_mixed_receipt_and_duplicate_rows_reject_without_replaying_effects(self):
        for corrupt in ('listeners','stages','duplicate'):
            with self.subTest(corrupt=corrupt):
                e,a,b=self.fixture()
                row=a.registry[0];part=row[G.TAG]
                if corrupt=='duplicate':a.registry.append(deepcopy(row))
                else:
                    a.registry.clear()
                    receipt=G.state(a)['effects'][part]
                    if corrupt=='listeners':receipt['listeners'].append('unrestored-passive')
                    else:receipt['stages']=True
                before=deepcopy((a.spec,a.registry,a.stages,a.stats,b.injuries))
                with self.assertRaises(ValueError):I.register_feats(e,a)
                self.assertEqual((a.spec,a.registry,a.stages,a.stats,b.injuries),before)

if __name__=='__main__':unittest.main()
