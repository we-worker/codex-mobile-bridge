'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');

const root = path.resolve(__dirname, '..');
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.style = {}; this.className = ''; this.value = ''; this.classList = {add:name=>{this.className += ' ' + name;}}; }
  get textContent() { return this.value + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this.value = value; this.children = []; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.value = ''; this.children = children; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener() {}
}
const elements = [], events = new Map();
const context = {window:{}, BridgeI18n:{language:()=> 'zh', t:text=>text}, AbortController, document:{createElement:tag=>{const element=new Element(tag);elements.push(element);return element;},createTextNode:text=>({textContent:text}),addEventListener:(name,fn)=>events.set(name,fn),querySelectorAll:selector=>elements.filter(element=>selector==='.wb-source-wrap'&&element.className==='wb-source-wrap')}};
vm.createContext(context);
for (const file of ['web/vendor/prism/source-view.min.js', 'web/features/workspace/source-view.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, file), 'utf8'), context, {filename:file});
}
const sourceView = vm.runInContext('BridgeSourceView', context);
const tokens = node => [node, ...(node.children || []).flatMap(tokens)];
const parts = view => { const body=view.children[1], gutter=body.children.find(child=>child.className==='wb-source-gutter'), pre=body.children.find(child=>child.className==='wb-source-code'); return {body,gutter,code:pre.children[0]}; };

test('bundled grammars cover the supported source types', () => {
  const names = ['x.py','x.js','x.ts','x.jsx','x.tsx','x.json','x.yaml','x.toml','x.html','x.css','x.sh','x.ps1','x.cmd'];
  for (const name of names) {
    const language = sourceView.languageFor(name);
    assert.ok(language, name);
    assert.ok(context.window.Prism.languages[language], name);
    assert.match(context.window.Prism.highlight('const value = "中文"', context.window.Prism.languages[language], language), /token|const/);
  }
  assert.equal(sourceView.languageFor('README.unknown'), null);
});

test('highlighted code preserves every source character and keeps line numbers separate', () => {
  const original = 'const 中文 = "<&>\u00a0";\r\n\tconsole.log(中文);\r\n';
  const view = sourceView.create({name:'sample.js', text:original});
  const {gutter,code} = parts(view);
  assert.deepEqual(gutter.children.map(row=>row.textContent), ['1','2','3']);
  assert.equal(gutter.attributes['aria-hidden'], 'true');
  assert.equal(code.textContent, original);
  assert.equal(code.children.length, 3);
  assert.deepEqual(code.children.map(row=>row.style.gridRow), ['1','2','3']);
  assert.ok(tokens(code).some(node => node.className?.includes('token')));
  assert.ok(tokens(code).some(node => node.textContent?.includes('\u00a0')));
  assert.equal(tokens(code).filter(node => node.tagName === 'img' || node.tagName === 'script').length, 0);
});

test('all bundled grammars preserve CRLF, lone CR, NBSP, tabs and hostile markup as text', () => {
  const original = '<script>\u00a0中文\t</script>\r\nnext\rline';
  for (const name of ['x.py','x.js','x.ts','x.jsx','x.tsx','x.json','x.yaml','x.toml','x.html','x.css','x.sh','x.ps1','x.cmd']) {
    const code = parts(sourceView.create({name, text:original})).code;
    assert.equal(code.textContent, original, name);
    assert.equal(tokens(code).filter(node => node.tagName === 'script').length, 0, name);
  }
});

test('unknown or expensive source falls back to original text', () => {
  const unknown = sourceView.create({name:'opaque.xyz', text:'\t中文\n\nend'});
  assert.equal(parts(unknown).code.textContent, '\t中文\n\nend');
  assert.deepEqual(parts(unknown).gutter.children.map(row=>row.textContent), ['1','2','3']);
  const big = 'print("x")\n'.repeat(7000);
  const view = sourceView.create({name:'big.py', text:big});
  assert.equal(view.dataset.plain, 'true');
  assert.equal(parts(view).code.textContent, big);
  const manyLines = sourceView.create({name:'many.py', text:'\n'.repeat(10001)});
  assert.equal(parts(manyLines).gutter, undefined);
  assert.equal(parts(manyLines).code.textContent, '\n'.repeat(10001));
});

test('line numbers follow LF, CRLF and CR without normalizing source', () => {
  const original = 'a\r\nb\rc\nd';
  const view = sourceView.create({name:'a.txt', text:original});
  assert.deepEqual(parts(view).gutter.children.map(row=>row.textContent), ['1','2','3','4']);
  assert.equal(parts(view).code.textContent, original);
});

test('wrap toggle preserves original line rows, highlighting and source text across CRLF tokens', () => {
  const original = '/* 多行\r\n注释 */\r\nconst long = "' + 'x'.repeat(240) + '";\t// end\r\n';
  const view = sourceView.create({name:'sample.js', text:original}), toggle=view.children[0], {gutter,code}=parts(view);
  assert.equal(toggle.textContent, '自动换行');assert.equal(view.dataset.wrap, 'false');
  assert.deepEqual(gutter.children.map(row=>row.style.gridRow), ['1','2','3','4']);
  assert.ok(tokens(code).some(node=>node.className?.includes('token comment')));
  toggle.onclick();assert.equal(view.dataset.wrap, 'true');assert.equal(toggle.attributes['aria-pressed'], 'true');assert.equal(toggle.textContent, '原始行宽');
  assert.equal(code.textContent, original);
  toggle.onclick();assert.equal(view.dataset.wrap, 'false');assert.equal(code.textContent, original);
  context.BridgeI18n.language=()=> 'en';events.get('bridge-language')();assert.equal(toggle.textContent, 'Wrap lines');
  toggle.onclick();assert.equal(toggle.textContent, 'Original line width');assert.equal(code.textContent, original);
  context.BridgeI18n.language=()=> 'zh';
});

test('a CRLF split across Prism tokens still creates one numbered source line', () => {
  const tokenize=context.window.Prism.tokenize;
  context.window.Prism.tokenize=()=>[{type:'comment',content:'a\r'},'\nb'];
  try {
    const {gutter,code}=parts(sourceView.create({name:'a.js',text:'a\r\nb'}));
    assert.deepEqual(gutter.children.map(row=>row.textContent), ['1','2']);
    assert.equal(code.children.length,2);
    assert.equal(code.textContent,'a\r\nb');
    assert.ok(tokens(code).some(node=>node.className?.includes('token comment')));
  } finally {context.window.Prism.tokenize=tokenize;}
});

test('file preview copies the original source rather than rendered tokens or line numbers', async () => {
  context.BridgeI18n = {language:()=> 'zh', t:text=>text};
  const copied = [];
  context.window.BridgeClipboard = {copy:async getText=>copied.push(await getText())};
  vm.runInContext(fs.readFileSync(path.join(root, 'web/features/workspace/workbench.js'), 'utf8'), context);
  const Workbench = vm.runInContext('Workbench', context);
  const workbench = Object.create(Workbench.prototype);
  const session = {key:'test', files:[]};
  const original = 'const x = "\u00a0";\r\n';
  Object.assign(workbench, {
    current:session, sessions:new Map([[session.key, session]]),
    node:(tag, cls='', text)=>{const element=new Element(tag);element.className=cls;if(text!==undefined)element.textContent=text;return element;},
    button:(text, action)=>{const button=new Element('button');button.textContent=text;button.onclick=action;return button;},
    raw:element=>element, select:()=>{}, url:()=>'/fixture',
    request:async()=>({kind:'text', name:'file.js', size:original.length, text:original})
  });
  await workbench.preview(session, {name:'file.js', path:'file.js'});
  const [head, content] = session.files[0].body.children;
  assert.equal(parts(content.children[0]).code.textContent, original);
  assert.equal(head.children[0].className, 'wb-preview-title');
  assert.equal(head.children[1].className, 'wb-preview-actions');
  assert.deepEqual(head.children[1].children.map(child=>child.className), ['wb-download','wb-preview-expand','wb-source-copy']);
  const copy = tokens(head).find(child=>child.className==='wb-source-copy');
  assert.ok(copy);
  await copy.onclick();
  assert.deepEqual(copied, [original]);
});

test('HTML preview keeps mode controls separate and its Escape signal exits only its fullscreen', async () => {
  let options, exits = 0;
  context.BridgeHtmlPreview = {create(value) { options = value; return {element:new Element('iframe'), dispose() {}}; }};
  const Workbench = vm.runInContext('Workbench', context), workbench = Object.create(Workbench.prototype);
  const session = {key:'html', files:[]};
  Object.assign(workbench, {
    current:session, sessions:new Map([[session.key, session]]),
    node:(tag, cls='', text)=>{const element=new Element(tag);element.className=cls;if(text!==undefined)element.textContent=text;return element;},
    button:(text, action)=>{const button=new Element('button');button.textContent=text;button.onclick=action;return button;},
    raw:element=>element, select:()=>{}, url:()=>'/fixture', closePreviewFullscreen:()=>{exits++;},
    request:async()=>({kind:'text', name:'index.html', size:30, text:'<button>Click</button>'})
  });
  await workbench.preview(session, {name:'index.html', path:'index.html'});
  const tab = session.files[0], [head,modes,content] = tab.body.children;
  assert.equal(modes.className, 'wb-preview-modes');
  assert.deepEqual(head.children[1].children.map(child=>child.className), ['wb-download','wb-preview-expand','wb-source-copy']);
  assert.equal(content.children[0].tagName, 'iframe');
  options.onEscape(); assert.equal(exits, 0);
  workbench.previewFullscreen = {tab}; options.onEscape(); assert.equal(exits, 1);
});
