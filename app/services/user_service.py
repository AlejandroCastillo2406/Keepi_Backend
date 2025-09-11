from typing import Optional, List, Dict, Any
from datetime import datetime
from app.config.database import DatabaseConfig
from app.models.user import UserCreate, UserUpdate, UserResponse, UserSettings

class UserService:
    """Servicio para gestión de usuarios"""
    
    def __init__(self):
        self.db = DatabaseConfig.get_firestore_client()
    
    async def get_user_by_uid(self, uid: str) -> Optional[UserResponse]:
        """Obtener usuario por UID"""
        try:
            user_doc = self.db.collection('users').document(uid).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_data['uid'] = uid
                return UserResponse(**user_data)
            return None
        except Exception as e:
            print(f"Error obteniendo usuario: {e}")
            return None
    
    async def create_user(self, user_data: UserCreate) -> UserResponse:
        """Crear nuevo usuario"""
        try:
            user_dict = user_data.dict()
            user_dict['created_at'] = datetime.now()
            user_dict['updated_at'] = datetime.now()
            user_dict['settings'] = UserSettings().dict()
            
            self.db.collection('users').document(user_data.uid).set(user_dict)
            user_dict['uid'] = user_data.uid
            
            return UserResponse(**user_dict)
        except Exception as e:
            print(f"Error creando usuario: {e}")
            raise
    
    async def update_user(self, uid: str, user_data: UserUpdate) -> Optional[UserResponse]:
        """Actualizar usuario"""
        try:
            update_data = user_data.dict(exclude_unset=True)
            update_data['updated_at'] = datetime.now()
            
            user_ref = self.db.collection('users').document(uid)
            user_ref.update(update_data)
            
            # Obtener usuario actualizado
            updated_doc = user_ref.get()
            if updated_doc.exists:
                user_dict = updated_doc.to_dict()
                user_dict['uid'] = uid
                return UserResponse(**user_dict)
            return None
        except Exception as e:
            print(f"Error actualizando usuario: {e}")
            return None
    
    async def get_all_users(self) -> List[UserResponse]:
        """Obtener todos los usuarios (solo para desarrollo)"""
        try:
            users = self.db.collection('users').stream()
            user_list = []
            for user in users:
                user_data = user.to_dict()
                user_data['uid'] = user.id
                user_list.append(UserResponse(**user_data))
            return user_list
        except Exception as e:
            print(f"Error obteniendo usuarios: {e}")
            return []
    
    async def delete_user(self, uid: str) -> bool:
        """Eliminar usuario"""
        try:
            self.db.collection('users').document(uid).delete()
            return True
        except Exception as e:
            print(f"Error eliminando usuario: {e}")
            return False
    
    async def update_user_settings(self, uid: str, settings: UserSettings) -> bool:
        """Actualizar configuración de usuario"""
        try:
            user_ref = self.db.collection('users').document(uid)
            user_ref.update({
                'settings': settings.dict(),
                'updated_at': datetime.now()
            })
            return True
        except Exception as e:
            print(f"Error actualizando configuración: {e}")
            return False
