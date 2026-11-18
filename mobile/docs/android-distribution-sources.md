# Android 发布：许可与对应源码

Agent Phone 是基于 DSH Go 的 AGPL-3.0 衍生版。保留 [AGPL 全文](../LICENSE)、[第三方声明](../THIRD_PARTY_NOTICES.md)以及源码中原有的版权和许可头；直接复用或修改新的第三方代码时，记录上游、精确版本、许可、文件和修改。第三方组件保留各自的许可，不随主项目改许可。

## 为每个发行包提供对应源码

从干净的发行标签生成安装包。同一下载页免费提供与 APK 内提交号一致的完整 Agent Phone 对应源码（包括必要的构建、安装脚本及补丁），并附上第三方对应源码说明。不要用会变动的分支、项目主页或二进制 npm 包代替源码。镜像若单独提供 APK，也要在下载旁提供同等源码入口。参见 [AGPL §6(d)](../LICENSE#L263-L274)。

发布准备需要提供本次构建的第三方源码说明。说明中应列出 APK 的 SHA-256、ABI、运行时版本；对每个实际分发且有对应源码义务的组件，列出精确二进制包/版本、许可、完整对应源码的下载地址及校验值，以及与本次构建一致的配方、补丁和修改。对 LGPL 组件，还应说明适用的替换或重新链接方式；如许可证要求安装信息，也要一并提供。验证链接从无登录、无付费的环境可取到；维护与二进制匹配的获取入口。工具的自动检查不能代替这一核验。

## 从实际 APK 盘点

```sh
python3 tooling/audit_android_distribution.py path/to/build.apk
```

该检查输出 APK 摘要、ABI、引擎版本、运行时归档和随包许可资产，拒绝已知不能分发的旧素材与缺失的必需通知。它不打开第三方源码链接、不证明许可证已经履行，也不证明某个依赖没有其他许可义务。

1. 解开 APK 内 `assets/runtime/` 对应 ABI 的 rootfs，依据 `/var/lib/dpkg/status`、各软件包的版权文件、npm 包清单及实际共享库/WASM 识别组件；不要用 lock 文件的可选项代替成品清单。
2. **Termux 与 Ubuntu。** PRoot 上游版本及本项目对 ELF 的改动已有记录，仍要找到与分发 `.deb` 一致的 Termux 构建配方、补丁和源码；libtalloc 同理。Ubuntu 按实际安装版本查找匹配的 source package，保留源包及适用的打包材料，不能只列 Ubuntu 版本。libandroid-shmem 保留适用的 BSD 通知。
3. **npm 与 Android 原生依赖。** 核对 libvips 原生库与 Sharp WASM 内的 LGPL 组件、版本和通知，补上裸包缺失的原组件许可/通知；核对 LibreOffice Kit（含 WASM）MPL 覆盖部分的源码入口。核对 `libspake2.so` 的版本、LGPL 对应源码及适用替换方式。Node、Python 和其他复合二进制也要按其实际捆绑内容核验。
4. **最后复核。** 重新检查 APK 里的 WebRTC 完整通知、Flutter 依赖通知、语音/字体等素材许可，以及是否误带旧伙伴包。第三方源码资料不全时，不公开发布该 APK；先补材料，或从发行构建中移除无法合规分发的组件，再对新包重做核验。

目前本地测试 APK 的精确 Termux 打包材料、Ubuntu 源包和部分 npm 组件的完整对应源码仍未核验，不能把本文当成这些组件的源码交付文件。已有可继续追溯的证据：

- `@img/sharp-libvips-linux-arm64@1.3.4` 的 npm 构建溯源指向 [sharp-libvips 固定提交](https://github.com/lovell/sharp-libvips/tree/ebb95f8add54eee8bed840e3fb587e4cbec857d7)，可从该提交的 [构建脚本](https://github.com/lovell/sharp-libvips/blob/ebb95f8add54eee8bed840e3fb587e4cbec857d7/build/posix.sh)及[第三方通知](https://github.com/lovell/sharp-libvips/blob/ebb95f8add54eee8bed840e3fb587e4cbec857d7/THIRD-PARTY-NOTICES.md)核对原生组件。`@img/sharp-wasm32@0.35.5` 的 npm 构建溯源指向 [Sharp 固定提交](https://github.com/lovell/sharp/tree/51a990faa26ade5586a4934ac9673c98d8893326)。构建仓库本身不能替代它下载的各组件源码和补丁。
- [Termux 配方快照](https://github.com/termux/termux-packages/tree/84e2a370eb92898242d4ef956f22931280131460/packages)中的 PRoot、libtalloc 和 libandroid-shmem 版本与本地测试 APK 一致，但尚未证实是该批 `.deb` 的实际构建配方；libtalloc 的包级许可字段与源码头也需区分核对。
- LibreOffice Kit 的发布包指向 [dsh-libreoffice-kit](https://github.com/deepseek-ai/dsh-libreoffice-kit)。WASM 包的 `prebuilds.json` 固定了 [LibreOffice Core 26.8.0.3 的源码提交](https://github.com/LibreOffice/core/tree/bce0998afefdbc355585ca324285661a2170ba77)，并包含源码摘要、补丁和构建脚本。本地测试包中，清单列出的 47 个文件摘要均吻合，且[官方源码下载地址](https://download.documentfoundation.org/libreoffice/src/26.8.0/libreoffice-26.8.0.3.tar.xz)可达；未下载完整源码归档验证摘要。入口包 `0.1.5` 的公开源码修订另待核实，不能用仓库默认分支代替。
