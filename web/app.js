const $ = (selector) => document.querySelector(selector);
const state = { items: [], selected: [], avatar: null, imageModel: { enabled: false, model: 'Gemini', max_garments: 4 }, detail: null, detailIndex: 0 };

function money(value) { return '$' + Number(value || 0).toFixed(2); }
function el(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = String(text); return node; }
async function api(url, options) { const response = await fetch(url, options); const data = await response.json(); if (!response.ok) throw Error(data.error || 'Request failed'); return data; }
function selected(item) { return state.selected.some((row) => row.listing_id === item.listing_id); }
function addItem(item) { if (selected(item) || state.selected.length >= state.imageModel.max_garments) return; state.selected.push(item); renderSelection(); renderItems(); updateDetailButton(); }

function renderItems() {
  const grid = $('#items'); grid.replaceChildren();
  $('#item-count').textContent = state.items.length + (state.items.length === 1 ? ' item' : ' items');
  for (const item of state.items) {
    const card = el('article', 'item');
    const open = el('button', 'item-open'); open.type = 'button'; open.setAttribute('aria-label', 'View ' + item.item_name);
    const image = el('img'); image.src = item.image; image.alt = item.item_name; image.loading = 'lazy'; open.append(image); open.addEventListener('click', () => showDetail(item));
    const body = el('div', 'item-body');
    const meta = el('div', 'item-meta'); meta.append(el('span', '', item.category || 'GRAILED'), el('strong', '', money(item.price)));
    const title = el('button', 'item-title', item.item_name); title.type = 'button'; title.addEventListener('click', () => showDetail(item));
    const foot = el('div', 'item-foot'); foot.append(el('span', '', item.size ? 'Size ' + item.size : 'Grailed piece'));
    const tryOn = el('a', 'mini-button', 'Try On →'); tryOn.href = '/tryon.html?item=' + encodeURIComponent(item.listing_id); foot.append(tryOn);
    body.append(meta, title, foot); card.append(open, body); grid.append(card);
  }
}

function renderSelection() {
  $('#count').textContent = state.selected.length + ' / ' + state.imageModel.max_garments;
  const list = $('#selected'); list.replaceChildren();
  if (!state.selected.length) list.append(el('p', 'empty', 'Choose a piece from the rack to start.'));
  for (const item of state.selected) {
    const row = el('div', 'selected-item'); const image = el('img'); image.src = item.image; image.alt = '';
    const name = el('span', '', item.item_name); const remove = el('button', '', '×'); remove.type = 'button'; remove.setAttribute('aria-label', 'Remove ' + item.item_name);
    remove.addEventListener('click', () => { state.selected = state.selected.filter((piece) => piece.listing_id !== item.listing_id); renderSelection(); renderItems(); updateDetailButton(); });
    row.append(image, name, remove); list.append(row);
  }
  $('#render-btn').disabled = !state.imageModel.enabled || !state.avatar || !state.selected.length;
}

