-- DROP SCHEMA public;

CREATE SCHEMA public AUTHORIZATION pg_database_owner;

COMMENT ON SCHEMA public IS 'standard public schema';

-- DROP TYPE public.halfvec;

CREATE TYPE public.halfvec (
	INPUT = halfvec_in,
	OUTPUT = halfvec_out,
	RECEIVE = halfvec_recv,
	SEND = halfvec_send,
	TYPMOD_IN = halfvec_typmod_in,
	ALIGNMENT = 4,
	STORAGE = secondary,
	CATEGORY = U,
	DELIMITER = ',');

-- DROP TYPE public.sparsevec;

CREATE TYPE public.sparsevec (
	INPUT = sparsevec_in,
	OUTPUT = sparsevec_out,
	RECEIVE = sparsevec_recv,
	SEND = sparsevec_send,
	TYPMOD_IN = sparsevec_typmod_in,
	ALIGNMENT = 4,
	STORAGE = secondary,
	CATEGORY = U,
	DELIMITER = ',');

-- DROP TYPE public.vector;

CREATE TYPE public.vector (
	INPUT = vector_in,
	OUTPUT = vector_out,
	RECEIVE = vector_recv,
	SEND = vector_send,
	TYPMOD_IN = vector_typmod_in,
	ALIGNMENT = 4,
	STORAGE = secondary,
	CATEGORY = U,
	DELIMITER = ',');

-- DROP SEQUENCE public."AgendaItem_sid_seq";

CREATE SEQUENCE public."AgendaItem_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."Body_sid_seq";

CREATE SEQUENCE public."Body_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."Consultation_sid_seq";

CREATE SEQUENCE public."Consultation_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."File_sid_seq";

CREATE SEQUENCE public."File_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."LegislativeTerm_sid_seq";

CREATE SEQUENCE public."LegislativeTerm_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."Location_sid_seq";

CREATE SEQUENCE public."Location_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."Meeting_sid_seq";

CREATE SEQUENCE public."Meeting_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."Membership_sid_seq";

CREATE SEQUENCE public."Membership_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."Organization_sid_seq";

CREATE SEQUENCE public."Organization_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."Paper_sid_seq";

CREATE SEQUENCE public."Paper_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."Person_sid_seq";

CREATE SEQUENCE public."Person_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."System_sid_seq";

CREATE SEQUENCE public."System_sid_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.concepts_id_seq;

CREATE SEQUENCE public.concepts_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public."contentEmbeddings_id_seq";

CREATE SEQUENCE public."contentEmbeddings_id_seq"
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 2147483647
	START 1
	CACHE 1
	NO CYCLE;
-- DROP SEQUENCE public.semantic_triples_id_seq;

CREATE SEQUENCE public.semantic_triples_id_seq
	INCREMENT BY 1
	MINVALUE 1
	MAXVALUE 9223372036854775807
	START 1
	CACHE 1
	NO CYCLE;-- public."File" definition

-- Drop table

-- DROP TABLE public."File";

CREATE TABLE public."File" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, accessurl varchar(256) NULL, "date" timestamp NULL, downloadurl varchar(256) NULL, filename varchar(256) NULL, mimetype varchar(256) NULL, "name" varchar(256) NULL, "content" text NULL, CONSTRAINT "File_pkey" PRIMARY KEY (sid));
CREATE INDEX "ix_File_id" ON public."File" USING btree (id);
CREATE UNIQUE INDEX "ix_File_oparlId" ON public."File" USING btree ("oparlId");
CREATE INDEX "ix_File_oparlKey" ON public."File" USING btree ("oparlKey");


-- public."Location" definition

-- Drop table

-- DROP TABLE public."Location";

CREATE TABLE public."Location" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, description varchar(256) NULL, locality varchar(256) NULL, postalcode varchar(256) NULL, room varchar(256) NULL, streetaddress varchar(256) NULL, sublocality varchar(256) NULL, CONSTRAINT "Location_pkey" PRIMARY KEY (sid));
CREATE INDEX "ix_Location_id" ON public."Location" USING btree (id);
CREATE UNIQUE INDEX "ix_Location_oparlId" ON public."Location" USING btree ("oparlId");
CREATE INDEX "ix_Location_oparlKey" ON public."Location" USING btree ("oparlKey");


-- public."Meeting" definition

-- Drop table

-- DROP TABLE public."Meeting";

CREATE TABLE public."Meeting" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, end_date timestamp NULL, "name" varchar(256) NULL, start_date timestamp NULL, CONSTRAINT "Meeting_pkey" PRIMARY KEY (sid));
CREATE INDEX "ix_Meeting_id" ON public."Meeting" USING btree (id);
CREATE UNIQUE INDEX "ix_Meeting_oparlId" ON public."Meeting" USING btree ("oparlId");
CREATE INDEX "ix_Meeting_oparlKey" ON public."Meeting" USING btree ("oparlKey");


-- public."System" definition

-- Drop table

-- DROP TABLE public."System";

CREATE TABLE public."System" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, body varchar(256) NULL, contactemail varchar(256) NULL, contactname varchar(256) NULL, "name" varchar(256) NULL, oparlversion varchar(256) NULL, product varchar(256) NULL, vendor varchar(256) NULL, website varchar(256) NULL, CONSTRAINT "System_pkey" PRIMARY KEY (sid));
CREATE INDEX "ix_System_id" ON public."System" USING btree (id);
CREATE UNIQUE INDEX "ix_System_oparlId" ON public."System" USING btree ("oparlId");
CREATE INDEX "ix_System_oparlKey" ON public."System" USING btree ("oparlKey");


-- public.concept_schemes definition

-- Drop table

-- DROP TABLE public.concept_schemes;

CREATE TABLE public.concept_schemes ( uri varchar(500) NOT NULL, title varchar(255) NOT NULL, description text NULL, "language" bpchar(2) DEFAULT 'de'::bpchar NULL, "version" varchar(20) NULL, created_at timestamp DEFAULT now() NULL, CONSTRAINT concept_schemes_pkey PRIMARY KEY (uri));


-- public."contentEmbeddings" definition

-- Drop table

-- DROP TABLE public."contentEmbeddings";

