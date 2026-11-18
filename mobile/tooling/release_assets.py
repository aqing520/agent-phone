#!/usr/bin/env python3
"""Prepare GitHub release assets for an in-app update (see docs/release.md).

Takes the version name from app/pubspec.yaml and the build number from the
APKs themselves (aapt2), copies them to dist/ under their release names, and
writes SHA256SUMS and update.json next to them. The default release contains
arm64 only; explicit flavor inputs remain available for local testing. Build
with `tooling/build-apk.sh` first. Explicit multiple inputs must share a build number.

It also makes delta patches (tooling/apk_delta.py, docs/design/delta-update.md)
from the arm64 APKs of the last --delta-from releases on GitHub (fetched with
`gh`, kept in ~/.cache/dshgo-release/apk/, checked against their SHA256SUMS),
and keeps those under 60 % of the new APK: in dist/, SHA256SUMS and update.json's
`patches`.

    AGENT_PHONE_SIGNER_SHA256=<fingerprint> python3 tooling/release_assets.py \
        --third-party-sources /path/to/verified-sources.md --delta-from 0

--base-url makes update.json point at your own host (self-hosted feed); without
it the app derives GitHub download URLs from the tag and asset names.
"""

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

import apk_delta
from audit_android_distribution import audit_apk
from check_apk_jni import ApkJniError, check_apk_jni
from build_number import MAX_VERSION_CODE, decode

ROOT = pathlib.Path(__file__).resolve().parent.parent
FLAVORS = ("arm64", "x64")
FLAVOR_ABI = {"arm64": "arm64-v8a", "x64": "x86_64"}
REPO = "aqing520/agent-phone"
APP_ID = "io.github.ccch1mneyyy.dsh_app.agentphone"
PROVENANCE = "assets/agent-phone-release.json"
SOURCE_RECORD = "THIRD_PARTY_SOURCES.md"
SOURCE_FILES = ("LICENSE.txt", "THIRD_PARTY_NOTICES.md", "SOURCE.md", SOURCE_RECORD)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
VERSION_RE = re.compile(r"^(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)(?:\+(\d+))?$")
BADGING_RE = re.compile(r"^package: .*?\bversionCode='(\d*)' versionName='([^']*)'", re.MULTILINE)
CACHE = pathlib.Path.home() / ".cache" / "agent-phone-release" / "apk"
# A patch this big saves too little to be worth a second download path.
PATCH_LIMIT = 0.6


class ReleaseError(Exception):
    pass


def check_abis(flavor: str, entries: list[str]) -> None:
    """A flavor's APK holds native libraries for its own ABI and no other."""
    abis = {name.split("/")[1] for name in entries if name.startswith("lib/") and name.endswith(".so")}
    if abis != {FLAVOR_ABI[flavor]}:
        raise ReleaseError(f"{flavor} APK has native libraries for {sorted(abis)}, expected only {FLAVOR_ABI[flavor]}")


def pubspec_version() -> str:
    text = (ROOT / "app" / "pubspec.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*(\S+)", text, re.MULTILINE)
    if not match:
        sys.exit("version: not found in app/pubspec.yaml")
    return match.group(1)


def find_aapt2() -> str | None:
    """aapt2 on PATH, else the newest one in the Android SDK's build-tools."""
    return find_sdk_tool("aapt2")


