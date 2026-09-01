export function formatUser(data) {
  return { ...data, label: `User #${data.id}` };
}

export async function createUser(name) {
  const res = await fetch('/api/users', { method: 'POST' });
  return res.json();
}
