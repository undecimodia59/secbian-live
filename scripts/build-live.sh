#!/bin/sh
set -eu

# Rebuild generated state together. Keeping .build markers while replacing the
# chroot lets live-build skip package installation on an incomplete filesystem.
if [ "$(id -u)" != 0 ]
then
	echo "Run this script with sudo on the Debian 13 build machine." >&2
	exit 1
fi
cd "$(dirname "$0")/.."

for _TOOL in lb veritysetup sha256sum
do
	if ! command -v "${_TOOL}" >/dev/null 2>&1
	then
		echo "Missing build prerequisite: ${_TOOL}. Install live-build and cryptsetup-bin." >&2
		exit 1
	fi
done

# Check transferred source artifacts before removing any previous build output.
for _FILE in \
	config/common config/bootstrap config/chroot config/binary config/source \
	config/archives/mullvad.key.chroot config/archives/mullvad.key.binary \
	config/includes.chroot/usr/local/bin/httpied \
	config/includes.chroot/usr/share/doc/httpied/SHA256SUMS
do
	if [ ! -s "${_FILE}" ]
	then
		echo "Missing source artifact: ${_FILE}. Sync the complete checkout first." >&2
		exit 1
	fi
done
# Verify the image-relative checksum without accessing the host's /usr/local/bin.
(
	cd config/includes.chroot
	sed 's|  /|  |' usr/share/doc/httpied/SHA256SUMS | sha256sum -c -
)

echo "Removing generated chroot, stage markers and image outputs; preserving download caches."
lb clean
lb config
exec lb build
