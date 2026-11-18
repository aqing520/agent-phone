#!/usr/bin/env python3
"""Check license assets and known upstream artwork in an Agent Phone APK."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

FLUTTER = 'assets/flutter_assets/'
REQUIRED_NOTICES = (
    FLUTTER + 'NOTICES.Z',
    FLUTTER + 'assets/licenses/webrtc-150.7871.04.md',
    FLUTTER + 'assets/licenses/unicode-15.0.txt',
    FLUTTER + 'assets/licenses/jquery-3.7.1-LICENSE.txt',
    FLUTTER + 'assets/licenses/lodash-4.17.21-LICENSE.txt',
    FLUTTER + 'assets/licenses/streaming-asr-model-APACHE-2.0.txt',
    'assets/runtime/licenses/proot-COPYING.txt',
    'assets/runtime/licenses/libtalloc-notice.txt',
    'assets/runtime/licenses/libandroid-shmem-copyright.txt',
    'assets/speech/silero-LICENSE.txt',
    'assets/speech/smart-turn-LICENSE.txt',
)
WEBRTC_NOTICE_SHA256 = 'd1f9382c6878ac024155fd6d44a5977329108bb8b0a01cea40e4a2f1d7de252e'
COMPANION_FILES = frozenset({'bare.js', 'float.js', 'index.html', 'scene.js', 'stage.css', 'stage.js'})


def audit_apk(path: Path) -> dict:
    with ZipFile(path) as apk:
        names = set(apk.namelist())
        companion = FLUTTER + 'assets/companion/'
        excluded = sorted(n for n in names if (
            n.startswith(companion) and n.removeprefix(companion) not in COMPANION_FILES
            or n.startswith(FLUTTER + 'assets/whale/')
            or any(marker in n.casefold() for marker in ('whale-girl', 'deepy-whale', 'star_whale'))
        ))
        if excluded:
            raise ValueError(f'Excluded upstream or unapproved companion assets: {", ".join(excluded)}')
        missing = [n for n in REQUIRED_NOTICES if n not in names or not apk.getinfo(n).file_size]
        if missing:
            raise ValueError(f'Missing license assets: {", ".join(missing)}')
        webrtc = apk.read(FLUTTER + 'assets/licenses/webrtc-150.7871.04.md')
        if hashlib.sha256(webrtc).hexdigest() != WEBRTC_NOTICE_SHA256:
            raise ValueError('WebRTC license asset differs from documented upstream bytes')
        manifest = 'assets/runtime/manifest.json'
        if manifest not in names:
            raise ValueError('Missing runtime manifest')
        runtime = json.loads(apk.read(manifest))
        if not isinstance(runtime, dict) or runtime.get('abi') not in ('arm64-v8a', 'x86_64'):
            raise ValueError('Invalid runtime ABI')
        layers = runtime.get('layers')
        if runtime.get('schema') == 2:
            if not isinstance(layers, dict) or any(not isinstance(layers.get(k), dict) for k in ('base', 'engine')):
                raise ValueError('Missing runtime layer records')
            archives = [layers[k].get('asset') for k in ('base', 'engine')]
        else:
            archives = [runtime.get('rootfs')]
        if any(not isinstance(n, str) or not n or '/' in n or 'assets/runtime/' + n not in names for n in archives):
            raise ValueError('Missing runtime archive named in manifest')
        if not runtime.get('dshVersion') or not runtime.get('runtimeVersion'):
            raise ValueError('Missing runtime or DSH version')
        return {
            'abi': runtime['abi'], 'dshVersion': runtime['dshVersion'],
            'runtimeVersion': runtime['runtimeVersion'], 'runtimeArchives': archives,
            'licenses': list(REQUIRED_NOTICES),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    args = parser.parse_args()
    try:
        summary = audit_apk(args.apk)
        digest = hashlib.sha256()
        with args.apk.open('rb') as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b''):
                digest.update(chunk)
        summary['apkSha256'] = digest.hexdigest()
    except (OSError, ValueError, BadZipFile) as error:
        parser.exit(1, f'audit_android_distribution: {error}\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
