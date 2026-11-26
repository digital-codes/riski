# Overall Goal
Extract information from documents which can be used as grounding statements
for subsequent augmented retrieval

Documents are available in a postgres database, parameters can be taken 
from file src/private.py, use read-only user RO_USER with RO_PWD. 
Check src/db/__init__.py for reference
Primary content is given chunked markdown text in table File_chunks which relates to table File.

Digest the project readme to understand the project scope.

# Constraints and Restrictions

We are building a protoype implementation
output goes into json files or sqlite database, whichever seems more suitable

The database at hand is reconstructed from source Oparl-API retrieval with enhancements. 
The extraction mechanism must be flexible as we might not be able to get structured Oparl information
for all deployments. If web-scaping has to be used, the database will probably only provide the following source tables, more or less:
  * Location with name
  * Organisation with name
  * Meeting with date
  * AgendaItem with names. Names may hint to results or roles
  * File with name and teaser
  * File_chunks with content

Embeddings, teasers and relations similar to the exiting ones probably can be derived.
Derived tables likes Districts and Streets will exist as well, likewise concept related tables.
However in such minimal cases the database will be sparse, compared to the current one. 


For the protoype we will look only at documents (from File and File_chunks) which are put forward from some entity
in order the initiate some action or decision by the organization "Gemeinderat". We will ignore orgnaizations for the time beeing. Normally the initiative will be a request like "Antrag" or "Anfrage" and the response outcome will be like "zugestimmt", "abgelehnt", "vertagt" or similar together with some minutes (Protokoll, Niederschrift, etc). If a ballot takes place, we expect some form of ballot result with votes, for the given case Karlsruhe we also will get a single page pdf file with a screenshot of the poll. 

Note: we cannot expect consistent wording in any of the columns to derive categories from.
All documents are German language.

## identify relevant documents
Once we understand the current data model, we can try to identify Files which are requests and responses. We need to find the related papers, agendaItems, consultations (if available) and meetings (assume organization is always Gemeinderat). We also get the dates of the meeting. Check src/search/pgTimeline.py for an example of a database traversal.

The hope is, we can identify those documents from the database structure alone.
We have embedding vectors for all chunks using BGE-M3 type model. Vector similarities can be used, if helpful. For endpoint see below. We might also use files teasers and the decision model to verify identification. Use LLM only as last resort.

The following tables might be usefull to find the right documents. Make an initial plan first, test against some samples and improve until reliable. 

|table|column|example(s) (optional|
|-----|---|---|
|concept_schemes|description| Rollen von Dateien innherhalb von Dokumenten|
|concepts|definition| |
|AgendaItem|name|Bauanträge|
|AgendaItem|result|Kenntnisnahme, erledigt, enstimmig zugestimmt|
|File|name| Protocoll GR, Anlage 3 |
|Paper|name|Antrag CDU, Bekanntgaben, Anfrage |
|Paper|pypertype|Anfrage, Änderungs/Ergänzungsantrag, Beschlussvorlage |
|Consultation|role|Entscheidung|
|Consultation|authoritative||
|District|name| |
|Street|name| |
|Location|description| Bürgersaal|
|Meeting|name| Gemeinderat, Planungsausschuss (öffentlich/nicht öffentlich) |
|Membership|role|Ordentliches Mitglied|
|Organization|classification| Dezernat|
|Organization|name| Stadtkämmerei|
|Organization|shortname| LA|
|Person|name|Anna Zolga|
|Person|familyname|Oppelt|
|Person|givenname|Stefan|
|Person|affix|Stadtrat|

Write output json or sqlite
Always print status information to console, max interval 10s

## Extract statements

Once we have a set of documents, try to assign tags using a new schema https://ris-ki.de/ris/file-tags

Tags will be like:
Mobility, Economy, Climate, Population, Science, Education, 
Culture, Politics, Energy, Health, Building Construction, Housing,
Road construction, city development, samrt city,
Social, Childcare, Seniors, Sport, Funding, Volunteering,
Elections, Work/Labour

Create a table of tags and descriptions first, then use those descriptions to classify. Multiple tags per item are possible
but be strict though.

Use confidence values for each tag. Tag qualifiers might help in some cases, e.g. for construction work one could 
distinguish inital contruction, maintenance, upgrade, reconstruction. Watch out for german term "Sanierung" which means reconstruction.

In the request documents identify who the author is. Often this will be a political party like CDU, SPD, Grüne etc. Party name don't need to be consistent and composition might change over time. Put effort here to get it right.

Finally, analyze the documents. We expect that in this scope documents will have up to 5 chunks. Check that after building the the list. 

Try to generate statements for the following, considering "pairs" of requests and reponses (pairs might actualy be more than 2 because there might be a requests accompanied by one or more modification requests on the same original topic "ergänzungdssantrag, Änderungsantrag". Normally we expect only one response to a request, but event that might change due to change in external conditions, like Haushaltssperre ):

Topic name or title of the request
Type of request
Date of request (date of meeting when it was discussed. not the date of the file)
Document id and file name
Who made the request
What is intended impact or outcome / what should be done
Who is the audience / is affected
Who should take action
What action is requested (as precise as possible)
start and end date
Expected Benefit
Involved cost

Type of response (Abgestimmt, zur Kenntnis, etc, delayed)
Result of response
Which action will be taken
Who will execute the action
Expected cost
start and end date
Modifcations to request
Dependencies or constraints (e.g. funding to some project might be granted only under the condition, that a third party also grants funds)

Each "pair" (or multi-pair) must come with a full list of input documents (document id and file name )


Be as brief as possible without violating content complexity. Crosscheck: generate sample text from the derived statements at least for the response and evaluate if generated text and original text are compatible. style is irrelevant. facts count.




## Implementation

Use python scripts for all implementations. Typed and documented. Create a documentation file with usage for each scripts. use separate scripts to implement separate functionality.


# Model endpoints

For the first version we use only models provided by a local ollama instance. Do not use endpoint urls from private.py at this moment, but add a command line parameter with default "ollama" to use only those enpoint and models.

  * local ollama endpoint base url (add chat/completion etc): http::/localhost:11434/v1
  * Language model: one of granite4.2:8b, qwen3.5:4b, mistral:latest  try all and select the best one
  * Embedding model: bge-m3:latest
  * Decision model (systemone style): d3:2b


