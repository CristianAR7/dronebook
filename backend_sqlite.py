import os
import google.generativeai as genai
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import bcrypt
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import stripe
import json
from math import radians, sin, cos, sqrt, atan2

# --- CONFIGURACIÓN ---
app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
UPLOAD_FOLDER = os.path.join(app.instance_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
db = SQLAlchemy(app)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- CONFIGURACIÓN GEMINI ---
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', 'AIzaSyCjST_lyf9SH2bU6PLhUVlx0bf3XwDRSJk')
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        print(f"Error configurando el modelo de IA: {e}")
        model = None
else:
    print("Advertencia: GOOGLE_API_KEY no encontrada. La búsqueda con IA estará desactivada.")
    model = None

# --- CONFIGURACIÓN STRIPE ---
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', 'pk_test_51234567890abcdef')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_51234567890abcdef')
stripe.api_key = STRIPE_SECRET_KEY

# --- MODELOS DE LA BASE DE DATOS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Cliente')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    pilot_profile = db.relationship('PilotProfile', backref='user', uselist=False, cascade="all, delete-orphan")
    bookings_made = db.relationship('Booking', foreign_keys='Booking.client_id', backref='client', lazy=True)

class PilotProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, default="Nuevo Piloto")
    tagline = db.Column(db.String(200))
    location = db.Column(db.String(100))
    bio = db.Column(db.Text)
    hourly_rate = db.Column(db.Integer, default=50)
    phone = db.Column(db.String(20))
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    bookings_received = db.relationship('Booking', foreign_keys='Booking.pilot_profile_id', backref='pilot', lazy=True)
    services = db.relationship('ServicePackage', backref='profile', lazy=True, cascade="all, delete-orphan")
    portfolio_items = db.relationship('PortfolioItem', backref='profile', lazy=True, cascade="all, delete-orphan")
    availability_slots = db.relationship('AvailabilitySlot', backref='profile', lazy=True, cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "tagline": self.tagline, 
            "location": self.location, "bio": self.bio, "hourly_rate": self.hourly_rate,
            "phone": self.phone, "user_id": self.user_id,
            "latitude": self.latitude, "longitude": self.longitude,
            "profilePictureUrl": f"https://picsum.photos/seed/{self.id}/300/300",
            "eventPackages": [s.to_dict() for s in self.services],
            "portfolio": [item.to_dict() for item in self.portfolio_items],
            "availability": [slot.to_dict() for slot in self.availability_slots],
            "certifications": [cert.to_dict() for cert in self.certifications],
            "badges": [badge.to_dict() for badge in self.badges],
            "is_verified": any(cert.verification_status == 'verified' for cert in self.certifications)
        }

class AvailabilitySlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pilot_profile_id = db.Column(db.Integer, db.ForeignKey('pilot_profile.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date.isoformat(),
            "start_time": self.start_time.strftime('%H:%M'),
            "end_time": self.end_time.strftime('%H:%M'),
            "is_available": self.is_available
        }

class ServicePackage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    duration_hours = db.Column(db.Integer, default=2)
    pilot_profile_id = db.Column(db.Integer, db.ForeignKey('pilot_profile.id'), nullable=False)
    
    def to_dict(self):
        return {
            "id": self.id, "name": self.name, 
            "description": self.description, "price": self.price,
            "duration_hours": self.duration_hours
        }

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_description = db.Column(db.Text, nullable=False)
    booking_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    total_price = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pilot_profile_id = db.Column(db.Integer, db.ForeignKey('pilot_profile.id'), nullable=False)
    service_package_id = db.Column(db.Integer, db.ForeignKey('service_package.id'), nullable=True)
    
    def to_dict(self):
        client_user = User.query.get(self.client_id)
        pilot_profile = PilotProfile.query.get(self.pilot_profile_id)
        service = ServicePackage.query.get(self.service_package_id) if self.service_package_id else None
        payment = Payment.query.filter_by(booking_id=self.id).first()
        
        return {
            "id": self.id, 
            "job_description": self.job_description, 
            "status": self.status,
            "booking_date": self.booking_date.isoformat(),
            "start_time": self.start_time.strftime('%H:%M'),
            "end_time": self.end_time.strftime('%H:%M'),
            "total_price": self.total_price,
            "created_at": self.created_at.isoformat(),
            "client_username": client_user.username,
            "client_email": client_user.email,
            "pilot_name": pilot_profile.name,
            "pilot_profile_id": self.pilot_profile_id,
            "service_name": service.name if service else "Servicio personalizado",
            "payment_status": payment.status if payment else "no_payment",
            "payment_id": payment.id if payment else None
        }

class PortfolioItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_url = db.Column(db.String(200), nullable=False)
    item_type = db.Column(db.String(20), nullable=False, default='image')
    title = db.Column(db.String(100))
    description = db.Column(db.Text)
    pilot_profile_id = db.Column(db.Integer, db.ForeignKey('pilot_profile.id'), nullable=False)
    
    def to_dict(self):
        return {
            "id": self.id, "url": self.file_url, "type": self.item_type,
            "title": self.title, "description": self.description
        }

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pilot_profile_id = db.Column(db.Integer, db.ForeignKey('pilot_profile.id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=True)
    
    def to_dict(self):
        client = User.query.get(self.client_id)
        return {
            "id": self.id,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at.isoformat(),
            "client_username": client.username if client else "Usuario eliminado",
            "client_id": self.client_id,
            "pilot_profile_id": self.pilot_profile_id,
            "booking_id": self.booking_id
        }

class Certification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pilot_profile_id = db.Column(db.Integer, db.ForeignKey('pilot_profile.id'), nullable=False)
    certification_type = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    document_url = db.Column(db.String(200))
    issue_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    verification_status = db.Column(db.String(20), default='pending')
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    verified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    pilot_profile = db.relationship('PilotProfile', backref='certifications')
    verifier = db.relationship('User', foreign_keys=[verified_by])
    
    def to_dict(self):
        return {
            "id": self.id,
            "pilot_profile_id": self.pilot_profile_id,
            "certification_type": self.certification_type,
            "name": self.name,
            "description": self.description,
            "document_url": self.document_url,
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "verification_status": self.verification_status,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "created_at": self.created_at.isoformat(),
            "is_expired": self.expiry_date < datetime.utcnow().date() if self.expiry_date else False
        }

class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pilot_profile_id = db.Column(db.Integer, db.ForeignKey('pilot_profile.id'), nullable=False)
    badge_type = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50))
    color = db.Column(db.String(20))
    description = db.Column(db.Text)
    earned_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    pilot_profile = db.relationship('PilotProfile', backref='badges')
    
    def to_dict(self):
        return {
            "id": self.id,
            "badge_type": self.badge_type,
            "name": self.name,
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
            "earned_at": self.earned_at.isoformat()
        }

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(200))
    related_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    user = db.relationship('User', backref='notifications')
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "notification_type": self.notification_type,
            "title": self.title,
            "message": self.message,
            "link": self.link,
            "related_id": self.related_id,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat(),
            "time_ago": self.get_time_ago()
        }
    
    def get_time_ago(self):
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"hace {diff.days} día{'s' if diff.days > 1 else ''}"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"hace {hours} hora{'s' if hours > 1 else ''}"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"hace {minutes} minuto{'s' if minutes > 1 else ''}"
        else:
            return "ahora mismo"

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pilot_profile_id = db.Column(db.Integer, db.ForeignKey('pilot_profile.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_message_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    client = db.relationship('User', backref='client_conversations')
    pilot_profile = db.relationship('PilotProfile', backref='pilot_conversations')
    messages = db.relationship('Message', backref='conversation', lazy=True, cascade="all, delete-orphan")
    
    def to_dict(self):
        last_message = Message.query.filter_by(conversation_id=self.id).order_by(Message.created_at.desc()).first()
        return {
            "id": self.id,
            "client_id": self.client_id,
            "pilot_profile_id": self.pilot_profile_id,
            "client_username": self.client.username,
            "pilot_name": self.pilot_profile.name,
            "pilot_avatar": f"https://picsum.photos/seed/{self.pilot_profile.id}/50/50",
            "client_avatar": f"https://picsum.photos/seed/client{self.client_id}/50/50",
            "created_at": self.created_at.isoformat(),
            "last_message_at": self.last_message_at.isoformat(),
            "last_message": last_message.content if last_message else "Inicia la conversación",
            "last_message_sender": last_message.sender_type if last_message else None,
            "unread_count": 0
        }

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)
    sender_id = db.Column(db.Integer, nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    
    def to_dict(self):
        if self.sender_type == 'client':
            sender = User.query.get(self.sender_id)
            sender_name = sender.username if sender else "Cliente eliminado"
            sender_avatar = f"https://picsum.photos/seed/client{self.sender_id}/40/40"
        else:
            sender = User.query.get(self.sender_id)
            pilot_profile = sender.pilot_profile if sender else None
            sender_name = pilot_profile.name if pilot_profile else "Piloto eliminado"
            sender_avatar = f"https://picsum.photos/seed/{pilot_profile.id}/40/40" if pilot_profile else ""
        
        return {
            "id": self.id,
            "content": self.content,
            "sender_type": self.sender_type,
            "sender_id": self.sender_id,
            "sender_name": sender_name,
            "sender_avatar": sender_avatar,
            "conversation_id": self.conversation_id,
            "created_at": self.created_at.isoformat(),
            "is_read": self.is_read,
            "time_ago": self.get_time_ago()
        }
    
    def get_time_ago(self):
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"hace {diff.days} día{'s' if diff.days > 1 else ''}"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"hace {hours} hora{'s' if hours > 1 else ''}"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"hace {minutes} minuto{'s' if minutes > 1 else ''}"
        else:
            return "ahora mismo"

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking.id'), nullable=False)
    stripe_payment_intent_id = db.Column(db.String(200), nullable=False, unique=True)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), default='eur')
    status = db.Column(db.String(50), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    booking = db.relationship('Booking', backref='payment')
    
    def to_dict(self):
        return {
            "id": self.id,
            "booking_id": self.booking_id,
            "stripe_payment_intent_id": self.stripe_payment_intent_id,
            "amount": self.amount,
            "amount_euros": self.amount / 100,
            "currency": self.currency,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }

# --- INICIALIZACIÓN DE LA BD ---
with app.app_context():
    db.create_all()
    print("✅ Base de datos inicializada con todas las tablas")

# --- FUNCIONES HELPER PARA NOTIFICACIONES ---
def create_notification(user_id, notification_type, title, message, link=None, related_id=None):
    """Crear una notificación in-app"""
    try:
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            link=link,
            related_id=related_id
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    except Exception as e:
        print(f"Error creando notificación: {e}")
        return None

def send_email_notification(to_email, subject, html_content):
    """Enviar email (simulado por ahora)"""
    try:
        print(f"""
        ==================== EMAIL ====================
        Para: {to_email}
        Asunto: {subject}
        Contenido:
        {html_content}
        ===============================================
        """)
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False
# --- RUTAS PARA PAGOS ---
@app.route('/api/create-payment-intent', methods=['POST'])
def create_payment_intent():
    try:
        data = request.get_json()
        booking_id = data.get('booking_id')
        
        if not booking_id:
            return jsonify({'error': 'booking_id es requerido'}), 400
        
        booking = Booking.query.get(booking_id)
        if not booking:
            return jsonify({'error': 'Reserva no encontrada'}), 404
        
        if booking.status != 'confirmed':
            return jsonify({'error': 'Solo se pueden pagar reservas confirmadas'}), 400
        
        existing_payment = Payment.query.filter_by(booking_id=booking_id).first()
        if existing_payment and existing_payment.status == 'succeeded':
            return jsonify({'error': 'Esta reserva ya ha sido pagada'}), 400
        
        amount_cents = booking.total_price * 100
        
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='eur',
            payment_method_types=['card'],
            metadata={
                'booking_id': booking_id,
                'client_id': booking.client_id,
                'pilot_id': booking.pilot_profile_id
            }
        )
        
        if existing_payment:
            existing_payment.stripe_payment_intent_id = intent.id
            existing_payment.amount = amount_cents
            existing_payment.status = 'pending'
        else:
            payment = Payment(
                booking_id=booking_id,
                stripe_payment_intent_id=intent.id,
                amount=amount_cents,
                status='pending'
            )
            db.session.add(payment)
        
        db.session.commit()
        
        return jsonify({
            'client_secret': intent.client_secret,
            'payment_intent_id': intent.id,
            'amount': amount_cents,
            'currency': 'eur'
        })
        
    except stripe.error.StripeError as e:
        return jsonify({'error': f'Error de Stripe: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Error del servidor: {str(e)}'}), 500

