from typing import Optional, List
from datetime import datetime
from app.config.database import DatabaseConfig
from app.models.notification import NotificationCreate, NotificationUpdate, NotificationResponse

class NotificationService:
    """Servicio para gestión de notificaciones"""
    
    def __init__(self):
        self.db = DatabaseConfig.get_firestore_client()
    
    async def get_user_notifications(self, user_id: str) -> List[NotificationResponse]:
        """Obtener todas las notificaciones de un usuario"""
        try:
            docs = self.db.collection('notifications').where('user_id', '==', user_id).order_by('created_at', direction='desc').stream()
            notifications = []
            for doc in docs:
                notification_data = doc.to_dict()
                notification_data['id'] = doc.id
                notifications.append(NotificationResponse(**notification_data))
            return notifications
        except Exception as e:
            print(f"Error obteniendo notificaciones: {e}")
            return []
    
    async def get_notification_by_id(self, notification_id: str, user_id: str) -> Optional[NotificationResponse]:
        """Obtener notificación por ID"""
        try:
            doc_ref = self.db.collection('notifications').document(notification_id)
            doc = doc_ref.get()
            
            if doc.exists:
                notification_data = doc.to_dict()
                if notification_data.get('user_id') == user_id:
                    notification_data['id'] = notification_id
                    return NotificationResponse(**notification_data)
            return None
        except Exception as e:
            print(f"Error obteniendo notificación: {e}")
            return None
    
    async def create_notification(self, user_id: str, notification_data: NotificationCreate) -> NotificationResponse:
        """Crear nueva notificación"""
        try:
            notification_dict = notification_data.dict()
            notification_dict['user_id'] = user_id
            notification_dict['read'] = False
            notification_dict['created_at'] = datetime.now()
            
            doc_ref = self.db.collection('notifications').add(notification_dict)
            notification_dict['id'] = doc_ref[1].id
            
            return NotificationResponse(**notification_dict)
        except Exception as e:
            print(f"Error creando notificación: {e}")
            raise
    
    async def mark_notification_read(self, notification_id: str, user_id: str) -> bool:
        """Marcar notificación como leída"""
        try:
            doc_ref = self.db.collection('notifications').document(notification_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return False
            
            notification_data = doc.to_dict()
            if notification_data.get('user_id') != user_id:
                return False
            
            doc_ref.update({
                "read": True,
                "read_at": datetime.now()
            })
            return True
        except Exception as e:
            print(f"Error marcando notificación como leída: {e}")
            return False
    
    async def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """Eliminar notificación"""
        try:
            doc_ref = self.db.collection('notifications').document(notification_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return False
            
            notification_data = doc.to_dict()
            if notification_data.get('user_id') != user_id:
                return False
            
            doc_ref.delete()
            return True
        except Exception as e:
            print(f"Error eliminando notificación: {e}")
            return False
    
    async def get_unread_notifications_count(self, user_id: str) -> int:
        """Obtener cantidad de notificaciones no leídas"""
        try:
            docs = self.db.collection('notifications').where('user_id', '==', user_id).where('read', '==', False).stream()
            count = 0
            for _ in docs:
                count += 1
            return count
        except Exception as e:
            print(f"Error contando notificaciones no leídas: {e}")
            return 0
