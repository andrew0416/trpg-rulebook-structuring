"""Export XLSX cached cell values, preserving coordinates and mixed cell types."""
import argparse,csv,hashlib,json,posixpath,re,zipfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
SHEETS={'abilities':'특성 데이터','calculator':'계산기','class-data':'클래스 데이터','damage-table':'데미지표','edges':'엣지 데이터','feats':'재주 데이터','inventory':'인벤 데이터','item-data':'아이템 데이터','learnsets':'포켓몬 데이터2','moves':'기술 목록','nature-type':'성격타입 정보','poke-edges':'포켓 엣지','pokebot':'포켓봇 데이터','pokemon-skills':'포켓몬 스킬','pokemon':'포켓몬 데이터','tm':'기술머신 데이터','weight-class':'무게 클래스'}
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
def number(value):
    n=Decimal(value)
    return str(int(n)) if n==n.to_integral_value() else format(n.normalize(),'f')
def read_workbook(path):
    result={}
    with zipfile.ZipFile(path) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(t.text or '' for t in si.findall('.//s:t',NS)) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
        relations={e.attrib['Id']:e.attrib['Target'] for e in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',NS):
            target=relations[sheet.attrib['{'+REL+'}id']]
            target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            cells={};missing=[];formulas=0
            for c in ET.fromstring(z.read(target)).findall('.//s:sheetData/s:row/s:c',NS):
                ref=c.attrib['r'];typ=c.get('t','n');v=c.find('s:v',NS);f=c.find('s:f',NS)
                if f is not None:
                    formulas+=1
                    if v is None:missing.append(ref)
                value=(v.text or '') if v is not None else ''
                if typ=='s':value=strings[int(value)] if value else ''
                elif typ=='inlineStr':value=''.join(t.text or '' for t in c.findall('.//s:t',NS))
                elif typ=='n' and value:value=number(value)
                if value:cells[ref]=value
            indexed={}
            for ref,value in cells.items():
                col=0
                for ch in re.match('[A-Z]+',ref)[0]:col=col*26+ord(ch)-64
                indexed[(int(re.search('[0-9]+',ref)[0]),col)]=value
            height=max((r for r,c in indexed),default=0);width=max((c for r,c in indexed),default=0)
            rows=[[indexed.get((r,c),'') for c in range(1,width+1)] for r in range(1,height+1)]
            result[sheet.attrib['name']]=dict(rows=rows,cells=cells,formula_count=formulas,missing_formula_cache=missing)
    return result
def export(path,destination):
    book=read_workbook(path)
    missing={n:book[n]['missing_formula_cache'] for n in SHEETS.values() if book[n]['missing_formula_cache']}
    if missing:raise ValueError('Formula cells have no cached value: '+json.dumps(missing,ensure_ascii=False))
    destination.mkdir(parents=True,exist_ok=True);records={}
    for stem,sheet in SHEETS.items():
        p=destination/(stem+'.csv')
        with p.open('w',encoding='utf-8',newline='') as f:csv.writer(f,lineterminator='\n').writerows(book[sheet]['rows'])
        records[p.name]=dict(sheet=sheet,rows=len(book[sheet]['rows']),nonempty_cells=len(book[sheet]['cells']),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    manifest=dict(format='xlsx-cell-coordinates-v1',source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),limitation='Cached values, formulas not recalculated. Integral numbers normalized; text leading zeros preserved.',files=records)
    (destination/'source-xlsx.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest
if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('xlsx',type=Path);ap.add_argument('destination',type=Path);a=ap.parse_args()
    print(json.dumps(export(a.xlsx,a.destination),ensure_ascii=False,indent=2))
