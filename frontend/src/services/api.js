const API_BASE = '';

export async function fetchStores() {
  const res = await fetch(`${API_BASE}/api/stores`);
  if (!res.ok) throw new Error('Failed to fetch stores');
  return res.json();
}

export async function createStore(displayName) {
  const res = await fetch(`${API_BASE}/api/stores`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName })
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteStore(storeName) {
  const res = await fetch(`${API_BASE}/api/stores/${encodeURIComponent(storeName)}`, {
    method: 'DELETE'
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchFiles(storeName) {
  const res = await fetch(`${API_BASE}/api/stores/${encodeURIComponent(storeName)}/files`);
  if (!res.ok) throw new Error('Failed to fetch files');
  return res.json();
}

export async function uploadFile(storeName, file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/api/stores/${encodeURIComponent(storeName)}/upload`, {
    method: 'POST',
    body: formData
  });

  if (!res.ok) {
    let errorMsg = await res.text();
    try {
      const json = JSON.parse(errorMsg);
      if (json.detail) errorMsg = json.detail;
    } catch(e) {}
    throw new Error(errorMsg);
  }
  return res.json();
}

export async function deleteFile(fileName) {
  const res = await fetch(`${API_BASE}/api/files/${encodeURIComponent(fileName)}`, {
    method: 'DELETE'
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function startChat(storeName) {
  const res = await fetch(`${API_BASE}/api/chat/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ store_name: storeName })
  });
  if (!res.ok) {
    let errorMsg = await res.text();
    try {
      const json = JSON.parse(errorMsg);
      if (json.detail) errorMsg = json.detail;
    } catch(e) {}
    throw new Error(errorMsg);
  }
  return res.json();
}

export async function sendMessage(message) {
  const res = await fetch(`${API_BASE}/api/chat/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  });

  if (!res.ok) {
    let errorMsg = await res.text();
    try {
      const json = JSON.parse(errorMsg);
      if (json.detail) errorMsg = json.detail;
    } catch(e) {}
    throw new Error(errorMsg);
  }
  return res.json();
}
