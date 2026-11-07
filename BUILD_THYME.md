# Mi 10S (thyme): MIUI base + BakaSU

This target combines `vendor/kona-perf_defconfig`, the SM8250 common fragment,
and `vendor/xiaomi/thyme.config`. It enables BakaSU manual hooks and ThinLTO;
SUSFS and GKI tracepoint hooks are disabled. `CONFIG_XIAOMI_MIUI=y` enables the
synced Xiaomi MIUI configuration. The kernel source is 4.19.325 CIP.
The missing ultrasound IIO driver is restored from Xiaomi's `cmi-r-oss`
source (`64b40409431988d060f7484369c8c2d7deca1bb3`,
`drivers/iio/proximity/us_prox.c`), with the unused bootinfo include removed,
zeroed event padding, and callback publication/teardown synchronized.

Initialize the pinned BakaSU submodule before building:

```sh
git submodule update --init --recursive
```

Build on an Ubuntu system with Clang/LLD/LLVM, the ARM64/ARM32 GNU cross tools,
build-essential, bc, bison, flex, OpenSSL/ELF development headers, Python 3,
and the device-tree tools installed:

```sh
BUILD_JOBS=3 ./build-thyme.sh
```

A matching Docker environment is included. From the repository root:

```sh
docker build --secret id=system_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -f Dockerfile.thyme -t thyme-build .
docker run --rm --user "$(id -u):$(id -g)" --network=none \
  --mount "type=bind,src=$PWD,dst=/src" --workdir /src \
  -e BUILD_JOBS=3 thyme-build bash ./build-thyme.sh
```

Outputs are in `out/thyme/arch/arm64/boot/`: `Image`, `Image.gz-dtb`,
and `dtbo.img`. The effective configuration is `out/thyme/.config`.
The DTBO contains the thyme overlay. Runtime/MIUI compatibility still needs
verification on the actual device; compilation alone does not test boot,
audio, cameras, Wi-Fi, or root operation.

Create a device-checked AnyKernel3 package after a successful build:

```sh
python3 package-thyme.py
```

This verifies the ARM64 Image, embedded config, appended DTBs and the single
thyme DTBO. The ZIP under `artifacts/thyme/` includes a build manifest and
checksums; a detached ZIP SHA256 is generated next to it. The installer checks
`thyme`, preserves the current ROM ramdisk, and installs the built kernel/DTB
and DTBO. Device boot testing remains necessary.

GitHub Actions uses `.github/workflows/build-thyme.yml` on Ubuntu 24.04 with
Clang 18. Pushes to `build/thyme-miui-bakasu` run the build automatically;
pull requests targeting that branch run the same checks. The workflow can
also build the default branch after these changes are merged there.
It checks out the pinned BakaSU submodule, builds the kernel/DTBO/modules,
validates the AnyKernel ZIP, then uploads artifacts for 14 days:

- `Mi10S-thyme-MIUI-BakaSU-<run>`: ZIP, checksum, manifest, config and a
  separate module archive. The flashable ZIP does not install the modules.
- `thyme-build-log-<run>`: build log and effective config, including on build
  failures.

The CI packager pins AnyKernel3 to
`41f04bdb4ee30a44e429c2c1131d5e8bb32b15f1`. No GitHub PAT or repository secret
is needed to build this public source or upload Actions artifacts.
