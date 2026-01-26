import type { Store, FileItem, ChatResponse, StartChatResponse } from '../types';

const API_BASE = '/api';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || response.statusText);
  }
  return response.json();
}

export async function fetchStores(): Promise<Store[]> {
  const response = await fetch(`${API_BASE}/stores`);
  return handleResponse<Store[]>(response);
}

export async function createStore(name: string): Promise<Store> {
  const response = await fetch(`${API_BASE}/stores`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return handleResponse<Store>(response);
}

export async function deleteStore(name: string): Promise<void> {
  const response = await fetch(`${API_BASE}/stores/${name}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function fetchFiles(storeName: string): Promise<FileItem[]> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/files`);
  return handleResponse<FileItem[]>(response);
}

export async function uploadFile(storeName: string, file: File): Promise<void> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE}/stores/${storeName}/files`, {
    method: 'POST',
    body: formData,
  });
  await handleResponse<void>(response);
}

export async function deleteFile(fileName: string): Promise<void> {
  const response = await fetch(`${API_BASE}/files/${fileName}`, {
    method: 'DELETE',
  });
  await handleResponse<void>(response);
}

export async function startChat(storeName: string): Promise<StartChatResponse> {
  const response = await fetch(`${API_BASE}/chat/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ store_name: storeName }),
  });
  return handleResponse<StartChatResponse>(response);
}

export async function sendMessage(text: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text }),
  });
  return handleResponse<ChatResponse>(response);
}

export async function getPrompt(storeName: string): Promise<{ prompt: string }> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/prompt`);
  return handleResponse<{ prompt: string }>(response);
}

export async function savePrompt(storeName: string, prompt: string): Promise<void> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
  await handleResponse<void>(response);
}

export async function getApiKey(storeName: string): Promise<{ api_key: string }> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/api-key`);
  return handleResponse<{ api_key: string }>(response);
}

export async function saveApiKey(storeName: string, apiKey: string): Promise<void> {
  const response = await fetch(`${API_BASE}/stores/${storeName}/api-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  });
  await handleResponse<void>(response);
}
