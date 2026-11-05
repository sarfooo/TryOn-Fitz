async function refreshNav() {
  try {
    const response = await fetch('/api/me');
    const { user } = await response.json();
    const account = document.getElementById('account-link');
    const logout = document.getElementById('logout-btn');
    const seller = document.getElementById('seller-link');
    if (account) { account.hidden = !!user; account.textContent = user ? user.email : 'Log in'; }
    if (logout) logout.hidden = !user;
    if (seller) seller.hidden = user?.role !== 'admin';
  } catch (_) { /* The page remains usable if account status is unavailable. */ }
}
document.getElementById('logout-btn')?.addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  location.href = '/account.html';
});
refreshNav();
