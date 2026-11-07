#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
thyme_out="${KERNEL_OUT:-out/thyme}"
thyme_jobs="${BUILD_JOBS:-$(nproc)}"
thyme_args=(O="$thyme_out" ARCH=arm64 LLVM=1 LLVM_IAS=1 LOCALVERSION=
  CROSS_COMPILE=aarch64-linux-gnu- CROSS_COMPILE_ARM32=arm-linux-gnueabi-
  CROSS_COMPILE_COMPAT=arm-linux-gnueabi-)
make "${thyme_args[@]}" vendor/kona-perf_defconfig \
  vendor/xiaomi/sm8250-common.config vendor/xiaomi/thyme.config
for symbol in MACH_XIAOMI_THYME BOARD_XIAOMI BOARD_XIAOMI_SM8250 BOARD_THYME XIAOMI_MIUI US_PROXIMITY KSU KSU_MANUAL_HOOK; do
  grep -qx "CONFIG_${symbol}=y" "$thyme_out/.config" || { echo "Missing CONFIG_${symbol}=y" >&2; exit 1; }
done
if grep -Eq '^CONFIG_KSU_(SUSFS|TRACEPOINT_HOOK)=y' "$thyme_out/.config"; then
  echo 'This build requires manual hooks without SUSFS or GKI tracepoint hooks.' >&2
  exit 1
fi
make "${thyme_args[@]}" -j"$thyme_jobs" Image.gz-dtb dtbo.img modules