CREATE TABLE public."contentEmbeddings" ( id serial4 NOT NULL, "oparlKey" varchar NULL, value public.vector NULL, CONSTRAINT "contentEmbeddings_pkey" PRIMARY KEY (id), CONSTRAINT "uq_embedding_oparlKey" UNIQUE ("oparlKey"));


-- public.entity_concepts definition

-- Drop table

-- DROP TABLE public.entity_concepts;

CREATE TABLE public.entity_concepts ( entity_type varchar(100) NOT NULL, entity_id int8 NOT NULL, concept_uri varchar(500) NOT NULL, relation_type varchar(50) DEFAULT 'skos:subject'::character varying NOT NULL, confidence_score float8 DEFAULT 1.0 NULL, CONSTRAINT entity_concepts_pkey PRIMARY KEY (entity_type, entity_id, concept_uri, relation_type));
CREATE INDEX idx_concept_entities ON public.entity_concepts USING btree (concept_uri);
CREATE INDEX idx_entity_concepts ON public.entity_concepts USING btree (entity_type, entity_id);


-- public.oparl_semantic_mapping definition

-- Drop table

-- DROP TABLE public.oparl_semantic_mapping;

CREATE TABLE public.oparl_semantic_mapping ( oparl_object_type varchar(100) NOT NULL, oparl_property varchar(200) NOT NULL, target_predicate_uri varchar(500) NOT NULL, target_value_type varchar(50) NOT NULL, transformation_rule text NULL, priority int4 DEFAULT 1 NULL, CONSTRAINT oparl_semantic_mapping_pkey PRIMARY KEY (oparl_object_type, oparl_property));


-- public.registered_ontologies definition

-- Drop table

-- DROP TABLE public.registered_ontologies;

CREATE TABLE public.registered_ontologies ( uri varchar(500) NOT NULL, title varchar(255) NOT NULL, "namespace" varchar(200) NOT NULL, "version" varchar(20) NULL, provider varchar(200) NULL, status varchar(20) DEFAULT 'active'::character varying NULL, documentation_url text NULL, last_verified date NULL, notes text NULL, CONSTRAINT registered_ontologies_pkey PRIMARY KEY (uri));


-- public.semantic_triples definition

-- Drop table

-- DROP TABLE public.semantic_triples;

CREATE TABLE public.semantic_triples ( id bigserial NOT NULL, subject_entity_type varchar(100) NOT NULL, subject_entity_id int8 NOT NULL, predicate_uri varchar(500) NOT NULL, object_value text NULL, object_entity_type varchar(100) NULL, object_entity_id int8 NULL, confidence_score float8 DEFAULT 1.0 NULL, provenance_source varchar(200) NULL, created_at timestamp DEFAULT now() NULL, CONSTRAINT chk_object_either_value_or_ref CHECK ((((object_value IS NOT NULL) AND (object_entity_id IS NULL)) OR ((object_value IS NULL) AND (object_entity_id IS NOT NULL)))), CONSTRAINT semantic_triples_pkey PRIMARY KEY (id));
CREATE INDEX idx_triples_composite ON public.semantic_triples USING btree (subject_entity_type, subject_entity_id, predicate_uri);
CREATE INDEX idx_triples_object_ref ON public.semantic_triples USING btree (object_entity_type, object_entity_id);
CREATE INDEX idx_triples_predicate ON public.semantic_triples USING btree (predicate_uri);
CREATE INDEX idx_triples_subject ON public.semantic_triples USING btree (subject_entity_type, subject_entity_id);


-- public.uri_mappings definition

-- Drop table

-- DROP TABLE public.uri_mappings;

CREATE TABLE public.uri_mappings ( local_uri varchar(500) NOT NULL, external_uri varchar(500) NOT NULL, mapping_type varchar(50) DEFAULT 'owl:equivalentClass'::character varying NULL, confidence float8 DEFAULT 1.0 NULL, verified_by varchar(100) NULL, verified_at timestamp NULL, CONSTRAINT uri_mappings_pkey PRIMARY KEY (local_uri));


-- public."Body" definition

-- Drop table

-- DROP TABLE public."Body";

CREATE TABLE public."Body" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, agendaitem varchar(256) NULL, consultation varchar(256) NULL, contactemail varchar(256) NULL, contactname varchar(256) NULL, file varchar(256) NULL, legislativetermlist varchar(256) NULL, licensevalidsince timestamp NULL, locationlist varchar(256) NULL, meeting varchar(256) NULL, membership varchar(256) NULL, "name" varchar(256) NULL, oparlsince timestamp NULL, organization varchar(256) NULL, paper varchar(256) NULL, person varchar(256) NULL, shortname varchar(256) NULL, website varchar(256) NULL, "systemSid" int8 NULL, CONSTRAINT "Body_pkey" PRIMARY KEY (sid), CONSTRAINT "Body_systemSid_fkey" FOREIGN KEY ("systemSid") REFERENCES public."System"(sid));
CREATE INDEX "ix_Body_id" ON public."Body" USING btree (id);
CREATE UNIQUE INDEX "ix_Body_oparlId" ON public."Body" USING btree ("oparlId");
CREATE INDEX "ix_Body_oparlKey" ON public."Body" USING btree ("oparlKey");
CREATE INDEX "ix_Body_systemSid" ON public."Body" USING btree ("systemSid");


-- public."File__meeting__Meeting" definition

-- Drop table

-- DROP TABLE public."File__meeting__Meeting";

CREATE TABLE public."File__meeting__Meeting" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "File__meeting__Meeting_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "File__meeting__Meeting_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."File"(sid), CONSTRAINT "File__meeting__Meeting_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Meeting"(sid));


-- public."LegislativeTerm" definition

-- Drop table

-- DROP TABLE public."LegislativeTerm";

CREATE TABLE public."LegislativeTerm" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, "name" varchar(256) NULL, startdate timestamp NULL, "bodySid" int8 NULL, CONSTRAINT "LegislativeTerm_pkey" PRIMARY KEY (sid), CONSTRAINT "LegislativeTerm_bodySid_fkey" FOREIGN KEY ("bodySid") REFERENCES public."Body"(sid));
CREATE INDEX "ix_LegislativeTerm_bodySid" ON public."LegislativeTerm" USING btree ("bodySid");
CREATE INDEX "ix_LegislativeTerm_id" ON public."LegislativeTerm" USING btree (id);
CREATE UNIQUE INDEX "ix_LegislativeTerm_oparlId" ON public."LegislativeTerm" USING btree ("oparlId");
CREATE INDEX "ix_LegislativeTerm_oparlKey" ON public."LegislativeTerm" USING btree ("oparlKey");


