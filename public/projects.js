const bifrostPreference = 'quaggansHoard.bifrostActive';
let bifrostActive = false;
let bifrostCatalog;
let bifrostProgress;
let bifrostController;
let legendaryItems = [];
let selectedLegendary = 0;
let trackedLegendary = 30698;
let selectedRecipe = 0;
let trackedRecipe = 0;
let trackedCatalog;
let trackedProgress;
let selectionController;
let collectionProgress;
let collectionController;

function projectName() { return bifrostCatalog?.name || legendaryItems.find(item => item.id === selectedLegendary)?.name || 'The Bifrost'; }
function updateProjectHeading() {
  $('project-title').textContent = projectName();
  $('project-subtitle').textContent = 'Gather the requirements for your next legendary.';
  const item = bifrostCatalog?.nodes[selectedLegendary] || legendaryItems.find(item => item.id === selectedLegendary);
  $('project-icon').hidden = !item?.icon?.startsWith('https://render.guildwars2.com/');
  if (!$('project-icon').hidden) $('project-icon').src = item.icon;
  $('project-guide').href = item?.source || 'https://wiki.guildwars2.com/wiki/' + encodeURIComponent(projectName().replaceAll(' ', '_'));
  const tracking = bifrostActive && trackedLegendary === selectedLegendary && trackedRecipe === selectedRecipe;
  const routes = bifrostCatalog?.routes || [];
  $('project-recipe-control').hidden = routes.length < 2;
  $('project-recipe').replaceChildren(...routes.map(route => new Option(route.label, String(route.id))));
  $('project-recipe').value = String(selectedRecipe);
  $('project-track').textContent = tracking ? 'Stop tracking' : 'Track';
  $('project-track').setAttribute('aria-pressed', String(tracking));
}

function renderLegendaryLibrary() {
  const grid = $('legendary-grid'); grid.replaceChildren();
  const query = $('legendary-search').value.trim().toLowerCase();
  const type = $('legendary-type').value;
  const subtype = $('legendary-subtype').value;
  const score = item => { const progress = collectionProgress?.items[item.id]; return progress?.owned ? 101 : progress?.percent ?? -1; };
  const items = legendaryItems.filter(item => (!type || item.type === type) && (!subtype || item.subtype === subtype) && item.name.toLowerCase().includes(query)).sort((a, b) => score(b) - score(a) || a.name.localeCompare(b.name));
  $('legendary-count').textContent = `${items.length} of ${legendaryItems.length} legendary items`;
  for (const item of items) {
    const card = element('button', 'legendary-choice'); card.type = 'button';
    card.setAttribute('aria-pressed', String(item.id === selectedLegendary));
    const text = element('span', 'legendary-choice-copy');
    text.append(element('strong', '', item.name), element('small', '', [item.type, item.weight, item.subtype].filter(Boolean).join(' · ')));
    const state = collectionProgress?.items[item.id];
    const progress = element('span', 'legendary-collection-progress');
    const label = state?.owned ? 'Owned' : state?.percent != null ? `${state.percent}%` : collectionController && !collectionProgress ? 'Checking' : '—';
    progress.append(element('strong', '', label));
    const meter = element('progress', 'legendary-collection-meter'); meter.max = 100; meter.value = state?.owned ? 100 : state?.percent || 0;
    meter.setAttribute('aria-label', state?.owned ? 'Owned in Legendary Armory' : state?.percent != null ? `${state.current} of ${state.max} linked collection objectives completed` : 'Collection progress unavailable');
    progress.append(meter);
    card.title = state?.percent != null ? `${state.current} / ${state.max} objectives: ${state.achievements.map(a => a.name).join('; ')}` : 'No reliably linked collection progress is available for this item.';
    card.append(projectIcon(item), text, progress);
    card.onclick = () => selectLegendary(item.id);
    grid.append(card);
  }
  if (!items.length) grid.append(element('p', '', 'No legendaries match your search.'));
}

function updateLegendaryCategories() {
  const type = $('legendary-type').value;
  $('legendary-subtype').replaceChildren(new Option(type === 'Weapon' ? 'All weapons' : 'All categories', ''));
  [...new Set(legendaryItems.filter(item => !type || item.type === type).map(item => item.subtype).filter(Boolean))].sort().forEach(subtype => $('legendary-subtype').add(new Option(subtype.replace(/([a-z])([A-Z])/g, '$1 $2'), subtype)));
  renderLegendaryLibrary();
}

