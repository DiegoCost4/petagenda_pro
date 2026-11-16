document.addEventListener('DOMContentLoaded', () => {
  const toggleValues = document.getElementById('toggle-values');
  if (toggleValues) {
    const updateToggle = () => {
      const hidden = document.documentElement.classList.contains('values-hidden');
      document.querySelectorAll('option[data-price-label]').forEach(option => {
        if (!option.dataset.visibleLabel) option.dataset.visibleLabel = option.textContent;
        option.textContent = hidden
          ? option.dataset.visibleLabel.replace(/\s-\sR\$\s[\d.,]+$/, '')
          : option.dataset.visibleLabel;
      });
      const label = hidden ? 'Mostrar valores' : 'Ocultar valores';
      toggleValues.setAttribute('aria-label', label);
      toggleValues.setAttribute('title', label);
      toggleValues.setAttribute('aria-pressed', String(hidden));
      toggleValues.querySelector('span').textContent = label;
      toggleValues.querySelector('i').className = `bi ${hidden ? 'bi-eye' : 'bi-eye-slash'} me-1`;
    };
    updateToggle();
    toggleValues.addEventListener('click', () => {
      document.documentElement.classList.toggle('values-hidden');
      try { localStorage.setItem('petagenda-hide-values', String(document.documentElement.classList.contains('values-hidden'))); } catch (error) {}
      updateToggle();
    });
  }

  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(el => new bootstrap.Tooltip(el));

  document.querySelectorAll('[data-confirm]').forEach(form => {
    form.addEventListener('submit', e => {
      const message = form.getAttribute('data-confirm') || 'Confirma esta ação?';
      if (!confirm(message)) e.preventDefault();
    });
  });
});
