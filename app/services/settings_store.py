from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.setting import Setting


def get_setting(db: Session, category: str, key: str, default: Any = None) -> Any:
    row = db.execute(select(Setting).where(Setting.category == category, Setting.key == key)).scalar_one_or_none()
    if row is None or row.value is None:
        return default
    return json.loads(row.value)


def set_setting(db: Session, category: str, key: str, value: Any, is_secret: bool = False) -> None:
    row = db.execute(select(Setting).where(Setting.category == category, Setting.key == key)).scalar_one_or_none()
    encoded = json.dumps(value)
    if row is None:
        db.add(Setting(category=category, key=key, value=encoded, is_secret=is_secret))
    else:
        row.value = encoded
        row.is_secret = is_secret
    db.commit()
