document.addEventListener('DOMContentLoaded', () => {
  const decorationForm = document.getElementById('christmas-decoration-form');
  if (decorationForm) {
    const toggle = document.getElementById('christmas-decoration-toggle');
    const status = document.getElementById('christmas-decoration-status');
    const saveButton = decorationForm.querySelector('button[type="submit"]');
    toggle.addEventListener('change', () => {
      status.textContent = 'Alteração não salva';
    });
    decorationForm.addEventListener('submit', async event => {
      event.preventDefault();
      saveButton.disabled = true;
      status.textContent = 'Salvando...';
      try {
        const response = await fetch(decorationForm.action, {
          method: 'POST',
          body: new FormData(decorationForm),
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin'
        });
        if (!response.ok) throw new Error('Falha ao salvar');
        const data = await response.json();
        document.documentElement.classList.toggle('christmas-enabled', data.christmas_decoration_enabled);
        toggle.checked = data.christmas_decoration_enabled;
        status.textContent = data.christmas_decoration_enabled ? 'Ativada' : 'Desativada';
      } catch (error) {
        status.textContent = 'Não foi possível salvar. Tente novamente.';
      } finally {
        saveButton.disabled = false;
      }
    });
  }

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