-- public."Meeting__auxiliaryFile__File" definition

-- Drop table

-- DROP TABLE public."Meeting__auxiliaryFile__File";

CREATE TABLE public."Meeting__auxiliaryFile__File" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Meeting__auxiliaryFile__File_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Meeting__auxiliaryFile__File_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Meeting"(sid), CONSTRAINT "Meeting__auxiliaryFile__File_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."File"(sid));


-- public."Organization" definition

-- Drop table

-- DROP TABLE public."Organization";

CREATE TABLE public."Organization" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, classification varchar(256) NULL, enddate timestamp NULL, meeting varchar(256) NULL, "name" varchar(256) NULL, shortname varchar(256) NULL, startdate timestamp NULL, "bodySid" int8 NULL, CONSTRAINT "Organization_pkey" PRIMARY KEY (sid), CONSTRAINT "Organization_bodySid_fkey" FOREIGN KEY ("bodySid") REFERENCES public."Body"(sid));
CREATE INDEX "ix_Organization_bodySid" ON public."Organization" USING btree ("bodySid");
CREATE INDEX "ix_Organization_id" ON public."Organization" USING btree (id);
CREATE UNIQUE INDEX "ix_Organization_oparlId" ON public."Organization" USING btree ("oparlId");
CREATE INDEX "ix_Organization_oparlKey" ON public."Organization" USING btree ("oparlKey");


-- public."Paper" definition

-- Drop table

-- DROP TABLE public."Paper";

CREATE TABLE public."Paper" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, "date" timestamp NULL, "name" varchar(256) NULL, papertype varchar(256) NULL, reference varchar(256) NULL, "bodySid" int8 NULL, CONSTRAINT "Paper_pkey" PRIMARY KEY (sid), CONSTRAINT "Paper_bodySid_fkey" FOREIGN KEY ("bodySid") REFERENCES public."Body"(sid));
CREATE INDEX "ix_Paper_bodySid" ON public."Paper" USING btree ("bodySid");
CREATE INDEX "ix_Paper_id" ON public."Paper" USING btree (id);
CREATE UNIQUE INDEX "ix_Paper_oparlId" ON public."Paper" USING btree ("oparlId");
CREATE INDEX "ix_Paper_oparlKey" ON public."Paper" USING btree ("oparlKey");


-- public."Paper__auxiliaryFile__File" definition

-- Drop table

-- DROP TABLE public."Paper__auxiliaryFile__File";

CREATE TABLE public."Paper__auxiliaryFile__File" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Paper__auxiliaryFile__File_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Paper__auxiliaryFile__File_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Paper"(sid), CONSTRAINT "Paper__auxiliaryFile__File_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."File"(sid));


-- public."Paper__location__Location" definition

-- Drop table

-- DROP TABLE public."Paper__location__Location";

CREATE TABLE public."Paper__location__Location" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Paper__location__Location_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Paper__location__Location_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Paper"(sid), CONSTRAINT "Paper__location__Location_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Location"(sid));


-- public."Paper__subordinatedPaper__Paper" definition

-- Drop table

-- DROP TABLE public."Paper__subordinatedPaper__Paper";

CREATE TABLE public."Paper__subordinatedPaper__Paper" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Paper__subordinatedPaper__Paper_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Paper__subordinatedPaper__Paper_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Paper"(sid), CONSTRAINT "Paper__subordinatedPaper__Paper_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Paper"(sid));


-- public."Paper__superordinatedPaper__Paper" definition

-- Drop table

-- DROP TABLE public."Paper__superordinatedPaper__Paper";

CREATE TABLE public."Paper__superordinatedPaper__Paper" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Paper__superordinatedPaper__Paper_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Paper__superordinatedPaper__Paper_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Paper"(sid), CONSTRAINT "Paper__superordinatedPaper__Paper_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Paper"(sid));


-- public."Paper__underDirectionOf__Organization" definition

-- Drop table

-- DROP TABLE public."Paper__underDirectionOf__Organization";

CREATE TABLE public."Paper__underDirectionOf__Organization" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Paper__underDirectionOf__Organization_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Paper__underDirectionOf__Organization_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Paper"(sid), CONSTRAINT "Paper__underDirectionOf__Organization_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Organization"(sid));


-- public."Person" definition

-- Drop table

-- DROP TABLE public."Person";

CREATE TABLE public."Person" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, affix varchar(256) NULL, familyname varchar(256) NULL, formofaddress varchar(256) NULL, gender varchar(256) NULL, givenname varchar(256) NULL, "name" varchar(256) NULL, web varchar(256) NULL, "bodySid" int8 NULL, "locationSid" int8 NULL, CONSTRAINT "Person_pkey" PRIMARY KEY (sid), CONSTRAINT "Person_bodySid_fkey" FOREIGN KEY ("bodySid") REFERENCES public."Body"(sid), CONSTRAINT "Person_locationSid_fkey" FOREIGN KEY ("locationSid") REFERENCES public."Location"(sid));
CREATE INDEX "ix_Person_bodySid" ON public."Person" USING btree ("bodySid");
CREATE INDEX "ix_Person_id" ON public."Person" USING btree (id);
CREATE INDEX "ix_Person_locationSid" ON public."Person" USING btree ("locationSid");
CREATE UNIQUE INDEX "ix_Person_oparlId" ON public."Person" USING btree ("oparlId");
CREATE INDEX "ix_Person_oparlKey" ON public."Person" USING btree ("oparlKey");


-- public.concepts definition

-- Drop table

-- DROP TABLE public.concepts;

CREATE TABLE public.concepts ( id bigserial NOT NULL, scheme_uri varchar(500) NULL, uri varchar(500) NULL, pref_label varchar(255) NOT NULL, alt_labels jsonb NULL, definition text NULL, broader_concept_id int8 NULL, narrower_concepts jsonb NULL, related_concepts jsonb NULL, in_scheme bool DEFAULT true NULL, deprecated bool DEFAULT false NULL, created_at timestamp DEFAULT now() NULL, CONSTRAINT concepts_pkey PRIMARY KEY (id), CONSTRAINT concepts_uri_key UNIQUE (uri), CONSTRAINT concepts_broader_concept_id_fkey FOREIGN KEY (broader_concept_id) REFERENCES public.concepts(id), CONSTRAINT concepts_scheme_uri_fkey FOREIGN KEY (scheme_uri) REFERENCES public.concept_schemes(uri));