@app.route('/api/confirm-payment', methods=['POST'])
def confirm_payment():
    try:
        data = request.get_json()
        payment_intent_id = data.get('payment_intent_id')
        
        if not payment_intent_id:
            return jsonify({'error': 'payment_intent_id es requerido'}), 400
        
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        payment = Payment.query.filter_by(stripe_payment_intent_id=payment_intent_id).first()
        if not payment:
            return jsonify({'error': 'Pago no encontrado'}), 404
        
        payment.status = intent.status
        if intent.status == 'succeeded':
            payment.completed_at = datetime.utcnow()
            booking = payment.booking
            booking.status = 'paid'
            
            # ✅ NOTIFICACIÓN AL PILOTO: Pago recibido
            pilot_profile = PilotProfile.query.get(booking.pilot_profile_id)
            create_notification(
                user_id=pilot_profile.user_id,
                notification_type='payment',
                title='💰 Pago recibido',
                message=f'Has recibido un pago de €{payment.amount / 100:.2f} por la reserva del {booking.booking_date.strftime("%d/%m/%Y")}',
                link='/dashboard/bookings',
                related_id=booking.id
            )
            
            # ✅ EMAIL AL PILOTO
            send_email_notification(
                to_email=pilot_profile.user.email,
                subject='Pago Recibido - DroneBook',
                html_content=f'''
                <h2>¡Has recibido un pago!</h2>
                <p>Hola {pilot_profile.name},</p>
                <p>El cliente <strong>{booking.client.username}</strong> ha completado el pago de:</p>
                <ul>
                    <li>Monto: <strong>€{payment.amount / 100:.2f}</strong></li>
                    <li>Reserva: {booking.booking_date.strftime("%d/%m/%Y")}</li>
                    <li>Servicio: {booking.job_description}</li>
                </ul>
                <p>El pago se procesará según los términos acordados.</p>
                '''
            )
            
            # ✅ NOTIFICACIÓN AL CLIENTE: Confirmación de pago
            create_notification(
                user_id=booking.client_id,
                notification_type='payment',
                title='✅ Pago confirmado',
                message=f'Tu pago de €{payment.amount / 100:.2f} ha sido procesado correctamente',
                link='/bookings',
                related_id=booking.id
            )
        
        db.session.commit()
        
        return jsonify({
            'status': intent.status,
            'payment': payment.to_dict(),
            'booking_id': payment.booking_id
        })
        
    except stripe.error.StripeError as e:
        return jsonify({'error': f'Error de Stripe: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Error del servidor: {str(e)}'}), 500

@app.route('/api/stripe-config', methods=['GET'])
def get_stripe_config():
    return jsonify({
        'publishable_key': STRIPE_PUBLISHABLE_KEY
    })

@app.route('/api/bookings/<int:booking_id>/payment-status', methods=['GET'])
def get_payment_status(booking_id):
    payment = Payment.query.filter_by(booking_id=booking_id).first()
    
    if not payment:
        return jsonify({
            'has_payment': False,
            'status': 'no_payment'
        })
    
    return jsonify({
        'has_payment': True,
        'payment': payment.to_dict()
    })

# --- RUTAS PARA MAPA Y GEOLOCALIZACIÓN ---
@app.route("/api/pilots/nearby", methods=['POST'])
def get_nearby_pilots():
    data = request.get_json()
    user_lat = data.get('latitude')
    user_lng = data.get('longitude')
    radius_km = data.get('radius', 25)
    
    if not user_lat or not user_lng:
        return jsonify({"error": "Coordenadas requeridas"}), 400
    
    try:
        def calculate_distance(lat1, lon1, lat2, lon2):
            R = 6371
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            return R * c
        
        profiles = PilotProfile.query.filter(
            PilotProfile.latitude.isnot(None),
            PilotProfile.longitude.isnot(None)
        ).all()
        
        nearby_pilots = []
        for profile in profiles:
            distance = calculate_distance(
                float(user_lat), float(user_lng),
                float(profile.latitude), float(profile.longitude)
            )
            
            if distance <= radius_km:
                reviews = Review.query.filter_by(pilot_profile_id=profile.id).all()
                total_reviews = len(reviews)
                average_rating = sum(r.rating for r in reviews) / total_reviews if total_reviews > 0 else 0
                
                pilot_dict = profile.to_dict()
                pilot_dict.update({
                    "distance": round(distance, 1),
                    "total_reviews": total_reviews,
                    "average_rating": round(average_rating, 1)
                })
                nearby_pilots.append(pilot_dict)
        
        nearby_pilots.sort(key=lambda x: x['distance'])
        return jsonify(nearby_pilots)
        
    except Exception as e:
        return jsonify({"error": f"Error calculando pilotos cercanos: {str(e)}"}), 500

# --- RUTAS PARA CHAT ---
@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    email = request.args.get('email')
    if not email:
        return jsonify({"error": "Email requerido"}), 400
    
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    
    conversations = []
    
    if user.role == 'Cliente':
        convs = Conversation.query.filter_by(client_id=user.id).order_by(Conversation.last_message_at.desc()).all()
        conversations = [conv.to_dict() for conv in convs]
    elif user.role == 'Piloto' and user.pilot_profile:
        convs = Conversation.query.filter_by(pilot_profile_id=user.pilot_profile.id).order_by(Conversation.last_message_at.desc()).all()
        conversations = [conv.to_dict() for conv in convs]
    
    return jsonify(conversations)

@app.route('/api/conversations', methods=['POST'])
def start_conversation():
    data = request.get_json()
    
    client = User.query.filter_by(email=data.get('client_email')).first()
    pilot_profile = PilotProfile.query.get(data.get('pilot_profile_id'))
    
    if not client or client.role != 'Cliente':
        return jsonify({"error": "Cliente no válido"}), 403
    
    if not pilot_profile:
        return jsonify({"error": "Piloto no encontrado"}), 404
    
    existing_conv = Conversation.query.filter_by(
        client_id=client.id,
        pilot_profile_id=pilot_profile.id
    ).first()
    
    if existing_conv:
        return jsonify({
            "message": "Conversación encontrada",
            "conversation": existing_conv.to_dict()
        })
    
    new_conversation = Conversation(
        client_id=client.id,
        pilot_profile_id=pilot_profile.id
    )
    
    db.session.add(new_conversation)
    db.session.commit()
    
    return jsonify({
        "message": "Conversación creada",
        "conversation": new_conversation.to_dict()
    }), 201

@app.route('/api/conversations/<int:conversation_id>/messages', methods=['GET'])
def get_messages(conversation_id):
    conversation = Conversation.query.get(conversation_id)
    if not conversation:
        return jsonify({"error": "Conversación no encontrada"}), 404
    
    email = request.args.get('email')
    user = User.query.filter_by(email=email).first()
    
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    
    has_access = False
    if user.role == 'Cliente' and conversation.client_id == user.id:
        has_access = True
    elif user.role == 'Piloto' and user.pilot_profile and conversation.pilot_profile_id == user.pilot_profile.id:
        has_access = True
    
    if not has_access:
        return jsonify({"error": "No autorizado"}), 403
    
    messages = Message.query.filter_by(conversation_id=conversation_id).order_by(Message.created_at.asc()).all()
    
    unread_messages = [msg for msg in messages if not msg.is_read and msg.sender_id != user.id]
    for msg in unread_messages:
        msg.is_read = True
    
    if unread_messages:
        db.session.commit()
    
    return jsonify({
        "conversation": conversation.to_dict(),
        "messages": [msg.to_dict() for msg in messages]
    })