function updateDetailButton() {
  const item = state.detail; if (!item) return;
  $('#detail-add').disabled = selected(item) || state.selected.length >= state.imageModel.max_garments;
  $('#detail-add').textContent = selected(item) ? 'Added to outfit ✓' : 'Add to outfit +';
}
function showDetail(item) {
  state.detail = item; state.detailIndex = 0;
  $('#detail-category').textContent = item.category || 'GRAILED'; $('#detail-title').textContent = item.item_name;
  $('#detail-price').textContent = money(item.price); $('#detail-size').textContent = item.size ? 'Size ' + item.size : 'Size not listed';
  const sizes = $('#detail-sizes'); sizes.replaceChildren();
  if (item.sizes) for (const size of ['S', 'M', 'L']) { const button = el('button', 'size-chip', size); button.type = 'button'; button.disabled = !item.sizes[size]; button.title = button.disabled ? 'Sold out' : size + ' in stock'; button.addEventListener('click', () => { sizes.querySelectorAll('button').forEach((part) => part.classList.remove('selected')); button.classList.add('selected'); $('#detail-try').href = '/tryon.html?item=' + encodeURIComponent(item.listing_id) + '&size=' + size; }); sizes.append(button); }
  const firstSize = ['S', 'M', 'L'].find((size) => item.sizes?.[size]) || '';
  if (firstSize) sizes.querySelector('button:not(:disabled)')?.click();
  $('#detail-try').href = '/tryon.html?item=' + encodeURIComponent(item.listing_id) + (firstSize ? '&size=' + firstSize : '');
  $('#detail-try').hidden = Boolean(item.sizes) && !firstSize;
  const buy = $('#detail-buy'); buy.hidden = !item.store_url; if (item.store_url) buy.href = item.store_url;
  const source = $('#detail-source'); source.href = item.product_url || '#'; source.hidden = !item.product_url;
  renderGallery(); updateDetailButton(); $('#item-dialog').showModal();
}
function renderGallery() {
  const images = state.detail.images || [state.detail.image];
  const main = $('#detail-main'); main.src = images[state.detailIndex]; main.alt = state.detail.item_name + ', photo ' + (state.detailIndex + 1);
  $('#detail-counter').textContent = 'Photo ' + (state.detailIndex + 1) + ' of ' + images.length;
  const thumbs = $('#detail-thumbs'); thumbs.replaceChildren();
  images.forEach((url, index) => { const button = el('button', index === state.detailIndex ? 'active' : ''); button.type = 'button'; button.setAttribute('aria-label', 'Show photo ' + (index + 1)); const image = el('img'); image.src = url; image.alt = ''; button.append(image); button.addEventListener('click', () => { state.detailIndex = index; renderGallery(); }); thumbs.append(button); });
}
$('#dialog-close').addEventListener('click', () => $('#item-dialog').close());
$('#item-dialog').addEventListener('click', (event) => { if (event.target === $('#item-dialog')) $('#item-dialog').close(); });
$('#detail-add').addEventListener('click', () => { addItem(state.detail); $('#item-dialog').close(); });
$('#avatar-file').addEventListener('change', async (event) => {
  const file = event.target.files[0]; if (!file) return;
  if (file.size > 5 * 1024 * 1024) { $('#render-status').textContent = 'Model photo must be under 5 MB.'; return; }
  state.avatar = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
  $('#avatar').src = state.avatar; $('#avatar').hidden = false; $('#stage-placeholder').hidden = true; $('#render-result').hidden = true; $('#stage-state').textContent = 'YOUR MODEL';
  $('#render-status').textContent = 'Photo ready. Select clothes to render with Gemini.'; renderSelection(); event.target.value = '';
});
$('#render-btn').addEventListener('click', async () => {
  const button = $('#render-btn'); button.disabled = true; button.textContent = 'Generating image…'; $('#render-status').textContent = 'Gemini is building your outfit preview…';
  try { const data = await api('/api/render', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ avatar: state.avatar, garments: state.selected.map((item) => item.image) }) });
    $('#result-img').src = data.image; $('#render-result').hidden = false; $('#stage-state').textContent = 'GEMINI PREVIEW'; $('#render-status').textContent = 'Rendered in ' + (data.elapsed_ms / 1000).toFixed(1) + 's.';
  } catch (error) { $('#render-status').textContent = error.message; }
  finally { button.innerHTML = 'Generate outfit image <span>↗</span>'; renderSelection(); }
});
Promise.all([api('/api/catalog'), api('/api/config')]).then(([catalog, config]) => {
  state.items = catalog.items; state.imageModel = config.image_model;
  $('#catalog-status').textContent = state.items.length ? 'Select a piece to see its photos.' : 'No pieces are published yet. The seller can choose items in the Seller panel.';
  $('#render-status').textContent = state.imageModel.enabled ? 'Upload a model photo and select clothes to render.' : 'Gemini rendering needs GOOGLE_API_KEY on the server.';
  renderItems(); renderSelection();
}).catch((error) => { $('#catalog-status').textContent = 'Could not load the collection: ' + error.message; });
