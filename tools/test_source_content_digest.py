"""Digest reuse never replaces a current path/boundary/read/byte comparison."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib,importlib.util,os,sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
import source_context as SOURCE


class SourceContentDigestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='source-digest-',dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'input').mkdir();(self.root/'source-audit').mkdir()
        self.rules=SimpleNamespace(root=str(self.root))
        self.path=self.root/'input/source.md';self.path.write_bytes(b'original source bytes')
        self.reference={'file':'input/source.md','sha256':sha256(self.path.read_bytes()).hexdigest()}
        SOURCE._content_sha256.cache_clear()

    def test_each_cache_hit_still_resolves_both_paths_and_reads_current_bytes(self):
        resolves=[];reads=[];resolve=Path.resolve;read=Path.read_bytes
        def observed_resolve(path,*args,**kwargs):
            if sys._getframe(1).f_code is SOURCE.verified_source.__code__:resolves.append(path)
            return resolve(path,*args,**kwargs)
        def observed_read(path):reads.append(path);return read(path)
        with patch.object(Path,'resolve',observed_resolve),patch.object(Path,'read_bytes',observed_read):
            for _ in range(2):self.assertEqual(SOURCE.verified_source(self.rules,self.reference),b'original source bytes')
        self.assertEqual(reads,[self.path,self.path])
        self.assertEqual(resolves,[self.path,self.root/'input',self.path,self.root/'input'])
        if SOURCE._NATIVE_SHA256 is not None:
            self.assertEqual(SOURCE._content_sha256.cache_info().hits,1)

    def test_same_size_same_mtime_single_byte_change_is_rejected(self):
        SOURCE.verified_source(self.rules,self.reference);before=self.path.stat()
        self.path.write_bytes(b'Original source bytes');os.utime(self.path,ns=(before.st_atime_ns,before.st_mtime_ns))
        self.assertEqual(self.path.stat().st_size,before.st_size);self.assertEqual(self.path.stat().st_mtime_ns,before.st_mtime_ns)
        with self.assertRaisesRegex(ValueError,'source changed'):SOURCE.verified_source(self.rules,self.reference)
        changed=dict(self.reference,sha256=sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(SOURCE.verified_source(self.rules,changed),b'Original source bytes')

    def test_wrong_expected_digest_is_rejected_even_for_already_cached_content(self):
        SOURCE.verified_source(self.rules,self.reference)
        with self.assertRaisesRegex(ValueError,'source changed'):
            SOURCE.verified_source(self.rules,dict(self.reference,sha256='0'*64))

    def test_patched_hasher_is_called_each_time_instead_of_using_cached_digest(self):
        SOURCE.verified_source(self.rules,self.reference)
        with patch.object(hashlib,'sha256',wraps=sha256) as hasher:
            for _ in range(2):SOURCE.verified_source(self.rules,self.reference)
        self.assertEqual(hasher.call_count,2)

    def test_custom_hasher_present_at_module_load_also_keeps_its_callbacks(self):
        try:import _hashlib
        except ImportError:self.skipTest('OpenSSL constructor unavailable')
        calls=[]
        def custom(content):calls.append(content);return sha256(content)
        spec=importlib.util.spec_from_file_location('_source_digest_custom_import',SOURCE.__file__)
        other=importlib.util.module_from_spec(spec)
        with patch.object(_hashlib,'openssl_sha256',custom),patch.object(hashlib,'sha256',custom):
            spec.loader.exec_module(other)
            self.assertIsNone(other._NATIVE_SHA256)
            for _ in range(2):other.verified_source(self.rules,self.reference)
        self.assertEqual(calls,[b'original source bytes']*2)
        self.assertEqual(other._content_sha256.cache_info().currsize,0)

    def test_bytes_subclasses_keep_direct_digest_path(self):
        class Content(bytes):
            def __hash__(self):raise AssertionError('custom bytes must not become cache keys')
        content=Content(b'original source bytes')
        with patch.object(Path,'read_bytes',return_value=content):
            for _ in range(2):self.assertIs(SOURCE.verified_source(self.rules,self.reference),content)
        self.assertEqual(SOURCE._content_sha256.cache_info().currsize,0)

    def test_large_content_bypasses_cache_and_entry_count_is_bounded(self):
        self.path.write_bytes(b'x'*(1024*1024+1))
        reference=dict(self.reference,sha256=sha256(self.path.read_bytes()).hexdigest())
        for _ in range(2):SOURCE.verified_source(self.rules,reference)
        self.assertEqual(SOURCE._content_sha256.cache_info().currsize,0)
        for index in range(20):
            content=bytes([index]);self.path.write_bytes(content)
            SOURCE.verified_source(self.rules,dict(reference,sha256=sha256(content).hexdigest()))
        if SOURCE._NATIVE_SHA256 is not None:
            self.assertEqual(SOURCE._content_sha256.cache_info().maxsize,8)
            self.assertEqual(SOURCE._content_sha256.cache_info().currsize,8)

    def test_source_audit_still_requires_explicit_boundary_and_current_bytes(self):
        path=self.root/'source-audit/review.md';path.write_bytes(b'original source bytes')
        reference=dict(self.reference,file='source-audit/review.md')
        SOURCE.verified_source(self.rules,self.reference)
        with self.assertRaisesRegex(ValueError,'source must be inside input'):SOURCE.verified_source(self.rules,reference)
        self.assertEqual(SOURCE.verified_source(self.rules,reference,source_root='source-audit'),b'original source bytes')
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'source changed'):SOURCE.verified_source(self.rules,reference,source_root='source-audit')

    def test_link_retarget_outside_boundary_rejects_even_identical_cached_bytes(self):
        inside=self.root/'input/inside';outside=self.root/'outside';inside.mkdir();outside.mkdir()
        for folder in (inside,outside):(folder/'source.md').write_bytes(b'original source bytes')
        link=self.root/'input/active'
        def create(target):link.symlink_to(target,target_is_directory=True)
        try:create(inside)
        except OSError as exc:
            if os.name!='nt':self.skipTest('symlink creation unavailable: '+str(exc))
            # Windows junctions exercise the same Path.resolve escape boundary
            # without requiring the symlink-creation privilege.
            import _winapi
            def create(target):_winapi.CreateJunction(str(target),str(link))
            create(inside)
        reference=dict(self.reference,file='input/active/source.md')
        self.assertEqual(SOURCE.verified_source(self.rules,reference),b'original source bytes')
        if link.is_symlink():link.unlink()
        else:link.rmdir()
        create(outside)
        with self.assertRaisesRegex(ValueError,'source must be inside input'):SOURCE.verified_source(self.rules,reference)

    def test_invalid_reference_and_missing_file_still_reject_after_warm_cache(self):
        SOURCE.verified_source(self.rules,self.reference)
        for reference in (None,{},dict(self.reference,sha256=None)):
            with self.assertRaisesRegex(ValueError,'source file and sha256 required'):SOURCE.verified_source(self.rules,reference)
        self.path.unlink()
        with self.assertRaises(OSError):SOURCE.verified_source(self.rules,self.reference)


if __name__=='__main__':unittest.main()