@app.route('/api/conversations/<int:conversation_id>/messages', methods=['POST'])
def send_message(conversation_id):
    data = request.get_json()
    
    conversation = Conversation.query.get(conversation_id)
    if not conversation:
        return jsonify({"error": "Conversación no encontrada"}), 404
    
    email = data.get('sender_email')
    user = User.query.filter_by(email=email).first()
    
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    
    sender_type = None
    if user.role == 'Cliente' and conversation.client_id == user.id:
        sender_type = 'client'
        recipient_id = conversation.pilot_profile.user_id
    elif user.role == 'Piloto' and user.pilot_profile and conversation.pilot_profile_id == user.pilot_profile.id:
        sender_type = 'pilot'
        recipient_id = conversation.client_id
    
    if not sender_type:
        return jsonify({"error": "No autorizado"}), 403
    
    content = data.get('content', '').strip()
    if not content:
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400
    
    message = Message(
        content=content,
        sender_type=sender_type,
        sender_id=user.id,
        conversation_id=conversation_id
    )
    
    conversation.last_message_at = datetime.utcnow()
    
    db.session.add(message)
    db.session.commit()
    
    # ✅ NOTIFICACIÓN AL RECEPTOR: Nuevo mensaje
    sender_name = user.username if sender_type == 'client' else user.pilot_profile.name
    create_notification(
        user_id=recipient_id,
        notification_type='message',
        title='💬 Nuevo mensaje',
        message=f'{sender_name}: {content[:50]}{"..." if len(content) > 50 else ""}',
        link=f'/chat/{conversation_id}',
        related_id=conversation_id
    )
    
    return jsonify({
        "message": "Mensaje enviado",
        "data": message.to_dict()
    }), 201
@app.route('/api/chat/unread-count', methods=['GET'])
def get_unread_count():
    email = request.args.get('email')
    user = User.query.filter_by(email=email).first()
    
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    
    unread_count = 0
    
    if user.role == 'Cliente':
        conversations = Conversation.query.filter_by(client_id=user.id).all()
        for conv in conversations:
            unread_count += Message.query.filter_by(
                conversation_id=conv.id,
                sender_type='pilot',
                is_read=False
            ).count()
    elif user.role == 'Piloto' and user.pilot_profile:
        conversations = Conversation.query.filter_by(pilot_profile_id=user.pilot_profile.id).all()
        for conv in conversations:
            unread_count += Message.query.filter_by(
                conversation_id=conv.id,
                sender_type='client',
                is_read=False
            ).count()
    
    return jsonify({"unread_count": unread_count})

# --- RUTAS PRINCIPALES ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(os.path.join(app.instance_path, 'static', 'uploads'), filename)

@app.route("/api/pilots")
def get_pilots_with_reviews():
    profiles = PilotProfile.query.all()
    pilots_with_reviews = []
    
    for profile in profiles:
        reviews = Review.query.filter_by(pilot_profile_id=profile.id).all()
        total_reviews = len(reviews)
        average_rating = sum(r.rating for r in reviews) / total_reviews if total_reviews > 0 else 0
        
        pilot_dict = profile.to_dict()
        pilot_dict.update({
            "total_reviews": total_reviews,
            "average_rating": round(average_rating, 1)
        })
        pilots_with_reviews.append(pilot_dict)
    
    return jsonify(pilots_with_reviews)

@app.route("/api/pilots/<int:profile_id>")
def get_pilot_details(profile_id):
    profile = PilotProfile.query.get(profile_id)
    if not profile:
        return jsonify({"error": "Perfil no encontrado"}), 404
    return jsonify(profile.to_dict())

@app.route("/api/register", methods=['POST'])
def register():
    data = request.get_json()
    username, email, password, password_confirm, role = (
        data.get('username'), data.get('email'), data.get('password'), 
        data.get('password_confirm'), data.get('role', 'Cliente')
    )
    
    if not all([username, email, password, password_confirm]):
        return jsonify({"error": "Todos los campos son requeridos"}), 400
    if password != password_confirm:
        return jsonify({"error": "Las contraseñas no coinciden"}), 400
    if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
        return jsonify({"error": "Usuario o email ya existen"}), 409
    
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_user = User(username=username, email=email, password=hashed, role=role)
    db.session.add(new_user)
    db.session.commit()
    
    if new_user.role == 'Piloto':
        profile = PilotProfile(name=new_user.username, user_id=new_user.id)
        db.session.add(profile)
        db.session.commit()
    
    return jsonify({"message": "Usuario creado con éxito"}), 201

@app.route("/api/login", methods=['POST'])
def login():
    data = request.get_json()
    email, password = data.get('email'), data.get('password')
    
    if not email or not password:
        return jsonify({"error": "Email y contraseña son requeridos"}), 400
    
    user = User.query.filter_by(email=email).first()
    if user and bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        pilot_profile_id = user.pilot_profile.id if user.pilot_profile else None
        return jsonify({
            "message": "Inicio de sesión exitoso", 
            "user": {
                "id": user.id, "email": user.email, "role": user.role, 
                "username": user.username, "pilot_profile_id": pilot_profile_id
            }
        }), 200
    
    return jsonify({"error": "Credenciales inválidas"}), 401

@app.route("/api/profile", methods=['POST'])
def handle_profile():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()
    
    if not user or user.role != 'Piloto':
        return jsonify({"error": "Usuario no es piloto"}), 403
    
    profile = user.pilot_profile
    old_location = profile.location
    
    profile.name = data.get('name', profile.name)
    profile.tagline = data.get('tagline', profile.tagline)
    profile.location = data.get('location', profile.location)
    profile.bio = data.get('bio', profile.bio)
    profile.hourly_rate = data.get('hourly_rate', profile.hourly_rate)
    profile.phone = data.get('phone', profile.phone)
    
    if data.get('location') and data.get('location') != old_location:
        try:
            sample_coordinates = {
                "madrid": {"lat": 40.4168, "lng": -3.7038},
                "barcelona": {"lat": 41.3851, "lng": 2.1734},
                "valencia": {"lat": 39.4699, "lng": -0.3763},
                "sevilla": {"lat": 37.3886, "lng": -5.9823},
                "zaragoza": {"lat": 41.6488, "lng": -0.8891},
                "málaga": {"lat": 36.7196, "lng": -4.4214},
                "murcia": {"lat": 37.9922, "lng": -1.1307},
                "palma": {"lat": 39.5696, "lng": 2.6502},
                "bilbao": {"lat": 43.263, "lng": -2.9349},
                "alicante": {"lat": 38.3452, "lng": -0.4810}
            }
            
            location_lower = data.get('location').lower()
            for city, coords in sample_coordinates.items():
                if city in location_lower:
                    profile.latitude = coords["lat"]
                    profile.longitude = coords["lng"]
                    break
        except:
            pass
    
    db.session.commit()
    return jsonify({"message": "Perfil guardado"})

