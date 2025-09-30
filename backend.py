import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import bcrypt
import google.generativeai as genai
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configuración de base de datos
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:[PASSWORD]@db.xxx.supabase.co:5432/postgres')

# Configuración de Gemini
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'TU_GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)

# Configuración de uploads
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    """Conexión a PostgreSQL"""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def time_ago(dt):
    """Calcula tiempo transcurrido"""
    now = datetime.now()
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
    diff = now - dt
    
    if diff.days > 365:
        return f"hace {diff.days // 365} año{'s' if diff.days // 365 > 1 else ''}"
    elif diff.days > 30:
        return f"hace {diff.days // 30} mes{'es' if diff.days // 30 > 1 else ''}"
    elif diff.days > 0:
        return f"hace {diff.days} día{'s' if diff.days > 1 else ''}"
    elif diff.seconds > 3600:
        return f"hace {diff.seconds // 3600} hora{'s' if diff.seconds // 3600 > 1 else ''}"
    elif diff.seconds > 60:
        return f"hace {diff.seconds // 60} minuto{'s' if diff.seconds // 60 > 1 else ''}"
    else:
        return "hace unos segundos"
# === RUTAS DE AUTENTICACIÓN ===

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        role = data.get('role', 'Cliente')
        
        if not all([username, email, password]):
            return jsonify({'error': 'Faltan campos requeridos'}), 400
        
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            cur.execute('''
                INSERT INTO users (username, email, password, role)
                VALUES (%s, %s, %s, %s) RETURNING id
            ''', (username, email, hashed.decode('utf-8'), role))
            
            user_id = cur.fetchone()['id']
            
            if role == 'Piloto':
                cur.execute('''
                    INSERT INTO pilot_profiles (user_id, name)
                    VALUES (%s, %s)
                ''', (user_id, username))
            
            conn.commit()
            return jsonify({'message': 'Usuario registrado correctamente'}), 201
        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify({'error': 'Usuario o email ya existe'}), 400
        finally:
            cur.close()
            conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        if not bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            cur.close()
            conn.close()
            return jsonify({'error': 'Contraseña incorrecta'}), 401
        
        pilot_profile_id = None
        if user['role'] == 'Piloto':
            cur.execute('SELECT id FROM pilot_profiles WHERE user_id = %s', (user['id'],))
            pilot = cur.fetchone()
            pilot_profile_id = pilot['id'] if pilot else None
        
        cur.close()
        conn.close()
        
        return jsonify({
            'message': 'Login exitoso',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'role': user['role'],
                'pilot_profile_id': pilot_profile_id
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === RUTAS DE PILOTOS ===

@app.route('/api/pilots', methods=['GET'])
def get_pilots():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT pp.*, u.username
            FROM pilot_profiles pp
            JOIN users u ON pp.user_id = u.id
            ORDER BY pp.created_at DESC
        ''')
        
        pilots = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify(pilots), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pilots/<int:profile_id>', methods=['GET'])
def get_pilot_detail(profile_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT pp.*, u.username
            FROM pilot_profiles pp
            JOIN users u ON pp.user_id = u.id
            WHERE pp.id = %s
        ''', (profile_id,))
        
        pilot = cur.fetchone()
        
        if not pilot:
            cur.close()
            conn.close()
            return jsonify({'error': 'Piloto no encontrado'}), 404
        
        # Obtener servicios
        cur.execute('SELECT * FROM event_packages WHERE pilot_profile_id = %s', (profile_id,))
        pilot['eventPackages'] = cur.fetchall()
        
        # Obtener portfolio
        cur.execute('SELECT * FROM portfolio WHERE pilot_profile_id = %s', (profile_id,))
        pilot['portfolio'] = cur.fetchall()
        
        # Obtener badges
        cur.execute('SELECT * FROM badges WHERE pilot_profile_id = %s', (profile_id,))
        pilot['badges'] = cur.fetchall()
        
        # Obtener disponibilidad
        cur.execute('SELECT * FROM availability WHERE pilot_profile_id = %s AND is_booked = FALSE', (profile_id,))
        pilot['availability'] = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return jsonify(pilot), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pilots/nearby', methods=['POST'])
def get_nearby_pilots():
    try:
        data = request.json
        user_lat = data.get('latitude')
        user_lng = data.get('longitude')
        radius = data.get('radius', 25)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Usar fórmula Haversine para calcular distancia
        cur.execute('''
            SELECT pp.*, u.username,
                   (6371 * acos(
                       cos(radians(%s)) * cos(radians(latitude)) *
                       cos(radians(longitude) - radians(%s)) +
                       sin(radians(%s)) * sin(radians(latitude))
                   )) AS distance
            FROM pilot_profiles pp
            JOIN users u ON pp.user_id = u.id
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            HAVING distance < %s
            ORDER BY distance
        ''', (user_lat, user_lng, user_lat, radius))
        
        pilots = cur.fetchall()
        cur.close()
        conn.close()
        
        for pilot in pilots:
            pilot['distance'] = round(pilot['distance'], 2)
        
        return jsonify(pilots), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# === PERFIL DEL PILOTO ===

@app.route('/api/profile', methods=['POST'])
def update_profile():
    try:
        data = request.json
        email = data.get('email')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        cur.execute('''
            UPDATE pilot_profiles
            SET name = %s, phone = %s, location = %s, hourly_rate = %s,
                tagline = %s, bio = %s
            WHERE user_id = %s
        ''', (
            data.get('name'),
            data.get('phone'),
            data.get('location'),
            data.get('hourly_rate'),
            data.get('tagline'),
            data.get('bio'),
            user['id']
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Perfil actualizado'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profile/services', methods=['POST'])
def add_service():
    try:
        data = request.json
        email = data.get('email')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT pp.id FROM pilot_profiles pp
            JOIN users u ON pp.user_id = u.id
            WHERE u.email = %s
        ''', (email,))
        
        pilot = cur.fetchone()
        
        if not pilot:
            cur.close()
            conn.close()
            return jsonify({'error': 'Piloto no encontrado'}), 404
        
        cur.execute('''
            INSERT INTO event_packages (pilot_profile_id, name, description, price, duration_hours)
            VALUES (%s, %s, %s, %s, %s)
        ''', (
            pilot['id'],
            data.get('name'),
            data.get('description'),
            data.get('price'),
            data.get('duration_hours')
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Servicio añadido'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/profile/portfolio', methods=['POST'])
def add_portfolio():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No se envió archivo'}), 400
        
        file = request.files['file']
        email = request.form.get('email')
        
        if file.filename == '':
            return jsonify({'error': 'Archivo vacío'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute('''
                SELECT pp.id FROM pilot_profiles pp
                JOIN users u ON pp.user_id = u.id
                WHERE u.email = %s
            ''', (email,))
            
            pilot = cur.fetchone()
            
            if not pilot:
                cur.close()
                conn.close()
                return jsonify({'error': 'Piloto no encontrado'}), 404
            
            cur.execute('''
                INSERT INTO portfolio (pilot_profile_id, title, description, image_url)
                VALUES (%s, %s, %s, %s)
            ''', (
                pilot['id'],
                request.form.get('title', ''),
                request.form.get('description', ''),
                f'/uploads/{filename}'
            ))
            
            conn.commit()
            cur.close()
            conn.close()
            
            return jsonify({'message': 'Imagen subida', 'url': f'/uploads/{filename}'}), 201
        
        return jsonify({'error': 'Tipo de archivo no permitido'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/<int:item_id>', methods=['DELETE'])
def delete_portfolio(item_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM portfolio WHERE id = %s', (item_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Imagen eliminada'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# === DISPONIBILIDAD ===

@app.route('/api/pilots/<int:profile_id>/availability', methods=['POST'])
def add_availability(profile_id):
    try:
        data = request.json
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO availability (pilot_profile_id, date, start_time, end_time)
            VALUES (%s, %s, %s, %s)
        ''', (
            profile_id,
            data.get('date'),
            data.get('start_time'),
            data.get('end_time')
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Disponibilidad añadida'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/availability/<int:slot_id>', methods=['DELETE'])
def delete_availability(slot_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM availability WHERE id = %s', (slot_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Disponibilidad eliminada'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === RESERVAS ===

@app.route('/api/book', methods=['POST'])
def create_booking():
    try:
        data = request.json
        client_email = data.get('client_email')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id FROM users WHERE email = %s', (client_email,))
        client = cur.fetchone()
        
        if not client:
            cur.close()
            conn.close()
            return jsonify({'error': 'Cliente no encontrado'}), 404
        
        cur.execute('''
            INSERT INTO bookings (client_id, pilot_id, job_description, booking_date, start_time, end_time, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (
            client['id'],
            data.get('pilot_id'),
            data.get('job_description'),
            data.get('booking_date'),
            data.get('start_time'),
            data.get('end_time'),
            'pending'
        ))
        
        booking_id = cur.fetchone()['id']
        
        # Crear notificación para el piloto
        cur.execute('SELECT user_id FROM pilot_profiles WHERE id = %s', (data.get('pilot_id'),))
        pilot = cur.fetchone()
        
        if pilot:
            cur.execute('''
                INSERT INTO notifications (user_id, notification_type, title, message, link)
                VALUES (%s, %s, %s, %s, %s)
            ''', (
                pilot['user_id'],
                'booking',
                'Nueva solicitud de reserva',
                f"Tienes una nueva solicitud para {data.get('booking_date')}",
                f"/dashboard/bookings/{booking_id}"
            ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Reserva creada', 'booking_id': booking_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    try:
        email = request.args.get('email')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id, role FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        if user['role'] == 'Piloto':
            cur.execute('''
                SELECT b.*, u.username as client_username, pp.name as pilot_name
                FROM bookings b
                JOIN pilot_profiles pp ON b.pilot_id = pp.id
                JOIN users u ON b.client_id = u.id
                WHERE pp.user_id = %s
                ORDER BY b.booking_date DESC
            ''', (user['id'],))
        else:
            cur.execute('''
                SELECT b.*, u.username as client_username, pp.name as pilot_name
                FROM bookings b
                JOIN pilot_profiles pp ON b.pilot_id = pp.id
                JOIN users u ON b.client_id = u.id
                WHERE b.client_id = %s
                ORDER BY b.booking_date DESC
            ''', (user['id'],))
        
        bookings = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify(bookings), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bookings/<int:booking_id>/respond', methods=['POST'])
def respond_booking(booking_id):
    try:
        data = request.json
        status = data.get('status')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('UPDATE bookings SET status = %s WHERE id = %s', (status, booking_id))
        
        # Crear notificación para el cliente
        cur.execute('''
            SELECT b.client_id, pp.name
            FROM bookings b
            JOIN pilot_profiles pp ON b.pilot_id = pp.id
            WHERE b.id = %s
        ''', (booking_id,))
        
        booking = cur.fetchone()
        
        if booking:
            status_text = 'aceptada' if status == 'confirmed' else 'rechazada'
            cur.execute('''
                INSERT INTO notifications (user_id, notification_type, title, message, link)
                VALUES (%s, %s, %s, %s, %s)
            ''', (
                booking['client_id'],
                'booking',
                f'Reserva {status_text}',
                f"Tu reserva con {booking['name']} ha sido {status_text}",
                f"/bookings/{booking_id}"
            ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': f'Reserva {status}'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# === CERTIFICACIONES ===

@app.route('/api/pilots/<int:profile_id>/certifications', methods=['GET'])
def get_certifications(profile_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT *, 
                   CASE WHEN expiry_date < CURRENT_DATE THEN TRUE ELSE FALSE END as is_expired
            FROM certifications 
            WHERE pilot_profile_id = %s
            ORDER BY created_at DESC
        ''', (profile_id,))
        
        certifications = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify(certifications), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pilots/<int:profile_id>/certifications', methods=['POST'])
def add_certification(profile_id):
    try:
        email = request.form.get('email')
        cert_type = request.form.get('certification_type')
        name = request.form.get('name')
        description = request.form.get('description', '')
        issue_date = request.form.get('issue_date')
        expiry_date = request.form.get('expiry_date')
        
        document_url = None
        if 'document' in request.files:
            file = request.files['document']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"{timestamp}_{filename}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                file.save(filepath)
                document_url = f'/uploads/{filename}'
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO certifications 
            (pilot_profile_id, certification_type, name, description, issue_date, expiry_date, document_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (profile_id, cert_type, name, description, issue_date, expiry_date, document_url))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Certificación añadida'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/certifications/<int:cert_id>', methods=['DELETE'])
def delete_certification(cert_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM certifications WHERE id = %s', (cert_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Certificación eliminada'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === BADGES ===

@app.route('/api/pilots/<int:profile_id>/badges', methods=['POST'])
def add_badge(profile_id):
    try:
        data = request.json
        badge_type = data.get('badge_type')
        
        badge_info = {
            'wedding': {'name': 'Especialista en Bodas', 'icon': '💍', 'color': 'pink', 'description': 'Experto en eventos sociales'},
            'real_estate': {'name': 'Inmobiliaria', 'icon': '🏢', 'color': 'blue', 'description': 'Fotografía de propiedades'},
            'inspection': {'name': 'Inspección Técnica', 'icon': '🔧', 'color': 'gray', 'description': 'Inspecciones industriales'},
            'agriculture': {'name': 'Agricultura', 'icon': '🌾', 'color': 'green', 'description': 'Agricultura de precisión'},
            'film': {'name': 'Producción Audiovisual', 'icon': '🎬', 'color': 'purple', 'description': 'Cine y televisión'},
            'sports': {'name': 'Eventos Deportivos', 'icon': '⚽', 'color': 'orange', 'description': 'Cobertura deportiva'}
        }
        
        badge = badge_info.get(badge_type)
        
        if not badge:
            return jsonify({'error': 'Tipo de badge inválido'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO badges (pilot_profile_id, badge_type, name, description, icon, color)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            profile_id,
            badge_type,
            badge['name'],
            badge['description'],
            badge['icon'],
            badge['color']
        ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Badge añadido'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/badges/<int:badge_id>', methods=['DELETE'])
def delete_badge(badge_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('DELETE FROM badges WHERE id = %s', (badge_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Badge eliminado'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === CHAT ===

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    try:
        email = request.args.get('email')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id, role FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        if user['role'] == 'Cliente':
            cur.execute('''
                SELECT c.*, 
                       pp.name as pilot_name,
                       'https://picsum.photos/seed/' || pp.id || '/50/50' as pilot_avatar,
                       (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY created_at DESC LIMIT 1) as last_message
                FROM conversations c
                JOIN pilot_profiles pp ON c.pilot_profile_id = pp.id
                WHERE c.client_id = %s
                ORDER BY c.updated_at DESC
            ''', (user['id'],))
        else:
            cur.execute('''
                SELECT c.*, 
                       u.username as client_username,
                       'https://picsum.photos/seed/' || u.id || '/50/50' as client_avatar,
                       (SELECT content FROM messages WHERE conversation_id = c.id ORDER BY created_at DESC LIMIT 1) as last_message
                FROM conversations c
                JOIN users u ON c.client_id = u.id
                JOIN pilot_profiles pp ON c.pilot_profile_id = pp.id
                WHERE pp.user_id = %s
                ORDER BY c.updated_at DESC
            ''', (user['id'],))
        
        conversations = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify(conversations), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    try:
        data = request.json
        client_email = data.get('client_email')
        pilot_profile_id = data.get('pilot_profile_id')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id FROM users WHERE email = %s', (client_email,))
        client = cur.fetchone()
        
        if not client:
            cur.close()
            conn.close()
            return jsonify({'error': 'Cliente no encontrado'}), 404
        
        # Verificar si ya existe la conversación
        cur.execute('''
            SELECT id FROM conversations 
            WHERE client_id = %s AND pilot_profile_id = %s
        ''', (client['id'], pilot_profile_id))
        
        existing = cur.fetchone()
        
        if existing:
            cur.close()
            conn.close()
            return jsonify({'conversation': {'id': existing['id']}}), 200
        
        # Crear nueva conversación
        cur.execute('''
            INSERT INTO conversations (client_id, pilot_profile_id)
            VALUES (%s, %s) RETURNING id
        ''', (client['id'], pilot_profile_id))
        
        conversation_id = cur.fetchone()['id']
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'conversation': {'id': conversation_id}}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversations/<int:conversation_id>/messages', methods=['GET'])
def get_messages(conversation_id):
    try:
        email = request.args.get('email')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id, role FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        # Obtener info de la conversación
        if user['role'] == 'Cliente':
            cur.execute('''
                SELECT c.*, 
                       pp.name as pilot_name,
                       'https://picsum.photos/seed/' || pp.id || '/50/50' as pilot_avatar
                FROM conversations c
                JOIN pilot_profiles pp ON c.pilot_profile_id = pp.id
                WHERE c.id = %s
            ''', (conversation_id,))
        else:
            cur.execute('''
                SELECT c.*, 
                       u.username as client_username,
                       'https://picsum.photos/seed/' || u.id || '/50/50' as client_avatar
                FROM conversations c
                JOIN users u ON c.client_id = u.id
                WHERE c.id = %s
            ''', (conversation_id,))
        
        conversation = cur.fetchone()
        
        # Obtener mensajes
        cur.execute('''
            SELECT * FROM messages 
            WHERE conversation_id = %s 
            ORDER BY created_at ASC
        ''', (conversation_id,))
        
        messages = cur.fetchall()
        
        # Marcar mensajes como leídos
        if user['role'] == 'Cliente':
            cur.execute('''
                UPDATE messages 
                SET is_read = TRUE 
                WHERE conversation_id = %s AND sender_type = 'pilot'
            ''', (conversation_id,))
        else:
            cur.execute('''
                UPDATE messages 
                SET is_read = TRUE 
                WHERE conversation_id = %s AND sender_type = 'client'
            ''', (conversation_id,))
        
        conn.commit()
        
        # Añadir time_ago a mensajes
        for msg in messages:
            msg['time_ago'] = time_ago(msg['created_at'])
        
        cur.close()
        conn.close()
        
        return jsonify({'conversation': conversation, 'messages': messages}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/conversations/<int:conversation_id>/messages', methods=['POST'])
def send_message(conversation_id):
    try:
        data = request.json
        sender_email = data.get('sender_email')
        content = data.get('content')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id, role FROM users WHERE email = %s', (sender_email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        sender_type = 'client' if user['role'] == 'Cliente' else 'pilot'
        
        cur.execute('''
            INSERT INTO messages (conversation_id, sender_type, content)
            VALUES (%s, %s, %s)
        ''', (conversation_id, sender_type, content))
        
        # Actualizar timestamp de conversación
        cur.execute('''
            UPDATE conversations 
            SET updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s
        ''', (conversation_id,))
        
        # Crear notificación para el receptor
        if sender_type == 'client':
            cur.execute('''
                SELECT pp.user_id, u.username as sender_name
                FROM conversations c
                JOIN pilot_profiles pp ON c.pilot_profile_id = pp.id
                JOIN users u ON c.client_id = u.id
                WHERE c.id = %s
            ''', (conversation_id,))
        else:
            cur.execute('''
                SELECT c.client_id as user_id, pp.name as sender_name
                FROM conversations c
                JOIN pilot_profiles pp ON c.pilot_profile_id = pp.id
                WHERE c.id = %s
            ''', (conversation_id,))
        
        receiver = cur.fetchone()
        
        if receiver:
            cur.execute('''
                INSERT INTO notifications (user_id, notification_type, title, message, link)
                VALUES (%s, %s, %s, %s, %s)
            ''', (
                receiver['user_id'],
                'message',
                'Nuevo mensaje',
                f"{receiver['sender_name']}: {content[:50]}...",
                f"/chat/{conversation_id}"
            ))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Mensaje enviado'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/unread-count', methods=['GET'])
def get_unread_count():
    try:
        email = request.args.get('email')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id, role FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        if user['role'] == 'Cliente':
            cur.execute('''
                SELECT COUNT(*) as count
                FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                WHERE c.client_id = %s AND m.sender_type = 'pilot' AND m.is_read = FALSE
            ''', (user['id'],))
        else:
            cur.execute('''
                SELECT COUNT(*) as count
                FROM messages m
                JOIN conversations c ON m.conversation_id = c.id
                JOIN pilot_profiles pp ON c.pilot_profile_id = pp.id
                WHERE pp.user_id = %s AND m.sender_type = 'client' AND m.is_read = FALSE
            ''', (user['id'],))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        return jsonify({'unread_count': result['count']}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# === NOTIFICACIONES ===

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    try:
        email = request.args.get('email')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        cur.execute('''
            SELECT * FROM notifications 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 50
        ''', (user['id'],))
        
        notifications = cur.fetchall()
        
        # Añadir time_ago
        for notif in notifications:
            notif['time_ago'] = time_ago(notif['created_at'])
        
        # Contar no leídas
        cur.execute('''
            SELECT COUNT(*) as count 
            FROM notifications 
            WHERE user_id = %s AND is_read = FALSE
        ''', (user['id'],))
        
        unread = cur.fetchone()
        
        cur.close()
        conn.close()
        
        return jsonify({
            'notifications': notifications,
            'unread_count': unread['count']
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
def mark_notification_read(notif_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('UPDATE notifications SET is_read = TRUE WHERE id = %s', (notif_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Notificación marcada como leída'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications/mark-all-read', methods=['POST'])
def mark_all_read():
    try:
        data = request.json
        email = data.get('email')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('SELECT id FROM users WHERE email = %s', (email,))
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return jsonify({'error': 'Usuario no encontrado'}), 404
        
        cur.execute('UPDATE notifications SET is_read = TRUE WHERE user_id = %s', (user['id'],))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'message': 'Todas las notificaciones marcadas'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === BÚSQUEDA CON IA ===

@app.route('/api/search', methods=['POST'])
def ai_search():
    try:
        data = request.json
        query = data.get('query')
        
        if not query:
            return jsonify({'error': 'Query vacío'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT pp.*, u.username,
                   COALESCE(
                       (SELECT string_agg(b.badge_type, ', ') 
                        FROM badges b 
                        WHERE b.pilot_profile_id = pp.id), 
                       ''
                   ) as specialties
            FROM pilot_profiles pp
            JOIN users u ON pp.user_id = u.id
        ''')
        
        pilots = cur.fetchall()
        cur.close()
        conn.close()
        
        pilots_info = "\n".join([
            f"- {p['name']}: {p['tagline'] or 'Piloto profesional'} (Ubicación: {p['location'] or 'No especificada'}, Tarifa: €{p['hourly_rate'] or 'N/A'}/hora, Especialidades: {p['specialties'] or 'Ninguna'})"
            for p in pilots
        ])
        
        prompt = f"""Eres un asistente experto en servicios de drones. Un cliente pregunta: "{query}"

Pilotos disponibles:
{pilots_info}

Proporciona una recomendación personalizada, específica y útil. Menciona pilotos concretos si son relevantes. Sé breve pero informativo (máximo 200 palabras)."""
        
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        
        return jsonify({'recommendation': response.text}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# === SERVIDOR DE ARCHIVOS ESTÁTICOS ===

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(UPLOAD_FOLDER, filename)

# === MAIN ===

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)