## MODIFIED Requirements

### Requirement: Inline image upload in MergedCsvTable editing mode
When `MergedCsvTable` is in editing mode and `onUploadImage` prop is provided, the img column SHALL show an upload button instead of a text input. After successful upload, `image_id` SHALL be automatically populated in the row.

#### Scenario: Upload image from table cell
- **WHEN** user clicks the upload button in an img cell while editing
- **AND** selects an image file
- **THEN** the file is uploaded via `onUploadImage`
- **AND** the row's `img` field is set to the returned `image_id`
- **AND** a thumbnail preview is displayed

#### Scenario: Remove image from cell
- **WHEN** a row has an `img` value and the user clicks the remove button
- **THEN** the row's `img` field is cleared and the upload button is shown again

#### Scenario: No onUploadImage prop
- **WHEN** `onUploadImage` is not provided
- **THEN** a plain text input is shown for manual `image_id` entry

## MODIFIED Requirements (existing: image-management)

### Requirement: Image API uses image_id as primary key
`DELETE /hciot-admin/images/{image_id}` SHALL accept `image_id` without file extension (previously accepted filename with extension). The `HciotImage` interface SHALL use `image_id` as primary identifier; `filename` field is removed.

#### Scenario: Delete by image_id
- **WHEN** client sends `DELETE /hciot-admin/images/IMG_001`
- **THEN** the image with `image_id = "IMG_001"` is removed from MongoDB

### Requirement: normalizeImageId utility
`normalizeImageId(raw)` SHALL strip file extensions and path prefixes from any image reference string, returning only the bare `image_id`.

#### Scenario: Strip extension
- **WHEN** `normalizeImageId("IMG_001.png")` is called
- **THEN** returns `"IMG_001"`

#### Scenario: Strip path prefix
- **WHEN** `normalizeImageId("images/IMG_001.png")` is called  
- **THEN** the caller uses this result (strip path is done in csv_utils; normalize handles extension)
