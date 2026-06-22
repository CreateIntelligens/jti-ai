import { getHciotImageUrl } from '../../utils/hciotImage';

interface HciotImageAttachmentProps {
  imageId: string;
  alt?: string;
}

export default function HciotImageAttachment({ imageId, alt }: HciotImageAttachmentProps) {
  const imageUrl = getHciotImageUrl(imageId);

  if (!imageUrl) {
    return null;
  }

  return (
    <figure className="qa-image-attachment">
      <a
        className="qa-image-link"
        href={imageUrl}
        target="_blank"
        rel="noreferrer"
        title={`Open image ${imageId}`}
      >
        <img
          className="qa-image-preview"
          src={imageUrl}
          alt={alt || `HCIoT reference image ${imageId}`}
          loading="lazy"
          decoding="async"
        />
      </a>
      <figcaption className="qa-image-caption">Image ID: {imageId}</figcaption>
    </figure>
  );
}
