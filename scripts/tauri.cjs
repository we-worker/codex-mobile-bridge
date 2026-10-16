'use strict';
// Node is build tooling only; it is never shipped with the Tauri application.
const {spawnSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const command=process.argv[2]||'dev';
if(!['dev','build'].includes(command))throw Error('Use dev or build');
const env={...process.env};
// MSVC is the recommended CI toolchain. Existing MinGW installations can also
// build locally; use Rust's matching linker without changing global tooling.
if(process.platform==='win32'&&!env.RUSTFLAGS&&!env.CARGO_ENCODED_RUSTFLAGS){
  const version=spawnSync('rustc',['-vV'],{encoding:'utf8',env,windowsHide:true});
  if(version.status===0&&/^host: x86_64-pc-windows-gnu$/m.test(version.stdout)){
    const sysroot=spawnSync('rustc',['--print','sysroot'],{encoding:'utf8',env,windowsHide:true});
    if(sysroot.status===0){
      const linker=path.join(sysroot.stdout.trim(),'lib/rustlib/x86_64-pc-windows-gnu/bin/gcc-ld');
      if(fs.existsSync(path.join(linker,'ld.lld.exe'))){
        const key=Object.keys(env).find(key=>key.toLowerCase()==='path')||'PATH';
        env[key]=linker+path.delimiter+(env[key]||'');
        env.RUSTFLAGS='-C link-arg=-fuse-ld=lld';
      }
    }
  }
}
if(command==='dev'){
  env.CMB_TAURI_SOURCE='1';
  const local=path.join(root,'.tmp','tauri-venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  env.CMB_PYTHON=env.CMB_PYTHON||(fs.existsSync(local)?local:process.platform==='win32'?'python':'python3');
}
const cli=require.resolve('@tauri-apps/cli/tauri.js');
const result=spawnSync(process.execPath,[cli,command,...process.argv.slice(3)],{cwd:root,env,stdio:'inherit'});
if(result.error)throw result.error;
process.exitCode=result.status??1;
