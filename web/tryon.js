const qs = (selector) => document.querySelector(selector);
const params = new URLSearchParams(location.search);
let currentItem = null;
let bodySize = ['S', 'M', 'L'].includes(params.get('size')) ? params.get('size') : 'M';
let selectedSize = ['S', 'M', 'L'].includes(params.get('size')) ? params.get('size') : null;
let timeoutId = null;
let attempt = 0;

function renderBodyOptions() {
  const root = qs('#body-options'); root.replaceChildren();
  for (const size of ['S', 'M', 'L']) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'size-chip' + (size === bodySize ? ' selected' : ''); button.textContent = size;
    button.setAttribute('aria-pressed', String(size === bodySize));
    button.addEventListener('click', async () => {
      bodySize = size; renderBodyOptions(); qs('#mannequin-stage').dataset.size = size;
      try { const response = await fetch('/api/me/mannequin', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ size }) }); if (response.ok) qs('#save-note').textContent = 'Saved to your account.'; } catch (_) {}
    }); root.append(button);
  }
}

function renderSizes() {
  const root = qs('#item-sizes'); root.replaceChildren();
  if (!currentItem.sizes) { qs('#stock-note').textContent = currentItem.size ? 'Listed size: ' + currentItem.size : 'Size availability was not supplied.'; return; }
  if (!selectedSize || !currentItem.sizes[selectedSize]) selectedSize = ['S', 'M', 'L'].find((size) => currentItem.sizes[size]) || null;
  for (const size of ['S', 'M', 'L']) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'size-chip' + (size === selectedSize ? ' selected' : ''); button.textContent = size; button.disabled = !currentItem.sizes[size]; button.title = button.disabled ? 'Sold out' : currentItem.sizes[size] + ' in stock';
    button.addEventListener('click', () => { selectedSize = size; renderSizes(); }); root.append(button);
  }
  qs('#stock-note').textContent = selectedSize ? 'Selected size: ' + selectedSize : 'All sizes are sold out.';
  qs('#buy-link').hidden = !currentItem.store_url || !selectedSize;
}

function preview() {
  const thisAttempt = ++attempt;
  const overlay = qs('#garment-overlay'); clearTimeout(timeoutId); overlay.hidden = true;
  qs('#retry-btn').hidden = true; qs('#tryon-status').textContent = 'Lining up the garment…';
  overlay.classList.toggle('bottom-garment', /pants|jeans|trouser|shorts|skirt/i.test(String(currentItem.category) + ' ' + currentItem.item_name));
  const load = new Image();
  timeoutId = setTimeout(() => { if (thisAttempt === attempt) { attempt++; fail('Preview took too long. You can retry or keep browsing.'); } }, 5000);
  load.onload = () => { if (thisAttempt !== attempt) return; clearTimeout(timeoutId); overlay.src = load.src; overlay.hidden = false; qs('#tryon-status').textContent = 'Preview ready. Actual fit may differ.'; };
  load.onerror = () => { if (thisAttempt !== attempt) return; clearTimeout(timeoutId); fail('Could not load the garment image.'); };
  load.src = currentItem.image;
}
function fail(message) { qs('#garment-overlay').hidden = true; qs('#tryon-status').textContent = message; qs('#retry-btn').hidden = false; }
qs('#retry-btn').addEventListener('click', preview);

fetch('/api/catalog').then((response) => response.json()).then(({ items }) => {
  currentItem = items.find((item) => item.listing_id === params.get('item'));
  if (!currentItem) { qs('#tryon-status').textContent = 'This piece is unavailable. Return to the shop to choose another.'; return; }
  qs('#tryon-item-image').src = currentItem.image; qs('#tryon-item-image').alt = currentItem.item_name;
  qs('#tryon-title').textContent = currentItem.item_name; qs('#tryon-price').textContent = '$' + Number(currentItem.price || 0).toFixed(2);
  qs('#tryon-category').textContent = currentItem.category || 'Clothing';
  qs('#buy-link').href = currentItem.store_url || '#'; qs('#buy-link').hidden = !currentItem.store_url;
  renderSizes(); preview();
}).catch((error) => { qs('#tryon-status').textContent = 'Could not load the piece: ' + error.message; });
fetch('/api/me').then((response) => response.json()).then(({ user }) => { if (user) { if (!params.has('size')) bodySize = user.mannequin; qs('#save-note').textContent = 'Your choice is saved to your account.'; renderBodyOptions(); qs('#mannequin-stage').dataset.size = bodySize; } }).catch(() => {});
renderBodyOptions(); qs('#mannequin-stage').dataset.size = bodySize;