def find_sdk_tool(name: str) -> str | None:
    suffix = {"aapt2": ".exe", "apksigner": ".bat"}[name] if sys.platform == "win32" else ""
    found = shutil.which(name)
    if found:
        return found
    sdks = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    props = ROOT / "app" / "android" / "local.properties"
    if props.is_file():
        match = re.search(r"^sdk\.dir=(.+)$", props.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            # local.properties uses Java escapes; environment paths do not.
            sdks.append(re.sub(
                r"(?:\\u[0-9a-fA-F]{4})+|\\([\\: =#!])",
                lambda escaped: escaped[1] if escaped[1] is not None else
                    bytes.fromhex(escaped[0].replace(r"\u", "")).decode("utf-16-be", "surrogatepass"),
                match.group(1).strip(),
            ))
    for sdk in filter(None, sdks):
        tools = sorted(
            pathlib.Path(sdk).glob(f"build-tools/*/{name}{suffix}"),
            key=lambda p: tuple(int(n) for n in re.findall(r"\d+", p.parent.name)),
        )
        if tools:
            return str(tools[-1])
    return None


def apk_version(aapt2: str, path: pathlib.Path, *, require_agent_phone: bool = False) -> tuple[str, int]:
    """(versionName, versionCode) as the APK's manifest says."""
    out = subprocess.run([aapt2, "dump", "badging", str(path)], capture_output=True, text=True).stdout
    match = BADGING_RE.search(out)
    if not match:
        raise ReleaseError(f"{path}: aapt2 could not read its manifest")
    if require_agent_phone and not match[0].startswith(f"package: name='{APP_ID}' "):
        raise ReleaseError(f"{path}: expected Agent Phone application ID {APP_ID}")
    return match.group(2), int(match.group(1) or 0)


def git(*args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(ROOT.parent), *args], capture_output=True, check=False)
    if result.returncode:
        raise ReleaseError(f"git {' '.join(args)}: {result.stderr.decode(errors='replace').strip()}")
    return result.stdout