@app.route("/api/book", methods=['POST'])
def create_booking():
    data = request.get_json()
    
    client = User.query.filter_by(email=data.get('client_email')).first()
    pilot = PilotProfile.query.get(data.get('pilot_id'))
    
    if not client or not pilot:
        return jsonify({"error": "Cliente o piloto no encontrado"}), 404
    
    try:
        booking_date = datetime.strptime(data.get('booking_date'), '%Y-%m-%d').date()
        start_time = datetime.strptime(data.get('start_time'), '%H:%M').time()
        end_time = datetime.strptime(data.get('end_time'), '%H:%M').time()
    except (ValueError, TypeError):
        return jsonify({"error": "Formato de fecha/hora inválido"}), 400
    
    duration_hours = (datetime.combine(booking_date, end_time) - 
                     datetime.combine(booking_date, start_time)).seconds // 3600
    total_price = duration_hours * pilot.hourly_rate
    
    new_booking = Booking(
        client_id=client.id,
        pilot_profile_id=pilot.id,
        job_description=data.get('job_description'),
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        total_price=total_price,
        service_package_id=data.get('service_package_id')
    )
    
    db.session.add(new_booking)
    db.session.commit()
    
    create_notification(
        user_id=pilot.user_id,
        notification_type='booking',
        title='Nueva solicitud de reserva',
        message=f'{client.username} ha solicitado una reserva para el {booking_date.strftime("%d/%m/%Y")}',
        link=f'/dashboard/bookings',
        related_id=new_booking.id
    )
    
    send_email_notification(
        to_email=pilot.user.email,
        subject='Nueva Reserva en DroneBook',
        html_content=f'''
        <h2>Nueva Solicitud de Reserva</h2>
        <p>Hola {pilot.name},</p>
        <p><strong>{client.username}</strong> ha solicitado una reserva:</p>
        <ul>
            <li>Fecha: {booking_date.strftime("%d/%m/%Y")}</li>
            <li>Hora: {start_time.strftime("%H:%M")} - {end_time.strftime("%H:%M")}</li>
            <li>Descripción: {data.get('job_description')}</li>
            <li>Precio: €{total_price}</li>
        </ul>
        <p>Accede a DroneBook para aceptar o rechazar la reserva.</p>
        '''
    )
    
    return jsonify({
        "message": "Solicitud de reserva enviada",
        "booking": new_booking.to_dict()
    })

@app.route("/api/bookings", methods=['GET'])
def get_bookings():
    user = User.query.filter_by(email=request.args.get('email')).first()
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 404
    
    if user.role == 'Cliente':
        bookings = user.bookings_made
    elif user.role == 'Piloto' and user.pilot_profile:
        bookings = user.pilot_profile.bookings_received
    else:
        bookings = []
    
    return jsonify([b.to_dict() for b in bookings])

@app.route("/api/bookings/<int:booking_id>/respond", methods=['POST'])
def respond_to_booking(booking_id):
    booking = Booking.query.get(booking_id)
    if not booking:
        return jsonify({"error": "Reserva no encontrada"}), 404
    
    new_status = request.json.get('status')
    if new_status not in ['confirmed', 'rejected', 'completed']:
        return jsonify({"error": "Estado inválido"}), 400
    
    booking.status = new_status
    db.session.commit()
    
    status_messages = {
        'confirmed': 'ha aceptado',
        'rejected': 'ha rechazado',
        'completed': 'ha marcado como completada'
    }
    
    pilot_profile = PilotProfile.query.get(booking.pilot_profile_id)
    client = User.query.get(booking.client_id)
    
    create_notification(
        user_id=booking.client_id,
        notification_type='booking',
        title=f'Actualización de reserva',
        message=f'{pilot_profile.name} {status_messages[new_status]} tu reserva del {booking.booking_date.strftime("%d/%m/%Y")}',
        link=f'/bookings',
        related_id=booking.id
    )
    
    send_email_notification(
        to_email=client.email,
        subject=f'Reserva {new_status.capitalize()} - DroneBook',
        html_content=f'''
        <h2>Estado de Reserva Actualizado</h2>
        <p>Hola {client.username},</p>
        <p><strong>{pilot_profile.name}</strong> {status_messages[new_status]} tu reserva:</p>
        <ul>
            <li>Fecha: {booking.booking_date.strftime("%d/%m/%Y")}</li>
            <li>Hora: {booking.start_time.strftime("%H:%M")} - {booking.end_time.strftime("%H:%M")}</li>
            <li>Estado: <strong>{new_status.upper()}</strong></li>
        </ul>
        '''
    )
    
    return jsonify({"message": f"Reserva {booking.status}"})

@app.route("/api/search", methods=['POST'])
def search_pilots():
    if not model:
        return jsonify({"error": "La función de búsqueda con IA no está configurada en el servidor."}), 500
    
    user_query = request.json.get("query")
    if not user_query:
        return jsonify({"error": "No se ha proporcionado ninguna consulta."}), 400

    try:
        profiles = PilotProfile.query.all()
        profiles_list = [p.to_dict() for p in profiles]
        
        prompt = f"""
        Eres un asistente experto en la plataforma "DroneBook". Tu misión es ayudar a los usuarios a encontrar el piloto de dron perfecto.
        A continuación, te proporciono una lista de los perfiles de los pilotos disponibles en formato JSON: {profiles_list}
        ---
        Analiza la siguiente petición de un usuario y recomiéndale el mejor piloto. Justifica brevemente por qué. Responde en español.
        Petición del usuario: "{user_query}"
        """
        response = model.generate_content(prompt)
        return jsonify({"recommendation": response.text})
    except Exception as e:
        return jsonify({"error": f"Ha ocurrido un error con la IA: {e}"}), 500

# --- RUTAS ADICIONALES PARA GESTIÓN PILOTO ---
@app.route("/api/profile/services", methods=['POST'])
def add_service():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()
    
    if not user or user.role != 'Piloto' or not user.pilot_profile:
        return jsonify({"error": "Usuario no es piloto"}), 403
    
    service = ServicePackage(
        name=data.get('name'),
        description=data.get('description'),
        price=int(data.get('price')),
        duration_hours=int(data.get('duration_hours', 2)),
        pilot_profile_id=user.pilot_profile.id
    )
    
    db.session.add(service)
    db.session.commit()
    
    return jsonify({"message": "Servicio añadido", "service": service.to_dict()})

