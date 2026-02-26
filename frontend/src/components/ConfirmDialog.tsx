interface ConfirmDialogProps {
  isOpen: boolean;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
  confirmText?: string;
  cancelText?: string;
}

export default function ConfirmDialog({
  isOpen,
  message,
  onConfirm,
  onCancel,
  loading = false,
  confirmText = '確認刪除',
  cancelText = '取消',
}: ConfirmDialogProps) {
  if (!isOpen) return null;

  return (
    <div className="jti-confirm-overlay" onClick={onCancel}>
      <div className="jti-confirm-box" onClick={e => e.stopPropagation()}>
        <p className="jti-confirm-text">{message}</p>
        <div className="jti-confirm-actions">
          <button
            className="jti-btn small secondary"
            onClick={onCancel}
            disabled={loading}
          >
            {cancelText}
          </button>
          <button
            className="jti-btn small danger"
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? '處理中...' : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
