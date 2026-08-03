
# Schema doc-types

base url is ris-ki.de
schemas defined at ris-ki.de/ris/<something> like ris-ki.de/ris/doc-types

## Directory structure

/var/www/html/<document_root>/ris/doc-types

## Apache config 

```
<VirtualHost *:80>
    ServerName ris-ki.de
    ServerAlias www.ris-ki.de
    
    DocumentRoot /var/www/html/ris-schema
    
    # Global logging
    ErrorLog /var/log/httpd/ris-error.log
    CustomLog /var/log/httpd/ris-access.log combined
    
    # Security headers
    Header always set X-Content-Type-Options "nosniff"
    Header always set X-Frame-Options "SAMEORIGIN"
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"
    
    # Enable rewrite engine at VirtualHost level
    RewriteEngine On
    
    # Route /ris/doc-types (no trailing slash) to index.php
    RewriteRule "^/ris/doc-types$" "/ris/doc-types/index.php" [L,QSA]
    
    <Directory />
        AllowOverride All
        Options FollowSymLinks
    </Directory>
    
    <Directory /var/www/html/ris-schema>
        AllowOverride All
        Options -Indexes +FollowSymLinks
    </Directory>

    <Directory /var/www/html/ris-schema/ris>
        AllowOverride None
        Options -Indexes +FollowSymLinks
        
        <IfModule mod_expires.c>
            ExpiresActive On
            ExpiresByType text/turtle "access plus 1 hour"
        </IfModule>
        
        <IfModule mod_headers.c>
            Header set Access-Control-Allow-Origin "*"
        </IfModule>
    </Directory>
    
    <Directory /var/www/html/ris-schema/ris/doc-types>
        AllowOverride None
        Options -Indexes +FollowSymLinks
        DirectorySlash Off
        DirectoryIndex index.php
        FallbackResource /ris/doc-types/index.php
    </Directory>
RewriteCond %{SERVER_NAME} =ris-ki.de [OR]
RewriteCond %{SERVER_NAME} =www.ris-ki.de
RewriteRule ^ https://%{SERVER_NAME}%{REQUEST_URI} [END,NE,R=permanent]
</VirtualHost>

```

## index.php 

```
<?php

// Handle potential 500 errors from missing PHP extensions
if (!extension_loaded('ctype')) {
    // Install: dnf install php-ctype
    error_log('PHP ctype extension missing');
}

header('Access-Control-Allow-Origin: *');

$uri = 'https://ris-ki.de/ris/doc-types';
$turtleFile = __DIR__ . '/doc-types.ttl';

// Check if the TTL file exists, otherwise generate minimal RDF
if (!file_exists($turtleFile)) {
    $rdf = <<<TURTLE
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<$uri> a skos:ConceptScheme ;
    dct:title "RIS Dokumententypen"@de ;
    dct:description "Fachliche Typen von Ratsdokumenten"@de ;
    dct:language "de"^^xsd:language .
TURTLE;
} else {
    $rdf = file_get_contents($turtleFile);
}

// Determine desired format from Accept header
function negotiateFormat(): string {
    $accept = $_SERVER['HTTP_ACCEPT'] ?? '*/*';
    
    // Order matters: more specific first
    if (strpos($accept, 'application/rdf+xml') !== false) {
        return 'xml';
    }
    if (strpos($accept, 'application/ld+json') !== false) {
        return 'json';
    }
    if (strpos($accept, 'text/turtle') !== false || strpos($accept, 'text/n3') !== false) {
        return 'ttl';
    }
    if (strpos($accept, 'text/html') !== false) {
        return 'html';
    }
    return 'html';
}

// Convert Turtle to JSON-LD
function turtleToJsonLd(string $ttl, string $baseUri): void {
    header('Content-Type: application/ld+json; charset=utf-8');
    echo json_encode([
        '@context' => [
            'skos' => 'http://www.w3.org/2004/02/skos/core#',
            'dct' => 'http://purl.org/dc/terms/',
            '@vocab' => 'http://www.w3.org/2000/01/rdf-schema#'
        ],
        '@id' => $baseUri,
        '@type' => 'skos:ConceptScheme',
        'dct:title' => [['@value' => 'RIS Dokumententypen', '@language' => 'de']],
        'dct:description' => [['@value' => 'Fachliche Typen von Ratsdokumenten', '@language' => 'de']],
        'dct:language' => 'de'
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

// Render human-readable HTML page
function renderHtml(string $ttl, string $baseUri): void {
    header('Content-Type: text/html; charset=utf-8');
    ?>
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>RIS Dokumententypen</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; line-height: 1.6; }
        h1 { border-bottom: 2px solid #6d4aff; padding-bottom: 0.5em; color: #333; }
        pre { background: #f5f5f5; padding: 1em; overflow-x: auto; border-radius: 4px; font-size: 0.9em; }
        code { background: #eee; padding: 0.2em 0.4em; border-radius: 3px; }
        .formats a { display: inline-block; margin-right: 1.5em; padding: 0.5em 1em; background: #6d4aff; color: white; text-decoration: none; border-radius: 4px; }
        .formats a:hover { background: #5a3dd4; }
        .uri-box { background: #f0f0f0; padding: 0.5em; border-left: 3px solid #6d4aff; margin: 1em 0; }
    </style>
</head>
<body>
    <h1>RIS Dokumententypen</h1>
    
    <div class="uri-box">
        <strong>URI:</strong> <code><?php echo htmlspecialchars($baseUri); ?></code>
    </div>
    
    <p><?php echo nl2br(htmlspecialchars("Fachliche Typen von Ratsdokumenten")); ?></p>
    
    <h2>Verfügbare Formate</h2>
    <div class="formats">
        <a href="<?php echo htmlspecialchars($baseUri); ?>">Turtle</a>
        <a href="<?php echo htmlspecialchars($baseUri); ?>" accept="application/ld+json">JSON-LD</a>
        <a href="<?php echo htmlspecialchars($baseUri); ?>" accept="application/rdf+xml">RDF/XML</a>
    </div>
    
    <h2>RDF-Turtle Darstellung</h2>
    <pre><code><?php echo htmlspecialchars($ttl); ?></code></pre>
</body>
</html>
<?php
    exit;
}

// Main routing
$format = negotiateFormat();

switch ($format) {
    case 'ttl':
        header('Content-Type: text/turtle; charset=utf-8');
        echo $rdf;
        break;
        
    case 'json':
        turtleToJsonLd($rdf, $uri);
        break;
        
    case 'xml':
        // For now, just return Turtle (proper conversion requires library)
        header('Content-Type: application/rdf+xml; charset=utf-8');
        echo "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n";
        echo "<!-- See Turtle representation at {$uri} -->\n";
        echo "<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">\n";
        echo "</rdf:RDF>";
        break;
        
    case 'html':
    default:
        renderHtml($rdf, $uri);
        break;
}
?>

```

