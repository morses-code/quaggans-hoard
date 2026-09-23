const bifrostPreference = 'quaggansHoard.bifrostActive';
let bifrostActive = false;
let bifrostCatalog;
let bifrostProgress;
let bifrostController;
let itemAcquisitionController;

function budgetWikiOffers(entry, row, snapshot) {
  const reserved = {};
  function visit(node) {
    reserved[node.id] = (reserved[node.id] || 0) + node.allocated;
    node.children.forEach(visit);
  }
  visit(snapshot.tree);
  return {...entry, offers: entry.offers.map(offer => {
    const trades = Math.ceil(row.missing / offer.output);
    const costs = offer.costs.map(cost => {
      const isItem = cost.kind === 'item';
      const known = isItem ? snapshot.complete_scan : snapshot.wallet != null;
      const owned = (isItem ? snapshot.holdings : snapshot.wallet)?.[cost.id] || 0;
      const keep = isItem ? reserved[cost.id] || 0 : 0;
      const available = Math.max(0, owned - keep);
      return {...cost, known_owned: owned, owned: known ? owned : null, reserved: keep,
        required: trades * cost.per_trade, available: known ? available : null,
        shortfall: known ? Math.max(0, trades * cost.per_trade - available) : null};
    });
    const supported = costs.every(c => c.available != null) ? Math.min(trades, offer.limit ?? trades, ...costs.map(c => Math.floor(c.available / c.per_trade))) * offer.output : null;
    return {...offer, costs, supported_output: supported};
  })};
}

// Turn regular wiki tables into labelled cards; keep complex headers as tables.
function acquisitionCards(block, title) {
  if (!block.rows.length || !block.rows[0].length || block.spans?.[0]?.some(cell => !cell.header)) return null;
  const headers = block.rows[0].map(text => text.trim());
  if (headers.some((text, i) => !text || (block.spans?.[0]?.[i]?.colspan || 1) !== 1 || (block.spans?.[0]?.[i]?.rowspan || 1) !== 1)) return null;
  const grid = element('div', 'acquisition-source-grid');
  const carried = [];
  for (let r = 1; r < block.rows.length; r++) {
    const cells = block.rows[r];
    const spans = block.spans?.[r];
    if (cells.length === 1 && spans?.[0]?.header && spans[0].colspan === headers.length) {
      grid.append(element('h4', 'acquisition-group-title', cells[0].trim()));
      continue;
    }
    if (spans?.some(span => span.header)) return null;
    const values = Array(headers.length).fill('');
    const occupied = Array(headers.length).fill(false);
    carried.forEach((value, i) => { if (value?.remaining) { values[i] = value.text; occupied[i] = true; value.remaining--; } });
    let column = 0;
    for (let c = 0; c < cells.length; c++) {
      while (column < values.length && occupied[column]) column++;
      if (column >= headers.length || (spans?.[c]?.colspan || 1) !== 1) return null;
      values[column] = cells[c].trim();
      if ((spans?.[c]?.rowspan || 1) > 1) carried[column] = {text: values[column], remaining: spans[c].rowspan - 1};
      column++;
    }
    const card = element('section', 'vendor-offer acquisition-source-card');
    const heading = element('div', 'vendor-heading');
    const name = values[0] || title;
    heading.append(element('h4', '', name));
    card.append(element('p', 'source-card-kicker', headers[0]), heading);
    const facts = element('dl', 'source-card-facts');
    values.slice(1).forEach((value, i) => {
      if (!value.trim()) return;
      const fact = element('div', 'source-card-fact');
      fact.append(element('dt', '', headers[i + 1]), element('dd', '', value));
      facts.append(fact);
    });
    card.append(facts);
    grid.append(card);
  }
  return grid.childElementCount ? grid : null;
}

function acquisitionTextCard(text, title) {
  const card = element('section', 'vendor-offer acquisition-source-card acquisition-prose');
  card.append(element('p', 'source-card-kicker', title));
  const lines = text.split(/\n+/).map(line => line.trim()).filter(Boolean);
  if (lines.length > 1) {
    const list = element('ul', 'source-card-list');
    lines.forEach(line => list.append(element('li', '', line)));
    card.append(list);
  } else card.append(element('p', 'source-card-copy', text.trim()));
  return card;
}

