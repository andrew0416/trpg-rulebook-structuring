"""Audit stated common skill probabilities using exact finite dice distributions."""
import hashlib,json,re
from collections import Counter
from fractions import Fraction
from pathlib import Path
RANKS={'불능':1,'미숙':2,'초보':3,'숙련':4,'전문':5,'달인':6}

def distribution(rank):
    if type(rank) is not int or not 1<=rank<=6:raise ValueError('Base rank must be 1..6')
    dist=Counter({0:1})
    for _ in range(rank):
        nxt=Counter()
        for total,count in dist.items():
            for face in range(1,7):nxt[total+face]+=count
        dist=nxt
    return dist

def probability(rank,dc,modifier=0):
    """Read the +0 distribution at DC-minus-modifier, without changing play DC."""
    if type(dc) is not int or type(modifier) is not int:raise ValueError('integer DC and modifier required')
    dc=dc-modifier
    dist=distribution(rank)
    return Fraction(sum(n for total,n in dist.items() if total>=dc),6**rank)

def parse_claims(text,dc,line):
    out=[]
    pattern=r'(불능|미숙|초보|숙련|전문|달인)\s*(이상)?\s*(?:에서|은|는)?\s*(?:(\d+(?:\.\d+)?)%\s*(이상|미만)?|(불가능))'
    for m in re.finditer(pattern,text):
        name,up,value,relation,impossible=m.groups();ranks=range(RANKS[name],7) if up else [RANKS[name]]
        for rank in ranks:
            out.append(dict(id=f'SKILL-PROB-L{line}-DC{dc}-R{rank}',line=line,dc=dc,rank=rank,claim=m[0],stated=value or '0',relation='zero' if impossible else 'ge' if relation=='이상' else 'lt' if relation=='미만' else 'approx'))
    return out

def agrees(claim,actual):
    stated=Fraction(claim['stated'])/100
    if claim['relation']=='zero':return actual==0
    if claim['relation']=='ge':return actual>=stated
    if claim['relation']=='lt':return actual<stated
    # Explicit display convention: truncation OR nearest half-up at printed
    # precision. A symmetric one-unit epsilon wrongly admits numbers that
    # neither rendering can produce (e.g. 49.91% as 50.0%).
    digits=len(claim['stated'].partition('.')[2]);scale=10**digits
    scaled=actual*100*scale
    truncated=scaled.numerator//scaled.denominator
    nearest=(2*scaled.numerator+scaled.denominator)//(2*scaled.denominator)
    return stated*100*scale in (truncated,nearest)

def audit(root, *, include_annotations=True):
    file='input/ch11-running-the-game.md';lines=(root/file).read_text(encoding='utf-8').splitlines();claims=[]
    # Fixed source spans are intentional: changed text requires re-review, not silent relocation.
    claims.extend(parse_claims(lines[1438],10,1439))
    chunks=re.split(r'\*\*DC\s*',lines[1440])[1:]
    for chunk in chunks:
        dc=int(re.match(r'\d+',chunk)[0]);claims.extend(parse_claims(chunk,dc,1441))
    if len(claims)!=54:raise ValueError(f'Expected 54 explicit rank claims, found {len(claims)}; review source parser')
    results=[]
    for c in claims:
        actual=probability(c['rank'],c['dc']);results.append(dict(**c,source=dict(file=file,line=c['line'],excerpt_sha256=hashlib.sha256(lines[c['line']-1].encode()).hexdigest()),status='consistent' if agrees(c,actual) else 'source_arithmetic_conflict',exact_probability=dict(numerator=actual.numerator,denominator=actual.denominator),calculated_percent=float(actual*100)))
    report=dict(status='source_conflicts' if any(c['status']!='consistent' for c in results) else 'pass',model='Independent uniform d6; rank k -> k dice; sum>=DC; no modifier. DC14 with +4 is compared as DC10.',model_source_spans=[dict(file='input/ch03-skills-edges-feats.md',start=22,end=30),dict(file='input/ch06-gameplay.md',start=23,end=23)],assumptions=['Fair independent dice (explicit mathematical assumption)','Published percentages are approximations at printed precision'],claims=results,conflicts=[c['id'] for c in results if c['status']!='consistent'],meaning='Arithmetic comparison to saved source. Original text is preserved; conflicting guidance remains unresolved for certification.')
    artifact=root/'data/verification/common-probability-corrections.json'
    if include_annotations and artifact.exists():
        annotations=json.loads(artifact.read_text(encoding='utf-8'))
        errors=validate_annotations(root,annotations,report)
        report['derived_annotations']={'file':artifact.relative_to(root).as_posix(),
            'status':'verified' if not errors else 'invalid','errors':errors,
            'unique_corrections':len(annotations.get('corrections',[])),
            'arithmetic_derivations_verified':not errors,
            'raw_source_agreement':False,
            'corrected_guidance':[{'id':c['id'],'rank':c['rank'],'dc':c['dc'],'stated':c['source_stated'],'claim_ids':c['claim_ids'],'exact_derived':c['derived']} for c in annotations.get('corrections',[])] if not errors else [],
            'meaning':'Exact derived values are separate from original source; raw source conflicts remain.'}
    return report