@app.route("/api/profile/portfolio", methods=['POST'])
def add_portfolio_item():
    user = User.query.filter_by(email=request.form.get('email')).first()
    
    if not user or user.role != 'Piloto' or not user.pilot_profile:
        return jsonify({"error": "Usuario no es piloto"}), 403
    
    if 'file' not in request.files:
        return jsonify({"error": "No se ha subido archivo"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No se ha seleccionado archivo"}), 400
    
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    
    portfolio_item = PortfolioItem(
        file_url='/uploads/' + filename,
        title=request.form.get('title', ''),
        description=request.form.get('description', ''),
        pilot_profile_id=user.pilot_profile.id
    )
    
    db.session.add(portfolio_item)
    db.session.commit()
    
    return jsonify({"message": "Imagen añadida al portfolio"})

@app.route("/api/pilots/<int:pilot_id>/availability", methods=['POST'])
def add_availability(pilot_id):
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()
    
    if not user or user.role != 'Piloto' or not user.pilot_profile:
        return jsonify({"error": "Usuario no es piloto"}), 403
    
    if user.pilot_profile.id != pilot_id:
        return jsonify({"error": "No autorizado"}), 403
    
    try:
        date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
        start_time = datetime.strptime(data.get('start_time'), '%H:%M').time()
        end_time = datetime.strptime(data.get('end_time'), '%H:%M').time()
    except (ValueError, TypeError):
        return jsonify({"error": "Formato de fecha/hora inválido"}), 400
    
    slot = AvailabilitySlot(
        pilot_profile_id=pilot_id,
        date=date,
        start_time=start_time,
        end_time=end_time
    )
    
    db.session.add(slot)
    db.session.commit()
    
    return jsonify({"message": "Disponibilidad añadida"})

@app.route("/api/availability/<int:slot_id>", methods=['DELETE'])
def delete_availability(slot_id):
    slot = AvailabilitySlot.query.get(slot_id)
    if not slot:
        return jsonify({"error": "Horario no encontrado"}), 404
    
    db.session.delete(slot)
    db.session.commit()
    
    return jsonify({"message": "Horario eliminado"})

@app.route("/api/portfolio/<int:item_id>", methods=['DELETE'])
def delete_portfolio_item(item_id):
    item = PortfolioItem.query.get(item_id)
    if not item:
        return jsonify({"error": "Elemento no encontrado"}), 404
    
    try:
        file_path = os.path.join(app.instance_path, 'static', item.file_url.lstrip('/'))
        if os.path.exists(file_path):
            os.remove(file_path)
    except:
        pass
    
    db.session.delete(item)
    db.session.commit()
    
    return jsonify({"message": "Elemento eliminado"})

# --- RUTAS DEL PANEL DE ADMINISTRACIÓN ---
def require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        email = request.args.get('admin_email') or request.json.get('admin_email')
        if not email:
            return jsonify({"error": "Email de admin requerido"}), 401
        
        user = User.query.filter_by(email=email).first()
        if not user or user.role != 'Admin':
            return jsonify({"error": "Acceso denegado. Solo administradores."}), 403
        
        return f(*args, **kwargs)
    return decorated_function

@app.route("/api/admin/stats", methods=['GET'])
@require_admin
def get_admin_stats():
    try:
        total_users = User.query.count()
        total_clients = User.query.filter_by(role='Cliente').count()
        total_pilots = User.query.filter_by(role='Piloto').count()
        total_admins = User.query.filter_by(role='Admin').count()
        
        total_bookings = Booking.query.count()
        pending_bookings = Booking.query.filter_by(status='pending').count()
        confirmed_bookings = Booking.query.filter_by(status='confirmed').count()
        completed_bookings = Booking.query.filter_by(status='completed').count()
        paid_bookings = Booking.query.filter_by(status='paid').count()
        
        total_revenue = db.session.query(db.func.sum(Booking.total_price)).filter_by(status='paid').scalar() or 0
        
        total_payments = Payment.query.count()
        successful_payments = Payment.query.filter_by(status='succeeded').count()
        
        total_conversations = Conversation.query.count()
        total_messages = Message.query.count()
        
        total_reviews = Review.query.count()
        average_rating = db.session.query(db.func.avg(Review.rating)).scalar() or 0
        
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        new_users = User.query.filter(User.created_at >= thirty_days_ago).count()
        
        return jsonify({
            "users": {
                "total": total_users,
                "clients": total_clients,
                "pilots": total_pilots,
                "admins": total_admins,
                "new_last_30_days": new_users
            },
            "bookings": {
                "total": total_bookings,
                "pending": pending_bookings,
                "confirmed": confirmed_bookings,
                "completed": completed_bookings,
                "paid": paid_bookings
            },
            "revenue": {
                "total": total_revenue,
                "average_per_booking": round(total_revenue / paid_bookings, 2) if paid_bookings > 0 else 0
            },
            "payments": {
                "total": total_payments,
                "successful": successful_payments,
                "success_rate": round((successful_payments / total_payments * 100), 2) if total_payments > 0 else 0
            },
            "engagement": {
                "conversations": total_conversations,
                "messages": total_messages,
                "reviews": total_reviews,
                "average_rating": round(average_rating, 2)
            }
        })
    except Exception as e:
        return jsonify({"error": f"Error obteniendo estadísticas: {str(e)}"}), 500

@app.route("/api/admin/users", methods=['GET'])
@require_admin
def get_all_users():
    try:
        users = User.query.all()
        users_list = []
        
        for user in users:
            user_dict = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat(),
                "has_pilot_profile": user.pilot_profile is not None,
                "total_bookings_made": len(user.bookings_made)
            }
            
            if user.pilot_profile:
                bookings_received = len(user.pilot_profile.bookings_received)
                user_dict["total_bookings_received"] = bookings_received
            
            users_list.append(user_dict)
        
        return jsonify(users_list)
    except Exception as e:
        return jsonify({"error": f"Error obteniendo usuarios: {str(e)}"}), 500

@app.route("/api/admin/users/<int:user_id>", methods=['PUT'])
@require_admin
def update_user_status(user_id):
    try:
        data = request.get_json()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        if user.role == 'Admin':
            return jsonify({"error": "No se puede modificar un administrador"}), 403
        
        if 'is_active' in data:
            user.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            "message": "Usuario actualizado correctamente",
            "user": {
                "id": user.id,
                "username": user.username,
                "is_active": user.is_active
            }
        })
    except Exception as e:
        return jsonify({"error": f"Error actualizando usuario: {str(e)}"}), 500

