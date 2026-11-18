# 发版与应用内更新

App 以 APK 分发、不上商店，更新靠 App 自己查 GitHub Releases、下载、校验、调系统安装器。本文是发版约定和步骤，以及更新链路的取舍。代码在 `app/lib/update/`（检查、下载、校验）、`app/lib/state/update_state.dart`（状态与节流）、`app/lib/ui/update/`（设置行、弹窗）、`app/android/.../update/`（PackageInstaller 安装）。

> **正式发版前必须先换成固定的发布密钥**（见「签名」）。存在 `app/android/key.properties` 时 release 使用其中的发布密钥；缺少配置时仅为本地构建回落到 debug key，不可用于正式发布。

## 资产约定

Agent Phone 的公开更新源为 `aqing520/agent-phone` 的 GitHub Releases。默认配置只访问本仓库的发布资产及其公共 GitHub 加速地址。自有镜像和内测源须在构建时显式指定。`dshtui.com` 和旧 R2、下载 CDN、香港桶都是上游历史设施。Agent Phone 的发布脚本不读取这些渠道的凭据、不上传到这些渠道。

正式版统一提供 arm64 安装包。`update.json` 供更新清单回退读取，`SHA256SUMS` 供缺少 GitHub digest 时校验 APK，`*.dshdelta` 是从最近几个旧版升上来的增量补丁（`docs/design/delta-update.md`），都由 App 自己用，不要求用户手动下载。GitHub 自动生成的 Source code 压缩包是源码快照，不是安装包。

| 项 | 约定 | 例子 |
|---|---|---|
| 版本名 | `app/pubspec.yaml` 的 `version: X.Y.Z[-pre]`，即 versionName；后面的 `+1` 只是占位 | `1.2.0` |
| 构建号 | Android versionCode，由 `tooling/build-apk.sh` 按构建时间生成，见「构建号」 | `10251234` |
| tag | `v` + 版本名（不带 `+N`） | `v1.2.0`、`v1.3.0-beta.1` |
| APK | 打包文件名前缀 `dsh-go-` 仅用于兼容现有更新解析；产品和 GitHub Release 标题均为 Agent Phone。`dsh-go-<版本名>-<flavor>.apk`，正式版 flavor 固定为 `arm64`；文件名不带 `+N`（GitHub 会改写 `+`） | `dsh-go-1.2.0-arm64.apk` |
| 增量补丁 | `dsh-go-<版本名>-from-<旧版本名>-arm64.dshdelta`，只发不到整包 60 % 的 | `dsh-go-1.2.0-from-1.1.0-arm64.dshdelta` |
| 校验和 | `SHA256SUMS` 覆盖所有 APK、补丁、清单和许可／源码说明 | `<hex>  dsh-go-1.2.0-arm64.apk` |
| 清单 | `update.json`（schema 1），镜像和自托管源都读它 | 见下 |
| 源码和许可 | `SOURCE.md`、`THIRD_PARTY_SOURCES.md`、`THIRD_PARTY_NOTICES.md`、`LICENSE.txt` 与 APK 同目录分发 | |
| 更新说明 | Release 正文提供同版本源码和许可入口；App 弹窗使用 `update.json` 的 `notes` | |

`update.json` 由脚本生成，不要手写：

```json
{
  "schema": 1,
  "version": "1.2.0+10251234",
  "tag": "v1.2.0",
  "title": "Agent Phone 1.2.0",
  "source": {
    "tag": "v1.2.0", "commit": "<完整的 40 位提交 SHA>",
    "source": "https://github.com/aqing520/agent-phone/tree/<完整的 40 位提交 SHA>"
  },
  "publishedAt": "2026-11-01T08:00:00Z",
  "notes": "## 新功能\n…",
  "page": "https://github.com/aqing520/agent-phone/releases/tag/v1.2.0",
  "assets": {
    "arm64": { "name": "dsh-go-1.2.0-arm64.apk", "size": 180107933, "sha256": "…" }
  },
  "patches": {
    "arm64": [
      { "from": "<1.1.0 APK 的 SHA-256>", "fromVersion": "1.1.0+10201200",
        "name": "dsh-go-1.2.0-from-1.1.0-arm64.dshdelta", "size": 13278848, "sha256": "…" }
    ]
  }
}
```

