// Run on the synthetic gateway fixture after app.js has loaded; no native client is contacted.
async function runModelCacheTests(){
  const checks=[],originalFetch=window.fetch,old={currentId,currentHost,state,listIdentity};
  const check=(value,label)=>{if(!value)throw Error(label);checks.push(label);};
  const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
  const response=data=>({ok:true,status:200,json:async()=>data});
  const accountA='a'.repeat(64),accountB='b'.repeat(64),id='11111111-1111-4111-8111-111111111111';
  const catalog=(identity,model,updatedAt)=>({models:[{id:model,name:model,efforts:['low']}],modelSource:'codex',cache:{identity,updatedAt}});
  let next=null,reads=0;
  window.fetch=async(url,options)=>{if(!String(url).includes('/catalog?kind=models'))return originalFetch(url,options);reads++;return next?next.promise:response(catalog(accountA,'model-a',1000));};
  try{
    currentId=id;currentHost='local';listIdentity='fixture-gateway';state={connected:true,provider:'chatgpt',model:'model-a',effort:'low',modelCatalogIdentity:accountA};
    await openModelDialog();check($('model-options').querySelector('input[value="model-a"]'),'First catalog renders model A');const originalTime=$('model-updated').textContent;check(originalTime.includes(BridgeI18n.t('更新于：')),'Successful catalog shows updatedAt');
    $('model-dialog').close();next=deferred();const delayed=openModelDialog();
    check($('model-options').querySelector('input[value="model-a"]'),'Reopen paints cached rows synchronously');check(!$('model-options').textContent.includes('读取模型列表'),'Reopen has no full loading replacement');check($('model-updated').textContent===originalTime,'Reopen preserves successful timestamp');
    next.resolve(response(catalog(accountA,'model-a',1000)));await delayed;$('model-dialog').close();
    next=deferred();const failed=openModelDialog(true);check($('model-options').querySelector('input[value="model-a"]'),'Refresh retains existing rows while pending');next.reject(Error('Synthetic upstream failure'));await failed;
    check($('model-options').querySelector('input[value="model-a"]'),'Failed refresh retains rows');check($('model-updated').textContent===originalTime,'Failed refresh retains last successful timestamp');
    $('model-dialog').close();next=deferred();const stale=openModelDialog();state={...state,modelCatalogIdentity:accountB,model:'model-b'};next.resolve(response(catalog(accountA,'model-a',2000)));await stale;
    $('model-dialog').close();next=deferred();const switched=openModelDialog();check(!$('model-options').querySelector('input[value="model-a"]'),'New account does not paint old catalog');next.resolve(response(catalog(accountB,'model-b',3000)));await switched;check($('model-options').querySelector('input[value="model-b"]'),'New account paints its own catalog');
    const newTime=$('model-updated').textContent;check(newTime!==originalTime,'Successful new catalog updates the timestamp');
    return {passed:checks.length,checks,reads};
  }finally{next?.resolve(response(catalog(accountB,'model-b',3000)));$('model-dialog').close();window.fetch=originalFetch;currentId=old.currentId;currentHost=old.currentHost;state=old.state;listIdentity=old.listIdentity;}
}
