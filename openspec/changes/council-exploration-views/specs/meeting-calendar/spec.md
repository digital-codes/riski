# Spec Delta

## Purpose

Macht kommende Sitzungen sichtbar und einzeln abonnierbar: Liste der
kommenden Sitzungen mit öffentlicher Tagesordnung und Download einer
Sitzung als Kalendereintrag (.ics).

## ADDED Requirements

### Requirement: Upcoming meetings

The API SHALL expose `GET /meetings/upcoming` returning scheduled meetings
with start time, body/committee name, and public/non-public status, ordered
by start time. Meetings without a start date SHALL NOT be listed.

#### Scenario: Upcoming meetings ordered

- **WHEN** `/meetings/upcoming` is requested
- **THEN** only meetings with a future start date are returned, ordered by
  start time ascending

### Requirement: Meeting detail with agenda

The API SHALL expose `GET /meetings/{id}` returning the meeting's metadata
and its public agenda: agenda items in order with name and decision status
where available, and the documents linked to each item. An unknown meeting
SHALL respond 404.

#### Scenario: Agenda with decision status

- **WHEN** a past meeting's detail is requested
- **THEN** the agenda items carry their recorded decision status where
  available

#### Scenario: Unknown meeting

- **WHEN** `GET /meetings/{id}` is called with an unknown id
- **THEN** the API responds 404

### Requirement: Single-meeting calendar download

The API SHALL expose `GET /meetings/{id}/calendar.ics` returning an
iCalendar file for the meeting (Europe/Berlin times), with public agenda
items as sub-events. The file SHALL be served with a calendar content type.

#### Scenario: ICS download

- **WHEN** the calendar endpoint for a meeting is fetched
- **THEN** a valid iCalendar file with the meeting time and public agenda
  items is returned

### Requirement: Meetings page in the frontend

The frontend SHALL provide a meetings page (menu-reachable) listing
upcoming meetings with an agenda accordion per meeting and a calendar
download button.

#### Scenario: Meetings page shows agenda and download

- **WHEN** the user opens the meetings page
- **THEN** upcoming meetings are listed with their public agenda and an
  .ics download button per meeting
