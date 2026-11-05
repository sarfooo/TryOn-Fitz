fetch('/api/me').then((response) => response.json()).then(({ user }) => {
  document.getElementById('wardrobe-state').innerHTML = user
    ? '<h2>Saved looks are coming in Sprint 2.</h2><p>You can browse the catalog and try pieces on a mannequin now.</p><a class="primary-button action-link" href="/">Browse clothes →</a>'
    : '<h2>Log in to view My Wardrobe.</h2><p>Your saved looks will appear here when that feature launches.</p><a class="primary-button action-link" href="/account.html?next=/wardrobe.html">Log in →</a>';
}).catch(() => { document.getElementById('wardrobe-state').textContent = 'Could not check your account. Please refresh.'; });
