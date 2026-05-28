import type { ImgHTMLAttributes } from 'react';

interface ZoomableThumbnailProps extends Omit<ImgHTMLAttributes<HTMLImageElement>, 'onClick' | 'alt'> {
  src: string;
  alt?: string;
  onZoom: (src: string) => void;
}

export default function ZoomableThumbnail({ src, alt = '', onZoom, style, ...rest }: ZoomableThumbnailProps) {
  return (
    <img
      {...rest}
      src={src}
      alt={alt}
      style={{ cursor: 'zoom-in', ...style }}
      onClick={() => onZoom(src)}
    />
  );
}
