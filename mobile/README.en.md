# Agent Phone for Android

[简体中文](README.md)

Agent Phone is an unofficial derivative of [DSH Go](https://github.com/ccch1mneyyy/dsh-go) by ccch1mneyyy. Some of the documentation below describes the upstream project; upstream release links do not provide Agent Phone builds.

### Custom pets

Agent Phone does not bundle the upstream whale pets. Open **Settings → Pet → Import** to choose your own theme ZIP. See the [pet-pack guide](docs/pets/README.en.md) for the format.

<p align="center">
  A mobile client for DeepSeek Harness. Android is released; iOS is in development and device testing, and currently needs a Mac build signed with your own team (<a href="app/ios/README.md">iOS project</a> · <a href="docs/architecture.md">architecture</a>).
</p>

<p align="center">
  <a href="https://github.com/ccch1mneyyy/dsh-go/releases/latest"><img alt="Android 8+" src="https://img.shields.io/badge/Android-8%2B-4B67B4?style=flat-square&logo=android&logoColor=white&labelColor=2B3245"></a>
  <a href="LICENSE"><img alt="License AGPL-3.0" src="https://img.shields.io/badge/license-AGPL--3.0-4B67B4?style=flat-square&labelColor=2B3245"></a>
  <a href="https://forum.dshtui.com"><img alt="Forum" src="https://img.shields.io/badge/forum-forum.dshtui.com-4B67B4?style=flat-square&labelColor=2B3245"></a>
  <a href="https://qm.qq.com/q/OEy2RqZnqY"><img alt="QQ group 1132118290" src="https://img.shields.io/badge/QQ%20group-1132118290-4B67B4?style=flat-square&logo=tencentqq&logoColor=white&labelColor=2B3245"></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/319451"><img src="https://trendshift.io/api/badge/trendshift/repositories/319451/daily" alt="DSH Go: #1 on Trendshift's all-language daily ranking (2026-10-30)" width="250" height="55"></a><br>
  <sub>#1 on Trendshift's all-language daily ranking · 2026-10-30</sub>
</p>

<br>

<a id="download"></a>
<h3 align="center">Download DSH Go</h3>

<p align="center">Get the latest APK from GitHub Releases or the download page at go.dshtui.com. Most phones need the arm64 package.</p>

<p align="center">
  <a href="https://github.com/ccch1mneyyy/dsh-go/releases/latest"><img alt="Download from GitHub Releases" src="https://img.shields.io/badge/GitHub%20Releases-Download%20APK-4B67B4?style=for-the-badge&logo=github&logoColor=white&labelColor=2B3245"></a>&emsp;<a href="https://go.dshtui.com/download"><img alt="Download from go.dshtui.com" src="https://img.shields.io/badge/go.dshtui.com-Download%20page-4B67B4?style=for-the-badge&labelColor=2B3245"></a>
</p>

<p align="center">
  <b>Thank you for supporting DSH Go! The download page currently provides Android APKs. iOS is still in development and device testing, with no public install package yet; HarmonyOS work continues too.</b>
</p>

<p align="center">
  <a href="https://github.com/ccch1mneyyy/dsh-go/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ccch1mneyyy/dsh-go?style=flat-square&logo=github&label=Star&color=4B67B4&labelColor=2B3245"></a>
</p>

<p align="center">
  <sub>New here? Start with the <a href="docs/guide/README.md">user guide</a>, and bring questions to the <a href="#community">forum and QQ group</a>.</sub><br>
  <sub>An early test build signed with a different key can't be updated in place: uninstall it first, which clears your chats, the Linux environment and settings.</sub>
</p>

<br>

<h3 align="center">Runs on your phone. Drives your computer.</h3>

<p align="center">A Linux environment built in, no root and no Termux. Switch to the DSH on your computer in one tap.</p>

<br>

<h3 align="center">Chime in, interrupt, stay tidy</h3>

<p align="center">Send a message while DSH is replying, and tap "Send now" whenever you like. Finished steps fold into one line.</p>

<br>

<h3 align="center">Native, with the web interface one tap away</h3>

<p align="center">Switch between the native app and the official web interface on the same chat. It reopens in whichever you used last.</p>

<br>

<h3 align="center">Share cards, replays and links</h3>

<p align="center">Turn a reply into a share card. Share a whole chat as a link that replays in any browser, end-to-end encrypted.</p>

<br>

<h3 align="center">Landscape and tablets</h3>

<p align="center">New layouts for landscape phones and tablets: the sidebar stays, content stays centered, the keyboard never crowds.</p>

<br>

<h3 align="center">Colors and home screen icons</h3>

<p align="center">Six accent colors, your wallpaper's, or your own. Four home screen icons and three icon styles.</p>

<br>

<h3 align="center">English and 中文</h3>

<p align="center">The whole app speaks both. It follows your system, or pick one in Settings.</p>

<br>

## Features

Agent Phone combines a chat interface, an on-device runtime and remote connections. It is a third-party project built on [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness). The DSH engine runs on your phone; model requests are still handled by the model provider you configure.

- **On-device runtime:** install Ubuntu, Node.js and DSH from the app without Root or a separate Termux installation.
- **Remote connections:** use DSH on a computer or server through SSH or [DSHarness Remote](https://github.com/liguobao/ds-harness-remote), developed by Li Guobao (liguobao).
- **Chat and tools:** switch models, send images, use voice input, and respond to tool approvals and questions. Chat and web interfaces are available.
- **Plugin interfaces:** use native tool cards, forms and panels from plugins adapted for DSH Go. This repository includes an SDK, guides and examples.
- **Feature scope:** This version does not include Phase, phone control, screen reading, or taps in other apps. The local engine and remote connections are still available.
- **Sharing and appearance:** share, export and replay conversations, and customize themes, icons and pets.

Capabilities depend on the host and connection. DSHarness Remote currently accepts image attachments only, does not open the web interface inside the app, limits plugin management to enabling or disabling plugins, and does not support DS Bot or conversation-log export. See [Engine and remote hosts](docs/guide/en/03-engine-hosts.md).

## Install

Installation requires Android 8.0 (API 26) or later. The **arm64** package on the Releases page is for typical 64-bit Android phones; the x64 package for x86_64 devices and emulators is under “Other builds” at the end of the release notes. This repository has no 32-bit ARM build.

1. Download the APK for your device architecture from [GitHub Releases](https://github.com/ccch1mneyyy/dsh-go/releases/latest) or the [download page](https://go.dshtui.com/download), and follow Android's prompt to allow that installation source.
2. On first launch, choose an on-device runtime or a remote host.
3. Configure a model and its credentials for the selected host, then start a conversation. Some remote providers must be configured on the host itself.

A remote-only setup does not need a local runtime on the phone. Follow the [user guide](docs/guide/README.md) for setup.

The local engine uses compatible PRoot startup by default. Direct startup is off by default in Developer options; see [Troubleshooting](docs/guide/en/11-faq.md) for compatibility and fallback behavior. The current Android build targets APK sideloading, not Google Play distribution.

## Data and permissions

Model requests and attachments you send go to the provider you configure.

“Send anonymous usage statistics” is on by default. You can turn it off during onboarding or in Settings → Privacy and sharing. See [Troubleshooting](docs/guide/en/11-faq.md) for the fields collected and what happens when it is disabled. Review content before sharing it; recipients can save a copy of a shared link or file's contents.

## Risks and disclaimer

DSH Go is an unofficial community project. It is not affiliated with, endorsed by, or a representative of DeepSeek. Before using it, please understand:

- **AI is fallible:** answers, code and actions may be wrong, and malicious instructions in web pages, messages or files may mislead it. Verify important results; do not rely solely on AI output for high-stakes medical, legal or investment decisions.
- **Tools have real effects:** Commands and file changes on local or remote hosts can cause data loss, privacy breaches or harm to accounts, funds or devices. Keep confirmations enabled and grant only necessary permissions.
- **Third-party services and costs:** models, remote hosts and plugins operate under their own terms. Data handling, availability and charges depend on the services and configuration you choose. Running locally does not mean the model is offline or that data never leaves the device.
- **Take precautions:** back up important data, connect only to trusted hosts, install only trusted plugins, and monitor model usage and costs. Do not leave AI unattended on irreversible or high-risk tasks.
- **No warranty and limits of liability:** to the extent permitted by applicable law, the software is provided “as is,” without guarantees of accuracy, continuous availability or fitness for a particular purpose. See sections 15–17 of [LICENSE](LICENSE) for warranty disclaimers and liability limits. This notice does not exclude or limit liability that cannot legally be excluded or limited, or reduce your statutory rights.

## FAQ

<details>
<summary><b>Is this an official DeepSeek app?</b></summary>
<br>

No. DSH Go is an unofficial client made by the community, built on the open-source [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness). DSH itself runs on your phone; model requests go to the provider you configure, so it needs a connection and bills your account with that provider.

</details>

<details>
<summary><b>Is it safe?</b></summary>
<br>

The local web interface only answers to the app itself. Shared links are end-to-end encrypted: the key lives only in the link, and the server never sees the content, but anyone with the complete link can read and save it. Safeguards cannot guarantee zero risk. See [Risks and disclaimer](#risks-and-disclaimer).

</details>

<details>
<summary><b>Will the system kill it in the background?</b></summary>
<br>

Some battery savers hold apps back. When that happens, DSH Go tells you and opens the right setting, on vivo, Xiaomi, Huawei, Honor and OPPO.

</details>

<details>
<summary><b>What phone do I need?</b></summary>
<br>

Android 8 or later. On a phone, download the package on the Releases page; the x86_64 build for emulators is under “Other builds” at the end of the release notes. Running DSH on the phone needs the built-in environment, so keep about 1 GB free; connecting to DSH on a computer or server doesn't.

</details>

<details>
<summary><b>Is it open source?</b></summary>
<br>

Yes. The code is in this repository under [AGPL-3.0](LICENSE); `sdk/` and `examples/` are MIT. The DSH Go name and logo, and the mascots Deepy and Whale girl, are not covered by the open-source license; see [ASSETS.md](ASSETS.md). Credit requirements for forks and redistributed builds are in [License scope and redistribution](#license-scope-and-redistribution).

</details>

## Build from source

The following workflow targets **Linux x86_64**. The toolchain script currently defaults to JDK 17, Flutter 3.47.7 and the Android SDK/NDK. The app requires Dart `^3.13.5`. Prepare Bash, Git, curl, tar, unzip, xz, Python 3, zstd (for unpacking zstd-compressed deb archives when Python does not provide `compression.zstd`), file and standard GNU utilities. Resolving Ubuntu package locks again also requires gpgv.

Start with the complete source tree and project assets. Fonts, images and other files declared in `app/pubspec.yaml` are build inputs. The following script generates the runtime bundle.

```bash
git clone https://github.com/ccch1mneyyy/dsh-go.git
cd dsh-go

bash tooling/setup-toolchain.sh
source tooling/env.sh
flutter --version
java -version

bash runtime/build-runtime.sh arm64-v8a
DSH_BETA_TOKEN_FILE= bash tooling/build-apk.sh -f arm64 --keep-daemon
```

The toolchain script downloads the SDK/NDK and emulator images and runs Android SDK license acceptance. Its default location is `~/dev`; set `DEV_ROOT` to use a separate directory. The script reuses existing installations, so check their versions before building.

The output is `app/build/app/outputs/flutter-apk/app-arm64-release.apk`. Runtime assembly uses the versions and verification data pinned in the repository and needs network access to download dependencies. `DSH_BETA_TOKEN_FILE=` leaves out the maintainer's beta-channel token. `--keep-daemon` preserves Gradle daemons, which is useful when working on other Android projects at the same time.

For an x86_64 APK, generate its runtime first:

```bash
bash runtime/build-runtime.sh x86_64
DSH_BETA_TOKEN_FILE= bash tooling/build-apk.sh -f x64 --keep-daemon
```

Without `app/android/key.properties`, a local release build uses debug signing. It cannot replace an official installation signed with a different key. Use a test device and preserve existing data; do not uninstall your daily-use app just to resolve a signing mismatch. Do not commit signing keys or their configuration.

To inspect APK build commands without building:

```bash
DSH_BETA_TOKEN_FILE= bash tooling/build-apk.sh --dry-run -f all
```

## Repository layout

| Path | Contents |
| --- | --- |
| `app/` | Flutter interface, Android Kotlin code, and iOS Swift/WidgetKit code under development |
| `packages/dsh_client/` | Dart client for the DSH Web API |
| `packages/dsh_remote/` | Dart client for DSH Remote |
| `runtime/` | Android Linux runtime assembly, iOS runtime specialization, engine patches and the app bridge |
| `sdk/plugin-kit/` | Native plugin authoring kit, used from the repository and not published to npm |
| `examples/plugins/` | Example plugins |
| `docs/guide/`, `docs/plugins/`, `docs/pets/`, `docs/live2d/` | User guides, plugin development, pet packs and Live2D companion authoring |
| `tooling/` | Toolchain, Android APK/iOS development build, and diagnostic scripts |
| `services/`, `site/`, `infra/` | Companion sharing service, website and deployment materials |

## Contribute

Report bugs and suggest improvements in [Issues](https://github.com/ccch1mneyyy/dsh-go/issues). For code, documentation and translation changes, start with [CONTRIBUTING.en.md](CONTRIBUTING.en.md). Plugin authors can use the [plugin guides](docs/plugins/en/README.md) and [SDK](sdk/plugin-kit/README.en.md).

Report security issues through [SECURITY.en.md](SECURITY.en.md). Keep vulnerability details and credentials out of public issues.

<a id="community"></a>

## Community

- **Forum**: [forum.dshtui.com](https://forum.dshtui.com)
- **QQ group**: `1132118290` ([join](https://qm.qq.com/q/OEy2RqZnqY))
<!-- Telegram: link to come, add a line here -->

## Friends' Links

- **[DSH-TUI](https://dshtui.com/)**: the interactive terminal UI for DeepSeek Harness by the same author — the desktop counterpart to DSH Go, with a pixel whale, live status and time travel ([GitHub](https://github.com/ccch1mneyyy/dsh-TUI)).

## License scope and redistribution

The code is open source under [AGPL-3.0](LICENSE), and forking it to study, self-host or build on is welcome. Please respect the original author and project origin:

- **Please contact the author before making modifications.** If you plan to modify this project, develop it further or publish a derivative product, please contact the original author, ccch1mneyyy, through [Issues](https://github.com/ccch1mneyyy/dsh-go/issues) or the [community](#community) in advance and describe your intended use and plans.
- **Please credit the upstream repository and author in forks.** When publishing a modified version, please clearly credit <https://github.com/ccch1mneyyy/dsh-go> and the original author, [ccch1mneyyy](https://github.com/ccch1mneyyy), in the repository README, in-app About screen and release page. Retain copyright, license and modification notices as required by the applicable license.
- **No unauthorized commercial reskins.** Do not use this project's brand graphics or protected assets, including Deepy and Whale girl, in reskinned products for sale, paid distribution or other commercial products without permission. Do not violate the applicable license by removing required copyright and license notices or distributing derivative code without the required source, or impersonate the original author or an official release.
- **The name and assets are separate.** The DSH Go name and logo, and the Deepy and Whale girl mascots, are not covered by AGPL-3.0. Ship a modified build under your own name and assets; see [ASSETS.md](ASSETS.md).

**License clarification:** AGPL-3.0 permits modification, redistribution and commercial use subject to its terms. Advance contact and the requested credit locations above are collaboration requests from the author, not additional restrictions on the code license. Brand and asset use remains subject to their own terms; this notice does not change the licenses of `sdk/`, `examples/` or third-party content.

## License and acknowledgments

This project is licensed under [AGPL-3.0](LICENSE). `sdk/` and `examples/` remain **MIT**. Third-party code and assets retain the terms stated in their own notices.

- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness): the agent DSH Go runs and connects to.
- [DSH-TUI](https://github.com/ccch1mneyyy/dsh-TUI): home of the mascots, Deepy and Whale girl.

DeepSeek Harness, PiPilot, DS Bot, DSH Remote and other third-party components and assets retain their own licenses and attribution. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for sources and terms.

The DSH Go name, logo and mascots (Deepy and Whale girl) are not covered by the AGPL; see [ASSETS.md](ASSETS.md) for their terms.

<sub>Remote connections follow the [ds-harness-remote](https://github.com/liguobao/ds-harness-remote) (MIT) protocol; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for sources and terms.</sub>

<br>

<p align="center"><sub>DSH Go is an unofficial client made by the community. It is not affiliated with or endorsed by DeepSeek. DeepSeek names and marks belong to their owners.</sub></p>
