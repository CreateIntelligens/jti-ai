import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import zh from './locales/zh.json';
import en from './locales/en.json';

i18n
  .use(initReactI18next)
  .init({
    resources: {
      zh: { translation: zh },
      en: { translation: en },
    },
    lng: localStorage.getItem('language') || 'zh', // 從 localStorage 讀取或預設繁中
    fallbackLng: 'zh',
    interpolation: {
      escapeValue: false, // React 已經處理 XSS
    },
  });

export default i18n;
