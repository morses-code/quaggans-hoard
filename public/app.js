const $ = (id) => document.getElementById(id);
let current = null;
let controller;
let charactersLoaded = false;
const defaultCharacterKey = 'tyria.defaultCharacter';
let defaultCharacter = '';
try { defaultCharacter = localStorage.getItem(defaultCharacterKey) || ''; } catch { /* Storage may be blocked. */ }

function updateDefaultCharacterButton() {
  const isDefault = charactersLoaded && $('character').value === defaultCharacter;
  $('save-character').disabled = !charactersLoaded;
  $('save-character').textContent = isDefault ? 'Default' : 'Make default';
  $('save-character').setAttribute('aria-pressed', String(isDefault));
  $('save-character').title = isDefault ? 'Remove this default character' : 'Load this character first on this browser';
}
let cleanupResults = {};
let cleanupController;
let cleanupExpiry;
let selectedItem;
let usesController;
let locationsController;
let craftingResults = {};
let wikiResults = {};
let analysisLoading = false;
const categoryLabels = { keep: 'Keep', sell: 'Sell / destroy', check: 'Check', crafting: 'Used in crafting', equipment: 'Equipment', consumables: 'Consumables' };
const equipmentTypes = new Set(['Armor', 'Weapon', 'Trinket', 'Back', 'Gathering', 'Bag', 'Relic']);
const protectedItemsKey = 'quaggansHoard.protectedItems';
let protectedItems = new Set();
try {
  const saved = JSON.parse(localStorage.getItem(protectedItemsKey) || '[]');
  if (Array.isArray(saved)) protectedItems = new Set(saved.filter(Number.isSafeInteger));
} catch { /* Invalid or blocked storage must not prevent inventory loading. */ }

function analysisDisplay(state, recipes = 0, wiki = 0, total = 0, account = 'Waiting', issues = false) {
  $('analysis-panel').dataset.state = state;
  $('analysis-panel').setAttribute('aria-busy', String(state === 'loading'));
  $('analysis-title').textContent = state === 'loading' ? 'Discovering what your items are for' : state === 'complete' ? 'Your inventory is ready' : state === 'warning' ? 'Some items need another look' : 'Preparing your inventory';
  $('analysis-subtitle').textContent = state === 'loading' ? 'Explore your bags while we check. Categories update as results arrive.' : state === 'complete' ? 'Checks complete. Choose a category or inspect an item.' : state === 'warning' ? 'Available results are shown below. Refresh to retry incomplete checks.' : 'Your items appear first. Their uses follow automatically.';
  for (const [key, done] of [['recipes', recipes], ['wiki', wiki]]) {
    $(key + '-progress').max = total || 1;
    $(key + '-progress').value = done;
    $(key + '-label').textContent = total ? `${done} / ${total}` : 'Waiting';
  }
  $('account-label').textContent = account;
  if (account === 'Checking…') $('account-progress').removeAttribute('value');
  else $('account-progress').value = ['Complete', 'Needs review'].includes(account) ? 100 : 0;
  const accountDone = ['Complete', 'Needs review'].includes(account);
  $('analysis-percent').textContent = total ? `${Math.round(((recipes + wiki) / total + Number(accountDone)) / 3 * 100)}%` : '—';
  if (issues) $('analysis-percent').textContent = 'Review';
}

async function loadProfile(name, signal) {
  $('profile-name').textContent = name;
  $('profile-meta').textContent = 'Loading character…';
  $('hero-art').hidden = true;
  $('art-caption').hidden = true;
  $('profession-icon').hidden = true;
  $('profession-fallback').hidden = false;
  try {
    const data = await api(`/api/character-profile?character=${encodeURIComponent(name)}`, signal);
    if (signal.aborted) return;
    $('profile-meta').textContent = [`Level ${data.level ?? '?'}`, data.race, data.profession].filter(Boolean).join(' · ');
    if (data.art && /^\/art\/[a-z]+\.jpg$/.test(data.art)) {
      $('hero-art').src = data.art;
      $('hero-art').hidden = false;
      $('art-caption').textContent = `${data.profession.toUpperCase()} PROFESSION ART · ARENANET`;
      $('art-caption').hidden = false;
    }
    if (data.icon?.startsWith('https://render.guildwars2.com/')) {
      $('profession-icon').src = data.icon;
      $('profession-icon').hidden = false;
      $('profession-fallback').hidden = true;
    }
  } catch (error) {
    if (!signal.aborted) $('profile-meta').textContent = 'Character details unavailable · Inventory is still available';
  }
}

