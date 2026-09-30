from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
import os
import re
import secrets
from sqlalchemy import func, or_, desc
from app.database.db import SessionLocal, init_database
from app.models.models import User, Employee, Room, RoomType, Guest, Stay, Booking, Payment, Expense, Maintenance, Cleaning, Notification
from app.core.security import verify_password, hash_password
from app.core.branding import load_brand
from app.services.bootstrap_service import bootstrap, seed_demo_occupancy

def load_secret_key():
    """Usa CONPEC_SECRET_KEY se definida; caso contrário, gera e persiste
    uma chave local em .secret_key para manter as sessões válidas entre
    reinícios sem depender de uma chave fixa no código-fonte."""
    env_key = os.environ.get('CONPEC_SECRET_KEY')
    if env_key:
        return env_key
    key_file = Path(__file__).resolve().parent / '.secret_key'
    if key_file.exists():
        return key_file.read_text().strip()
    import secrets
    new_key = secrets.token_hex(32)
    key_file.write_text(new_key)
    return new_key

app=Flask(__name__); app.secret_key=load_secret_key(); BRAND=load_brand(); init_database(); bootstrap(); seed_demo_occupancy()

def auth_required(f):
 @wraps(f)
 def w(*a,**k):
  if 'user_id' not in session: return redirect(url_for('login'))
  if session.get('must_change_password') and f.__name__ not in ('change_password','logout','update_own_profile'):
   return redirect(url_for('change_password'))
  return f(*a,**k)
 return w

def money(v): return float(v or 0)
def parse_dt(s):
 if not s: return None
 try: return datetime.fromisoformat(s)
 except: return None

def notifications():
 with SessionLocal() as db:
  n=[]; now=datetime.now()
  # Pagamentos e despesas pendentes cuja data já passou viram atrasados automaticamente.
  stale=db.query(Payment).filter(Payment.status=='PENDENTE', Payment.due_date<now).all()
  for p in stale: p.status='ATRASADO'
  stale_expenses=db.query(Expense).filter(Expense.status=='PENDENTE', Expense.date<now).all()
  for e in stale_expenses: e.status='ATRASADO'
  if stale or stale_expenses: db.commit()
  overdue=db.query(Payment).filter(Payment.status=='ATRASADO').count()
  cleaning=db.query(Cleaning).filter(Cleaning.status.in_(['PENDENTE','ABERTO'])).count()
  maintenance=db.query(Maintenance).filter(Maintenance.status.in_(['ABERTO','PENDENTE'])).count()
  if overdue: n.append({'title':'Pagamentos atrasados','message':f'{overdue} pagamento(s) precisam de atenção.','type':'danger','url':url_for('finance',kind='PAGAMENTOS',status='ATRASADO')})
  if cleaning: n.append({'title':'Limpeza pendente','message':f'{cleaning} tarefa(s) de limpeza pendente(s).','type':'warning','url':url_for('operations')+'#limpeza'})
  if maintenance: n.append({'title':'Manutenção','message':f'{maintenance} chamado(s) em aberto.','type':'info','url':url_for('operations')+'#manutencao'})
  return n

def room_block_label(number):
    value=(number or '').strip().upper()
    if value and value[0] in ('A','B','C'):
        return value[0]
    return 'A'

@app.context_processor
def inject():
 return {'notifications':notifications(), 'now':datetime.now(), 'brand':BRAND}

@app.after_request
def no_cache_after_logout(response):
 # Sem isso, o botão "voltar" do navegador reexibe páginas protegidas do
 # cache local mesmo depois do logout, sem passar pelo auth_required.
 if not request.path.startswith('/static/'):
  response.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'
  response.headers['Pragma']='no-cache'
  response.headers['Expires']='0'
 return response

@app.route('/')
def index(): return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  u=request.form.get('username','').strip(); p=request.form.get('password','')
  with SessionLocal() as db:
   user=db.query(User).filter_by(username=u,active=True).first()
   if user and verify_password(p,user.password_hash): session['user_id']=user.id; session['username']=user.username; session['role']=user.role; session['must_change_password']=user.must_change_password; return redirect(url_for('dashboard'))
  flash('Usuário ou senha inválidos.','danger')
 return render_template('login.html')
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('login'))

@app.route('/dashboard')
@auth_required
def dashboard():
 with SessionLocal() as db:
  rooms=db.query(Room).filter_by(active=True).all(); guests=db.query(Guest).count()
  metrics={s:sum(r.status==s for r in rooms) for s in ['OCUPADO','DISPONÍVEL','RESERVADO']}
  metrics['LIMPEZA']=db.query(Cleaning).filter(Cleaning.status.in_(['AGENDADA','PENDENTE','EM ANDAMENTO'])).count()
  metrics['MANUTENÇÃO']=db.query(Maintenance).filter(Maintenance.status.in_(['ABERTO','PENDENTE','EM ANDAMENTO'])).count()
  payments=db.query(Payment).order_by(desc(Payment.due_date)).limit(8).all()
  maint=db.query(Maintenance).filter(Maintenance.status.notin_(['CONCLUÍDA','FECHADO'])).order_by(desc(Maintenance.date)).limit(5).all()
  clean=db.query(Cleaning).filter(Cleaning.status.notin_(['CONCLUÍDA','REALIZADA'])).order_by(Cleaning.date).limit(5).all()
  stays=db.query(Stay).filter_by(status='ATIVA').all()
  guestmap={g.id:g.full_name for g in db.query(Guest).all()}; roommap={r.id:r.number for r in rooms}
  month=datetime.now().month; year=datetime.now().year
  income=db.query(func.coalesce(func.sum(Payment.amount),0)).filter(Payment.status=='PAGO',func.strftime('%m',Payment.paid_at)==f'{month:02d}',func.strftime('%Y',Payment.paid_at)==str(year)).scalar() or 0
  expense=db.query(func.coalesce(func.sum(Expense.amount),0)).filter(func.strftime('%m',Expense.date)==f'{month:02d}',func.strftime('%Y',Expense.date)==str(year)).scalar() or 0
  pending=db.query(func.coalesce(func.sum(Payment.amount),0)).filter(Payment.status.in_(['PENDENTE','ATRASADO'])).scalar() or 0
  chart=[]
  for m in range(1,13):
   inc=db.query(func.coalesce(func.sum(Payment.amount),0)).filter(Payment.status=='PAGO',func.strftime('%m',Payment.paid_at)==f'{m:02d}',func.strftime('%Y',Payment.paid_at)==str(year)).scalar() or 0
   exp=db.query(func.coalesce(func.sum(Expense.amount),0)).filter(func.strftime('%m',Expense.date)==f'{m:02d}',func.strftime('%Y',Expense.date)==str(year)).scalar() or 0
   chart.append({'month':f'{m:02d}/{str(year)[2:]}','income':money(inc),'expense':money(exp)})
  return render_template('dashboard.html',rooms=rooms,metrics=metrics,guests=guests,payments=payments,maint=maint,clean=clean,stays=stays,guestmap=guestmap,roommap=roommap,income=money(income),expense=money(expense),pending=money(pending),chart=chart)

@app.route('/rooms')
@auth_required
def rooms():
 q=request.args.get('q','').strip(); status=request.args.get('status',''); block=request.args.get('block','').strip().upper()
 with SessionLocal() as db:
  query=db.query(Room).filter_by(active=True)
  if q: query=query.filter(or_(Room.number.ilike(f'%{q}%'),Room.notes.ilike(f'%{q}%')))
  if status: query=query.filter(Room.status==status)
  if block:
   query=query.filter(Room.number.ilike(f'{block}%'))
  rooms=query.order_by(Room.number).all(); room_types=db.query(RoomType).order_by(RoomType.name).all(); types={t.id:t.name for t in room_types}
  rooms_by_block={b:[] for b in ['A','B','C']}
  for room in rooms:
   key=room_block_label(room.number)
   if key in rooms_by_block: rooms_by_block[key].append(room)
 return render_template('rooms.html',rooms=rooms,rooms_by_block=rooms_by_block,types=types,room_types=room_types,q=q,status=status,block=block)

@app.route('/room-types/<int:rtid>/pricing',methods=['POST'])
@auth_required
def room_type_pricing(rtid):
    try:
        rent=Decimal(request.form.get('rent_value','0').replace(',','.'))
        daily=Decimal(request.form.get('daily_value','0').replace(',','.'))
    except Exception:
        flash('Informe valores válidos.','danger'); return redirect(url_for('rooms')+'#valores')
    if rent<0 or daily<0:
        flash('Os valores não podem ser negativos.','danger'); return redirect(url_for('rooms')+'#valores')
    with SessionLocal() as db:
        rt=db.get(RoomType,rtid)
        if not rt: flash('Tipo de unidade não encontrado.','danger'); return redirect(url_for('rooms')+'#valores')
        rt.rent_value=rent; rt.daily_value=daily; db.commit()
    flash('Valores atualizados com sucesso.','success'); return redirect(url_for('rooms')+'#valores')

