// Desktop-only bootstrap. API keys never enter browser storage or preferences.
window.desktopConnected = false;
async function desktopRequest(path, data) {
  const response = await fetch(path, {method: data === undefined ? 'GET' : 'POST',
    headers: {'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(30000)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed. Please retry.');
  return result;
}

async function desktopBoot() {
  const state = await desktopRequest('/desktop/state');
  window.desktopConnected = state.connected;
  for (const key of ['tyria.defaultCharacter', 'quaggansHoard.protectedItems']) {
    if (state.preferences[key] !== undefined) localStorage.setItem(key, state.preferences[key]);
    else localStorage.removeItem(key);
  }
  const settings = document.createElement('section');
  settings.className = 'desktop-account';
  settings.innerHTML = `<div class="desktop-account-heading"><span>WINDOWS EDITION</span><button id="account-settings" type="button">Account settings</button></div>
    <form id="connect-form" hidden><h2>Your hoard, on your computer.</h2>
    <p>Create a Guild Wars 2 API key with <strong>account, characters, inventories and progression</strong> permissions. Your key is saved in Windows Credential Manager for your Windows user. It is sent only to the official Guild Wars 2 API.</p>
    <p><a href="https://account.arena.net/applications" target="_blank" rel="noopener noreferrer">Create or manage your API keys ↗</a></p>
    <label for="desktop-key">API KEY</label><input id="desktop-key" type="password" autocomplete="off" spellcheck="false" required maxlength="200" placeholder="Paste your API key">
    <div class="desktop-account-actions"><button id="connect-key" class="primary-button" type="submit">Save and connect</button><button id="forget-key" type="button">Forget saved key</button><button id="cancel-settings" type="button">Cancel</button></div>
    <p id="connection-status" role="status"></p></form>`;
  document.querySelector('main').prepend(settings);
  const form = document.getElementById('connect-form');
  const status = document.getElementById('connection-status');
  const showForm = () => {
    form.hidden = false;
    document.getElementById('forget-key').hidden = !state.connected;
    document.getElementById('cancel-settings').hidden = !state.connected;
    document.getElementById('desktop-key').focus();
  };
  document.getElementById('account-settings').onclick = showForm;
  document.getElementById('cancel-settings').onclick = () => { form.hidden = true; document.getElementById('desktop-key').value = ''; };
  form.onsubmit = async event => {
    event.preventDefault();
    const input = document.getElementById('desktop-key');
    const key = input.value.trim();
    input.value = '';
    const buttons = form.querySelectorAll('button');
    buttons.forEach(button => button.disabled = true);
    status.textContent = 'Checking permissions and saving to Windows Credential Manager…';
    status.classList.add('desktop-working');
    try {
      await desktopRequest('/desktop/connect', {key});
      location.reload();
    } catch (error) { status.textContent = error.message; }
    finally { buttons.forEach(button => button.disabled = false); status.classList.remove('desktop-working'); }
  };
  document.getElementById('forget-key').onclick = async () => {
    try { await desktopRequest('/desktop/disconnect', {}); location.reload(); }
    catch (error) { status.textContent = error.message; }
  };
  let saveQueue = Promise.resolve();
  window.persistDesktopPreferences = () => {
    const preferences = {};
    for (const key of ['tyria.defaultCharacter', 'quaggansHoard.protectedItems']) {
      const value = localStorage.getItem(key);
      if (value !== null) preferences[key] = value;
    }
    saveQueue = saveQueue.then(() => desktopRequest('/desktop/preferences', preferences)).catch(() => {
      showForm(); status.textContent = 'Your preference could not be saved to disk. Check that your Windows profile is writable.';
    });
  };
  if (!state.connected) {
    showForm();
    document.body.classList.add('desktop-disconnected');
  }
  const script = document.createElement('script');
  script.src = '/app.js';
  document.head.append(script);
}
desktopBoot().catch(() => {
  const message = document.createElement('p');
  message.className = 'lookup-error';
  message.textContent = 'The desktop app could not initialise. Close it and open it again.';
  document.querySelector('main').prepend(message);
});
