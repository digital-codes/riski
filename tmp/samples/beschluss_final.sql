-- Final beschluss pool: standalone Beschluss words + Wortlaut-der-Beschluesse series,
-- excluding vorlag(en/entwuerfe) and 'ohne Beschluss' plan items
SELECT count(*) FROM "File"
WHERE (name ~* '(^|[[:punct:][:space:]])beschlu'
       OR name ~* 'beschlüsse' OR name ~* 'wortlaut')
  AND name !~* 'vorlag' AND name !~* 'ohne beschluss'
  AND name !~* 'entwurf';

-- what is left beyond the wortlaut series?
SELECT name, count(*) FROM "File"
WHERE (name ~* '(^|[[:punct:][:space:]])beschlu'
       OR name ~* 'beschlüsse' OR name ~* 'wortlaut')
  AND name !~* 'vorlag' AND name !~* 'ohne beschluss'
  AND name !~* 'entwurf'
  AND name !~* 'wortlaut'
GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
