import os
from backend import app, db, User, PilotProfile
import bcrypt

# Si ejecutas este archivo directamente, borrará y poblará la base de datos
if __name__ == "__main__":
    with app.app_context():
        print("Eliminando base de datos existente...")
        db.drop_all()
        print("Creando nuevas tablas...")
        db.create_all()
        print("Tablas creadas.")

        print("Poblando con datos de prueba...")
        client_password = 'password_cliente'
        client_hashed = bcrypt.hashpw(client_password.encode('utf-8'), bcrypt.gensalt())
        client_user = User(username='cliente_test', email='cliente@test.com', password=client_hashed.decode('utf-8'), role='Cliente')
        
        pilot_password = 'password_piloto'
        pilot_hashed = bcrypt.hashpw(pilot_password.encode('utf-8'), bcrypt.gensalt())
        pilot_user = User(username='piloto_test', email='piloto@test.com', password=pilot_hashed.decode('utf-8'), role='Piloto')
        
        profile = PilotProfile(name='AeroVision Pro')
        pilot_user.pilot_profile = profile
        
        db.session.add(client_user)
        db.session.add(pilot_user)
        db.session.commit()
        
        print("\n¡Base de datos poblada con éxito!")