from datetime import datetime, timedelta, date
from decimal import Decimal
from app.database.db import SessionLocal
from app.models.models import (
    Room, RoomType, Guest, Stay, StayHistory, Booking, Payment, Expense,
    LaundryMachine, LaundryBooking, Maintenance, Cleaning, Notification,
    Document, AuditLog, InstitutionSettings, BackupSettings, Employee, User
)

def seed_demo_data():
    """Insere dados fictícios e realistas para testar todos os módulos.
    É idempotente: não duplica se já houver hóspedes cadastradas.
    """
    with SessionLocal() as db:
        if db.query(Guest).count() > 0:
            return
        now = datetime.now()
        rooms = {r.number: r for r in db.query(Room).all()}
        types = {t.name: t for t in db.query(RoomType).all()}
        guests_data = [
            ("Ana Beatriz Oliveira","529.381.740-10","RG-28.451.903","1997-03-14","(61) 99111-2201","ana.oliveira@example.test","Águas Claras","DF"),
            ("Camila Rodrigues Santos","418.726.930-22","RG-31.908.772","1994-08-22","(61) 99222-3412","camila.santos@example.test","Taguatinga","DF"),
            ("Juliana Martins Lima","307.615.820-34","RG-24.118.650","1999-11-06","(61) 99333-4523","juliana.lima@example.test","Ceilândia","DF"),
            ("Mariana Costa Almeida","196.504.710-46","RG-19.774.231","1992-01-30","(61) 99444-5634","mariana.almeida@example.test","Samambaia","DF"),
            ("Fernanda Souza Pereira","285.493.610-58","RG-27.665.114","1996-06-18","(61) 99555-6745","fernanda.pereira@example.test","Gama","DF"),
            ("Larissa Mendes Rocha","174.382.500-60","RG-22.440.918","2001-09-27","(61) 99666-7856","larissa.rocha@example.test","Plano Piloto","DF"),
            ("Beatriz Ferreira Gomes","063.271.490-72","RG-18.335.902","1998-12-11","(61) 99777-8967","beatriz.gomes@example.test","Sobradinho","DF"),
            ("Patrícia Nunes Ribeiro","952.160.380-84","RG-33.512.776","1989-04-03","(61) 99888-9078","patricia.ribeiro@example.test","Guará","DF"),
            ("Isabela Carvalho Dias","841.059.270-96","RG-26.781.440","2000-07-25","(61) 99999-0189","isabela.dias@example.test","Lago Sul","DF"),
            ("Renata Alves Moraes","730.948.160-08","RG-21.654.339","1995-10-16","(61) 99000-1290","renata.moraes@example.test","Vicente Pires","DF"),
            ("Sofia Barros Teixeira","629.837.050-19","RG-30.229.541","1993-02-09","(61) 99123-2301","sofia.teixeira@example.test","Planaltina","DF"),
            ("Carolina Freitas Moura","518.726.940-21","RG-25.118.762","1997-05-21","(61) 99234-3412","carolina.moura@example.test","Brazlândia","DF"),
        ]
        guests=[]
        for i, (name,cpf,rg,birth,phone,email,city,state) in enumerate(guests_data):
            g=Guest(full_name=name,cpf=cpf,rg=rg,birth_date=date.fromisoformat(birth),
                    phone=phone,whatsapp=phone,email=email,address=f"Rua de Teste, {100+i}",
                    city=city,state=state,emergency_contact="Contato de emergência fictício",
                    notes="Registro demonstrativo para testes.")
            db.add(g); guests.append(g)
        db.flush()

        # Ocupação distribuída pelos três tipos de unidade
        assignments=[("A01","ATIVA",0),("B01","ATIVA",1),("C01","ATIVA",2),("B02","ATIVA",3),("C02","ATIVA",4),("A02","ATIVA",5)]
        stays=[]
        for room_no,status,idx in assignments:
            if room_no not in rooms: continue
            g=guests[idx]
            ci=now-timedelta(days=18-idx)
            co=now+timedelta(days=12+idx)
            value=Decimal("1450.00") if room_no.startswith("A") else (Decimal("980.00") if room_no.startswith("B") else Decimal("720.00"))
            st=Stay(guest_id=g.id,room_id=rooms[room_no].id,check_in=ci,expected_check_out=co,
                    has_expected_check_out=True,value=value,deposit=Decimal("300.00"),status="ATIVA")
            db.add(st); stays.append(st)
            g.room_id=rooms[room_no].id
            rooms[room_no].status="OCUPADO"
        # Histórico de uma hospedagem encerrada
        old_guest=guests[6]; old_room=rooms.get("C03") or next(iter(rooms.values()))
        old_stay=Stay(guest_id=old_guest.id,room_id=old_room.id,check_in=now-timedelta(days=90),
                       expected_check_out=now-timedelta(days=60),actual_check_out=now-timedelta(days=61),
                       has_expected_check_out=True,value=Decimal("680.00"),deposit=Decimal("200.00"),status="ENCERRADA")
        db.add(old_stay); db.flush()
        db.add(StayHistory(stay_id=old_stay.id,action="CHECK_OUT",old_room_id=old_room.id,
                           old_checkout=now-timedelta(days=60),reason="Encerramento demonstrativo."))

        # Reservas em estados diferentes
        for idx,room_no in enumerate(["C04","B03","A03"]):
            if room_no in rooms:
                db.add(Booking(guest_id=guests[7+idx].id,room_id=rooms[room_no].id,
                    check_in=now+timedelta(days=5+idx),check_out=now+timedelta(days=12+idx),
                    value=Decimal("850.00")+Decimal(idx*150),notes="Reserva de teste.",
                    booking_type="HOSPEDAGEM",status=["CONFIRMADA","PRÉ-RESERVA","CANCELADA"][idx]))
                if idx<2: rooms[room_no].status="RESERVADO"

        # Financeiro: pagos, pendentes e atrasados
        for idx,st in enumerate(stays):
            due=now-timedelta(days=3) if idx==2 else now+timedelta(days=idx-2)
            paid=due+timedelta(hours=2) if idx in (0,1,3) else None
            db.add(Payment(guest_id=stays[idx].guest_id,room_id=st.room_id,
                description=f"Mensalidade demonstrativa - {guests[idx].full_name}",
                amount=st.value,due_date=due,paid_at=paid,method="PIX" if paid else None,
                status="PAGO" if paid else ("ATRASADO" if due<now else "PENDENTE"),
                notes="Lançamento fictício para teste."))
        db.add(Payment(guest_id=guests[6].id,room_id=old_room.id,description="Caução devolvida - teste",
                       amount=Decimal("200.00"),due_date=now-timedelta(days=50),paid_at=now-timedelta(days=49),
                       method="TRANSFERÊNCIA",status="PAGO"))
        for desc,cat,amount,days,status in [
            ("Conta de energia elétrica","UTILIDADES",Decimal("1840.50"),-4,"PAGO"),
            ("Compra de materiais de limpeza","MATERIAIS",Decimal("468.90"),-2,"PAGO"),
            ("Internet e telefonia","SERVIÇOS",Decimal("299.90"),3,"PENDENTE"),
            ("Manutenção hidráulica","MANUTENÇÃO",Decimal("620.00"),-1,"PAGO"),
            ("Reposição de enxoval","OPERAÇÃO",Decimal("890.00"),8,"PENDENTE"),
        ]:
            db.add(Expense(description=desc,category=cat,amount=amount,date=now+timedelta(days=days),
                            due_date=now+timedelta(days=days),status=status,notes="Despesa fictícia de teste."))

        # Lavanderia
        machines=[]
        for no,desc,typ,status in [("L01","Lavadora industrial 01","Lavadora","DISPONÍVEL"),
                                   ("L02","Lavadora industrial 02","Lavadora","EM MANUTENÇÃO"),
                                   ("S01","Secadora 01","Secadora","DISPONÍVEL")]:
            m=LaundryMachine(number=no,description=desc,type=typ,status=status,notes="Equipamento demonstrativo.")
            db.add(m); machines.append(m)
        db.flush()
        db.add(LaundryBooking(guest_id=guests[0].id,machine_id=machines[0].id,start_at=now+timedelta(days=1,hours=9),
                              end_at=now+timedelta(days=1,hours=10)))
        db.add(LaundryBooking(guest_id=guests[1].id,machine_id=machines[2].id,start_at=now+timedelta(days=1,hours=11),
                              end_at=now+timedelta(days=1,hours=12)))

        # Operações
        for room_no,status in [("B02","ABERTO"),(None,"EM ANDAMENTO"),("C03","CONCLUÍDA")]:
            room=rooms.get(room_no) if room_no else None
            if status in ("ABERTO","PENDENTE","EM ANDAMENTO") and room and room.status=="DISPONÍVEL":
                room.status="MANUTENÇÃO"
        db.add_all([
            Maintenance(location="B02",room_id=rooms.get("B02").id if rooms.get("B02") else None,
                        description="Torneira do banheiro apresenta vazamento.",date=now-timedelta(days=1),
                        priority="ALTA",responsible="Equipe de manutenção",status="ABERTO",cost=Decimal("0")),
            Maintenance(location="Área comum",description="Revisão preventiva do quadro elétrico.",
                        date=now-timedelta(days=4),priority="MÉDIA",responsible="Carlos - prestador",
                        status="EM ANDAMENTO",cost=Decimal("250.00")),
            Maintenance(location="C03",room_id=rooms.get("C03").id if rooms.get("C03") else None,
                        description="Pintura de parede após saída.",date=now-timedelta(days=20),
                        priority="BAIXA",responsible="Equipe de manutenção",status="CONCLUÍDA",cost=Decimal("370.00")),
        ])
        for i,room_no in enumerate(["A04","B04","C05","B05","C06"]):
            if room_no in rooms:
                status=["PENDENTE","REALIZADA","EM ANDAMENTO","PENDENTE","REALIZADA"][i]
                db.add(Cleaning(room_id=rooms[room_no].id,area="Unidade",
                    date=now+timedelta(days=i-2),responsible="Equipe de limpeza",
                    status=status,notes="Checklist de limpeza demonstrativo."))
                if status in ("AGENDADA","PENDENTE","EM ANDAMENTO") and rooms[room_no].status=="DISPONÍVEL":
                    rooms[room_no].status="LIMPEZA"
        for title,msg,read in [
            ("Pagamento em atraso","Existe uma mensalidade demonstrativa em atraso.",False),
            ("Limpeza pendente","Há unidades aguardando limpeza.",False),
            ("Manutenção aberta","Existe um chamado de manutenção aguardando atendimento.",False),
            ("Teste concluído","Massa de dados demonstrativa carregada com sucesso.",True),
        ]:
            db.add(Notification(title=title,message=msg,read=read))
        admin=db.query(User).filter_by(username="admin").first()
        for name,function,salary,phone,active,user in [
            ("Helena Duarte Campos","Administração","4200.00","(61) 98111-4401",True,admin),
            ("Rosa Maria Figueiredo","Recepção","2350.00","(61) 98222-5502",True,None),
            ("Célia Andrade Brito","Limpeza","1850.00","(61) 98333-6603",True,None),
            ("Márcia Pires Lopes","Limpeza","1850.00","(61) 98444-7704",True,None),
            ("João Batista Nogueira","Manutenção","2600.00","(61) 98555-8805",True,None),
            ("Vera Lúcia Tavares","Lavanderia","1750.00","(61) 98666-9906",False,None),
        ]:
            db.add(Employee(full_name=name,function=function,salary=Decimal(salary),phone=phone,whatsapp=phone,
                            active=active,user_id=user.id if user else None,
                            address="Endereço fictício",notes="Registro demonstrativo para testes."))
        db.add(Document(guest_id=guests[0].id,name="Documento demonstrativo - Ana Beatriz",path="demo/documento_ana.pdf"))
        db.add(AuditLog(action="SEED_DEMO",entity="SYSTEM",entity_id=None))
        db.add(BackupSettings(automatic_enabled=False,directory=None,last_backup=None))
        db.commit()
