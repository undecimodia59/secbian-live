# secbian-live

Amnesic, hardened, security/privacy-focused Debian Live (trixie, i3) built with live-build.

## Build (on Debian 13 trixie)

```sh
sudo apt install -y live-build cryptsetup-bin
sudo ./scripts/build-live.sh
```

`cryptsetup-bin` supplies the host's `veritysetup`: this live-build version calls
it outside the chroot. A final binary hook independently verifies the generated
verity tree and root hash and fails the build on missing or invalid output.
Other build tools (debootstrap, xorriso, mtools, syslinux/grub bits,
memtest86+, ...) are pulled automatically into the build chroot
(`LB_BUILD_WITH_CHROOT="true"`).

Signed UEFI shim/GRUB packages are required: the build fails rather than silently
falling back to unsigned UEFI loaders. Legacy BIOS boot is still included.
The build script checks prerequisites and HTTPied's checksum, then runs these
commands in order:

```sh
sudo lb clean
sudo lb config
sudo lb build
```

This removes the generated chroot, stage markers and image outputs together,
while preserving download caches. Keep any previous images you need elsewhere.
Use this path after configuration/package changes or when a resumed build skips
package installation despite missing packages. Repeating `lb build` cannot repair
that mismatch by itself. `lb clean --purge` additionally deletes caches and is
not normally necessary for this recovery.

When syncing between machines, transfer the complete source checkout but exclude
`.build/`, `chroot/`, `binary/` and `cache/`; generated build state belongs to its
builder. In particular, stage markers must not be paired with a different chroot.

## Hardened by default

| Layer         | What                                                                                                |
|---------------|-----------------------------------------------------------------------------------------------------|
| Kernel        | `apparmor=1 security=apparmor lockdown=integrity slab_nomerge init_on_alloc=1 init_on_free=1 page_alloc.shuffle=1 vsyscall=none` |
| sysctl        | kptr/dmesg restrict, ptrace_scope=1, unpriv BPF off, rp_filter, no redirects/source-route (v4+v6), protected links/fifos/regular, sysrq=0, IPv6 temp addrs |
| Network       | Random MAC (Wi-Fi scan + per-connection, ethernet), no DHCP hostname, random hostname per boot, UFW deny-in/allow-out |
| Amnesia       | No persistence, journald RAM-only, machine-id/SSH host keys/udev rules/logs wiped from image       |
| MAC / USB     | AppArmor + apparmor-profiles(-extra); USBGuard preserves devices authorized at startup and blocks all new attachments pending approval |
| Integrity     | dm-verity checks root-filesystem reads; corruption triggers a kernel panic rather than continuing with corrupt data |
| Tor           | Installed, manual start: `sudo systemctl start tor` (use via torsocks/nyx)                          |

## Tools

