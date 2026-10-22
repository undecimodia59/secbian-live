# secbian-live

Amnesic, hardened, security/privacy-focused Debian Live (trixie, i3) built with live-build.

## Build (on Debian 13 trixie)

```sh
sudo apt install -y live-build cryptsetup-bin
sudo lb config
sudo lb build
```

`cryptsetup-bin` supplies the host's `veritysetup`: this live-build version calls
it outside the chroot. A final binary hook independently verifies the generated
verity tree and root hash and fails the build on missing or invalid output.
Other build tools (debootstrap, xorriso, mtools, syslinux/grub bits,
memtest86+, ...) are pulled automatically into the build chroot
(`LB_BUILD_WITH_CHROOT="true"`).

Signed UEFI shim/GRUB packages are required: the build fails rather than silently
falling back to unsigned UEFI loaders. Legacy BIOS boot is still included.
After changing this configuration, rebuild from a clean chroot so cached stages
cannot retain old settings:

```sh
sudo lb clean --purge
sudo lb config
sudo lb build
```

This removes existing live-build build state and caches; keep any needed build
artifacts separately first.

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
| security.list   | nmap, wireshark, aircrack-ng, john, hashcat, hydra, sqlmap, gobuster, ffuf, nikto, netcat, tcpdump, ettercap, dsniff, foremost, testdisk, binwalk, sleuthkit, chkrootkit, rkhunter (+ nuclei & volatility3 via pinned hooks) |
| privacy.list    | mullvad-browser, mullvad-vpn, tor, torsocks, nyx, obfs4proxy, firejail, apparmor stack, usbguard, ufw, mat2, metadata-cleaner, cryptsetup, bind9-dnsutils (dig); erase(Custom shred wrapper) |
| desktop.list    | i3, lightdm, kitty, rofi, dunst, feh, xorg, network-manager-applet, firmware-linux/-realtek/-iwlwifi             |
| useful.list     | gparted, tmux, git, python3-pip/-venv, build-essential, unzip                                                   |

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
  checkout), nuclei (sha256 plus version assertion), volatility3 and its base
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
