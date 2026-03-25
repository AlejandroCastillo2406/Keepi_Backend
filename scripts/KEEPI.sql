--
-- PostgreSQL database dump
--

-- Dumped from database version 16.8
-- Dumped by pg_dump version 16.3

-- Started on 2026-03-25 00:34:26

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 5 (class 2615 OID 50345)
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA public;


ALTER SCHEMA public OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 216 (class 1259 OID 50537)
-- Name: archivos_temporales; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.archivos_temporales (
    id integer NOT NULL,
    nombre_archivo character varying(255),
    ruta_archivo text,
    token_acceso character varying(255),
    fecha_expiracion timestamp without time zone,
    usuario_id uuid
);


ALTER TABLE public.archivos_temporales OWNER TO postgres;

--
-- TOC entry 215 (class 1259 OID 50536)
-- Name: archivos_temporales_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.archivos_temporales_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.archivos_temporales_id_seq OWNER TO postgres;

--
-- TOC entry 4428 (class 0 OID 0)
-- Dependencies: 215
-- Name: archivos_temporales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.archivos_temporales_id_seq OWNED BY public.archivos_temporales.id;


--
-- TOC entry 220 (class 1259 OID 50785)
-- Name: documents; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    category character varying(100) NOT NULL,
    description text,
    file_url text,
    file_name character varying(255),
    file_size integer,
    file_type character varying(100),
    expiry_date timestamp with time zone,
    document_metadata jsonb DEFAULT '{}'::jsonb,
    tags text[] DEFAULT '{}'::text[],
    drive_file_id character varying(255),
    cloud_provider character varying(50),
    s3_key character varying(500),
    extracted_text text,
    ai_analysis jsonb DEFAULT '{}'::jsonb,
    folder_id uuid,
    is_archived boolean DEFAULT false NOT NULL,
    is_favorite boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.documents OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 50765)
-- Name: folders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.folders (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    category character varying(100) NOT NULL,
    parent_folder_id uuid,
    drive_folder_id character varying(255) NOT NULL,
    drive_parent_id character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.folders OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 50810)
-- Name: notifications; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.notifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    document_id uuid,
    title character varying(255) NOT NULL,
    message text NOT NULL,
    type character varying(50) DEFAULT 'info'::character varying NOT NULL,
    target_date date,
    payload jsonb DEFAULT '{}'::jsonb,
    read boolean DEFAULT false NOT NULL,
    read_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.notifications OWNER TO postgres;

--
-- TOC entry 222 (class 1259 OID 50832)
-- Name: notifications_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.notifications_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    document_id uuid NOT NULL,
    notification_type character varying(50) NOT NULL,
    target_date date NOT NULL,
    days_before integer,
    email_to character varying(255),
    ses_message_id character varying(255),
    sent_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.notifications_logs OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 50852)
-- Name: oauth_credentials; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.oauth_credentials (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    provider character varying(50) DEFAULT 'google'::character varying NOT NULL,
    access_token text NOT NULL,
    refresh_token text,
    token_uri character varying(255) DEFAULT 'https://oauth2.googleapis.com/token'::character varying NOT NULL,
    client_id character varying(255),
    client_secret character varying(255),
    scopes jsonb DEFAULT '[]'::jsonb,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.oauth_credentials OWNER TO postgres;

--
-- TOC entry 224 (class 1259 OID 50870)
-- Name: plans; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.plans (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    price integer DEFAULT 0 NOT NULL,
    currency character varying(10) DEFAULT 'MXN'::character varying NOT NULL,
    "interval" character varying(50) DEFAULT 'month'::character varying NOT NULL,
    stripe_price_id character varying(255),
    analysis_limit integer DEFAULT 2 NOT NULL,
    features jsonb DEFAULT '[]'::jsonb,
    is_active boolean DEFAULT true NOT NULL,
    recommended boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.plans OWNER TO postgres;

--
-- TOC entry 226 (class 1259 OID 50932)
-- Name: shared_links; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.shared_links (
    id character varying NOT NULL,
    token character varying NOT NULL,
    file_path character varying NOT NULL,
    used boolean,
    expires_at timestamp without time zone NOT NULL,
    created_at timestamp without time zone
);


ALTER TABLE public.shared_links OWNER TO postgres;

--
-- TOC entry 225 (class 1259 OID 50890)
-- Name: subscriptions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.subscriptions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    plan_id uuid,
    stripe_customer_id character varying(255),
    stripe_subscription_id character varying(255),
    stripe_price_id character varying(255),
    status character varying(50) DEFAULT 'inactive'::character varying NOT NULL,
    trial_end timestamp with time zone,
    current_period_start timestamp with time zone,
    current_period_end timestamp with time zone,
    analysis_limit integer DEFAULT 2 NOT NULL,
    analysis_used integer DEFAULT 0 NOT NULL,
    extra_metadata text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    canceled_at timestamp with time zone
);


ALTER TABLE public.subscriptions OWNER TO postgres;

--
-- TOC entry 218 (class 1259 OID 50746)
-- Name: user_configs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_configs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    cloud_provider character varying(50) DEFAULT 'not_configured'::character varying NOT NULL,
    notification_preferences jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.user_configs OWNER TO postgres;

--
-- TOC entry 217 (class 1259 OID 50732)
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    hashed_password character varying(255),
    refresh_token character varying(500),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.users OWNER TO postgres;

--
-- TOC entry 4180 (class 2604 OID 50540)
-- Name: archivos_temporales id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.archivos_temporales ALTER COLUMN id SET DEFAULT nextval('public.archivos_temporales_id_seq'::regclass);


--
-- TOC entry 4231 (class 2606 OID 50544)
-- Name: archivos_temporales archivos_temporales_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.archivos_temporales
    ADD CONSTRAINT archivos_temporales_pkey PRIMARY KEY (id);


--
-- TOC entry 4244 (class 2606 OID 50799)
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- TOC entry 4242 (class 2606 OID 50774)
-- Name: folders folders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_pkey PRIMARY KEY (id);


--
-- TOC entry 4248 (class 2606 OID 50840)
-- Name: notifications_logs notifications_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications_logs
    ADD CONSTRAINT notifications_logs_pkey PRIMARY KEY (id);


--
-- TOC entry 4246 (class 2606 OID 50821)
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- TOC entry 4251 (class 2606 OID 50864)
-- Name: oauth_credentials oauth_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.oauth_credentials
    ADD CONSTRAINT oauth_credentials_pkey PRIMARY KEY (id);


--
-- TOC entry 4254 (class 2606 OID 50888)
-- Name: plans plans_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT plans_code_key UNIQUE (code);


--
-- TOC entry 4256 (class 2606 OID 50886)
-- Name: plans plans_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.plans
    ADD CONSTRAINT plans_pkey PRIMARY KEY (id);


--
-- TOC entry 4264 (class 2606 OID 50938)
-- Name: shared_links shared_links_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shared_links
    ADD CONSTRAINT shared_links_pkey PRIMARY KEY (id);


--
-- TOC entry 4266 (class 2606 OID 50940)
-- Name: shared_links shared_links_token_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shared_links
    ADD CONSTRAINT shared_links_token_key UNIQUE (token);


--
-- TOC entry 4260 (class 2606 OID 50902)
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);


