'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {validateGatewayMetadata}=require('../scripts/tauri-build-metadata.cjs');

function fixture(version,metadata){
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'cmb-tauri-metadata-'));
  fs.mkdirSync(path.join(root,'dist'));
  fs.writeFileSync(path.join(root,'package.json'),JSON.stringify({version}));
  fs.writeFileSync(path.join(root,'dist/update-version.json'),JSON.stringify(metadata));
  return root;
}

test('Tauri build accepts gateway metadata for the same version and target',()=>{
  const root=fixture('2.1.1',{version:'2.1.1',platform:'win32',arch:'x64'});
  try{
    assert.deepEqual(validateGatewayMetadata(root,'x86_64-pc-windows-msvc'),{version:'2.1.1',platform:'win32',arch:'x64'});
  }finally{
    fs.rmSync(root,{recursive:true,force:true});
  }
});

test('Tauri build rejects stale gateway metadata before packaging',()=>{
  const root=fixture('2.1.1',{version:'2.0.3',platform:'win32',arch:'x64'});
  try{
    assert.throws(()=>validateGatewayMetadata(root,'x86_64-pc-windows-msvc'),/expected 2\.1\.1\/win32\/x64/);
  }finally{
    fs.rmSync(root,{recursive:true,force:true});
  }
});
