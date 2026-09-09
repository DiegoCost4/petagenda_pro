document.addEventListener('DOMContentLoaded', () => {
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(el => new bootstrap.Tooltip(el));

  document.querySelectorAll('[data-confirm]').forEach(form => {
    form.addEventListener('submit', e => {
      const message = form.getAttribute('data-confirm') || 'Confirma esta ação?';
      if (!confirm(message)) e.preventDefault();
    });
  });
});
