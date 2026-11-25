-- Broader decided-result variants for the beschluss pool
SELECT count(*), count(DISTINCT f."oparlKey")
FROM "Consultation" c
JOIN "AgendaItem__auxiliaryFile__File" af ON af."srcSid" = c."agendaItemSid"
JOIN "AgendaItem" ai ON ai.sid = c."agendaItemSid"
JOIN "File" f ON f.sid = af."tgtSid"
WHERE c.role = 'Entscheidung'
  AND lower(coalesce(ai.result, '')) ~ 'beschlossen|zugestimmt|abgelehnt|einverstanden|genehmigt|gewählt';

-- distinct files + results for export (picker works from a TSV dump)
SELECT f."oparlKey", f.name, coalesce(to_char(f."date", 'YYYY-MM-DD'), ''), ai.result, m."name"
FROM "Consultation" c
JOIN "AgendaItem__auxiliaryFile__File" af ON af."srcSid" = c."agendaItemSid"
JOIN "AgendaItem" ai ON ai.sid = c."agendaItemSid"
JOIN "File" f ON f.sid = af."tgtSid"
LEFT JOIN "Meeting" m ON m.sid = c."meetingSid"
WHERE c.role = 'Entscheidung'
  AND lower(coalesce(ai.result, '')) ~ 'beschlossen|zugestimmt|abgelehnt|einverstanden|genehmigt|gewählt'
ORDER BY f."oparlKey";
