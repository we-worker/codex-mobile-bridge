'use strict';

// Read-only source rendering shared by file preview and source-mode consumers.
const BridgeSourceView = (() => {
  const extensions = {
    py:'python', pyw:'python', js:'javascript', mjs:'javascript', cjs:'javascript', jsx:'jsx',
    ts:'typescript', mts:'typescript', cts:'typescript', tsx:'tsx', json:'json', jsonc:'json',
    yaml:'yaml', yml:'yaml', toml:'toml', html:'markup', htm:'markup', xml:'markup', svg:'markup',
    css:'css', sh:'bash', bash:'bash', zsh:'bash', ps1:'powershell', psm1:'powershell',
    cmd:'batch', bat:'batch'
  };
  const languageFor = name => {
    const file = name.split('/').pop().toLowerCase();
    const extension = file.includes('.') ? file.split('.').pop() : '';
    return extensions[extension] || null;
  };
  const wrapLabel = button => {
    const english = BridgeI18n.language() === 'en';
    button.textContent = button.dataset.wrap === 'true'
      ? (english ? 'Original line width' : '原始行宽')
      : (english ? 'Wrap lines' : '自动换行');
  };
  document.addEventListener('bridge-language', () => document.querySelectorAll('.wb-source-wrap').forEach(wrapLabel));
  const create = ({name, text}) => {
    const source = document.createElement('div'); source.className = 'wb-source';
    source.dataset.wrap = 'false';
    const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'wb-source-wrap';
    toggle.dataset.wrap = 'false'; toggle.setAttribute('aria-pressed', 'false'); wrapLabel(toggle);
    toggle.onclick = () => {
      const wrap = source.dataset.wrap !== 'true';
      source.dataset.wrap = toggle.dataset.wrap = String(wrap);
      toggle.setAttribute('aria-pressed', String(wrap)); wrapLabel(toggle);
    };
    source.append(toggle);
    let lines = 1;
    for (let index = 0; index < text.length; index++) {
      const character = text.charCodeAt(index);
      if (character === 10 || character === 13 && text.charCodeAt(index + 1) !== 10) lines++;
    }
    const large = text.length > 65536 || lines > 4000;
    const body = document.createElement('div'); body.className = 'wb-source-body';
    const pre = document.createElement('pre'); pre.className = 'wb-source-code';
    const code = document.createElement('code');
    const language = languageFor(name);
    const grammar = !large && language && window.Prism?.languages[language];
    let tokens = text;
    if (grammar) try { tokens = window.Prism.tokenize(text, grammar); } catch (_) { /* Preserve the original source. */ }
    if (language) code.className = 'language-' + language;
    if (lines <= 10000) {
      const gutter = document.createElement('pre'); gutter.className = 'wb-source-gutter';
      gutter.setAttribute('aria-hidden', 'true');
      for (let index = 0; index < lines; index++) {
        const number = document.createElement('span'); number.className = 'wb-source-number';
        number.textContent = String(index + 1); number.style.gridRow = String(index + 1);
        gutter.append(number);
      }
      body.append(gutter);
      let line = document.createElement('span'); line.className = 'wb-source-line'; line.style.gridRow = '1'; code.append(line);
      let pendingCR = false, lineNumber = 1;
      const appendPiece = (value, classes) => {
        if (!value) return;
        let parent = line;
        for (const cls of classes) { const span = document.createElement('span'); span.className = cls; parent.append(span); parent = span; }
        parent.append(document.createTextNode(value));
      };
      const endLine = ending => {
        const eol = document.createElement('span'); eol.className = 'wb-source-eol'; eol.textContent = ending; line.append(eol);
        line = document.createElement('span'); line.className = 'wb-source-line'; line.style.gridRow = String(++lineNumber); code.append(line);
      };
      const appendText = (value, classes) => {
        let start = 0;
        for (let index = 0; index < value.length; index++) {
          const character = value.charCodeAt(index);
          if (pendingCR) {
            if (character === 10) { endLine('\r\n'); pendingCR = false; start = index + 1; continue; }
            endLine('\r'); pendingCR = false; start = index;
          }
          if (character === 13 || character === 10) {
            appendPiece(value.slice(start, index), classes);
            if (character === 13) pendingCR = true;
            else endLine('\n');
            start = index + 1;
          }
        }
        appendPiece(value.slice(start), classes);
      };
      const appendTokens = (items, classes = []) => {
        for (const token of Array.isArray(items) ? items : [items]) {
          if (typeof token === 'string') appendText(token, classes);
          else appendTokens(token.content, [...classes, ['token', token.type, ...[].concat(token.alias || [])].join(' ')]);
        }
      };
      appendTokens(tokens);
      if (pendingCR) endLine('\r');
    } else {
      body.classList.add('wb-source-no-gutter');
      code.textContent = text;
    }
    pre.append(code); body.append(pre); source.append(body);
    source.addEventListener('copy', event => {
      const selection = window.getSelection(), range = selection?.rangeCount === 1 && selection.getRangeAt(0);
      if (!event.clipboardData || !range || range.collapsed || !code.contains(range.startContainer) || !code.contains(range.endContainer)) return;
      const offset = (container, position) => {
        const prefix = document.createRange(); prefix.selectNodeContents(code); prefix.setEnd(container, position);
        return prefix.cloneContents().textContent.length;
      };
      event.clipboardData.setData('text/plain', text.slice(offset(range.startContainer, range.startOffset), offset(range.endContainer, range.endOffset)));
      event.preventDefault();
    });
    if (large) source.dataset.plain = 'true';
    return source;
  };
  return {create, languageFor};
})();
