# DeepSeek desktop bridge deployment

Verified on November 18, 2026 with DeepSeek Harness 0.2.2-rc.3. An isolated desktop profile verified native archive, restore, and workspace attachment. A real model identified the color of a test PNG, and the phone history displayed the image saved by Harness. The user then confirmed image sending and desktop archive sync in the everyday profile from a physical phone.

## Install in the desktop profile

After active turns finish, fully quit DeepSeek Harness Desktop. Run this command from the repository root.

```sh
"/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh" plugin --profile desktop add "link:$(pwd)/tools/dsh-desktop-bridge"
```

The plugin manager registers the package's bundle and loads its patch automatically. If an older checkout was installed as a plain dependency, remove `agent-phone-desktop-bridge` in the same profile and install it again to register the bundle. The default socket directory is `~/.config/agent-phone/control`.

Open DeepSeek Desktop and check for `~/.config/agent-phone/control/dsh-desktop.sock`. The plugin runs inside the desktop Host and calls `workspaceRegistry.archiveSession`, `unarchiveSession`, and `attachSession` through the native registry. Phone-created sessions attach only to already registered workspaces with the same working directory.

## Activate image runtime

Declare `input: [text, image]` on the verified image-capable model entry in its provider config. Set that route as the ACP startup model in `~/.config/agent-phone/control/dsh-provider.patch.yml`. Harness checks the startup route during `initialize`, so choosing an image model later in the UI alone cannot enable image input.

```yaml
- id: acp
  config:
    provider: your-provider-id
    model: your-image-model-id
```

Merge the entry into the existing patch list and retain provider settings and credential references. After active tasks finish, restart `local.agent-phone.dsh` and `local.agent-phone.gateway`. In an existing DeepSeek conversation, select an image-capable model and attach up to four PNG, JPEG, WebP, or GIF files of 3 MiB each. An active ACP connection that did not advertise image support disables the attachment button. An unsupported model route returns an error without submitting a text-only turn.

## Archive state

When the desktop bridge is connected the phone reads and modifies the native archive set. The phone refreshes the open session list every five seconds. If the bridge is unavailable, the phone uses its separate archive records. Old phone archive records stay in the phone store. Native state is authoritative while the bridge is connected.

## Verification

- The isolated desktop Host and the phone HTTP API reflected archive and restore in both directions. The native workspace stored the newly attached session and its archive state.
- The official ACP process sent a synthetic PNG through an image-capable route. The model recognized its color, and the phone history returned the normalized attachment.
- Mobile-sized Chromium selected two PNGs whose encoded payload exceeded localStorage capacity. After a simulated dropped connection and reload, it kept the same request ID and image payload, then cleared the local copy after acknowledgment.
- Image submission also reached the gateway when IndexedDB stopped responding. After reloading the page, the browser retried a small image or accepted a reattached large image with the original request ID.

## Isolated checks

```sh
node tools/test_dsh_desktop_bridge.mjs
python3 -m unittest tools.test_dsh_images tools.test_dsh_runtime tools.test_dsh_discovery tools.test_dsh_archive
node --check app.js
```

No Codex or WorkBuddy runtime is called by these checks. The desktop bridge test uses only a fake in-memory registry and a temporary socket.