`assets.*.url` 可省：省略时 App 用 tag 和文件名拼 GitHub 下载地址；自托管时写绝对地址或相对 `update.json` 的地址（脚本的 `--base-url`）。自托管目前没有自动发布功能；下载页面仍须同时提供该版对应源码和许可。`patches` 没有补丁时不出现，条目不带 `url`：补丁在每条线路上都和 APK 在同一目录。旧版 App 不认识它，照常下整包。

版本比较按 semver：预发布版低于正式版（`1.3.0-beta.1 < 1.3.0`），`+N` 只在两边都有时才参与比较（GitHub API 只给 tag，不带 `+N`）。所以 **同一个版本名重新打包不会被当成新版本**，要发就升版本名。

## 构建号

所有 APK，不论开发包还是正式包，一律用 `tooling/build-apk.sh` 出：

```sh
tooling/build-apk.sh                 # release arm64（真机）
tooling/build-apk.sh -f x64          # 本地模拟器验证，不公开发布
tooling/build-apk.sh -f all          # 双架构本地验证；正式发版不用此选项
tooling/build-apk.sh --dry-run -f all   # 只打印要执行的命令
```

脚本把构建时间编成 versionCode，传给 `--build-number`，同时传 `--build-name` 和 `DSH_APP_VERSION`：

```text
versionCode = (年 - 2026) × 10^8 + MMDDhhmm      时钟固定按 UTC+8
2026-10-25 12:34 → 10251234    2027-01-02 03:04 → 101020304    2046-12-31 23:59 → 2012312359
```

- **一条序列**：开发包和正式包按同一个时钟编号；更高版本号仍需与设备上已安装的同包名应用使用相同签名，才能覆盖安装。Debug 签名测试包不能直接覆盖为不同签名的发布包。
- **每次都变**：系统和厂商 ROM 常按「包名 + versionCode」决定要不要刷新缓存的图标。号一直不变时，换了图标资源，通知和状态栏也可能一直显示旧的（vivo OriginOS 上出现过）。
- **看得懂**：设置里显示 `1.0.0 (10251234)`，一眼知道是 10 月 25 日 12:34 打的包；`python3 tooling/build_number.py --decode N` 可反查。
- **上限**：Android 限 2,100,000,000，这套编码用到 2046 年底。
- **绕过脚本时**（`flutter run`、IDE）：`build.gradle.kts` 发现 versionCode 还是占位的 `1`，就按同一公式现算。否则装到已有新号的设备上会被当成降级，`flutter run` 会先卸载旧版再装，数据全清。
- 测试：`python3 -m unittest discover -s tooling -p 'test_*.py'`。

## Agent Phone 发版步骤（仅 GitHub）

1. 修改 `app/pubspec.yaml` 的版本名并同步指南，审阅变更并提交。给该提交打对应的 `v<版本名>` 标签，发版时不移动标签或用同一版本名重发不同 APK。只在干净的标签 checkout 构建，且勿把旧 APK 当作该提交的产物。
2. 配置固定发布密钥，准备 ARM64 运行时，再运行 `tooling/build-apk.sh --public-release`。它写入随签名保护的源码身份，普通测试包和内测包不要走公开发版流程。准备及上传工具都用 `AGENT_PHONE_SIGNER_SHA256` 与 APK 的实际证书比对，并拒绝 Debug 签名；指纹应来自独立确认的发布证书，不要从待上传 APK 盲目复制。构建后先做真机安装／升级验证。
3. 按 [Android 对应源码核验](android-distribution-sources.md) 检查实际 APK，补齐这个发行物的对应源码、第三方告知与构建材料。把查找/下载指引写入一份 UTF-8 Markdown，使用独立的 `APK SHA-256: <64 位小写十六进制>` 行标注每个实际发布的 APK。文件中的链接必须对应实际打包版本、公开发布时有效；清单模板、未经核验的材料或旧版报告不能当作已完成。工具核对哈希和分发路径，不能代替对所需源码与许可的人工核验。
4. 本地生成发布目录（要求新目录或空目录），然后无网络预演。`--delta-from` 默认 `0`，有 Agent Phone 的旧版安装包时才考虑显式启用，绝不向上游查包。

   ```sh
   export AGENT_PHONE_SIGNER_SHA256='<预先确认的发布证书指纹>'
   python3 tooling/release_assets.py --third-party-sources /path/to/verified-sources.md --notes /path/to/notes.md
   services/share-worker/scripts/publish-release.sh dist --dry-run
   ```

