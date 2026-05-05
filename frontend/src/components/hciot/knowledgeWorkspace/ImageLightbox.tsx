import { X } from 'lucide-react';
import { useEscapeKey } from '../../../hooks/useEscapeKey';

interface ImageLightboxProps {
  url: string | null;
  alt?: string;
  onClose: () => void;
}

export default function ImageLightbox({ url, alt = '', onClose }: ImageLightboxProps) {
  useEscapeKey(onClose, Boolean(url));

  if (!url) return null;

  return (
    <div className="hciot-image-lightbox" onClick={onClose}>
      <div className="hciot-image-lightbox-frame" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="hciot-image-lightbox-close"
          aria-label="關閉"
          onClick={onClose}
        >
          <X size={24} />
        </button>
        <img src={url} alt={alt} className="hciot-image-lightbox-img" />
      </div>
    </div>
  );
}
