# secbian-live

Amnesic, security/privacy-focused Debian Live (trixie, i3) built with live-build.
Tails-like hygiene, Kali-like toolset. Nothing persists unless you set it up.

## Build (on Debian 13 trixie)

```sh
sudo apt install -y live-build
lb build        # -> secbian.amd64.iso + SHA256SUMS
lb clean        # before a rebuild
```

All other build tools (debootstrap, xorriso, mtools, syslinux/grub bits,
memtest86+, ...) are pulled automatically into the build chroot
(`LB_BUILD_WITH_CHOUT="true"`).

## Hardened by default

| Layer         | What                                                                                                |
|---------------|-----------------------------------------------------------------------------------------------------|
| Kernel        | `apparmor=1 security=apparmor lockdown=integrity slab_nomerge init_on_alloc=1 init_on_free=1 page_alloc.shuffle=1 vsyscall=none` |
| sysctl        | kptr/dmesg restrict, ptrace_scope=1, unpriv BPF off, rp_filter, no redirects/source-route (v4+v6), protected links/fifos/regular, sysrq=0, IPv6 temp addrs |
| Network       | Random MAC (Wi-Fi scan + per-connection, ethernet), no DHCP hostname, random hostname per boot, UFW deny-in/allow-out |
| Amnesia       | No persistence, journald RAM-only, machine-id/SSH host keys/udev rules/logs wiped from image       |
| MAC / USB     | AppArmor + apparmor-profiles(-extra); USBGuard allowlist (HID allowed, `sudo usbguard allow-device <id>` for the rest) |
| Tor           | Installed, manual start: `sudo systemctl start tor` (use via torsocks/nyx)                          |

## Tools

| List            | Contents                                                                                                        |
|-----------------|-----------------------------------------------------------------------------------------------------------------|
| security.list   | nmap, wireshark, aircrack-ng, john, hashcat, hydra, sqlmap, gobuster, ffuf, nikto, netcat, tcpdump, ettercap, dsniff, foremost, testdisk, binwalk, sleuthkit, chkrootkit, rkhunter (+ nuclei & volatility3 via pinned hooks) |
| privacy.list    | mullvad-browser, mullvad-vpn, tor, torsocks, nyx, obfs4proxy, firejail, apparmor stack, usbguard, ufw, mat2, metadata-cleaner, cryptsetup |
| desktop.list    | i3, lightdm, kitty, rofi, dunst, feh, xorg, network-manager-applet, firmware-linux/-realtek/-iwlwifi             |
| useful.list     | gparted, tmux, git, python3-pip/-venv, build-essential, unzip                                                   |

## Notes

- Live user `secbian`, password `secbian`, passwordless sudo; root locked.
- Mullvad apt repo key is scoped (`signed-by`), not globally trusted.
- VeraCrypt volumes: `cryptsetup open --type veracrypt <container> <name>`.
- Build-time downloads are pinned: rockyou (sha256), jwt_tool (commit), nuclei
  (sha256), volatility3 (sha256). nuclei templates / volatility3 symbol tables
  download on first use.
