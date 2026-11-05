const $ = (selector) => document.querySelector(selector);
const state = { items: [], selectedId: null, busy: false };
function el(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = String(text); return node; }
function status(message, error = false) { const node = $('#seller-status'); node.textContent = message; node.classList.toggle('error', error); }
function itemById() { return state.items.find((item) => item.listing_id === state.selectedId); }
async function api(url, options) {
  const response = await fetch(url, options);
  const type = response.headers.get('content-type') || '';
  if (!type.includes('application/json')) throw Error('The server is running older code. Stop it, restart /usr/bin/python3 /Users/michael/fitz-demo/server.py, then refresh this page.');
  const data = await response.json(); if (!response.ok) throw Error(data.error || 'Request failed'); return data;
}
async function refresh() {
  const data = await api('/api/admin/catalog'); state.items = data.items;
  if (!itemById()) state.selectedId = state.items[0]?.listing_id || null;
  render(); return data.items;
}
async function save(item, changes) {
  try {
    const data = await api('/api/admin/items/' + encodeURIComponent(item.listing_id), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes) });
    Object.assign(item, data.item); status('Saved “' + item.item_name + '”.'); render();
  } catch (error) { status('Could not save: ' + error.message, true); renderEditor(); }
}
async function importItems() {
  if (state.busy) return; state.busy = true; $('#import-btn').disabled = true;
  status('Importing real listings from Grailed. This may take a moment…');
  try { const result = await api('/api/admin/import', { method: 'POST' }); await refresh();
    status('Saved ' + result.imported + ' Grailed pieces. Choose which ones to publish.' + (result.errors.length ? ' Some searches failed: ' + result.errors.join('; ') : ''));
  } catch (error) { status('Import failed: ' + error.message, true); }
  finally { state.busy = false; $('#import-btn').disabled = false; }
}
function render() {
  const visible = state.items.filter((item) => item.visible).length;
  $('#seller-count').textContent = state.items.length + ' saved · ' + visible + ' live';
  renderList(); renderEditor();
}
function renderList() {
  const filter = $('#seller-filter').value.trim().toLowerCase(); const list = $('#seller-items'); list.replaceChildren();
  const items = state.items.filter((item) => (item.item_name + ' ' + item.listing_id).toLowerCase().includes(filter));
  if (!items.length) { list.append(el('p', 'inventory-empty', state.items.length ? 'No matching pieces.' : 'No pieces saved yet. Import from Grailed to start.')); return; }
  for (const item of items) {
    const row = el('div', 'inventory-row' + (item.listing_id === state.selectedId ? ' selected' : ''));
    const select = el('button', 'inventory-select'); select.type = 'button'; select.setAttribute('aria-label', 'Edit ' + item.item_name);
    const photo = el('img'); photo.src = item.image; photo.alt = '';
    const info = el('span', 'inventory-info'); info.append(el('strong', '', item.item_name), el('small', '', '$' + Number(item.price || 0).toFixed(2)));
    select.append(photo, info); select.addEventListener('click', () => { state.selectedId = item.listing_id; render(); });
    const publish = el('button', item.visible ? 'publish-pill is-live' : 'publish-pill', item.visible ? 'Live ✓' : 'Show in shop'); publish.type = 'button';
    publish.setAttribute('aria-label', item.visible ? 'Hide ' + item.item_name + ' from shop' : 'Show ' + item.item_name + ' in shop');
    publish.title = item.visible ? 'Click to hide from shoppers' : 'Click to publish for shoppers';
    publish.addEventListener('click', () => { state.selectedId = item.listing_id; save(item, { visible: !item.visible }); });
    row.append(select, publish); list.append(row);
  }
}
function sectionHeading(number, title, note) { const row = el('div', 'editor-section-head'); const left = el('div'); left.append(el('span', 'eyebrow', number), el('h4', '', title)); row.append(left); if (note) row.append(el('span', 'muted', note)); return row; }
function renderEditor() {
  const root = $('#seller-editor'); root.replaceChildren(); const item = itemById();
  if (!item) { const empty = el('div', 'editor-empty'); empty.append(el('span', 'eyebrow', 'SELECT A PIECE'), el('h3', '', 'Choose an item to edit.'), el('p', '', 'Your product details and gallery will appear here.')); root.append(empty); return; }
  const heading = el('div', 'editor-title'); const titleWrap = el('div'); titleWrap.append(el('span', 'eyebrow', (item.source || 'ITEM').toUpperCase() + ' / ' + item.listing_id), el('h3', '', item.item_name));
  const source = el('a', 'source-link', 'Original listing ↗'); source.href = item.product_url || '#'; source.target = '_blank'; source.rel = 'noopener noreferrer'; heading.append(titleWrap); if (item.product_url) heading.append(source); root.append(heading);
  const publish = el('label', 'publish-bar' + (item.visible ? ' is-live' : '')); const publishText = el('span'); publishText.append(el('strong', '', item.visible ? 'Live in shop' : 'Hidden from shop'), el('small', '', item.visible ? 'Shoppers can see this piece.' : 'Only you can see this piece.'));
  const check = el('input'); check.type = 'checkbox'; check.checked = Boolean(item.visible); check.setAttribute('aria-label', 'Publish item'); check.addEventListener('change', () => save(item, { visible: check.checked })); publish.append(publishText, check); root.append(publish);
  root.append(sectionHeading('01 / PRODUCT', 'Details', 'Saved when changed'));
  const fields = el('div', 'editor-fields'); const nameLabel = el('label', '', 'Display name'); const name = el('input'); name.value = item.item_name; name.maxLength = 160; name.addEventListener('change', () => save(item, { item_name: name.value })); nameLabel.append(name);
  const priceLabel = el('label', '', 'Your price ($)'); const price = el('input'); price.type = 'number'; price.min = '0'; price.max = '100000'; price.step = '0.01'; price.value = Number(item.price || 0).toFixed(2); price.addEventListener('change', () => save(item, { price: price.value })); priceLabel.append(price);
  fields.append(nameLabel, priceLabel); root.append(fields);
  const storeLabel = el('label', 'wide-field', 'Store product URL'); const store = el('input'); store.type = 'url'; store.placeholder = 'https://...'; store.value = item.store_url || ''; store.addEventListener('change', () => save(item, { store_url: store.value.trim() })); storeLabel.append(store); root.append(storeLabel);
  if (item.sizes) { const stock = el('div', 'stock-fields'); stock.append(el('strong', '', 'Stock by size'));
    for (const size of ['S', 'M', 'L']) { const label = el('label', '', size); const input = el('input'); input.type = 'number'; input.min = '0'; input.step = '1'; input.value = item.sizes[size]; input.addEventListener('change', () => save(item, { sizes: { ...item.sizes, [size]: Number(input.value) } })); label.append(input); stock.append(label); } root.append(stock); }
  const detailLine = el('p', 'editor-meta', (item.size ? 'Size ' + item.size + ' · ' : '') + (item.category || 'Grailed') + ' · Original Grailed price $' + Number(item.grailed_price || 0).toFixed(2)); root.append(detailLine);
  root.append(sectionHeading('02 / GALLERY', 'Photos', (item.images || []).length + ' of 12'));
  const main = el('div', 'editor-main-photo'); const mainImage = el('img'); mainImage.src = item.image; mainImage.alt = item.item_name + ' cover photo'; main.append(mainImage, el('span', '', 'COVER PHOTO')); root.append(main);
  const gallery = el('div', 'editor-gallery');
  (item.images || []).forEach((url, index) => {
    const tile = el('div', 'editor-photo'); const image = el('img'); image.src = url; image.alt = 'Item photo ' + (index + 1);
    const controls = el('div', 'editor-photo-controls'); const up = el('button', '', '←'); up.type = 'button'; up.title = 'Move earlier'; up.disabled = index === 0; up.addEventListener('click', () => { const images = [...item.images]; [images[index - 1], images[index]] = [images[index], images[index - 1]]; save(item, { images }); });
    const remove = el('button', '', '×'); remove.type = 'button'; remove.title = 'Remove photo'; remove.disabled = item.images.length === 1; remove.addEventListener('click', () => save(item, { images: item.images.filter((_, position) => position !== index) })); controls.append(up, remove); tile.append(image, controls); gallery.append(tile);
  }); root.append(gallery);
  const actions = el('div', 'gallery-actions');
  if (/^\d+$/.test(item.listing_id)) { const fetchPhotos = el('button', 'outline-action', 'Fetch Grailed photos ↗'); fetchPhotos.type = 'button'; fetchPhotos.addEventListener('click', async () => { fetchPhotos.disabled = true; status('Fetching more photos for “' + item.item_name + '”…');
      try { const data = await api('/api/admin/items/' + encodeURIComponent(item.listing_id) + '/fetch-photos', { method: 'POST' }); Object.assign(item, data.item); status('Saved ' + item.images.length + ' photos for “' + item.item_name + '”.'); render(); }
      catch (error) { status('Could not fetch photos: ' + error.message, true); fetchPhotos.disabled = false; }
    }); actions.append(fetchPhotos); }
  const upload = el('label', 'outline-action upload-action', 'Upload photo +'); const file = el('input'); file.type = 'file'; file.accept = 'image/png,image/jpeg,image/webp'; file.hidden = true;
  file.addEventListener('change', async () => { const picked = file.files[0]; if (!picked) return; if (picked.size > 5 * 1024 * 1024) return status('Photo must be under 5 MB.', true);
    try { const imageData = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(picked); });
      const data = await api('/api/admin/items/' + encodeURIComponent(item.listing_id) + '/upload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image: imageData }) }); Object.assign(item, data.item); status('Uploaded a photo for “' + item.item_name + '”.'); render();
    } catch (error) { status('Could not upload photo: ' + error.message, true); }
  }); upload.append(file); actions.append(upload); root.append(actions);
  const addForm = el('form', 'add-photo'); const urlInput = el('input'); urlInput.type = 'url'; urlInput.placeholder = 'Paste another HTTPS image URL'; urlInput.required = true; const add = el('button', 'small-button', 'Add URL'); add.type = 'submit'; addForm.append(urlInput, add);
  addForm.addEventListener('submit', (event) => { event.preventDefault(); if (item.images.length >= 12) return status('An item can have at most 12 photos.', true); save(item, { images: [...item.images, urlInput.value.trim()] }); }); root.append(addForm);
}
$('#seller-filter').addEventListener('input', renderList);
$('#import-btn').addEventListener('click', importItems);
$('#create-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button[type="submit"]'); const statusNode = $('#create-status'); button.disabled = true; statusNode.textContent = 'Saving product…';
  try { const values = new FormData(form); const picture = values.get('picture'); if (!picture || !picture.size) throw Error('A product picture is required'); if (picture.size > 5 * 1024 * 1024) throw Error('Picture must be under 5 MB');
    const image = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(picture); });
    const payload = { item_name: values.get('item_name'), price: values.get('price'), image, category: values.get('category'), store_url: values.get('store_url'), sizes: { S: Number(values.get('S')), M: Number(values.get('M')), L: Number(values.get('L')) }, visible: values.has('visible') };
    const data = await api('/api/admin/items', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    form.reset(); state.selectedId = data.item.listing_id; await refresh(); statusNode.textContent = 'Saved “' + data.item.item_name + '”.' + (data.item.visible ? ' It is live in the shop.' : ' Publish it when ready.');
  } catch (error) { statusNode.textContent = error.message; } finally { button.disabled = false; }
});
refresh().then((items) => { if (!items.length) importItems(); else status(items.some((item) => item.visible) ? 'Use the buttons beside each piece to show or hide it in the shop.' : 'All saved pieces are hidden. Click “Show in shop” beside the items you want customers to see.'); }).catch((error) => status(error.message, true));
