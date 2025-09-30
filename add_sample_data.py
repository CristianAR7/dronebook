from backend import app, db, PilotProfile, User
import bcrypt

with app.app_context():
    # Crear usuarios pilotos de ejemplo si no existen
    pilots_data = [
        {"name": "Carlos Madrid", "location": "Madrid", "lat": 40.4168, "lng": -3.7038, "rate": 75},
        {"name": "Ana Barcelona", "location": "Barcelona", "lat": 41.3851, "lng": 2.1734, "rate": 85},
        {"name": "Luis Valencia", "location": "Valencia", "lat": 39.4699, "lng": -0.3763, "rate": 65},
        {"name": "María Sevilla", "location": "Sevilla", "lat": 37.3886, "lng": -5.9823, "rate": 70},
    ]
    
    for pilot_data in pilots_data:
        email = f"{pilot_data['name'].replace(' ', '_').lower()}@test.com"
        
        # Verificar si ya existe
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            print(f"Usuario {email} ya existe, saltando...")
            continue
        
        # Crear usuario
        user = User(
            username=pilot_data["name"].replace(" ", "_").lower(),
            email=email,
            password=bcrypt.hashpw("123456".encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
            role="Piloto"
        )
        db.session.add(user)
        db.session.flush()
        
        # Crear perfil de piloto
        profile = PilotProfile(
            name=pilot_data["name"],
            location=pilot_data["location"],
            latitude=pilot_data["lat"],
            longitude=pilot_data["lng"],
            hourly_rate=pilot_data["rate"],
            tagline="Piloto profesional especializado en eventos",
            bio="Experiencia en grabación aérea y eventos especiales",
            user_id=user.id
        )
        db.session.add(profile)
        print(f"Creado piloto: {pilot_data['name']}")
    
    db.session.commit()
    print("¡Datos de ejemplo añadidos!")