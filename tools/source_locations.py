"""Coordinates describe CSV logical records (XLSX rows), never physical text lines."""
from pathlib import Path
from import_source_xlsx import SHEETS
WORKBOOK='https://docs.google.com/spreadsheets/d/1B9lu8IF37rSjM9uY4Cnzv9RfxI8w3TZBbfS9uBax5BU/edit'
def record(file,row,columns,end=None):
    name=Path(file).name
    return dict(file='db/'+name,record_span=[row,end or row],columns=columns,
                sheet=SHEETS.get(Path(name).stem),workbook_url=WORKBOOK)

def validate_record(root,source,title=None,cache=None):
    import csv
    root=Path(root);cache={} if cache is None else cache
    errors=[];file=source.get('file','');span=source.get('record_span')
    if Path(file).parent!=Path('db') or not (root/'input'/file).is_file():return ['missing_csv_file']
    if file not in cache:
        with (root/'input'/file).open(encoding='utf-8',newline='') as f:cache[file]=list(csv.reader(f))
    rows=cache[file]
    if not isinstance(span,list) or len(span)!=2 or not all(type(i) is int for i in span) or not 1<=span[0]<=span[1]<=len(rows):
        return ['invalid_record_span']
    if source.get('sheet')!=SHEETS.get(Path(file).stem):errors.append('wrong_sheet')
    columns=source.get('columns') or {}
    if not columns or any(type(c) is not int or c<1 or c>len(rows[span[0]-1]) for c in columns.values()):
        return errors+['invalid_columns']
    if title is not None and 'name' in columns and rows[span[0]-1][columns['name']-1].strip()!=title.strip():
        errors.append('record_name_mismatch')
    return errors