-- public."Body__legislativeTerm__LegislativeTerm" definition

-- Drop table

-- DROP TABLE public."Body__legislativeTerm__LegislativeTerm";

CREATE TABLE public."Body__legislativeTerm__LegislativeTerm" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Body__legislativeTerm__LegislativeTerm_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Body__legislativeTerm__LegislativeTerm_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Body"(sid), CONSTRAINT "Body__legislativeTerm__LegislativeTerm_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."LegislativeTerm"(sid));


-- public."File__paper__Paper" definition

-- Drop table

-- DROP TABLE public."File__paper__Paper";

CREATE TABLE public."File__paper__Paper" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "File__paper__Paper_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "File__paper__Paper_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."File"(sid), CONSTRAINT "File__paper__Paper_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Paper"(sid));


-- public."Meeting__organization__Organization" definition

-- Drop table

-- DROP TABLE public."Meeting__organization__Organization";

CREATE TABLE public."Meeting__organization__Organization" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Meeting__organization__Organization_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Meeting__organization__Organization_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Meeting"(sid), CONSTRAINT "Meeting__organization__Organization_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Organization"(sid));


-- public."Membership" definition

-- Drop table

-- DROP TABLE public."Membership";

CREATE TABLE public."Membership" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, enddate timestamp NULL, "role" varchar(256) NULL, startdate timestamp NULL, votingright bool NULL, "organizationSid" int8 NULL, "personSid" int8 NULL, CONSTRAINT "Membership_pkey" PRIMARY KEY (sid), CONSTRAINT "Membership_organizationSid_fkey" FOREIGN KEY ("organizationSid") REFERENCES public."Organization"(sid), CONSTRAINT "Membership_personSid_fkey" FOREIGN KEY ("personSid") REFERENCES public."Person"(sid));
CREATE INDEX "ix_Membership_id" ON public."Membership" USING btree (id);
CREATE UNIQUE INDEX "ix_Membership_oparlId" ON public."Membership" USING btree ("oparlId");
CREATE INDEX "ix_Membership_oparlKey" ON public."Membership" USING btree ("oparlKey");
CREATE INDEX "ix_Membership_organizationSid" ON public."Membership" USING btree ("organizationSid");
CREATE INDEX "ix_Membership_personSid" ON public."Membership" USING btree ("personSid");


-- public."Organization__membership__Membership" definition

-- Drop table

-- DROP TABLE public."Organization__membership__Membership";

CREATE TABLE public."Organization__membership__Membership" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Organization__membership__Membership_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Organization__membership__Membership_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Organization"(sid), CONSTRAINT "Organization__membership__Membership_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Membership"(sid));


-- public."Person__membership__Membership" definition

-- Drop table

-- DROP TABLE public."Person__membership__Membership";

CREATE TABLE public."Person__membership__Membership" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Person__membership__Membership_pkey" PRIMARY KEY ("srcSid", "tgtSid"), CONSTRAINT "Person__membership__Membership_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Person"(sid), CONSTRAINT "Person__membership__Membership_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Membership"(sid));


-- public."AgendaItem" definition

-- Drop table

-- DROP TABLE public."AgendaItem";

CREATE TABLE public."AgendaItem" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, end_date timestamp NULL, "name" varchar(256) NULL, "number" varchar(256) NULL, order_col int8 NULL, public bool NULL, "result" varchar(256) NULL, start_date timestamp NULL, "consultationSid" int8 NULL, "meetingSid" int8 NULL, CONSTRAINT "AgendaItem_pkey" PRIMARY KEY (sid));
CREATE INDEX "ix_AgendaItem_consultationSid" ON public."AgendaItem" USING btree ("consultationSid");
CREATE INDEX "ix_AgendaItem_id" ON public."AgendaItem" USING btree (id);
CREATE INDEX "ix_AgendaItem_meetingSid" ON public."AgendaItem" USING btree ("meetingSid");
CREATE UNIQUE INDEX "ix_AgendaItem_oparlId" ON public."AgendaItem" USING btree ("oparlId");
CREATE INDEX "ix_AgendaItem_oparlKey" ON public."AgendaItem" USING btree ("oparlKey");


-- public."AgendaItem__auxiliaryFile__File" definition

-- Drop table

-- DROP TABLE public."AgendaItem__auxiliaryFile__File";

CREATE TABLE public."AgendaItem__auxiliaryFile__File" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "AgendaItem__auxiliaryFile__File_pkey" PRIMARY KEY ("srcSid", "tgtSid"));


-- public."Consultation" definition

-- Drop table

-- DROP TABLE public."Consultation";

CREATE TABLE public."Consultation" ( sid bigserial NOT NULL, id int8 NULL, "oparlKey" varchar(255) NOT NULL, "oparlId" varchar(512) NOT NULL, "type" varchar(255) NOT NULL, created timestamp NULL, modified timestamp NULL, "data" jsonb NOT NULL, authoritative bool NULL, "role" varchar(256) NULL, "agendaItemSid" int8 NULL, "meetingSid" int8 NULL, "paperSid" int8 NULL, CONSTRAINT "Consultation_pkey" PRIMARY KEY (sid));
CREATE INDEX "ix_Consultation_agendaItemSid" ON public."Consultation" USING btree ("agendaItemSid");
CREATE INDEX "ix_Consultation_id" ON public."Consultation" USING btree (id);
CREATE INDEX "ix_Consultation_meetingSid" ON public."Consultation" USING btree ("meetingSid");
CREATE UNIQUE INDEX "ix_Consultation_oparlId" ON public."Consultation" USING btree ("oparlId");
CREATE INDEX "ix_Consultation_oparlKey" ON public."Consultation" USING btree ("oparlKey");
CREATE INDEX "ix_Consultation_paperSid" ON public."Consultation" USING btree ("paperSid");


-- public."Consultation__organization__Organization" definition

-- Drop table

