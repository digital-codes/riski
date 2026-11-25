-- Wider Beschluss name pool: any name mentioning Beschluss/Beschlüsse, no 'vorlage'
SELECT count(*) FROM "File"
WHERE name ~* 'beschlu(ss|ss)' AND name !~* 'vorlage';

-- family breakdown: collapse long names, show the recognizable families
SELECT regexp_replace(lower(name), '^[0-9].*$', '(dated: Wortlaut/Protokoll series)', '')
       AS family, count(*)
FROM "File"
WHERE name ~* 'beschluss' AND name !~* 'vorlage'
GROUP BY 1 ORDER BY 2 DESC LIMIT 25;

-- distinct non-Wortlaut names, alphabetical, to eyeball purity
SELECT name, count(*) FROM "File"
WHERE name ~* 'beschluss' AND name !~* 'vorlage' AND name !~* 'wortlaut'
GROUP BY 1 ORDER BY 2 DESC LIMIT 30;
