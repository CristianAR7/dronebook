from backend import app, db, User
import bcrypt

with app.app_context():
    # Verificar si ya existe un admin
    existing_admin = User.query.filter_by(role='Admin').first()
    
    if existing_admin:
        print(f"Ya existe un administrador: {existing_admin.email}")
    else:
        # Crear nuevo admin
        admin_user = User(
            username="admin",
            email="admin@dronebook.com",
            password=bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),
            role="Admin",
            is_active=True
        )
        db.session.add(admin_user)
        db.session.commit()
        
        print("✅ Usuario administrador creado!")
        print("Email: admin@dronebook.com")
        print("Contraseña: admin123")
        print("⚠️  Cambia esta contraseña en producción!")