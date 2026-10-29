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


def normalize_source_text(text):
    """Presentation-only search key; signs, numbers, words and slash survive."""
    import re,unicodedata
    text=unicodedata.normalize('NFC',text).translate(str.maketrans({'–':'-','—':'-','‑':'-'}))
    text=re.sub(r'</?(?:table|tr|td|th|br|span)\b[^>]*>','',text,flags=re.I)
    text=re.sub(r'(?m)^\s*#{1,6}\s+','',text)
    text=re.sub(r'(?m)^\s*\|([^\n]*)\|\s*$',lambda m:m[1].replace('|',''),text)
    text=text.replace('**','').replace('__','').replace('`','')
    return re.sub(r'''[\s»“”‘’"']''','',text)


def compare_csv_book(root,registry=None):
    """Find source candidates, not full equivalence, variants, PASS or credit.

    Read each source once. Explicit CSV coordinates and saved cells must agree
    before cached spans and then bounded named headings are searched.
    """
    import csv,hashlib,io,json,re
    from collections import Counter
    root=Path(root).resolve()
    registry_path=root/'data/verification/category2-class-csv-clause-status.json' if registry is None else Path(registry)
    registry_raw=registry_path.read_bytes()
    saved=json.loads(registry_raw.decode('utf-8-sig'))
    pending=[r for r in saved['rows'] if r.get('include_category2') is True
             and r.get('dedupe_target') is None and r.get('status')=='incomplete']
    contents={};fingerprints={};csv_rows={};spans={};headings={}
    def read(name):
        path=(root/name).resolve()
        if not path.is_relative_to(root/'input'):
            raise ValueError('source must remain under input: '+name)
        if name not in contents:
            raw=path.read_bytes();fingerprints[name]=hashlib.sha256(raw).hexdigest()
            contents[name]=raw.decode('utf-8-sig')
        return contents[name]
    def named_starts(name):
        if name not in headings:
            found=[]
            for number,line in enumerate(read(name).splitlines(),1):
                line=line.strip();title=None
                if re.match(r'^#{1,6}\s+',line):title=re.sub(r'^#{1,6}\s+','',line)
                elif line.startswith('| **'):
                    match=re.match(r'\| \*\*(.+?)\*\*',line)
                    if match:title=match[1]
                else:
                    match=re.fullmatch(r'\*\*(.+?)\*\*\s*(?:\[[^\]]+\])?',line)
                    if match and ':' not in match[1] and '：' not in match[1]:title=match[1]
                if title:found.append((number,normalize_source_text(title)))
            headings[name]=found
        return headings[name]
    def span(block):
        if block not in spans:
            match=re.fullmatch(r'(input/[^:]+\.md):(\d+)-(\d+)',block)
            if not match:raise ValueError('invalid saved Book block: '+block)
            name,lo,hi=match[1],int(match[2]),int(match[3]);lines=read(name).splitlines()
            if not 1<=lo<=hi<=len(lines):raise ValueError('invalid saved Book lines: '+block)
            # A broad cached class span cannot combine two adjacent Features.
            starts=[n for n,_ in named_starts(name) if lo<=n<=hi]
            spans[block]=None if len(starts)>1 else normalize_source_text('\n'.join(lines[lo-1:hi]))
        return spans[block]
    def contains(body,cell):
        if body is None:return False
        for match in re.finditer(re.escape(cell),body):
            if cell[0].isdigit() and match.start() and (body[match.start()-1].isdigit() or body[match.start()-1] in '+-−'):continue
            if cell[-1].isdigit() and match.end()<len(body) and body[match.end()].isdigit():continue
            return True
        return False
    results=[]
    for row in pending:
        name=row['file']
        if name not in csv_rows:
            csv_rows[name]=list(csv.reader(io.StringIO(read(name),newline='')))
        if fingerprints[name]!=row['file_sha256']:raise ValueError('CSV source SHA256 mismatch: '+name)
        number=row['csv_record'];columns=row['columns'];rows=csv_rows[name]
        if (type(number) is not int or not 1<=number<=len(rows) or not columns
                or any(type(c) is not int or not 1<=c<=len(rows[number-1]) for c in columns)):
            raise ValueError('invalid CSV logical coordinates: '+row['id'])
        cells=[rows[number-1][c-1].strip() for c in columns]
        if cells!=[c.strip() for c in row['cells']]:raise ValueError('CSV registry cells mismatch: '+row['id'])
        keys=[normalize_source_text(c) for c in cells if c not in ('','-','--')]
        if not keys or any(not c for c in keys):raise ValueError('empty normalized CSV cells: '+row['id'])
        blocks=list(dict.fromkeys([x['block_id'] for x in row.get('literal_md_matches',[])]+row.get('potential_md_blocks',[])))
        matches=[b for b in blocks if all(contains(span(b),c) for c in keys)]
        results.append(dict(id=row['id'],name=row['name'],classification='all_cells_format_match' if matches else 'manual_difference_or_unmapped',
                            matched_blocks=matches,cached_literal=bool(row.get('literal_md_matches'))))
    named=[]
    for path in sorted((root/'input').glob('*.md')):
        name=path.relative_to(root).as_posix();lines=read(name).splitlines();starts=named_starts(name)
        for index,(lo,title) in enumerate(starts):
            hi=starts[index+1][0]-1 if index+1<len(starts) else len(lines)
            # shortcut: >160 lines is a search limit, not a rule or proof of a variant.
            if hi-lo+1<=160:named.append((f'{name}:{lo}-{hi}',title,normalize_source_text('\n'.join(lines[lo-1:hi]))))
    for row,result in zip(pending,results):
        if result['matched_blocks']:continue
        cells=[normalize_source_text(c.strip()) for c in row['cells'] if c.strip() not in ('','-','--')]
        title=normalize_source_text(row['cells'][0].strip())
        matches=[block for block,heading,body in named if title in heading and all(contains(body,c) for c in cells)]
        if matches:result.update(classification='all_cells_named_heading_match',matched_blocks=matches)
    return dict(kind='read_only_csv_book_comparison_not_completion_ledger',denominator=2352,pending_count=len(pending),
                normalization='NFC; presentation Markdown/table tags/quotes/list chevrons/whitespace; en/em/nonbreaking hyphen -> ASCII hyphen. Signs, numerals, words, negation and slash preserved. All cells in one bounded Book block means source candidate only; human completeness/current-proof review remains required.',
                source_sha256=fingerprints,registry_sha256=hashlib.sha256(registry_raw).hexdigest(),
                summary=dict(Counter(r['classification'] for r in results)),rows=results,
                heading_recheck=dict(named_blocks=len(named),new_matches=sum(r['classification']=='all_cells_named_heading_match' for r in results),
                                     boundary='Standalone bold, Markdown or table-name heading to next named heading; >160 lines excluded. A miss is not a proven source variant.'))


if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser(description='Read-only CSV/Book source candidates; never completion or variant adjudication.')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--compare-csv-book',action='store_true',required=True)
    parser.add_argument('--registry',type=Path)
    parser.add_argument('--output',type=Path,help='New JSON only under the private D revision-scratch directory; default stdout.')
    args=parser.parse_args()
    if args.output:
        private=(args.root.resolve().parent/'work/revision-scratch-20261024').resolve();target=args.output.resolve()
        if (not args.output.is_absolute() or target.drive.lower()!='d:' or not target.is_relative_to(private)
                or target==private or target.exists()):parser.error('--output must be a new private D scratch file')
    result=json.dumps(compare_csv_book(args.root,args.registry),ensure_ascii=False,indent=2)+'\n'
    if args.output:
        with target.open('x',encoding='utf-8') as stream:stream.write(result)
    else:print(result,end='')