def resolve_room_number(block, raw_number):
    """Valida bloco+número e retorna (numero_final, None) ou (None, mensagem_de_erro)."""
    if block not in ('A', 'B', 'C'):
        return None, 'Selecione um bloco válido: A, B ou C.'
    if not raw_number:
        return None, 'Informe o número da unidade.'
    # Aceita tanto “101” (o bloco será acrescentado) quanto “A101”.
    if raw_number[0:1] in ('A', 'B', 'C'):
        if raw_number[0] != block:
            return None, f'O número informado pertence ao bloco {raw_number[0]}. Selecione o bloco {raw_number[0]} ou informe apenas os números.'
        room_number = raw_number
    else:
        room_number = f'{block}{raw_number}'
    if not re.fullmatch(r'[ABC][0-9]+', room_number):
        return None, 'Use apenas números, como 101, ou o formato completo, como A101.'
    return room_number, None

@app.route('/rooms/new',methods=['POST'])
@auth_required
def new_room():
    block = request.form.get('block', '').strip().upper()
    raw_number = request.form.get('number', '').strip().upper().replace(' ', '')
    room_type_id = request.form.get('room_type_id', type=int)
    status = request.form.get('status', 'DISPONÍVEL').strip().upper()
    active = request.form.get('active') == 'on'
    daily = request.form.get('daily') == 'on'
    notes = request.form.get('notes', '').strip()

    room_number, error = resolve_room_number(block, raw_number)
    if error: flash(error, 'danger'); return redirect(url_for('rooms'))
    if not room_type_id: flash('Selecione o tipo da unidade.','danger'); return redirect(url_for('rooms'))
    if status not in ('DISPONÍVEL','OCUPADO','RESERVADO','MANUTENÇÃO','LIMPEZA','INDISPONÍVEL'): flash('Status inválido.','danger'); return redirect(url_for('rooms'))
    with SessionLocal() as db:
        if not db.get(RoomType, room_type_id): flash('Tipo de unidade inválido.','danger'); return redirect(url_for('rooms'))
        if db.query(Room).filter(Room.number == room_number).first(): flash('Já existe uma unidade com este número.','danger'); return redirect(url_for('rooms'))
        room=Room(number=room_number, room_type_id=room_type_id, status=status, active=active, daily=daily, notes=notes or None)
        db.add(room); db.commit()
    flash('Unidade cadastrada com sucesso.','success'); return redirect(url_for('rooms'))

@app.route('/rooms/<int:rid>/edit',methods=['POST'])
@auth_required
def edit_room(rid):
    block = request.form.get('block', '').strip().upper()
    raw_number = request.form.get('number', '').strip().upper().replace(' ', '')
    room_type_id = request.form.get('room_type_id', type=int)
    active = request.form.get('active') == 'on'
    daily = request.form.get('daily') == 'on'
    notes = request.form.get('notes', '').strip()
    new_status = request.form.get('status', '').strip().upper()

    room_number, error = resolve_room_number(block, raw_number)
    if error: flash(error, 'danger'); return redirect(url_for('rooms'))
    if not room_type_id: flash('Selecione o tipo da unidade.','danger'); return redirect(url_for('rooms'))
    with SessionLocal() as db:
        room=db.get(Room,rid)
        if not room: flash('Unidade não encontrada.','danger'); return redirect(url_for('rooms'))
        if not db.get(RoomType, room_type_id): flash('Tipo de unidade inválido.','danger'); return redirect(url_for('rooms'))
        if db.query(Room).filter(Room.number == room_number, Room.id != rid).first(): flash('Já existe uma unidade com este número.','danger'); return redirect(url_for('rooms'))
        room.number=room_number; room.room_type_id=room_type_id; room.active=active; room.daily=daily; room.notes=notes or None
        # Status é gerenciado automaticamente pelas hospedagens/reservas/operações;
        # só permite alternar manualmente entre DISPONÍVEL e INDISPONÍVEL.
        if room.status in ('DISPONÍVEL','INDISPONÍVEL') and new_status in ('DISPONÍVEL','INDISPONÍVEL'):
            room.status=new_status
        db.commit()
    flash('Unidade atualizada com sucesso.','success'); return redirect(url_for('rooms'))

@app.route('/guests')
@auth_required
def guests():
 q=request.args.get('q','').strip(); city=request.args.get('city','').strip()
 with SessionLocal() as db:
    query=db.query(Guest)
    if q: query=query.filter(or_(Guest.full_name.ilike(f'%{q}%'),Guest.cpf.ilike(f'%{q}%'),Guest.phone.ilike(f'%{q}%'),Guest.whatsapp.ilike(f'%{q}%')))
    if city: query=query.filter(Guest.city.ilike(f'%{city}%'))
    guests=query.order_by(Guest.full_name).all()
    cities=sorted({g.city for g in db.query(Guest).all() if g.city})
    rooms=db.query(Room).filter(Room.active==True, Room.status=='DISPONÍVEL').order_by(Room.number).all()
    rooms_map={r.id:r.number for r in db.query(Room).all()}
 return render_template('guests.html',guests=guests,q=q,city=city,cities=cities,rooms=rooms,rooms_map=rooms_map)

@app.route('/guest/<int:gid>')
@auth_required
def guest_detail(gid):
 with SessionLocal() as db:
  g=db.get(Guest,gid)
  if not g: return redirect(url_for('guests'))
  stays=db.query(Stay).filter_by(guest_id=gid).order_by(desc(Stay.check_in)).all(); bookings=db.query(Booking).filter_by(guest_id=gid).order_by(desc(Booking.check_in)).all(); pays=db.query(Payment).filter_by(guest_id=gid).order_by(desc(Payment.due_date)).all(); current_stay=next((s for s in stays if s.status == 'ATIVA'), None); current_room_id=(current_stay.room_id if current_stay else g.room_id)
  all_rooms=db.query(Room).filter(Room.active == True).order_by(Room.number).all()
  if g.room_id and not any(r.id == g.room_id for r in all_rooms):
   current_room=db.get(Room,g.room_id)
   if current_room: all_rooms.append(current_room)
  rooms={r.id:r.number for r in db.query(Room).all()}
  history=[{'kind':'Hospedagem','room_id':s.room_id,'start':s.check_in,'end':s.actual_check_out or s.expected_check_out,'value':s.value,'status':s.status} for s in stays]
  history+=[{'kind':'Reserva','room_id':b.room_id,'start':b.check_in,'end':b.check_out,'value':b.value,'status':b.status} for b in bookings]
  history.sort(key=lambda h:h['start'],reverse=True)
 return render_template('guest_detail.html',g=g,stays=stays,bookings=bookings,pays=pays,rooms=rooms,rooms_list=all_rooms,now=datetime.now(),current_room_id=current_room_id,history=history)


@app.route('/stays')
@auth_required
def stays_page():
    q=request.args.get('q','').strip(); status=request.args.get('status','').strip(); room_id=request.args.get('room_id',type=int)
    period,period_value,period_start,period_end=parse_period_args()
    with SessionLocal() as db:
        # Hospedagens encerradas saem do painel; permanecem visíveis apenas no histórico da hóspede.
        query=db.query(Stay,Guest,Room).join(Guest,Guest.id==Stay.guest_id).join(Room,Room.id==Stay.room_id).filter(Stay.status.notin_(['ENCERRADA','FINALIZADA']))
        if q: query=query.filter(or_(Guest.full_name.ilike(f'%{q}%'),Room.number.ilike(f'%{q}%')))
        if status: query=query.filter(Stay.status==status)
        if room_id: query=query.filter(Stay.room_id==room_id)
        if period_start and period_end: query=query.filter(Stay.check_in>=period_start,Stay.check_in<period_end)
        rows=query.order_by(desc(Stay.check_in)).all()
        rooms=db.query(Room).filter_by(active=True).order_by(Room.number).all()
        guests=db.query(Guest).order_by(Guest.full_name).all()
        type_pricing={t.id:{'rent':money(t.rent_value),'daily':money(t.daily_value)} for t in db.query(RoomType).all()}
        summary={'total':len(rows),'ativas':sum(x.status=='ATIVA' for x,_,__ in rows),'agendadas':sum(x.status in ('AGENDADA','PENDENTE') for x,_,__ in rows)}
    return render_template('stays.html',rows=rows,rooms=rooms,guests=guests,summary=summary,q=q,status=status,room_id=room_id,type_pricing=type_pricing,period=period,period_value=period_value)

