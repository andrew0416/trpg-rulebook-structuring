"""Source-derived obligations for plate references and the Flayed One gift.
Expectations are constants transcribed from source, never read from reviewed effects.
"""
import hashlib,json,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from synthetic_rule_fixture import register_synthetic
import items as ITEMS
import effects as FX
import downtime as DT

PLATES=[
('용의플레이트','드래곤',159),('공포플레이트','악',160),('대지플레이트','땅',161),
('주먹플레이트','격투',162),('불구슬플레이트','불꽃',163),('고드름플레이트','얼음',164),
('비단벌레플레이트','벌레',165),('강철플레이트','강철',166),('초록플레이트','풀',167),
('이상한플레이트','에스퍼',168),('정령플레이트','페어리',169),('푸른하늘플레이트','비행',170),
('물방울플레이트','물',171),('원령플레이트','고스트',172),('암석플레이트','바위',173),
('맹독플레이트','독',174),('우뢰플레이트','전기',175),('순백플레이트','노말',176)]
GIFT='feat/이벨타르의-메이저-기프트-박피사의-접촉'

class ReferenceRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset='all')
        # Isolated test payload; this registration does not certify a source rule.
        register_synthetic(cls.rules,'audit/plate-damage',name='검사 공격')
    def fixture(self,item=None,feat=False):
        e=Engine(self.rules,seed=19)
        def actor(name):
            return Combatant(self.rules,dict(name=name,kind='trainer',level=10,
                stats={s:20 for s in ['hp','atk','def','spa','spd','spe']},
                types=[],abilities=[],feats=[GIFT] if feat and name=='holder' else []))
        a,b=actor('holder'),actor('target')
        a.types=[];b.types=[]
        if item:a.item=item;ITEMS.register_item(e,a)
        if feat:ITEMS.register_feats(e,a)
        return e,a,b
    def move(self,ty,category='물리'):
        return dict(id='audit/plate-damage',name='검사 공격',type=ty,damage_base=12,**{'class':category},range='원거리')
    def bonus(self,e,a,b,m):
        return FX.passive_damage_mods(e,a,b,m,dict(attacker=a,target=b,move=m,hit=True,engine=e))[1]
    def test_original_plate_reference_chain(self):
        book=json.loads((ROOT/'output/source-audit/2026-10-10/xlsx-cells.json').read_text(encoding='utf-8'))
        cells=book['인벤 데이터']['cells']
        text=(ROOT/'input/ch09-equipment.md').read_text(encoding='utf-8').splitlines()
        self.assertIn('5',text[817]);self.assertIn('15',text[818])
        for name,ty,row in PLATES:
            self.assertEqual(cells[f'J{row}'].strip(),name)
            self.assertIn(ty+'부스터',cells[f'L{row}']);self.assertIn(ty+'깁스',cells[f'L{row}'])
        self.assertIn('타입부스터와 타입깁스',cells['L158'])
    def test_generic_plate_requires_type_selection(self):
        e,a,b=self.fixture('타입플레이트')
        for _,ty,_ in PLATES:
            m=self.move(ty)
            self.assertEqual(self.bonus(e,a,b,m),0)
            self.assertEqual(ITEMS.item_damage_reduction(a,m),0)
        effects,_=self.rules.item_effects('타입플레이트')
        self.assertEqual(sum(x.get('type')=='damage_reduction' and x.get('value')==15 and x.get('vs_type')=='chosen' for x in effects),1)
        self.assertFalse(any(x.get('type')=='damage_reduction' for x in a.modifiers))
    def test_gift_one_additional_injury_per_acknowledged_trigger(self):
        e,a,b=self.fixture(feat=True)
        before=b.injuries
        for i in range(3):
            self.assertEqual(ITEMS.manual_feat(e,a,GIFT,b),(1,0))
            self.assertEqual(b.injuries,before+i+1)
        self.assertEqual(a.injuries,0)
    def test_gift_fourth_use_rejected_without_target_mutation(self):
        e,a,b=self.fixture(feat=True)
        for _ in range(3):ITEMS.manual_feat(e,a,GIFT,b)
        before=(b.injuries,b.hp)
        self.assertEqual(ITEMS.manual_feat(e,a,GIFT,b),(0,1))
        self.assertEqual((b.injuries,b.hp),before)
    def test_gift_scene_end_does_not_refresh_daily_limit(self):
        e,a,b=self.fixture(feat=True)
        for _ in range(3):ITEMS.manual_feat(e,a,GIFT,b)
        e.end_scene([a,b])
        self.assertEqual(ITEMS.manual_feat(e,a,GIFT,b),(0,1))
        self.assertEqual(b.injuries,3)
    def test_gift_explicit_new_day_refreshes_only_daily_uses(self):
        e,a,b=self.fixture(feat=True)
        for _ in range(3):ITEMS.manual_feat(e,a,GIFT,b)
        DT.new_day(a)
        for _ in range(3):self.assertEqual(ITEMS.manual_feat(e,a,GIFT,b),(1,0))
        self.assertEqual(ITEMS.manual_feat(e,a,GIFT,b),(0,1))
        self.assertEqual(b.injuries,6)
    def test_gift_usage_survives_serialized_spec_and_reregistration(self):
        e,a,b=self.fixture(feat=True)
        for _ in range(3):ITEMS.manual_feat(e,a,GIFT,b)
        spec=json.loads(json.dumps(a.spec,ensure_ascii=False))
        restored=Combatant(self.rules,spec)
        ITEMS.register_feats(e,restored)
        ITEMS.register_feats(e,restored)
        self.assertEqual(ITEMS.manual_feat(e,restored,GIFT,b),(0,1))

