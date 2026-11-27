# Releasing the desktop app

How to publish a new version of Deep Study Center for Windows, macOS and Linux. The installed apps (0.4.1 and later) find it by
themselves (SPEC §39).

## Before you start

- You need the updater's private key: `~/.tauri/dsc-updater.key` on the maintainer's computer. It is not in the
  repository. Keep a backup copy in a safe place. **If the key is lost, installed apps cannot update again.**
- The public key is in `desktop/src-tauri/tauri.conf.json` (`plugins.updater.pubkey`). Do not change it.

## Steps

GitHub Actions builds the app on each system (`.github/workflows/desktop.yml`). One time only: put the key into the
repository secret `TAURI_SIGNING_PRIVATE_KEY` (`gh secret set TAURI_SIGNING_PRIVATE_KEY < ~/.tauri/dsc-updater.key`).
The key has no password; if it gets one, also set `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`.

1. Set the new version in `desktop/package.json`, `desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/Cargo.toml`
   (and `Cargo.lock`) and `backend/pyproject.toml`. Add the version to `docs/CHANGELOG.md` and write
   `docs/release-notes-<version>.md`.
2. Merge the release pull request into `main`.
3. Tag `main` and push the tag. This starts the build:

   ```bash
   git checkout main && git pull
   git tag v<version> && git push origin v<version>
   ```

4. Wait for the "Desktop" workflow (about 20 minutes). It makes a **draft** release with the Windows installer, the
   two macOS `.dmg` files, the Linux `.AppImage` and `.deb`, the update files with their signatures, and one
   `latest.json` for all systems. The release text comes from `docs/release-notes-<version>.md`.
5. Open the draft on the Releases page and check it: every system has its files, and `latest.json` lists
   `windows-x86_64`, `darwin-aarch64`, `darwin-x86_64` and `linux-x86_64`. Then publish it and mark it as the latest
   (`gh release edit v<version> --draft=false --latest`). The apps read `latest.json` from the latest release only.
6. Check: open `https://github.com/romank-foxcale/deep-study-center/releases/latest/download/latest.json`. It must show
   the new version. An installed older app then offers the update at its next start.

A Windows release can also be built by hand on Windows: `npm run build` in `desktop/` with
`TAURI_SIGNING_PRIVATE_KEY` set, then `python release.py`, then `gh release create` with the files in
`desktop/release/<version>/`. That `latest.json` has Windows only, so the macOS and Linux apps do not update from it.

## A local update test

1. Build an older version with the key, with `--config` and a file that holds
   `{"version": "0.4.0", "plugins": {"updater": {"dangerousInsecureTransportProtocol": true}}}`. The flag lets this
   test build use the `http` server below; never set it in `tauri.conf.json`. Install the test build.
2. Build the new version. Then run `python release.py --base-url http://127.0.0.1:8765/`.
3. Serve the folder: `python -m http.server 8765 --directory release/<version>`.
4. Start the installed app with `DSC_UPDATE_URL=http://127.0.0.1:8765/latest.json` and `DSC_WORKSPACE` set to a test
   folder. Click "Install and restart". The log is `%LOCALAPPDATA%\app.deepstudycenter.desktop\logs\update.log`.