5. 明确确认后，把同版本标签推至 `aqing520/agent-phone`。`--draft` 只建并验证草稿，`--publish` 才会公开；现有已发布版本不会被覆盖。脚本检查 GitHub 仓库是公开的、远端版本标签与 APK 内的提交一致，给下载页加入对应源码与许可链接，并读回草稿所有文件核对哈希后才允许公开。

   ```sh
   services/share-worker/scripts/publish-release.sh dist --draft
   # 审阅草稿、确认对应源码可获取之后再执行：
   services/share-worker/scripts/publish-release.sh dist --publish
   ```

6. 验证公开页面和 APK 下载旁的源码入口可在未登录情况下访问，并在已装同签名上一版的真机上验证更新。镜像／内测渠道暂不由此脚本部署或发布；旧的 `--github`、`--no-dl`、`--no-cn`、`--skip-verify` 参数已停用。

## 统计

下载、更新检查和 App 的匿名使用报告都记在 Cloudflare 的 Analytics Engine 里，不存 IP；数据模型和隐私说明见 `docs/design/share-links.md` §15。

**开通**（一次，我们的账号已经做完）。`wrangler.jsonc` 绑定了三个数据集，`provision.sh` 默认带着部署；没开 Analytics Engine 的账号带着它们部署会失败，所以先开通。没开通期间（`--no-analytics`）下载和更新检查不计数，`/api/usage/v1` 是 404。

1. 在 Cloudflare 后台的 Analytics Engine 页面开通（免费计划可用）。
2. `USAGE_SECRET` 和带上数据集的部署：

   ```sh
   cd services/share-worker
   (umask 077; openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n' > <USAGE_SECRET 文件>)
   CLOUDFLARE_API_TOKEN="$(cat <token 文件>)" CLOUDFLARE_ACCOUNT_ID="$(cat ~/keys/dshgo-cloudflare-account-id)" \
     npx wrangler secret put USAGE_SECRET < <USAGE_SECRET 文件>
   CF_TOKEN_FILE=<token 文件> scripts/provision.sh deploy   # 默认绑定 DOWNLOADS、CHECKS、USAGE（数据集第一次写入时自动建）
   ```

3. 点一次下载页的按钮，几分钟后 `scripts/stats.sh` 有数。没开通 Analytics Engine 的账号（fork）部署时要带 `--no-analytics`（或 `DSH_ANALYTICS=0`），否则部署失败。

- 读数用的 token 要加一项权限：Account → Account Analytics → Read（部署用的那把可以一起加，也可以另开一把只读的）。
- `USAGE_SECRET` 不要换：换了以后安装编号的哈希对不上，留存从那天断开。丢了也只是从头算，不影响 App。
- 没设 `USAGE_SECRET` 时 `/api/usage/v1` 是 404，下载和更新检查照常计数。

**看数**：

```sh
CF_TOKEN_FILE=<token 文件> scripts/stats.sh              # 最近 14 天（UTC+8）
CF_TOKEN_FILE=<token 文件> scripts/stats.sh --days 30
scripts/stats.sh --dry-run                               # 只打印 SQL
scripts/github-downloads.sh                              # GitHub 每个 release 每个文件的累计下载数
```

AE 只留约 3 个月，想长期保留就定期把输出存下来。

## 签名

Android 只接受和已装版本**同一签名**的覆盖安装。`build.gradle.kts` 从 `app/android/key.properties` 读取发布签名；配置缺失时回落到打包机器的 `~/.android/debug.keystore`，仅供本地构建。正式发版必须先配置发布密钥。

做法：生成一把发布密钥，只在发版机器上用，并离线备份（丢了等于以后再也发不了更新，所有用户都得卸载重装）。

```sh
keytool -genkeypair -v -keystore /home/you/keys/dsh-release.jks -keyalg RSA -keysize 4096 -validity 36500 -alias dsh
```

`app/android/key.properties`（**加进 .gitignore，不要提交**）：

