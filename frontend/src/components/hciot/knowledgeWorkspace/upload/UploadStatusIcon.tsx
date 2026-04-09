import { CheckCircle2, Loader2, XCircle } from 'lucide-react';

import type { FileStatus } from './types';

interface UploadStatusIconProps {
  status: FileStatus;
  error?: string;
}

export default function UploadStatusIcon({ status, error }: UploadStatusIconProps) {
  if (status === 'uploading') {
    return <Loader2 size={16} style={{ color: '#3b82f6', animation: 'spin 1s linear infinite' }} />;
  }

  if (status === 'done') {
    return <CheckCircle2 size={16} style={{ color: '#22c55e' }} />;
  }

  if (status === 'error') {
    return (
      <span title={error}>
        <XCircle size={16} style={{ color: '#ef4444' }} />
      </span>
    );
  }

  return null;
}
