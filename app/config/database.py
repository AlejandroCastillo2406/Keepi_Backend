import firebase_admin
from firebase_admin import credentials, firestore, auth
from app.config.settings import settings
import os

class DatabaseConfig:
    """Configuración de Firebase/Firestore"""
    
    _initialized = False
    
    @classmethod
    def initialize_firebase(cls):
        """Inicializar Firebase Admin SDK"""
        if cls._initialized:
            print("Firebase ya está inicializado")
            return
        
        try:
            # Verificar si ya está inicializado
            firebase_admin.get_app()
            print("Firebase ya está inicializado")
            cls._initialized = True
        except ValueError:
            try:
                # Verificar si existe archivo de credenciales válido
                if settings.google_application_credentials and os.path.exists(settings.google_application_credentials):
                    # Inicializar con credenciales de servicio
                    cred = credentials.Certificate(settings.google_application_credentials)
                    firebase_admin.initialize_app(cred)
                    print("Firebase inicializado con credenciales de servicio")
                else:
                    raise FileNotFoundError("Archivo de credenciales no encontrado")
            except Exception as e:
                print(f"⚠️ Error con credenciales de servicio: {e}")
                print("🔄 Inicializando en modo desarrollo...")
                
                # Inicializar con configuración del proyecto (para desarrollo)
                config = {
                    'projectId': settings.firebase_project_id,
                    'storageBucket': settings.firebase_storage_bucket
                }
                firebase_admin.initialize_app(options=config)
                print("✅ Firebase inicializado en modo desarrollo")
            
            cls._initialized = True
    
    @classmethod
    def get_firestore_client(cls):
        """Obtener cliente de Firestore"""
        if not cls._initialized:
            cls.initialize_firebase()
        return firestore.client()
    
    @classmethod
    def verify_firebase_token(cls, token: str):
        """Verificar token de Firebase Auth"""
        try:
            decoded_token = auth.verify_id_token(token, check_revoked=False)
            return decoded_token
        except auth.ExpiredIdTokenError:
            print("Token expirado")
            return None
        except auth.RevokedIdTokenError:
            print("Token revocado")
            return None
        except auth.InvalidIdTokenError as e:
            print(f"Token inválido: {e}")
            return None
        except Exception as e:
            print(f"Error verificando token: {e}")
            return None
