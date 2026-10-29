"""Independent original-cell checks and conditional STAB regression cases."""
import csv,json,re,sys,unittest
from decimal import Decimal,InvalidOperation
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from synthetic_rule_fixture import register_synthetic
from import_source_xlsx import SHEETS
from ptk_structure import parse_abilities
def normalized(value):
    value='' if value is None else str(value)
    if re.fullmatch(r'0[0-9]+',value):return value
    try:return str(Decimal(value).normalize()) if value else ''
    except InvalidOperation:return value
class SourceRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=json.loads((ROOT/'output/source-audit/2026-10-10/xlsx-cells.json').read_text(encoding='utf-8'))
        cls.rules=Rules(str(ROOT),ruleset='all')
        # Component-only synthetic attack identity; never a production/core source.
        register_synthetic(cls.rules,'audit/fighting',name='감사 공격')
    def test_every_original_cell_survives_csv_at_same_coordinate(self):
        differences=[]
        for stem,sheet in SHEETS.items():
            with (ROOT/'input/db'/f'{stem}.csv').open(encoding='utf-8',newline='') as f:actual=list(csv.reader(f))
            expected=self.source[sheet]['rows']
            for i in range(max(len(expected),len(actual))):
                a=actual[i] if i<len(actual) else [];b=expected[i] if i<len(expected) else []
                for j in range(max(len(a),len(b))):
                    av=a[j] if j<len(a) else '';bv=b[j] if j<len(b) else ''
                    if normalized(av)!=normalized(bv):differences.append((stem,i+1,j+1,av[:40],bv[:40]))
        self.assertEqual(len(differences),0,str(differences[:8])+f'; total={len(differences)}')
    def test_effect2_retained_and_bonus_in_effect_body(self):
        abilities,_=parse_abilities(str(ROOT/'input/db/abilities.csv'))
        a=next(a for a in abilities if a['name']=='마이티체인지[홈브류]')
        bonus='보너스: 마이티폼일 때, 사용자는 격투타입 기술에 자속 보정을 받습니다.'
        self.assertIn(bonus,self.source['특성 데이터']['cells']['G685'])
        self.assertIn(bonus,a['effect'])
        self.assertEqual(a['effect2'],self.source['특성 데이터']['cells']['G685'])
    def test_original_headers_and_region_labels_are_not_entities(self):
        def read(name):return json.loads((ROOT/'output/entities'/name).read_text(encoding='utf-8'))
        self.assertEqual(len(read('pokemon.json')),1212)
        self.assertEqual(len(read('learnsets.json')),1212)
        self.assertEqual(read('pokemon-failed.json'),[])
        self.assertNotIn('포켓몬 이름:',[x['species'] for x in read('learnsets.json')])
        self.assertEqual(read('pokemon.json')[0]['dex'],'001')
        self.assertEqual(len(read('fields_sheet.json')),12)

    def fixture(self,ability=True,types=None,ruleset=None):
        rules=self.rules if ruleset is None else Rules(str(ROOT),ruleset=ruleset)
        if ruleset is not None:
            # Explicit fixture-only admission; the core profile still excludes custom/HB rules.
            register_synthetic(rules,'audit/fighting',name='감사 공격')
        e=Engine(rules,seed=11)
        c=Combatant(rules,dict(name='감사 대상',kind='pokemon',level=10,stats={'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},types=types or ['물'],abilities=['마이티체인지[홈브류]'] if ability else []))
        e.register_abilities(c)
        # Activation, recall and stat replacement remain separate unverified clauses.
        c.form='마이티폼'
        move={'id':'audit/fighting','name':'감사 공격','type':'격투','damage_base':6,'class':'물리'}
        return e,c,move
    def test_mighty_fighting_attack_gets_source_stab_plus_two(self):
        e,c,m=self.fixture()
        for category in ['물리','특수']:
            m['class']=category;self.assertEqual(e.damage_base(c,m),8)
    def test_non_mighty_form_does_not_get_bonus(self):
        e,c,m=self.fixture();c.form='나이브폼';self.assertEqual(e.damage_base(c,m),6)
    def test_other_type_does_not_get_bonus(self):
        e,c,m=self.fixture();m['type']='불꽃';self.assertEqual(e.damage_base(c,m),6)
    def test_form_without_ability_does_not_get_bonus(self):
        e,c,m=self.fixture(ability=False);self.assertEqual(e.damage_base(c,m),6)
    def test_natural_stab_is_not_doubled(self):
        e,c,m=self.fixture(types=['격투']);self.assertEqual(e.damage_base(c,m),8)
    def test_status_and_struggle_do_not_get_bonus(self):
        e,c,m=self.fixture();m['class']='변화';self.assertEqual(e.damage_base(c,m),6)
        m['class']='물리';m['id']='struggle';self.assertEqual(e.damage_base(c,m),6)
    def test_form_reversion_and_ability_removal_stop_bonus(self):
        e,c,m=self.fixture();self.assertEqual(e.damage_base(c,m),8)
        c.form=None;self.assertEqual(e.damage_base(c,m),6)
        c.form='마이티폼';c.abilities=[];self.assertEqual(e.damage_base(c,m),6)
    def test_core_ruleset_does_not_enable_homebrew_bonus(self):
        e,c,m=self.fixture(ruleset='core');self.assertEqual(e.damage_base(c,m),6)
if __name__=='__main__':
    import hashlib
    from datetime import datetime,timezone
    class RecordedResult(unittest.TextTestResult):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.rows=[]
        def record(self,test,status):self.rows.append(dict(id='SRC-'+test._testMethodName,status=status))
        def addSuccess(self,test):super().addSuccess(test);self.record(test,'pass')
        def addFailure(self,test,err):super().addFailure(test,err);self.record(test,'fail')
        def addError(self,test,err):super().addError(test,err);self.record(test,'error')
        def addSkip(self,test,reason):super().addSkip(test,reason);self.record(test,'skip')
    result=unittest.TextTestRunner(verbosity=2,resultclass=RecordedResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(SourceRepairTests))
    paths=[p for folder,glob in [('engine','*.py'),('data','*.json'),('output/entities','*.json'),('input/db','*.csv')] for p in (ROOT/folder).glob(glob)]
    paths += [ROOT/'tools/synthetic_rule_fixture.py',Path(__file__),ROOT/'tools/ptk_structure.py',ROOT/'tools/import_source_xlsx.py',ROOT/'output/source-audit/2026-10-10/xlsx-cells.json']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),results=result.rows,input_hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/source-repair-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
