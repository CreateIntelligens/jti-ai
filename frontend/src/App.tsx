import { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ChatArea from './components/ChatArea';
import StoreManagementModal from './components/StoreManagementModal';
import PromptManagementModal from './components/PromptManagementModal';
import UserApiKeyModal from './components/UserApiKeyModal';
import JtiTest from './pages/JtiTest';
import * as api from './services/api';
import type { Store, FileItem, Message } from './types';
import './styles/App.css';

export default function App() {
  // 簡單的路由判斷：如果路徑是 /jti，顯示 JTI 測試頁面
  const isJtiPage = window.location.pathname === '/jti';

  if (isJtiPage) {
    return <JtiTest />;
  }
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [storeModalOpen, setStoreModalOpen] = useState(false);
  const [promptModalOpen, setPromptModalOpen] = useState(false);
  const [userApiKeyModalOpen, setUserApiKeyModalOpen] = useState(false);
  const [status, setStatus] = useState('');
  const [stores, setStores] = useState<Store[]>([]);
  const [currentStore, setCurrentStore] = useState<string | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = localStorage.getItem('theme');
    return (saved === 'light' || saved === 'dark') ? saved : 'dark';
  });

  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  const toggleSidebar = () => setSidebarOpen(!sidebarOpen);

  const showStatus = (msg: string) => {
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
      console.error(e);
      return [];
    }
  }, []);

  const refreshFiles = useCallback(async () => {
    if (!currentStore) return;
    setFilesLoading(true);
    try {
      const data = await api.fetchFiles(currentStore);
      data.sort((a, b) =>
        (a.display_name || a.name).localeCompare(b.display_name || b.name)
      );
      setFiles(data);
    } catch (e) {
      console.error('Failed to fetch files:', e);
    } finally {
      setFilesLoading(false);
    }
  }, [currentStore]);

  useEffect(() => {
    const init = async () => {
      const storeList = await refreshStores();
      const lastStore = localStorage.getItem('lastStore');
      if (lastStore && storeList.find(s => s.name === lastStore)) {
        handleStoreChange(lastStore);
      } else if (storeList.length > 0) {
        handleStoreChange(storeList[0].name);
      }
    };
    init();
  }, [refreshStores]);

  useEffect(() => {
    if (currentStore) {
      refreshFiles();
    }
  }, [currentStore, refreshFiles]);

  const handleStoreChange = async (storeName: string) => {
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
        const errorMsg = e instanceof Error ? e.message : String(e);
        showStatus('連線失敗: ' + errorMsg);
        setMessages([{
          role: 'model',
          text: '連線失敗: ' + errorMsg,
          error: true
        }]);
      }
    }
  };

  const handleRestartChat = async () => {
    if (!currentStore) return;
    setMessages([]);
    try {
      const result = await api.startChat(currentStore);
      if (result.prompt_applied) {
        showStatus('✅ 已套用新的 Prompt');
      }
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      showStatus('重新啟動失敗: ' + errorMsg);
    }
  };

  const handleCreateStore = async (name: string) => {
    try {
      const newStore = await api.createStore(name);
      await refreshStores();
      handleStoreChange(newStore.name);
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('建立失敗: ' + errorMsg);
    }
  };

  const handleDeleteStore = async (storeName: string) => {
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
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + errorMsg);
    }
  };

  const handleUploadFile = async (file: File) => {
    if (!currentStore) {
      alert('請先選擇知識庫');
      return;
    }
    try {
      await api.uploadFile(currentStore, file);
      await refreshFiles();
      showStatus('文件上傳成功');
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('上傳失敗: ' + errorMsg);
    }
  };

  const handleDeleteFile = async (fileName: string) => {
    if (!confirm('確定刪除此文件？')) return;
    try {
      await api.deleteFile(fileName);
      await refreshFiles();
      showStatus('文件已刪除');
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      alert('刪除失敗: ' + errorMsg);
    }
  };

  const handleSendMessage = async (text: string) => {
    // 一次性更新訊息，減少重新渲染次數
    setMessages(prev => [
      ...prev,
      { role: 'user', text },
      { role: 'model', loading: true }
    ]);
    setLoading(true);

    try {
      const data = await api.sendMessage(text);
      setMessages(prev => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 1] = {
          role: 'model',
          text: data.answer
        };
        return newMessages;
      });
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      setMessages(prev => {
        const newMessages = [...prev];
        newMessages[newMessages.length - 1] = {
          role: 'model',
          text: '錯誤: ' + errorMsg,
          error: true
        };
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
        onOpenUserApiKeySettings={() => setUserApiKeyModalOpen(true)}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
      <div className="app-container">
        <Sidebar
          isOpen={sidebarOpen}
          stores={stores}
          currentStore={currentStore}
          files={files}
          filesLoading={filesLoading}
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
        stores={stores}
      />
      <UserApiKeyModal
        isOpen={userApiKeyModalOpen}
        onClose={() => setUserApiKeyModalOpen(false)}
        onApiKeySaved={() => {
          showStatus('✅ API Key 已儲存');
          refreshStores();
          refreshFiles();
        }}
      />
    </>
  );
}
