"""CLI: python scripts/seed_questionnaires_from_json.py (desde carpeta backend)."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.database import SessionLocal
from app.services.questionnaires.seed import load_json, seed_specialties, seed_all_if_needed
from app.models.questionnaire_catalog import QuestionnaireTemplate, QuestionnaireVersion


def main() -> None:
    db = SessionLocal()
    try:
        data = load_json()
        seed_specialties(db, data)
        db.commit()
        ok = seed_all_if_needed(db)
        print("OK" if ok else "Already seeded (nothing new)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
