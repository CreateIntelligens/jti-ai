import { X } from 'lucide-react';
import { useEscapeKey } from '../../../hooks/useEscapeKey';
import { useOverlayPressClose } from '../../../hooks/useOverlayPressClose';

interface ImageLightboxProps {
  url: string | null;
  alt?: string;
  onClose: () => void;
}

export default function ImageLightbox({ url, alt = '', onClose }: ImageLightboxProps) {
  const overlayPressClose = useOverlayPressClose(onClose);

  useEscapeKey(onClose, Boolean(url));

  if (!url) return null;

  return (
    <div className="qa-workspace-image-lightbox" {...overlayPressClose}>
      <div className="qa-workspace-image-lightbox-frame" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="qa-workspace-image-lightbox-close"
          aria-label="關閉"
          onClick={onClose}
        >
          <X size={24} />
        </button>
        <img src={url} alt={alt} className="qa-workspace-image-lightbox-img" />
      </div>
    </div>
  );
}
