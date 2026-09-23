const bifrostPreference = 'quaggansHoard.bifrostActive';
let bifrostActive = false;
let bifrostCatalog;
let bifrostProgress;
let bifrostController;

function neededForBifrost(id) {
  if (!bifrostActive) return false;
  if (!bifrostCatalog) return true; // Hold disposal guidance until requirements are known.
  if (bifrostProgress?.complete_scan) return bifrostProgress.needed_ids.includes(Number(id));
  return Number(id) !== bifrostCatalog.root && !!bifrostCatalog.nodes[String(id)];
}

function invalidateBifrost() {
  bifrostController?.abort();
  bifrostProgress = null;
  if (bifrostCatalog) {
    $('project-refresh').disabled = false;
    $('project-status').textContent = 'Inventory changed or refreshed. Refresh account progress to update this project.';
    $('project-results').replaceChildren();
  }
}

function showAppView(projects) {
  $('inventory-view').hidden = projects;
  $('projects-view').hidden = !projects;
  $('inventory-tab').setAttribute('aria-pressed', String(!projects));
  $('projects-tab').setAttribute('aria-pressed', String(projects));
  if (projects && bifrostCatalog && !bifrostProgress && !$('project-refresh').disabled) refreshBifrost();
}

function renderBifrost(data) {
  const panel = $('project-results');
  panel.replaceChildren();
  const branches = data.tree.children;
  const owned = data.tree.allocated > 0;
  const finished = branches.filter(row => row.allocated >= row.required).length;
  const heading = element('h2', '', owned ? 'The Bifrost is already owned' : `${finished} of 4 final components owned`);
  panel.append(heading);
  const progress = element('progress', 'project-progress');
  progress.max = 4; progress.value = owned ? 4 : finished;
  progress.setAttribute('aria-label', 'Final components owned, not total crafting effort');
  panel.append(progress);
  if (!owned && data.tree.ready) panel.append(element('p', 'project-ready', 'The counted materials cover the remaining recipe tree. Craft the unfinished gifts in order, then combine the four final components in the Mystic Forge. Verify recipe unlocks and crafting levels in game.'));
  data.warnings.forEach(warning => panel.append(element('p', 'lookup-error', warning)));
  panel.append(element('p', 'evidence', `Checked ${new Date(data.checked_at).toLocaleString()}. ${data.complete_scan ? 'All requested storage sources returned.' : 'Partial scan: missing amounts may be overstated.'} Game API updates can be delayed.`));

  function branch(row, depth = 0) {
    const details = element('details', 'project-branch');
    details.open = row.missing > 0 && depth === 0;
    const summary = element('summary', '', `${row.name} · ${row.allocated}/${row.required} owned${row.missing && row.children.length ? (row.ready ? ' · Materials gathered' : ' · Ingredients needed') : row.missing ? ` · Need ${row.missing}` : ' · Ready'}`);
    details.append(summary);
    if (row.note) details.append(element('p', '', row.note));
    const locations = data.locations[row.id] || [];
    if (locations.length) details.append(element('p', 'evidence', locations.map(place => `${place.location}: ${place.count}`).join(' · ')));
    const source = sourceLink('Requirement source', row.source);
    details.append(source);
    row.children.forEach(child => details.append(branch(child, depth + 1)));
    return details;
  }
  branches.forEach(row => panel.append(branch(row)));
  const missing = data.shopping.filter(row => row.missing > 0);
  if (missing.length) {
    panel.append(element('h2', '', 'Still to collect'));
    panel.append(element('p', 'evidence', 'Combined quantities for unfinished gifts. Shared ingredients are allocated once. Completed gifts replace their ingredients; clover gambling and precursor crafting costs are not expanded.'));
    const table = element('table', 'project-shopping');
    const head = element('thead', '');
    const header = element('tr', '');
    ['Item', 'Required', 'Allocated', 'Still need'].forEach(label => header.append(element('th', '', label)));
    head.append(header); table.append(head);
    const body = element('tbody', '');
    missing.forEach(row => {
      const tr = element('tr', '');
      const name = element('td', ''); name.append(sourceLink(row.name, row.source)); tr.append(name);
      [row.required, row.allocated, row.missing].forEach(count => tr.append(element('td', '', String(count))));
      body.append(tr);
    });
    table.append(body);
    const scroll = element('div', 'project-table-scroll'); scroll.append(table); panel.append(scroll);
  }
}

async function refreshBifrost() {
  bifrostController?.abort();
  bifrostController = new AbortController();
  const signal = bifrostController.signal;
  bifrostProgress = null;
  $('project-refresh').disabled = true;
  $('project-status').textContent = 'Checking account-wide holdings. This does not change anything in game.';
  const finish = showLookupLoading($('project-results'), 'Counting gifts and materials across your account', signal);
  render();
  try {
    const data = await api('/api/projects/bifrost', signal, 60000);
    if (signal.aborted) return;
    bifrostProgress = data;
    renderBifrost(data);
    $('project-status').textContent = bifrostActive ? 'Tracking The Bifrost. Needed item types are protected in inventory, including surplus copies; review quantities here.' : 'Preview only. Track this project to protect its materials in inventory.';
    render();
    if ($('item-dialog').open && selectedItem) renderCleanupDetails(selectedItem.item, selectedItem.slot);
  } catch (error) {
    if (!signal.aborted) {
      $('project-results').replaceChildren(element('p', 'lookup-error', error.message));
      $('project-status').textContent = 'Progress unavailable. Use Refresh account progress to retry. Active projects keep protecting all recipe item types.';
    }
  } finally {
    if (!signal.aborted) { finish(); $('project-refresh').disabled = false; }
  }
}

async function initProjects() {
  try { bifrostActive = localStorage.getItem(bifrostPreference) === 'true'; } catch { /* Optional preference. */ }
  const updateTrackButton = () => {
    $('project-track').textContent = bifrostActive ? 'Stop tracking' : 'Track The Bifrost';
    $('project-track').setAttribute('aria-pressed', String(bifrostActive));
  };
  updateTrackButton();
  $('inventory-tab').onclick = () => showAppView(false);
  $('projects-tab').onclick = () => showAppView(true);
  $('project-refresh').onclick = refreshBifrost;
  $('project-track').onclick = () => {
    try {
      localStorage.setItem(bifrostPreference, String(!bifrostActive));
      bifrostActive = !bifrostActive;
      window.persistDesktopPreferences?.();
      updateTrackButton(); render();
      if ($('item-dialog').open && selectedItem) renderCleanupDetails(selectedItem.item, selectedItem.slot);
      $('project-status').textContent = bifrostActive ? 'Tracking enabled. Needed item types now appear in Keep.' : 'Tracking stopped. Normal inventory categories restored.';
    } catch { $('project-status').textContent = 'Browser storage is blocked; the tracking preference could not be saved.'; }
  };
  try {
    bifrostCatalog = await api('/bifrost.json', undefined, 15000);
    const icon = bifrostCatalog.nodes[bifrostCatalog.root].icon;
    if (icon?.startsWith('https://render.guildwars2.com/')) { $('project-icon').src = icon; $('project-icon').hidden = false; }
    $('project-track').disabled = false;
    $('project-refresh').disabled = false;
    $('project-status').textContent = 'Refresh account progress to see which gifts and materials you already own.';
    if (!$('projects-view').hidden) refreshBifrost();
    render();
  } catch {
    $('project-track').disabled = false;
    $('project-status').textContent = 'Requirements could not load. Reload the app to retry. While tracking is active, inventory stays in Keep until requirements can be checked.';
  }
}
