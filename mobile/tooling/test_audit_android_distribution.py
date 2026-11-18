import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

import audit_android_distribution as audit


class AndroidDistributionAuditTests(unittest.TestCase):
    def fixture(self, directory, *, extra=(), omit=(), webrtc=b''):
        app = Path(__file__).resolve().parents[1] / 'app'
        path = Path(directory) / 'app.apk'
        web_name = audit.FLUTTER + 'assets/licenses/webrtc-150.7871.04.md'
        with ZipFile(path, 'w') as apk:
            for notice in audit.REQUIRED_NOTICES:
                if notice not in omit:
                    apk.writestr(notice, (webrtc or (app / notice.removeprefix(audit.FLUTTER)).read_bytes())
                                 if notice == web_name else b'test notice')
            apk.writestr('assets/runtime/manifest.json', json.dumps({
                'abi': 'arm64-v8a', 'dshVersion': '0.2.2-rc.1', 'runtimeVersion': 'test-runtime',
                'rootfs': 'rootfs.tar.xz',
            }))
            apk.writestr('assets/runtime/rootfs.tar.xz', b'test archive')
            apk.writestr(audit.FLUTTER + 'assets/companion/index.html', b'web shell')
            for name in extra:
                apk.writestr(audit.FLUTTER + name, b'not a distributable asset')
        return path

    def test_reports_valid_assets(self):
        with TemporaryDirectory() as directory:
            result = audit.audit_apk(self.fixture(directory))
            self.assertEqual(result['abi'], 'arm64-v8a')
            self.assertEqual(result['runtimeArchives'], ['rootfs.tar.xz'])

    def test_rejects_known_pets_and_unlisted_companion_assets(self):
        for name in ('assets/companion/whale-girl.zip', 'assets/companion/local.zip', 'assets/pets/deepy-whale/idle.png'):
            with self.subTest(name=name), TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, 'Excluded'):
                    audit.audit_apk(self.fixture(directory, extra=(name,)))

    def test_rejects_missing_or_modified_notices(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'Missing license assets'):
                audit.audit_apk(self.fixture(directory, omit=(audit.REQUIRED_NOTICES[0],)))
            with self.assertRaisesRegex(ValueError, 'WebRTC license asset differs'):
                audit.audit_apk(self.fixture(directory, webrtc=b'not the upstream notice'))


if __name__ == '__main__':
    unittest.main()
