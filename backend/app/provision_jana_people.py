"""Explicit, repeatable provisioning of synthetic directory people in mock mode."""

import secrets

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.models import Employee
from app.modules.integrations import DemoZupFixtures
from app.security import password_hash


def provision(db: Session) -> int:
    if get_settings().zup_mode != "mock":
        raise RuntimeError("Synthetic people can only be provisioned with ZUP_MODE=mock")
    snapshots = [person for person in DemoZupFixtures().employees() if person.zup_id.startswith("people-")]
    fixture_ids = {person.id for person in snapshots}
    if len(fixture_ids) != len(snapshots) or any(person.manager_id not in fixture_ids for person in snapshots if person.manager_id is not None):
        raise RuntimeError("Invalid synthetic reporting structure")
    db.execute(text("LOCK TABLE employees IN SHARE ROW EXCLUSIVE MODE"))
    existing = {person.zup_id: person for person in db.scalars(select(Employee).where(Employee.zup_id.in_([item.zup_id for item in snapshots])))}
    mapped_ids: dict[int, int] = {}
    created = 0
    # Fixtures are ordered with managers first; fail rather than invent a link.
    for snapshot in snapshots:
        if snapshot.manager_id is not None and snapshot.manager_id not in mapped_ids:
            raise RuntimeError(f"Missing synthetic manager for {snapshot.zup_id}")
        manager_id = mapped_ids.get(snapshot.manager_id)
        person = existing.get(snapshot.zup_id)
        if person is None:
            if db.scalar(select(Employee.id).where(Employee.email == snapshot.email)) is not None:
                raise RuntimeError(f"Directory identity collision: {snapshot.zup_id}")
            person = Employee(email=snapshot.email, password_hash=password_hash.hash(secrets.token_urlsafe(48)),
                full_name=snapshot.full_name, role=snapshot.role, company=snapshot.company,
                position=snapshot.position, department=snapshot.department, manager_id=manager_id,
                hire_date=snapshot.hire_date, leave_balance=snapshot.leave_balance, zup_id=snapshot.zup_id)
            db.add(person)
            db.flush()
            created += 1
        # Existing rows may have been edited by an administrator; never overwrite them.
        mapped_ids[snapshot.id] = person.id
    return created


def main() -> None:
    with Session(get_engine()) as db:
        created = provision(db)
        db.commit()
    print(f"Synthetic Jana People ready: {created} created.")


if __name__ == "__main__":
    main()