def source_identity(tag: str) -> dict:
    commit = git("rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ReleaseError(f"{tag}: expected a Git commit SHA-1")
    return {"tag": tag, "commit": commit, "source": f"https://github.com/{REPO}/tree/{commit}"}


def signer_fingerprint(value: str) -> str:
    fingerprint = value.lower().replace(":", "").strip()
    if not SHA256_RE.fullmatch(fingerprint):
        raise ReleaseError("set AGENT_PHONE_SIGNER_SHA256 to the trusted release certificate SHA-256 fingerprint")
    return fingerprint


def validate_release_apk(path: pathlib.Path, flavor: str, source: dict, signer: str, apksigner: str) -> None:
    result = subprocess.run([apksigner, "verify", "--verbose", "--min-sdk-version", "21", "--print-certs", str(path)],
                            capture_output=True, text=True)
    certs = re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$", result.stdout, re.MULTILINE)
    signing = all(re.search(rf"^Verified using {scheme} scheme .*: true$", result.stdout, re.MULTILINE)
                  for scheme in ("v1", "v2", "v3"))
    if result.returncode or not signing or re.search(r"^Signer #\d+ certificate DN: .*\bCN=Android Debug\b", result.stdout, re.MULTILINE):
        raise ReleaseError(f"{path}: requires valid v1/v2/v3 release signing; Android Debug signing is not accepted")
    if [cert.lower() for cert in certs] != [signer]:
        raise ReleaseError(f"{path}: signer does not match AGENT_PHONE_SIGNER_SHA256")
    with zipfile.ZipFile(path) as apk:
        entries = apk.namelist()
        check_abis(flavor, entries)
        if entries.count(PROVENANCE) != 1:
            raise ReleaseError(f"{path}: missing or duplicate signed source identity; build with --public-release")
        if json.loads(apk.read(PROVENANCE)) != source:
            raise ReleaseError(f"{path}: signed source identity does not match {source['tag']} ({source['commit']})")
        for name, embedded in (("LICENSE.txt", "assets/agent-phone-LICENSE"),
                               ("THIRD_PARTY_NOTICES.md", "assets/agent-phone-THIRD_PARTY_NOTICES.md")):
            if entries.count(embedded) != 1 or apk.read(embedded) != tagged_notice(source, name):
                raise ReleaseError(f"{path}: signed {name} is absent or differs from tagged source")
    if audit_apk(path)["abi"] != FLAVOR_ABI[flavor]:
        raise ReleaseError(f"{path}: runtime ABI differs from release APK flavor {flavor}")
    check_apk_jni(path)


def source_notice(source: dict, build: int, assets: dict) -> bytes:
    hashes = "\n".join(f"- `{asset['name']}`: SHA-256 `{asset['sha256']}`" for asset in assets.values())
    return (
        f"# Agent Phone {source['tag']} (build {build}): corresponding source\n\n"
        f"Agent Phone is an unofficial derivative of [DSH Go](https://github.com/ccch1mneyyy/dsh-go).\n"
        f"Download the exact [Agent Phone source and build scripts]({source['source']}) for this release "
        f"as a [ZIP archive](https://github.com/{REPO}/archive/{source['commit']}.zip), free of charge.\n\n"
        f"See [AGPL-3.0](LICENSE.txt), [third-party license notices](THIRD_PARTY_NOTICES.md) and "
        f"[third-party corresponding-source directions]({SOURCE_RECORD}) for this release.\n\n{hashes}\n"
    ).encode("utf-8")


def tagged_notice(source: dict, name: str) -> bytes:
    return git("show", f"{source['commit']}:mobile/{'LICENSE' if name == 'LICENSE.txt' else name}")


def validate_source_record(path: pathlib.Path, assets: dict) -> bytes:
    record = path.read_bytes()
    text = record.decode('utf-8')
    hashes = set(re.findall(r"^APK SHA-256: ([0-9a-f]{64})[ \t]*$", text, re.MULTILINE))
    if hashes != {asset['sha256'] for asset in assets.values()}:
        raise ReleaseError(f"{path}: provide third-party source directions containing each release APK SHA-256")
    if not any(line.strip() and not line.startswith('APK SHA-256:') for line in text.splitlines()):
        raise ReleaseError(f"{path}: APK SHA-256 headers alone are not source directions")
    return record


def asset_item(path: pathlib.Path) -> dict:
    return {"name": path.name, "size": path.stat().st_size, "sha256": sha256(path)}


def check_dist(out: pathlib.Path, signer: str, aapt2: str, apksigner: str) -> tuple[dict, list[str]]:
    manifest = json.loads((out / "update.json").read_bytes())
    tag = manifest["tag"]
    version = VERSION_RE.fullmatch(manifest["version"])
    if manifest["schema"] != 1 or not version or not version[2] or tag != "v" + version[1]:
        raise ReleaseError("dist: manifest version and tag do not agree")
    source = source_identity(tag)
    tagged_pubspec = git("show", f"{source['commit']}:mobile/app/pubspec.yaml").decode()
    if not re.search(rf"^version:[ \t]*{re.escape(version[1])}(?:\+[0-9]+)?[ \t]*$", tagged_pubspec, re.MULTILINE):
        raise ReleaseError("dist: version does not match the tagged pubspec.yaml")
    if (manifest["source"] != source or manifest["title"] != f"Agent Phone {version[1]}"
            or manifest["page"] != f"https://github.com/{REPO}/releases/tag/{tag}"):
        raise ReleaseError("dist: manifest does not match the Agent Phone release source")
    assets = manifest["assets"]
    if not assets.keys() <= FLAVOR_ABI.keys() or "arm64" not in assets:
        raise ReleaseError("dist: an arm64 APK and only supported flavors are required")
    entries = {}
    versions = {}
    for flavor, item in assets.items():
        name = f"dsh-go-{version[1]}-{flavor}.apk"
        if item["name"] != name:
            raise ReleaseError(f"dist: expected {name}")
        entries[name] = item
        versions[flavor] = apk_version(aapt2, out / name, require_agent_phone=True)
        validate_release_apk(out / name, flavor, source, signer, apksigner)
    build = release_build(version[1], int(version[2]), versions)
    for patch in manifest.get("patches", {}).get("arm64", []):
        name = patch["name"]
        if not re.fullmatch(rf"dsh-go-{re.escape(version[1])}-from-[0-9A-Za-z.-]+-arm64\.dshdelta", name) or name in entries:
            raise ReleaseError(f"dist: unexpected or duplicate patch {name}")
        entries[name] = patch
    for name, item in entries.items():
        actual = asset_item(out / name)
        if any(item[key] != actual[key] for key in ("sha256", "size")):
            raise ReleaseError(f"dist: {name} differs from update.json")
    validate_source_record(out / SOURCE_RECORD, assets)
    for name in SOURCE_FILES[:2]:
        if (out / name).read_bytes() != tagged_notice(source, name):
            raise ReleaseError(f"dist: {name} differs from tagged source")
    if (out / "SOURCE.md").read_bytes() != source_notice(source, build, assets):
        raise ReleaseError("dist: SOURCE.md differs from this release's APKs or tagged source")
    files = [*entries, *SOURCE_FILES, "update.json"]
    sums = (out / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    if len(sums) != len(files) or set(sums) != {f"{sha256(out / name)}  {name}" for name in files}:
        raise ReleaseError("dist: SHA256SUMS must cover exactly the release files, including notices and source directions")
    return source, [*files, "SHA256SUMS"]


def release_build(name: str, expected: int | None, apks: dict[str, tuple[str, int]]) -> int:
    """The build number (versionCode) of the release, once the APKs agree with
    [name], with each other and with [expected] (`--version X.Y.Z+N`)."""
    for flavor, (apk_name, _) in sorted(apks.items()):
        if apk_name != name:
            raise ReleaseError(f"{flavor}: the APK is version {apk_name!r}, the release is {name!r}")
    codes = sorted({code for _, code in apks.values()})
    if len(codes) != 1:
        found = ", ".join(f"{flavor} {code}" for flavor, (_, code) in sorted(apks.items()))
        raise ReleaseError(f"flavors have different build numbers ({found}); rebuild with tooling/build-apk.sh -f all")
    code = codes[0]
    if not 1 < code <= MAX_VERSION_CODE:
        raise ReleaseError(f"versionCode {code} is a placeholder; build with tooling/build-apk.sh")
    if expected is not None and expected != code:
        raise ReleaseError(f"--version says +{expected} but the APKs are {code}")
    return code


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gh(*args: str) -> str:
    run = subprocess.run(["gh", *args, "--repo", REPO], capture_output=True, text=True)
    if run.returncode:
        raise ReleaseError(f"gh {' '.join(args[:2])} failed: {run.stderr.strip()} (--delta-from 0 makes no patches)")
    return run.stdout


def previous_releases(tag: str, count: int) -> list[str]:
    """The tags of the [count] newest published releases other than [tag]."""
    releases = json.loads(gh("release", "list", "--exclude-drafts", "--limit", "50", "--json", "tagName,publishedAt"))
    releases.sort(key=lambda r: r["publishedAt"], reverse=True)
    return [r["tagName"] for r in releases if r["tagName"] != tag and r["tagName"].startswith("v")
            and VERSION_RE.fullmatch(r["tagName"][1:]) and "+" not in r["tagName"]][:count]


def listed(sums: pathlib.Path, name: str) -> str | None:
    """The SHA-256 that the SHA256SUMS file [sums] gives [name]."""
    if sums.is_file():
        for line in sums.read_text(encoding="utf-8").splitlines():
            digest, _, file = line.partition(" ")
            if file.lstrip(" *") == name:
                return digest.lower()
    return None


def published_apk(tag: str, cache: pathlib.Path) -> pathlib.Path:
    """[tag]'s arm64 APK from its GitHub release, kept in [cache], as the
    release's SHA256SUMS says it is."""
    name = f"dsh-go-{tag.removeprefix('v')}-arm64.apk"
    apk, sums = cache / tag / name, cache / tag / "SHA256SUMS"
    if not (apk.is_file() and listed(sums, name) == sha256(apk)):
        gh("release", "download", tag, "--pattern", name, "--pattern", "SHA256SUMS", "--dir", str(cache / tag), "--clobber")
        if listed(sums, name) != sha256(apk):
            raise ReleaseError(f"{tag}: {name} doesn't match the release's SHA256SUMS")
    return apk


def base_layer_sha256(path: pathlib.Path) -> str | None:
    """The actual base archive digest; legacy APKs have no separate base to compare."""
    with zipfile.ZipFile(path) as apk:
        manifest = "assets/runtime/manifest.json"
        if manifest not in apk.namelist():
            return None
        manifest = json.loads(apk.read(manifest))
        if manifest.get("schema") != 2:
            return None
        digest = hashlib.sha256()
        with apk.open("assets/runtime/" + manifest["layers"]["base"]["asset"]) as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()


def patch_from(old: pathlib.Path, old_version: str, new: pathlib.Path, name: str, out: pathlib.Path) -> dict | None:
    """The patch from [old] (version X.Y.Z+N) to the arm64 APK [new] of
    version [name], written to [out]; None, and nothing written, unless it's
    under PATCH_LIMIT of [new]."""
    old_base = base_layer_sha256(old)
    if old_base is not None:
        new_base = base_layer_sha256(new)
        if new_base is not None and old_base != new_base:
            print(f"WARNING: base layer SHA-256 changed from {old_version}: {old_base} -> {new_base}; delta savings may be reduced")
    patch = out / f"dsh-go-{name}-from-{old_version.partition('+')[0]}-arm64.dshdelta"
    apk_delta.make(old, new, patch)
    size = patch.stat().st_size
    share = size / new.stat().st_size
    print(f"patch from {old_version}: {size} bytes, {share:.0%} of the APK{'' if share < PATCH_LIMIT else ', left out'}")
    if share >= PATCH_LIMIT:
        patch.unlink()
        return None
    return {"from": sha256(old), "fromVersion": old_version, "name": patch.name, "size": size, "sha256": sha256(patch)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--version",
        help="X.Y.Z[-pre][+build]; default: app/pubspec.yaml's name. The build number is read from the APKs; "
        "a +build given here must match them.",
    )
    parser.add_argument("--verify-dist", type=pathlib.Path, help="revalidate a prepared directory and print its upload plan")
    parser.add_argument("--third-party-sources", type=pathlib.Path, help="reviewed source directions for the actual APK SHA-256 hashes")
    parser.add_argument("--notes", type=pathlib.Path, help="Markdown release notes (shown in the app)")
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "dist")
    parser.add_argument("--base-url", help="absolute or relative URL prefix for the APKs in update.json")
    parser.add_argument(
        "--delta-from",
        type=int,
        default=0,
        metavar="N",
        help="patches from the arm64 APKs of the N newest releases on GitHub (default 0: none)",
    )
    parser.add_argument(
        "apks",
        nargs="*",
        metavar="FLAVOR=PATH",
        help="default: arm64 only, app/build/app/outputs/flutter-apk/app-arm64-release.apk",
    )
    args = parser.parse_args()

    try:
        signer = signer_fingerprint(os.environ.get("AGENT_PHONE_SIGNER_SHA256", ""))
    except ReleaseError as e:
        sys.exit(str(e))
    aapt2, apksigner = find_aapt2(), find_sdk_tool("apksigner")
    if not (aapt2 and apksigner):
        sys.exit("aapt2 and apksigner from Android SDK build-tools are required")
    if args.verify_dist:
        try:
            source, files = check_dist(args.verify_dist, signer, aapt2, apksigner)
        except (ReleaseError, ApkJniError, OSError, ValueError, zipfile.BadZipFile, KeyError, TypeError) as e:
            sys.exit(str(e))
        print(source["tag"], source["commit"], *files, sep="\n")
        return
    if not args.third_party_sources:
        parser.error("--third-party-sources is required; review docs/android-distribution-sources.md first")
    if args.delta_from < 0:
        parser.error("--delta-from must be nonnegative")
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        parser.error("--out must be a new or empty directory")

    full = args.version or pubspec_version()
    match = VERSION_RE.match(full)
    if not match:
        sys.exit(f"not a release version: {full}")
    name = match.group(1)
    # pubspec's +N is a placeholder; only an explicit --version's +N is an expectation.
    expected = int(match.group(2)) if args.version and match.group(2) else None

    sources = {}
    for item in args.apks:
        flavor, _, path = item.partition("=")
        if flavor not in FLAVORS or not path:
            sys.exit(f"expected FLAVOR=PATH with FLAVOR in {FLAVORS}: {item}")
        sources[flavor] = pathlib.Path(path)
    if not sources:
        sources["arm64"] = ROOT / "app" / "build" / "app" / "outputs" / "flutter-apk" / "app-arm64-release.apk"
    for flavor, path in sources.items():
        if not path.is_file():
            sys.exit(f"{flavor}: {path} not found (build that flavor with tooling/build-apk.sh first)")

    tag = f"v{name}"
    try:
        source = source_identity(tag)
        if (git("rev-parse", "HEAD").decode().strip() != source["commit"]
                or git("status", "--porcelain", "--untracked-files=normal")):
            raise ReleaseError(f"prepare from a clean checkout at {tag}")
        if name != pubspec_version().partition("+")[0]:
            raise ReleaseError("the release version must match the tagged pubspec.yaml")
        if "arm64" not in sources:
            raise ReleaseError("release assets require an arm64 APK")
        build = release_build(name, expected, {
            flavor: apk_version(aapt2, path, require_agent_phone=True) for flavor, path in sources.items()})
        for flavor, path in sources.items():
            validate_release_apk(path, flavor, source, signer, apksigner)
        record = validate_source_record(args.third_party_sources, {f: asset_item(p) for f, p in sources.items()})
        notices = {file: tagged_notice(source, file) for file in SOURCE_FILES[:2]}
    except (ReleaseError, ApkJniError, OSError, ValueError, zipfile.BadZipFile) as e:
        sys.exit(str(e))

    args.out.mkdir(parents=True, exist_ok=True)
    assets = {}
    for flavor, path in sources.items():
        asset = f"dsh-go-{name}-{flavor}.apk"
        target = args.out / asset
        shutil.copyfile(path, target)
        entry = asset_item(target)
        if args.base_url:
            entry["url"] = args.base_url.rstrip("/") + "/" + asset
        assets[flavor] = entry

    patches = []
    if args.delta_from and "arm64" in assets:
        try:
            for old_tag in previous_releases(tag, args.delta_from):
                old = published_apk(old_tag, CACHE)
                old_name, old_code = apk_version(aapt2, old)
                patch = patch_from(old, f"{old_name}+{old_code}", args.out / assets["arm64"]["name"], name, args.out)
                if patch:
                    patches.append(patch)
        except (ReleaseError, apk_delta.DeltaError) as e:
            sys.exit(str(e))

    manifest = {
        "schema": 1,
        "version": f"{name}+{build}",
        "tag": tag,
        "title": f"Agent Phone {name}",
        "source": source,
        "publishedAt": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "notes": args.notes.read_text(encoding="utf-8").strip() if args.notes else "",
        "page": f"https://github.com/{REPO}/releases/tag/{tag}",
        "assets": assets,
    }
    if patches:
        manifest["patches"] = {"arm64": patches}
    (args.out / "update.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    notices["SOURCE.md"] = source_notice(source, build, assets)
    notices[SOURCE_RECORD] = record
    for file, data in notices.items():
        (args.out / file).write_bytes(data)
    files = [item["name"] for item in (*assets.values(), *patches)] + [*SOURCE_FILES, "update.json"]
    sums = [f"{sha256(args.out / file)}  {file}" for file in files]
    (args.out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="ascii", newline="\n")

    try:
        built = f"{decode(build):%Y-%m-%d %H:%M} UTC+8"
    except ValueError:
        built = "custom build number"
    print(f"Agent Phone {name}+{build} ({built})")
    print(f"{args.out}:")
    for line in sums:
        print("  " + line)
    print(f"\nPrepared locally only. Verify with services/share-worker/scripts/publish-release.sh {args.out} --dry-run")


if __name__ == "__main__":
    main()
