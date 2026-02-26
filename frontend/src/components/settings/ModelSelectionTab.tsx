interface ModelInfo {
  id: string;
  name: string;
  description: string;
}

const MODELS: ModelInfo[] = [
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', description: '輕量快速版本' },
  { id: 'gemini-2.5-flash-lite', name: 'Gemini 2.5 Flash Lite', description: '輕量快速版本' },
  { id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash (Preview)', description: '新一代快速模型' },
  { id: 'gemini-3-pro-preview', name: 'Gemini 3 Pro (Preview)', description: '新一代最強模型' },
];

interface ModelSelectionTabProps {
  selectedModel: string;
  onModelChange: (modelId: string) => void;
}

export default function ModelSelectionTab({ selectedModel, onModelChange }: ModelSelectionTabProps) {
  return (
    <div className="modal-content">
      <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--crystal-cyan)' }}>
        選擇 Gemini 模型
      </h3>
      <p style={{ color: '#8090b0', fontSize: '0.9rem', marginBottom: '1rem' }}>
        選擇用於處理查詢的 AI 模型。不同模型有不同的速度和能力。
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {MODELS.map(model => (
          <div
            key={model.id}
            onClick={() => onModelChange(model.id)}
            style={{
              padding: '1rem',
              border: selectedModel === model.id
                ? '2px solid var(--crystal-cyan)'
                : '1px solid rgba(128,144,176,0.3)',
              borderRadius: '8px',
              cursor: 'pointer',
              background: selectedModel === model.id
                ? 'rgba(64,224,208,0.1)'
                : 'rgba(0,0,0,0.2)',
              transition: 'all 0.2s ease'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 'bold', color: 'var(--text-primary)', marginBottom: '0.25rem' }}>
                  {model.name}
                  {selectedModel === model.id && (
                    <span style={{ marginLeft: '0.5rem', color: 'var(--crystal-cyan)' }}>✓ 使用中</span>
                  )}
                </div>
                <div style={{ fontSize: '0.85rem', color: '#8090b0' }}>{model.description}</div>
              </div>
              {selectedModel === model.id && (
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--crystal-cyan)' }} />
              )}
            </div>
          </div>
        ))}
      </div>
      <div style={{
        marginTop: '1.5rem',
        padding: '1rem',
        background: 'rgba(64,224,208,0.05)',
        border: '1px solid rgba(64,224,208,0.2)',
        borderRadius: '8px'
      }}>
        <p style={{ fontSize: '0.85rem', color: '#8090b0', margin: 0 }}>
          💡 <strong style={{ color: 'var(--crystal-cyan)' }}>提示：</strong> Flash 模型速度快且免費額度較高，Pro 模型適合需要更深入分析的場景。
        </p>
      </div>
    </div>
  );
}
