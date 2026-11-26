# Spec Delta

## ADDED Requirements

### Requirement: Session file list uses the File's downloadUrl

The meeting-scope (gremium session) answer SHALL assemble every file-list
entry (topic files and `top_files`) with the File row's download URL,
resolved from the file store by the file's OParL id/key. The file's OParL
entry URL (`oparlId`) SHALL NOT be substituted as the value of a file's
download URL: an entry without a resolvable download URL SHALL carry no
download URL (the frontend renders it as plain text), never a metadata
link.

#### Scenario: File with stored downloadUrl

- **WHEN** a session answer's file list contains a file whose File row has
  a download URL
- **THEN** the entry's `downloadurl` equals that download URL (a document
  link, e.g. `…/downloadfiles/…pdf`), not the file's OParL entry URL

#### Scenario: File without stored downloadUrl

- **WHEN** a session answer's file list contains a file whose File row has
  no download URL
- **THEN** the entry's `downloadurl` is absent/None — the OParL entry URL
  (`…/files/<id>`) is not delivered as a download link

#### Scenario: URL stays clickable in the topic popup

- **WHEN** the session topic list renders a file entry carrying a download
  URL
- **THEN** the card links that URL directly for download (no frontend
  fallback to the OParL entry URL is required for the link to work)
