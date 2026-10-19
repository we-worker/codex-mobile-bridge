'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../web/shared/dialog-dismiss.js'), 'utf8');

function fixture() {
  const listeners = new Map();
  const document = {addEventListener(type, listener) { listeners.set(type, listener); }};
  vm.runInNewContext(source, {document, Event});
  const actions = [];
  const dialog = {
    id:'test', tagName:'DIALOG', open:true, modal:true,
    matches(selector) { return selector === ':modal' && this.modal; },
    getBoundingClientRect() { return {left:100, top:100, right:300, bottom:260}; },
    querySelectorAll() { return [button]; },
    querySelector() { return button; },
    close() { this.open = false; actions.push('close'); },
  };
  const button = {dataset:{close:'test'}, disabled:false, click() { actions.push('button'); dialog.close(); }};
  function fire(type, target=dialog, x=50, y=50, extra={}) {
    const event = {target, clientX:x, clientY:y, pointerId:1, button:0,
      preventDefault() { actions.push('prevent'); }, stopPropagation() { actions.push('stop'); }, ...extra};
    listeners.get(type)(event);
  }
  function gesture({down=[50,50], up=down, move, target=dialog}={}) {
    fire('pointerdown',target,...down);
    if (move) fire('pointermove',target,...move);
    fire('pointerup',target,...up);
    fire('click',target,...up);
  }
  return {dialog,button,actions,fire,gesture};
}

test('backdrop activation uses the close button and consumes its click', () => {
  const f = fixture(); f.gesture();
  assert.deepEqual(f.actions, ['prevent','stop','button','close']);
  assert.equal(f.dialog.open, false);
});

test('inside whitespace, inside-to-outside release, drag, and scroll leave dialog open', () => {
  for (const interaction of [
    f => f.gesture({down:[120,120]}),
    f => { f.fire('pointerdown',f.dialog,120,120); f.fire('pointerup'); f.fire('click'); },
    f => f.gesture({move:[90,50]}),
    f => { f.fire('pointerdown'); f.fire('scroll'); f.fire('pointerup'); f.fire('click'); },
  ]) {
    const f=fixture(); interaction(f); assert.equal(f.dialog.open,true); assert.deepEqual(f.actions,[]);
  }
});

test('disabled close control preserves busy dialog state', () => {
  const f=fixture(); f.button.disabled=true; f.gesture();
  assert.equal(f.dialog.open,true); assert.deepEqual(f.actions,['prevent','stop']);
});

test('delegated listener also handles dialogs created after installation', () => {
  const f=fixture(); f.gesture(); assert.equal(f.dialog.open,false);
});