def make_plate_test(name,ty,mode):
    def test(self):
        e,a,b=self.fixture(name)
        if mode=='matching':
            for cls in ['물리','특수']:
                m=self.move(ty,cls)
                self.assertEqual(self.bonus(e,a,b,m),5)
                self.assertEqual(ITEMS.item_damage_reduction(a,m),15)
                base_e,plain,target=self.fixture()
                baseline=base_e.roll_damage(plain,target,m,set_damage=True)
                self.assertEqual(e.roll_damage(a,b,m,set_damage=True),baseline+5)
                self.assertEqual(e.roll_damage(b,a,m,set_damage=True),baseline-15)
        elif mode=='nonmatching':
            for _,other,_ in PLATES:
                if other==ty:continue
                for cls in ['물리','특수']:
                    m=self.move(other,cls)
                    self.assertEqual(self.bonus(e,a,b,m),0)
                    self.assertEqual(ITEMS.item_damage_reduction(a,m),0)
            self.assertEqual(self.bonus(e,a,b,self.move(ty,'변화')),0)
        else:
            m=self.move(ty)
            self.assertEqual(ITEMS.register_item(e,a),0)
            self.assertEqual(self.bonus(e,a,b,m),5)
            self.assertEqual(ITEMS.item_damage_reduction(a,m),15)
            ITEMS.unregister_item(e,a)
            self.assertEqual(self.bonus(e,a,b,m),0)
            self.assertEqual(ITEMS.item_damage_reduction(a,m),0)
            b.item=name;ITEMS.register_item(e,b)
            self.assertEqual(self.bonus(e,b,a,m),5)
            self.assertEqual(ITEMS.item_damage_reduction(b,m),15)
    return test
for index,(name,ty,row) in enumerate(PLATES,1):
    for mode in ['matching','nonmatching','lifecycle']:
        setattr(ReferenceRuleTests,f'test_plate_{index:02d}_{mode}',make_plate_test(name,ty,mode))

if __name__=='__main__':
    class RecordedResult(unittest.TextTestResult):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.rows=[]
        def record(self,test,status):self.rows.append(dict(id='REF-'+test._testMethodName,status=status))
        def addSuccess(self,test):super().addSuccess(test);self.record(test,'pass')
        def addFailure(self,test,err):super().addFailure(test,err);self.record(test,'fail')
        def addError(self,test,err):super().addError(test,err);self.record(test,'error')
        def addSkip(self,test,reason):super().addSkip(test,reason);self.record(test,'skip')
    result=unittest.TextTestRunner(verbosity=2,resultclass=RecordedResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceRuleTests))
    paths=[p for folder,glob in [('engine','*.py'),('data','*.json')] for p in (ROOT/folder).glob(glob)]
    paths += [ROOT/'tools/synthetic_rule_fixture.py',Path(__file__),ROOT/'input/ch09-equipment.md',ROOT/'input/supp-blessings.md',ROOT/'output/source-audit/2026-10-10/xlsx-cells.json']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),results=result.rows,
        scope='Plate +5/DR15 type restrictions and lifecycle; GM-acknowledged Flayed One +1 injury and daily cap. Not full source certification.',
        input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/reference-rule-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
