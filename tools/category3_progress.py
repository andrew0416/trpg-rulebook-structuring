"""Count verified survey IDs, never implementation files, tests or RuleUnits."""
import argparse
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def stable_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()

def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Evidence must stay inside the project')
    return path

def calculate(root, ledger):
    entries = ledger['entries']
    ids = [e['id'] for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate clause ID')
    known = set()
    history = ledger['scope_history']
    if not history or history[0]['revision'] != 1 or len(history[0]['added_ids']) != 352:
        raise ValueError('The approved original baseline must remain 352 IDs')
    for number, revision in enumerate(history, 1):
        additions = revision['added_ids']
        if revision['revision'] != number or revision.get('removed_ids'):
            raise ValueError('Scope revisions must be consecutive and preserve previous IDs')
        if len(additions) != len(set(additions)) or known.intersection(additions):
            raise ValueError('Scope addition repeats an existing ID')
        known.update(additions)
        if revision['denominator'] != len(known):
            raise ValueError('Scope denominator does not match the revision history')
    if known != set(ids):
        raise ValueError('Scope history and clause list differ')
    reports, hashes, counts, details = {}, {}, Counter(), []
    def current_hash(relative):
        if relative not in hashes:
            path = inside(root, relative)
            hashes[relative] = fingerprint(path) if path.is_file() else None
        return hashes[relative]
    for entry in entries:
        if stable_hash(entry['source_snapshot']) != entry['scope_sha256']:
            raise ValueError('Source scope snapshot changed: ' + entry['id'])
        status = entry['status']
        if status not in ('pending', 'partial', 'deferred', 'completed'):
            raise ValueError('Unknown clause status: ' + status)
        reasons = []
        if status == 'completed':
            review = entry.get('review', {})
            evidence = entry.get('evidence', {})
            if not review.get('full_scope_verified') or review.get('remaining_obligations'):
                reasons.append('full scope review is incomplete')
            if not entry.get('implementation', {}).get('symbols'):
                reasons.append('no runtime implementation reference')
            required = evidence.get('required_tests', [])
            required_files = evidence.get('required_files', [])
            if not required or not required_files or not evidence.get('report'):
                reasons.append('missing verification evidence')
            else:
                report_name = evidence['report']
                if report_name not in reports:
                    path = inside(root, report_name)
                    reports[report_name] = json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
                report = reports[report_name]
                outcomes = {r['id']: r['status'] for r in report.get('results', [])}
                if report.get('successful') is not True or any(outcomes.get(t) != 'pass' for t in required):
                    reasons.append('required tests are missing or failed')
                input_hashes = report.get('input_hashes', {})
                if not set(required_files).issubset(input_hashes):
                    reasons.append('required dependency fingerprints are missing')
                if any(current_hash(p) != h for p, h in input_hashes.items()):
                    reasons.append('evidence is stale: source, implementation or tests changed')
            if reasons:
                status = 'needs_reverification'
        counts[status] += 1
        details.append({'id': entry['id'], 'status': status, 'reasons': reasons})
    total, completed = len(entries), counts['completed']
    def percent(value):
        return format((Decimal(value) * 100 / Decimal(total)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), 'f')
    return {
        'scope': 'category3', 'scope_revision': history[-1]['revision'],
        'denominator': total, 'completed': completed,
        'completion_fraction': f'{completed}/{total}',
        'completion_percent': percent(completed),
        'not_completed': total - completed,
        'remaining_percent': percent(total - completed),
        'counts': dict(sorted(counts.items())),
        'meaning': 'Completed = entire existing survey-ID scope implemented and verified with current evidence. Pending may already have code but has not been certified. Partial counts as zero.',
        'entries': details,
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--ledger', default='data/verification/category3-register.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    ledger = json.loads(inside(args.root, args.ledger).read_text(encoding='utf-8-sig'))
    report = calculate(args.root, ledger)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'entries'}, ensure_ascii=False, indent=2))
    return 1 if report['counts'].get('needs_reverification') else 0

if __name__ == '__main__':
    raise SystemExit(main())

