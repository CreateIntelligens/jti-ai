import { useEffect, useRef } from 'react';

export function usePendingImageUrls(rows: { pendingImageFile?: File | null }[]): Map<File, string> {
  const cacheRef = useRef(new Map<File, string>());

  const currentFiles = new Set(
    rows.map((r) => r.pendingImageFile).filter((f): f is File => f instanceof File),
  );

  for (const [file, url] of cacheRef.current) {
    if (!currentFiles.has(file)) {
      URL.revokeObjectURL(url);
      cacheRef.current.delete(file);
    }
  }

  for (const file of currentFiles) {
    if (!cacheRef.current.has(file)) {
      cacheRef.current.set(file, URL.createObjectURL(file));
    }
  }

  useEffect(() => {
    const cache = cacheRef.current;
    return () => { for (const url of cache.values()) URL.revokeObjectURL(url); };
  }, []);

  return cacheRef.current;
}

export interface UploadedImageResult {
  image_id?: string;
  id?: string;
  name?: string;
}

export type DeleteImageHandler = (imageId: string) => Promise<void>;

export function extractUploadedImageId(result: UploadedImageResult): string {
  const imageId = result.image_id || result.id || result.name;
  if (!imageId) {
    throw new Error('Image upload did not return an image ID.');
  }
  return imageId;
}

export async function rollbackUploadedImages(
  imageIds: string[],
  onDeleteImage?: DeleteImageHandler,
): Promise<void> {
  if (!imageIds.length || !onDeleteImage) return;

  const results = await Promise.allSettled(imageIds.map((imageId) => onDeleteImage(imageId)));
  results.forEach((result, index) => {
    if (result.status === 'rejected') {
      console.error('Failed to rollback uploaded image:', imageIds[index], result.reason);
    }
  });
}
