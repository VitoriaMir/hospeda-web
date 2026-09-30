from app.database.db import SessionLocal
from app.models.models import User, RoomType, Room, InstitutionSettings
from app.core.security import hash_password

ROOM_TYPES = [
    ("KITNET", "privativo", "privativa", 5),
    ("QUARTO COMPARTILHADO", "compartilhado", "compartilhada", 40),
    ("QUARTO COM BANHEIRO", "privativo", "compartilhada", 25),
]

def bootstrap():
    with SessionLocal() as session:
        if not session.query(User).filter_by(username="admin").first():
            session.add(User(
                username="admin",
                password_hash=hash_password("admin123"),
                role="ADMINISTRADOR",
                active=True,
                must_change_password=True,
            ))

        if not session.query(InstitutionSettings).first():
            session.add(InstitutionSettings(
                name="Hospeda",
                subtitle="Gestão de hospedagem",
                city_state="",
            ))

        existing_types = {x.name: x for x in session.query(RoomType).all()}
        for name, bathroom, kitchen, quantity in ROOM_TYPES:
            rt = existing_types.get(name)
            if not rt:
                rt = RoomType(name=name, bathroom=bathroom, kitchen=kitchen)
                session.add(rt)
                session.flush()

            current = session.query(Room).filter(Room.room_type_id == rt.id).count()
            for i in range(current + 1, quantity + 1):
                prefix = {"KITNET": "A", "QUARTO COMPARTILHADO": "C", "QUARTO COM BANHEIRO": "B"}[name]
                session.add(Room(
                    number=f"{prefix}{i:02d}",
                    room_type_id=rt.id,
                    status="DISPONÍVEL",
                    active=True,
                ))
        session.commit()

# A base distribuída com o projeto já contém dados demonstrativos realistas e fictícios.
# Não recriar automaticamente registros de teste ao iniciar a aplicação.
def seed_demo_occupancy():
    """Carrega uma massa de testes fictícia, uma única vez, em base vazia."""
    from app.services.demo_data import seed_demo_data
    seed_demo_data()
