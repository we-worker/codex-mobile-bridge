'use strict';
(() => {
  let pressed = null;
  let released = null;
  const outside = (dialog, event) => {
    const box = dialog.getBoundingClientRect();
    return event.clientX < box.left || event.clientX > box.right ||
      event.clientY < box.top || event.clientY > box.bottom;
  };
  const closeControl = dialog => {
    const marked = [...dialog.querySelectorAll('[data-close]')]
      .find(button => button.dataset.close === dialog.id);
    return marked || dialog.querySelector(
      '.picker-head > button:last-of-type, .client-disable-options > button:last-child, ' +
      '.reset-confirm-actions > button:first-child, .wb-upload-cancel, ' +
      '.copy-dialog > button, .image-preview-toolbar > button:first-child'
    );
  };
  const dismiss = dialog => {
    const button = closeControl(dialog);
    if (button) { if (!button.disabled) button.click(); return; }
    if (typeof dialog.requestClose === 'function') dialog.requestClose();
    else {
      const cancel = new Event('cancel', {cancelable:true});
      if (dialog.dispatchEvent(cancel) && dialog.open) dialog.close();
    }
  };
  document.addEventListener('pointerdown', event => {
    released = pressed = null;
    if (event.button !== 0 || event.target.tagName !== 'DIALOG' ||
        !event.target.matches(':modal') || !outside(event.target, event)) return;
    pressed = {dialog:event.target, id:event.pointerId, x:event.clientX, y:event.clientY, moved:false};
  }, true);
  document.addEventListener('pointermove', event => {
    if (pressed?.id === event.pointerId &&
        Math.hypot(event.clientX - pressed.x, event.clientY - pressed.y) > 8) pressed.moved = true;
  }, true);
  document.addEventListener('pointercancel', () => { pressed = released = null; }, true);
  document.addEventListener('scroll', () => { pressed = released = null; }, true);
  document.addEventListener('pointerup', event => {
    if (!pressed || pressed.id !== event.pointerId) return;
    const gesture = pressed; pressed = null;
    if (!gesture.moved && Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) <= 8 &&
        event.target === gesture.dialog && gesture.dialog.open && outside(gesture.dialog, event)) released = gesture.dialog;
  }, true);
  document.addEventListener('click', event => {
    const dialog = released; released = null;
    if (!dialog || !dialog.open || event.target !== dialog || !dialog.matches(':modal') ||
        !outside(dialog, event)) return;
    event.preventDefault(); event.stopPropagation();
    dismiss(dialog);
  }, true);
})();
