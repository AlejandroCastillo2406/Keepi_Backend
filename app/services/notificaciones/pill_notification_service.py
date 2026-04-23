import logging
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
from app.models.prescription import Prescription 

logger = logging.getLogger(__name__)

async def run_pill_reminders_process(db: Session):
    """
    Procesa recordatorios de pastillas verificando vigencia y frecuencia.
    """
    # 1. Filtramos solo recetas con recordatorios habilitados (CORREGIDO: enabled con 'd')
    active_prescriptions = db.query(Prescription).filter(
        Prescription.patient_reminders_enabled == True
    ).all()

    notifications_sent = 0
    now = datetime.now(timezone.utc)

    for prescription in active_prescriptions:
        # Lógica de Vigencia: Fecha de creación + duración
        duration = getattr(prescription, 'duration_days', 0)
        expiry_date = prescription.created_at + timedelta(days=duration)
        
        if now > expiry_date:
            continue

        # Lógica de Frecuencia: Cada cuántas horas
        frequency = getattr(prescription, 'frequency_hours', 0)
        
        if frequency > 0:
            diff = now - prescription.created_at
            hours_since_start = diff.total_seconds() / 3600
            
            # Si el residuo es cercano a 0, significa que toca dosis
            if hours_since_start >= 0 and (int(hours_since_start) % frequency == 0):
                # Aquí se integraría el envío de la notificación (Push/SMS)
                logger.info(f"Enviando recordatorio para receta {prescription.id}")
                notifications_sent += 1

    return {
        "status": "success",
        "processed_prescriptions": len(active_prescriptions),
        "notifications_sent": notifications_sent,
        "timestamp": now.isoformat()
    }