function wikiAcquisitionView(entry, row, snapshot) {
  const view = element('div', 'wiki-acquisition');
  view.append(element('p', 'evidence', `GW2 Wiki revision ${entry.revision} · retrieved ${new Date(entry.checked_at).toLocaleString()}. Public results cached up to 6 hours.`));
  if (snapshot && entry.offers.length) {
    const budgets = element('details', 'wiki-source-section');
    budgets.append(element('summary', '', `Compare vendor costs with my storage (${entry.offers.length} offers)`), acquisitionPanel(row, budgetWikiOffers(entry, row, snapshot)));
    view.append(budgets);
  }
  if (!entry.sections.length) view.append(element('p', '', 'No acquisition or notes section was found on this item’s wiki page.'));
  if (entry.unparsed_offers) view.append(element('p', 'evidence', `${entry.unparsed_offers} vendor offers could not be fully interpreted. Their original costs are shown below without an affordability estimate.`));
  view.append(element('p', 'evidence', 'Check the notes and conditions below. Vendor eligibility, purchase history and shared limits are not checked.'));
  for (const section of entry.sections) {
    const details = element('details', 'wiki-source-section');
    details.open = ['acquisition', 'overview', 'notes'].includes(section.title.toLowerCase());
    const summary = element('summary', 'source-section-heading');
    const label = element('span', 'source-section-label', section.title);
    label.append(element('small', '', 'Sources, rewards & requirements'));
    summary.append(label);
    details.append(summary);
    const content = element('div', 'source-section-content');
    for (const block of section.blocks) {
      if (block.kind === 'text') content.append(acquisitionTextCard(block.text, section.title));
      else {
        const cards = acquisitionCards(block, section.title);
        if (cards) { content.append(cards); continue; }
        const scroll = element('div', 'project-table-scroll');
        scroll.tabIndex = 0;
        scroll.setAttribute('aria-label', section.title + ' table; scroll sideways for more columns');
        const table = element('table', 'wiki-source-table');
        block.rows.forEach((cells, index) => {
          const tr = element('tr', '');
          cells.forEach((text, column) => {
            const span = block.spans?.[index]?.[column];
            const cell = element((span ? span.header : index === 0) ? 'th' : 'td', '', text);
            if (span) { cell.colSpan = span.colspan; cell.rowSpan = span.rowspan; }
            tr.append(cell);
          });
          table.append(tr);
        });
        scroll.classList.add('vendor-offer', 'acquisition-source-card');
        scroll.append(table); content.append(scroll);
      }
    }
    content.append(sourceLink('View this section on the wiki ↗', entry.source + '#' + encodeURIComponent(section.title.replaceAll(' ', '_'))));
    details.append(content);
    view.append(details);
  }
  view.append(sourceLink('Source: Guild Wars 2 Wiki contributors', entry.source), document.createTextNode(' · '), sourceLink('GFDL licence', 'https://wiki.guildwars2.com/wiki/Guild_Wars_2_Wiki:Copyrights'));
  return view;
}

function acquisitionLookup(row, signal, snapshot) {
  const panel = element('div', 'acquisition-panel');
  const load = async () => {
    const finish = showLookupLoading(panel, 'Loading acquisition methods and vendor costs from the wiki', signal);
    try {
      const entry = await api(`/api/acquisition?id=${row.id}`, signal, 60000);
      if (!signal.aborted) panel.replaceChildren(wikiAcquisitionView(entry, row, snapshot));
    } catch (error) {
      if (!signal.aborted) {
        const retry = element('button', 'secondary', 'Retry wiki lookup');
        retry.type = 'button'; retry.onclick = load;
        panel.replaceChildren(element('p', 'lookup-error', error.message), retry);
      }
    } finally { finish(); }
  };
  return {panel, load};
}

function prepareItemAcquisition(item) {
  itemAcquisitionController?.abort();
  itemAcquisitionController = new AbortController();
  const details = $('item-acquisition');
  const lookup = acquisitionLookup(item, itemAcquisitionController.signal);
  details.open = false;
  details.replaceChildren(element('summary', '', 'How to obtain this item'), lookup.panel);
  details.ontoggle = () => { if (details.open) { details.ontoggle = null; lookup.load(); } };
}

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

