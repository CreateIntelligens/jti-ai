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
    <figure className="hciot-image-attachment">
      <a
        className="hciot-image-link"
        href={imageUrl}
        target="_blank"
        rel="noreferrer"
        title={`Open image ${imageId}`}
      >
        <img
          className="hciot-image-preview"
          src={imageUrl}
          alt={alt || `HCIoT reference image ${imageId}`}
          loading="lazy"
          decoding="async"
        />
      </a>
      <figcaption className="hciot-image-caption">Image ID: {imageId}</figcaption>
    </figure>
  );
}
