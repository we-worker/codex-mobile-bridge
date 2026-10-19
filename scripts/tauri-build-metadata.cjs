'use strict';
const fs=require('node:fs'),path=require('node:path');

const ARCH={x86_64:'x64',amd64:'x64',aarch64:'arm64',arm64:'arm64'};

function expectedGatewayMetadata(root,target){
  const packageInfo=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
  const normalized=String(target||'').toLowerCase();
  const cpu=normalized.split('-')[0];
  const platform=normalized.includes('windows')?'win32':normalized.includes('darwin')?'darwin':normalized.includes('linux')?'linux':process.platform;
  const arch=normalized?ARCH[cpu]||cpu:process.arch;
  return {version:packageInfo.version,platform,arch};
}

function validateGatewayMetadata(root,target){
  const expected=expectedGatewayMetadata(root,target);
  const metadataPath=path.join(root,'dist/update-version.json');
  let metadata;
  try{
    metadata=JSON.parse(fs.readFileSync(metadataPath,'utf8'));
  }catch(error){
    throw new Error(`Cannot read gateway version metadata at ${metadataPath}. Run python scripts/build-desktop.py for the target first.`,{cause:error});
  }
  if(metadata.version!==expected.version||metadata.platform!==expected.platform||metadata.arch!==expected.arch){
    throw new Error(`Gateway metadata is ${metadata.version}/${metadata.platform}/${metadata.arch}, expected ${expected.version}/${expected.platform}/${expected.arch}. Run python scripts/build-desktop.py for the target first.`);
  }
  return expected;
}

module.exports={expectedGatewayMetadata,validateGatewayMetadata};
