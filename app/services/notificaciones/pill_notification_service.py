import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.repositories.prescription_repository import PrescriptionRepository

logger = logging.getLogger(__name__)


async def run_pill_reminders_process(db: Session):
    active_prescriptions = PrescriptionRepository(
        db
    ).list_with_patient_reminders_enabled()

    notifications_sent = 0
    now = datetime.now(timezone.utc)

    for prescription in active_prescriptions:
        duration = getattr(prescription, "duration_days", 0)
        expiry_date = prescription.created_at + timedelta(days=duration)

        if now > expiry_date:
            continue

        frequency = getattr(prescription, "frequency_hours", 0)

        if frequency > 0:
            diff = now - prescription.created_at
            hours_since_start = diff.total_seconds() / 3600

            if hours_since_start >= 0 and (int(hours_since_start) % frequency == 0):
                logger.info("Enviando recordatorio para receta %s", prescription.id)
                notifications_sent += 1

    return {
        "status": "success",
        "processed_prescriptions": len(active_prescriptions),
        "notifications_sent": notifications_sent,
        "timestamp": now.isoformat(),
    }
