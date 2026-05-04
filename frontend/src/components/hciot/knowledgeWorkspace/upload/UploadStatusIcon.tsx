import { CheckCircle2, Loader2, XCircle } from 'lucide-react';

import type { FileStatus } from './types';

interface UploadStatusIconProps {
  status: FileStatus;
  error?: string;
}

export default function UploadStatusIcon({ status, error }: UploadStatusIconProps) {
  if (status === 'uploading') {
    return <Loader2 className="hciot-upload-icon-spin" size={16} />;
  }

  if (status === 'done') {
    return <CheckCircle2 className="hciot-upload-icon-success" size={16} />;
  }

  if (status === 'error') {
    return (
      <span title={error}>
        <XCircle className="hciot-upload-icon-error" size={16} />
      </span>
    );
  }

  return null;
}
