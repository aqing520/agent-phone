# DeepSeek desktop bridge deployment

Status: bridge and image code are implemented and isolated tests pass. Desktop installation was attempted through the official plugin manager, but the write to `~/.dsh/profiles/desktop/package.json.lock` was denied and the escalation approval was cancelled. No alternative write was attempted. Native synchronization has **not** been verified or activated in the user's desktop App.

## Install (requires permission to change desktop profile)

From this repository:

```sh
"/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh" plugin --profile desktop add "link:$(pwd)/tools/dsh-desktop-bridge"
```

Then merge the entry from `tools/dsh-desktop-bridge.patch.yml` into the desktop profile's existing `cordis.patch.yml` (do not replace the existing file). The directory field is optional; by default the plugin uses the current user's `~/.config/agent-phone/control`.

Restart DeepSeek Desktop only after any active desktop/phone task has finished. The plugin must run inside the desktop Host, not a second ACP process. It opens a 0600 Unix socket, and invokes `workspaceRegistry.archiveSession`, `unarchiveSession`, and existing workspace `attachSession`. It never writes raw workspace or projection documents.

## Activate image runtime

After active tasks have finished, restart the DeepSeek control service and HTTP gateway. Restarting the control service during a running task can interrupt it; this has deliberately not been performed during the current phone task.

The image button stays disabled until the controller advertises `imageInput=true`. Actual ACP image acceptance still depends on initialization capability and the selected provider/model's image modality. An unsupported route must fail explicitly, never silently fall back to text.

## Archive state

When the desktop bridge is connected the phone reads and modifies the native archive set. When unavailable the existing phone-only archive remains explicitly labeled. Old phone-only archive records are retained; they are not automatically merged into native archives, since this could unexpectedly archive desktop conversations. Native state is authoritative while the bridge is connected.

## Verification still required

- Launch plugin in the actual desktop Host and confirm socket availability.
- Confirm desktop-native archive/restore changes propagate to phone and vice versa.
- Confirm `attachSession` makes a phone-created session visible in the desktop workspace feed; unknown directories must not create unexpected projects.
- Verify an actual image with a declared image-capable model, including normalized attachment history.
- Confirm safe phone/desktop handoff and refresh after external process writes. This implementation does not promise simultaneous writers or perfect live desktop UI refresh.

## Isolated checks

```sh
node tools/test_dsh_desktop_bridge.mjs
python3 -m unittest tools.test_dsh_images tools.test_dsh_runtime tools.test_dsh_discovery tools.test_dsh_archive
node --check app.js
```

No Codex or WorkBuddy runtime is called by these checks. The desktop bridge test uses only a fake in-memory registry and a temporary socket.
