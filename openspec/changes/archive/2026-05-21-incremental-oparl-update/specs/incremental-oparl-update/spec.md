## ADDED Requirements

### Requirement: Incremental OParl update capability
The system SHALL provide an incremental update mechanism for OParl resources. It SHALL track the timestamp of the newest processed resource in ``last_run.txt`` and, on subsequent runs, request only resources created or modified after that timestamp using the OParl ``createdSince`` query parameter. The mechanism SHALL skip saving resources whose ``modified``/``created`` timestamps are not newer than the existing saved file.

#### Scenario: First full crawl creates timestamp
- **WHEN** the incremental update script is executed for the first time (no ``last_run.txt`` present)
- **THEN** the script shall treat the timestamp as the epoch, crawl all resources, save them, and write the newest timestamp to ``last_run.txt``.

#### Scenario: Subsequent run fetches only new resources
- **WHEN** the script runs with an existing ``last_run.txt`` containing a timestamp
- **THEN** it shall request resources with ``createdSince`` set to that timestamp, save any newly created or modified resources, and update ``last_run.txt`` with the newest timestamp seen.

#### Scenario: Modified resource is updated
- **WHEN** an existing resource on disk has a newer ``modified`` timestamp in the fetched JSON
- **THEN** the script shall overwrite the existing JSON file with the newer version.

#### Scenario: Unchanged resource is skipped
- **WHEN** a fetched resource has a ``modified``/``created`` timestamp that is not newer than the stored file
- **THEN** the script shall not rewrite the file and shall log that the resource was unchanged.
