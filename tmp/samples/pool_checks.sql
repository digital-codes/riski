-- Cross-check: pools vs Paper.papertype / header reality
SELECT p.papertype, count(*)
FROM "File__paper__Paper" fp
JOIN "File" f ON f.sid = fp."srcSid"
JOIN "Paper" p ON p.sid = fp."tgtSid"
WHERE f."oparlKey" IN (
    SELECT a.oparl_key FROM "File_tags_assoc" a
    JOIN "File_tags" t ON t.id = a.tag_id
    WHERE t.tag = 'Beschlüsse' AND a.scheme = 'document-type')
GROUP BY 1 ORDER BY 2 DESC LIMIT 6;

-- paper-linked files of Beschlussvorlage/Antrag papers: what are their File.name labels?
SELECT p.papertype, f.name, count(*)
FROM "File__paper__Paper" fp
JOIN "File" f ON f.sid = fp."srcSid"
JOIN "Paper" p ON p.sid = fp."tgtSid"
WHERE p.papertype IN ('Beschlussvorlage', 'Antrag')
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 12;

-- are 'Antrag'-named files actually motion papers?
SELECT coalesce(p.papertype, '(no paper link)') AS papertype, count(*)
FROM "File" f
LEFT JOIN "File__paper__Paper" fp ON fp."srcSid" = f.sid
LEFT JOIN "Paper" p ON p.sid = fp."tgtSid"
WHERE f.name ~* '^antrag\y'
GROUP BY 1 ORDER BY 2 DESC;

-- same for Beschlussvorlage-named files
SELECT coalesce(p.papertype, '(no paper link)') AS papertype, count(*)
FROM "File" f
LEFT JOIN "File__paper__Paper" fp ON fp."srcSid" = f.sid
LEFT JOIN "Paper" p ON p.sid = fp."tgtSid"
WHERE f.name ILIKE 'Beschlussvorlage%' OR f.name ILIKE 'Beschlusssvorlage%'
GROUP BY 1 ORDER BY 2 DESC;
