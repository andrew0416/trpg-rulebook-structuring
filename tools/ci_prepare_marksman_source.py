"""Derive one missing source input from the already authenticated Core PDF."""
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import json
import logging
from pathlib import Path
import warnings

PDF_PATH = 'source-audit/ptu-core-1.05.pdf'
PDF_SHA256 = 'e5e0371031601c3ad0a04056771c17599a2d8826e5a5102ccd37f9b368108907'
PDF_SIZE = 12661816
OUTPUT_PATH = 'source-audit/core-marksman-sniper.txt'
OUTPUT_SHA256 = '8511072e84b04527f2a965651f401f3475a158b911cebd7a4b77829c842bda1e'
OUTPUT_SIZE = 148
PYPDF_VERSION = '6.21.2'
NORMALIZATION = 'sniper-two-line-v1'
HEADING = 'Ability: Sniper'


class SourcePreparationError(ValueError):
    def __init__(self, report):
        self.safe_report = dict(report)
        super().__init__(report['status'])


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _stage_path(stage, name):
    path = stage / name
    if not path.resolve().is_relative_to(stage):
        raise ValueError('source_path_leaves_stage')
    for part in (path, *path.parents):
        if part == stage:
            break
        if part.is_symlink():
            raise ValueError('source_path_is_symlink')
    return path


def _line(text):
    return ' '.join(text.split())


def _heading_lines(text):
    return [index for index, line in enumerate(text.splitlines()) if _line(line) == HEADING]


def _excerpt(text, heading_line):
    lines = text.splitlines()
    if _line(lines[heading_line]) != HEADING:
        raise ValueError('source_heading_changed')
    parts, used = [], []
    for index in range(heading_line + 1, len(lines)):
        line = _line(lines[index])
        if not line:
            if parts and parts != ['Static']:
                break
            continue
        if line.startswith('Ability:'):
            break
        parts.append(line)
        used.append(index)
    paragraph = ' '.join(parts)
    if not paragraph.startswith('Static Effect: ') or not used:
        raise ValueError('source_static_paragraph_missing')
    # shortcut: one adjacent page paragraph; a cross-page body needs source review.
    body = (_line(lines[heading_line]) + '\n' + paragraph + '\n').encode('utf-8')
    return body, used


def _reader(path):
    import pypdf
    if pypdf.__version__ != PYPDF_VERSION:
        raise ValueError('source_extractor_version_mismatch')
    return pypdf.PdfReader(str(path))