async function loadCollectionProgress() {
  collectionController?.abort(); collectionController = new AbortController();
  const signal = collectionController.signal;
  $('legendary-refresh').disabled = true;
  const finish = showLookupLoading($('legendary-progress-status'), 'Checking legendary collections', signal);
  try {
    const data = await api('/api/legendary-progress', signal, 60000);
    if (signal.aborted) return;
    collectionProgress = data;
    $('legendary-progress-status').replaceChildren(...data.warnings.map(warning => element('p', 'lookup-error', warning)));
    renderLegendaryLibrary();
  } catch (error) {
    if (!signal.aborted) $('legendary-progress-status').replaceChildren(element('p', 'lookup-error', error.message + ' Use Refresh progress to retry.'));
  } finally { finish(); if (!signal.aborted) { $('legendary-refresh').disabled = false; collectionController = null; renderLegendaryLibrary(); } }
}

async function selectLegendary(id, route = 0) {
  selectionController?.abort(); bifrostController?.abort();
  selectionController = new AbortController(); const signal = selectionController.signal;
  selectedLegendary = id; bifrostCatalog = null; bifrostProgress = null;
  selectedRecipe = route;
  $('selected-project').hidden = false;
  updateProjectHeading(); renderLegendaryLibrary();
  $('selected-project').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
  $('project-track').disabled = true; $('project-refresh').disabled = true;
  $('project-status').textContent = 'Loading this legendary’s recipe requirements…';
  const finish = showLookupLoading($('project-results'), 'Loading legendary requirements', signal);
  try {
    const catalog = await api(id === 30698 ? '/bifrost.json' : `/api/project-definition?id=${id}&route=${route}`, signal, 60000);
    if (signal.aborted) return;
    bifrostCatalog = catalog;
    if (bifrostActive && trackedLegendary === id && trackedRecipe === route) trackedCatalog = bifrostCatalog;
    updateProjectHeading();
    $('project-track').disabled = false;
    finish();
    await refreshBifrost();
  } catch (error) {
    if (!signal.aborted) {
      const retry = element('button', 'uses-retry', 'Retry project'); retry.onclick = () => selectLegendary(id, route);
      $('project-results').replaceChildren(element('p', 'lookup-error', error.message), retry);
      $('project-status').textContent = 'This project could not load. Retry or select another legendary.';
    }
  } finally { finish(); }
}

async function loadLegendaryLibrary() {
  const panel = $('legendary-grid');
  const controller = new AbortController();
  const finish = showLookupLoading(panel, 'Loading legendary catalogue', controller.signal);
  try {
    const data = await api('/api/legendaries', controller.signal, 30000);
    legendaryItems = data.items;
    $('legendary-type').replaceChildren(new Option('All equipment', ''));
    [...new Set(legendaryItems.map(item => item.type))].sort().forEach(type => $('legendary-type').add(new Option(type, type)));
    updateLegendaryCategories();
  } catch (error) {
    const retry = element('button', 'uses-retry', 'Retry catalogue'); retry.onclick = loadLegendaryLibrary;
    panel.replaceChildren(element('p', 'lookup-error', error.message), retry);
  } finally { finish(); }
}

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
function mapBonusRotation(text) {
  // Read the rotation from the wiki text, including older cached flattened lists.
  const entries = [...text.matchAll(/\bWeek\s+(\d+)\s*[-–—:]\s*([\s\S]*?)(?=\bWeek\s+\d+\s*[-–—:]|$)/gi)];
  if (entries.length < 2 || text.slice(0, entries[0].index).trim()) return null;
  const table = element('table', 'map-bonus-rotation');
  const caption = element('caption', '', 'Map bonus reward rotation');
  const head = element('thead', '');
  const labels = element('tr', '');
  ['Week', 'Map', 'Reward total'].forEach(label => {
    const th = element('th', '', label); th.scope = 'col'; labels.append(th);
  });
  head.append(labels);
  const body = element('tbody', '');
  for (const entry of entries) {
    const value = entry[2].trim().replace(/\s*\/\s*$/, '');
    if (!value) return null;
    const reward = value.match(/^([\s\S]+?)\s*[-–—]\s*([\d,]+\s+total)\s*$/i);
    const row = element('tr', '');
    const week = element('th', 'rotation-week', `Week ${entry[1]}`); week.scope = 'row';
    const map = element('td', 'rotation-map', reward ? reward[1].trim() : value);
    const total = element('td', 'rotation-total', reward ? reward[2] : '—');
    row.append(week, map, total); body.append(row);
  }
  table.append(caption, head, body);
  return table;
}

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
      const description = element('dd', '');
      const rotation = mapBonusRotation(value);
      if (rotation) { description.append(rotation); fact.classList.add('source-card-rotation'); }
      else description.textContent = value;
      fact.append(element('dt', '', headers[i + 1]), description);
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
  const rotation = mapBonusRotation(text);
  if (rotation) { card.append(rotation); return card; }
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
  view.append(element('p', 'evidence', `GW2 Wiki revision ${entry.revision} · retrieved ${new Date(entry.checked_at).toLocaleString()}. Public results cached up to 24 hours.`));
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

