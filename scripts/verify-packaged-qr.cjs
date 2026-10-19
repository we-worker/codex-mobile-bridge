'use strict';
const fs=require('node:fs'),path=require('node:path');
const {execFileSync}=require('node:child_process');
const asar=require('@electron/asar');

const check=String.raw`
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module');
const root=fs.realpathSync(process.argv[1]);
const resolve=Module._resolveFilename;
Module._resolveFilename=function(request,parent,...rest){
  const result=resolve.call(this,request,parent,...rest);
  if(!Module.isBuiltin(request)){
    const file=fs.realpathSync(result);
    if(!file.startsWith(root+path.sep))throw Error('Packaged QR dependency escaped app.asar: '+request);
  }
  return result;
};
(async()=>{
  const {pairingImage}=require(path.join(root,'desktop/features/connections/qr.cjs'));
  const url='https://example.invalid/pair?token=package-check';
  const {image}=await pairingImage({url});
  const prefix='data:image/png;base64,';
  if(!image.startsWith(prefix)||!Buffer.from(image.slice(prefix.length),'base64').subarray(0,8).equals(Buffer.from('89504e470d0a1a0a','hex'))){
    throw Error('Packaged QR renderer did not generate a PNG');
  }
})().catch(error=>{console.error(error);process.exitCode=1});
`;

function verifyAsar(archive){
  const temporary=path.resolve(__dirname,'../.tmp');
  fs.mkdirSync(temporary,{recursive:true});
  const extracted=fs.mkdtempSync(path.join(temporary,'packaged-qr-'));
  try{
    asar.extractAll(archive,extracted);
    execFileSync(process.execPath,['--no-global-search-paths','-e',check,extracted],{
      cwd:extracted,env:{...process.env,NODE_PATH:'',NODE_OPTIONS:''},stdio:'pipe',timeout:30000,
    });
  }catch(error){
    throw Error(`Packaged QR renderer failed in ${archive}: ${error.stderr?.toString()||error.message}`);
  }finally{
    fs.rmSync(extracted,{recursive:true,force:true});
  }
}

module.exports=async context=>{
  const resources=context.electronPlatformName==='darwin'
    ?path.join(context.appOutDir,`${context.packager.appInfo.productFilename}.app`,'Contents','Resources')
    :path.join(context.appOutDir,'resources');
  verifyAsar(path.join(resources,'app.asar'));
};
module.exports.verifyAsar=verifyAsar;