```properties
storeFile=/home/you/keys/dsh-release.jks
storePassword=…
keyAlias=dsh
keyPassword=…
```

`app/android/app/build.gradle.kts`：

```kotlin
import java.util.Properties

val keyProps = Properties().apply {
    rootProject.file("key.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}

android {
    signingConfigs {
        create("release") {
            storeFile = keyProps.getProperty("storeFile")?.let { file(it) }
            storePassword = keyProps.getProperty("storePassword")
            keyAlias = keyProps.getProperty("keyAlias")
            keyPassword = keyProps.getProperty("keyPassword")
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName(if (keyProps.isEmpty) "debug" else "release")
        }
    }
}
```

**换钥匙的代价**：已经装了 debug 签名版的人，第一次更新会被系统拒绝。App 会在安装前比对签名，提示「签名不一致，不能直接覆盖」，引导去发布页下载；他们得**卸载旧版再装新版一次**，卸载会清空本地数据（对话、Linux 环境、设置、Keystore 里的 API Key）。之后的更新都正常。

想让老用户免卸载，有两条路，各有代价：

| 做法 | 好处 | 代价 |
|---|---|---|
| 把现在那台机器的 `debug.keystore` 当发布密钥长期用 | 老用户无感 | 证书是「Android Debug」，口令是公开的 `android`，安全全靠文件不外泄；以后想换还是要走一次这个流程 |
| APK 签名 v3 密钥轮换（`apksigner rotate` 生成 lineage，用 `apksigner sign --lineage` 重签） | Android 9+ 的老用户直接覆盖更新 | AGP 不直接支持，要在构建后手工重签；Android 8.x（minSdk 26）不认 lineage，仍需重装 |

App 的签名预检认 lineage：新包的签名历史里含已装版本的签名，就当作一致。

## App 怎么更新

```text
启动 6 秒后（每天最多一次，设置里可关）或 设置 → 关于 → 检查更新
  → 依次问元数据源（见「镜像与回落」），第一个给出可用版本的为准
  → 比已装版本新、且没被「跳过」→ 弹窗：版本、下载大小（有补丁可用时是补丁的大小）、更新说明
  → 立即更新：有补丁就下补丁、用已装 APK 拼出新包，否则下整包；都在 cache/updates/，断点续传，可取消，关掉弹窗也继续
  → SHA-256 校验（不一致删掉、换下一个源从头下）
  → 没有「安装未知应用」权限 → 引导到系统设置，回来自动继续
  → 预检：包名、签名和已装版本一致
  → PackageInstaller 会话安装，系统弹确认框 → App 被替换并退出
```

- **节流**：成功检查后 24 小时内不再自动查；失败后 4 小时内不重试；时钟被往回拨视为到期。手动检查不受限。
- **跳过这个版本**：这个版本不再自动弹，有更新的版本照常提醒；「关于」里显示「已跳过」。手动检查仍会打开弹窗。
- **稍后**：只关弹窗，下次自动检查（次日）还会提醒。
- **上次的结果会缓存**：重启后不联网也能看到「新版本」标记；装好新版后自动清掉缓存和残留安装包。
- **导出安装包**：「可以安装」，或签名不一致 / 安装被拦截的失败界面，可以「导出安装包」：把校验过的包复制到 `Download/DSH-Go/`（MediaStore，文件名就是清单里的资产名）。这是给「首次安装被厂商拦、只能自己重签」的人兜底，不是常规更新路径——重签后的包和官方签名不同，App 内更新会一直停在「签名不一致」，以后每版都得手动重签覆盖装。能走 Shizuku / 本机 ADB 就别走这条路。导出只是复制，`cache/updates/` 里的原文件、安装和清理逻辑都不变（提权安装器要求文件直接在 `cache/updates` 下，别把下载目录搬走）。
- **磁盘**：开始下载前要求可用空间 ≥ 安装包 × 2 + 64 MB（下载 + 安装暂存）。走补丁也是这个门槛：补丁拼完就删，峰值仍是安装暂存那一刻。
- 安装用 PackageInstaller 会话（把文件流写进会话），不用 FileProvider，也不需要 `content://`。

### 增量更新