@app.route('/stays/new',methods=['POST'])
@auth_required
def new_stay():
    guest_id=request.form.get('guest_id',type=int); room_id=request.form.get('room_id',type=int)
    ci=parse_dt(request.form.get('check_in','')); co=parse_dt(request.form.get('expected_check_out',''))
    has_checkout = request.form.get('has_expected_check_out') == 'on'
    try:
        value=Decimal(request.form.get('value','0').replace(',','.'))
        deposit=Decimal(request.form.get('deposit','0').replace(',','.'))
    except Exception:
        flash('Informe valores financeiros válidos.', 'danger')
        return redirect(url_for('stays_page'))
    if not guest_id or not room_id or not ci or (has_checkout and (not co or co<=ci)):
        flash('Informe hóspede, unidade e uma data válida quando houver saída prevista.','danger'); return redirect(url_for('stays_page'))
    technical_end = co or (ci.replace(year=ci.year + 10) if ci.year <= 9990 else ci)
    with SessionLocal() as db:
        guest=db.get(Guest,guest_id); room=db.get(Room,room_id)
        if not guest or not room: flash('Hóspede ou unidade não encontrada.','danger'); return redirect(url_for('stays_page'))
        active_guest=db.query(Stay).filter(Stay.guest_id==guest_id,Stay.status=='ATIVA').first()
        active_room=db.query(Stay).filter(Stay.room_id==room_id,Stay.status=='ATIVA').first()
        if active_guest: flash(f'{guest.full_name} já está hospedada em outra unidade.','danger'); return redirect(url_for('stays_page'))
        if active_room: flash('A unidade já possui uma hospedagem ativa.','danger'); return redirect(url_for('stays_page'))
        st=Stay(guest_id=guest_id,room_id=room_id,check_in=ci,expected_check_out=technical_end,has_expected_check_out=has_checkout,value=value,deposit=deposit,status='ATIVA')
        db.add(st); room.status='OCUPADO'
        db.add(Notification(title='Novo check-in',message=f'{guest.full_name} entrou no quarto {room.number}.',created_for_user_id=session.get('user_id'))); db.commit()
    flash('Hospedagem registrada com sucesso.','success'); return redirect(url_for('stays_page'))

@app.route('/stays/<int:sid>/checkout',methods=['POST'])
@auth_required
def checkout_stay(sid):
    with SessionLocal() as db:
        st=db.get(Stay,sid)
        if not st: flash('Hospedagem não encontrada.','danger'); return redirect(url_for('stays_page'))
        room=db.get(Room,st.room_id); guest=db.get(Guest,st.guest_id); st.status='ENCERRADA'; st.actual_check_out=datetime.now();
        if room: room.status='LIMPEZA'; db.add(Cleaning(room_id=room.id,area='Quarto',date=datetime.now(),status='AGENDADA',notes='Limpeza gerada automaticamente após check-out.'))
        db.add(Notification(title='Check-out realizado',message=f'{guest.full_name if guest else "Hóspede"} saiu do quarto {room.number if room else ""}. Limpeza criada.',created_for_user_id=session.get('user_id'))); db.commit()
    flash('Check-out realizado. A unidade foi enviada para limpeza.','success'); return redirect(url_for('stays_page'))

@app.route('/bookings')
@auth_required
def bookings_page():
    q=request.args.get('q','').strip(); status=request.args.get('status','').strip(); room_id=request.args.get('room_id',type=int)
    period,period_value,period_start,period_end=parse_period_args()
    with SessionLocal() as db:
        # Reservas canceladas saem do painel; permanecem visíveis apenas no histórico da hóspede.
        query=db.query(Booking,Guest,Room).join(Guest,Guest.id==Booking.guest_id).join(Room,Room.id==Booking.room_id).filter(Booking.status!='CANCELADA')
        if q: query=query.filter(or_(Guest.full_name.ilike(f'%{q}%'),Room.number.ilike(f'%{q}%')))
        if status: query=query.filter(Booking.status==status)
        if room_id: query=query.filter(Booking.room_id==room_id)
        if period_start and period_end: query=query.filter(Booking.check_in>=period_start,Booking.check_in<period_end)
        rows=query.order_by(desc(Booking.check_in)).all(); rooms=db.query(Room).filter_by(active=True).order_by(Room.number).all(); guests=db.query(Guest).order_by(Guest.full_name).all()
        type_pricing={t.id:{'rent':money(t.rent_value),'daily':money(t.daily_value)} for t in db.query(RoomType).all()}
        summary={'total':len(rows),'confirmadas':sum(x.status=='CONFIRMADA' for x,_,__ in rows),'pre':sum(x.status=='PRÉ-RESERVA' for x,_,__ in rows)}
    return render_template('bookings.html',rows=rows,rooms=rooms,guests=guests,summary=summary,q=q,status=status,room_id=room_id,type_pricing=type_pricing,period=period,period_value=period_value)

@app.route('/bookings/new',methods=['POST'])
@auth_required
def new_booking():
    guest_id=request.form.get('guest_id',type=int); room_id=request.form.get('room_id',type=int); ci=parse_dt(request.form.get('check_in','')); co=parse_dt(request.form.get('check_out','')); booking_type=request.form.get('booking_type','HOSPEDAGEM'); status=request.form.get('status','PRÉ-RESERVA');
    try: value=Decimal(request.form.get('value','0').replace(',','.'))
    except: value=Decimal('0')
    if booking_type not in ('DIÁRIA','HOSPEDAGEM'): flash('Tipo de reserva inválido.','danger'); return redirect(url_for('bookings_page'))
    if not guest_id or not room_id or not ci or not co or co<=ci: flash('Informe hóspede, unidade e período válido.','danger'); return redirect(url_for('bookings_page'))
    if (co - ci).days > 31: flash('As reservas devem ter duração máxima de 31 dias. Para permanências maiores, registre um check-in em Hospedagens.','danger'); return redirect(url_for('bookings_page'))
    with SessionLocal() as db:
        guest=db.get(Guest,guest_id); room=db.get(Room,room_id)
        conflict=db.query(Booking).filter(Booking.room_id==room_id,Booking.status!='CANCELADA',Booking.check_in<co,Booking.check_out>ci).first()
        active=db.query(Stay).filter(Stay.room_id==room_id,Stay.status=='ATIVA',Stay.check_in<co,Stay.expected_check_out>ci).first()
        if not guest or not room: flash('Hóspede ou unidade não encontrada.','danger'); return redirect(url_for('bookings_page'))
        if conflict or active: flash('A unidade já está ocupada ou reservada nesse período.','danger'); return redirect(url_for('bookings_page'))
        b=Booking(guest_id=guest_id,room_id=room_id,check_in=ci,check_out=co,value=value,booking_type=booking_type,status=status,notes=request.form.get('notes') or None); db.add(b)
        if status=='CONFIRMADA' and room.status=='DISPONÍVEL': room.status='RESERVADO'
        db.add(Notification(title='Nova reserva',message=f'Reserva de {guest.full_name} para o quarto {room.number}.',created_for_user_id=session.get('user_id'))); db.commit()
    flash('Reserva cadastrada com sucesso.','success'); return redirect(url_for('bookings_page'))

@app.route('/bookings/<int:bid>/status/<status>',methods=['POST'])
@auth_required
def booking_status(bid,status):
    if status not in ('PRÉ-RESERVA','CONFIRMADA','CANCELADA','CONCLUÍDA'): flash('Status inválido.','danger'); return redirect(url_for('bookings_page'))
    with SessionLocal() as db:
        b=db.get(Booking,bid)
        if not b: flash('Reserva não encontrada.','danger'); return redirect(url_for('bookings_page'))
        b.status=status; room=db.get(Room,b.room_id)
        if room and status=='CONFIRMADA' and room.status=='DISPONÍVEL': room.status='RESERVADO'
        if room and status in ('CANCELADA','CONCLUÍDA') and room.status=='RESERVADO':
            active_booking=db.query(Booking).filter(Booking.room_id==b.room_id, Booking.status.in_(['PRÉ-RESERVA','CONFIRMADA']), Booking.id!=b.id).first()
            active_stay=db.query(Stay).filter(Stay.room_id==b.room_id, Stay.status=='ATIVA').first()
            if not active_booking and not active_stay: room.status='DISPONÍVEL'
        db.add(Notification(title='Reserva atualizada',message=f'Reserva #{b.id} agora está {status.lower()}.',created_for_user_id=session.get('user_id'))); db.commit()
    flash('Status da reserva atualizado.','success'); return redirect(url_for('bookings_page'))

@app.route('/guests/new',methods=['POST'])
@auth_required
def new_guest():
    data={k:(request.form.get(k,'').strip() or None) for k in ['full_name','cpf','rg','phone','whatsapp','email','address','city','state','emergency_contact','notes']}
    birth=request.form.get('birth_date','').strip()
    required_fields = {'full_name':'nome completo','cpf':'CPF','rg':'RG','whatsapp':'WhatsApp','address':'endereço','city':'cidade','state':'UF','emergency_contact':'contato de emergência'}
    missing = [label for field,label in required_fields.items() if not data[field]]
    if birth == '': missing.append('data de nascimento')
    if missing:
        flash('Preencha os campos obrigatórios: ' + ', '.join(missing) + '.','danger'); return redirect(url_for('guests'))
    try: data['birth_date']=date.fromisoformat(birth) if birth else None
    except: flash('Informe uma data de nascimento válida.','danger'); return redirect(url_for('guests'))
    room_id=request.form.get('room_id',type=int)
    with SessionLocal() as db:
        if data.get('cpf') and db.query(Guest).filter(Guest.cpf==data['cpf']).first(): flash('Já existe uma hóspede com este CPF.','danger'); return redirect(url_for('guests'))
        if room_id:
            room = db.query(Room).filter(Room.id == room_id, Room.active == True).first()
            if not room or room.status != 'DISPONÍVEL':
                flash('Selecione uma unidade ativa e disponível, ou deixe o campo sem unidade.', 'danger')
                return redirect(url_for('guests'))
            occupied = db.query(Stay).filter(Stay.room_id == room_id, Stay.status == 'ATIVA').first()
            if occupied:
                flash('A unidade selecionada já possui uma hospedagem ativa.', 'danger')
                return redirect(url_for('guests'))
        g=Guest(**data,room_id=room_id); db.add(g); db.commit(); gid=g.id
    flash('Hóspede cadastrada com sucesso.','success'); return redirect(url_for('guest_detail',gid=gid))

