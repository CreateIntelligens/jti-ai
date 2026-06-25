import { useState } from 'react';
import { getHciotImageUrl } from '../../utils/hciotImage';
import ImageLightbox from '../_shared/qaKnowledgeWorkspace/ImageLightbox';

interface HciotImageAttachmentProps {
  imageId: string;
  alt?: string;
}

export default function HciotImageAttachment({ imageId, alt }: HciotImageAttachmentProps) {
  const imageUrl = getHciotImageUrl(imageId);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);

  if (!imageUrl) {
    return null;
  }

  const altText = alt || `HCIoT reference image ${imageId}`;

  return (
    <figure className="qa-image-attachment">
      <button
        type="button"
        className="qa-image-link"
        onClick={() => setLightboxUrl(imageUrl)}
        title={`放大圖片 ${imageId}`}
      >
        <img
          className="qa-image-preview"
          src={imageUrl}
          alt={altText}
          loading="lazy"
          decoding="async"
        />
      </button>
      <figcaption className="qa-image-caption">Image ID: {imageId}</figcaption>
      <ImageLightbox url={lightboxUrl} alt={altText} onClose={() => setLightboxUrl(null)} />
    </figure>
  );
}