@app.route("/api/admin/users/<int:user_id>", methods=['DELETE'])
@require_admin
def delete_user(user_id):
    try:
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        if user.role == 'Admin':
            return jsonify({"error": "No se puede eliminar un administrador"}), 403
        
        username = user.username
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({"message": f"Usuario {username} eliminado correctamente"})
    except Exception as e:
        return jsonify({"error": f"Error eliminando usuario: {str(e)}"}), 500

@app.route("/api/admin/bookings", methods=['GET'])
@require_admin
def get_all_bookings():
    try:
        bookings = Booking.query.order_by(Booking.created_at.desc()).all()
        return jsonify([b.to_dict() for b in bookings])
    except Exception as e:
        return jsonify({"error": f"Error obteniendo reservas: {str(e)}"}), 500

@app.route("/api/admin/reviews", methods=['GET'])
@require_admin
def get_all_reviews():
    try:
        reviews = Review.query.order_by(Review.created_at.desc()).all()
        return jsonify([r.to_dict() for r in reviews])
    except Exception as e:
        return jsonify({"error": f"Error obteniendo reviews: {str(e)}"}), 500

@app.route("/api/admin/reviews/<int:review_id>", methods=['DELETE'])
@require_admin
def delete_review(review_id):
    try:
        review = Review.query.get(review_id)
        
        if not review:
            return jsonify({"error": "Review no encontrada"}), 404
        
        db.session.delete(review)
        db.session.commit()
        
        return jsonify({"message": "Review eliminada correctamente"})
    except Exception as e:
        return jsonify({"error": f"Error eliminando review: {str(e)}"}), 500

@app.route("/api/admin/pilots/pending", methods=['GET'])
@require_admin
def get_pending_pilots():
    try:
        pilots = PilotProfile.query.filter(
            (PilotProfile.bio == None) | (PilotProfile.bio == '')
        ).all()
        
        pilots_list = []
        for pilot in pilots:
            pilot_dict = pilot.to_dict()
            pilot_dict['user_email'] = pilot.user.email
            pilot_dict['user_created_at'] = pilot.user.created_at.isoformat()
            pilots_list.append(pilot_dict)
        
        return jsonify(pilots_list)
    except Exception as e:
        return jsonify({"error": f"Error obteniendo pilotos pendientes: {str(e)}"}), 500

# --- RUTAS PARA CERTIFICACIONES ---
@app.route("/api/pilots/<int:pilot_id>/certifications", methods=['GET'])
def get_pilot_certifications(pilot_id):
    try:
        certifications = Certification.query.filter_by(pilot_profile_id=pilot_id).all()
        return jsonify([cert.to_dict() for cert in certifications])
    except Exception as e:
        return jsonify({"error": f"Error obteniendo certificaciones: {str(e)}"}), 500