@app.route('/guests/<int:gid>/edit',methods=['POST'])
@auth_required
def edit_guest(gid):
    with SessionLocal() as db:
        g=db.get(Guest,gid)
        if not g: flash('Hóspede não encontrada.','danger'); return redirect(url_for('guests'))
        for k in ['full_name','cpf','rg','phone','whatsapp','email','address','city','state','emergency_contact','notes']: setattr(g,k,request.form.get(k,'').strip() or None)
        birth=request.form.get('birth_date','').strip(); g.birth_date=date.fromisoformat(birth) if birth else None
        room_id=request.form.get('room_id',type=int)
        if room_id:
            room=db.query(Room).filter(Room.id == room_id, Room.active == True).first()
            occupied=db.query(Stay).filter(Stay.room_id == room_id, Stay.status == 'ATIVA', Stay.guest_id != gid).first()
            if not room or (room.status != 'DISPONÍVEL' and room_id != g.room_id) or occupied:
                flash('Selecione uma unidade ativa e disponível, ou mantenha a unidade atual.', 'danger'); return redirect(url_for('guest_detail',gid=gid))
        g.room_id=room_id
        db.commit()
    flash('Dados da hóspede atualizados.','success'); return redirect(url_for('guest_detail',gid=gid))

@app.route('/finance/payment/new',methods=['POST'])
@auth_required
def new_payment():
    guest_id=request.form.get('guest_id',type=int) or None; room_id=request.form.get('room_id',type=int) or None; desc=request.form.get('description','').strip(); due=parse_dt(request.form.get('due_date','')); method=request.form.get('method') or None; status=request.form.get('status','PENDENTE'); notes=request.form.get('notes') or None
    try: amount=Decimal(request.form.get('amount','0').replace(',','.'))
    except: amount=Decimal('0')
    if not desc or not due or amount<0: flash('Preencha descrição, vencimento e valor válidos.','danger'); return redirect(url_for('finance'))
    paid_at=datetime.now() if status=='PAGO' else None
    with SessionLocal() as db: db.add(Payment(guest_id=guest_id,room_id=room_id,description=desc,amount=amount,due_date=due,paid_at=paid_at,method=method,status=status,notes=notes)); db.commit()
    flash('Pagamento lançado com sucesso.','success'); return redirect(url_for('finance'))

@app.route('/finance/expense/new',methods=['POST'])
@auth_required
def new_expense():
    desc=request.form.get('description','').strip(); category=request.form.get('category','').strip(); dt=parse_dt(request.form.get('date','')); status=request.form.get('status','PENDENTE'); notes=request.form.get('notes') or None
    try: amount=Decimal(request.form.get('amount','0').replace(',','.'))
    except: amount=Decimal('0')
    if not desc or not category or not dt or amount<0: flash('Preencha descrição, categoria, data e valor válidos.','danger'); return redirect(url_for('finance'))
    with SessionLocal() as db: db.add(Expense(description=desc,category=category,amount=amount,date=dt,status=status,notes=notes)); db.commit()
    flash('Despesa lançada com sucesso.','success'); return redirect(url_for('finance'))

@app.route('/finance/expense/<int:eid>/edit',methods=['POST'])
@auth_required
def edit_expense(eid):
    desc=request.form.get('description','').strip(); category=request.form.get('category','').strip(); dt=parse_dt(request.form.get('date','')); status=request.form.get('status','PENDENTE'); notes=request.form.get('notes') or None
    try: amount=Decimal(request.form.get('amount','0').replace(',','.'))
    except: amount=Decimal('0')
    if not desc or not category or not dt or amount<0: flash('Preencha descrição, categoria, data e valor válidos.','danger'); return redirect(url_for('finance',kind='DESPESAS'))
    if status not in ('PAGO','PENDENTE','ATRASADO','CANCELADO'): flash('Status inválido.','danger'); return redirect(url_for('finance',kind='DESPESAS'))
    with SessionLocal() as db:
        e=db.get(Expense,eid)
        if not e: flash('Despesa não encontrada.','danger'); return redirect(url_for('finance',kind='DESPESAS'))
        e.description=desc; e.category=category; e.amount=amount; e.date=dt; e.status=status; e.notes=notes
        db.commit()
    flash('Despesa atualizada com sucesso.','success'); return redirect(url_for('finance',kind='DESPESAS'))

@app.route('/finance/expense/<int:eid>/status/<status>',methods=['POST'])
@auth_required
def expense_status(eid,status):
    if status not in ('PAGO','PENDENTE','ATRASADO','CANCELADO'): return redirect(url_for('finance',kind='DESPESAS'))
    with SessionLocal() as db:
        e=db.get(Expense,eid)
        if e: e.status=status; db.commit(); flash('Status da despesa atualizado.','success')
    return redirect(url_for('finance',kind='DESPESAS'))

@app.route('/finance/payment/<int:pid>/status/<status>',methods=['POST'])
@auth_required
def payment_status(pid,status):
    if status not in ('PAGO','PENDENTE','ATRASADO','CANCELADO'): return redirect(url_for('finance'))
    with SessionLocal() as db:
        p=db.get(Payment,pid)
        if p: p.status=status; p.paid_at=datetime.now() if status=='PAGO' else None; db.commit(); flash('Status do pagamento atualizado.','success')
    return redirect(url_for('finance'))

@app.route('/finance/payment/<int:pid>/edit',methods=['POST'])
@auth_required
def edit_payment(pid):
    guest_id=request.form.get('guest_id',type=int) or None; room_id=request.form.get('room_id',type=int) or None; desc=request.form.get('description','').strip(); due=parse_dt(request.form.get('due_date','')); method=request.form.get('method') or None; status=request.form.get('status','PENDENTE'); notes=request.form.get('notes') or None
    try: amount=Decimal(request.form.get('amount','0').replace(',','.'))
    except: amount=Decimal('0')
    if not desc or not due or amount<0: flash('Preencha descrição, vencimento e valor válidos.','danger'); return redirect(url_for('finance'))
    if status not in ('PAGO','PENDENTE','ATRASADO','CANCELADO'): flash('Status inválido.','danger'); return redirect(url_for('finance'))
    with SessionLocal() as db:
        p=db.get(Payment,pid)
        if not p: flash('Pagamento não encontrado.','danger'); return redirect(url_for('finance'))
        p.guest_id=guest_id; p.room_id=room_id; p.description=desc; p.amount=amount; p.due_date=due; p.method=method; p.status=status; p.notes=notes
        p.paid_at=datetime.now() if status=='PAGO' else None
        db.commit()
    flash('Pagamento atualizado com sucesso.','success'); return redirect(url_for('finance'))

