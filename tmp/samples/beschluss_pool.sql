-- The name-regex-derived Beschluesse tag pool: name + parent papertype + date spread
SELECT f.name,
       coalesce(p.papertype, '(no paper link)') AS papertype,
       coalesce(to_char(f."date", 'YYYY-MM-DD'), '') AS d
FROM "File_tags_assoc" a
JOIN "File_tags" t ON t.id = a.tag_id
JOIN "File" f ON f."oparlKey" = a.oparl_key
LEFT JOIN "File__paper__Paper" fp ON fp."srcSid" = f.sid
LEFT JOIN "Paper" p ON p.sid = fp."tgtSid"
WHERE t.tag = 'Beschlüsse' AND a.scheme = 'document-type' AND a.source = 'name-regex'
  AND f.name !~* 'vorlage'
ORDER BY f.name
LIMIT 60;
