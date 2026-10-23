"""Recompute current CSV/entity fidelity against the frozen original cell snapshot."""
import csv,json,re
from collections import defaultdict
from decimal import Decimal,InvalidOperation
from pathlib import Path
from import_source_xlsx import SHEETS
def norm(v):
    if isinstance(v,list):return [norm(x) for x in v]
    v='' if v is None else str(v).strip()
    try:return str(Decimal(v).normalize()) if v else ''
    except InvalidOperation:return re.sub(r'\s+','',v)
def cell_norm(value):
    value='' if value is None else str(value)
    if re.fullmatch(r'0[0-9]+',value):return value
    try:return str(Decimal(value).normalize()) if value else ''
    except InvalidOperation:return value

def current_checks(root,evidence):
    book=json.loads((evidence/'xlsx-cells.json').read_text(encoding='utf-8'))
    sheets=[]
    for stem,sheet in SHEETS.items():
        with (root/'input/db'/f'{stem}.csv').open(encoding='utf-8',newline='') as f:actual=list(csv.reader(f))
        expected=book[sheet]['rows'];differences=[]
        for i in range(max(len(actual),len(expected))):
            a=actual[i] if i<len(actual) else [];b=expected[i] if i<len(expected) else []
            for j in range(max(len(a),len(b))):
                av=a[j] if j<len(a) else '';bv=b[j] if j<len(b) else ''
                if cell_norm(av)!=cell_norm(bv):
                    differences.append(dict(row=i+1,col=j+1,local=av,remote=bv,kind='missing_in_csv' if bv and not av else 'value_difference'))
        sheets.append(dict(file=stem+'.csv',sheet=sheet,coordinate_semantics='original XLSX row and column',differences=differences))
    checks=[]
    for kind,sheet in [('moves','기술 목록'),('abilities','특성 데이터'),('pokemon','포켓몬 데이터')]:
        rows=book[sheet]['rows'];byname=defaultdict(list);used=defaultdict(int)
        for i,row in enumerate(rows,1):
            if row:byname[row[0].strip()].append((i,row))
        for entity in json.loads((root/'output/entities'/f'{kind}.json').read_text(encoding='utf-8')):
            name=entity['name'];pos=used[name];used[name]+=1
            record=dict(id=entity['id'],entity=kind,name=name,source_sheet=sheet,checked_fields=[],differences=[],cautions=[],source_column_disagreements=[],semantic_status='not_verified')
            matches=byname[name]
            if pos>=len(matches):
                record['differences'].append(dict(field='source_row',expected='matching source occurrence',actual=None));checks.append(record);continue
            rownum,r=matches[pos];g=lambda i:r[i] if i<len(r) else ''
            record.update(source_row=rownum,row_resolution='exact name, next occurrence in document order')
            def check(field,expected,actual):
                record['checked_fields'].append(field)
                if norm(expected)!=norm(actual):record['differences'].append(dict(field=field,expected=expected,actual=actual))
            if kind=='moves':
                for key,col in [('frequency',4),('range',6),('effect',7),('contest',8),('class',9),('type',10),('eng',22)]:
                    check(key,'' if key=='effect' and g(col)=='--' else g(col),entity.get(key))
                for key,col in [('damage_base',3),('ac',5)]:
                    try:
                        value=Decimal(g(col))
                        if value==value.to_integral_value():check(key,int(value),entity.get(key))
                    except InvalidOperation:
                        if g(col) not in ('','--','-'):record['cautions'].append(dict(field=key,source_value=g(col),reason='special header needs semantic review'))
            elif kind=='abilities':
                for key,col in [('frequency',1),('effect_primary',2),('trigger',3),('target',4),('keyword',5),('eng',7),('effect2',6)]:
                    check(key,g(col),entity.get(key))
                expected_primary=norm(g(2));actual_effect=norm(entity.get('effect'))
                if expected_primary not in actual_effect:record['differences'].append(dict(field='effect',expected='preserve primary effect',actual=entity.get('effect')))
                original='\n'.join(([f'키워드 - {g(5)}'] if g(5) else [])+([f'발동조건 - {g(3)}'] if g(3) else [])+([f'대상 - {g(4)}'] if g(4) else [])+[g(2)])
                if norm(original)!=norm(g(6)):record['source_column_disagreements'].append(dict(field='effect2_source_redundancy',primary=original,secondary=g(6),meaning='Original columns differ; preserved raw, needs semantic review'))
            else:
                for j,key in enumerate(['hp','atk','def','spa','spd','spe'],1):check('base_stats.'+key,g(j),entity['base_stats'].get(key))
                from ptk_structure import pokemon_type_values
                raw_types=[g(i) for i in [31,32] if g(i) not in ('','None','-')]
                expected_types,type_note=pokemon_type_values(g(0),raw_types)
                check('types',expected_types,entity['types'])
                if type_note is not None:
                    check('types_raw',raw_types,entity.get('types_raw'))
                    check('type_normalization_raw',type_note['raw'],entity.get('_type_normalization',{}).get('raw'))
                    check('type_normalization_values',expected_types,entity.get('_type_normalization',{}).get('normalized'))
                for j,key in enumerate(['land','sky','swim','levitate','burrow','high_jump','long_jump','power'],9):check('movement.'+key,g(j),entity['movement'].get(key))
                check('capabilities',[g(i) for i in range(18,27) if g(i) not in ('','-')],entity['capabilities'])
                check('size',g(27),entity['size']);check('weight_class',g(28),entity['weight_class'])
            record['status']='field_mismatch' if record['differences'] else 'selected_fields_match'
            checks.append(record)
    return sheets,checks
