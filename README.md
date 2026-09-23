# Quaggan’s Hoard · Inventory Companion

Windows desktop development is on `windows-app`; the original working browser app
is preserved on `main` and tag `web-baseline`. See [Windows setup and packaging](WINDOWS.md).
The desktop build uses Windows Credential Manager instead of `.env` and includes
its own Python runtime. Browser mode below remains supported.

A local, read-only character inventory viewer. Python 3.10+; no dependencies.

The interface takes its parchment, crimson, and ink palette from the Guild Wars 2 website. Character selection loads race, level, profession, and official profession artwork/emblems independently from the inventory. These are profession illustrations, not rendered portraits of your character. Source attribution is in `public/art/SOURCES.md`.

An analysis panel shows separate recipe, wiki, and collection/storage progress, with distinct completion and partial-failure states. Category cards double as filters. Item hover/selection and the inspector use short transitions; the interface respects `prefers-reduced-motion` and supports narrow screens and keyboard navigation.

## Run

1. Put your API key in `.env`:
   ```dotenv
   GW2_API_KEY=your_key_here
   ```
   Create a key at https://account.arena.net/applications with **account**, **characters**, and **inventories** permissions. If `.env` is missing, copy `.env.example` to `.env` first.
2. Run `python server.py` from this folder.
3. Open http://127.0.0.1:8000 and choose a character.

The key stays on the Python server and `.env` is ignored by Git. The server only listens on your own computer. An existing `GW2_API_KEY` environment variable takes precedence over `.env`.

Items are grouped by bag, with names, icons, quantities, rarity borders, and empty slots. Search filters item names. Click an item (or focus it and press Enter) to open its description, rarity, quantity, binding, and available equipment stats. Close the panel with Close or Escape. Items without an API description show a fallback message. Refresh requests the selected character again; the GW2 API may serve cached inventory for several minutes. Unequipped bags and account-wide shared inventory are not included.

API reference: https://wiki.guildwars2.com/wiki/API:2/characters/:id/inventory

## Inventory cleanup

Selecting a character displays the inventory immediately, then automatically checks recipes, collections, and storage. A **Loading usages…** message shows recipe progress. Refresh reruns the checks; switching characters cancels the old browser requests and ignores stale results. Collection verification needs **progression** permission; other information remains available without it.

The four categories are **Keep**, **Sell / destroy**, **Check**, and **Used in crafting** (plus All items). Confirmed recipe inputs take priority over all other categories. Keep covers known uncredited collections and remaining material-storage items. Sell / destroy covers disposal or vendor recommendations only after a successful recipe search finds no recipes. Unresolved, pending, or failed checks stay Check. No recipes found does not itself approve disposal. Crafting coverage is limited to the API; the wiki may document other uses.

Items can have multiple suggestions. Click an item for conditions, evidence labels, source links, and collection progress. Suggestions are read-only; perform the chosen action in the game.

- **Deposit materials:** checks material-storage membership and available capacity. Unknown capacity is labelled conditional; full storage is explained instead of suggesting disposal.
- **Combine stacks:** checks this character's fresh bag contents for matching item ID, binding, stats, and other metadata. Requires at least one observed multi-item stack and estimates slots saved using a 250-item limit. It does not compare other characters or bank stacks.
- **Sell to vendor:** suggests vendor junk as community advice, respecting NoSell and known uncredited objectives. Confirmed collection-only items are sold rather than discarded if they have vendor value.
- **Consider salvaging:** conditional advice for explicitly labelled salvage items, excluding ectoplasm, equipment, known storage materials, and NoSalvage items. It does not claim this is the most profitable option.
- **Consume for currency:** conditional advice for currency consumables. Review caps and alternative uses first; ordinary food, boosters, and unlock consumables are not automatically recommended.
- **Collection-only disposal:** covers trophies with the exact official description “This item only has value as part of a collection.” and confirmed credit for every directly mapped objective. Repeatable/resetting achievements, missing mappings, and missing progress block approval. The three original item-specific rules remain as additional mapping checks. Collection completion alone never approves disposal.