function categoryFor(id) {
  if (neededForBifrost(id)) return 'keep';
  if (protectedItems.has(Number(id))) return 'keep';
  const type = current?.items?.[id]?.type;
  if (equipmentTypes.has(type)) return 'equipment';
  if (type === 'Consumable') return 'consumables';
  const crafting = craftingResults[id];
  const advice = cleanupResults[id];
  const wiki = wikiResults[id];
  if (crafting?.count > 0) return 'crafting';
  if (advice?.status === 'keep') return 'keep';
  if (!crafting || crafting.error || !advice) return 'check';
  if (!wiki || wiki.state === 'review') return 'check';
  if (wiki.state === 'explicit' && advice.collections_available && !advice.collections?.some(c => !c.credited || c.repeatable)) return 'sell';
  if (advice.status === 'safe' || advice.actions?.some(a => a.kind === 'vendor')) return 'sell';
  if (advice.storage?.eligible) return 'keep';
  return 'check';
}
const cleanupLabels = { safe: 'Safe to sell / discard', keep: 'Keep for now', check: 'Needs checking' };
const actionLabels = { deposit: 'Deposit materials', combine: 'Combine stacks', vendor: 'Sell to vendor', salvage: 'Consider salvaging', consume: 'Consume for currency', discard: 'Discard collection item', keep: 'Keep for now', check: 'Needs checking' };
const rarityClasses = new Set(['Junk', 'Basic', 'Fine', 'Masterwork', 'Rare', 'Exotic', 'Ascended', 'Legendary']);

