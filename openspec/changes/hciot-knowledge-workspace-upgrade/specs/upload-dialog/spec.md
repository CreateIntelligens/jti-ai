## ADDED Requirements

### Requirement: Per-file upload status indicator
Each file in the UploadDialog file list SHALL display an icon indicating its current status: pending (grey), uploading (spinner), done (green check), or error (red X with tooltip).

#### Scenario: File upload in progress
- **WHEN** a file is being uploaded
- **THEN** a spinner icon is shown next to that file's name

#### Scenario: File upload complete
- **WHEN** a file upload succeeds
- **THEN** a green checkmark replaces the spinner

#### Scenario: File upload error
- **WHEN** a file upload fails
- **THEN** a red X icon is shown with the error message in a tooltip

### Requirement: File type icons
Each file in the UploadDialog file list SHALL display a type-specific icon based on its extension: CSV (table icon), PDF (file icon), Word/docx (file-text icon), image files (image icon), other (generic file icon).

#### Scenario: CSV file selected
- **WHEN** user adds a .csv file to the upload list
- **THEN** a table icon is shown next to the filename

#### Scenario: Image file selected
- **WHEN** user adds a .png file to the upload list
- **THEN** an image icon is shown next to the filename

### Requirement: Duplicate filename detection
When a file is added to the selectedFiles list, the system SHALL check if a file with the same name already exists in the list. If so, it SHALL show a warning badge on the duplicate file entry.

#### Scenario: Duplicate file added
- **WHEN** user adds "data.csv" when "data.csv" is already in the list
- **THEN** the new entry shows a warning indicator "(重複)"

#### Scenario: No duplicate
- **WHEN** user adds a file with a unique name
- **THEN** no warning is shown