-- DROP TABLE public."Consultation__organization__Organization";

CREATE TABLE public."Consultation__organization__Organization" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Consultation__organization__Organization_pkey" PRIMARY KEY ("srcSid", "tgtSid"));


-- public."Meeting__agendaItem__AgendaItem" definition

-- Drop table

-- DROP TABLE public."Meeting__agendaItem__AgendaItem";

CREATE TABLE public."Meeting__agendaItem__AgendaItem" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Meeting__agendaItem__AgendaItem_pkey" PRIMARY KEY ("srcSid", "tgtSid"));


-- public."Paper__consultation__Consultation" definition

-- Drop table

-- DROP TABLE public."Paper__consultation__Consultation";

CREATE TABLE public."Paper__consultation__Consultation" ( "srcSid" int8 NOT NULL, "tgtSid" int8 NOT NULL, CONSTRAINT "Paper__consultation__Consultation_pkey" PRIMARY KEY ("srcSid", "tgtSid"));


-- public."AgendaItem" foreign keys

ALTER TABLE public."AgendaItem" ADD CONSTRAINT "AgendaItem_consultationSid_fkey" FOREIGN KEY ("consultationSid") REFERENCES public."Consultation"(sid);
ALTER TABLE public."AgendaItem" ADD CONSTRAINT "AgendaItem_meetingSid_fkey" FOREIGN KEY ("meetingSid") REFERENCES public."Meeting"(sid);


-- public."AgendaItem__auxiliaryFile__File" foreign keys

ALTER TABLE public."AgendaItem__auxiliaryFile__File" ADD CONSTRAINT "AgendaItem__auxiliaryFile__File_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."AgendaItem"(sid);
ALTER TABLE public."AgendaItem__auxiliaryFile__File" ADD CONSTRAINT "AgendaItem__auxiliaryFile__File_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."File"(sid);


-- public."Consultation" foreign keys

ALTER TABLE public."Consultation" ADD CONSTRAINT "Consultation_agendaItemSid_fkey" FOREIGN KEY ("agendaItemSid") REFERENCES public."AgendaItem"(sid);
ALTER TABLE public."Consultation" ADD CONSTRAINT "Consultation_meetingSid_fkey" FOREIGN KEY ("meetingSid") REFERENCES public."Meeting"(sid);
ALTER TABLE public."Consultation" ADD CONSTRAINT "Consultation_paperSid_fkey" FOREIGN KEY ("paperSid") REFERENCES public."Paper"(sid);


-- public."Consultation__organization__Organization" foreign keys

ALTER TABLE public."Consultation__organization__Organization" ADD CONSTRAINT "Consultation__organization__Organization_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Consultation"(sid);
ALTER TABLE public."Consultation__organization__Organization" ADD CONSTRAINT "Consultation__organization__Organization_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Organization"(sid);


-- public."Meeting__agendaItem__AgendaItem" foreign keys

ALTER TABLE public."Meeting__agendaItem__AgendaItem" ADD CONSTRAINT "Meeting__agendaItem__AgendaItem_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Meeting"(sid);
ALTER TABLE public."Meeting__agendaItem__AgendaItem" ADD CONSTRAINT "Meeting__agendaItem__AgendaItem_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."AgendaItem"(sid);


-- public."Paper__consultation__Consultation" foreign keys

ALTER TABLE public."Paper__consultation__Consultation" ADD CONSTRAINT "Paper__consultation__Consultation_srcSid_fkey" FOREIGN KEY ("srcSid") REFERENCES public."Paper"(sid);
ALTER TABLE public."Paper__consultation__Consultation" ADD CONSTRAINT "Paper__consultation__Consultation_tgtSid_fkey" FOREIGN KEY ("tgtSid") REFERENCES public."Consultation"(sid);


-- public.mv_paper_enriched source

CREATE MATERIALIZED VIEW public.mv_paper_enriched
TABLESPACE pg_default
AS SELECT p.id AS paper_id,
    p.created,
    p.name,
    ec.concept_uri AS topic_uri,
    c.pref_label AS topic_label,
    ec.relation_type,
    st.predicate_uri AS additional_predicate,
    st.object_value AS predicate_value
   FROM "Paper" p
     LEFT JOIN entity_concepts ec ON ec.entity_type::text = 'paper'::text AND ec.entity_id = p.id
     LEFT JOIN concepts c ON c.uri::text = ec.concept_uri::text
     LEFT JOIN semantic_triples st ON st.subject_entity_type::text = 'paper'::text AND st.subject_entity_id = p.id
WITH DATA;


-- public.mv_person_roles source

CREATE MATERIALIZED VIEW public.mv_person_roles
TABLESPACE pg_default
AS SELECT per.id AS person_id,
    per.name,
    ec.concept_uri AS role_uri,
    c.pref_label AS role_label,
    ec2.concept_uri AS organization_uri,
    c2.pref_label AS organization_label
   FROM "Person" per
     LEFT JOIN entity_concepts ec ON ec.entity_type::text = 'person'::text AND ec.entity_id = per.id AND ec.relation_type::text = 'ris:role'::text
     LEFT JOIN concepts c ON c.uri::text = ec.concept_uri::text
     LEFT JOIN entity_concepts ec2 ON ec2.entity_type::text = 'person'::text AND ec2.entity_id = per.id AND ec2.relation_type::text = 'org:memberOf'::text
     LEFT JOIN concepts c2 ON c2.uri::text = ec2.concept_uri::text
WITH DATA;



