-- What do decision-consultations and their agenda items look like?
SELECT ai.result, count(*)
FROM "Consultation" c
JOIN "AgendaItem" ai ON ai.sid = c."agendaItemSid"
WHERE c.role = 'Entscheidung'
GROUP BY 1 ORDER BY 2 DESC;

-- Files hanging off agenda items of 'Entscheidung' consultations: name labels
SELECT f.name, count(*)
FROM "Consultation" c
JOIN "AgendaItem__auxiliaryFile__File" af ON af."srcSid" = c."agendaItemSid"
JOIN "File" f ON f.sid = af."tgtSid"
WHERE c.role = 'Entscheidung'
GROUP BY 1 ORDER BY 2 DESC LIMIT 25;