function projectIcon(item, className = 'project-item-icon') {
  const icon = element('img', className);
  icon.alt = '';
  icon.loading = 'lazy';
  if (item.icon?.startsWith('https://render.guildwars2.com/')) icon.src = item.icon;
  else icon.hidden = true;
  return icon;
}

function tradeAmount(resource, value) {
  if (value == null) return 'Unknown';
  if (resource.kind === 'currency' && resource.id === 1) {
    return `${Math.floor(value / 10000)}g ${Math.floor(value % 10000 / 100)}s ${value % 100}c`;
  }
  return value.toLocaleString();
}

function acquisitionPanel(row, entry) {
  const panel = element('div', 'acquisition-panel');
  if (entry?.offers?.length) {
    panel.append(element('h4', '', 'Vendor exchanges'));
    panel.append(element('p', 'evidence', `Each option is an alternative, not a combined budget. Costs below cover all ${row.missing} missing items, across resets if needed. Materials reserved for the direct Bifrost recipe are excluded from spendable balances. Purchase history, vendor access and unlocks are not checked.`));
    const offers = element('div', 'vendor-offers');
    for (const offer of entry.offers) {
      const card = element('section', 'vendor-offer');
      const heading = element('div', 'vendor-heading');
      heading.append(element('h4', '', offer.vendor), element('span', 'vendor-limit', offer.limit == null ? 'See source for limits' : `${offer.limit} / ${offer.period}`));
      card.append(heading, element('p', 'vendor-area', offer.area));
      card.append(element('p', '', `Trade output: ${offer.output} × ${row.name}`));
      const coverage = element('p', 'vendor-coverage', offer.supported_output == null ? 'Affordability not fully checked — some balances are unavailable.' : `Resources cover up to ${offer.supported_output} of your missing ${row.missing}, before eligibility and past purchases.`);
      coverage.classList.toggle('vendor-short', offer.supported_output === 0);
      card.append(coverage);
      const table = element('table', 'vendor-costs');
      const header = element('tr', '');
      ['Cost', 'Per trade', 'For all missing', 'Spendable', 'Shortfall'].forEach(label => header.append(element('th', '', label)));
      const thead = element('thead', ''); thead.append(header); table.append(thead);
      const tbody = element('tbody', '');
      for (const cost of offer.costs) {
        const tr = element('tr', '');
        const name = element('td', '');
        const title = element('div', 'cost-name'); title.append(projectIcon(cost, 'cost-icon'), element('span', '', cost.name));
        name.append(title, element('small', '', cost.owned == null ? `Known count: ${tradeAmount(cost, cost.known_owned)} · incomplete scan` : `Have ${tradeAmount(cost, cost.owned)}${cost.reserved ? ` · ${tradeAmount(cost, cost.reserved)} reserved` : ''}`));
        tr.append(name);
        [cost.per_trade, cost.required, cost.available, cost.shortfall].forEach(value => tr.append(element('td', '', tradeAmount(cost, value))));
        tbody.append(tr);
      }
      table.append(tbody);
      card.append(element('p', 'cost-scroll-hint', 'Scroll sideways to see all cost columns.'));
      const scroll = element('div', 'project-table-scroll'); scroll.append(table); card.append(scroll);
      if (offer.condition) card.append(element('p', 'vendor-condition', offer.condition));
      card.append(sourceLink('Vendor & cost source ↗', offer.source));
      offers.append(card);
    }
    panel.append(offers, element('p', 'evidence', 'Costs imported from the wiki. Read the source conditions below before spending.'));
  }
  return panel;
}

