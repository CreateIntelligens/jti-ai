export type HciotLanguage = 'zh' | 'en';

export interface HciotTopic {
  id: string;
  icon: string;
  accent: string;
  labels: Record<HciotLanguage, string>;
  summaries: Record<HciotLanguage, string>;
  prompts: Record<HciotLanguage, string>;
}

export const HCIOT_DEFAULT_STORE_NAME = (
  (import.meta.env.VITE_HCIOT_STORE_NAME as string | undefined)?.trim() || 'hciot'
);

export const HCIOT_TOPICS: HciotTopic[] = [
  {
    id: 'prp',
    icon: '🩸',
    accent: '#8f5cf7',
    labels: { zh: 'PRP', en: 'PRP Therapy' },
    summaries: {
      zh: '了解適應症、術後照護與常見疑問。',
      en: 'Learn indications, post-procedure care, and common questions.',
    },
    prompts: {
      zh: '請用病人容易理解的方式說明 PRP 的用途、治療後照護重點與何時需要回診。',
      en: 'Please explain PRP therapy in patient-friendly English, including its purpose, aftercare, and when follow-up is needed.',
    },
  },
  {
    id: 'h-pylori',
    icon: '🦠',
    accent: '#13a891',
    labels: { zh: '幽門螺旋桿菌', en: 'Helicobacter pylori' },
    summaries: {
      zh: '整理感染原因、治療方式與飲食注意事項。',
      en: 'Summarize causes, treatment approach, and dietary cautions.',
    },
    prompts: {
      zh: '請整理幽門螺旋桿菌的感染原因、治療方式、用藥提醒與日常飲食注意事項。',
      en: 'Please summarize H. pylori causes, treatment, medication reminders, and daily diet advice in English.',
    },
  },
  {
    id: 'trigger-finger',
    icon: '✋',
    accent: '#ff7f50',
    labels: { zh: '板機指', en: 'Trigger Finger' },
    summaries: {
      zh: '說明症狀、保守治療與就醫時機。',
      en: 'Explain symptoms, conservative care, and when to seek treatment.',
    },
    prompts: {
      zh: '請說明板機指的症狀、平常可以怎麼照護，以及什麼情況需要進一步治療。',
      en: 'Please explain trigger finger symptoms, home care, and when further treatment is needed.',
    },
  },
  {
    id: 'herniated-disc',
    icon: '🦴',
    accent: '#2f6fed',
    labels: { zh: '椎間盤突出', en: 'Herniated Disc' },
    summaries: {
      zh: '整理常見症狀、姿勢調整與警訊。',
      en: 'Review common symptoms, posture advice, and warning signs.',
    },
    prompts: {
      zh: '請用清楚條列方式說明椎間盤突出的常見症狀、日常姿勢建議與需要立即就醫的警訊。',
      en: 'Please explain herniated disc symptoms, posture advice, and urgent warning signs in clear bullet points.',
    },
  },
  {
    id: 'peptic-ulcer',
    icon: '🥣',
    accent: '#d98b2b',
    labels: { zh: '消化性潰瘍', en: 'Peptic Ulcer' },
    summaries: {
      zh: '涵蓋症狀、用藥與飲食調整。',
      en: 'Cover symptoms, medication reminders, and diet changes.',
    },
    prompts: {
      zh: '請說明消化性潰瘍的常見症狀、用藥重點、飲食建議，以及什麼情況要回診。',
      en: 'Please explain peptic ulcer symptoms, medication reminders, diet advice, and when follow-up is necessary.',
    },
  },
  {
    id: 'gout',
    icon: '🦶',
    accent: '#d95f75',
    labels: { zh: '痛風', en: 'Gout' },
    summaries: {
      zh: '重點整理發作期照護與飲食控制。',
      en: 'Focus on flare care and diet control.',
    },
    prompts: {
      zh: '請用病人可以照做的方式說明痛風急性發作時怎麼處理、平常飲食要注意什麼。',
      en: 'Please explain what patients should do during a gout flare and what diet habits to follow afterward.',
    },
  },
  {
    id: 'cast-care',
    icon: '🩹',
    accent: '#4da3a8',
    labels: { zh: '石膏固定後照護', en: 'Cast Care' },
    summaries: {
      zh: '說明固定後照護、禁忌與危險徵象。',
      en: 'Explain aftercare, restrictions, and red-flag symptoms.',
    },
    prompts: {
      zh: '請說明石膏固定後的照護重點、不能做的事，以及哪些情況代表需要立即回診。',
      en: 'Please explain cast care, things patients must avoid, and symptoms that require urgent reassessment.',
    },
  },
  {
    id: 'diabetes',
    icon: '🩺',
    accent: '#1a8f5a',
    labels: { zh: '糖尿病', en: 'Diabetes' },
    summaries: {
      zh: '整理飲食、監測與生活型態建議。',
      en: 'Summarize diet, monitoring, and lifestyle advice.',
    },
    prompts: {
      zh: '請說明糖尿病病人平常在飲食、血糖監測、運動與用藥方面的重點。',
      en: 'Please explain the key daily care points for diabetes, including diet, glucose monitoring, exercise, and medication.',
    },
  },
  {
    id: 'fatty-liver',
    icon: '🫀',
    accent: '#b78232',
    labels: { zh: '脂肪肝', en: 'Fatty Liver' },
    summaries: {
      zh: '聚焦體重、飲食與追蹤建議。',
      en: 'Focus on weight, diet, and follow-up recommendations.',
    },
    prompts: {
      zh: '請說明脂肪肝的日常照護，包括飲食、體重控制、運動與追蹤檢查的重點。',
      en: 'Please explain fatty liver self-care, including diet, weight control, exercise, and follow-up testing.',
    },
  },
  {
    id: 'meniscus',
    icon: '🦵',
    accent: '#5b6ceb',
    labels: { zh: '膝蓋半月板損傷', en: 'Meniscus Injury' },
    summaries: {
      zh: '整理休息、復健與活動限制。',
      en: 'Summarize rest, rehab, and activity restrictions.',
    },
    prompts: {
      zh: '請說明膝蓋半月板損傷時平常如何休息與復健，哪些動作需要避免。',
      en: 'Please explain rest, rehabilitation, and movement restrictions for a meniscus injury.',
    },
  },
  {
    id: 'ankle-sprain',
    icon: '🏃',
    accent: '#0e9bb3',
    labels: { zh: '足踝扭傷', en: 'Ankle Sprain' },
    summaries: {
      zh: '重點說明急性期處置與恢復期活動。',
      en: 'Highlight acute care and return-to-activity guidance.',
    },
    prompts: {
      zh: '請說明足踝扭傷後前幾天怎麼處理、何時可以慢慢恢復活動，以及哪些警訊不能拖。',
      en: 'Please explain ankle sprain care in the first few days, when activity can resume, and which warning signs need prompt care.',
    },
  },
  {
    id: 'osteoarthritis',
    icon: '🪑',
    accent: '#7367c9',
    labels: { zh: '退化性關節炎', en: 'Osteoarthritis' },
    summaries: {
      zh: '涵蓋疼痛管理、運動與保養建議。',
      en: 'Cover pain control, exercise, and joint protection.',
    },
    prompts: {
      zh: '請整理退化性關節炎的疼痛管理方式、適合的活動建議，以及平常保養重點。',
      en: 'Please summarize pain management, suitable activity, and daily joint-care advice for osteoarthritis.',
    },
  },
  {
    id: 'osteoporosis',
    icon: '🧍',
    accent: '#cc6f91',
    labels: { zh: '骨質疏鬆', en: 'Osteoporosis' },
    summaries: {
      zh: '整理補充營養、運動與跌倒預防。',
      en: 'Summarize nutrition, exercise, and fall prevention.',
    },
    prompts: {
      zh: '請說明骨質疏鬆病人平常應注意的營養補充、運動方式與跌倒預防重點。',
      en: 'Please explain nutrition, exercise, and fall-prevention advice for patients with osteoporosis.',
    },
  },
  {
    id: 'hypertension',
    icon: '❤️',
    accent: '#d33f49',
    labels: { zh: '高血壓', en: 'Hypertension' },
    summaries: {
      zh: '快速掌握量血壓、用藥與生活習慣。',
      en: 'Quickly review blood pressure checks, medication, and habits.',
    },
    prompts: {
      zh: '請用病人容易理解的方式說明高血壓的日常照護，包括量血壓、用藥、飲食與生活習慣。',
      en: 'Please explain daily hypertension care in simple English, including blood pressure checks, medication, diet, and lifestyle habits.',
    },
  },
];

export function normalizeHciotLanguage(language?: string): HciotLanguage {
  return typeof language === 'string' && language.trim().toLowerCase().startsWith('en')
    ? 'en'
    : 'zh';
}
