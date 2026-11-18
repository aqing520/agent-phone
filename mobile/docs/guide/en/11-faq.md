# Troubleshooting

## Messages won't send, or no reply comes

Check the host status at the bottom of the chat list.

- **This phone**: open the engine page and check its status and **Logs**. Not installed, stopped and failed to start are different cases; follow the page. When a start fails, the failure card links to the logs and a diagnostics bundle.
- **Remote host**: the remote hosts page offers a fix for the cause, such as **Reconnect**, **Sign in again** or **Trust again**.
- If no model is set up, **Choose model** offers to enter an API key or add a provider.

Reset and uninstall both delete data on this phone; you rarely need them to fix a problem.

<!-- nav: commonSettings,phoneEngineDiagnostics -->
`Settings › Diagnostics` · [Open](dshgo://open/diagnostics)

To report a problem, export a diagnostics bundle here. It includes the version, device, bounded engine logs and captured errors, not all system logs or a complete crash history. The app attempts to remove keys and tokens; still inspect the bundle before sharing it.

To let the AI look into it, tap **Let the AI read diagnostics**. The app writes a bounded snapshot for the local engine, then ask the AI to "check the diagnostics". The bundled `dsh-go-support` skill walks the symptoms and drafts an issue you can paste.

### Crashes and automatic failure analysis

The app keeps bounded local records of error categories, a few app/framework source locations and voice stages, without exception bodies, recordings or chat content. On Android 11 and later it also attempts to read this app's historical process-exit reasons. Missing or empty system records do not prove there was no failure, and are not complete crash stacks.

In an ordinary local chat, ask the AI to check the recent crash. Supported versions expose a diagnostics tool that refreshes and reads individual sections, without a manual export. In Safe mode or with an older runtime, the published snapshot remains the fallback; export only if more evidence is needed.

**Automatic failure analysis** is off by default. Enabling it explains that, after a failure and only while the app is foregrounded and connected to the working local engine, allowlisted versions, device/system facts, error categories, source locations, voice stages and exit reasons are sent to the model provider configured on that engine. Model charges may apply. Chat bodies, recordings, credentials, raw logs and system input-method evidence are excluded. After an app crash, analysis must wait until the app is reopened and connected.

Analysis uses a separate tool-free conversation, without switching your current chat, performing repairs or publishing to GitHub. Matching failures are grouped; failed or ambiguous attempts are not retried automatically. Check its status here and tap the report entry to read the analysis. Disabling it, switching to a remote host or backgrounding the app prevents new requests and attempts to stop ongoing analysis; sent data and generated conversations cannot be retracted.

If local analysis records cannot be read or saved, automatic analysis pauses and a recovery entry appears. Recovery is local only: it baselines already retained failures without resending old requests, then resumes handling future failures after a successful save. Failed recovery remains paused and is not retried in a loop.

## The engine stops in the background, or notifications don't arrive

<!-- nav: commonSettings,phoneEngineKeepAlive -->
`Settings › Background running` · [Open](dshgo://open/background)

Follow the guide to turn off battery optimization, keep the "engine running" notification, and lock the app in Recents. Limits vary by brand, and Android may still stop the engine.

For notifications, also turn on the alerts you want in the app's **Notifications** and allow Agent Phone notifications in system settings. Alerts from remote hosts need the app running and the connection online.

## The engine keeps failing to start

**Automatic Safe mode** on the local engine page is on by default: after two failed starts in a row, the engine starts without plugins. You can also tap **Start in Safe mode** on the same page. Your chats are safe in Safe mode; fix the configuration, then tap **Return to normal mode**. Web settings changed in Safe mode aren't kept.

Direct local engine launch is off by default; you turn it on under Developer options. Once it is on, on a phone where a direct start fails (Android 16 blocks it, for one), it switches to compatible launch on its own: that doesn't count as a failed start and doesn't lead to Safe mode. It keeps using compatible launch until an app update brings a new runtime, and **Diagnostics** shows **Direct launch failed**. To try again, stop the local engine, then turn on **Direct local engine launch** under **Developer options** on the Diagnostics page.

After an upgrade from an earlier version, the first direct start tidies your plugin files once; the engine shows **Tidying plugin files** meanwhile. If the phone is short of space or the tidy-up doesn't finish, that start uses compatible launch, **Fallback reason** on the **Diagnostics** page says why, and the next start carries on. No files are lost.

**tawcroot fast launch** is also under **Developer options**, off by default, and only one of it and direct launch can be on. With it on, tawcroot runs the local engine: it starts about three times faster, and package installs and apt get faster too. If it can't start, the app switches to compatible launch on its own; that doesn't count as a failed start either, and **Diagnostics** shows **tawcroot failed to start**. To try again, stop the local engine and turn it back on. The first start after you turn it off first turns the hard links it made into ordinary files, and the engine shows **Tidying plugin files**. If the phone is short on space, that start fails and says how much is missing; free up space or turn tawcroot back on. No files are lost.

## The app can chat, but headless reports MISSING_CREDENTIAL

`dsh --profile headless` starts a separate one-shot task. Its default profile disables the interactive credential store, authorization and DeepSeek account services, so it does not automatically use API keys or account sign-ins saved in the app. A working chat in the app does not mean this command has credentials configured.

The default DeepSeek official API route needs `DEEPSEEK_API_KEY`. Supply it in the process environment that launches the command, or set your own API key as `DEEPSEEK_API_KEY=...` in the launch directory's `.env` or `$DSH_HOME/.env`. These are read in order: process environment, launch directory's `.env`, then `$DSH_HOME/.env`. An exported empty variable also shadows the `.env` fallback; unset that empty variable before using a file instead. Keep real keys out of chats, issue reports and source control.

DeepSeek account sign-in and an official API key are different credentials. An account sign-in token cannot be used as `DEEPSEEK_API_KEY`. You can keep using the account in the app, or configure an API key separately for headless.

Adding the app's sign-in patch alone does not enable the services that headless disables by default. Custom profiles and remote hosts may use different configurations; follow the configuration of that host.

## The pet is gone

- Not in chats: if the pet page is set to **None**, choose a pet; if it's hidden for an hour, tap **Show now**.
- Not outside the app: check that **Show outside the app** is on and display over other apps is allowed. **When to show** defaults to **When active**, which hides the pet after 5 quiet minutes. If it was hidden for today, tap **Restore** on the pet page. It also hides while the app is in the foreground.

See [Pets](06-pets.md).

## A plugin is installed but doesn't show up

Check that the plugin is enabled, and restart the engine if asked. A plugin's native UI needs the dsh-go bridge on the host: this phone's engine has it built in, remote hosts usually don't. A display place may also be turned off in the plugin's details. Plugin panels without a native UI appear in the Plugins group of All features, opening in the app or as Web entries. See [Plugins](08-plugins.md).

## What the app sends

<!-- nav: commonSettings,hubPrivacy,usageStatsTitle -->
`Settings › Privacy and sharing › Send anonymous usage stats` · [Open](dshgo://open/usage-stats)

Agent Phone’s own anonymous usage statistics are on by default; the switch is on the welcome screen the first time you open the app. If you updated from an earlier version, a one-time notice at the bottom of the home screen tells you, and can turn it off right there. While it's on, the app sends anonymous stats for the days before, at most once a day, and only this: app and Android version, CPU architecture, phone maker and model (such as `V2405A`, from 1.0.15), the maker's system and its version (such as OriginOS 5.0, from 1.0.15), app language, how the local engine was started, and that day's number of messages, voice inputs (speech typed into the message box, not voice calls), generations, shares and installed plugins. From 1.0.17 also: messages sent in the tavern, visits to the companion room, voice calls that connected, and the day's total input and output tokens that model replies reported (only the numbers the provider gives in its replies; channels that give none are not counted, and nothing is estimated). Devices are told apart by a random ID that changes every 90 days.

These statistics never include accounts, API keys, chats, character cards, files, prompts, host addresses or which model you use, or device identifiers such as phone number or IMEI. Turning this switch off stops these Agent Phone statistics; the random ID and the counts kept on the phone are deleted at once.

## QR scanning and Google ML Kit

On Android, opening Remote’s pairing scanner initializes the Google ML Kit barcode-scanning SDK on demand. Scanning runs on the device; the SDK collects usage statistics such as device model, app version and processing time. Agent Phone’s own statistics switch does not control that SDK. To connect without using the scanner SDK, paste the pairing link or use Remote account sign-in.

See the [Google ML Kit terms](https://developers.google.com/ml-kit/terms) and [Android SDK data disclosure](https://developers.google.com/ml-kit/android-data-disclosure). These terms are distinct from the Apache 2.0 license for documentation examples.

## The guide doesn't match what I see

Check the app version under **Version** in Settings and compare it with the version in the [guide index](../README.md). The app is always right.