def prepare_stage(stage, manifest, hashes, output):
    """Run only after authenticated restore, before freezing native input hashes.

    Private pages, candidate bytes, provenance and parser diagnostics use root
    *.log files, already included by ci_validate.encrypt_evidence. Never print.
    """
    stage, output = Path(stage).resolve(), Path(output).resolve()
    report = dict(status='preparing', source_path=PDF_PATH, source_sha256=PDF_SHA256,
                  source_size=PDF_SIZE, output_path=OUTPUT_PATH,
                  expected_sha256=OUTPUT_SHA256, expected_size=OUTPUT_SIZE,
                  extractor='pypdf', required_extractor_version=PYPDF_VERSION,
                  normalization=NORMALIZATION, heading_count=0, pages_scanned=0,
                  page_indexes=[])
    provenance = dict(normalization={
        'id': NORMALIZATION,
        'reader': 'PdfReader(path).pages[index].extract_text() or empty string',
        'heading': 'one exact normalized Ability heading; scan every actual page',
        'paragraph': 'adjacent Static Effect paragraph, end at blank line/next Ability/page end',
        'whitespace': 'split whitespace and join with ASCII space, retaining all words',
        'encoding': 'UTF-8 without BOM; heading LF paragraph LF; no punctuation or body edits',
    }, pages=[])

    def fail(status):
        report['status'] = status
        raise SourcePreparationError(report)

    try:
        rows = [row for row in manifest['files'] if row['path'] == PDF_PATH]
        if rows != [dict(path=PDF_PATH, sha256=PDF_SHA256, size=PDF_SIZE)] or hashes.get(PDF_PATH) != PDF_SHA256:
            fail('source_not_authenticated')
        if OUTPUT_PATH in hashes or any(row['path'].casefold() == OUTPUT_PATH.casefold() for row in manifest['files']):
            fail('derived_input_already_declared')
        source, target = _stage_path(stage, PDF_PATH), _stage_path(stage, OUTPUT_PATH)
        if target.exists():
            fail('derived_input_already_exists')
        if source.stat().st_size != PDF_SIZE:
            fail('source_size_mismatch')
        with source.open('rb') as stream:
            report['actual_source_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        if report['actual_source_sha256'] != PDF_SHA256:
            fail('source_digest_mismatch')

        headings = []
        logger = logging.getLogger('pypdf')
        previous = logger.handlers[:], logger.propagate, logger.level
        with (output / 'marksman-source-parser.log').open('x', encoding='utf-8', newline='\n') as log:
            handler = logging.StreamHandler(log)
            logger.handlers, logger.propagate, logger.level = [handler], False, logging.WARNING
            try:
                with redirect_stdout(log), redirect_stderr(log), warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    try:
                        reader = _reader(source)
                        report['extractor_version'] = PYPDF_VERSION
                        report['page_count'] = len(reader.pages)
                        for page_index, page in enumerate(reader.pages):
                            report['active_page_index'] = page_index
                            text = page.extract_text() or ''
                            page_sha = _sha(text.encode('utf-8'))
                            positions = _heading_lines(text)
                            provenance['pages'].append(dict(page_index=page_index, page_text_sha256=page_sha,
                                                            heading_lines=positions))
                            report['pages_scanned'] += 1
                            if positions:
                                with (output / f'marksman-source-page-{page_index:04d}.log').open('x', encoding='utf-8', newline='\n') as raw:
                                    raw.write(text)
                                headings.extend((page_index, position, text, page_sha) for position in positions)
                                report['heading_count'] = len(headings)
                                report['page_indexes'] = sorted({item[0] for item in headings})
                    finally:
                        for warning in caught:
                            log.write(warnings.formatwarning(warning.message, warning.category,
                                                             warning.filename, warning.lineno))
            finally:
                logger.handlers, logger.propagate, logger.level = previous
        if not headings:
            fail('heading_missing')
        if len(headings) != 1:
            fail('heading_ambiguous')
        page_index, position, text, page_sha = headings[0]
        report.update(page_index=page_index, page_text_sha256=page_sha)
        try:
            body, used = _excerpt(text, position)
        except (ValueError, IndexError):
            fail('paragraph_missing_or_unsupported')
        provenance['selected'] = dict(page_index=page_index, heading_line=position,
                                      paragraph_lines=used, page_text_sha256=page_sha)
        with (output / 'marksman-source-candidate.log').open('xb') as raw:
            raw.write(body)
        report.update(output_sha256=_sha(body), output_size=len(body))
        if len(body) != OUTPUT_SIZE or report['output_sha256'] != OUTPUT_SHA256:
            fail('derived_identity_mismatch')
        with target.open('xb') as stream:
            stream.write(body)
        with target.open('rb') as stream:
            written_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
        if written_sha256 != report['output_sha256']:
            fail('derived_write_mismatch')
        hashes[OUTPUT_PATH] = written_sha256
        report['status'] = 'prepared'
        return dict(report)
    except SourcePreparationError:
        raise
    except Exception as exc:
        report['status'] = 'source_preparation_error'
        raise SourcePreparationError(report) from exc
    finally:
        provenance['report'] = report
        with (output / 'marksman-source-provenance.log').open('x', encoding='utf-8', newline='\n') as log:
            json.dump(provenance, log, ensure_ascii=False, indent=2)
            log.write('\n')