@app.route("/api/pilots/<int:pilot_id>/certifications", methods=['POST'])
def add_certification(pilot_id):
    try:
        user = User.query.filter_by(email=request.form.get('email')).first()
        
        if not user or user.role != 'Piloto' or not user.pilot_profile:
            return jsonify({"error": "Usuario no es piloto"}), 403
        
        if user.pilot_profile.id != pilot_id:
            return jsonify({"error": "No autorizado"}), 403
        
        document_url = None
        if 'document' in request.files:
            file = request.files['document']
            if file.filename != '':
                filename = secure_filename(f"cert_{pilot_id}_{datetime.utcnow().timestamp()}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                document_url = '/uploads/' + filename
        
        issue_date = None
        expiry_date = None
        if request.form.get('issue_date'):
            issue_date = datetime.strptime(request.form.get('issue_date'), '%Y-%m-%d').date()
        if request.form.get('expiry_date'):
            expiry_date = datetime.strptime(request.form.get('expiry_date'), '%Y-%m-%d').date()
        
        certification = Certification(
            pilot_profile_id=pilot_id,
            certification_type=request.form.get('certification_type'),
            name=request.form.get('name'),
            description=request.form.get('description'),
            document_url=document_url,
            issue_date=issue_date,
            expiry_date=expiry_date
        )
        
        db.session.add(certification)
        db.session.commit()
        
        return jsonify({
            "message": "Certificación añadida correctamente",
            "certification": certification.to_dict()
        }), 201
        
    except Exception as e:
        return jsonify({"error": f"Error añadiendo certificación: {str(e)}"}), 500

@app.route("/api/certifications/<int:cert_id>", methods=['DELETE'])
def delete_certification(cert_id):
    try:
        certification = Certification.query.get(cert_id)
        
        if not certification:
            return jsonify({"error": "Certificación no encontrada"}), 404
        
        if certification.document_url:
            try:
                file_path = os.path.join(app.instance_path, 'static', certification.document_url.lstrip('/'))
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
        
        db.session.delete(certification)
        db.session.commit()
        
        return jsonify({"message": "Certificación eliminada"})
    except Exception as e:
        return jsonify({"error": f"Error eliminando certificación: {str(e)}"}), 500

@app.route("/api/admin/certifications/pending", methods=['GET'])
@require_admin
def get_pending_certifications():
    try:
        certifications = Certification.query.filter_by(verification_status='pending').all()
        
        certs_list = []
        for cert in certifications:
            cert_dict = cert.to_dict()
            cert_dict['pilot_name'] = cert.pilot_profile.name
            cert_dict['pilot_email'] = cert.pilot_profile.user.email
            certs_list.append(cert_dict)
        
        return jsonify(certs_list)
    except Exception as e:
        return jsonify({"error": f"Error obteniendo certificaciones pendientes: {str(e)}"}), 500

@app.route("/api/admin/certifications/<int:cert_id>/verify", methods=['POST'])
@require_admin
def verify_certification(cert_id):
    try:
        data = request.get_json()
        admin = User.query.filter_by(email=data.get('admin_email')).first()
        
        certification = Certification.query.get(cert_id)
        if not certification:
            return jsonify({"error": "Certificación no encontrada"}), 404
        
        status = data.get('status')
        if status not in ['verified', 'rejected']:
            return jsonify({"error": "Estado inválido"}), 400
        
        certification.verification_status = status
        certification.verified_by = admin.id
        certification.verified_at = datetime.utcnow()
        
        db.session.commit()
        
        # ✅ NOTIFICACIÓN AL PILOTO sobre verificación
        pilot = certification.pilot_profile
        status_emoji = '✅' if status == 'verified' else '❌'
        status_text = 'verificada' if status == 'verified' else 'rechazada'
        
        create_notification(
            user_id=pilot.user_id,
            notification_type='certification',
            title=f'{status_emoji} Certificación {status_text}',
            message=f'Tu certificación "{certification.name}" ha sido {status_text}',
            link='/dashboard/certifications',
            related_id=cert_id
        )
        
        return jsonify({
            "message": f"Certificación {status}",
            "certification": certification.to_dict()
        })
    except Exception as e:
        return jsonify({"error": f"Error verificando certificación: {str(e)}"}), 500

# --- RUTAS PARA BADGES ---
@app.route("/api/pilots/<int:pilot_id>/badges", methods=['POST'])
def add_badge(pilot_id):
    try:
        data = request.get_json()
        user = User.query.filter_by(email=data.get('email')).first()
        
        if not user or user.role != 'Piloto' or not user.pilot_profile:
            return jsonify({"error": "Usuario no es piloto"}), 403
        
        if user.pilot_profile.id != pilot_id:
            return jsonify({"error": "No autorizado"}), 403
        
        available_badges = {
            "wedding": {"name": "Especialista en Bodas", "icon": "fa-rings-wedding", "color": "pink"},
            "real_estate": {"name": "Fotografía Inmobiliaria", "icon": "fa-building", "color": "blue"},
            "inspection": {"name": "Inspección Técnica", "icon": "fa-hard-hat", "color": "yellow"},
            "agriculture": {"name": "Agricultura de Precisión", "icon": "fa-tractor", "color": "green"},
            "film": {"name": "Producción Audiovisual", "icon": "fa-video", "color": "red"},
            "sports": {"name": "Eventos Deportivos", "icon": "fa-futbol", "color": "orange"}
        }
        
        badge_type = data.get('badge_type')
        if badge_type not in available_badges:
            return jsonify({"error": "Tipo de badge inválido"}), 400
        
        existing = Badge.query.filter_by(
            pilot_profile_id=pilot_id,
            badge_type=badge_type
        ).first()
        
        if existing:
            return jsonify({"error": "Ya tienes este badge"}), 409
        
        badge_info = available_badges[badge_type]
        badge = Badge(
            pilot_profile_id=pilot_id,
            badge_type=badge_type,
            name=badge_info["name"],
            icon=badge_info["icon"],
            color=badge_info["color"],
            description=data.get('description', '')
        )
        
        db.session.add(badge)
        db.session.commit()
        
        return jsonify({
            "message": "Badge añadido",
            "badge": badge.to_dict()
        }), 201
        
    except Exception as e:
        return jsonify({"error": f"Error añadiendo badge: {str(e)}"}), 500

@app.route("/api/badges/<int:badge_id>", methods=['DELETE'])
def delete_badge(badge_id):
    try:
        badge = Badge.query.get(badge_id)
        
        if not badge:
            return jsonify({"error": "Badge no encontrado"}), 404
        
        db.session.delete(badge)
        db.session.commit()
        
        return jsonify({"message": "Badge eliminado"})
    except Exception as e:
        return jsonify({"error": f"Error eliminando badge: {str(e)}"}), 500

# --- ✅ RUTAS PARA NOTIFICACIONES ---
@app.route("/api/notifications", methods=['GET'])
def get_notifications():
    """Obtener notificaciones del usuario"""
    try:
        email = request.args.get('email')
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        notifications = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(50).all()
        
        return jsonify({
            "notifications": [notif.to_dict() for notif in notifications],
            "unread_count": sum(1 for n in notifications if not n.is_read)
        })
    except Exception as e:
        return jsonify({"error": f"Error obteniendo notificaciones: {str(e)}"}), 500

@app.route("/api/notifications/<int:notif_id>/read", methods=['POST'])
def mark_notification_read(notif_id):
    """Marcar notificación como leída"""
    try:
        notification = Notification.query.get(notif_id)
        
        if not notification:
            return jsonify({"error": "Notificación no encontrada"}), 404
        
        notification.is_read = True
        db.session.commit()
        
        return jsonify({"message": "Notificación marcada como leída"})
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500

@app.route("/api/notifications/mark-all-read", methods=['POST'])
def mark_all_read():
    """Marcar todas las notificaciones como leídas"""
    try:
        data = request.get_json()
        email = data.get('email')
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        Notification.query.filter_by(user_id=user.id, is_read=False).update({"is_read": True})
        db.session.commit()
        
        return jsonify({"message": "Todas las notificaciones marcadas como leídas"})
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500

@app.route("/api/notifications/unread-count", methods=['GET'])
def get_unread_notifications_count():
    """Obtener contador de notificaciones no leídas"""
    try:
        email = request.args.get('email')
        user = User.query.filter_by(email=email).first()
        
        if not user:
            return jsonify({"error": "Usuario no encontrado"}), 404
        
        unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
        
        return jsonify({"unread_count": unread_count})
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 500

# --- RUTA PARA AÑADIR REVIEWS (CON NOTIFICACIÓN) ---
@app.route("/api/pilots/<int:pilot_id>/reviews", methods=['POST'])
def add_review(pilot_id):
    """Añadir una review a un piloto"""
    try:
        data = request.get_json()
        user = User.query.filter_by(email=data.get('email')).first()
        
        if not user or user.role != 'Cliente':
            return jsonify({"error": "Solo los clientes pueden dejar reviews"}), 403
        
        pilot_profile = PilotProfile.query.get(pilot_id)
        if not pilot_profile:
            return jsonify({"error": "Piloto no encontrado"}), 404
        
        rating = data.get('rating')
        if not rating or rating < 1 or rating > 5:
            return jsonify({"error": "La calificación debe estar entre 1 y 5"}), 400
        
        review = Review(
            rating=rating,
            comment=data.get('comment', ''),
            client_id=user.id,
            pilot_profile_id=pilot_id,
            booking_id=data.get('booking_id')
        )
        
        db.session.add(review)
        db.session.commit()
        
        # ✅ NOTIFICACIÓN AL PILOTO sobre nueva review
        stars = '⭐' * rating
        create_notification(
            user_id=pilot_profile.user_id,
            notification_type='system',
            title=f'Nueva reseña recibida {stars}',
            message=f'{user.username} te ha dejado una reseña de {rating} estrellas',
            link='/dashboard/reviews',
            related_id=review.id
        )
        
        return jsonify({
            "message": "Review añadida correctamente",
            "review": review.to_dict()
        }), 201
        
    except Exception as e:
        return jsonify({"error": f"Error añadiendo review: {str(e)}"}), 500

@app.route("/api/pilots/<int:pilot_id>/reviews", methods=['GET'])
def get_pilot_reviews(pilot_id):
    """Obtener reviews de un piloto"""
    try:
        reviews = Review.query.filter_by(pilot_profile_id=pilot_id).order_by(Review.created_at.desc()).all()
        return jsonify([r.to_dict() for r in reviews])
    except Exception as e:
        return jsonify({"error": f"Error obteniendo reviews: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)