The generic collection, junk, and salvage approaches were informed by [GW2Stacks](https://github.com/zwei2stein/gw2stacks/blob/main/data/model.py). This implementation adds collection checks, independent source failures, and visible conditions. It does not import or execute external code, and your API key is sent only to the official GW2 API. Community suggestions are not labelled verified disposal guidance.

The public achievement catalog and successful recipe searches are cached in memory for one hour. Recipe lookups use at most four upstream requests at once and update the browser in batches of twenty items. Failed searches are not cached. Account progress is requested on every check. Checks refresh automatically after five minutes and are cleared when changing characters or refreshing inventory. The displayed timestamp is when data was retrieved, not a guarantee of when the upstream API updated. Missing or delayed credit means keep for now. Text/skin-only objectives and achievements absent from the public API cannot be automatically mapped. Wiki links help with manual review; pages are not automatically interpreted as disposal rules.

References: [achievement definitions](https://wiki.guildwars2.com/wiki/API:2/achievements), [account progress](https://wiki.guildwars2.com/wiki/API:2/account/achievements), and the official item API links in each rule.

## Item uses and overflow

Click an item to look up crafting-station recipes that use its ID as an ingredient, regardless of whether its type says Trophy, CraftingMaterial, or something else. Results show output names, ingredient quantities, crafting disciplines, required rating, and source/wiki links, with 20 recipes per page. This does not check recipe unlocks or your character's crafting level. Mystic Forge recipes, vendor exchanges, and other uses may be missing from the API; a zero-result search is not disposal advice.

The same panel shows this character's bag quantity, material-storage quantity and capacity, how much can be deposited, and how much would remain as overflow. Counts exclude the bank, other characters, and shared slots. Deposit, overflow, stacking, salvage, and consumption details stay in this panel rather than creating additional inventory categories. Storage data and crafting data fail independently and can be retried.

## Wiki Notes

Wiki Notes are checked automatically alongside the other usage checks. The server requests rendered pages from the official GW2 Wiki MediaWiki API by the item's official name, follows wiki redirects, and requires a unique matching item ID in the item infobox before using any notes. Ambiguous or missing pages are not treated as disposal evidence. No account key is sent to the wiki.

The item panel displays Notes as plain text with the page link, source revision, retrieval time, and contributor/license attribution. Only a single, complete, unqualified disposal statement (including “after acquisition”) can support automatic Sell / destroy. Other disposal wording, additional notes, or conditions require manual review. Wiki-based disposal additionally requires a successful zero-result recipe search, available collection checks, and no uncredited or repeatable mapped objective. Crafting matches always take priority. Missing wiki data does not create disposal approval; existing API-based advice remains available.

Wiki requests are limited to two at once. Successful checks are cached in memory for six hours; failures for one minute. Refresh retries expired checks. The app does not execute wiki HTML or interpret page text as instructions. Source: [GW2 Wiki copyrights](https://wiki.guildwars2.com/wiki/Guild_Wars_2_Wiki:Copyrights).

Notes text can distinguish optional utility from a disposal prerequisite. Wording that permits destruction except for access to collected pages before acquiring the completed journal/book is recognized for any item. The app displays the reading-access trade-off. This rule uses the note's complete wording, not an item-ID allowlist; additional requirements, negation, or conflicting notes return it to manual review. Item IDs are still verified to ensure the page describes the correct item. Recipe and collection checks still apply.

## Running checks

Run `python -m unittest discover -s tests -v` for mocked API and local HTTP tests. Live account access requires your own key.

Run `python tests/browser_smoke.py` on Windows with Microsoft Edge for a headless browser check using synthetic inventory fixtures (no account key). It checks loading, cleanup filters, item details, evidence labels, and invalidation after refresh.

### Find space

Use the Find space filter alongside the category and search filters to find items
in multiple bag slots, stacks that may combine, material-storage overflow, or
copies also held in your bank, shared inventory, or material storage. Counts are
unique item IDs, not the number of units or slots you can free. Click an item for
bag/slot locations and bank/shared quantities. Different bindings or stats can
share an item ID; duplicates alone do not imply stackability or safe disposal.
Other characters are not included yet. Failed sources remain unknown, not zero.
Account contents are fetched fresh and are not stored in the public-data caches.

Bank and shared inventory use the documented GW2 endpoints:
https://wiki.guildwars2.com/wiki/API:2/account/bank and
https://wiki.guildwars2.com/wiki/API:2/account/inventory.

### Review tools

- Select Equipment for rarity, equipment subtype, actual slot binding, and minimum/
  maximum required level filters. Reset clears these filters. Select Consumables
  for subtypes available in the loaded inventory, such as Food or Booster.
- Keep for me in item details saves item IDs in this browser only. It applies to
  every copy, moves the item into Keep, and suppresses disposal action suggestions.
  No API keys are stored. Remove the preference from the same button.
- Item cards show concise reasons, such as recipe counts or collection credit.
- Find matching copies in item details searches character bags, bank, shared slots,
  and material storage on demand. It matches item IDs, not stats or upgrades, and
  excludes equipped items and guild storage. Failed sources produce partial results
  and warnings rather than being treated as empty. Private results are not cached.

Category, search, and Find space filters combine. Keep for me items appear
under Keep rather than their original equipment/consumable/crafting category.

### Legendary projects: The Bifrost

Open Legendary projects to scan account holdings and expand the four final
components. Track The Bifrost saves a local preference and protects required item
types in inventory. Stop tracking restores the normal categories. Protection is
conservative: it includes surplus copies of a required type, and protects the full
recipe catalog until a complete account scan can narrow it down.

The reviewed recipe tree is in bifrost.json, with item IDs, wiki links/revisions
and the review date. Crafting-station recipes were checked against API recipes
4315 and 3165. Mystic Forge requirements are sourced from the linked wiki pages.
Owned gifts replace their ingredient requirements. Shared ingredients are allocated
once across the tree; the remaining-materials table combines repeated requirements.
The progress bar measures final components owned, not time, gold or overall effort.

The first version tracks one final Bifrost crafting path. It counts bags, bank,
shared slots, material storage and Legendary Armory. It does not infer equipped
items, unopened starter kits, precursor collection progress,
recipe unlocks, crafting levels or reward-track/map-completion percentages. Those
steps have source links and guidance. Clover gambling is not expanded into a
fixed-cost recipe. Failed sources produce explicit partial results. Refresh after
crafting in game; GW2 API data can lag. Account holdings are never saved to disk.

#### Acquisition tips and vendor budgets

Expand any missing material, or “How to obtain this item” in an inventory item,
to load its acquisition and notes sections from the GW2 Wiki. This uses a generic
parser, not an item-specific list of methods, vendors or prices. Wiki item IDs must
match the selected API item. Unmatched pages and failed requests offer a retry.
Public results are cached in memory for six hours, with revision and attribution.
Text and tables are imported safely without running wiki HTML. Unrecognized costs
remain readable but receive no affordability estimate. The Bifrost recipe tree
itself remains the reviewed definition in bifrost.json.

Enable **wallet** on your API key for currency comparisons. Missing permissions
show unknown currency balances; inventory progress still works. Trade tables show
per-purchase costs, the cost of the entire missing quantity, spendable holdings and
shortfalls. Direct Bifrost requirements are reserved first so that their ectoplasm
and obsidian cannot simultaneously fund clover purchases. Each offer is evaluated
independently, and full-shortfall costs can span multiple weekly/seasonal resets.
The resource-supported quantity is capped by the listed purchase limit, but past
purchases, vendor access, unlocks and seasonal availability are not verified. No
trade is executed and no vendor currency is actually reserved or spent.
