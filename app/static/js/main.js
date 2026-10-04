// Document Tracking System — progressive-enhancement JS
document.addEventListener('DOMContentLoaded', () => {
  // Confirmation dialogs on forms that opt in via data-confirm.
  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Disable submit buttons after first click to avoid double submissions.
  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button[type="submit"]');
      if (button && !form.dataset.allowDouble) {
        setTimeout(() => { button.disabled = true; }, 0);
      }
    });
  });

  // Auto-dismiss success/info flashes after a few seconds.
  setTimeout(() => {
    document.querySelectorAll('.alert-dismissible').forEach((alertEl) => {
      if (window.bootstrap && window.bootstrap.Alert) {
        window.bootstrap.Alert.getOrCreateInstance(alertEl).close();
      }
    });
  }, 6000);
});