`update.json` 可以带 `patches`，按 flavor 列出从某个旧 APK 到这一版 APK 的补丁：

```json
"patches": {
  "arm64": [
    { "from": "<旧 APK 的 SHA-256>", "fromVersion": "1.0.7", "name": "<补丁文件名>", "size": 12345678, "sha256": "<补丁文件的 SHA-256>" }
  ]
}
```

补丁和 APK 放在同一个版本、同样的镜像上，地址照 APK 的推：APK 地址的最后一段换成 `name`，然后是 GitHub 这一版的同名附件经各个镜像。缺字段的补丁条目直接忽略；APK 和补丁的 `name` 会成为下载目录里的文件名，必须是普通文件名（字母或数字开头，只含字母、数字和 `._+-`），否则那一项也忽略。没有 `patches` 的旧清单行为不变。

补丁格式 `DSHDLT01`，整数一律大端：

| 部分 | 内容 |
|---|---|
| 头（80 字节） | 8 字节 `DSHDLT01` · 32 字节旧 APK 的 SHA-256 · 32 字节新 APK 的 SHA-256 · u64 新 APK 长度 |
| `0x01` COPY | u64 旧 APK 里的偏移 · u64 长度：复制旧 APK 的这一段 |
| `0x02` DATA | u64 长度 · 这么多字节：原样写出 |
| `0x00` END | 结束；写出的必须正好是头里的长度，SHA-256 也要对上 |

App 这边（`app/lib/update/delta.dart`、`app/lib/state/update_state.dart`）：

1. **已装 APK 的哈希**：清单里有本机 flavor 的补丁时，才去算 `applicationInfo.sourceDir` 的 SHA-256，在后台 isolate 里算，按 versionCode + 安装时间缓存（`update_installed_sha256`），每个装上的包只算一次。检查要等它算完才算结束，所以弹窗一出来就是对的大小。
2. **用补丁**：某条补丁的 `from` 等于这个哈希 → 下载补丁（续传、换源、超时都和 APK 一样）→ 校验补丁的 SHA-256 → 头里的旧 APK 哈希、新 APK 哈希和长度都要对上 → 从已装 APK 流式拼到整包下载会用的同一个文件（先写 `.part`，对上了才改名）→ 长度和 SHA-256 等于清单里 APK 的 → 删掉补丁，后面的签名预检和 PackageInstaller 安装不变。
3. **回落**：上面任何一步失败 → 不提示，当场改下整包，并记住这一版不再试补丁（`update_patch_failed`）。没有 `from` 对得上的补丁不算失败，直接下整包。取消下载不算失败，下次接着下补丁。
4. **内存**：补丁顺序读、旧 APK 按偏移读，各一个 64 KiB 缓冲，边写边算哈希。180 MB、约 42 万个操作的合成补丁，桌面上（AOT）2.1 秒、常驻内存 8 MB。

补丁不改变信任链：它只是拿到同一个 APK 的另一种办法，最后核对的仍是清单里 APK 的 SHA-256，安装前照旧过签名预检。

## 镜像与回落

源列表集中在 `app/lib/update/update_config.dart`。元数据按下表从上到下问，下载按镜像顺序试。除了内测通道和 GitHub API，**上次成功的源排到最前**，连不上某个源的手机不会每次都先等它超时；GitHub API 哪怕上次成功也排最后。

| 源 | 用于 | 好处 | 坏处 |
|---|---|---|---|
| 内测通道 `go.dshtui.com/beta/update.json`（带通道令牌的包才有，永远排第一，不参与「上次成功排最前」） | 元数据 + APK（同一令牌） | 不公开；国内可达；发版即生效 | 令牌编在包里，可被提取；没令牌的包用不了 |
| 自有下载站 `dl.dshtui.com`（R2 公共桶，所有包默认都有） | 元数据 `/update.json`（最新公开版，资产带绝对地址）+ APK 和补丁 `/download/<版本>/<文件>`（下载也排第一） | 自己的，完全可控；不占 GitHub 配额；有补丁 | 流量和可达性要自己盯；国内速度看 Cloudflare 线路 |
| `github.com/…/releases/latest/download/update.json` | 元数据 + APK | 不占 API 配额；和 APK 同一个 CDN | 国内常慢或不通 |
| 公共加速镜像（默认 `ghfast.top`、`gh-proxy.com`） | 元数据 + APK | 零成本，国内大多能用 | 第三方：随时失效、换域名（几个月一换很常见），有的整段网络一律 403（`ghfast.top` 2026-11 起从我们机器出去全是 403，仍留在列表里，被拒只多一次请求）；能看到下载者 IP；大文件可能限速；理论上能篡改内容（见下） |
| GitHub API `releases/latest`（最后） | 元数据 | 官方；带 digest，不额外请求校验和 | 匿名 60 次/小时/IP，校园网、运营商 NAT 和代理出口下常常已经 403；回答里没有补丁；国内常超时 |

