export type HciotLanguage = 'zh' | 'en';

export interface HciotTopic {
  id: string;
  icon: string;
  accent: string;
  labels: Record<HciotLanguage, string>;
  summaries: Record<HciotLanguage, string>;
  questions: Record<HciotLanguage, string[]>;
}

const HCIOT_TOPIC_QUESTIONS_ZH = {
  prp: [
    'PRP 治療會痛嗎？',
    'PRP 注射後多久會見效？',
    'PRP 有副作用嗎？',
    'PRP 需要禁食嗎？',
    '施打 PRP 前可以吃止痛藥嗎？',
  ],
  'h-pylori': [
    '感染幽門螺旋桿菌的症狀有哪些？',
    '感染幽門螺旋桿菌一定要治療嗎？',
    '幽門螺旋桿菌如何治療？',
    '治療期間可以喝酒嗎？',
    '治療幽門螺旋桿菌會有副作用嗎？',
  ],
  'trigger-finger': [
    '板機指為什麼會發生？',
    '那些人較會有板機指？',
    '板機指會自己好嗎？',
    '板機指常見的治療方式有哪些？',
    '板機指痛在哪裡？',
  ],
  'herniated-disc': [
    '椎間盤突出常見的部位?',
    '椎間盤突出和坐骨神經痛有什麼關係？',
    '椎間盤突出會自己好嗎？',
    '如何診斷椎間盤突出？',
    '椎間盤突出一定要開刀嗎？',
  ],
  'peptic-ulcer': [
    '如何診斷消化性潰瘍？',
    '消化性潰瘍需要治療嗎?',
    '消化性潰瘍要怎麼治療?',
    '胃潰瘍和十二指腸潰瘍有什麼不同？',
    '黑便代表什麼？',
  ],
  gout: [
    '痛風發作多久會好？',
    '為什麼會痛風？',
    '如何檢查是否痛風？',
    '尿酸高就一定會痛風發作嗎？',
    '痛風發作時應該冰敷還是熱敷？',
  ],
  'cast-care': [
    '石膏弄濕怎麼辦？',
    '石膏變得很緊怎麼辦？',
    '下肢石膏固定期間能走路嗎？',
    '石膏內有異味怎麼辦？',
    '石膏期間可以洗澡嗎？',
  ],
  diabetes: [
    '糖尿病有哪幾種類型？',
    '糖尿病如何診斷？',
    '糖化血色素（HbA1c）是什麼？',
    '糖尿病會遺傳嗎？',
    '糖尿病患者一定要吃藥嗎？',
  ],
  'fatty-liver': [
    '什麼是脂肪肝？',
    '脂肪肝有哪幾種類型？',
    '脂肪肝會有症狀嗎？',
    '脂肪肝怎麼檢查？',
    '脂肪肝嚴重嗎？',
  ],
  meniscus: [
    '半月板損傷是怎麼發生的？',
    '需要做 MRI 才能確診嗎？',
    '半月板損傷可以走路嗎？',
    '半月板損傷會卡住膝蓋嗎？',
    '半月板損傷需要開刀嗎？',
  ],
  'ankle-sprain': [
    '什麼是足踝扭傷？',
    '足踝扭傷程度怎麼分類?',
    '足踝扭傷會變慢性不穩嗎？',
    '足踝扭傷最常傷到哪個部位？',
    '扭傷後立刻腫起來是正常的嗎？',
  ],
  osteoarthritis: [
    '什麼是退化性膝關節炎？',
    '退化性關節炎的原因？',
    '早上起床膝蓋僵硬是退化嗎？',
    'X 光可以確診退化性膝關節炎嗎？',
    '為什麼會膝蓋退化？',
  ],
  osteoporosis: [
    '哪些人容易得骨質疏鬆？',
    '骨質疏鬆最容易發生哪些骨折？',
    '如何診斷骨質疏鬆？',
    'T-score 是什麼？',
    '骨質疏鬆會痛嗎？',
  ],
  hypertension: [
    '高血壓會有症狀嗎？',
    '高血壓如何診斷？',
    '高血壓的原因？',
    '高血壓的危險因素有哪些？',
    '高血壓可以治癒嗎？',
  ],
} as const;

type HciotTopicQuestionKey = keyof typeof HCIOT_TOPIC_QUESTIONS_ZH;

function getTopicQuestions(key: HciotTopicQuestionKey): Record<HciotLanguage, string[]> {
  const questions = [...HCIOT_TOPIC_QUESTIONS_ZH[key]];
  return {
    zh: [...questions],
    en: [...questions],
  };
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
    questions: getTopicQuestions('prp'),
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
    questions: getTopicQuestions('h-pylori'),
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
    questions: getTopicQuestions('trigger-finger'),
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
    questions: getTopicQuestions('herniated-disc'),
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
    questions: getTopicQuestions('peptic-ulcer'),
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
    questions: getTopicQuestions('gout'),
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
    questions: getTopicQuestions('cast-care'),
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
    questions: getTopicQuestions('diabetes'),
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
    questions: getTopicQuestions('fatty-liver'),
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
    questions: getTopicQuestions('meniscus'),
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
    questions: getTopicQuestions('ankle-sprain'),
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
    questions: getTopicQuestions('osteoarthritis'),
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
    questions: getTopicQuestions('osteoporosis'),
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
    questions: getTopicQuestions('hypertension'),
  },
];

export function normalizeHciotLanguage(language?: string): HciotLanguage {
  return typeof language === 'string' && language.trim().toLowerCase().startsWith('en')
    ? 'en'
    : 'zh';
}
