'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

test('HTML preview sends bounded text only to its opaque shell after a matching ready message', () => {
  const listeners = new Map();
  const sent = [];
  const document = {createElement(tag) {
    const node = {tag, children: [], attrs: {}, setAttribute(key, value) {this.attrs[key] = value;},
      append(child) {this.children.push(child);}, remove() {this.removed = true;}};
    if (tag === 'iframe') node.contentWindow = {postMessage: (...args) => sent.push(args)};
    return node;
  }};
  const window = {BridgeRelayBase: '/d/' + 'a'.repeat(32),
    addEventListener(name, callback) {listeners.set(name, callback);},
    removeEventListener(name, callback) {if (listeners.get(name) === callback) listeners.delete(name);}};
  const context = vm.createContext({document, window, TextEncoder, module: {exports: {}},
    setTimeout: callback => callback, clearTimeout() {}});
  vm.runInContext(fs.readFileSync(path.join(root, 'web/features/workspace/html-preview.js'), 'utf8'), context);
  const preview = context.module.exports.create({text: 'x'.repeat(512 * 1024)});
  const frame = preview.element.children[0];
  assert.equal(frame.attrs.sandbox, 'allow-scripts');
  assert.equal(frame.src, window.BridgeRelayBase + '/html-preview-shell');
  const receive = listeners.get('message');
  receive({source: {}, origin: 'null', data: {type: 'bridge-html-preview-ready',instance:'a'.repeat(32)}});
  receive({source: frame.contentWindow, origin: 'https://example.test', data: {type: 'bridge-html-preview-ready',instance:'a'.repeat(32)}});
  assert.equal(sent.length, 0);
  receive({source: frame.contentWindow, origin: 'null', data: {type: 'bridge-html-preview-ready',instance:'a'.repeat(32)}});
  assert.equal(sent.length, 1);
  assert.equal(sent[0][0].text.length, 512 * 1024);
  assert.equal(sent[0][1], '*');
  assert.equal(listeners.has('message'), true);
  receive({source:frame.contentWindow,origin:'null',data:{type:'bridge-html-preview-ready',instance:'a'.repeat(32)}});
  assert.equal(sent.length,1);
  receive({source:frame.contentWindow,origin:'null',data:{type:'bridge-html-preview-ready',instance:'b'.repeat(32)}});
  assert.equal(sent.length,2);
  assert.equal(sent[1][0].text,sent[0][0].text);
  assert.equal(sent[1][0].instance,'b'.repeat(32));
  preview.dispose();
  assert.equal(listeners.has('message'),false);
  assert.equal(frame.removed, true);
  assert.throws(() => context.module.exports.create({text: 'x'.repeat(512 * 1024 + 1)}));
});

test('fixed shell accepts one same-origin parent message and rejects oversized content', () => {
  const shell = fs.readFileSync(path.join(root, 'web/features/workspace/html-preview-shell.html'), 'utf8');
  const script = shell.match(/<script>([\s\S]*?)<\/script>/i)[1];
  const listeners = new Map();
  const writes = [];
  const parent = {postMessage: (...args) => writes.push(['ready', ...args])};
  const document = {open: () => writes.push(['open']), write: value => writes.push(['write', value]),
    close: () => writes.push(['close'])};
  const window = {addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: (name, callback) => {if (listeners.get(name) === callback) listeners.delete(name);}};
  const context = vm.createContext({parent, document, window, TextEncoder, URL, crypto:require('node:crypto').webcrypto,
    location: {href: 'https://bridge.test/html-preview-shell'}});
  vm.runInContext(script, context);
  // document.open/write keeps the Window's lexical environment. Workspace HTML
  // must remain free to declare names that the fixed handshake also uses.
  assert.doesNotThrow(() => vm.runInContext('const sourceOrigin = "local", receive = "local";', context));
  assert.equal(writes[0][2], 'https://bridge.test');
  const receive = listeners.get('message');
  receive({source: {}, origin: 'https://bridge.test', data: {type: 'bridge-html-preview-content', instance:writes[0][1].instance, text: 'bad'}});
  receive({source: parent, origin: 'https://other.test', data: {type: 'bridge-html-preview-content', instance:writes[0][1].instance, text: 'bad'}});
  receive({source: parent, origin: 'https://bridge.test', data: {type: 'bridge-html-preview-content', instance:writes[0][1].instance, text: 'x'.repeat(512 * 1024 + 1)}});
  assert.equal(writes.length, 1);
  receive({source: parent, origin: 'https://bridge.test', data: {type: 'bridge-html-preview-content', instance:writes[0][1].instance, text: '<button>OK</button>'}});
  assert.deepEqual(writes.slice(1), [['open'], ['write', '<button>OK</button>'], ['close']]);
  assert.equal(listeners.has('message'), false);
  listeners.get('keydown')({key:'Enter'}); assert.equal(writes.length,4);
  listeners.get('keydown')({key:'Escape'});
  assert.equal(writes[4][1].type,'bridge-html-preview-escape');
  assert.equal(writes[4][2],'https://bridge.test');
});


test('fullscreen Escape accepts only the ready opaque preview and never resends HTML', () => {
  const listeners = new Map(), sent = [];
  let exits = 0;
  const document = {createElement(tag) {
    const node = {children:[],setAttribute(){},append(child){this.children.push(child);},remove(){}};
    if(tag==='iframe')node.contentWindow={postMessage:value=>sent.push(value)};
    return node;
  }};
  const window = {addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name);}};
  const context=vm.createContext({document,window,TextEncoder,module:{exports:{}},setTimeout:()=>1,clearTimeout(){}});
  vm.runInContext(fs.readFileSync(path.join(root,'web/features/workspace/html-preview.js'),'utf8'),context);
  const preview=context.module.exports.create({text:'<button>OK</button>',onEscape:()=>exits++});
  const frame=preview.element.children[0], receive=listeners.get('message');
  const send=(type,source=frame.contentWindow,origin='null')=>receive({source,origin,data:{type,instance:'a'.repeat(32)}});
  send('bridge-html-preview-escape'); assert.equal(exits,0);
  send('bridge-html-preview-ready'); send('bridge-html-preview-ready'); assert.equal(sent.length,1);
  send('bridge-html-preview-escape',{}); send('bridge-html-preview-escape',frame.contentWindow,'https://bridge.test'); assert.equal(exits,0);
  send('bridge-html-preview-escape'); assert.equal(exits,1);
  preview.dispose(); assert.equal(listeners.has('message'),false);
  send('bridge-html-preview-escape'); assert.equal(exits,1);
});