构建时可以改（`--dart-define`，不用改代码）：

| 变量 | 作用 |
|---|---|
| `DSH_UPDATE_MIRROR=https://…` | 配置本发行版的自有下载站（同样的 `/update.json` + `/download/<版本>/<文件>` 布局）；设成空串就不用自有站，只剩 GitHub 和加速镜像 |
| `DSH_UPDATE_FEED=https://…/update.json` | 只换要问的清单，下载仍先试自有站；空串 = 不问清单 |
| `DSH_UPDATE_MIRRORS=a,b` | 换掉公共加速镜像列表（前缀 + 完整 GitHub 地址）；空串 = 不用 |
| `DSH_BETA_CHANNEL_ORIGIN` | 指定本发行版内测通道的域名，配合内测令牌使用 |
| `DSH_WORKSHOP_ORIGIN=https://…` | 换创意工坊的部署，默认 `https://go.dshtui.com`；空串 = 这个包不带工坊入口 |

公共镜像要定期确认还活着，失效的直接从列表删。

下载的超时策略：连接 15 秒、30 秒没收到数据算断线；同一个地址断线续传最多再试 2 次，连不上或返回错误就换下一个源。补丁和 APK 用同一套。

## 安全

- **SHA-256**：来自元数据（API 的 `digest`、`update.json` 的 `sha256`，都没有时读 `SHA256SUMS`）。缺校验和的版本 App 不装，只给发布页链接。它防的是传输损坏，以及只篡改 APK 的镜像。
- **签名**才是最后一道防线：镜像如果同时篡改清单和 APK，校验和也能对上，但它签不出我们的签名，系统和 App 的预检都会拒绝覆盖安装。所以发布密钥必须固定且保密，绝不能用一把谁都拿得到的钥匙。
- **降级**：系统拒绝 versionCode 更低的包；App 也只在版本更新时提示。正式包要在升完版本名之后、用 `build-apk.sh` 现打，不要拿早先打好的包去发：手机上若装着更晚打的旧版本名开发包，App 会提示更新，系统却会按降级拒装。

## 出问题时 App 的表现

| 情况 | 表现 |
|---|---|
| 还没有 release、仓库私有、限流、断网 | 「关于」里显示「暂时检查不了」；手动检查弹一条提示，不弹错误对话框；自动检查静默 |
| 新版没有本机 flavor 的 APK | 弹窗说明，按钮改为「打开发布页」 |
| 下载断了 | 保留已下载部分，「重试」接着下 |
| 校验不通过 | 删除文件，换源重下；都不通过就报错 |
| 签名不一致 | 安装前拦下，说明要卸载重装，按钮「打开发布页」「导出安装包」 |
| 用户在系统确认框里取消 | 回到「安装包已下载」，可再装 |

## 真机验证清单（尚未在真机上跑过）

- [ ] 首次安装：「安装未知应用」引导页能打开，授权后回到 App 自动继续安装
- [ ] 同签名覆盖：确认后 App 退出，重开后版本号变化、对话和设置还在，运行时按新版本升级
- [ ] 签名不同的包：安装前提示「签名不一致」，不出现系统报错
- [ ] 系统确认框按返回：回到「已取消安装」，可以再装
- [ ] 下载中切到后台、断网再恢复、杀进程后重进：都能续传
- [ ] 国产 ROM（vivo / 小米 / 华为）：自带的安装拦截页、「安全安装」流程不会让 App 卡在「安装中」（App 回到前台 3 秒后会自动放开）
- [ ] 公共镜像实测可用；GitHub 不通时能回落
