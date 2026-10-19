'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');

const listeners = new Map();
const document = {
  activeElement:null,
  addEventListener(name, handler) { listeners.set(name, handler); },
  removeEventListener(name, handler) { if (listeners.get(name) === handler) listeners.delete(name); }
};
class Element {
  constructor() {
    this.children = []; this.dataset = {}; this.attributes = {}; this.classes = new Set(); this.inert = false;
    this.classList = {add:name=>this.classes.add(name), remove:name=>this.classes.delete(name)};
  }
  append(...children) { for (const child of children) { child.parentElement = this; this.children.push(child); } }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  get isConnected() { for (let node=this; node; node=node.parentElement) if (node===document.body) return true; return false; }
  querySelectorAll() { return this.controls || []; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  getClientRects() { return [1]; }
  focus() { document.activeElement = this; }
}
const context = {document, BridgeI18n:{t:text=>text}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/features/workspace/workbench.js'), 'utf8'), context);
const Workbench = vm.runInContext('Workbench', context);

test('fullscreen preserves the mounted preview and restores background, focus and back', () => {
  const page = document.body = new Element(), outside = new Element(), panel = new Element();
  page.append(outside, panel);
  const body = new Element(), sibling = new Element(); panel.append(body, sibling);
  const trigger = new Element(), content = new Element(), iframe = new Element();
  body.append(trigger, content); content.append(iframe); body.controls = [trigger, iframe];
  const session = {key:'local|one'}, tab = {id:'file:demo.html', body};
  const workbench = Object.create(Workbench.prototype);
  workbench.current = session;
  content.scrollTop = 73;
  workbench.openPreviewFullscreen(session, tab, content, trigger);
  assert.equal(body.classes.has('wb-preview-fullscreen'), true);
  assert.equal(outside.inert, true); assert.equal(sibling.inert, true);
  assert.equal(content.parentElement, body); assert.equal(iframe.parentElement, content);
  assert.equal(content.scrollTop, 73); assert.equal(document.activeElement, trigger);
  assert.equal(trigger.attributes['aria-label'], '退出全屏');
  assert.equal(body.attributes['aria-modal'], 'true');
  assert.equal(workbench.back(), true);
  assert.equal(workbench.previewFullscreen, null);
  assert.equal(body.classes.has('wb-preview-fullscreen'), false);
  assert.equal(outside.inert, false); assert.equal(sibling.inert, false);
  assert.equal(content.parentElement, body); assert.equal(iframe.parentElement, content);
  assert.equal(content.scrollTop, 73); assert.equal(document.activeElement, trigger);
  assert.equal(trigger.attributes['aria-label'], '全屏预览');
  assert.equal(body.attributes['aria-modal'], undefined);
  assert.equal(listeners.has('keydown'), false); assert.equal(listeners.has('focusin'), false);

  workbench.openPreviewFullscreen(session, tab, content, trigger);
  const event = {key:'Escape', preventDefault() { this.prevented = true; }};
  listeners.get('keydown')(event);
  assert.equal(event.prevented, true); assert.equal(workbench.previewFullscreen, null);
});

test('fullscreen closes when another file tab is selected', () => {
  const page = document.body = new Element(), panel = new Element(), body = new Element(), content = new Element(), trigger = new Element();
  page.append(panel); panel.append(body); body.append(trigger, content);
  body.controls = [trigger];
  const session = {key:'local|two', active:'file:a', files:[], scroll:0};
  const tab = {id:'file:a', body};
  const workbench = Object.create(Workbench.prototype);
  Object.assign(workbench, {current:session, chat:{classList:{contains:()=>false}}, rememberScroll(){}, paint(){}});
  workbench.openPreviewFullscreen(session, tab, content, trigger);
  workbench.select('file:b');
  assert.equal(workbench.previewFullscreen, null);
  assert.equal(session.active, 'file:b');
  assert.equal(body.classes.has('wb-preview-fullscreen'), false);
});
