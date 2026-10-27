"""Synthetic preparation boundaries only; no rule body or real PDF fixture."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import logging
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci_prepare_marksman_source as P


class MarksmanSourcePreparationTests(unittest.TestCase):
    PAGE = 'Ability: Sniper\nStatic\nEffect: synthetic input\nparagraph.\n\nAbility: Other\n'
    BODY = b'Ability: Sniper\nStatic Effect: synthetic input paragraph.\n'

    @contextmanager
    def environment(self, pages):
        with tempfile.TemporaryDirectory(prefix='source-preparation-synthetic-') as directory:
            root = Path(directory)
            stage, output = root / 'stage', root / 'evidence'
            (stage / 'source-audit').mkdir(parents=True)
            output.mkdir()
            source_bytes = b'synthetic PDF identity; reader is stubbed, not a game fixture'
            (stage / P.PDF_PATH).write_bytes(source_bytes)
            source_sha = hashlib.sha256(source_bytes).hexdigest()
            body_sha = hashlib.sha256(self.BODY).hexdigest()
            manifest = {'version': 1, 'files': [dict(path=P.PDF_PATH, size=len(source_bytes), sha256=source_sha)]}
            hashes = {P.PDF_PATH: source_sha}
            reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=Mock(return_value=text)) for text in pages])
            with patch.multiple(P, PDF_SHA256=source_sha, PDF_SIZE=len(source_bytes),
                                OUTPUT_SHA256=body_sha, OUTPUT_SIZE=len(self.BODY)), \
                 patch.object(P, '_reader', return_value=reader) as open_reader:
                yield stage, output, manifest, hashes, open_reader

    def test_normalizes_only_actual_heading_and_adjacent_paragraph_to_two_lf_lines(self):
        body, used = P._excerpt('front\n Ability:\tSniper \n\nStatic\n\nEffect:  synthetic\tinput\nparagraph.\n\nfooter', 1)
        self.assertEqual(body, self.BODY)
        self.assertEqual(body.count(b'\n'), 2)
        self.assertNotIn(b'\r', body)
        self.assertFalse(body.startswith(b'\xef\xbb\xbf'))
        self.assertTrue(used)
        self.assertEqual(P._heading_lines('Ability: Sniper (index)\nSee Ability: Sniper\nAbility: Sniper\n'), [2])
        with self.assertRaises(ValueError):
            P._excerpt('Ability: Sniper\nFrequency: Daily\nEffect: synthetic.\n', 0)

    def test_unique_actual_page_is_recorded_and_derived_input_is_frozen_without_overwriting_source(self):
        with self.environment(['no heading', 'also no heading', self.PAGE]) as (stage, output, manifest, hashes, reader):
            before = (stage / P.PDF_PATH).read_bytes()
            report = P.prepare_stage(stage, manifest, hashes, output)
            self.assertEqual(report['status'], 'prepared')
            self.assertEqual((stage / P.OUTPUT_PATH).read_bytes(), self.BODY)
            self.assertEqual(hashes[P.OUTPUT_PATH], report['output_sha256'])
            self.assertEqual((stage / P.PDF_PATH).read_bytes(), before)
            self.assertEqual((report['page_index'], report['pages_scanned'], report['heading_count']), (2, 3, 1))
            private = json.loads((output / 'marksman-source-provenance.log').read_text(encoding='utf-8'))
            self.assertEqual(private['selected']['page_index'], 2)
            self.assertEqual(len(private['pages']), 3)
            self.assertEqual((output / 'marksman-source-page-0002.log').read_text(encoding='utf-8'), self.PAGE)
            self.assertEqual((output / 'marksman-source-candidate.log').read_bytes(), self.BODY)
            reader.assert_called_once()

    def test_missing_or_ambiguous_actual_heading_fails_without_output_even_if_one_candidate_matches(self):
        for pages, status in ((['no heading'], 'heading_missing'),
                              ([self.PAGE, self.PAGE], 'heading_ambiguous')):
            with self.subTest(status=status), self.environment(pages) as (stage, output, manifest, hashes, _):
                with self.assertRaises(P.SourcePreparationError) as caught:
                    P.prepare_stage(stage, manifest, hashes, output)
                self.assertEqual(caught.exception.safe_report['status'], status)
                self.assertNotIn(P.OUTPUT_PATH, hashes)
                self.assertFalse((stage / P.OUTPUT_PATH).exists())
                self.assertTrue((output / 'marksman-source-provenance.log').is_file())

    def test_mismatch_reports_only_safe_metadata_and_keeps_parser_noise_and_actual_candidate_private(self):
        marker = 'PRIVATE_SYNTHETIC_TEXT_MUST_NOT_LEAVE'
        page = 'Ability: Sniper\nStatic Effect: ' + marker + '.\n'
        with self.environment([page]) as (stage, output, manifest, hashes, reader):
            actual_reader = reader.return_value
            def noisy_reader(path):
                print(marker)
                print(marker, file=sys.stderr)
                logging.getLogger('pypdf.synthetic').warning(marker)
                warnings.warn(marker)
                return actual_reader
            reader.side_effect = noisy_reader
            public_stdout, public_stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(public_stdout), redirect_stderr(public_stderr):
                with self.assertRaises(P.SourcePreparationError) as caught:
                    P.prepare_stage(stage, manifest, hashes, output)
            report = caught.exception.safe_report
            self.assertEqual(report['status'], 'derived_identity_mismatch')
            self.assertEqual(report['page_index'], 0)
            self.assertIn('output_sha256', report)
            self.assertNotIn(marker, json.dumps(report) + str(caught.exception))
            self.assertEqual(public_stdout.getvalue() + public_stderr.getvalue(), '')
            self.assertIn(marker, (output / 'marksman-source-parser.log').read_text(encoding='utf-8'))
            self.assertIn(marker.encode(), (output / 'marksman-source-candidate.log').read_bytes())
            self.assertFalse((stage / P.OUTPUT_PATH).exists())
            self.assertNotIn(P.OUTPUT_PATH, hashes)

    def test_missing_authenticated_binding_or_changed_pdf_refuses_before_extraction(self):
        for changed_bytes in (False, True):
            with self.subTest(changed_bytes=changed_bytes), self.environment([self.PAGE]) as (stage, output, manifest, hashes, reader):
                if changed_bytes:
                    source = stage / P.PDF_PATH
                    body = source.read_bytes()
                    source.write_bytes(b'X' + body[1:])
                    expected = 'source_digest_mismatch'
                else:
                    hashes.clear()
                    expected = 'source_not_authenticated'
                with self.assertRaises(P.SourcePreparationError) as caught:
                    P.prepare_stage(stage, manifest, hashes, output)
                self.assertEqual(caught.exception.safe_report['status'], expected)
                reader.assert_not_called()
                self.assertFalse((stage / P.OUTPUT_PATH).exists())

    def test_existing_or_manifest_declared_output_is_never_overwritten(self):
        for declared in (False, True):
            with self.subTest(declared=declared), self.environment([self.PAGE]) as (stage, output, manifest, hashes, reader):
                target = stage / P.OUTPUT_PATH
                target.write_bytes(b'preexisting synthetic source')
                if declared:
                    manifest['files'].append(dict(path=P.OUTPUT_PATH, sha256='0' * 64, size=0))
                with self.assertRaises(P.SourcePreparationError) as caught:
                    P.prepare_stage(stage, manifest, hashes, output)
                self.assertEqual(caught.exception.safe_report['status'],
                                 'derived_input_already_declared' if declared else 'derived_input_already_exists')
                self.assertEqual(target.read_bytes(), b'preexisting synthetic source')
                reader.assert_not_called()

    def test_unpinned_extractor_version_is_refused(self):
        stub = SimpleNamespace(__version__='unreviewed', PdfReader=Mock())
        with patch.dict(sys.modules, {'pypdf': stub}), self.assertRaises(ValueError):
            P._reader(Path('not-opened.pdf'))
        stub.PdfReader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
