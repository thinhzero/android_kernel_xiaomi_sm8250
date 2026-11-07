#!/usr/bin/env python3
"""Validate the built thyme kernel and create a device-checked AnyKernel ZIP."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=ROOT / 'out/thyme')
parser.add_argument('--output-dir', type=Path, default=ROOT / 'artifacts/thyme')
parser.add_argument('--anykernel-dir', type=Path)
args = parser.parse_args()
args.out = args.out.resolve()
args.output_dir = args.output_dir.resolve()
args.output_dir.mkdir(parents=True, exist_ok=True)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def revision(path):
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()

boot = args.out / 'arch/arm64/boot'
image = (boot / 'Image').read_bytes()
assert image[56:60] == b'ARM\x64', 'Invalid ARM64 Image header'
packed = (boot / 'Image.gz-dtb').read_bytes()
gzip = zlib.decompressobj(16 + zlib.MAX_WBITS)
assert gzip.decompress(packed) == image and gzip.eof, 'Compressed Image differs from Image'
base_names = ('kona.dtb', 'kona-v2.dtb', 'kona-v2.1.dtb')
bases = [(boot / 'dts/vendor/qcom' / name).read_bytes() for name in base_names]
tail = gzip.unused_data
appended = []
while tail:
    magic, size = struct.unpack('>2I', tail[:8])
    assert magic == 0xd00dfeed and 40 <= size <= len(tail), 'Invalid appended DTB'
    appended.append(digest(tail[:size]))
    tail = tail[size:]
assert sorted(appended) == sorted(map(digest, bases)), 'Unexpected appended DTB set'
dtbo = (boot / 'dtbo.img').read_bytes()
header = struct.unpack('>8I', dtbo[:32])
assert header[0] == 0xd7b7ab1e and header[4] == 1, 'Expected one DTBO entry'
entry = struct.unpack('>8I', dtbo[header[5]:header[5] + 32])
overlay = dtbo[entry[1]:entry[1] + entry[0]]
assert overlay == (boot / 'dts/vendor/qcom/thyme-sm8250-overlay.dtbo').read_bytes()
assert b'xiaomi thyme\0' in overlay, 'DTBO is not for thyme'
config = subprocess.check_output(['bash', str(ROOT / 'scripts/extract-ikconfig'), str(boot / 'Image')])
assert config.strip() == (args.out / '.config').read_bytes().strip(), 'Embedded config mismatch'
for symbol in ('MACH_XIAOMI_THYME', 'BOARD_THYME', 'US_PROXIMITY', 'KSU', 'KSU_MANUAL_HOOK'):
    assert f'CONFIG_{symbol}=y\n'.encode() in config, f'Missing {symbol}'
assert b'CONFIG_KSU_SUSFS=y\n' not in config, 'SUSFS must be disabled'
assert b'CONFIG_KSU_TRACEPOINT_HOOK=y\n' not in config, 'GKI tracepoint hook must be disabled'
release = (args.out / 'include/config/kernel.release').read_text().strip()
makefile = (ROOT / 'Makefile').read_text()
version = '.'.join(re.search(r'^' + field + r'\s*=\s*(\d+)', makefile, re.M)[1]
                   for field in ('VERSION', 'PATCHLEVEL', 'SUBLEVEL'))
commit = revision(ROOT)
filename = f'Mi10S-thyme-MIUI-BakaSU-{version}-{commit[:8]}.zip'

with tempfile.TemporaryDirectory(prefix='thyme-package-') as tmp:
    work = Path(tmp)
    upstream = args.anykernel_dir
    if upstream is None:
        upstream = work / 'AnyKernel3'
        subprocess.run(['git', 'clone', '--depth=1', 'https://github.com/osm0sis/AnyKernel3.git', str(upstream)], check=True)
    stage = work / 'package'
    stage.mkdir()
    for directory in ('META-INF', 'tools'):
        shutil.copytree(upstream / directory, stage / directory)
    shutil.copy2(upstream / 'LICENSE', stage / 'LICENSE')
    (stage / 'anykernel.sh').write_text('''### AnyKernel3: Xiaomi Mi 10S (thyme), MIUI base + BakaSU
properties() { '
kernel.string=Thyme MIUI BakaSU
do.devicecheck=1
do.modules=0
do.systemless=1
do.cleanup=1
do.cleanuponabort=0
device.name1=thyme
supported.versions=
supported.patchlevels=
supported.vendorpatchlevels=
'; }
BLOCK=boot;
IS_SLOT_DEVICE=auto;
RAMDISK_COMPRESSION=auto;
PATCH_VBMETA_FLAG=auto;
. tools/ak3-core.sh;
# Preserve the current ROM ramdisk and replace the kernel/DTB and thyme DTBO.
split_boot;
flash_boot;
flash_generic dtbo;
''')
    (stage / 'anykernel.sh').chmod(0o755)
    (stage / 'Image.gz-dtb').write_bytes(packed)
    (stage / 'dtbo.img').write_bytes(dtbo)
    (stage / 'dtb').write_bytes(b''.join(bases))
    (stage / 'kernel.config').write_bytes(config)
    manifest = {
        'device': 'Xiaomi Mi 10S', 'codename': 'thyme', 'rom_target': 'MIUI base',
        'kernel_release': release, 'lto': 'thin',
        'compiler': (args.out / 'include/generated/compile.h').read_text().split('LINUX_COMPILER', 1)[1].strip().splitlines()[0].strip(' \"'),
        'kernel_repository': 'https://github.com/thinhzero/android_kernel_xiaomi_sm8250',
        'kernel_commit': commit, 'bakasu_repository': 'https://github.com/Baka-SU/BakaSU',
        'bakasu_commit': revision(ROOT / 'KernelSU'), 'hook': 'manual', 'susfs': False,
        'anykernel3_repository': 'https://github.com/osm0sis/AnyKernel3', 'anykernel3_commit': revision(upstream),
        'built_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'config_sha256': digest(config), 'image_sha256': digest(image),
        'image_gz_dtb_sha256': digest(packed), 'dtbo_sha256': digest(dtbo),
        'dtbo_entries': 1, 'boot_tested': False,
    }
    (stage / 'BUILD-INFO.json').write_text(json.dumps(manifest, indent=2) + '\n')
    paths = sorted(path for path in stage.rglob('*') if path.is_file())
    (stage / 'SHA256SUMS').write_text(''.join(f'{digest(path.read_bytes())}  {path.relative_to(stage)}\n' for path in paths))
    archive = args.output_dir / filename
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                output.write(path, str(path.relative_to(stage)))
    with zipfile.ZipFile(archive) as check:
        assert check.testzip() is None, 'ZIP integrity check failed'
        for line in check.read('SHA256SUMS').decode().splitlines():
            expected, name = line.split('  ', 1)
            assert digest(check.read(name)) == expected, f'Checksum failed: {name}'
    (args.output_dir / (filename + '.sha256')).write_text(f'{digest(archive.read_bytes())}  {filename}\n')
    shutil.copy2(stage / 'BUILD-INFO.json', args.output_dir / 'BUILD-INFO.json')
    shutil.copy2(stage / 'kernel.config', args.output_dir / 'kernel.config')
print(archive)
print('Validated ARM64 Image, embedded BakaSU/no-SUSFS config, thyme DTBO and ZIP checksums')