function renderBifrost(data) {
  const panel = $('project-results');
  panel.replaceChildren();
  const branches = data.tree.children;
  const owned = data.tree.allocated > 0;
  const finished = branches.filter(row => row.allocated >= row.required).length;
  const heading = element('h2', '', owned ? 'The Bifrost is already owned' : `${finished} of 4 final components owned`);
  const overview = element('section', 'project-overview');
  overview.append(element('p', 'eyebrow', 'YOUR LEGENDARY JOURNEY'), heading);
  const progress = element('progress', 'project-progress');
  progress.max = 4; progress.value = owned ? 4 : finished;
  progress.setAttribute('aria-label', 'Final components owned, not total crafting effort');
  overview.append(progress, element('p', 'evidence', 'Final components owned · this meter does not estimate crafting time or gold cost.'));
  const components = element('div', 'project-components');
  branches.forEach(row => {
    const card = element('button', 'component-card');
    card.classList.toggle('component-owned', row.allocated >= row.required);
    card.type = 'button';
    card.append(projectIcon(row, 'component-icon'), element('strong', '', row.name), element('span', '', row.allocated >= row.required ? 'Owned' : row.ready ? 'Materials gathered' : 'In progress'));
    card.onclick = () => { const target = $('component-' + row.id); target.open = true; target.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'}); };
    components.append(card);
  });
  overview.append(components); panel.append(overview);
  if (!owned && data.tree.ready) panel.append(element('p', 'project-ready', 'The counted materials cover the remaining recipe tree. Craft the unfinished gifts in order, then combine the four final components in the Mystic Forge. Verify recipe unlocks and crafting levels in game.'));
  data.warnings.forEach(warning => panel.append(element('p', 'lookup-error', warning)));
  (data.acquisition_warnings || []).forEach(warning => panel.append(element('p', 'lookup-error', warning)));
  panel.append(element('p', 'evidence', `Checked ${new Date(data.checked_at).toLocaleString()}. ${data.complete_scan ? 'All requested storage sources returned.' : 'Partial scan: missing amounts may be overstated.'} Game API updates can be delayed.`));

  function branch(row, depth = 0) {
    const details = element('details', 'project-branch');
    details.open = false;
    if (depth === 0) details.id = 'component-' + row.id;
    const summary = element('summary', '');
    summary.append(projectIcon(row), element('span', 'branch-name', row.name), element('span', 'branch-count', `${row.allocated} / ${row.required}`), element('span', 'branch-state', row.missing && row.children.length ? (row.ready ? 'Materials gathered' : 'Ingredients needed') : row.missing ? `Need ${row.missing}` : 'Owned'));
    details.append(summary);
    if (row.note) details.append(element('p', '', row.note));
    const locations = data.locations[row.id] || [];
    if (locations.length) details.append(element('p', 'evidence', locations.map(place => `${place.location}: ${place.count}`).join(' · ')));
    const source = sourceLink('Requirement source', row.source);
    details.append(source);
    row.children.forEach(child => details.append(branch(child, depth + 1)));
    return details;
  }
  if (branches.length) panel.append(element('h2', '', 'The four components'));
  branches.forEach(row => panel.append(branch(row)));
  const missing = data.shopping.filter(row => row.missing > 0);
  if (missing.length) {
    panel.append(element('h2', '', 'Still to collect'));
    panel.append(element('p', 'evidence', 'Combined quantities for unfinished gifts. Shared ingredients are allocated once. Completed gifts replace their ingredients; clover gambling and precursor crafting costs are not expanded.'));
    const list = element('div', 'project-materials');
    missing.forEach(row => {
      const card = element('details', 'material-card');
      const summary = element('summary', '');
      const label = element('div', 'material-label');
      label.append(element('strong', '', row.name), element('span', '', `${row.allocated.toLocaleString()} of ${row.required.toLocaleString()} allocated · ${data.acquisition?.[row.id]?.offers?.length ? 'Vendor options & tips' : 'Acquisition tips'}`));
      summary.append(projectIcon(row), label, element('span', 'material-needed', `${row.missing.toLocaleString()} to go`));
      const meter = element('progress', 'material-progress'); meter.max = row.required; meter.value = row.allocated;
      meter.setAttribute('aria-label', `${row.name}: ${row.allocated} of ${row.required} allocated`);
      const lookup = acquisitionLookup(row, bifrostController.signal, data);
      card.ontoggle = () => { if (card.open) { card.ontoggle = null; lookup.load(); } };
      card.append(summary, meter, lookup.panel);
      list.append(card);
    });
    panel.append(list);
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