-- DROP FUNCTION public.array_to_halfvec(_numeric, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_halfvec(numeric[], integer, boolean)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_halfvec$function$
;

-- DROP FUNCTION public.array_to_halfvec(_float8, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_halfvec(double precision[], integer, boolean)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_halfvec$function$
;

-- DROP FUNCTION public.array_to_halfvec(_float4, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_halfvec(real[], integer, boolean)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_halfvec$function$
;

-- DROP FUNCTION public.array_to_halfvec(_int4, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_halfvec(integer[], integer, boolean)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_halfvec$function$
;

-- DROP FUNCTION public.array_to_sparsevec(_numeric, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_sparsevec(numeric[], integer, boolean)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_sparsevec$function$
;

-- DROP FUNCTION public.array_to_sparsevec(_float4, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_sparsevec(real[], integer, boolean)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_sparsevec$function$
;

-- DROP FUNCTION public.array_to_sparsevec(_int4, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_sparsevec(integer[], integer, boolean)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_sparsevec$function$
;

-- DROP FUNCTION public.array_to_sparsevec(_float8, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_sparsevec(double precision[], integer, boolean)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_sparsevec$function$
;

-- DROP FUNCTION public.array_to_vector(_float8, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_vector(double precision[], integer, boolean)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_vector$function$
;

-- DROP FUNCTION public.array_to_vector(_float4, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_vector(real[], integer, boolean)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_vector$function$
;

-- DROP FUNCTION public.array_to_vector(_int4, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_vector(integer[], integer, boolean)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_vector$function$
;

-- DROP FUNCTION public.array_to_vector(_numeric, int4, bool);

CREATE OR REPLACE FUNCTION public.array_to_vector(numeric[], integer, boolean)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$array_to_vector$function$
;

-- DROP AGGREGATE public.avg(vector);

-- Aggregate function public.avg(vector)
-- FEHLER: es gibt mehrere Funktionen namens »public.avg«;

-- DROP AGGREGATE public.avg(halfvec);

-- Aggregate function public.avg(halfvec)
-- FEHLER: es gibt mehrere Funktionen namens »public.avg«;

-- DROP FUNCTION public.binary_quantize(halfvec);

CREATE OR REPLACE FUNCTION public.binary_quantize(halfvec)
 RETURNS bit
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_binary_quantize$function$
;

-- DROP FUNCTION public.binary_quantize(vector);

CREATE OR REPLACE FUNCTION public.binary_quantize(vector)
 RETURNS bit
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$binary_quantize$function$
;

-- DROP FUNCTION public.cosine_distance(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.cosine_distance(halfvec, halfvec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_cosine_distance$function$
;

-- DROP FUNCTION public.cosine_distance(vector, vector);

CREATE OR REPLACE FUNCTION public.cosine_distance(vector, vector)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$cosine_distance$function$
;

-- DROP FUNCTION public.cosine_distance(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.cosine_distance(sparsevec, sparsevec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_cosine_distance$function$
;

-- DROP FUNCTION public.halfvec(halfvec, int4, bool);

CREATE OR REPLACE FUNCTION public.halfvec(halfvec, integer, boolean)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec$function$
;

-- DROP FUNCTION public.halfvec_accum(_float8, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_accum(double precision[], halfvec)
 RETURNS double precision[]
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_accum$function$
;

-- DROP FUNCTION public.halfvec_add(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_add(halfvec, halfvec)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_add$function$
;

-- DROP FUNCTION public.halfvec_avg(_float8);

CREATE OR REPLACE FUNCTION public.halfvec_avg(double precision[])
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_avg$function$
;

-- DROP FUNCTION public.halfvec_cmp(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_cmp(halfvec, halfvec)
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_cmp$function$
;

-- DROP FUNCTION public.halfvec_combine(_float8, _float8);

CREATE OR REPLACE FUNCTION public.halfvec_combine(double precision[], double precision[])
 RETURNS double precision[]
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_combine$function$
;

-- DROP FUNCTION public.halfvec_concat(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_concat(halfvec, halfvec)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_concat$function$
;

-- DROP FUNCTION public.halfvec_eq(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_eq(halfvec, halfvec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_eq$function$
;

-- DROP FUNCTION public.halfvec_ge(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_ge(halfvec, halfvec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_ge$function$
;

-- DROP FUNCTION public.halfvec_gt(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_gt(halfvec, halfvec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_gt$function$
;

-- DROP FUNCTION public.halfvec_in(cstring, oid, int4);

CREATE OR REPLACE FUNCTION public.halfvec_in(cstring, oid, integer)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_in$function$
;

-- DROP FUNCTION public.halfvec_l2_squared_distance(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_l2_squared_distance(halfvec, halfvec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_l2_squared_distance$function$
;

-- DROP FUNCTION public.halfvec_le(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_le(halfvec, halfvec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_le$function$
;

-- DROP FUNCTION public.halfvec_lt(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_lt(halfvec, halfvec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_lt$function$
;

-- DROP FUNCTION public.halfvec_mul(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_mul(halfvec, halfvec)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_mul$function$
;

-- DROP FUNCTION public.halfvec_ne(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_ne(halfvec, halfvec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_ne$function$
;

-- DROP FUNCTION public.halfvec_negative_inner_product(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_negative_inner_product(halfvec, halfvec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_negative_inner_product$function$
;

-- DROP FUNCTION public.halfvec_out(halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_out(halfvec)
 RETURNS cstring
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_out$function$
;

-- DROP FUNCTION public.halfvec_recv(internal, oid, int4);

CREATE OR REPLACE FUNCTION public.halfvec_recv(internal, oid, integer)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_recv$function$
;

-- DROP FUNCTION public.halfvec_send(halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_send(halfvec)
 RETURNS bytea
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_send$function$
;

-- DROP FUNCTION public.halfvec_spherical_distance(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_spherical_distance(halfvec, halfvec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_spherical_distance$function$
;

-- DROP FUNCTION public.halfvec_sub(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.halfvec_sub(halfvec, halfvec)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_sub$function$
;

-- DROP FUNCTION public.halfvec_to_float4(halfvec, int4, bool);

CREATE OR REPLACE FUNCTION public.halfvec_to_float4(halfvec, integer, boolean)
 RETURNS real[]
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_to_float4$function$
;

-- DROP FUNCTION public.halfvec_to_sparsevec(halfvec, int4, bool);

CREATE OR REPLACE FUNCTION public.halfvec_to_sparsevec(halfvec, integer, boolean)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_to_sparsevec$function$
;

-- DROP FUNCTION public.halfvec_to_vector(halfvec, int4, bool);

CREATE OR REPLACE FUNCTION public.halfvec_to_vector(halfvec, integer, boolean)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_to_vector$function$
;

-- DROP FUNCTION public.halfvec_typmod_in(_cstring);

CREATE OR REPLACE FUNCTION public.halfvec_typmod_in(cstring[])
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_typmod_in$function$
;

-- DROP FUNCTION public.hamming_distance(bit, bit);

CREATE OR REPLACE FUNCTION public.hamming_distance(bit, bit)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$hamming_distance$function$
;

-- DROP FUNCTION public.hnsw_bit_support(internal);

CREATE OR REPLACE FUNCTION public.hnsw_bit_support(internal)
 RETURNS internal
 LANGUAGE c
AS '$libdir/vector', $function$hnsw_bit_support$function$
;

-- DROP FUNCTION public.hnsw_halfvec_support(internal);

CREATE OR REPLACE FUNCTION public.hnsw_halfvec_support(internal)
 RETURNS internal
 LANGUAGE c
AS '$libdir/vector', $function$hnsw_halfvec_support$function$
;

-- DROP FUNCTION public.hnsw_sparsevec_support(internal);

CREATE OR REPLACE FUNCTION public.hnsw_sparsevec_support(internal)
 RETURNS internal
 LANGUAGE c
AS '$libdir/vector', $function$hnsw_sparsevec_support$function$
;

-- DROP FUNCTION public.hnswhandler(internal);

CREATE OR REPLACE FUNCTION public.hnswhandler(internal)
 RETURNS index_am_handler
 LANGUAGE c
AS '$libdir/vector', $function$hnswhandler$function$
;

-- DROP FUNCTION public.inner_product(vector, vector);

CREATE OR REPLACE FUNCTION public.inner_product(vector, vector)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$inner_product$function$
;

-- DROP FUNCTION public.inner_product(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.inner_product(sparsevec, sparsevec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_inner_product$function$
;

-- DROP FUNCTION public.inner_product(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.inner_product(halfvec, halfvec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_inner_product$function$
;

-- DROP FUNCTION public.ivfflat_bit_support(internal);

CREATE OR REPLACE FUNCTION public.ivfflat_bit_support(internal)
 RETURNS internal
 LANGUAGE c
AS '$libdir/vector', $function$ivfflat_bit_support$function$
;

-- DROP FUNCTION public.ivfflat_halfvec_support(internal);

CREATE OR REPLACE FUNCTION public.ivfflat_halfvec_support(internal)
 RETURNS internal
 LANGUAGE c
AS '$libdir/vector', $function$ivfflat_halfvec_support$function$
;

-- DROP FUNCTION public.ivfflathandler(internal);

CREATE OR REPLACE FUNCTION public.ivfflathandler(internal)
 RETURNS index_am_handler
 LANGUAGE c
AS '$libdir/vector', $function$ivfflathandler$function$
;

-- DROP FUNCTION public.jaccard_distance(bit, bit);

CREATE OR REPLACE FUNCTION public.jaccard_distance(bit, bit)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$jaccard_distance$function$
;

-- DROP FUNCTION public.l1_distance(vector, vector);

CREATE OR REPLACE FUNCTION public.l1_distance(vector, vector)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$l1_distance$function$
;

-- DROP FUNCTION public.l1_distance(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.l1_distance(halfvec, halfvec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_l1_distance$function$
;

-- DROP FUNCTION public.l1_distance(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.l1_distance(sparsevec, sparsevec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_l1_distance$function$
;

-- DROP FUNCTION public.l2_distance(halfvec, halfvec);

CREATE OR REPLACE FUNCTION public.l2_distance(halfvec, halfvec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_l2_distance$function$
;

-- DROP FUNCTION public.l2_distance(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.l2_distance(sparsevec, sparsevec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_l2_distance$function$
;

-- DROP FUNCTION public.l2_distance(vector, vector);

CREATE OR REPLACE FUNCTION public.l2_distance(vector, vector)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$l2_distance$function$
;

-- DROP FUNCTION public.l2_norm(sparsevec);

CREATE OR REPLACE FUNCTION public.l2_norm(sparsevec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_l2_norm$function$
;

-- DROP FUNCTION public.l2_norm(halfvec);

CREATE OR REPLACE FUNCTION public.l2_norm(halfvec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_l2_norm$function$
;

-- DROP FUNCTION public.l2_normalize(halfvec);

CREATE OR REPLACE FUNCTION public.l2_normalize(halfvec)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_l2_normalize$function$
;

-- DROP FUNCTION public.l2_normalize(sparsevec);

CREATE OR REPLACE FUNCTION public.l2_normalize(sparsevec)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_l2_normalize$function$
;

-- DROP FUNCTION public.l2_normalize(vector);

CREATE OR REPLACE FUNCTION public.l2_normalize(vector)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$l2_normalize$function$
;

-- DROP FUNCTION public.sparsevec(sparsevec, int4, bool);

CREATE OR REPLACE FUNCTION public.sparsevec(sparsevec, integer, boolean)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec$function$
;

-- DROP FUNCTION public.sparsevec_cmp(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_cmp(sparsevec, sparsevec)
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_cmp$function$
;

-- DROP FUNCTION public.sparsevec_eq(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_eq(sparsevec, sparsevec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_eq$function$
;

-- DROP FUNCTION public.sparsevec_ge(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_ge(sparsevec, sparsevec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_ge$function$
;

-- DROP FUNCTION public.sparsevec_gt(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_gt(sparsevec, sparsevec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_gt$function$
;

-- DROP FUNCTION public.sparsevec_in(cstring, oid, int4);

CREATE OR REPLACE FUNCTION public.sparsevec_in(cstring, oid, integer)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_in$function$
;

-- DROP FUNCTION public.sparsevec_l2_squared_distance(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_l2_squared_distance(sparsevec, sparsevec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_l2_squared_distance$function$
;

-- DROP FUNCTION public.sparsevec_le(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_le(sparsevec, sparsevec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_le$function$
;

-- DROP FUNCTION public.sparsevec_lt(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_lt(sparsevec, sparsevec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_lt$function$
;

-- DROP FUNCTION public.sparsevec_ne(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_ne(sparsevec, sparsevec)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_ne$function$
;

-- DROP FUNCTION public.sparsevec_negative_inner_product(sparsevec, sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_negative_inner_product(sparsevec, sparsevec)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_negative_inner_product$function$
;

-- DROP FUNCTION public.sparsevec_out(sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_out(sparsevec)
 RETURNS cstring
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_out$function$
;

-- DROP FUNCTION public.sparsevec_recv(internal, oid, int4);

CREATE OR REPLACE FUNCTION public.sparsevec_recv(internal, oid, integer)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_recv$function$
;

-- DROP FUNCTION public.sparsevec_send(sparsevec);

CREATE OR REPLACE FUNCTION public.sparsevec_send(sparsevec)
 RETURNS bytea
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_send$function$
;

-- DROP FUNCTION public.sparsevec_to_halfvec(sparsevec, int4, bool);

CREATE OR REPLACE FUNCTION public.sparsevec_to_halfvec(sparsevec, integer, boolean)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_to_halfvec$function$
;

-- DROP FUNCTION public.sparsevec_to_vector(sparsevec, int4, bool);

CREATE OR REPLACE FUNCTION public.sparsevec_to_vector(sparsevec, integer, boolean)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_to_vector$function$
;

-- DROP FUNCTION public.sparsevec_typmod_in(_cstring);

CREATE OR REPLACE FUNCTION public.sparsevec_typmod_in(cstring[])
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$sparsevec_typmod_in$function$
;

-- DROP FUNCTION public.subvector(vector, int4, int4);

CREATE OR REPLACE FUNCTION public.subvector(vector, integer, integer)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$subvector$function$
;

-- DROP FUNCTION public.subvector(halfvec, int4, int4);

CREATE OR REPLACE FUNCTION public.subvector(halfvec, integer, integer)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_subvector$function$
;

-- DROP AGGREGATE public.sum(vector);

-- Aggregate function public.sum(vector)
-- FEHLER: es gibt mehrere Funktionen namens »public.sum«;

-- DROP AGGREGATE public.sum(halfvec);

-- Aggregate function public.sum(halfvec)
-- FEHLER: es gibt mehrere Funktionen namens »public.sum«;

-- DROP FUNCTION public.vector(vector, int4, bool);

CREATE OR REPLACE FUNCTION public.vector(vector, integer, boolean)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector$function$
;

-- DROP FUNCTION public.vector_accum(_float8, vector);

CREATE OR REPLACE FUNCTION public.vector_accum(double precision[], vector)
 RETURNS double precision[]
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_accum$function$
;

-- DROP FUNCTION public.vector_add(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_add(vector, vector)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_add$function$
;

-- DROP FUNCTION public.vector_avg(_float8);

CREATE OR REPLACE FUNCTION public.vector_avg(double precision[])
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_avg$function$
;

-- DROP FUNCTION public.vector_cmp(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_cmp(vector, vector)
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_cmp$function$
;

-- DROP FUNCTION public.vector_combine(_float8, _float8);

CREATE OR REPLACE FUNCTION public.vector_combine(double precision[], double precision[])
 RETURNS double precision[]
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_combine$function$
;

-- DROP FUNCTION public.vector_concat(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_concat(vector, vector)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_concat$function$
;

-- DROP FUNCTION public.vector_dims(halfvec);

CREATE OR REPLACE FUNCTION public.vector_dims(halfvec)
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$halfvec_vector_dims$function$
;

-- DROP FUNCTION public.vector_dims(vector);

CREATE OR REPLACE FUNCTION public.vector_dims(vector)
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_dims$function$
;

-- DROP FUNCTION public.vector_eq(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_eq(vector, vector)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_eq$function$
;

-- DROP FUNCTION public.vector_ge(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_ge(vector, vector)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_ge$function$
;

-- DROP FUNCTION public.vector_gt(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_gt(vector, vector)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_gt$function$
;

-- DROP FUNCTION public.vector_in(cstring, oid, int4);

CREATE OR REPLACE FUNCTION public.vector_in(cstring, oid, integer)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_in$function$
;

-- DROP FUNCTION public.vector_l2_squared_distance(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_l2_squared_distance(vector, vector)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_l2_squared_distance$function$
;

-- DROP FUNCTION public.vector_le(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_le(vector, vector)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_le$function$
;

-- DROP FUNCTION public.vector_lt(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_lt(vector, vector)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_lt$function$
;

-- DROP FUNCTION public.vector_mul(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_mul(vector, vector)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_mul$function$
;

-- DROP FUNCTION public.vector_ne(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_ne(vector, vector)
 RETURNS boolean
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_ne$function$
;

-- DROP FUNCTION public.vector_negative_inner_product(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_negative_inner_product(vector, vector)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_negative_inner_product$function$
;

-- DROP FUNCTION public.vector_norm(vector);

CREATE OR REPLACE FUNCTION public.vector_norm(vector)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_norm$function$
;

-- DROP FUNCTION public.vector_out(vector);

CREATE OR REPLACE FUNCTION public.vector_out(vector)
 RETURNS cstring
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_out$function$
;

-- DROP FUNCTION public.vector_recv(internal, oid, int4);

CREATE OR REPLACE FUNCTION public.vector_recv(internal, oid, integer)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_recv$function$
;

-- DROP FUNCTION public.vector_send(vector);

CREATE OR REPLACE FUNCTION public.vector_send(vector)
 RETURNS bytea
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_send$function$
;

-- DROP FUNCTION public.vector_spherical_distance(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_spherical_distance(vector, vector)
 RETURNS double precision
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_spherical_distance$function$
;

-- DROP FUNCTION public.vector_sub(vector, vector);

CREATE OR REPLACE FUNCTION public.vector_sub(vector, vector)
 RETURNS vector
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_sub$function$
;

-- DROP FUNCTION public.vector_to_float4(vector, int4, bool);

CREATE OR REPLACE FUNCTION public.vector_to_float4(vector, integer, boolean)
 RETURNS real[]
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_to_float4$function$
;

-- DROP FUNCTION public.vector_to_halfvec(vector, int4, bool);

CREATE OR REPLACE FUNCTION public.vector_to_halfvec(vector, integer, boolean)
 RETURNS halfvec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_to_halfvec$function$
;

-- DROP FUNCTION public.vector_to_sparsevec(vector, int4, bool);

CREATE OR REPLACE FUNCTION public.vector_to_sparsevec(vector, integer, boolean)
 RETURNS sparsevec
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_to_sparsevec$function$
;

-- DROP FUNCTION public.vector_typmod_in(_cstring);

CREATE OR REPLACE FUNCTION public.vector_typmod_in(cstring[])
 RETURNS integer
 LANGUAGE c
 IMMUTABLE PARALLEL SAFE STRICT
AS '$libdir/vector', $function$vector_typmod_in$function$
;
