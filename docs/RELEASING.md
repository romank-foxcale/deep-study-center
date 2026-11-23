# Releasing the desktop app

How to publish a new version of Deep Study Center for Windows. The installed apps (0.4.1 and later) find it by
themselves (SPEC §39).

## Before you start

- You need the updater's private key: `~/.tauri/dsc-updater.key` on the maintainer's computer. It is not in the
  repository. Keep a backup copy in a safe place. **If the key is lost, installed apps cannot update again.**
- The public key is in `desktop/src-tauri/tauri.conf.json` (`plugins.updater.pubkey`). Do not change it.

## Steps

1. Set the new version in `desktop/package.json`, `desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/Cargo.toml`
   (and `Cargo.lock`) and `backend/pyproject.toml`. Add the version to `docs/CHANGELOG.md`.
2. Merge the release pull request into `main`.
3. Build the signed installer (PowerShell):

   ```powershell
   $env:TAURI_SIGNING_PRIVATE_KEY = Get-Content -Raw "$HOME\.tauri\dsc-updater.key"
   $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
   cd desktop
   npm run build
   ```

   The build writes the installer and its signature (`.exe.sig`) to `src-tauri/target/release/bundle/nsis/`.
4. Make the release files:

   ```powershell
   python release.py
   ```

   This writes `desktop/release/<version>/` with the installer (spaces in its name become dots, as on GitHub) and
   `latest.json`.
5. Publish the release and mark it as the latest. The app reads `latest.json` from the latest release only.

   ```powershell
   gh release create v<version> (Get-ChildItem release/<version>/*).FullName --target main --title "Deep Study Center <version>" --notes-file ../docs/release-notes-<version>.md --latest
   ```

6. Check: open `https://github.com/romank-foxcale/deep-study-center/releases/latest/download/latest.json`. It must show
   the new version. An installed older app then offers the update at its next start.

## A local update test

1. Build an older version with the key, with `--config` and a file that holds
   `{"version": "0.4.0", "plugins": {"updater": {"dangerousInsecureTransportProtocol": true}}}`. The flag lets this
   test build use the `http` server below; never set it in `tauri.conf.json`. Install the test build.
2. Build the new version. Then run `python release.py --base-url http://127.0.0.1:8765/`.
3. Serve the folder: `python -m http.server 8765 --directory release/<version>`.
4. Start the installed app with `DSC_UPDATE_URL=http://127.0.0.1:8765/latest.json` and `DSC_WORKSPACE` set to a test
   folder. Click "Install and restart". The log is `%LOCALAPPDATA%\app.deepstudycenter.desktop\logs\update.log`.