| List            | Contents                                                                                                        |
|-----------------|-----------------------------------------------------------------------------------------------------------------|
| security.list   | nmap, wireshark, aircrack-ng, john, hashcat, hydra, sqlmap, gobuster, ffuf, nikto, netcat, tcpdump, ettercap, dsniff, foremost, testdisk, binwalk, sleuthkit, chkrootkit, rkhunter, apktool, Java runtime (+ nuclei, volatility3 & JADX via pinned hooks) |
| privacy.list    | mullvad-browser, mullvad-vpn, tor, torsocks, nyx, obfs4proxy, firejail, apparmor stack, usbguard, ufw, mat2, metadata-cleaner, cryptsetup, bind9-dnsutils (dig); erase(Custom shred wrapper) |
| desktop.list    | i3, lightdm, kitty, rofi, dunst, feh, xorg, network-manager-applet, firmware-linux/-realtek/-iwlwifi             |
| useful.list     | gparted, tmux, git, python3-pip/-venv, build-essential, unzip, fastfetch, jq, golang-go, sqlite3                 |
| included binary | [HTTPied](https://github.com/undecimodia59/HTTPied): native HTTP(S) interception and testing workspace, supplied as a prebuilt Linux x86_64 Trixie release |

### Android reverse engineering

[JADX](https://github.com/skylot/jadx) 1.5.6 provides APK/DEX-to-Java decompilation
through `jadx` and the **JADX** application-menu entry (`jadx-gui`). Its official
cross-platform release is SHA-256 verified during the build and installed under
`/opt/jadx`, with commands on `$PATH`. The full Debian Java runtime is included
for both CLI and GUI use. The hook checks both launchers' versions without
opening the GUI.

[Apktool](https://packages.debian.org/trixie/apktool) comes from Debian's archive
and decodes Android resources and smali, then rebuilds modified projects:

```sh
jadx-gui ./app.apk
jadx -d ./java-source ./app.apk
apktool d ./app.apk -o ./decoded-app
apktool b ./decoded-app -o ./rebuilt.apk
```

JADX produces reconstructed source, not necessarily buildable original code.
Apktool rebuilding does not sign the resulting APK. Debian trixie's Apktool is
2.7.0; newer Android resource formats may require a newer upstream release.

### [HTTPied](https://github.com/undecimodia59/HTTPied)

Launch **HTTPied** from the application menu (`Super+D`), or run `httpied` from a
terminal. It provides Intercept, History, Replay, Intruder, Attack, Compare and
Coder workspaces, including a local JWT workbench. Projects store captures,
workspace state and attack results in a local SQLite database. Choose **Open
project**, **Create project**, or **Temporary session** on the start screen.
Temporary sessions are removed on orderly exit; project files in the live RAM
overlay are lost when the machine shuts down unless saved to external storage.

For a capture-to-replay workflow, select a request in History, press `Ctrl+R` to
open it in Replay, then `Ctrl+Enter` to send. Headless proxy mode is also available:

```sh
httpied --headless --listen 127.0.0.1:8080
```

The desktop supports HTTPS interception and automatically installs the opened
project's public CA into the current user's Chromium NSS store. `libnss3-tools`
and the X11/Wayland/OpenGL runtime libraries are included. **Open browser** needs
a separately installed Chromium/Chrome browser; Mullvad Browser is not Chromium.
Other certificate stores need manual public-CA import and browser proxy setup.
Keep the project's private `ca.key.pem` private. Full usage documentation is
included at `/usr/share/doc/httpied/README.md`.

The executable is stored directly in
`config/includes.chroot/usr/local/bin/httpied` and installed as
`/usr/local/bin/httpied`. It comes from HTTPied's Trixie release, with a maximum
required GLIBC symbol version of 2.39. The build hook verifies its SHA-256 and
runs `httpied --help` inside the build chroot to detect loader incompatibility.
No Rust toolchain or HTTPied source build is needed for the live image.
When replacing the binary, use a Trixie-compatible UI build, refresh its bundled
README and update `config/includes.chroot/usr/share/doc/httpied/SHA256SUMS`
(the entry names `/usr/local/bin/httpied` inside the image).

## Notes

- Live user `secbian`, password `secbian`, passwordless sudo; root locked.
- Mullvad APT entries use `signed-by`, but live-build installs their keys under
  `/etc/apt/trusted.gpg.d/`. Those keys also participate in global APT trust for
  sources without their own `signed-by` restriction. This working placement is
  retained because chroot and final-image key availability differ during the
  build. There is no package allowlist limiting the Mullvad repository; installing
  its packages trusts their privileged maintainer scripts as well.
- VeraCrypt volumes: `sudo cryptsetup open --type tcrypt <container> <name>`.
- Build-time downloads are pinned: rockyou (sha256), jwt_tool (commit plus clean
  checkout), nuclei and JADX (sha256 plus version assertions), volatility3 and its base
  dependency pefile (versions and wheel hashes). Nuclei is reverified and
  Volatility's venv is recreated whenever their build hooks run. Volatility uses
  wheels only and installs offline from verified downloads; optional extras are
  not included. Its complete lock is
  `config/includes.chroot/usr/share/secbian/volatility3-requirements.txt`.
  Nuclei templates / Volatility symbol tables download on first use.
- Normal and fail-safe boot use the same live user, password hook and security
  arguments; fail-safe adds hardware compatibility arguments.

## File overwriting and deletion

GNU `shred` is included through Debian's essential `coreutils` package; the setup
hook checks that it is available. The `erase` wrapper supplies the everyday
defaults, including recursive removal; `rm` keeps its normal behavior.

```sh
# One random pass, one zero pass, then removal:
erase ./file
erase -r ./folder

# Multiple files and names starting with a dash:
erase ./first ./second
erase -- -filename
```

`erase` uses `shred` with exactly those two overwrite passes and removes each file
only after successful overwriting. Recursive mode skips symlinks, hard-linked
files, special files and mount points. It rejects `/`, the current directory and
its ancestors. Failed or skipped entries remain in place, with a nonzero exit
status; it never finishes with a blanket `rm -rf`. Use it on a tree that other
processes are not modifying. It starts immediately, without a confirmation prompt.

These tools attempt overwriting; they cannot guarantee erasure on SSDs, USB flash,
copy-on-write filesystems, snapshots or backups. Overwriting a file from the live
image affects its overlay copy, leaving the read-only squashfs original intact.
Overwriting files in RAM does not guarantee removal of every other RAM copy.
Use encryption before storing sensitive data on persistent media.
See [GNU shred limitations](https://www.gnu.org/software/coreutils/manual/html_node/shred-invocation.html).

## Shell shortcuts

Interactive Bash sessions load these aliases from `~/.bash_aliases`:

| Alias | Command |
|-------|---------|
| `la` | `ls -lah` |
| `ll` | `ls -lh` |
| `cl` | `clear` |

## USB devices

Connect the boot drive, keyboard, mouse and any required hub before starting the
machine. USBGuard preserves devices already authorized when its daemon starts,
including the live boot drive. It blocks every new attachment, including keyboards
and devices reconnected after unplugging. A daemon restart preserves blocked
states rather than automatically approving them.

Press **Super+Shift+U**, or open **USB Devices** from the application launcher.
Select a blocked device, review its details, and choose **Allow this attachment**.
The default is **Keep blocked**; Esc closes the menu. Approval applies only to
the current attachment, so reconnecting requires approval again. For a new hub,
approve the hub first, then review its downstream devices. If no devices are
waiting, the utility says so.

From a terminal:

```sh
sudo usbguard list-devices --blocked
sudo usbguard allow-device <id>
```

Use the leading numeric ID from the listing. Avoid `--permanent`: this image is
amnesic and intentionally requires approval for new attachments. If protection
is unavailable, inspect `sudo systemctl status usbguard` and
`sudo journalctl -u usbguard`.

Only approve hardware you recognize: names, serials and USB descriptors can be
forged. Devices connected before USBGuard starts are trusted, including malicious
ones; this is the portability tradeoff. Keep a working input device connected
before boot so you can approve a replacement. Devices that enumerate late may
also need manual approval. USB protection starts in userspace and does not cover
firmware or initramfs USB activity.

## Boot integrity and its limits

live-build creates `filesystem.squashfs.verity` and
`filesystem.squashfs.roothash` alongside the root image. live-boot uses them to
check root-filesystem blocks as they are read. This detects accidental corruption
and modification of the image without corresponding changes to the verity data.

**This is not a fully authenticated boot chain.** The root hash, initramfs and
boot configuration remain on the boot medium without a custom authenticated
trust chain. An attacker able to rewrite the medium can replace those files or
disable verification. Signed UEFI loaders and kernel lockdown do not close that
gap; BIOS has no equivalent firmware Secure Boot protection. Secure Boot must
also be enabled in firmware for its signature checks to apply.

Before writing an ISO, compare its SHA-256 against a value received through a
trusted independent channel. If distributing images, publish a detached signature
over the checksum file and communicate the signing-key fingerprint separately.
A checksum stored only beside an untrusted ISO does not authenticate it. Keep
boot media physically secure; hardware write protection or read-only optical
media can reduce later tampering. Protecting against an attacker who can replace
the entire medium requires an authenticated boot design beyond this portable
configuration.

## Verification without building an ISO

Run `python3 -B -m unittest discover -s tests -v` for isolated regression checks.
They use temporary files and mocked system/USB commands; they do not change the
host hostname, USB policy, network or services. A real Debian build and BIOS/UEFI
boot checks are still needed before releasing an image.