@app.route('/calendar')
@auth_required
def calendar():
    with SessionLocal() as db:
        bookings = db.query(Booking).filter(Booking.status != 'CANCELADA').order_by(Booking.check_in).all()
        stays = db.query(Stay).filter(Stay.status == 'ATIVA').order_by(Stay.check_in).all()
        guests = {g.id: g.full_name for g in db.query(Guest).all()}
        rooms = {r.id: r.number for r in db.query(Room).all()}
        events = []

        # O calendário mostra somente dois marcadores por registro:
        # um no check-in e outro no check-out. Assim, não cria barras longas
        # que ocupam todo o período e deixam a agenda poluída.
        active_pairs = []

        def add_markers(prefix, entity_id, guest, room, check_in, check_out, status, css_class, editable=True, show_checkout=True):
            base_props = {
                'guest': guest,
                'room': room,
                'checkIn': check_in.strftime('%d/%m/%Y %H:%M'),
                'checkOut': check_out.strftime('%d/%m/%Y %H:%M') if check_out else 'Sem data definida',
                'status': status,
                'originalCheckIn': check_in.isoformat(),
                'originalCheckOut': check_out.isoformat() if check_out else None,
                'entityKind': prefix,
            }
            events.append({
                'id': f'{prefix}-in-{entity_id}',
                'title': f'↗ Check-in • {guest} • {room}',
                'start': check_in.isoformat(),
                'allDay': False,
                'className': 'event-checkin-marker ' + css_class,
                'editable': editable,
                'extendedProps': {**base_props, 'kind': 'checkin_marker', 'marker': 'checkin'},
            })
            if not show_checkout:
                return
            events.append({
                'id': f'{prefix}-out-{entity_id}',
                'title': f'↘ Check-out • {guest} • {room}',
                'start': check_out.isoformat(),
                'allDay': False,
                'className': 'event-checkout-marker',
                'editable': False,
                'extendedProps': {**base_props, 'kind': 'checkout_marker', 'marker': 'checkout'},
            })

        for st in stays:
            guest = guests.get(st.guest_id, 'Hóspede')
            room = rooms.get(st.room_id, '?')
            end = st.actual_check_out or (st.expected_check_out if getattr(st, 'has_expected_check_out', True) else None)
            conflict_end = end or (st.check_in.replace(year=st.check_in.year + 10) if st.check_in.year <= 9990 else st.check_in)
            active_pairs.append((st.guest_id, st.room_id, st.check_in, conflict_end))
            add_markers('stay', st.id, guest, room, st.check_in, end, 'HOSPEDAGEM ATIVA', 'event-hospedada', editable=bool(getattr(st, 'has_expected_check_out', True)), show_checkout=bool(end))

        for b in bookings:
            # Se a reserva já virou hospedagem ativa, exibe somente os marcadores da hospedagem.
            duplicated = any(
                guest_id == b.guest_id and room_id == b.room_id
                and check_in < b.check_out and end > b.check_in
                for guest_id, room_id, check_in, end in active_pairs
            )
            if duplicated:
                continue
            guest = guests.get(b.guest_id, 'Hóspede')
            room = rooms.get(b.room_id, '?')
            add_markers('booking', b.id, guest, room, b.check_in, b.check_out, b.status, 'event-reserva')
    return render_template('calendar.html', events=events)


@app.route('/calendar/move', methods=['POST'])
@auth_required
def move_calendar_event():
    data = request.get_json(silent=True) or {}
    event_id = str(data.get('id', ''))
    start = parse_dt(data.get('start', ''))
    end = parse_dt(data.get('end', ''))
    if not event_id or not start or not end or end <= start:
        return jsonify({'ok': False, 'message': 'Período inválido.'}), 400
    try:
        parts = event_id.split('-')
        kind, marker, raw_id = parts[0], parts[1], '-'.join(parts[2:])
        entity_id = int(raw_id)
    except (ValueError, AttributeError, IndexError):
        return jsonify({'ok': False, 'message': 'Evento inválido.'}), 400
    if marker != 'in':
        return jsonify({'ok': False, 'message': 'Somente o marcador de check-in pode ser arrastado.'}), 400
    with SessionLocal() as db:
        if kind == 'booking':
            item = db.get(Booking, entity_id)
            if not item or item.status == 'CANCELADA':
                return jsonify({'ok': False, 'message': 'Reserva não encontrada ou cancelada.'}), 404
            conflict = db.query(Booking).filter(
                Booking.id != item.id, Booking.room_id == item.room_id, Booking.status != 'CANCELADA',
                Booking.check_in < end, Booking.check_out > start
            ).first()
            active = db.query(Stay).filter(
                Stay.room_id == item.room_id, Stay.status == 'ATIVA',
                Stay.check_in < end, Stay.expected_check_out > start
            ).first()
            if conflict or active:
                return jsonify({'ok': False, 'message': 'A unidade já está ocupada ou reservada nesse período.'}), 409
            item.check_in, item.check_out = start, end
            label = 'Reserva'
        elif kind == 'stay':
            item = db.get(Stay, entity_id)
            if not item or item.status != 'ATIVA':
                return jsonify({'ok': False, 'message': 'Hospedagem ativa não encontrada.'}), 404
            conflict = db.query(Stay).filter(
                Stay.id != item.id, Stay.room_id == item.room_id, Stay.status == 'ATIVA',
                Stay.check_in < end, Stay.expected_check_out > start
            ).first()
            booking_conflict = db.query(Booking).filter(
                Booking.room_id == item.room_id, Booking.status != 'CANCELADA',
                Booking.check_in < end, Booking.check_out > start
            ).first()
            if conflict or booking_conflict:
                return jsonify({'ok': False, 'message': 'Existe conflito com outra hospedagem ou reserva.'}), 409
            item.check_in, item.expected_check_out = start, end
            label = 'Hospedagem'
        else:
            return jsonify({'ok': False, 'message': 'Este evento não pode ser movido.'}), 400
        db.add(Notification(title='Calendário atualizado', message=f'{label} #{entity_id} foi remanejada.', created_for_user_id=session.get('user_id')))
        db.commit()
    return jsonify({'ok': True, 'message': f'{label} atualizada com sucesso.'})


def resolve_period_filter(period,period_value):
    """Retorna (inicio,fim) como datetimes half-open [inicio,fim) para o período informado,
    ou (None,None) se period_value for inválido."""
    try:
        if period=='TODOS':
            return None,None
        if period=='DIA':
            d=date.fromisoformat(period_value)
            start=datetime.combine(d,datetime.min.time()); end=start+timedelta(days=1)
        elif period=='SEMANA':
            start=datetime.strptime(period_value+'-1','%G-W%V-%u'); end=start+timedelta(days=7)
        elif period=='ANO':
            year=int(period_value); start=datetime(year,1,1); end=datetime(year+1,1,1)
        else:
            year,month=(int(x) for x in period_value.split('-'))
            start=datetime(year,month,1); end=datetime(year+1,1,1) if month==12 else datetime(year,month+1,1)
        return start,end
    except (ValueError,TypeError):
        return None,None

def parse_period_args(period_key='period',value_key='period_value'):
    """Lê os parâmetros de período (dia/semana/mês/ano/todos) da querystring, com mês atual como padrão."""
    period=request.args.get(period_key,'MES').strip().upper()
    if period not in ('DIA','SEMANA','MES','ANO','TODOS'): period='MES'
    today=date.today()
    default_value={'DIA':today.isoformat(),'SEMANA':f'{today.isocalendar()[0]}-W{today.isocalendar()[1]:02d}','MES':today.strftime('%Y-%m'),'ANO':str(today.year),'TODOS':''}[period]
    period_value=request.args.get(value_key,'').strip() or default_value
    start,end=resolve_period_filter(period,period_value)
    return period,period_value,start,end

@app.route('/finance')
@auth_required
def finance():
 q=request.args.get('q','').strip(); status=request.args.get('status',''); kind=request.args.get('kind','PAGAMENTOS')
 if kind not in ('PAGAMENTOS','DESPESAS'): kind='PAGAMENTOS'
 period,period_value,period_start,period_end=parse_period_args()
 with SessionLocal() as db:
  payment_query=db.query(Payment)
  if kind=='PAGAMENTOS':
   if q: payment_query=payment_query.filter(or_(Payment.description.ilike(f'%{q}%'),Payment.notes.ilike(f'%{q}%')))
   if status: payment_query=payment_query.filter(Payment.status==status)
   if period_start and period_end: payment_query=payment_query.filter(Payment.due_date>=period_start,Payment.due_date<period_end)
  pays=payment_query.order_by(desc(Payment.due_date)).all()

  expense_query=db.query(Expense)
  if kind=='DESPESAS':
   if q: expense_query=expense_query.filter(or_(Expense.description.ilike(f'%{q}%'),Expense.category.ilike(f'%{q}%'),Expense.notes.ilike(f'%{q}%')))
   if status: expense_query=expense_query.filter(Expense.status==status)
   if period_start and period_end: expense_query=expense_query.filter(Expense.date>=period_start,Expense.date<period_end)
  expenses=expense_query.order_by(desc(Expense.date)).limit(100).all()

  payment_total_count=db.query(Payment).count(); expense_total_count=db.query(Expense).count()
  total_p=money(db.query(func.coalesce(func.sum(Payment.amount),0)).filter(Payment.status=='PAGO').scalar())
  total_e=money(db.query(func.coalesce(func.sum(Expense.amount),0)).scalar())
  pending=money(db.query(func.coalesce(func.sum(Payment.amount),0)).filter(Payment.status.in_(['PENDENTE','ATRASADO'])).scalar())
  overdue=db.query(Payment).filter(Payment.status=='ATRASADO').count()
  guests=db.query(Guest).order_by(Guest.full_name).all(); rooms=db.query(Room).filter_by(active=True).order_by(Room.number).all()
  guests_map={g.id:g.full_name for g in guests}; rooms_map={r.id:r.number for r in db.query(Room).all()}
 return render_template('finance.html',pays=pays,expenses=expenses,total_p=total_p,total_e=total_e,pending=pending,overdue=overdue,q=q,status=status,kind=kind,guests=guests,rooms=rooms,guests_map=guests_map,rooms_map=rooms_map,payment_total_count=payment_total_count,expense_total_count=expense_total_count,period=period,period_value=period_value)

