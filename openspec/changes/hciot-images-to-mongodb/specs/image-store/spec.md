## ADDED Requirements

### Requirement: MongoDB image store
The system SHALL provide `HciotImageStore` backed by MongoDB collection `hciot_images`. Images SHALL be stored as `bson.Binary(data)` with `image_id` (no extension), `content_type`, `size`, and `created_at` fields.

#### Scenario: Insert and retrieve image
- **WHEN** `insert_image("test_001", data, "image/png")` is called
- **THEN** the image is stored and `get_image("test_001")` returns `{ image_id, data, content_type, size }`

#### Scenario: Duplicate image_id rejected
- **WHEN** `insert_image` is called with an `image_id` that already exists
- **THEN** `ValueError` is raised with "already exists" in the message

#### Scenario: List images excludes binary data
- **WHEN** `list_images()` is called
- **THEN** returns list of dicts without the `data` field

#### Scenario: Delete returns bool
- **WHEN** `delete_image("existing_id")` is called
- **THEN** returns `True` and the image is no longer retrievable
- **WHEN** `delete_image("nonexistent_id")` is called
- **THEN** returns `False`
