#!/usr/bin/env python3
"""
Script para poblar la base de datos con datos de prueba
Ejecutar desde el mismo directorio que backend.py
"""

import os
import sys
import bcrypt
from datetime import datetime, date, time, timedelta

# Importar los modelos del backend
from backend import app, db, User, PilotProfile, ServicePackage, AvailabilitySlot, PortfolioItem

def create_test_data():
    with app.app_context():
        print("Creando datos de prueba...")
        
        # Limpiar datos existentes (opcional)
        # db.drop_all()
        # db.create_all()
        
        # 1. Crear usuarios de prueba
        users_data = [
            {
                'username': 'cliente_madrid',
                'email': 'cliente@madrid.com',
                'password': '123456',
                'role': 'Cliente'
            },
            {
                'username': 'cliente_barcelona', 
                'email': 'cliente@barcelona.com',
                'password': '123456',
                'role': 'Cliente'
            },
            {
                'username': 'piloto_alex',
                'email': 'alex@pilotos.com', 
                'password': '123456',
                'role': 'Piloto'
            },
            {
                'username': 'piloto_maria',
                'email': 'maria@pilotos.com',
                'password': '123456', 
                'role': 'Piloto'
            },
            {
                'username': 'piloto_carlos',
                'email': 'carlos@pilotos.com',
                'password': '123456',
                'role': 'Piloto'
            }
        ]
        
        created_users = {}
        for user_data in users_data:
            # Verificar si ya existe
            existing_user = User.query.filter_by(email=user_data['email']).first()
            if existing_user:
                print(f"Usuario {user_data['email']} ya existe")
                created_users[user_data['username']] = existing_user
                continue
                
            hashed_password = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            user = User(
                username=user_data['username'],
                email=user_data['email'], 
                password=hashed_password,
                role=user_data['role']
            )
            db.session.add(user)
            created_users[user_data['username']] = user
            print(f"✓ Creado usuario: {user_data['username']} ({user_data['role']})")
        
        db.session.commit()
        
        # 2. Crear perfiles de piloto con datos completos
        pilots_data = [
            {
                'user': 'piloto_alex',
                'name': 'Alex Rodríguez',
                'tagline': 'Especialista en fotografía aérea y eventos corporativos',
                'location': 'Madrid, España',
                'bio': 'Piloto certificado con más de 5 años de experiencia en fotografía y videografía aérea. Especializado en bodas, eventos corporativos y promociones inmobiliarias. Equipado con drones DJI Mavic 3 Pro y Mini 3 Pro.',
                'hourly_rate': 75,
                'phone': '+34 600 123 456'
            },
            {
                'user': 'piloto_maria',
                'name': 'María González',
                'tagline': 'Experta en inspecciones técnicas y mapeo agrícola',
                'location': 'Barcelona, España', 
                'bio': 'Ingeniera agrónoma y piloto profesional especializada in inspecciones de infraestructuras, mapeo de cultivos y análisis termográfico. Más de 200 vuelos técnicos completados.',
                'hourly_rate': 95,
                'phone': '+34 610 987 654'
            },
            {
                'user': 'piloto_carlos',
                'name': 'Carlos Mendoza',
                'tagline': 'Creatividad aérea para cine y publicidad',
                'location': 'Valencia, España',
                'bio': 'Director de fotografía aérea con amplia experiencia en producciones cinematográficas y spots publicitarios. Trabajó en más de 50 proyectos audiovisuales.',
                'hourly_rate': 120,
                'phone': '+34 620 456 789'
            }
        ]
        
        created_pilots = {}
        for pilot_data in pilots_data:
            user = created_users[pilot_data['user']]
            
            # Verificar si ya tiene perfil
            existing_profile = PilotProfile.query.filter_by(user_id=user.id).first()
            if existing_profile:
                print(f"Perfil para {pilot_data['name']} ya existe")
                created_pilots[pilot_data['user']] = existing_profile
                continue
                
            profile = PilotProfile(
                name=pilot_data['name'],
                tagline=pilot_data['tagline'], 
                location=pilot_data['location'],
                bio=pilot_data['bio'],
                hourly_rate=pilot_data['hourly_rate'],
                phone=pilot_data['phone'],
                user_id=user.id
            )
            db.session.add(profile)
            created_pilots[pilot_data['user']] = profile
            print(f"✓ Creado perfil de piloto: {pilot_data['name']}")
        
        db.session.commit()
        
        # 3. Crear servicios para cada piloto
        services_data = [
            # Servicios para Alex (fotografía)
            {
                'pilot': 'piloto_alex',
                'services': [
                    {
                        'name': 'Fotografía de Boda',
                        'description': 'Cobertura aérea completa de tu boda con fotografías profesionales desde perspectivas únicas.',
                        'price': 200,
                        'duration_hours': 3
                    },
                    {
                        'name': 'Evento Corporativo',
                        'description': 'Documentación profesional de eventos empresariales, conferencias y presentaciones.',
                        'price': 150,
                        'duration_hours': 2
                    },
                    {
                        'name': 'Promoción Inmobiliaria',
                        'description': 'Fotografías y videos aéreos para destacar propiedades y proyectos inmobiliarios.',
                        'price': 120,
                        'duration_hours': 2
                    }
                ]
            },
            # Servicios para María (técnico)
            {
                'pilot': 'piloto_maria',
                'services': [
                    {
                        'name': 'Inspección de Tejados',
                        'description': 'Inspección técnica detallada de tejados y estructuras con cámara térmica.',
                        'price': 180,
                        'duration_hours': 2
                    },
                    {
                        'name': 'Mapeo Agrícola',
                        'description': 'Análisis multispectral de cultivos para optimización de rendimientos.',
                        'price': 250,
                        'duration_hours': 3
                    },
                    {
                        'name': 'Inspección Industrial',
                        'description': 'Revisión de instalaciones industriales, torres y líneas eléctricas.',
                        'price': 300,
                        'duration_hours': 4
                    }
                ]
            },
            # Servicios para Carlos (audiovisual)
            {
                'pilot': 'piloto_carlos',
                'services': [
                    {
                        'name': 'Producción Cinematográfica',
                        'description': 'Tomas aéreas profesionales para producciones de cine y televisión.',
                        'price': 400,
                        'duration_hours': 4
                    },
                    {
                        'name': 'Spot Publicitario',
                        'description': 'Grabación aérea para campañas publicitarias y marketing digital.',
                        'price': 350,
                        'duration_hours': 3
                    },
                    {
                        'name': 'Video Musical',
                        'description': 'Dirección de fotografía aérea para videoclips musicales.',
                        'price': 280,
                        'duration_hours': 3
                    }
                ]
            }
        ]
        
        for pilot_services in services_data:
            pilot_profile = created_pilots[pilot_services['pilot']]
            for service_data in pilot_services['services']:
                # Verificar si ya existe
                existing_service = ServicePackage.query.filter_by(
                    pilot_profile_id=pilot_profile.id,
                    name=service_data['name']
                ).first()
                
                if existing_service:
                    continue
                    
                service = ServicePackage(
                    name=service_data['name'],
                    description=service_data['description'],
                    price=service_data['price'],
                    duration_hours=service_data['duration_hours'],
                    pilot_profile_id=pilot_profile.id
                )
                db.session.add(service)
                
        print("✓ Creados servicios para todos los pilotos")
        db.session.commit()
        
        # 4. Crear slots de disponibilidad para la próxima semana
        print("Creando disponibilidad para pilotos...")
        today = date.today()
        
        for pilot_key, pilot_profile in created_pilots.items():
            for day_offset in range(1, 8):  # Próximos 7 días
                current_date = today + timedelta(days=day_offset)
                
                # Crear 3 slots por día para cada piloto
                time_slots = [
                    (time(9, 0), time(12, 0)),   # Mañana
                    (time(14, 0), time(17, 0)),  # Tarde  
                    (time(18, 0), time(20, 0))   # Noche
                ]
                
                for start_time, end_time in time_slots:
                    # Verificar si ya existe
                    existing_slot = AvailabilitySlot.query.filter_by(
                        pilot_profile_id=pilot_profile.id,
                        date=current_date,
                        start_time=start_time,
                        end_time=end_time
                    ).first()
                    
                    if existing_slot:
                        continue
                        
                    slot = AvailabilitySlot(
                        pilot_profile_id=pilot_profile.id,
                        date=current_date,
                        start_time=start_time,
                        end_time=end_time,
                        is_available=True
                    )
                    db.session.add(slot)
                    
        print("✓ Creada disponibilidad para todos los pilotos")
        db.session.commit()
        
        print("\n🎉 Datos de prueba creados correctamente!")
        print("\n📋 Usuarios creados:")
        print("=" * 50)
        print("CLIENTES:")
        print("  Email: cliente@madrid.com | Contraseña: 123456")
        print("  Email: cliente@barcelona.com | Contraseña: 123456")
        print("\nPILOTOS:")
        print("  Email: alex@pilotos.com | Contraseña: 123456 (Alex - Madrid)")
        print("  Email: maria@pilotos.com | Contraseña: 123456 (María - Barcelona)")  
        print("  Email: carlos@pilotos.com | Contraseña: 123456 (Carlos - Valencia)")
        print("\n✅ Ya puedes hacer login con cualquiera de estas cuentas")

if __name__ == "__main__":
    create_test_data()