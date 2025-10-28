// client/src/services/authApi.js
export async function registerApi(payload) {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  return await res.json();
}

export async function loginApi(payload) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (res.ok && data.token) {
    localStorage.setItem("token", data.token);
  }
  return data;
}