def _refresh_operation_room(db, room_id):
    """Atualiza o status operacional da unidade sem sobrescrever OCUPADO/RESERVADO."""
    room = db.get(Room, room_id)
    if not room:
        return
    if room.status not in ('LIMPEZA', 'MANUTENÇÃO'):
        return
    active_clean = db.query(Cleaning).filter(
        Cleaning.room_id == room_id,
        Cleaning.status.in_(['AGENDADA', 'PENDENTE', 'EM ANDAMENTO'])
    ).first()
    active_maint = db.query(Maintenance).filter(
        Maintenance.room_id == room_id,
        Maintenance.status.in_(['ABERTO', 'PENDENTE', 'EM ANDAMENTO'])
    ).first()
    if active_clean:
        room.status = 'LIMPEZA'
    elif active_maint:
        room.status = 'MANUTENÇÃO'
    else:
        room.status = 'DISPONÍVEL'


@app.route('/operations')
@auth_required
def operations():
    clean_status = request.args.get('clean_status', '').strip()
    clean_room = request.args.get('clean_room', type=int)
    clean_responsible = request.args.get('clean_responsible', '').strip()
    clean_q = request.args.get('clean_q', '').strip()
    clean_period,clean_period_value,clean_period_start,clean_period_end = parse_period_args('clean_period','clean_period_value')
    maint_status = request.args.get('maint_status', '').strip()
    maint_priority = request.args.get('maint_priority', '').strip()
    maint_room = request.args.get('maint_room', type=int)
    maint_responsible = request.args.get('maint_responsible', '').strip()
    maint_q = request.args.get('maint_q', '').strip()
    with SessionLocal() as db:
        clean_query = db.query(Cleaning).join(Room, Room.id == Cleaning.room_id)
        if clean_status:
            clean_query = clean_query.filter(Cleaning.status == clean_status)
        if clean_room:
            clean_query = clean_query.filter(Cleaning.room_id == clean_room)
        if clean_responsible:
            clean_query = clean_query.filter(Cleaning.responsible.ilike(f'%{clean_responsible}%'))
        if clean_q:
            clean_query = clean_query.filter(or_(Cleaning.area.ilike(f'%{clean_q}%'), Cleaning.notes.ilike(f'%{clean_q}%'), Room.number.ilike(f'%{clean_q}%')))
        if clean_period_start and clean_period_end:
            clean_query = clean_query.filter(Cleaning.date >= clean_period_start, Cleaning.date < clean_period_end)
        clean = clean_query.order_by(desc(Cleaning.date)).all()

        maint_query = db.query(Maintenance).outerjoin(Room, Room.id == Maintenance.room_id)
        if maint_status:
            maint_query = maint_query.filter(Maintenance.status == maint_status)
        if maint_priority:
            maint_query = maint_query.filter(Maintenance.priority == maint_priority)
        if maint_room:
            maint_query = maint_query.filter(Maintenance.room_id == maint_room)
        if maint_responsible:
            maint_query = maint_query.filter(Maintenance.responsible.ilike(f'%{maint_responsible}%'))
        if maint_q:
            maint_query = maint_query.filter(or_(Maintenance.location.ilike(f'%{maint_q}%'), Maintenance.description.ilike(f'%{maint_q}%'), Maintenance.notes.ilike(f'%{maint_q}%'), Room.number.ilike(f'%{maint_q}%')))
        maint = maint_query.order_by(desc(Maintenance.date)).all()

        rooms = {r.id:r.number for r in db.query(Room).order_by(Room.number).all()}
        clean_responsibles = sorted({x.responsible for x in db.query(Cleaning).filter(Cleaning.responsible.isnot(None)).all() if x.responsible})
        maint_responsibles = sorted({x.responsible for x in db.query(Maintenance).filter(Maintenance.responsible.isnot(None)).all() if x.responsible})
        clean_total = db.query(Cleaning).count()
        maint_total = db.query(Maintenance).count()

    clean_summary = {
        'total': len(clean),
        'pendente': sum(1 for x in clean if x.status in ('PENDENTE','AGENDADA')),
        'andamento': sum(1 for x in clean if x.status == 'EM ANDAMENTO'),
        'concluida': sum(1 for x in clean if x.status in ('CONCLUÍDA','REALIZADA')),
    }
    maint_summary = {
        'total': len(maint),
        'pendente': sum(1 for x in maint if x.status in ('ABERTO','PENDENTE')),
        'andamento': sum(1 for x in maint if x.status == 'EM ANDAMENTO'),
        'concluida': sum(1 for x in maint if x.status in ('CONCLUÍDO','CONCLUÍDA','FECHADO')),
        'urgente': sum(1 for x in maint if x.priority == 'URGENTE' and x.status not in ('CONCLUÍDO','CONCLUÍDA','FECHADO','CANCELADO','CANCELADA')),
    }
    return render_template('operations.html', maint=maint, clean=clean, rooms=rooms,
        clean_summary=clean_summary, maint_summary=maint_summary, clean_total=clean_total, maint_total=maint_total,
        clean_status=clean_status, clean_room=clean_room, clean_responsible=clean_responsible, clean_q=clean_q,
        clean_period=clean_period, clean_period_value=clean_period_value,
        maint_status=maint_status, maint_priority=maint_priority, maint_room=maint_room, maint_responsible=maint_responsible, maint_q=maint_q, clean_responsibles=clean_responsibles, maint_responsibles=maint_responsibles)

@app.route('/operations/cleaning/new', methods=['POST'])
@auth_required
def new_cleaning():
    room_id = request.form.get('room_id', type=int)
    area = request.form.get('area', '').strip()
    date_value = request.form.get('date', '').strip()
    responsible = request.form.get('responsible', '').strip() or None
    status = request.form.get('status', 'AGENDADA').strip()
    notes = request.form.get('notes', '').strip() or None
    allowed = ('AGENDADA','PENDENTE','EM ANDAMENTO','CONCLUÍDA','CANCELADA')
    if not room_id or not area or not date_value:
        flash('Preencha quarto, área e data da tarefa de limpeza.', 'danger')
        return redirect(url_for('operations') + '#limpeza')
    if status not in allowed:
        flash('Status de limpeza inválido.', 'danger')
        return redirect(url_for('operations') + '#limpeza')
    try:
        task_date = datetime.fromisoformat(date_value)
    except ValueError:
        flash('Data da limpeza inválida.', 'danger')
        return redirect(url_for('operations') + '#limpeza')
    with SessionLocal() as db:
        room = db.get(Room, room_id)
        if not room:
            flash('Quarto não encontrado.', 'danger')
            return redirect(url_for('operations') + '#limpeza')
        task = Cleaning(room_id=room_id, area=area, date=task_date, responsible=responsible, status=status, notes=notes)
        db.add(task)
        if status in ('AGENDADA','PENDENTE','EM ANDAMENTO') and room.status == 'DISPONÍVEL':
            room.status = 'LIMPEZA'
        db.add(Notification(title='Nova tarefa de limpeza', message=f'Limpeza do quarto {room.number} foi cadastrada.', created_for_user_id=session.get('user_id')))
        db.commit()
    flash('Tarefa de limpeza cadastrada com sucesso.', 'success')
    return redirect(url_for('operations') + '#limpeza')

@app.route('/operations/cleaning/<int:cid>/edit', methods=['POST'])
@auth_required
def edit_cleaning(cid):
    room_id = request.form.get('room_id', type=int)
    area = request.form.get('area', '').strip()
    date_value = request.form.get('date', '').strip()
    responsible = request.form.get('responsible', '').strip() or None
    status = request.form.get('status', 'AGENDADA').strip()
    notes = request.form.get('notes', '').strip() or None
    allowed = ('AGENDADA','PENDENTE','EM ANDAMENTO','CONCLUÍDA','CANCELADA')
    if not room_id or not area or not date_value or status not in allowed:
        flash('Preencha os dados da tarefa de limpeza corretamente.', 'danger')
        return redirect(url_for('operations') + '#limpeza')
    try:
        task_date = datetime.fromisoformat(date_value)
    except ValueError:
        flash('Data da limpeza inválida.', 'danger')
        return redirect(url_for('operations') + '#limpeza')
    with SessionLocal() as db:
        task = db.get(Cleaning, cid)
        room = db.get(Room, room_id)
        if not task or not room:
            flash('Tarefa ou quarto não encontrado.', 'danger')
            return redirect(url_for('operations') + '#limpeza')
        old_room_id = task.room_id
        task.room_id, task.area, task.date = room_id, area, task_date
        task.responsible, task.status, task.notes = responsible, status, notes
        if status in ('AGENDADA','PENDENTE','EM ANDAMENTO') and room.status == 'DISPONÍVEL':
            room.status = 'LIMPEZA'
        if old_room_id != room_id:
            _refresh_operation_room(db, old_room_id)
        if status in ('CONCLUÍDA','CANCELADA'):
            _refresh_operation_room(db, room_id)
        db.add(Notification(title='Tarefa de limpeza atualizada', message=f'Limpeza do quarto {room.number} foi atualizada.', created_for_user_id=session.get('user_id')))
        db.commit()
    flash('Tarefa de limpeza atualizada.', 'success')
    return redirect(url_for('operations') + '#limpeza')