function element(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, signal, timeoutMs = 0) {
  const request = new AbortController();
  const cancel = () => request.abort();
  let timedOut = false;
  if (signal?.aborted) cancel();
  signal?.addEventListener('abort', cancel, {once: true});
  const timer = timeoutMs ? setTimeout(() => { timedOut = true; request.abort(); }, timeoutMs) : null;
  try {
    const response = await fetch(path, { signal: request.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed. Please retry.');
    return data;
  } catch (error) {
    if (timedOut && !signal?.aborted) throw new Error('This lookup timed out. Please retry in a moment.');
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}

function showLookupLoading(panel, label, signal) {
  const box = element('div', 'lookup-loading');
  const spinner = element('span', 'spinner');
  spinner.setAttribute('aria-hidden', 'true');
  const text = element('div', '');
  const elapsed = element('p', '', 'Waiting for Guild Wars 2…');
  text.append(element('strong', '', label), elapsed);
  box.append(spinner, text);
  panel.replaceChildren(box);
  panel.setAttribute('aria-busy', 'true');
  const started = Date.now();
  const timer = setInterval(() => {
    const seconds = Math.floor((Date.now() - started) / 1000);
    elapsed.textContent = `${seconds}s elapsed${seconds >= 15 ? ' · Taking longer than usual. You can close this window; requests time out after 60 seconds.' : ' · Request in progress'}`;
  }, 1000);
  const finish = () => {
    clearInterval(timer);
    panel.setAttribute('aria-busy', 'false');
    signal.removeEventListener('abort', finish);
  };
  signal.addEventListener('abort', finish, {once: true});
  return finish;
}

// API descriptions contain formatting tags. Extract only text, never insert API HTML.
function descriptionText(value) {
  const document = new DOMParser().parseFromString(String(value).replace(/<br\s*\/?\s*>/gi, '\n'), 'text/html');
  document.querySelectorAll('script, style, iframe, object').forEach(node => node.remove());
  return document.body.textContent.trim();
}

function showItem(item, slot) {
  selectedItem = { item, slot };
  $('detail-icon').hidden = !item.icon?.startsWith('https://render.guildwars2.com/');
  if (!$('detail-icon').hidden) $('detail-icon').src = item.icon;
  $('item-title').textContent = item.name;
  $('item-meta').textContent = [item.rarity, item.type, `Quantity: ${slot.count}`].filter(Boolean).join(' · ');
  $('item-description').textContent = item.description ? descriptionText(item.description) : 'No description is available for this item.';
  const stats = $('item-stats');
  stats.replaceChildren();
  function stat(label, value) {
    if (value !== undefined && value !== null && value !== '') stats.append(element('dt', '', label), element('dd', '', String(value)));
  }
  stat('Required level', item.level);
  stat('Binding', slot.binding ? `${slot.binding}${slot.bound_to ? ` (${slot.bound_to})` : ''}` : undefined);
  stat('Item ID', slot.id);
  const details = item.details || {};
  stat('Defense', details.defense);
  if (details.min_power !== undefined) stat('Weapon strength', `${details.min_power}–${details.max_power}`);
  if (slot.stats?.attributes) {
    for (const [name, value] of Object.entries(slot.stats.attributes)) stat(name, `+${value}`);
  } else {
    for (const attribute of details.infix_upgrade?.attributes || []) stat(attribute.attribute, `+${attribute.modifier}`);
  }
  locationsController?.abort();
  $('find-item').disabled = false;
  $('find-item').textContent = 'Find matching copies';
  $('item-locations').replaceChildren(element('p', 'evidence', 'Search character bags, bank, shared inventory and material storage. Equipped items and guild storage are excluded.'));
  renderCleanupDetails(item, slot);
  if (!$('item-dialog').open) $('item-dialog').showModal();
  document.querySelectorAll('button.slot').forEach(card => card.setAttribute('aria-expanded', String(card.dataset.itemId === String(slot.id))));
  loadItemUses(item, slot);
}

async function loadItemUses(item, slot, page = 0) {
  usesController?.abort();
  usesController = new AbortController();
  const signal = usesController.signal;
  const panel = $('item-uses');
  const finishLoading = showLookupLoading(panel, 'Checking recipes and storage', signal);
  try {
    const data = await api(`/api/item-uses?id=${slot.id}&page=${page}&character=${encodeURIComponent($('character').value)}`, signal, 60000);
    if (signal.aborted) return;
    panel.replaceChildren(element('h3', '', 'What do I have?'));
    const storage = data.storage;
    if (storage.error) panel.append(element('p', '', storage.error));
    else {
      panel.append(element('p', '', `In this character’s bags: ${storage.carried}`));
      if (!storage.eligible) panel.append(element('p', '', 'This item has no material-storage slot. That does not mean it has no crafting uses.'));
      else {
        panel.append(element('p', '', `Material storage: ${storage.stored} / ${storage.capacity ?? 'unknown capacity'} · Total here + storage: ${storage.total}`));
        if (storage.overflow !== null) {
          panel.append(element('p', 'overflow-note', `${storage.depositable} can be deposited; ${storage.overflow} would remain in your bags because storage has no room for them.`));
        } else panel.append(element('p', '', 'Storage capacity could not be verified.'));
      }
      panel.append(element('p', 'evidence', 'Counts exclude your bank, shared slots, and other characters. API updates may be delayed.'));
    }
    panel.append(element('h3', '', 'Used to craft'));
    const crafting = data.crafting;
    if (crafting.error) panel.append(element('p', '', crafting.error));
    else {
      panel.append(element('p', '', crafting.total ? `${crafting.total} crafting recipes use this item. Page ${crafting.page + 1}.` : 'No crafting-station recipes found in the API. This does not mean the item is safe to discard.'));
      for (const recipe of crafting.recipes) {
        const section = element('section', 'action-detail');
        section.append(sourceLink(`${recipe.name} ×${recipe.count}`, recipe.wiki));
        section.append(element('p', 'evidence', `${recipe.disciplines.join(' / ')} · Rating ${recipe.rating}`));
        const list = element('ul', 'recipe-ingredients');
        for (const ingredient of recipe.ingredients) list.append(element('li', ingredient.selected ? 'selected-ingredient' : '', `${ingredient.count} × ${ingredient.name}${ingredient.selected ? ' (this item)' : ''}`));
        section.append(list, sourceLink('Recipe source', recipe.source));
        panel.append(section);
      }
      const nav = element('div', 'recipe-nav');
      for (const [label, target, visible] of [['Previous recipes', page - 1, page > 0], ['Next recipes', page + 1, crafting.has_more]]) {
        if (visible) {
          const button = element('button', '', label);
          button.type = 'button';
          button.addEventListener('click', () => loadItemUses(item, slot, target));
          nav.append(button);
        }
      }
      panel.append(nav);
    }
    panel.append(element('p', '', 'Recipe results do not verify your unlocks or crafting level. Mystic Forge recipes, vendor exchanges, and other uses may be missing; check the wiki’s Used in and Currency for sections.'));
    panel.append(sourceLink('Check other uses on the wiki', `https://wiki.guildwars2.com/wiki/Special:Search?search=${encodeURIComponent(item.chat_link || item.name)}`));
    if (crafting.error || storage.error) {
      const retry = element('button', 'uses-retry', 'Retry item lookup');
      retry.addEventListener('click', () => loadItemUses(item, slot, page));
      panel.append(retry);
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      panel.replaceChildren(element('p', 'lookup-error', error.message));
      const retry = element('button', 'uses-retry', 'Retry item lookup');
      retry.addEventListener('click', () => loadItemUses(item, slot, page));
      panel.append(retry);
    }
  } finally { if (!signal.aborted) finishLoading(); }
}

function sourceLink(label, url) {
  const link = element('a', '', label);
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
}

function renderCleanupDetails(item, slot) {
  const panel = $('item-cleanup');
  panel.replaceChildren();
  const advice = cleanupResults[slot.id];
  const status = advice?.status || 'check';
  panel.append(element('h3', '', 'Ways to clear space'));
  panel.append(element('p', '', `Category: ${categoryLabels[categoryFor(slot.id)]}`));
  if (neededForBifrost(slot.id)) panel.append(element('p', 'project-reserved', 'Reserved for The Bifrost. Review quantities in Legendary projects before using or disposing of this item.'));
  const protect = element('button', 'uses-retry', protectedItems.has(slot.id) ? 'Remove “Keep for me”' : 'Keep for me');
  protect.type = 'button';
  protect.setAttribute('aria-pressed', String(protectedItems.has(slot.id)));
  const protectionStatus = element('p', 'evidence', protectedItems.has(slot.id) ? 'You marked this item to keep. Applies to every copy of this item on this browser.' : 'Save a personal keep preference on this browser.');
  protect.addEventListener('click', () => {
    const next = new Set(protectedItems);
    if (next.has(slot.id)) next.delete(slot.id); else next.add(slot.id);
    try {
      localStorage.setItem(protectedItemsKey, JSON.stringify([...next]));
      window.persistDesktopPreferences?.();
      protectedItems = next;
      render();
      renderCleanupDetails(item, slot);
    } catch { protectionStatus.textContent = 'Browser storage is unavailable; your keep preference could not be saved.'; }
  });
  panel.append(protect, protectionStatus);
  const locations = bagLocations(slot.id);
  const space = element('section', 'action-detail');
  space.append(element('h4', '', 'Where are my copies?'));
  space.append(element('p', '', `${locations.reduce((total, row) => total + row.count, 0)} in ${locations.length} bag slot(s).`));
  const list = element('ul', 'recipe-ingredients');
  locations.forEach(row => list.append(element('li', '', `${row.location}: ${row.count}`)));
  space.append(list);
  for (const [key, label] of [['bank', 'Bank'], ['shared', 'Shared inventory']]) {
    space.append(element('p', '', `${label}: ${advice?.elsewhere?.[key] ?? (analysisLoading ? 'Checking…' : 'Unavailable')}`));
  }
  if (advice?.storage?.eligible) {
    const storage = advice.storage;
    space.append(element('p', '', `Material storage: ${storage.stored} / ${storage.capacity ?? 'unknown capacity'}`));
    if (storage.overflow != null) space.append(element('p', 'overflow-note', `${storage.depositable} can be deposited; ${storage.overflow} would remain in these bags.`));
  }
  space.append(element('p', 'evidence', 'Copies match by item ID; stats and binding may differ. Other characters are not checked. Extra copies and overflow do not mean an item is safe to destroy.'));
  panel.append(space);
  const wiki = wikiResults[slot.id];
  const notes = element('section', 'action-detail');
  notes.append(element('h4', '', 'Wiki Notes'));
  notes.append(element('p', '', wiki?.message || (analysisLoading ? 'Checking the wiki…' : 'Wiki check unavailable. Refresh to retry.')));
  if (wiki) {
    for (const note of wiki.notes || []) notes.append(element('blockquote', '', note));
    notes.append(sourceLink('Read Notes on the GW2 Wiki', wiki.source));
    if (wiki.revision) {
      const attribution = element('p', 'evidence', `GW2 Wiki contributors · revision ${wiki.revision} · checked ${new Date(wiki.checked_at).toLocaleString()} · `);
      attribution.append(sourceLink('Source revision', wiki.revision_source), document.createTextNode(' · '), sourceLink('GFDL', 'https://wiki.guildwars2.com/wiki/Guild_Wars_2_Wiki:Copyrights'));
      notes.append(attribution);
    }
    if (wiki.state === 'explicit') notes.append(element('p', '', 'This supports Sell / destroy only when no API recipes are found, collection checks succeed, and no mapped objective remains uncredited or repeatable.'));
  }
  panel.append(notes);
  if (craftingResults[slot.id]?.count > 0) panel.append(element('p', '', `Used in ${craftingResults[slot.id].count} crafting recipes. Review those uses before selling or destroying; the suggestions below are alternatives, not a disposal verdict.`));
  panel.append(element('p', '', advice ? 'Each suggestion shows its evidence. Community and conditional advice require checking the stated conditions.' : analysisLoading ? 'Loading usages and collection checks…' : 'Checks unavailable. Refresh to retry.'));
  if (advice) {
    for (const action of advice.actions || []) {
      if ((protectedItems.has(slot.id) || neededForBifrost(slot.id)) && ['vendor', 'discard', 'salvage', 'consume'].includes(action.kind)) continue;
      const section = element('section', 'action-detail');
      section.append(element('h4', '', action.label), element('span', 'evidence', action.evidence), element('p', '', action.reason), sourceLink('Source', action.source));
      panel.append(section);
    }
    if (advice.storage_note) panel.append(element('p', '', advice.storage_note));
    panel.append(element('h4', `cleanup-${status}`, neededForBifrost(slot.id) ? 'Keep for The Bifrost' : protectedItems.has(slot.id) ? 'Your preference: Keep for me' : `Collection disposal: ${cleanupLabels[status]}`));
    panel.append(element('p', '', advice.reason));
    panel.append(element('p', '', `Checked: ${new Date(advice.checked_at).toLocaleString()}. The game API may return delayed progress.`));
    for (const collection of advice.collections) {
      const row = element('p', 'collection-row');
      row.append(sourceLink(collection.name, collection.url), document.createTextNode(` — ${collection.credited ? 'Credit confirmed' : 'Credit not confirmed'}${collection.repeatable ? ' (repeatable / resetting)' : ''}`));
      panel.append(row);
    }
    if (advice.rule) {
      panel.append(element('p', '', `Disposal rule reviewed ${advice.rule.reviewed}. Requires collection-only wording and confirmed credit.`));
      panel.append(sourceLink('Verified item source', advice.rule.source));
    }
  }
  const wikiLink = advice?.rule?.wiki || advice?.wiki || `https://wiki.guildwars2.com/wiki/Special:Search?search=${encodeURIComponent(item.chat_link || item.name)}`;
  const row = element('p', '');
  row.append(sourceLink('Look up this item on the GW2 Wiki', wikiLink));
  panel.append(row);
}

async function checkCleanup() {
  if (!current) return;
  cleanupController?.abort();
  cleanupController = new AbortController();
  const signal = cleanupController.signal;
  clearTimeout(cleanupExpiry);
  cleanupResults = {};
  craftingResults = {};
  wikiResults = {};
  analysisLoading = true;
  render();
  if ($('item-dialog').open && selectedItem) renderCleanupDetails(selectedItem.item, selectedItem.slot);
  $('cleanup-status').textContent = 'Loading usages… Checking recipes, wiki Notes, collections, and storage.';
  const ids = [...new Set(current.bags.filter(Boolean).flatMap(bag => bag.inventory.filter(Boolean).map(slot => slot.id)))];
  const character = $('character').value;
  const warnings = [];
  let checked = 0;
  let wikiChecked = 0;
  let accountState = 'Checking…';
  analysisDisplay('loading', 0, 0, ids.length, accountState);
  const update = () => {
    if (signal.aborted) return;
    $('cleanup-status').textContent = `Loading usages… Recipes ${checked} / ${ids.length} · Wiki Notes ${wikiChecked} / ${ids.length}; checking collections and storage.`;
    analysisDisplay('loading', checked, wikiChecked, ids.length, accountState);
    render();
    if ($('item-dialog').open && selectedItem) renderCleanupDetails(selectedItem.item, selectedItem.slot);
  };
  try {
    if (!ids.length) { $('cleanup-status').textContent = 'No items to check.'; analysisDisplay('complete'); return; }
    await Promise.all([
      (async () => {
        for (let offset = 0; offset < ids.length && !signal.aborted; offset += 8) {
          const batch = ids.slice(offset, offset + 8);
          try {
            const data = await api(`/api/wiki-summary?ids=${batch.join(',')}`, signal);
            if (signal.aborted) return;
            Object.assign(wikiResults, data.items);
            batch.forEach(id => {
              if (!wikiResults[id]) wikiResults[id] = {state: 'unavailable', message: 'Wiki item lookup unavailable.', notes: [], source: `https://wiki.guildwars2.com/wiki/Special:Search?search=${id}`};
            });
          } catch (error) {
            if (signal.aborted) return;
            batch.forEach(id => wikiResults[id] = {state: 'unavailable', message: 'Wiki lookup failed. Refresh to retry.', notes: [], source: `https://wiki.guildwars2.com/wiki/Special:Search?search=${id}`});
          }
          wikiChecked += batch.length;
          update();
        }
      })(),
      (async () => {
        try {
          const data = await api(`/api/cleanup?ids=${ids.join(',')}&character=${encodeURIComponent(character)}`, signal);
          if (signal.aborted) return;
          cleanupResults = data.items;
          warnings.push(...(data.warnings || []));
          accountState = data.warnings?.length ? 'Needs review' : 'Complete';
          update();
        } catch (error) { if (error.name !== 'AbortError') { warnings.push(error.message); accountState = 'Needs review'; update(); } }
      })(),
      (async () => {
        for (let offset = 0; offset < ids.length && !signal.aborted; offset += 20) {
          const batch = ids.slice(offset, offset + 20);
          try {
            const data = await api(`/api/crafting-summary?ids=${batch.join(',')}`, signal);
            if (signal.aborted) return;
            Object.assign(craftingResults, data.items);
          } catch (error) {
            if (signal.aborted) return;
            batch.forEach(id => craftingResults[id] = { error: error.message });
          }
          checked += batch.length;
          update();
        }
      })(),
    ]);
    if (signal.aborted) return;
    const counts = Object.fromEntries(Object.keys(categoryLabels).map(key => [key, 0]));
    ids.forEach(id => counts[categoryFor(id)]++);
    if (Object.values(craftingResults).some(value => value.error)) warnings.push('Some recipe checks failed. Refresh to retry.');
    if (Object.values(wikiResults).some(value => value.state === 'unavailable')) warnings.push('Some wiki pages could not be checked; no wiki-based disposal approval was inferred for them.');
    analysisLoading = false;
    analysisDisplay(warnings.length ? 'warning' : 'complete', checked, wikiChecked, ids.length, accountState, warnings.length > 0);
    $('cleanup-status').textContent = Object.entries(counts).map(([kind, count]) => `${categoryLabels[kind]}: ${count}`).join(' · ') + '. ' + warnings.join(' ');
    render();
    if ($('item-dialog').open && selectedItem) renderCleanupDetails(selectedItem.item, selectedItem.slot);
    cleanupExpiry = setTimeout(checkCleanup, 5 * 60 * 1000);
  } catch (error) {
    if (error.name !== 'AbortError') { $('cleanup-status').textContent = `${error.message} Items remain Needs checking.`; analysisDisplay('warning', checked, wikiChecked, ids.length, accountState, true); }
  } finally {
    if (!signal.aborted) analysisLoading = false;
  }
}

function bagLocations(id) {
  const rows = [];
  current?.bags.forEach((bag, b) => bag?.inventory.forEach((slot, s) => {
    if (slot?.id === Number(id)) rows.push({count: slot.count, location: `Bag ${b + 1}, slot ${s + 1}`});
  }));
  return rows;
}

function spaceFlags(id, locations = bagLocations(id)) {
  const advice = cleanupResults[id];
  return {
    duplicates: locations.length > 1,
    combine: !!advice?.actions?.some(action => action.kind === 'combine'),
    overflow: advice?.storage?.overflow > 0,
    elsewhere: advice?.elsewhere?.bank > 0 || advice?.elsewhere?.shared > 0 || advice?.storage?.stored > 0,
  };
}

function subtype(item) {
  return item.details?.type || item.type || 'Unknown';
}

function refreshDetailFilters() {
  const items = Object.values(current?.items || {});
  for (const [id, values] of [
    ['gear-rarity', items.filter(item => equipmentTypes.has(item.type)).map(item => item.rarity).filter(Boolean)],
    ['gear-type', items.filter(item => equipmentTypes.has(item.type)).map(subtype)],
    ['consumable-type', items.filter(item => item.type === 'Consumable').map(subtype)],
  ]) {
    const select = $(id);
    select.length = 1;
    [...new Set(values)].sort().forEach(value => select.add(new Option(value.replace(/([a-z])([A-Z])/g, '$1 $2'), value)));
  }
  $('gear-binding').value = 'all';
  $('gear-min').value = '';
  $('gear-max').value = '';
}

function matchesEquipment(item, slot) {
  return ($('gear-rarity').value === 'all' || item.rarity === $('gear-rarity').value) &&
    ($('gear-type').value === 'all' || subtype(item) === $('gear-type').value) &&
    ($('gear-binding').value === 'all' || (slot.binding || 'unbound') === $('gear-binding').value) &&
    ($('gear-min').value === '' || (item.level != null && item.level >= Number($('gear-min').value))) &&
    ($('gear-max').value === '' || (item.level != null && item.level <= Number($('gear-max').value)));
}

function cardReason(item, slot) {
  const id = slot.id;
  if (neededForBifrost(id)) return 'Needed for The Bifrost';
  if (protectedItems.has(id)) return 'Keep for me';
  if (craftingResults[id]?.count > 0) return `Used in ${craftingResults[id].count} recipes`;
  if (equipmentTypes.has(item.type)) return `${subtype(item)}${item.level != null ? ` · Level ${item.level}` : ''}`;
  if (item.type === 'Consumable') return subtype(item).replace(/([a-z])([A-Z])/g, '$1 $2');
  if (categoryFor(id) === 'sell') return wikiResults[id]?.state === 'explicit' ? 'Wiki disposal note checked' : cleanupResults[id]?.status === 'safe' ? 'Collection credit confirmed' : 'Vendor junk';
  if (cleanupResults[id]?.status === 'keep') return 'Collection still needs this';
  return '';
}

function render() {
  const focusedSlot = document.activeElement?.dataset.slotKey;
  $('bags').replaceChildren();
  if (!current) return;
  const categoryCounts = Object.fromEntries(Object.keys(categoryLabels).map(key => [key, 0]));
  const distinct = new Set(current.bags.filter(Boolean).flatMap(bag => bag.inventory.filter(Boolean).map(slot => slot.id)));
  const spaceCounts = {duplicates: 0, combine: 0, overflow: 0, elsewhere: 0};
  const spaceById = new Map();
  distinct.forEach(id => {
    const flags = spaceFlags(id);
    spaceById.set(id, flags);
    Object.keys(spaceCounts).forEach(key => { if (flags[key]) spaceCounts[key]++; });
  });
  const storagePending = [...distinct].some(id => !cleanupResults[id]);
  const storagePartial = [...distinct].some(id => {
    const advice = cleanupResults[id];
    return advice && (!advice.storage || advice.elsewhere?.bank == null || advice.elsewhere?.shared == null || (advice.storage.eligible && advice.storage.capacity == null));
  });
  $('space-summary').textContent = `${spaceCounts.duplicates} items in multiple bag slots · ${spaceCounts.combine} to combine · ${spaceCounts.overflow} overflowing · ${spaceCounts.elsewhere} stored elsewhere${storagePending ? (analysisLoading ? ' · Storage checks pending' : ' · Storage checks unavailable') : storagePartial ? ' · Some storage could not be checked' : ''}`;
  distinct.forEach(id => categoryCounts[categoryFor(id)]++);
  Object.entries(categoryCounts).forEach(([key, count]) => $('count-' + key).textContent = count);
  document.querySelectorAll('[data-filter]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === $('cleanup-filter').value)));
  const query = $('search').value.trim().toLowerCase();
  const cleanupFilter = $('cleanup-filter').value;
  $('equipment-filters').hidden = cleanupFilter !== 'equipment';
  $('consumable-filters').hidden = cleanupFilter !== 'consumables';
  const spaceFilter = $('space-filter').value;
  let occupied = 0, total = 0, matches = 0;
  current.bags.forEach((bag, index) => {
    if (!bag) return;
    total += bag.size;
    occupied += bag.inventory.filter(Boolean).length;
    const section = element('section', 'bag');
    const heading = element('div', 'bag-heading');
    heading.append(element('h3', '', current.items[bag.id]?.name || `Bag ${index + 1}`), element('span', '', `${bag.inventory.filter(Boolean).length} / ${bag.size}`));
    section.append(heading);
    const grid = element('div', 'grid');
    bag.inventory.forEach((slot, slotIndex) => {
      if (!slot) {
        if (!query && cleanupFilter === 'all' && spaceFilter === 'all') {
          const empty = element('div', 'slot empty', '·');
          empty.setAttribute('aria-label', 'Empty slot');
          grid.append(empty);
        }
        return;
      }
      const item = current.items[slot.id] || { name: `Item #${slot.id}` };
      if (query && !item.name.toLowerCase().includes(query)) return;
      const advice = cleanupResults[slot.id];
      const primary = categoryFor(slot.id);
      if (cleanupFilter !== 'all' && cleanupFilter !== primary) return;
      if (cleanupFilter === 'equipment' && !matchesEquipment(item, slot)) return;
      if (cleanupFilter === 'consumables' && $('consumable-type').value !== 'all' && subtype(item) !== $('consumable-type').value) return;
      const space = spaceById.get(slot.id);
      if (spaceFilter !== 'all' && !space[spaceFilter]) return;
      matches++;
      const card = element('button', `slot ${rarityClasses.has(item.rarity) ? item.rarity : 'Basic'}`);
      card.type = 'button';
      card.dataset.itemId = slot.id;
      card.dataset.slotKey = `${index}-${slotIndex}`;
      card.setAttribute('aria-expanded', String($('item-dialog').open && selectedItem?.slot.id === slot.id));
      card.setAttribute('aria-haspopup', 'dialog');
      card.addEventListener('click', () => showItem(item, slot));
      const description = `${item.name} ×${slot.count}${item.rarity ? ` · ${item.rarity}` : ''}${slot.binding ? ` · ${slot.binding} bound` : ''}`;
      card.title = description;
      card.setAttribute('aria-label', description);
      if (item.icon && item.icon.startsWith('https://render.guildwars2.com/')) {
        const img = document.createElement('img');
        img.src = item.icon;
        img.alt = '';
        img.loading = 'lazy';
        card.append(img);
      } else card.append(element('span', 'unknown', '?'));
      card.append(element('span', 'quantity', String(slot.count)), element('span', 'item-name', item.name));
      card.append(element('span', `cleanup-badge cleanup-${primary}`, analysisLoading && !craftingResults[slot.id] && !['equipment', 'consumables'].includes(primary) ? 'Loading usages…' : categoryLabels[primary]));
      const reason = cardReason(item, slot);
      if (reason) card.append(element('span', 'item-reason', reason));
      const highlights = [];
      if (space.combine) highlights.push('Combine stacks');
      else if (space.duplicates) highlights.push('Multiple bag slots');
      if (space.overflow) highlights.push(`${advice.storage.overflow} overflow`);
      if (space.elsewhere) highlights.push('Stored elsewhere');
      if (highlights.length) card.append(element('span', 'space-badge', highlights.join(' · ')));
      grid.append(card);
    });
    if (grid.childElementCount) { section.append(grid); $('bags').append(section); }
  });
  $('capacity').textContent = `${occupied} / ${total}`;
  if (!$('bags').childElementCount) $('bags').append(element('div', 'empty-state', query || cleanupFilter !== 'all' || spaceFilter !== 'all' ? 'No items match these filters. Storage results update as checks finish.' : 'This character has no inventory bags equipped.'));
  if (query) $('status').textContent = `${matches} matching item stacks${current.warning ? ` · ${current.warning}` : ''}`;
  else $('status').textContent = current.warning || 'Inventory loaded. Click an item to see its description and details.';
  if (focusedSlot) document.querySelector(`[data-slot-key="${focusedSlot}"]`)?.focus({preventScroll: true});
}

async function loadInventory() {
  invalidateBifrost();
  usesController?.abort();
  cleanupController?.abort();
  clearTimeout(cleanupExpiry);
  cleanupResults = {};
  craftingResults = {};
  wikiResults = {};
  analysisLoading = false;
  analysisDisplay('idle');
  Object.keys(categoryLabels).forEach(key => $('count-' + key).textContent = '—');
  selectedItem = null;
  $('cleanup-filter').value = 'all';
  $('space-filter').value = 'all';
  $('space-summary').textContent = 'Loading bags and storage checks…';
  $('cleanup-status').textContent = 'Usage checks start automatically when the inventory loads.';
  $('item-dialog').close();
  controller?.abort();
  controller = new AbortController();
  const signal = controller.signal;
  const name = $('character').value;
  loadProfile(name, signal);
  $('inventory-loading').hidden = false;
  $('bags').setAttribute('aria-busy', 'true');
  current = null;
  $('bags').replaceChildren();
  $('summary').hidden = true;
  $('search').disabled = true;
  $('status').textContent = `Loading ${name}’s inventory…`;
  $('refresh').disabled = true;
  try {
    current = await api(`/api/inventory?character=${encodeURIComponent(name)}`, signal);
    if (signal.aborted) return;
    refreshDetailFilters();
    $('name').textContent = name;
    $('summary').hidden = false;
    $('search').disabled = false;
    render();
    $('inventory-loading').hidden = true;
    $('bags').setAttribute('aria-busy', 'false');
    checkCleanup();
    if (!$('projects-view').hidden && bifrostCatalog && !bifrostProgress) refreshBifrost();
  } catch (error) {
    if (error.name !== 'AbortError') { $('status').textContent = error.message; analysisDisplay('warning'); }
  } finally {
    if (!signal.aborted) { $('refresh').disabled = false; $('inventory-loading').hidden = true; $('bags').setAttribute('aria-busy', 'false'); }
  }
}

async function loadCharacters() {
  $('refresh').disabled = true;
  $('status').textContent = 'Loading your characters…';
  try {
    const names = await api('/api/characters');
    $('character').replaceChildren();
    names.sort((a, b) => a.localeCompare(b)).forEach(name => $('character').append(new Option(name, name)));
    charactersLoaded = names.length > 0;
    if (names.includes(defaultCharacter)) $('character').value = defaultCharacter;
    updateDefaultCharacterButton();
    $('character').disabled = !charactersLoaded;
    $('refresh').textContent = 'Refresh';
    if (charactersLoaded) await loadInventory();
    else {
      $('character').append(new Option('No characters found', ''));
      $('status').textContent = 'No characters found on this account.';
    }
  } catch (error) {
    $('character').replaceChildren(new Option('Waiting for connection', ''));
    $('status').textContent = error.message;
    analysisDisplay('warning');
    $('cleanup-status').textContent = error.message;
    $('refresh').textContent = 'Retry';
  } finally { $('refresh').disabled = false; }
}

$('save-character').addEventListener('click', () => {
  if (!charactersLoaded) return;
  const name = $('character').value;
  const clearing = defaultCharacter === name;
  const status = $('character-preference-status');
  try {
    if (clearing) localStorage.removeItem(defaultCharacterKey);
    else localStorage.setItem(defaultCharacterKey, name);
    defaultCharacter = clearing ? '' : name;
    window.persistDesktopPreferences?.();
    updateDefaultCharacterButton();
    status.textContent = clearing ? 'Default character removed.' : `${name} will load first next time on this browser.`;
  } catch {
    status.textContent = 'Your browser blocked saving this preference. Allow site storage and try again.';
  }
  status.hidden = false;
});
$('character').addEventListener('change', () => {
  $('search').value = '';
  $('character-preference-status').hidden = true;
  updateDefaultCharacterButton();
  loadInventory();
});
$('search').addEventListener('input', render);
$('cleanup-filter').addEventListener('change', render);
$('space-filter').addEventListener('change', render);
['gear-rarity', 'gear-type', 'gear-binding', 'consumable-type'].forEach(id => $(id).addEventListener('change', render));
['gear-min', 'gear-max'].forEach(id => $(id).addEventListener('input', render));
$('gear-reset').addEventListener('click', () => { refreshDetailFilters(); render(); });
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
  $('cleanup-filter').value = $('cleanup-filter').value === button.dataset.filter ? 'all' : button.dataset.filter;
  render();
}));
const itemDialog = $('item-dialog');
$('find-item').addEventListener('click', async () => {
  if (!selectedItem) return;
  locationsController?.abort();
  locationsController = new AbortController();
  const signal = locationsController.signal;
  const panel = $('item-locations');
  $('find-item').disabled = true;
  $('find-item').textContent = 'Searching…';
  const finishLoading = showLookupLoading(panel, 'Searching account storage and character bags', signal);
  try {
    const data = await api(`/api/item-locations?id=${selectedItem.slot.id}`, signal, 60000);
    if (signal.aborted) return;
    panel.replaceChildren(element('p', '', `${data.total} matching copies found${data.warnings.length ? ' (partial results)' : ''}.`));
    const list = element('ul', 'recipe-ingredients');
    data.locations.forEach(row => list.append(element('li', '', `${row.location} · ${row.slot}: ${row.count}${row.binding ? ` · ${row.binding} bound${row.bound_to ? ` to ${row.bound_to}` : ''}` : ''}`)));
    panel.append(list);
    data.warnings.forEach(warning => panel.append(element('p', 'overflow-note', warning)));
    panel.append(element('p', 'evidence', 'Matches share an item ID; stats, upgrades and binding may differ. Equipped items and guild storage are excluded. API updates can be delayed.'));
  } catch (error) {
    if (!signal.aborted) panel.replaceChildren(element('p', 'lookup-error', error.message));
  } finally {
    if (!signal.aborted) {
      finishLoading();
      $('find-item').disabled = false;
      $('find-item').textContent = 'Search again';
    }
  }
});
let backdropPointerDown = false;
function isOutsideItemDialog(event) {
  const bounds = itemDialog.getBoundingClientRect();
  return event.target === itemDialog && (event.clientX < bounds.left || event.clientX > bounds.right ||
    event.clientY < bounds.top || event.clientY > bounds.bottom);
}
itemDialog.addEventListener('pointerdown', event => {
  backdropPointerDown = isOutsideItemDialog(event);
});
itemDialog.addEventListener('click', event => {
  if (backdropPointerDown && isOutsideItemDialog(event)) itemDialog.close();
  backdropPointerDown = false;
});
itemDialog.addEventListener('close', () => {
  locationsController?.abort();
  backdropPointerDown = false;
  usesController?.abort();
  document.querySelectorAll('button.slot').forEach(card => card.setAttribute('aria-expanded', 'false'));
});
$('hero-art').addEventListener('error', () => { $('hero-art').hidden = true; $('art-caption').hidden = true; });
$('profession-icon').addEventListener('error', () => { $('profession-icon').hidden = true; $('profession-fallback').hidden = false; });
$('refresh').addEventListener('click', () => charactersLoaded ? loadInventory() : loadCharacters());
initProjects();
if (window.desktopConnected !== false) loadCharacters();
