from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.core.database import get_db
from app.core.security import require_no_temp_password_user
from app.models.user import User
from app.models.plans import Plan, PlanCreate, PlanUpdate, PlanResponse

router = APIRouter(prefix="/api/v1/admin/plans", tags=["Admin Plans"])

# Dependencia para verificar permisos
# Sugerencia: En el futuro puedes agregar un campo 'is_admin' en tu modelo User
def check_admin_user(current_user: User = Depends(require_no_temp_password_user)):
    # if not current_user.is_admin:
    #     raise HTTPException(status_code=403, detail="Acceso denegado: Se requieren permisos de administrador")
    return current_user

@router.post("/", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    plan_in: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_user)
):
    """
    Crear un nuevo plan.
    Incluye la configuración de Stripe y límites de análisis a futuro.
    """
   
    existing_plan = db.query(Plan).filter(Plan.code == plan_in.code).first()
    if existing_plan:
        raise HTTPException(status_code=400, detail="Ya existe un plan con este código")
    
    new_plan = Plan(**plan_in.model_dump())
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    
    return PlanResponse.from_orm(new_plan)

@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_user)
):
    """
    Obtener los detalles específicos de un plan mediante su ID.
    """
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de plan inválido")
        
    plan = db.query(Plan).filter(Plan.id == plan_uuid).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
        
    return PlanResponse.from_orm(plan)

@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: str,
    plan_in: PlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_user)
):
    """
    Actualizar la información de un plan.
    Útil para cambiar precios, límites de análisis o el ID del precio de Stripe.
    """
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de plan inválido")
        
    plan = db.query(Plan).filter(Plan.id == plan_uuid).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
        
    update_data = plan_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plan, key, value)
        
    db.commit()
    db.refresh(plan)
    
    return PlanResponse.from_orm(plan)

@router.delete("/{plan_id}")
async def delete_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(check_admin_user)
):
    """
    Eliminar un plan (Soft Delete).
    Se desactiva en lugar de borrarse de la BD para no romper el historial
    ni afectar a los usuarios que ya tienen una suscripción con este plan.
    """
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de plan inválido")
        
    plan = db.query(Plan).filter(Plan.id == plan_uuid).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
        
    # Aplicar Soft Delete
    plan.is_active = False
    db.commit()
    
    return {"message": f"El plan '{plan.name}' ha sido desactivado exitosamente."}