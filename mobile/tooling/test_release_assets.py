"""Tests for tooling/release_assets.py: the version checks, and the delta
patches from earlier releases (with a fake gh and made-up APKs; no network).

    python3 -m unittest discover -s tooling -p 'test_*.py'
"""

import contextlib
import hashlib
import io
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

import apk_delta
import release_assets
from build_number import MAX_VERSION_CODE
from release_assets import BADGING_RE, ReleaseError, check_abis, find_aapt2, patch_from, previous_releases, published_apk, release_build

# Stands in for gh: `release list` prints $FAKE_RELEASES, `release download`
# copies the asset files from $FAKE_ASSETS/<tag>/; every call goes to $FAKE_LOG.
FAKE_GH = """#!{python}
import json, os, shutil, sys
args = sys.argv[1:]
open(os.environ["FAKE_LOG"], "a").write(" ".join(args) + "\\n")
assert args[:1] == ["release"] and args[args.index("--repo") + 1] == "aqing520/agent-phone", args
if args[1] == "list":
    print(os.environ["FAKE_RELEASES"])
elif args[1] == "download":
    source = os.path.join(os.environ["FAKE_ASSETS"], args[2])
    if not os.path.isdir(source):
        sys.exit("release not found")
    folder = args[args.index("--dir") + 1]
    os.makedirs(folder, exist_ok=True)
    for i, a in enumerate(args):
        if a == "--pattern":
            shutil.copyfile(os.path.join(source, args[i + 1]), os.path.join(folder, args[i + 1]))
"""


