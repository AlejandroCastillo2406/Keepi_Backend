from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.utils.auth import verify_token
from app.services.notification_service import NotificationService
from app.models.notification import NotificationCreate, NotificationResponse

router = APIRouter()

@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(user_token: dict = Depends(verify_token)):
    """Obtener todas las notificaciones del usuario autenticado"""
    try:
        notification_service = NotificationService()
        notifications = await notification_service.get_user_notifications(user_token['uid'])
        return notifications
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: str,
    user_token: dict = Depends(verify_token)
):
    """Obtener notificación específica por ID"""
    try:
        notification_service = NotificationService()
        notification = await notification_service.get_notification_by_id(notification_id, user_token['uid'])
        
        if notification:
            return notification
        else:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=NotificationResponse)
async def create_notification(
    notification_data: NotificationCreate,
    user_token: dict = Depends(verify_token)
):
    """Crear nueva notificación"""
    try:
        notification_service = NotificationService()
        notification = await notification_service.create_notification(user_token['uid'], notification_data)
        return notification
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user_token: dict = Depends(verify_token)
):
    """Marcar notificación como leída"""
    try:
        notification_service = NotificationService()
        success = await notification_service.mark_notification_read(notification_id, user_token['uid'])
        
        if success:
            return {"message": "Notificación marcada como leída", "notification_id": notification_id}
        else:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    user_token: dict = Depends(verify_token)
):
    """Eliminar notificación"""
    try:
        notification_service = NotificationService()
        success = await notification_service.delete_notification(notification_id, user_token['uid'])
        
        if success:
            return {"message": "Notificación eliminada correctamente", "notification_id": notification_id}
        else:
            raise HTTPException(status_code=404, detail="Notificación no encontrada")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/unread/count")
async def get_unread_notifications_count(user_token: dict = Depends(verify_token)):
    """Obtener cantidad de notificaciones no leídas"""
    try:
        notification_service = NotificationService()
        count = await notification_service.get_unread_notifications_count(user_token['uid'])
        return {"unread_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
