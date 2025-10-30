// client/src/services/authApi.js

const jsonRequest = async (url, options) => {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  let data;
  try {
    data = await response.json();
  } catch (e) {
    data = {};
  }

  if (!response.ok) {
    const message = data?.error || `Request failed with status ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = data;
    throw error;
  }

  return data;
};

export async function registerApi(payload) {
  return jsonRequest("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loginApi(payload) {
  const data = await jsonRequest("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  if (data.token) {
    localStorage.setItem("authToken", data.token);
  }
  if (data.email) {
    localStorage.setItem("authEmail", data.email);
  }

  return data;
}

export function logout() {
  localStorage.removeItem("authToken");
  localStorage.removeItem("authEmail");
  localStorage.removeItem("authUsername");
}