def apk(path, seed, *, libapp_seed=None):
    """A made-up APK: a big runtime, libapp.so, classes.dex."""
    rng = random.Random(seed)
    with zipfile.ZipFile(path, "w") as z:
        for name, data, method in [
            ("AndroidManifest.xml", b"<manifest/>", zipfile.ZIP_DEFLATED),
            ("assets/runtime/rootfs-arm64-v8a.tar.xz", random.Random(1).randbytes(300_000), zipfile.ZIP_STORED),
            ("lib/arm64-v8a/libapp.so", random.Random(libapp_seed if libapp_seed is not None else seed).randbytes(40_000), zipfile.ZIP_DEFLATED),
            ("classes.dex", rng.randbytes(10_000), zipfile.ZIP_DEFLATED),
        ]:
            z.writestr(zipfile.ZipInfo(name, date_time=(2026, 11, 1, 0, 0, 0)), data, compress_type=method)
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReleaseBuildTest(unittest.TestCase):
    def test_sdk_tool_lookup_uses_platform_filename_newest_version_and_path_first(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for platform, filename in (("win32", "aapt2.exe"), ("linux", "aapt2")):
                with self.subTest(platform=platform):
                    sdk = root / platform / "Android SDK"
                    for version in ("35.0.9", "35.0.10"):
                        tool = sdk / "build-tools" / version / filename
                        tool.parent.mkdir(parents=True)
                        tool.write_bytes(b"not executed")
                    with mock.patch("release_assets.ROOT", root), \
                            mock.patch("release_assets.sys.platform", platform), \
                            mock.patch("release_assets.shutil.which", return_value=None) as which, \
                            mock.patch.dict(os.environ, {"ANDROID_HOME": str(sdk), "ANDROID_SDK_ROOT": ""}):
                        self.assertEqual(find_aapt2(), str(sdk / "build-tools" / "35.0.10" / filename))
                        preferred = root / filename
                        preferred.write_bytes(b"not executed")
                        which.return_value = str(preferred)
                        self.assertEqual(find_aapt2(), str(preferred))

    def test_sdk_tool_lookup_decodes_local_properties_without_changing_plain_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            sdk = root / "Android SDK 用户 🐳 #!="
            tool = sdk / "build-tools" / "35.0.10" / ("aapt2.exe" if sys.platform == "win32" else "aapt2")
            tool.parent.mkdir(parents=True)
            tool.write_bytes(b"not executed")
            props = root / "app" / "android" / "local.properties"
            props.parent.mkdir(parents=True)
            escaped = str(sdk).replace("\\", "\\\\").replace(":", "\\:")
            escaped = escaped.replace("#", "\\#").replace("!", "\\!").replace("=", "\\=")
            escaped = escaped.replace("用户 🐳", r"\u7528\u6237 \uD83D\uDC33")
            for value in (str(sdk), escaped):
                with self.subTest(value=value):
                    props.write_text("sdk.dir=" + value + "\n", encoding="utf-8")
                    with mock.patch("release_assets.ROOT", root), \
                            mock.patch("release_assets.shutil.which", return_value=None), \
                            mock.patch.dict(os.environ, {"ANDROID_HOME": "", "ANDROID_SDK_ROOT": ""}):
                        self.assertEqual(find_aapt2(), str(tool))

    def test_sdk_tool_lookup_unescapes_windows_path_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            props = root / "app" / "android" / "local.properties"
            props.parent.mkdir(parents=True)
            tool = root / "build-tools" / "35.0.10" / "aapt2.exe"
            sdk = r"C:\Users\用户\u1234\Android SDK"
            for value in (
                r"C:\\Users\\用户\\u1234\\Android SDK",
                r"C\:\\Users\\\u7528\u6237\\u1234\\Android SDK",
                "C:/Users/用户/u1234/Android SDK",
            ):
                expected = sdk if "\\" in value else value
                with self.subTest(value=value):
                    props.write_text("sdk.dir=" + value + "\n", encoding="utf-8")
                    with mock.patch("release_assets.ROOT", root), \
                            mock.patch("release_assets.shutil.which", return_value=None), \
                            mock.patch("release_assets.sys.platform", "win32"), \
                            mock.patch.dict(os.environ, {"ANDROID_HOME": "", "ANDROID_SDK_ROOT": ""}), \
                            mock.patch("release_assets.pathlib.Path") as paths:
                        paths.return_value.glob.return_value = [tool]
                        self.assertEqual(find_aapt2(), str(tool))
                        paths.assert_called_once_with(expected)
                        paths.return_value.glob.assert_called_once_with("build-tools/*/aapt2.exe")

    def test_both_flavors_agree(self):
        apks = {"arm64": ("1.2.0", 10251234), "x64": ("1.2.0", 10251234)}
        self.assertEqual(release_build("1.2.0", None, apks), 10251234)
        self.assertEqual(release_build("1.2.0", 10251234, apks), 10251234)

    def test_flavors_built_at_different_minutes(self):
        with self.assertRaisesRegex(ReleaseError, "different build numbers"):
            release_build("1.2.0", None, {"arm64": ("1.2.0", 10251234), "x64": ("1.2.0", 10251301)})

    def test_version_name_mismatch(self):
        with self.assertRaisesRegex(ReleaseError, "x64"):
            release_build("1.2.0", None, {"arm64": ("1.2.0", 10251234), "x64": ("1.1.0", 10251234)})

    def test_placeholder_build_number(self):
        for code in [0, 1, MAX_VERSION_CODE + 1]:
            with self.assertRaisesRegex(ReleaseError, "placeholder"):
                release_build("1.0.0", None, {"arm64": ("1.0.0", code)})

    def test_explicit_version_must_match(self):
        with self.assertRaisesRegex(ReleaseError, r"\+7"):
            release_build("1.2.0", 7, {"arm64": ("1.2.0", 10251234)})

    def test_apk_holds_only_its_own_abi(self):
        check_abis("arm64", ["classes.dex", "lib/arm64-v8a/libapp.so", "lib/arm64-v8a/libflutter.so"])
        check_abis("x64", ["lib/x86_64/libapp.so"])

    def test_apk_with_another_abi_is_refused(self):
        with self.assertRaisesRegex(ReleaseError, "armeabi-v7a"):
            check_abis("arm64", ["lib/arm64-v8a/libapp.so", "lib/armeabi-v7a/libspake2.so"])

    def test_apk_without_native_libraries_is_refused(self):
        with self.assertRaisesRegex(ReleaseError, "expected only arm64-v8a"):
            check_abis("arm64", ["classes.dex"])
        with self.assertRaisesRegex(ReleaseError, "expected only arm64-v8a"):
            check_abis("arm64", ["lib/arm64-v8a/"])

    def test_badging_line(self):
        line = ("package: name='io.github.ccch1mneyyy.dsh_app' versionCode='10251234' versionName='1.2.0-beta.1' "
                "platformBuildVersionName='16'\nminSdkVersion:'26'\n")
        m = BADGING_RE.search(line)
        self.assertEqual((m.group(1), m.group(2)), ("10251234", "1.2.0-beta.1"))


class DeltaTest(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        (self.dir / "out").mkdir()

    def test_a_small_patch_is_kept(self):
        old, new = apk(self.dir / "old.apk", 1), apk(self.dir / "new.apk", 2, libapp_seed=1)
        with contextlib.redirect_stdout(io.StringIO()):
            patch = patch_from(old, "1.0.7+10311844", new, "1.0.8", self.dir / "out")
        name = "dsh-go-1.0.8-from-1.0.7-arm64.dshdelta"
        path = self.dir / "out" / name
        self.assertEqual(patch, {"from": sha(old), "fromVersion": "1.0.7+10311844", "name": name, "size": path.stat().st_size, "sha256": sha(path)})
        self.assertLess(patch["size"], 0.1 * new.stat().st_size)
        apk_delta.apply(old, path, self.dir / "again.apk")
        self.assertEqual((self.dir / "again.apk").read_bytes(), new.read_bytes())

    def test_a_patch_of_60_percent_or_more_is_left_out(self):
        old = apk(self.dir / "old.apk", 1)
        new = self.dir / "new.apk"
        # Another runtime: nearly everything changes.
        with zipfile.ZipFile(new, "w") as z:
            z.writestr("assets/runtime/rootfs-arm64-v8a.tar.xz", random.Random(9).randbytes(300_000), compress_type=zipfile.ZIP_STORED)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(patch_from(old, "1.0.7+10311844", new, "1.0.8", self.dir / "out"))
        self.assertIn("left out", out.getvalue())
        self.assertEqual(list((self.dir / "out").iterdir()), [])

    def add_base_layer(self, path, data):
        asset = "base-arm64-v8a.tar.xz"
        with zipfile.ZipFile(path, "a") as archive:
            # This diagnostic compares the actual asset, not a possibly stale declared digest.
            archive.writestr("assets/runtime/manifest.json", json.dumps({"schema": 2, "layers": {
                "base": {"asset": asset, "sha256": "a" * 64}}}))
            archive.writestr("assets/runtime/" + asset, data)

    def test_base_warning_compares_actual_bytes_and_does_not_reject_patch(self):
        old, new = apk(self.dir / "old.apk", 1), apk(self.dir / "new.apk", 2, libapp_seed=1)
        self.add_base_layer(old, b"old base bytes")
        self.add_base_layer(new, b"new base bytes")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            patch = patch_from(old, "1.0.7+10311844", new, "1.0.8", self.dir / "out")
        self.assertIsNotNone(patch)
        self.assertEqual(output.getvalue().count("WARNING: base layer SHA-256 changed"), 1)
        apk_delta.apply(old, self.dir / "out" / patch["name"], self.dir / "again.apk")
        self.assertEqual((self.dir / "again.apk").read_bytes(), new.read_bytes())

    def test_unchanged_base_and_legacy_transition_do_not_claim_a_changed_base(self):
        for legacy in [False, True]:
            with self.subTest(legacy=legacy):
                old, new = apk(self.dir / "old.apk", 1), apk(self.dir / "new.apk", 2, libapp_seed=1)
                if not legacy:
                    self.add_base_layer(old, b"same base bytes")
                self.add_base_layer(new, b"same base bytes")
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertIsNotNone(patch_from(old, "1.0.7+10311844", new, "1.0.8", self.dir / "out"))
                self.assertNotIn("WARNING: base layer", output.getvalue())


class PublishedTest(unittest.TestCase):
    """The earlier releases' APKs, from GitHub through a fake gh."""

    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        bin_dir = self.dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(FAKE_GH.format(python=sys.executable))
        (bin_dir / "gh").chmod(0o755)
        self.log = self.dir / "gh.log"
        self.log.write_text("")
        self.assets = self.dir / "assets"
        releases = [
            {"tagName": "v1.0.6", "publishedAt": "2026-10-31T09:07:32Z"},
            {"tagName": "v1.0.8", "publishedAt": "2026-11-01T11:24:24Z"},
            {"tagName": "v1.0.7", "publishedAt": "2026-10-31T10:46:17Z"},
            {"tagName": "v1.0.5", "publishedAt": "2026-10-31T07:11:50Z"},
        ]
        env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(self.log),
               "FAKE_ASSETS": str(self.assets), "FAKE_RELEASES": json.dumps(releases)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def release(self, tag, sums_for=None):
        folder = self.assets / tag
        folder.mkdir(parents=True)
        name = f"dsh-go-{tag[1:]}-arm64.apk"
        path = apk(folder / name, 7)
        (folder / "SHA256SUMS").write_text(f"{sums_for or sha(path)}  {name}\n")
        return path

    def test_the_newest_releases_before_this_one(self):
        self.assertEqual(previous_releases("v1.0.9", 3), ["v1.0.8", "v1.0.7", "v1.0.6"])
        self.assertEqual(previous_releases("v1.0.8", 3), ["v1.0.7", "v1.0.6", "v1.0.5"])
        self.assertEqual(previous_releases("v1.0.9", 1), ["v1.0.8"])
        self.assertIn("release list --exclude-drafts", self.log.read_text())

    def test_downloads_once_and_checks_the_release_sums(self):
        original = self.release("v1.0.7")
        cache = self.dir / "cache"
        got = published_apk("v1.0.7", cache)
        self.assertEqual(got, cache / "v1.0.7" / "dsh-go-1.0.7-arm64.apk")
        self.assertEqual(got.read_bytes(), original.read_bytes())
        self.assertEqual(published_apk("v1.0.7", cache), got)
        self.assertEqual(self.log.read_text().count("release download v1.0.7"), 1)
        # A damaged copy in the cache is fetched again.
        got.write_bytes(b"truncated")
        self.assertEqual(published_apk("v1.0.7", cache).read_bytes(), original.read_bytes())
        self.assertEqual(self.log.read_text().count("release download v1.0.7"), 2)

    def test_an_apk_unlike_its_sums_is_refused(self):
        self.release("v1.0.6", sums_for="00" * 32)
        with self.assertRaisesRegex(ReleaseError, "doesn't match the release's SHA256SUMS"):
            published_apk("v1.0.6", self.dir / "cache")

    def test_gh_failing_says_how_to_go_without(self):
        with self.assertRaisesRegex(ReleaseError, "--delta-from 0"):
            published_apk("v0.1.0", self.dir / "cache")


class ReleaseSourceTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = pathlib.Path(folder.name)
        self.commit = 'a' * 40
        self.source = {'tag': 'v1.2.0', 'commit': self.commit,
                       'source': f'https://github.com/aqing520/agent-phone/tree/{self.commit}'}
        self.cert = 'b' * 64
        self.apk = apk(self.root / 'fixture.apk', 1)
        self.record = self.root / 'review.md'
        self.out = self.root / 'dist'
        self.signature = '\n'.join([
            *[f'Verified using {scheme} scheme (APK signing): true' for scheme in ('v1', 'v2', 'v3')],
            'Signer #1 certificate DN: CN=Agent Phone',
            f'Signer #1 certificate SHA-256 digest: {self.cert}',
        ])

    def embed(self, source):
        with zipfile.ZipFile(self.apk, 'a') as archive:
            archive.writestr(release_assets.PROVENANCE, json.dumps(source))
            archive.writestr('assets/agent-phone-LICENSE', 'LICENSE.txt')
            archive.writestr('assets/agent-phone-THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md')

    def test_refuses_debug_signing_even_if_certificate_matches(self):
        debug = self.signature.replace('CN=Agent Phone', 'CN=Android Debug')
        with mock.patch('release_assets.subprocess.run', return_value=subprocess.CompletedProcess([], 0, debug)):
            with self.assertRaisesRegex(ReleaseError, 'Android Debug signing is not accepted'):
                release_assets.validate_release_apk(self.apk, 'arm64', self.source, self.cert, 'apksigner')

    def test_refuses_missing_provenance_and_wrong_commit(self):
        result = subprocess.CompletedProcess([], 0, self.signature)
        with mock.patch('release_assets.subprocess.run', return_value=result):
            with self.assertRaisesRegex(ReleaseError, 'missing or duplicate signed source identity'):
                release_assets.validate_release_apk(self.apk, 'arm64', self.source, self.cert, 'apksigner')
            self.embed(dict(self.source, commit='c' * 40))
            with self.assertRaisesRegex(ReleaseError, 'signed source identity does not match'):
                release_assets.validate_release_apk(self.apk, 'arm64', self.source, self.cert, 'apksigner')

    def test_source_record_cannot_be_reused_for_another_apk(self):
        self.record.write_text(f'APK SHA-256: {"0" * 64}\n')
        with self.assertRaisesRegex(ReleaseError, 'each release APK SHA-256'):
            release_assets.validate_source_record(self.record, {'arm64': release_assets.asset_item(self.apk)})

    def test_prepare_and_recheck_distribution(self):
        self.embed(self.source)
        self.record.write_text(f'APK SHA-256: {sha(self.apk)}\n\nComponent source directions.\n')
        git_responses = {('rev-parse', 'HEAD'): self.commit.encode(),
                         ('status', '--porcelain', '--untracked-files=normal'): b'',
                         ('show', f'{self.commit}:mobile/app/pubspec.yaml'): b'version: 1.2.0+1\n'}
        with mock.patch.object(sys, 'argv', ['release_assets.py', '--out', str(self.out),
                                            '--third-party-sources', str(self.record), f'arm64={self.apk}']), \
                mock.patch.dict(os.environ, AGENT_PHONE_SIGNER_SHA256=self.cert), \
                mock.patch('release_assets.find_sdk_tool', side_effect=lambda name: name), \
                mock.patch('release_assets.pubspec_version', return_value='1.2.0+1'), \
                mock.patch('release_assets.git', side_effect=lambda *args: git_responses[args]), \
                mock.patch('release_assets.source_identity', return_value=self.source), \
                mock.patch('release_assets.tagged_notice', side_effect=lambda _, file: file.encode()), \
                mock.patch('release_assets.apk_version', return_value=('1.2.0', 11181621)), \
                mock.patch('release_assets.check_apk_jni'), \
                mock.patch('release_assets.audit_apk', return_value={'abi': 'arm64-v8a'}), \
                mock.patch('release_assets.subprocess.run', return_value=subprocess.CompletedProcess([], 0, self.signature)), \
                contextlib.redirect_stdout(io.StringIO()):
            release_assets.main()
            source, files = release_assets.check_dist(self.out, self.cert, 'aapt2', 'apksigner')
            self.assertEqual(source, self.source)
            self.assertEqual(set(files), set(release_assets.SOURCE_FILES) | {
                'dsh-go-1.2.0-arm64.apk', 'update.json', 'SHA256SUMS'})
            self.assertIn(self.source['source'], (self.out / 'SOURCE.md').read_text())
            (self.out / 'THIRD_PARTY_NOTICES.md').write_text('tampered')
            with self.assertRaisesRegex(ReleaseError, 'differs from tagged source'):
                release_assets.check_dist(self.out, self.cert, 'aapt2', 'apksigner')


class PublisherTest(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        base = pathlib.Path(root.name)
        self.dist = base / 'dist'
        self.dist.mkdir()
        self.log = base / 'gh.log'
        self.log.touch()
        self.script = pathlib.Path(__file__).resolve().parents[1] / 'services/share-worker/scripts/publish-release.sh'
        self.env = dict(os.environ, PATH=f'{base}{os.pathsep}{os.environ["PATH"]}', FAKE_LOG=str(self.log))
        self.stub(base / 'python3', '''
[[ "$2" == --verify-dist ]] || exit 7
printf '%s\n' v1.2.0 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa SOURCE.md SHA256SUMS
''')
        self.stub(base / 'gh', '''
printf '%s\n' "$*" >>"$FAKE_LOG"
if [[ "$1 $2" == 'repo view' ]]; then
  printf '%s\n' PUBLIC
elif [[ "$1" == api ]]; then
  printf '%s\n' 'commit bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
else
  exit 7
fi
''')

    @staticmethod
    def stub(path, script):
        path.write_text('#!/bin/bash\n' + script)
        path.chmod(0o755)

    def run_publisher(self, mode):
        return subprocess.run(['bash', str(self.script), str(self.dist), mode], env=self.env,
                              capture_output=True, text=True, check=False)

    def test_dry_run_and_old_mirror_flag_never_call_github(self):
        result = self.run_publisher('--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('aqing520/agent-phone', result.stdout)
        self.assertIn('SOURCE.md', result.stdout)
        self.assertEqual(self.run_publisher('--no-cn').returncode, 2)
        self.assertEqual(self.log.read_text(), '')

    def test_wrong_remote_tag_stops_before_release_creation(self):
        result = self.run_publisher('--publish')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('does not point to APK source commit', result.stderr)
        calls = self.log.read_text()
        self.assertIn('repos/aqing520/agent-phone/git/ref/tags/v1.2.0', calls)
        self.assertNotIn('release create', calls)


if __name__ == "__main__":
    unittest.main()
