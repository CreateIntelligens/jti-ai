## ADDED Requirements

### Requirement: Image list API
The system SHALL provide `GET /hciot-admin/images/` that lists all image files in `data/hciot/images/`, returning an array of `{filename, size_bytes, image_id, url}` for each file.

#### Scenario: List images
- **WHEN** client requests `GET /hciot-admin/images/`
- **THEN** system returns all images with their filename, size, extracted image_id (filename without extension), and URL path

#### Scenario: Empty images directory
- **WHEN** images directory has no files
- **THEN** system returns `{ images: [] }` with status 200

### Requirement: Image upload API
The system SHALL provide `POST /hciot-admin/images/upload` accepting a multipart file upload with an optional `image_id` form field. If `image_id` is provided, the file SHALL be saved as `{image_id}.{original_extension}`. If omitted, the original filename is used. File size MUST NOT exceed 10MB. Only image extensions (jpg, jpeg, png, gif, webp) SHALL be accepted.

#### Scenario: Upload with custom image_id
- **WHEN** user uploads `photo.jpg` with `image_id=IMG_T02_006`
- **THEN** file is saved as `data/hciot/images/IMG_T02_006.jpg` and response includes the saved filename

#### Scenario: Upload without image_id
- **WHEN** user uploads `my_diagram.png` without specifying image_id
- **THEN** file is saved as `data/hciot/images/my_diagram.png`

#### Scenario: Filename conflict
- **WHEN** user uploads with image_id that already exists (any extension)
- **THEN** system returns 409 with error message

#### Scenario: Invalid file type
- **WHEN** user uploads a `.pdf` file
- **THEN** system returns 400 with error message

#### Scenario: File too large
- **WHEN** user uploads an image exceeding 10MB
- **THEN** system returns 413 with error message

### Requirement: Image delete API
The system SHALL provide `DELETE /hciot-admin/images/{filename}` that removes the specified image file from the filesystem.

#### Scenario: Delete existing image
- **WHEN** client sends DELETE for an existing image filename
- **THEN** file is removed and system returns success

#### Scenario: Delete non-existent image
- **WHEN** client sends DELETE for a filename that does not exist
- **THEN** system returns 404

### Requirement: Image explorer section in sidebar
The ExplorerSidebar SHALL display an "圖片" top-level folder node at the bottom of the tree. Expanding it SHALL list all images from the list API. Clicking an image SHALL show a preview in the detail pane.

#### Scenario: View images in explorer
- **WHEN** user expands the "圖片" folder in the sidebar
- **THEN** all images are listed with their filenames

#### Scenario: Click image in explorer
- **WHEN** user clicks an image in the explorer
- **THEN** the detail pane shows the image preview with filename and size metadata

### Requirement: Image upload UI in workspace
The workspace SHALL provide an image upload interface accessible from the images section. Users can drag-and-drop or click to select image files. An optional text field allows specifying the image_id (IMG ID). When uploading multiple images, each file uses its original filename unless individually renamed.

#### Scenario: Single image upload with custom ID
- **WHEN** user uploads one image and fills in `IMG_T15_001` as the image ID
- **THEN** the image is uploaded with that ID and appears in the explorer

#### Scenario: Batch image upload
- **WHEN** user uploads 3 images without specifying IDs
- **THEN** all 3 images are uploaded using their original filenames
