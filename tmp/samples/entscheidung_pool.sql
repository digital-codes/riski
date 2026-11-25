-- Pool: agenda-item files of decided consultations (role='Entscheidung', decided result)
SELECT count(*), count(DISTINCT f."oparlKey")
FROM "Consultation" c
JOIN "AgendaItem__auxiliaryFile__File" af ON af."srcSid" = c."agendaItemSid"
JOIN "AgendaItem" ai ON ai.sid = c."agendaItemSid"
JOIN "File" f ON f.sid = af."tgtSid"
WHERE c.role = 'Entscheidung'
  AND lower(coalesce(ai.result, '')) ~ 'beschlossen|zugestimmt|abgelehnt';

-- name families of that pool + year spread
SELECT regexp_replace(lower(f.name), '^20[0-9]{2}[-._]?[0-9]{2}[-._]?[0-9]{2}_?', '') AS fam, count(*),
       min(to_char(f."date", 'YYYY-MM-DD')), max(to_char(f."date", 'YYYY-MM-DD'))
FROM "Consultation" c
JOIN "AgendaItem__auxiliaryFile__File" af ON af."srcSid" = c."agendaItemSid"
JOIN "AgendaItem" ai ON ai.sid = c."agendaItemSid"
JOIN "File" f ON f.sid = af."tgtSid"
WHERE c.role = 'Entscheidung'
  AND lower(coalesce(ai.result, '')) ~ 'beschlossen|zugestimmt|abgelehnt'
GROUP BY 1 ORDER BY 2 DESC LIMIT 15;

-- do these agenda-item files ALSO link to a paper (File__paper__Paper)?
SELECT count(*) FROM "Consultation" c
JOIN "AgendaItem__auxiliaryFile__File" af ON af."srcSid" = c."agendaItemSid"
JOIN "File" f ON f.sid = af."tgtSid"
LEFT JOIN "File__paper__Paper" fp2 ON fp2."srcSid" = f.sid
WHERE c.role = 'Entscheidung'
  AND lower(coalesce((SELECT ai.result FROM "AgendaItem" ai WHERE ai.sid = c."agendaItemSid"), '')) ~ 'beschlossen|zugestimmt|abgelehnt'
  AND fp2."tgtSid" IS NOT NULL;
