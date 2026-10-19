'use strict';

// Drafts stay on this device. Every read requires a verified gateway and account scope.
class ComposerDrafts {
  constructor(storage=localStorage){this.storage=storage;}
  key(scope,kind='draft'){
    if(!scope||!['gateway','provider','account','host','session'].every(name=>typeof scope[name]==='string'&&scope[name]))return null;
    return 'composer-v1:'+kind+':'+JSON.stringify([scope.gateway,scope.provider,scope.account,scope.host,scope.session]);
  }
  read(key){if(!key)return null;try{return JSON.parse(this.storage.getItem(key)||'null');}catch{return null;}}
  write(key,value){if(!key)return false;try{this.storage.setItem(key,JSON.stringify(value));return true;}catch{return false;}}
  remove(key){if(!key)return;try{this.storage.removeItem(key);}catch{}}
  load(scope){const saved=this.read(this.key(scope));return saved&&typeof saved.text==='string'?saved:null;}
  save(scope,fields){
    const key=this.key(scope);if(!key)return null;
    const previous=this.load(scope),text=String(fields.text||'').slice(0,100000);
    const draft={text,selectionStart:Math.max(0,Math.min(text.length,Number(fields.selectionStart)||0)),selectionEnd:Math.max(0,Math.min(text.length,Number(fields.selectionEnd)||0)),sendMode:fields.sendMode||'send',workMode:fields.workMode||'default',skills:Array.isArray(fields.skills)?fields.skills.filter(value=>typeof value==='string').slice(0,8):[],revision:previous?.revision||0};
    if(JSON.stringify({...draft,revision:0})!==JSON.stringify({...previous,revision:0}))draft.revision++;
    return this.write(key,draft)?draft:null;
  }
  clear(scope){this.remove(this.key(scope));}
  pending(scope){const saved=this.read(this.key(scope,'pending'));return saved&&typeof saved.id==='string'&&saved.id?saved:null;}
  discardPending(scope,id){if(this.pending(scope)?.id===id)this.remove(this.key(scope,'pending'));}
  begin(scope,body,id){
    const key=this.key(scope,'pending');if(!key)return null;
    const fingerprint=JSON.stringify(body),previous=this.pending(scope);
    if(previous?.fingerprint===fingerprint)return previous;
    if(previous?.body?.text===body.text)return {...previous,blocked:true};
    const pending={id,fingerprint,body};return this.write(key,pending)?pending:null;
  }
  confirm(scope,id,revision){
    const pending=this.pending(scope);if(pending?.id!==id)return false;
    this.remove(this.key(scope,'pending'));
    if(this.load(scope)?.revision===revision)this.clear(scope);
    return true;
  }
  migrate(scope,temporary,keys){
    if(!this.key(scope)||this.load(scope))return this.load(scope);
    let text;try{text=temporary.getItem(keys.text);}catch{return null;}
    if(text===null)return null;
    let skills=[];try{skills=JSON.parse(temporary.getItem(keys.skills)||'[]');}catch{}
    const saved=this.save(scope,{text,skills,sendMode:'send',workMode:'default'});
    if(saved)for(const key of Object.values(keys))try{temporary.removeItem(key);}catch{}
    return saved;
  }
}

if(typeof module!=='undefined')module.exports={ComposerDrafts};