## Sample schema 

**doc-types.ttl**

```
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<https://ris-ki.de/ris/doc-types> a skos:ConceptScheme ;
    dct:title "RIS Dokumententypen"@de ;
    dct:description "Fachliche Typen von Ratsdokumenten"@de ;
    dct:language "de"^^xsd:language .


```



# Adding new schemas
## 1. Create the Directory and Files
> mkdir -p /var/www/html/ris-schema/ris/locations

Create index.php (copy from doc-types, change the URI and labels):
```
cp /var/www/html/ris-schema/ris/doc-types/index.php /var/www/html/ris-schema/ris/locations/index.php
```

Then edit /var/www/html/ris-schema/ris/locations/index.php and change these lines:
```
$uri = 'https://ris-ki.de/ris/locations';
```

And in the fallback RDF block:
```
<$uri> a skos:ConceptScheme ;
    dct:title "RIS Orte"@de ;
    dct:description "Fachliche Orte von Ratsdokumenten"@de ;
    dct:language "de"^^xsd:language .
```

Optionally create a .ttl file if your vocabulary manager exports one:
``` 
# When ready, export your Turtle here:
/var/www/html/ris-schema/ris/locations/locations.ttl
```

## 2. Add the VirtualHost-Level Rewrite Rule

In /etc/httpd/conf.d/ris-schema.conf, add one line next to the existing doc-types rule:
```
    # Route vocabulary URIs to their index.php (no trailing slash)
    RewriteRule "^/ris/doc-types$" "/ris/doc-types/index.php" [L,QSA]
    RewriteRule "^/ris/locations$" "/ris/locations/index.php" [L,QSA]
```

## 3. Add the Directory Block

Add a new <Directory> block alongside the existing one:
```
    <Directory /var/www/html/ris-schema/ris/locations>
        AllowOverride None
        Options -Indexes +FollowSymLinks
        DirectorySlash Off
        DirectoryIndex index.php
        FallbackResource /ris/locations/index.php
    </Directory>
```

## 4. Apply and Test
```
sudo apachectl configtest
sudo systemctl restart httpd

curl -I http://ris-ki.de/ris/locations
curl -I http://ris-ki.de/ris/locations/
curl -H "Accept: text/turtle" http://ris-ki.de/ris/locations
```

Summary: Checklist for Any New Scheme

For a new scheme called X:
 1)	mkdir /var/www/html/ris-schema/ris/X
 2)	Copy and edit index.php (change $uri, title, description)
 3)	Add RewriteRule "^/ris/X$" "/ris/X/index.php" [L,QSA] in vhost
 4)	Add <Directory /var/www/html/ris-schema/ris/X> block in vhost
 5)	apachectl configtest && systemctl restart httpd

That's the whole pattern — two lines in Apache config plus the PHP file. Each scheme is fully independent.