def validate_annotations(root,annotations,report=None):
    report=report or audit(root,include_annotations=False)
    errors=[]
    if annotations.get('source_arithmetic_conflicts_resolved') is not False:errors.append('false_source_resolution_claim')
    if annotations.get('semantic_closure') is not False:errors.append('false_semantic_closure_claim')
    if annotations.get('model',{}).get('check')!='sum(dice)+modifier >= DC':errors.append('model_comparator_changed')
    required={'rank_dice','inclusive_success','equality_example','probability_context','PTU-219','PTU-220','PTU-465'}
    if set(annotations.get('source_anchors',{}))!=required:errors.append('source_anchor_set_mismatch')
    raw={c['id']:c for c in report['claims'] if c['status']!='consistent'}
    seen=[]
    for c in annotations.get('corrections',[]):
        ids=c.get('claim_ids',[]);seen.extend(ids)
        if not ids:errors.append('empty_correction_locations')
        for cid in ids:
            actual=raw.get(cid)
            if actual is None:errors.append('not_a_current_conflict:'+cid);continue
            for key,rawkey in [('rank','rank'),('dc','dc'),('source_stated','stated')]:
                if c.get(key)!=actual[rawkey]:errors.append('changed_claim:'+cid+':'+key)
            if c.get('derived',{}).get('numerator')!=actual['exact_probability']['numerator'] or c.get('derived',{}).get('denominator')!=actual['exact_probability']['denominator']:
                errors.append('incorrect_derived_fraction:'+cid)
            exact=Fraction(actual['exact_probability']['numerator'],actual['exact_probability']['denominator'])*100
            if c.get('derived',{}).get('percent_exact')!=f'{exact.numerator}/{exact.denominator}':errors.append('incorrect_derived_percent:'+cid)
            rendered=(2*exact.numerator*100+exact.denominator)//(2*exact.denominator)
            try:display_ok=Fraction(c['derived']['display_percent_2dp'])*100==rendered
            except (KeyError,ValueError,ZeroDivisionError):display_ok=False
            if not display_ok:errors.append('incorrect_derived_display:'+cid)
            location=next((x for x in c.get('locations',[]) if x.get('line')==actual['line']),None)
            if location is None or any(location.get(k)!=actual['source'].get(k) for k in ('file','excerpt_sha256')) or location.get('claim')!=actual['claim']:
                errors.append('changed_source_location:'+cid)
        if c.get('source_preserved') is not True:errors.append('source_preservation_missing')
    if set(seen)!=set(raw):errors.append('conflict_set_mismatch')
    if len(seen)!=len(set(seen)):errors.append('duplicate_conflict_annotation')
    for key,a in annotations.get('source_anchors',{}).items():
        path=root/a['file']
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=a.get('file_sha256'):errors.append('source_file_hash:'+key);continue
        if hashlib.sha256(a.get('excerpt','').encode()).hexdigest()!=a.get('excerpt_sha256'):errors.append('excerpt_hash:'+key)
        if 'start' in a:
            current='\n'.join(path.read_text(encoding='utf-8').splitlines()[a['start']-1:a['end']])
            if current!=a['excerpt']:errors.append('source_excerpt:'+key)
    return errors


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1];report=audit(root)
    report['input_hashes']={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in ['tools/audit_common_probabilities.py','input/ch03-skills-edges-feats.md','input/ch06-gameplay.md','input/ch11-running-the-game.md']}
    artifact=root/'data/verification/common-probability-corrections.json'
    if artifact.exists():
        report['input_hashes'][artifact.relative_to(root).as_posix()]=hashlib.sha256(artifact.read_bytes()).hexdigest()
        annotations=json.loads(artifact.read_text(encoding='utf-8'))
        for anchor in annotations['source_anchors'].values():
            report['input_hashes'][anchor['file']]=hashlib.sha256((root/anchor['file']).read_bytes()).hexdigest()
    (root/'output/whole-rulebook-audit').mkdir(parents=True,exist_ok=True)
    (root/'output/whole-rulebook-audit/common-probability-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['status'],claims=len(report['claims']),conflicts=[dict(id=c['id'],stated=c['stated'],calculated_percent=c['calculated_percent']) for c in report['claims'] if c['status']!='consistent']),ensure_ascii=False))
    raise SystemExit(1 if report['conflicts'] or report.get('derived_annotations',{}).get('errors') else 0)
