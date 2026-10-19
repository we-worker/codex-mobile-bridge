'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {test}=require('node:test');
const asar=require('@electron/asar');
const verify=require('../scripts/verify-packaged-qr.cjs');

const root=path.resolve(__dirname,'..');

test('the packaged QR renderer loads only its archive and generates a PNG',async()=>{
  fs.mkdirSync(path.join(root,'.tmp'),{recursive:true});
  const temporary=fs.mkdtempSync(path.join(root,'.tmp','packaged-qr-test-'));
  try{
    const app=path.join(temporary,'app');
    const source=path.join(root,'desktop/features/connections/qr.cjs');
    const target=path.join(app,'desktop/features/connections/qr.cjs');
    fs.mkdirSync(path.dirname(target),{recursive:true});
    fs.copyFileSync(source,target);

    const copied=new Set();
    function copyDependency(name,from){
      const manifest=require.resolve(`${name}/package.json`,{paths:[from]});
      if(copied.has(manifest))return;
      copied.add(manifest);
      const directory=path.dirname(manifest);
      const relative=path.relative(path.dirname(fs.realpathSync(path.join(root,'node_modules'))),directory);
      assert.ok(relative.startsWith('node_modules'+path.sep),relative);
      fs.cpSync(directory,path.join(app,relative),{recursive:true});
      for(const dependency of Object.keys(JSON.parse(fs.readFileSync(manifest,'utf8')).dependencies||{})){
        copyDependency(dependency,directory);
      }
    }
    copyDependency('qrcode',root);

    const good=path.join(temporary,'good.asar');
    await asar.createPackage(app,good);
    for(const platform of ['win32','linux','darwin']){
      const appOutDir=path.join(temporary,platform);
      const resources=platform==='darwin'
        ?path.join(appOutDir,'Codex Mobile Bridge.app','Contents','Resources')
        :path.join(appOutDir,'resources');
      fs.mkdirSync(resources,{recursive:true});
      fs.copyFileSync(good,path.join(resources,'app.asar'));
      await verify({electronPlatformName:platform,appOutDir,packager:{appInfo:{productFilename:'Codex Mobile Bridge'}}});
    }

    fs.rmSync(path.join(app,'node_modules/dijkstrajs'),{recursive:true});
    const missing=path.join(temporary,'missing.asar');
    await asar.createPackage(app,missing);
    assert.throws(()=>verify.verifyAsar(missing),/Packaged QR dependency escaped app\.asar: dijkstrajs|Cannot find module 'dijkstrajs'/);
  }finally{
    fs.rmSync(temporary,{recursive:true,force:true});
  }
});
