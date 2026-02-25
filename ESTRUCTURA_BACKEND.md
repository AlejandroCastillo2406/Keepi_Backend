# Estructura del Backend (KIPI)

Arquitectura por capas: una responsabilidad por archivo. Inyección de dependencias para testabilidad.

## Esquema de carpetas

```
app/
├── main.py                    # Entrada FastAPI; registra routers desde app.routes
│
├── core/                      # Lógica central, config global, constantes, seguridad
│   ├── config.py              # Settings (Pydantic), variables de entorno
│   ├── database.py            # Engine, Base, SessionLocal, get_db, DatabaseConfig
│   ├── constants.py           # Constantes de negocio (ej. ANALYSIS_LIMIT_FREE)
│   ├── exceptions.py          # Excepciones de dominio (DriveAuthRequiredException)
│   └── security.py            # JWT: verify_token, get_current_user, create_access_token, etc.
│
├── dto/                       # Data Transfer Objects (validación entrada/salida)
│   ├── document.py            # DocumentCreate, DocumentUpdate, DocumentResponse
│   └── ...
│
├── factories/                 # Generación de instancias para DI
│   └── dependencies.py       # get_db, get_current_user_token, get_document_repository,
│                             # get_document_service, get_subscription_service
│
├── interfaces/                # Contratos para Services y Repositories (testeable)
│   └── repositories/
│       └── document_repository.py   # IDocumentRepository
│
├── models/                    # Solo esquemas SQLAlchemy (entidades BD)
│   ├── user.py, document.py, subscription.py, notification.py, folder.py, ...
│   └── (Los Pydantic/schemas pueden vivir en models o en dto según migración)
│
├── repositories/              # Acceso a datos; solo queries usando Models
│   ├── document_repository.py
│   └── subscription_repository.py
│
├── routes/                    # Definición de endpoints y orquestación de middlewares
│   ├── dependencies.py       # Re-export de factories + get_current_user (para rutas)
│   ├── auth.py, users.py, documents.py, notifications.py, subscriptions.py, ...
│   ├── aws_documents.py, user_config.py, cloud_storage.py
│   └── __init__.py           # Export auth, documents, users, ...
│
└── services/                  # Lógica de aplicación por dominio (subcarpetas por área)
    ├── almacenamiento/        # Drive, S3 y carpetas (almacenamiento en la nube)
    │   ├── drive_service.py   # Google Drive
    │   ├── s3_service.py      # AWS S3
    │   └── folder_service.py # Carpetas por categoría (S3/Drive)
    ├── ocr/                   # Extracción de texto (Textract, etc.)
    │   └── ocr_service.py
    ├── aws/                   # AWS: Textract, Comprehend, Bedrock y análisis IA
    │   ├── aws_service.py     # Textract + Comprehend
    │   ├── bedrock_service.py
    │   ├── comprehend_service.py
    │   └── ai_analysis_service.py  # DocumentAnalysisService (Bedrock + suscripciones)
    ├── stripe/                # Integración Stripe
    │   ├── stripe_config.py, stripe_customer_service.py
    │   ├── stripe_checkout_service.py, stripe_subscription_service.py
    ├── subscription/          # Orquestación suscripciones + webhooks
    │   ├── subscription_service.py, webhook_handlers.py
    ├── subscription_service.py      # Re-export
    ├── subscription_webhook_handlers.py  # Re-export
    ├── document_service.py
    ├── user_service.py, notification_service.py, user_config_service.py
    ├── oauth_service.py, oauth_credentials_service.py
    └── ...
```

## Reglas

- **Core:** Configuración, BD, constantes y seguridad. Sin reglas de negocio por dominio.
- **DTO:** Validación de entrada/salida (Pydantic). Un archivo por entidad o grupo coherente.
- **Factories:** Solo donde aporta valor (get_db, get_*_service para DI). No relleno.
- **Interfaces:** Contratos para repositorios/servicios cuando se quiera mockear en tests.
- **Models:** Solo definiciones SQLAlchemy. Sin Pydantic en el mismo archivo (migrar a dto si aplica).
- **Repositories:** Todas las queries aquí; usan solo Models. Sin lógica de negocio.
- **Routes:** Endpoints y middlewares; usan DTOs, Core (auth) y Services vía Depends.
- **Services:** Por dominio (stripe, subscription, document, user, …). Cada dominio puede tener su carpeta con varios módulos (ej. stripe/, subscription/). Conectan Repositories con las peticiones; no hacen queries directas salvo que no exista repositorio aún.

## Inyección de dependencias

- `get_db` → core.database (inyectado en rutas que necesitan Session).
- `get_current_user` → core.security (devuelve User ORM).
- `get_document_service` → factories.dependencies (construye DocumentService con DocumentRepository inyectado).
- `get_subscription_service` → factories.dependencies (devuelve SubscriptionService).

Las rutas reciben los servicios por `Depends(get_*_service)` para poder sustituirlos en tests.

## Compatibilidad

- `app.config.settings` y `app.config.database` re-exportan desde `app.core` para no romper imports existentes.
- `app.utils.auth` re-exporta desde `app.core.security`.
- `app.exceptions` re-exporta desde `app.core.exceptions`.
- Los routers están en `app.routes` (auth, documents, users, subscriptions, etc.); main importa desde `app.routes`.
