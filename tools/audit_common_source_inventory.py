"""Physical source inventory. Exhaustive line accounting is not semantic coverage."""
import argparse,hashlib,json,re
from pathlib import Path
from collections import Counter

def sha(data):return hashlib.sha256(data).hexdigest()
def build(root):
    files=[];blocks=[]
    for p in sorted((root/'input').rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(root).as_posix();row=dict(file=rel,sha256=sha(p.read_bytes()),bytes=p.stat().st_size,semantic_scope='pending')
        files.append(row)
        if p.suffix!='.md':row['format_review']='External/tabular input; semantic inventory pending';continue
        lines=p.read_text(encoding='utf-8').splitlines();row['lines']=len(lines);section=[];i=0
        while i<len(lines):
            if not lines[i].strip():i+=1;continue
            start=i;h=re.match(r'^(#{1,6})\s*(.*)$',lines[i])
            if h:
                level=len(h[1]);section=[s for s in section if s['level']<level]+[dict(level=level,title=h[2],line=i+1)];i+=1;kind='heading'
            else:
                while i<len(lines) and lines[i].strip() and not re.match(r'^#{1,6}\s',lines[i]):i+=1
                kind='table' if any(l.lstrip().startswith(('|','<table','</table')) for l in lines[start:i]) else 'prose'
            excerpt='\n'.join(lines[start:i]);flags=[]
            if re.search(r'!\[|<img|\[img\]|\[이미지|image\s*:',excerpt,re.I):flags.append('image_candidate')
            if re.search(r'참조|챕터|페이지|chapter|page\s*\d',excerpt,re.I):flags.append('cross_reference_candidate')
            blocks.append(dict(id=f'{rel}:{start+1}-{i}',file=rel,start=start+1,end=i,kind=kind,section_path=[s['title'] for s in section],excerpt_sha256=sha(excerpt.encode()),flags=flags,semantic_review='pending'))
    return dict(version=1,scope='All files currently saved under input; Markdown nonblank spans only. Original Drive completeness and semantic common-rule scope are unverified.',files=files,blocks=blocks,image_placeholders=sum((root/f['file']).read_text(encoding='utf-8').count('[img]') for f in files if f['file'].endswith('.md')),source_clause_total=None,semantic_coverage_percent=None)

def validate(inventory,root):
    errors=[];paths={p.relative_to(root).as_posix():p for p in (root/'input').rglob('*') if p.is_file()}
    files=inventory.get('files',[]);names=[f['file'] for f in files]
    if set(names)!=set(paths) or len(names)!=len(set(names)):errors.append('input_file_set_mismatch')
    blocks=inventory.get('blocks',[]);ids=[b['id'] for b in blocks]
    if len(ids)!=len(set(ids)):errors.append('duplicate_source_block')
    for f in files:
        p=paths.get(f['file'])
        if p is None:continue
        if sha(p.read_bytes())!=f['sha256']:errors.append('source_file_changed:'+f['file'])
        if p.suffix!='.md':continue
        lines=p.read_text(encoding='utf-8').splitlines();seen=Counter()
        for b in [b for b in blocks if b['file']==f['file']]:
            a,z=b['start'],b['end']
            if not 1<=a<=z<=len(lines):errors.append('invalid_source_span:'+b['id']);continue
            seen.update(range(a,z+1))
            if sha('\n'.join(lines[a-1:z]).encode())!=b['excerpt_sha256']:errors.append('source_block_changed:'+b['id'])
        if {i for i,l in enumerate(lines,1) if l.strip()}!={i for i,c in seen.items() if c==1}:errors.append('nonblank_line_partition_mismatch:'+f['file'])
        if any(c>1 for c in seen.values()):errors.append('overlapping_source_blocks:'+f['file'])
    for b in blocks:
        if b['file'] not in paths:errors.append('unknown_source_block_file:'+b['id'])
    return errors

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--refresh',action='store_true');args=ap.parse_args();root=Path(__file__).resolve().parents[1]
    target=root/'data/verification/common-source-inventory.json'
    if args.refresh:target.write_text(json.dumps(build(root),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    inv=json.loads(target.read_text(encoding='utf-8'));errors=validate(inv,root)
    report=dict(status='pass' if not errors else 'fail',errors=errors,files=len(inv['files']),markdown_files=sum(f['file'].endswith('.md') for f in inv['files']),blocks=len(inv['blocks']),image_placeholders=inv.get('image_placeholders'),block_kinds=dict(Counter(b['kind'] for b in inv['blocks'])),flagged_blocks=dict(Counter(flag for b in inv['blocks'] for flag in b['flags'])),common_clause_total=None,meaning='Physical snapshot accounting only; no semantic completeness claim.')
    (root/'output/whole-rulebook-audit/common-source-inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
