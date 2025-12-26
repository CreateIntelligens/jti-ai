import { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import StoreManagementModal from './components/StoreManagementModal';
import PromptManagementModal from './components/PromptManagementModal';
import APIKeyModal from './components/APIKeyModal';
import * as api from './services/api';
import './styles/App.css';

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [storeModalOpen, setStoreModalOpen] = useState(false);
  const [promptModalOpen, setPromptModalOpen] = useState(false);
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false);
  const [status, setStatus] = useState('');
  const [stores, setStores] = useState([]);
  const [currentStore, setCurrentStore] = useState(null);
  const [files, setFiles] = useState([]);
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const toggleSidebar = () => setSidebarOpen(!sidebarOpen);

  const showStatus = (msg) => {
    setStatus(msg);
    setTimeout(() => setStatus(''), 3000);
  };

  const refreshStores = useCallback(async () => {
    try {
      const data = await api.fetchStores();
      setStores(data);
      return data;
    } catch (e) {
      showStatus('載入知識庫列表失敗');
      return [];
    }
  }, []);

  const refreshFiles = useCallback(async () => {
    if (!currentStore) return;
    try {
      const data = await api.fetchFiles(currentStore);
      data.sort((a, b) => (a.display_name || a.name).localeCompare(b.display_name || b.name));
      setFiles(data);
    } catch (e) {
      console.error('Failed to fetch files:', e);
    }
  }, [currentStore]);

  useEffect(() => {
    const init = async () => {
      const storeList = await refreshStores();
      const lastStore = localStorage.getItem('lastStore');
      if (lastStore && storeList.find(s => s.name === lastStore)) {
        handleStoreChange(lastStore);
      }
    };
    init();
  }, []);

  useEffect(() => {
    if (currentStore) {
      refreshFiles();
    }
  }, [currentStore, refreshFiles]);

  const handleStoreChange = async (storeName) => {
    setCurrentStore(storeName);
    setMessages([]);
    if (storeName) {
      localStorage.setItem('lastStore', storeName);
      try {
        const result = await api.startChat(storeName);
        if (result.prompt_applied) {
          showStatus('✅ 已套用自訂 Prompt');
        }
      } catch (e) {
        showStatus('連線失敗: ' + e.message);
        setMessages([{ role: 'model', text: '連線失敗: ' + e.message, error: true }]);
      }
    }
  };

  // 重新啟動對話（用於套用新的 Prompt）
  const handleRestartChat = async () => {
    if (!currentStore) return;
    setMessages([]);
    try {
      const result = await api.startChat(currentStore);
      if (result.prompt_applied) {
        showStatus('✅ 已套用新的 Prompt');
      }
    } catch (e) {
      showStatus('重新啟動失敗: ' + e.message);
    }
  };

  const handleCreateStore = async (name) => {
    try {
      const newStore = await api.createStore(name);
      await refreshStores();
      handleStoreChange(newStore.name);
    } catch (e) {
      alert('建立失敗: ' + e.message);
    }
  };

  const handleDeleteStore = async (storeName) => {
    if (!storeName) return;
    try {
      await api.deleteStore(storeName);
      if (currentStore === storeName) {
        setCurrentStore(null);
        setFiles([]);
        setMessages([]);
      }
      await refreshStores();
      showStatus('知識庫已刪除');
    } catch (e) {
      alert('刪除失敗: ' + e.message);
    }
  };

  const handleUploadFile = async (file) => {
    if (!currentStore) {
      alert('請先選擇知識庫');
      return;
    }
    try {
      await api.uploadFile(currentStore, file);
      await refreshFiles();
      showStatus('文件上傳成功');
    } catch (e) {
      alert('上傳失敗: ' + e.message);
    }
  };

  const handleDeleteFile = async (fileName) => {
    if (!confirm('確定刪除此文件？')) return;
    try {
      await api.deleteFile(fileName);
      await refreshFiles();
      showStatus('文件已刪除');
    } catch (e) {
      alert('刪除失敗: ' + e.message);
    }
  };

  const handleSendMessage = async (text) => {
    setMessages(prev => [...prev, { role: 'user', text }]);
    setMessages(prev => [...prev, { role: 'model', loading: true }]);
    setLoading(true);

    try {
      const data = await api.sendMessage(text);
      setMessages(prev => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 1] = { role: 'model', text: data.answer };
        return newMessages;
      });
    } catch (e) {
      setMessages(prev => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 1] = { role: 'model', text: '錯誤: ' + e.message, error: true };
        return newMessages;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Header
        status={status}
        onToggleSidebar={toggleSidebar}
        sidebarOpen={sidebarOpen}
        onOpenStoreManagement={() => setStoreModalOpen(true)}
        onOpenAPIKeyManagement={() => setApiKeyModalOpen(true)}
      />
      <div className="app-container">
        <Sidebar
          isOpen={sidebarOpen}
          stores={stores}
          currentStore={currentStore}
          files={files}
          onStoreChange={handleStoreChange}
          onUploadFile={handleUploadFile}
          onDeleteFile={handleDeleteFile}
          onRefresh={refreshStores}
          onOpenPromptManagement={() => setPromptModalOpen(true)}
        />
        <ChatArea
          messages={messages}
          onSendMessage={handleSendMessage}
          disabled={!currentStore}
          loading={loading}
        />
      </div>
      <StoreManagementModal
        isOpen={storeModalOpen}
        onClose={() => setStoreModalOpen(false)}
        stores={stores}
        currentStore={currentStore}
        onCreateStore={handleCreateStore}
        onDeleteStore={handleDeleteStore}
        onRefresh={refreshStores}
      />
      <PromptManagementModal
        isOpen={promptModalOpen}
        onClose={() => setPromptModalOpen(false)}
        currentStore={currentStore}
        onRefresh={refreshStores}
        onRestartChat={handleRestartChat}
      />
      <APIKeyModal
        isOpen={apiKeyModalOpen}
        onClose={() => setApiKeyModalOpen(false)}
        stores={stores}
      />
    </>
  );
}
