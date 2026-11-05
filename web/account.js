async function submitAccount(event, route, errorId) {
  event.preventDefault();
  const form = event.currentTarget;
  const error = document.getElementById(errorId);
  error.textContent = '';
  const button = form.querySelector('button'); button.disabled = true;
  try {
    const body = Object.fromEntries(new FormData(form));
    const response = await fetch(route, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await response.json();
    if (!response.ok) throw Error(data.error || 'Please try again.');
    const next = new URLSearchParams(location.search).get('next');
    location.href = route === '/api/signup' ? '/' : (next?.startsWith('/') && !next.startsWith('//') ? next : '/');
  } catch (failure) { error.textContent = failure.message; button.disabled = false; }
}
document.getElementById('signup-form').addEventListener('submit', (event) => submitAccount(event, '/api/signup', 'signup-error'));
document.getElementById('login-form').addEventListener('submit', (event) => submitAccount(event, '/api/login', 'login-error'));