@app.route('/operations/cleaning/<int:cid>/status/<status>', methods=['POST'])
@auth_required
def cleaning_status(cid, status):
    if status not in ('AGENDADA','PENDENTE','EM ANDAMENTO','CONCLUÍDA','CANCELADA'):
        flash('Status de limpeza inválido.', 'danger')
        return redirect(url_for('operations') + '#limpeza')
    with SessionLocal() as db:
        task=db.get(Cleaning,cid)
        if not task:
            flash('Tarefa de limpeza não encontrada.', 'danger')
            return redirect(url_for('operations') + '#limpeza')
        task.status=status
        if status in ('AGENDADA','PENDENTE','EM ANDAMENTO'):
            room=db.get(Room,task.room_id)
            if room and room.status == 'DISPONÍVEL': room.status='LIMPEZA'
        else:
            _refresh_operation_room(db, task.room_id)
        db.add(Notification(title='Status de limpeza alterado', message=f'A tarefa do quarto {db.get(Room,task.room_id).number} agora está {status.lower()}.', created_for_user_id=session.get('user_id')))
        db.commit()
    flash('Status da tarefa atualizado.', 'success')
    return redirect(url_for('operations') + '#limpeza')

@app.route('/operations/cleaning/<int:cid>/delete', methods=['POST'])
@auth_required
def delete_cleaning(cid):
    with SessionLocal() as db:
        task=db.get(Cleaning,cid)
        if not task:
            flash('Tarefa de limpeza não encontrada.', 'danger')
            return redirect(url_for('operations') + '#limpeza')
        room_id=task.room_id
        db.delete(task)
        db.flush()
        _refresh_operation_room(db, room_id)
        db.commit()
    flash('Tarefa de limpeza excluída.', 'success')
    return redirect(url_for('operations') + '#limpeza')

@app.route('/operations/maintenance/new', methods=['POST'])
@auth_required
def new_maintenance():
    location = request.form.get('location', '').strip()
    room_id = request.form.get('room_id', type=int) or None
    description = request.form.get('description', '').strip()
    date_value = request.form.get('date', '').strip()
    priority = request.form.get('priority', 'MÉDIA').strip()
    responsible = request.form.get('responsible', '').strip() or None
    status = request.form.get('status', 'ABERTO').strip()
    cost_raw = request.form.get('cost', '').strip().replace(',', '.')
    notes = request.form.get('notes', '').strip() or None
    allowed_status=('ABERTO','PENDENTE','EM ANDAMENTO','CONCLUÍDO','CANCELADO')
    if not location or not description or not date_value or status not in allowed_status:
        flash('Preencha local, problema, data e status corretamente.', 'danger')
        return redirect(url_for('operations') + '#manutencao')
    try:
        maintenance_date = datetime.fromisoformat(date_value)
        cost = Decimal(cost_raw or '0')
    except (ValueError, ArithmeticError):
        flash('Data ou custo inválido.', 'danger')
        return redirect(url_for('operations') + '#manutencao')
    with SessionLocal() as db:
        if room_id and not db.get(Room, room_id):
            flash('Quarto selecionado não encontrado.', 'danger')
            return redirect(url_for('operations') + '#manutencao')
        item = Maintenance(location=location, room_id=room_id, description=description, date=maintenance_date, priority=priority, responsible=responsible, status=status, cost=cost, notes=notes)
        db.add(item)
        if room_id and status in ('ABERTO','PENDENTE','EM ANDAMENTO'):
            room = db.get(Room, room_id)
            if room and room.status == 'DISPONÍVEL': room.status = 'MANUTENÇÃO'
        db.add(Notification(title='Novo chamado de manutenção', message=f'{location}: {description}', created_for_user_id=session.get('user_id')))
        db.commit()
    flash('Chamado de manutenção cadastrado com sucesso.', 'success')
    return redirect(url_for('operations') + '#manutencao')

@app.route('/operations/maintenance/<int:mid>/edit', methods=['POST'])
@auth_required
def edit_maintenance(mid):
    location=request.form.get('location','').strip(); room_id=request.form.get('room_id',type=int) or None; description=request.form.get('description','').strip(); date_value=request.form.get('date','').strip(); priority=request.form.get('priority','MÉDIA').strip(); responsible=request.form.get('responsible','').strip() or None; status=request.form.get('status','ABERTO').strip(); cost_raw=request.form.get('cost','').strip().replace(',','.'); notes=request.form.get('notes','').strip() or None
    allowed_status=('ABERTO','PENDENTE','EM ANDAMENTO','CONCLUÍDO','CANCELADO')
    if not location or not description or not date_value or status not in allowed_status:
        flash('Preencha os dados do chamado corretamente.', 'danger'); return redirect(url_for('operations') + '#manutencao')
    try: maintenance_date=datetime.fromisoformat(date_value); cost=Decimal(cost_raw or '0')
    except (ValueError,ArithmeticError): flash('Data ou custo inválido.', 'danger'); return redirect(url_for('operations') + '#manutencao')
    with SessionLocal() as db:
        item=db.get(Maintenance,mid); room=db.get(Room,room_id) if room_id else None
        if not item or (room_id and not room):
            flash('Chamado ou quarto não encontrado.', 'danger'); return redirect(url_for('operations') + '#manutencao')
        old_room_id=item.room_id
        item.location,item.room_id,item.description,item.date=location,room_id,description,maintenance_date
        item.priority,item.responsible,item.status,item.cost,item.notes=priority,responsible,status,cost,notes
        if room_id and status in ('ABERTO','PENDENTE','EM ANDAMENTO') and room and room.status == 'DISPONÍVEL': room.status='MANUTENÇÃO'
        if old_room_id and old_room_id != room_id: _refresh_operation_room(db,old_room_id)
        if room_id and status in ('CONCLUÍDO','CANCELADO'): _refresh_operation_room(db,room_id)
        db.add(Notification(title='Chamado de manutenção atualizado', message=f'{location}: chamado atualizado.', created_for_user_id=session.get('user_id')))
        db.commit()
    flash('Chamado de manutenção atualizado.', 'success'); return redirect(url_for('operations') + '#manutencao')

@app.route('/operations/maintenance/<int:mid>/status/<status>', methods=['POST'])
@auth_required
def maintenance_status(mid,status):
    if status not in ('ABERTO','PENDENTE','EM ANDAMENTO','CONCLUÍDO','CANCELADO'):
        flash('Status de manutenção inválido.', 'danger'); return redirect(url_for('operations') + '#manutencao')
    with SessionLocal() as db:
        item=db.get(Maintenance,mid)
        if not item: flash('Chamado não encontrado.', 'danger'); return redirect(url_for('operations') + '#manutencao')
        item.status=status
        if item.room_id:
            room=db.get(Room,item.room_id)
            if room and status in ('ABERTO','PENDENTE','EM ANDAMENTO') and room.status == 'DISPONÍVEL': room.status='MANUTENÇÃO'
            elif status in ('CONCLUÍDO','CANCELADO'): _refresh_operation_room(db,item.room_id)
        db.add(Notification(title='Status de manutenção alterado', message=f'{item.location}: {status.lower()}.', created_for_user_id=session.get('user_id')))
        db.commit()
    flash('Status do chamado atualizado.', 'success'); return redirect(url_for('operations') + '#manutencao')

@app.route('/operations/maintenance/<int:mid>/delete', methods=['POST'])
@auth_required
def delete_maintenance(mid):
    with SessionLocal() as db:
        item=db.get(Maintenance,mid)
        if not item: flash('Chamado não encontrado.', 'danger'); return redirect(url_for('operations') + '#manutencao')
        room_id=item.room_id
        db.delete(item); db.flush()
        if room_id: _refresh_operation_room(db,room_id)
        db.commit()
    flash('Chamado de manutenção excluído.', 'success'); return redirect(url_for('operations') + '#manutencao')

@app.route('/employees')
@auth_required
def employees_page():
    q = request.args.get('q','').strip()
    status = request.args.get('status','').strip()
    function = request.args.get('function','').strip()
    with SessionLocal() as db:
        query = db.query(Employee)
        if q: query = query.filter(or_(Employee.full_name.ilike(f'%{q}%'), Employee.function.ilike(f'%{q}%'), Employee.phone.ilike(f'%{q}%'), Employee.whatsapp.ilike(f'%{q}%')))
        if status == 'ATIVO': query = query.filter(Employee.active==True)
        elif status == 'INATIVO': query = query.filter(Employee.active==False)
        if function: query = query.filter(Employee.function==function)
        employees = query.order_by(Employee.full_name).all()
        functions = sorted({e.function for e in db.query(Employee).all() if e.function})
        user_map = {u.id:u for u in db.query(User).all()}
        all_employees = db.query(Employee).all()
        summary = {
            'total': len(all_employees),
            'ativos': sum(1 for e in all_employees if e.active),
            'inativos': sum(1 for e in all_employees if not e.active),
            'com_acesso': sum(1 for e in all_employees if e.user_id),
        }
    return render_template('employees.html', employees=employees, functions=functions, user_map=user_map, summary=summary, q=q, status=status, function=function)

