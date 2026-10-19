#!/usr/bin/env python3
"""Build a local debug APK using project-local JDK/SDK; never installs tools."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, default=ROOT/'dist/mobile-preview')
parser.add_argument('--tailscale-aar', type=Path, default=ROOT/'.tmp/mobile-tools/codex-mobile-tailscale.aar')
parser.add_argument('--androidx-webkit-aar', type=Path, default=ROOT/'.tmp/mobile-tools/androidx-webkit.aar')
parser.add_argument('--androidx-core-aar', type=Path, default=ROOT/'.tmp/mobile-tools/androidx-core.aar')
parser.add_argument('--androidx-annotation-jar', type=Path, default=ROOT/'.tmp/mobile-tools/androidx-annotation-jvm.jar')
parser.add_argument('--androidx-annotation-experimental-aar', type=Path, default=ROOT/'.tmp/mobile-tools/androidx-annotation-experimental.aar')
parser.add_argument('--jspecify-jar', type=Path, default=ROOT/'.tmp/mobile-tools/jspecify.jar')
parser.add_argument('--kotlin-stdlib-jar', type=Path, default=ROOT/'.tmp/mobile-tools/kotlin-stdlib.jar')
options = parser.parse_args()
tools = ROOT/'.tmp/mobile-tools'
jdks = list((tools/'jdk').glob('*/Contents/Home'))
if not jdks:
    raise SystemExit('Place a JDK 17 in .tmp/mobile-tools/jdk first.')
jdk = jdks[0]
sdk = tools/'sdk'
def executable(folder,name):
    for candidate in (folder/(name+'.exe'),folder/(name+'.bat'),folder/name):
        if candidate.is_file():
            return candidate
    return folder/name
build_tools = next(p for p in (sdk/'build-tools').iterdir() if executable(p,'aapt2').is_file())
android = next((sdk/'platforms').glob('*/android.jar'))
zxing = tools/'zxing-core-3.5.3.jar'
if hashlib.sha1(zxing.read_bytes()).hexdigest() != (tools/'zxing.sha1').read_text().strip():
    raise SystemExit('ZXing checksum mismatch')
tailscale_aar = options.tailscale_aar.resolve()
if not tailscale_aar.is_file():
    raise SystemExit('Build the gomobile Tailscale AAR first or pass --tailscale-aar.')
androidx_inputs = {
    'AndroidX WebKit': options.androidx_webkit_aar.resolve(),
    'AndroidX Core': options.androidx_core_aar.resolve(),
    'AndroidX Annotation': options.androidx_annotation_jar.resolve(),
    'AndroidX Annotation Experimental': options.androidx_annotation_experimental_aar.resolve(),
    'JSpecify': options.jspecify_jar.resolve(),
    'Kotlin standard library': options.kotlin_stdlib_jar.resolve(),
}
for label, path in androidx_inputs.items():
    if not path.is_file():
        raise SystemExit(f'{label} artifact is missing: {path}')
work = ROOT/'.tmp/mobile-preview/android-build'
work.mkdir(parents=True, exist_ok=True)
for name in ('gen', 'classes', 'dex', 'tailscale-aar', 'androidx-webkit-aar', 'androidx-core-aar',
             'androidx-annotation-experimental-aar'):
    folder = work/name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
with zipfile.ZipFile(tailscale_aar) as archive:
    for member in archive.infolist():
        target = (work/'tailscale-aar'/member.filename).resolve()
        if not target.is_relative_to((work/'tailscale-aar').resolve()):
            raise SystemExit('Unsafe path in Tailscale AAR: '+member.filename)
    archive.extractall(work/'tailscale-aar')
tailscale_classes = work/'tailscale-aar/classes.jar'
native_libraries = sorted((work/'tailscale-aar/jni').glob('*/libgojni.so'))
if not tailscale_classes.is_file() or not native_libraries:
    raise SystemExit('Tailscale AAR must contain classes.jar and jni/<abi>/libgojni.so')
for source_aar, target_name in (
    (androidx_inputs['AndroidX WebKit'], 'androidx-webkit-aar'),
    (androidx_inputs['AndroidX Core'], 'androidx-core-aar'),
    (androidx_inputs['AndroidX Annotation Experimental'], 'androidx-annotation-experimental-aar'),
):
    target_root = work/target_name
    with zipfile.ZipFile(source_aar) as archive:
        for member in archive.infolist():
            target = (target_root/member.filename).resolve()
            if not target.is_relative_to(target_root.resolve()):
                raise SystemExit(f'Unsafe path in {source_aar.name}: '+member.filename)
        archive.extractall(target_root)
androidx_classes = [
    work/'androidx-webkit-aar/classes.jar',
    work/'androidx-core-aar/classes.jar',
    work/'androidx-annotation-experimental-aar/classes.jar',
]
for path in androidx_classes:
    if not path.is_file():
        raise SystemExit(f'AndroidX classes are missing: {path}')
compile_classpath = [
    android, zxing, tailscale_classes, *androidx_classes,
    androidx_inputs['AndroidX Annotation'], androidx_inputs['JSpecify'],
    androidx_inputs['Kotlin standard library'],
]
dex_classpath = [zxing, tailscale_classes, work/'androidx-webkit-aar/classes.jar',
                 work/'androidx-core-aar/classes.jar']
env = {**os.environ, 'JAVA_HOME': str(jdk), 'PATH': str(jdk/'bin')+os.pathsep+os.environ['PATH']}
def run(*args):
    subprocess.run([str(a) for a in args], env=env, check=True, cwd=ROOT)
source = ROOT/'mobile/android'
run(executable(build_tools,'aapt2'),'compile','--dir',source/'res','-o',work/'resources.zip')
run(executable(build_tools,'aapt2'),'link','-I',android,'--manifest',source/'AndroidManifest.xml','--java',work/'gen','-o',work/'base.apk',work/'resources.zip')
java = list((source/'src').rglob('*.java')) + list((work/'gen').rglob('*.java'))
run(executable(jdk/'bin','javac'),'-encoding','UTF-8','--release','8','-classpath',os.pathsep.join(map(str,compile_classpath)),'-d',work/'classes',*java)
run(executable(build_tools,'d8'),'--lib',android,'--min-api','26','--output',work/'dex',*list((work/'classes').rglob('*.class')),*dex_classpath)
shutil.copy2(work/'base.apk',work/'unsigned.apk')
with zipfile.ZipFile(work/'unsigned.apk','a') as archive:
    for path in (work/'dex').glob('*.dex'):
        archive.write(path,path.name)
    for directory in (ROOT/'mobile/shared/web', source/'assets', ROOT/'web/client-icons'):
        for asset in directory.glob('*.js'):
            archive.write(asset,'assets/'+asset.name)
    for provider in ('codex', 'claude', 'deepseek'):
        archive.write(ROOT/'web/client-icons'/f'{provider}.png', 'assets/'+provider+'.png')
    for library in native_libraries:
        relative=library.relative_to(work/'tailscale-aar/jni')
        archive.write(library,'lib/'+relative.as_posix())
    archive.write(ROOT/'mobile/NOTICE.md','assets/NOTICE.md')
    archive.write(ROOT/'mobile/licenses/ZXing-LICENSE.txt','assets/ZXing-LICENSE.txt')
    archive.write(ROOT/'mobile/licenses/AndroidX-LICENSE.txt','assets/AndroidX-LICENSE.txt')
    archive.write(ROOT/'mobile/licenses/gomobile-LICENSE.txt','assets/gomobile-LICENSE.txt')
    archive.write(ROOT/'tsnet/third_party/tailscale/LICENSE.txt','assets/Tailscale-LICENSE.txt')
    archive.write(ROOT/'tsnet/third_party/tailscale/licenses/android.md','assets/Tailscale-Third-Party-NOTICES.md')
key = tools/'preview-debug.p12'
if not key.exists():
    run(executable(jdk/'bin','keytool'),'-genkeypair','-keystore',key,'-storepass','android','-keypass','android','-alias','preview','-keyalg','RSA','-keysize','2048','-validity','3650','-dname','CN=Bridge Local Preview')
run(executable(build_tools,'zipalign'),'-f','-P','16','4',work/'unsigned.apk',work/'aligned.apk')
out = options.output_dir.resolve()
out.mkdir(parents=True,exist_ok=True)
version = json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
apk = out/('Codex-Mobile-Bridge-'+version+'-Android.apk')
run(executable(build_tools,'apksigner'),'sign','--ks',key,'--ks-pass','pass:android','--out',apk,work/'aligned.apk')
run(executable(build_tools,'apksigner'),'verify','--verbose',apk)
print(apk)
print('SHA-256',hashlib.sha256(apk.read_bytes()).hexdigest())