function neededForBifrost(id) {
  if (!bifrostActive) return false;
  const catalog = trackedCatalog;
  if (!catalog) return true;
  if (trackedProgress?.complete_scan) return trackedProgress.needed_ids.includes(Number(id));
  return Number(id) !== catalog.root && !!catalog.nodes[String(id)];
}

function invalidateBifrost() {
  bifrostController?.abort();
  bifrostProgress = null;
  trackedProgress = null;
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
  if (projects && !collectionProgress && !collectionController) loadCollectionProgress();
  if (projects && selectedLegendary && bifrostCatalog && !bifrostProgress && !$('project-refresh').disabled) refreshBifrost();
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
    panel.append(element('p', 'evidence', `Each option is an alternative, not a combined budget. Costs below cover all ${row.missing} missing items, across resets if needed. Materials reserved for this project?s direct recipe are excluded from spendable balances. Purchase history, vendor access and unlocks are not checked.`));
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

function projectOwnedSummary(row, data) {
  const owned = Number(data.holdings?.[row.id] || 0);
  const locations = (data.locations?.[row.id] || []).map(place => `${place.source === 'bags' ? 'On ' : ''}${place.location}: ${place.count.toLocaleString()}`);
  const elsewhere = row.missing > 0 ? Math.max(0, owned - row.allocated) : 0;
  return [`${data.complete_scan ? 'Owned' : 'Known owned'}: ${owned.toLocaleString()}`, ...locations, ...(elsewhere ? [`${elsewhere.toLocaleString()} allocated to other steps`] : []), ...(data.complete_scan ? [] : ['partial scan'])].join(' · ');
}

function renderBifrost(data) {
  const panel = $('project-results');
  panel.replaceChildren();
  const branches = data.tree.children;
  const owned = data.tree.allocated > 0;
  const finished = branches.filter(row => row.allocated >= row.required).length;
  const heading = element('h2', '', owned ? `${projectName()} is already owned` : branches.length ? `${finished} of ${branches.length} final components owned` : 'Acquisition project');
  const overview = element('section', 'project-overview');
  overview.append(element('p', 'eyebrow', 'YOUR LEGENDARY JOURNEY'), heading);
  const progress = element('progress', 'project-progress');
  progress.max = 100; progress.value = owned ? 100 : data.coverage || 0;
  progress.setAttribute('aria-label', 'Recipe requirement coverage, not time or gold completion');
  overview.append(progress, element('p', 'evidence', data.coverage == null ? 'A verified recipe is unavailable. Explore acquisition details below; no completion percentage is estimated.' : `${data.coverage}% requirement coverage${data.complete_scan ? '' : ' (partial account scan)'}. Recipe branches are weighted equally; this is not time or gold completion.`));
  if (data.catalog?.scope) overview.append(element('p', 'evidence', data.catalog.scope));
  const components = element('div', 'project-components');
  branches.forEach(row => {
    const card = element('button', 'component-card');
    card.classList.toggle('component-owned', row.allocated >= row.required);
    card.type = 'button';
    card.append(projectIcon(row, 'component-icon'), element('strong', '', row.name), element('span', '', row.allocated >= row.required ? 'Owned' : row.ready ? 'Materials gathered' : 'In progress'));
    card.append(element('small', 'component-owned-quantity', projectOwnedSummary(row, data)));
    card.onclick = () => { const target = $('component-' + row.id); target.open = true; target.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'}); };
    components.append(card);
  });
  overview.append(components); panel.append(overview);
  if (!owned && data.tree.ready) panel.append(element('p', 'project-ready', 'The counted materials cover the remaining recipe tree. Craft the unfinished gifts in order, then follow the recipe source for the final combination. Verify recipe unlocks and crafting levels in game.'));
  data.warnings.forEach(warning => panel.append(element('p', 'lookup-error', warning)));
  (data.acquisition_warnings || []).forEach(warning => panel.append(element('p', 'lookup-error', warning)));
  panel.append(element('p', 'evidence', `Checked ${new Date(data.checked_at).toLocaleString()}. ${data.complete_scan ? 'All requested storage sources returned.' : 'Partial scan: missing amounts may be overstated.'} Game API updates can be delayed.`));

  function branch(row, depth = 0) {
    const details = element('details', 'project-branch');
    details.open = false;
    if (depth === 0) details.id = 'component-' + row.id;
    const summary = element('summary', '');
    const label = element('span', 'branch-name', row.name);
    label.append(element('small', 'branch-owned-quantity', projectOwnedSummary(row, data)));
    summary.append(projectIcon(row), label, element('span', 'branch-count', `${row.allocated} / ${row.required} allocated`), element('span', 'branch-state', row.missing && row.children.length ? (row.ready ? 'Materials gathered' : 'Ingredients needed') : row.missing ? `Need ${row.missing}` : 'Owned'));
    details.append(summary);
    if (row.note) details.append(element('p', '', row.note));
    const locations = data.locations[row.id] || [];
    if (locations.length) details.append(element('p', 'evidence', locations.map(place => `${place.location}: ${place.count}`).join(' · ')));
    const source = sourceLink('Requirement source', row.source);
    details.append(source);
    row.children.forEach(child => details.append(branch(child, depth + 1)));
    return details;
  }
  if (branches.length) panel.append(element('h2', '', 'Final components'));
  branches.forEach(row => panel.append(branch(row)));
  const missing = data.shopping.filter(row => row.missing > 0);
  if (missing.length) {
    panel.append(element('h2', '', 'Still to collect'));
    panel.append(element('p', 'evidence', 'Combined quantities for unfinished gifts. Final recipe ingredients are reserved before deeper crafting steps, and shared stock is counted once. Completed gifts replace their ingredients; unexpanded recipes remain acquisition targets.'));
    const list = element('div', 'project-materials');
    missing.forEach(row => {
      const card = element('details', 'material-card');
      const summary = element('summary', '');
      const label = element('div', 'material-label');
      label.append(element('strong', '', row.name), element('span', '', `${row.allocated.toLocaleString()} of ${row.required.toLocaleString()} allocated · ${data.acquisition?.[row.id]?.offers?.length ? 'Vendor options & tips' : 'Acquisition tips'}`));
      label.append(element('span', 'material-owned-quantity', projectOwnedSummary(row, data)));
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
    const data = await api(`/api/projects/bifrost?id=${selectedLegendary}&route=${selectedRecipe}`, signal, 60000);
    if (signal.aborted) return;
    bifrostProgress = data;
    if (data.catalog) bifrostCatalog = data.catalog;
    if (bifrostActive && trackedLegendary === selectedLegendary && trackedRecipe === selectedRecipe) { trackedProgress = data; trackedCatalog = bifrostCatalog; }
    updateProjectHeading(); renderLegendaryLibrary();
    renderBifrost(data);
    $('project-status').textContent = bifrostActive && trackedLegendary === selectedLegendary && trackedRecipe === selectedRecipe ? `Tracking ${projectName()}. Needed item types are protected in inventory, including surplus copies; review quantities here.` : 'Preview only. Track this recipe to protect its materials in inventory.';
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
  try { trackedLegendary = Number(localStorage.getItem('quaggansHoard.trackedLegendary')) || 30698; } catch {}
  try { trackedRecipe = Number(localStorage.getItem('quaggansHoard.trackedRecipe')) || 0; } catch {}
  $('project-recipe').onchange = () => selectLegendary(selectedLegendary, Number($('project-recipe').value));
  const updateTrackButton = updateProjectHeading;
  $('legendary-search').oninput = renderLegendaryLibrary;
  $('legendary-type').onchange = updateLegendaryCategories;
  $('legendary-subtype').onchange = renderLegendaryLibrary;
  $('legendary-refresh').onclick = updateApplicationData;
  loadLegendaryLibrary();
  updateTrackButton();
  $('inventory-tab').onclick = () => showAppView(false);
  $('projects-tab').onclick = () => showAppView(true);
  $('project-refresh').onclick = updateApplicationData;
  $('project-track').onclick = () => {
    try {
      const active = !(bifrostActive && trackedLegendary === selectedLegendary && trackedRecipe === selectedRecipe);
      localStorage.setItem(bifrostPreference, String(active));
      localStorage.setItem('quaggansHoard.trackedLegendary', String(selectedLegendary));
      localStorage.setItem('quaggansHoard.trackedRecipe', String(selectedRecipe));
      trackedRecipe = selectedRecipe;
      bifrostActive = active; trackedLegendary = selectedLegendary;
      trackedCatalog = bifrostCatalog; trackedProgress = bifrostProgress;
      window.persistDesktopPreferences?.();
      updateTrackButton(); render();
      if ($('item-dialog').open && selectedItem) renderCleanupDetails(selectedItem.item, selectedItem.slot);
      $('project-status').textContent = bifrostActive ? 'Tracking enabled. Needed item types now appear in Keep.' : 'Tracking stopped. Normal inventory categories restored.';
    } catch { $('project-status').textContent = 'Browser storage is blocked; the tracking preference could not be saved.'; }
  };
  try {
    if (bifrostActive) {
      const id = trackedLegendary;
      const route = trackedRecipe;
      const catalog = await api(id === 30698 ? '/bifrost.json' : `/api/project-definition?id=${id}&route=${route}`, undefined, 60000);
      if (bifrostActive && trackedLegendary === id && trackedRecipe === route) trackedCatalog = catalog;
    }
    render();
  } catch {
    $('legendary-progress-status').replaceChildren(element('p', 'lookup-error', 'The tracked project could not load. Select it to retry. Inventory remains protected until its requirements are known.'));
  }
}
