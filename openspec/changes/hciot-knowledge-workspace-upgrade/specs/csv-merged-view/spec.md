## ADDED Requirements

### Requirement: Backend merged CSV API
The system SHALL provide an API endpoint `GET /hciot-admin/knowledge/topic-csv-merged` that accepts `topic_id` and `language` query parameters, reads all CSV files belonging to that topic from MongoDB, parses them, and returns a merged JSON response with `rows` (array of `{index, q, a, img}`) and `source_files` (array of filenames).

#### Scenario: Merge multiple CSVs for a topic
- **WHEN** client requests `GET /hciot-admin/knowledge/topic-csv-merged?topic_id=other/prp&language=zh`
- **THEN** system returns all rows from the main CSV and IMG CSVs under that topic, merged and sorted by index

#### Scenario: Topic has no CSV files
- **WHEN** client requests the merged endpoint for a topic with no CSV files
- **THEN** system returns `{ rows: [], source_files: [] }` with status 200

#### Scenario: Topic does not exist
- **WHEN** client requests the merged endpoint with an unknown topic_id
- **THEN** system returns `{ rows: [], source_files: [] }` with status 200

### Requirement: FileDetailPane default tab is merged view
The FileDetailPane SHALL display a tab bar with two tabs: "整合預覽" (default active) and "檔案內容". When the selected file has a `topic_id`, the "整合預覽" tab SHALL call the merged CSV API and render a table with columns: index, question, answer, image ID.

#### Scenario: File with topic_id selected
- **WHEN** user selects a file that belongs to topic `other/prp`
- **THEN** the detail pane shows the merged Q&A table as default view, with a tab to switch to single-file content

#### Scenario: File without topic_id selected
- **WHEN** user selects a file that has no topic_id
- **THEN** only the "檔案內容" tab is shown (no merged view tab)

#### Scenario: Switch to single file tab
- **WHEN** user clicks the "檔案內容" tab
- **THEN** the pane shows the original single-file content editor/preview

### Requirement: Merged table displays image references
Each row in the merged table that has a non-empty `img` field SHALL display the image ID as a clickable link or thumbnail preview using the existing `GET /hciot/images/{image_id}` endpoint.

#### Scenario: Row with image reference
- **WHEN** a merged row has `img: "IMG_T02_001"`
- **THEN** the table cell shows the image ID and a small thumbnail loaded from `/hciot/images/IMG_T02_001`

#### Scenario: Row without image reference
- **WHEN** a merged row has an empty `img` field
- **THEN** the image column cell is empty