--
-- TOC entry 4262 (class 2606 OID 50904)
-- Name: subscriptions subscriptions_user_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_user_id_key UNIQUE (user_id);


--
-- TOC entry 4238 (class 2606 OID 50757)
-- Name: user_configs user_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_configs
    ADD CONSTRAINT user_configs_pkey PRIMARY KEY (id);


--
-- TOC entry 4240 (class 2606 OID 50759)
-- Name: user_configs user_configs_user_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_configs
    ADD CONSTRAINT user_configs_user_id_key UNIQUE (user_id);


--
-- TOC entry 4234 (class 2606 OID 50744)
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- TOC entry 4236 (class 2606 OID 50742)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 4252 (class 1259 OID 50889)
-- Name: ix_plans_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_plans_code ON public.plans USING btree (code);


--
-- TOC entry 4257 (class 1259 OID 50916)
-- Name: ix_subscriptions_plan_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_subscriptions_plan_id ON public.subscriptions USING btree (plan_id);


--
-- TOC entry 4258 (class 1259 OID 50915)
-- Name: ix_subscriptions_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_subscriptions_user_id ON public.subscriptions USING btree (user_id);


--
-- TOC entry 4232 (class 1259 OID 50745)
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_users_email ON public.users USING btree (email);


--
-- TOC entry 4249 (class 1259 OID 50851)
-- Name: uq_notifications_logs; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX uq_notifications_logs ON public.notifications_logs USING btree (user_id, document_id, notification_type, target_date);


--
-- TOC entry 4270 (class 2606 OID 50805)
-- Name: documents documents_folder_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_folder_id_fkey FOREIGN KEY (folder_id) REFERENCES public.folders(id) ON DELETE SET NULL;


--
-- TOC entry 4271 (class 2606 OID 50800)
-- Name: documents documents_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 4268 (class 2606 OID 50780)
-- Name: folders folders_parent_folder_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_parent_folder_id_fkey FOREIGN KEY (parent_folder_id) REFERENCES public.folders(id) ON DELETE SET NULL;


--
-- TOC entry 4269 (class 2606 OID 50775)
-- Name: folders folders_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.folders
    ADD CONSTRAINT folders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 4272 (class 2606 OID 50827)
-- Name: notifications notifications_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- TOC entry 4274 (class 2606 OID 50846)
-- Name: notifications_logs notifications_logs_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications_logs
    ADD CONSTRAINT notifications_logs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- TOC entry 4275 (class 2606 OID 50841)
-- Name: notifications_logs notifications_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications_logs
    ADD CONSTRAINT notifications_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4273 (class 2606 OID 50822)
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 4276 (class 2606 OID 50865)
-- Name: oauth_credentials oauth_credentials_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.oauth_credentials
    ADD CONSTRAINT oauth_credentials_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 4277 (class 2606 OID 50910)
-- Name: subscriptions subscriptions_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES public.plans(id);


--
-- TOC entry 4278 (class 2606 OID 50905)
-- Name: subscriptions subscriptions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 4267 (class 2606 OID 50760)
-- Name: user_configs user_configs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_configs
    ADD CONSTRAINT user_configs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- TOC entry 4427 (class 0 OID 0)
-- Dependencies: 5
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;


-- Completed on 2026-03-25 00:34:42

--
-- PostgreSQL database dump complete
--

