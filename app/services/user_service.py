from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.config.database import get_db, DatabaseConfig
from app.models.user import User, UserCreate, UserUpdate, UserResponse, UserSettings, UserLogin
from app.utils.auth import get_password_hash, verify_password, create_access_token

class UserService:
    """Servicio para gestión de usuarios"""
    
    def __init__(self, db: Session = None):
        self.db = db or next(get_db())
    
    async def get_user_by_uid(self, uid: str) -> Optional[UserResponse]:
        """Obtener usuario por UID"""
        try:
            user = self.db.query(User).filter(User.id == uid).first()
            if user:
                return UserResponse.from_orm(user)
            return None
        except Exception as e:
            print(f"Error obteniendo usuario: {e}")
            return None
    
    async def create_user(self, user_data: UserCreate) -> UserResponse:
        """Crear nuevo usuario"""
        try:
            # Verificar si el usuario ya existe
            existing_user = self.db.query(User).filter(User.email == user_data.email).first()
            if existing_user:
                raise ValueError("El usuario con este email ya existe")
            
            # Crear instancia de usuario
            user = User(
                email=user_data.email,
                name=user_data.name,
                hashed_password=get_password_hash(user_data.password) if user_data.password else None,
                profile_picture=user_data.profile_picture,
                settings=user_data.settings or {},
                storage_preference=user_data.storage_preference or "local"
            )
            
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            
            return UserResponse.from_orm(user)
        except Exception as e:
            print(f"Error creando usuario: {e}")
            self.db.rollback()
            raise
    
    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Autenticar usuario con email y contraseña"""
        try:
            user = self.db.query(User).filter(User.email == email).first()
            if not user:
                return None
            if not user.hashed_password:
                return None
            if not verify_password(password, user.hashed_password):
                return None
            return user
        except Exception as e:
            print(f"Error autenticando usuario: {e}")
            return None
    
    async def login_user(self, login_data: UserLogin) -> Optional[Dict[str, Any]]:
        """Login de usuario y retornar token"""
        try:
            user = await self.authenticate_user(login_data.email, login_data.password)
            if not user:
                return None
            
            # Crear token JWT
            access_token_expires = timedelta(minutes=30)
            access_token = create_access_token(
                data={
                    "sub": str(user.id),
                    "email": user.email,
                    "name": user.name,
                    "picture": user.profile_picture
                },
                expires_delta=access_token_expires
            )
            
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user": UserResponse.from_orm(user)
            }
        except Exception as e:
            print(f"Error en login: {e}")
            return None
    
    async def update_user(self, uid: str, user_data: UserUpdate) -> Optional[UserResponse]:
        """Actualizar usuario"""
        try:
            user = self.db.query(User).filter(User.id == uid).first()
            if not user:
                return None
            
            # Actualizar campos
            update_data = user_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(user, field, value)
            
            self.db.commit()
            self.db.refresh(user)
            
            return UserResponse.from_orm(user)
        except Exception as e:
            print(f"Error actualizando usuario: {e}")
            self.db.rollback()
            return None
    
    async def update_user_fields(self, uid: str, fields: dict) -> bool:
        """Actualizar campos específicos del usuario"""
        try:
            user = self.db.query(User).filter(User.id == uid).first()
            if not user:
                return False
            
            for field, value in fields.items():
                if hasattr(user, field):
                    setattr(user, field, value)
            
            self.db.commit()
            return True
        except Exception as e:
            print(f"Error actualizando campos del usuario: {e}")
            self.db.rollback()
            return False
    
    async def get_all_users(self) -> List[UserResponse]:
        """Obtener todos los usuarios (solo para desarrollo)"""
        try:
            users = self.db.query(User).all()
            return [UserResponse.from_orm(user) for user in users]
        except Exception as e:
            print(f"Error obteniendo usuarios: {e}")
            return []
    
    async def delete_user(self, uid: str) -> bool:
        """Eliminar usuario"""
        try:
            user = self.db.query(User).filter(User.id == uid).first()
            if user:
                self.db.delete(user)
                self.db.commit()
                return True
            return False
        except Exception as e:
            print(f"Error eliminando usuario: {e}")
            self.db.rollback()
            return False
    
    async def update_user_settings(self, uid: str, settings: UserSettings) -> bool:
        """Actualizar configuración de usuario"""
        try:
            user = self.db.query(User).filter(User.id == uid).first()
            if user:
                user.settings = settings.dict()
                self.db.commit()
                return True
            return False
        except Exception as e:
            print(f"Error actualizando configuración: {e}")
            self.db.rollback()
            return False