@app.route('/employees/new', methods=['POST'])
@auth_required
def new_employee():
    full_name = request.form.get('full_name','').strip()
    function = request.form.get('function','').strip()
    birth = request.form.get('birth_date','').strip()
    address = request.form.get('address','').strip() or None
    phone = request.form.get('phone','').strip() or None
    whatsapp = request.form.get('whatsapp','').strip() or None
    notes = request.form.get('notes','').strip() or None
    active = request.form.get('active') == 'on'
    create_access = request.form.get('create_access') == 'on'
    username = request.form.get('username','').strip()
    password = request.form.get('password','')
    role = request.form.get('role','FUNCIONARIO').strip().upper()
    if role not in ('ADMINISTRADOR','FUNCIONARIO'): role = 'FUNCIONARIO'

    if not full_name or not function:
        flash('Informe nome e função.', 'danger'); return redirect(url_for('employees_page'))
    try: birth_date = date.fromisoformat(birth) if birth else None
    except ValueError: flash('Informe uma data de nascimento válida.', 'danger'); return redirect(url_for('employees_page'))
    try: salary = Decimal(request.form.get('salary','0').replace(',','.') or '0')
    except Exception: flash('Informe um salário válido.', 'danger'); return redirect(url_for('employees_page'))
    if salary < 0: flash('O salário não pode ser negativo.', 'danger'); return redirect(url_for('employees_page'))

    with SessionLocal() as db:
        user = None
        if create_access:
            if not username or len(password) < 6:
                flash('Para criar acesso, informe usuário e senha com pelo menos 6 caracteres.', 'danger')
                return redirect(url_for('employees_page'))
            if db.query(User).filter_by(username=username).first():
                flash('Já existe um usuário com esse nome de login.', 'danger')
                return redirect(url_for('employees_page'))
            user = User(username=username, password_hash=hash_password(password), role=role, active=active, must_change_password=True)
            db.add(user); db.flush()
        emp = Employee(full_name=full_name, function=function, birth_date=birth_date, address=address, salary=salary, phone=phone, whatsapp=whatsapp, notes=notes, active=active, user_id=user.id if user else None)
        db.add(emp); db.commit()
    flash('Funcionário cadastrado com sucesso.', 'success'); return redirect(url_for('employees_page'))

@app.route('/employees/<int:eid>/edit', methods=['POST'])
@auth_required
def edit_employee(eid):
    full_name = request.form.get('full_name','').strip()
    function = request.form.get('function','').strip()
    birth = request.form.get('birth_date','').strip()
    address = request.form.get('address','').strip() or None
    phone = request.form.get('phone','').strip() or None
    whatsapp = request.form.get('whatsapp','').strip() or None
    notes = request.form.get('notes','').strip() or None
    active = request.form.get('active') == 'on'
    if not full_name or not function:
        flash('Informe nome e função.', 'danger'); return redirect(url_for('employees_page'))
    try: birth_date = date.fromisoformat(birth) if birth else None
    except ValueError: flash('Informe uma data de nascimento válida.', 'danger'); return redirect(url_for('employees_page'))
    try: salary = Decimal(request.form.get('salary','0').replace(',','.') or '0')
    except Exception: flash('Informe um salário válido.', 'danger'); return redirect(url_for('employees_page'))
    if salary < 0: flash('O salário não pode ser negativo.', 'danger'); return redirect(url_for('employees_page'))
    with SessionLocal() as db:
        emp = db.get(Employee, eid)
        if not emp: flash('Funcionário não encontrado.', 'danger'); return redirect(url_for('employees_page'))
        emp.full_name=full_name; emp.function=function; emp.birth_date=birth_date; emp.address=address; emp.salary=salary; emp.phone=phone; emp.whatsapp=whatsapp; emp.notes=notes; emp.active=active
        if emp.user_id:
            user = db.get(User, emp.user_id)
            if user: user.active = active
        db.commit()
    flash('Funcionário atualizado com sucesso.', 'success'); return redirect(url_for('employees_page'))

@app.route('/employees/<int:eid>/access/grant', methods=['POST'])
@auth_required
def grant_employee_access(eid):
    username = request.form.get('username','').strip()
    password = request.form.get('password','')
    role = request.form.get('role','FUNCIONARIO').strip().upper()
    if role not in ('ADMINISTRADOR','FUNCIONARIO'): role = 'FUNCIONARIO'
    if not username or len(password) < 6:
        flash('Informe usuário e senha com pelo menos 6 caracteres.', 'danger'); return redirect(url_for('employees_page'))
    with SessionLocal() as db:
        emp = db.get(Employee, eid)
        if not emp: flash('Funcionário não encontrado.', 'danger'); return redirect(url_for('employees_page'))
        if emp.user_id: flash('Este funcionário já possui uma conta de acesso.', 'danger'); return redirect(url_for('employees_page'))
        if db.query(User).filter_by(username=username).first():
            flash('Já existe um usuário com esse nome de login.', 'danger'); return redirect(url_for('employees_page'))
        user = User(username=username, password_hash=hash_password(password), role=role, active=emp.active, must_change_password=True)
        db.add(user); db.flush()
        emp.user_id = user.id
        db.commit()
    flash('Acesso ao sistema criado com sucesso.', 'success'); return redirect(url_for('employees_page'))

@app.route('/employees/<int:eid>/access/toggle', methods=['POST'])
@auth_required
def toggle_employee_access(eid):
    with SessionLocal() as db:
        emp = db.get(Employee, eid)
        if not emp or not emp.user_id:
            flash('Funcionário sem conta de acesso.', 'danger'); return redirect(url_for('employees_page'))
        user = db.get(User, emp.user_id)
        user.active = not user.active
        db.commit()
        flash(f'Acesso {"ativado" if user.active else "desativado"} com sucesso.', 'success')
    return redirect(url_for('employees_page'))

@app.route('/employees/<int:eid>/access/reset-password', methods=['POST'])
@auth_required
def reset_employee_password(eid):
    with SessionLocal() as db:
        emp = db.get(Employee, eid)
        if not emp or not emp.user_id:
            flash('Funcionário sem conta de acesso.', 'danger'); return redirect(url_for('employees_page'))
        user = db.get(User, emp.user_id)
        temp_password = secrets.token_hex(4)
        user.password_hash = hash_password(temp_password)
        user.must_change_password = True
        db.commit()
    flash(f'Senha redefinida. Senha temporária: {temp_password} — peça para o funcionário trocá-la no primeiro acesso.', 'success')
    return redirect(url_for('employees_page'))

@app.route('/account/profile',methods=['POST'])
@auth_required
def update_own_profile():
    full_name = request.form.get('full_name','').strip()
    function = request.form.get('function','').strip()
    phone = request.form.get('phone','').strip() or None
    whatsapp = request.form.get('whatsapp','').strip() or None
    address = request.form.get('address','').strip() or None
    birth = request.form.get('birth_date','').strip()
    if not full_name:
        flash('Informe seu nome completo.', 'danger'); return redirect(url_for('change_password'))
    try: birth_date = date.fromisoformat(birth) if birth else None
    except ValueError: flash('Informe uma data de nascimento válida.', 'danger'); return redirect(url_for('change_password'))
    with SessionLocal() as db:
        emp = db.query(Employee).filter_by(user_id=session['user_id']).first()
        if emp:
            emp.full_name=full_name; emp.phone=phone; emp.whatsapp=whatsapp; emp.address=address; emp.birth_date=birth_date
        else:
            if not function:
                flash('Informe sua função.', 'danger'); return redirect(url_for('change_password'))
            emp = Employee(full_name=full_name, function=function, phone=phone, whatsapp=whatsapp, address=address, birth_date=birth_date, active=True, user_id=session['user_id'])
            db.add(emp)
        db.commit()
    flash('Seus dados foram atualizados com sucesso.', 'success'); return redirect(url_for('change_password'))

@app.route('/change-password',methods=['GET','POST'])
@auth_required
def change_password():
 if request.method=='POST':
  p=request.form.get('password',''); p2=request.form.get('password2','')
  if len(p)<6 or p!=p2: flash('A senha precisa ter pelo menos 6 caracteres e as duas senhas devem coincidir.','danger')
  else:
   with SessionLocal() as db: u=db.get(User,session['user_id']); u.password_hash=hash_password(p); u.must_change_password=False; db.commit()
   session['must_change_password']=False; flash('Senha alterada com sucesso.','success'); return redirect(url_for('dashboard'))
 with SessionLocal() as db:
  user=db.get(User,session['user_id'])
  employee=db.query(Employee).filter_by(user_id=session['user_id']).first()
 return render_template('change_password.html',employee=employee,account_active=user.active)

if __name__=='__main__': app.run(host='127.0.0.1',port=5000,debug=False)
