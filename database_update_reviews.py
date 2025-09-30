#!/usr/bin/env python3
"""
Script para actualizar la base de datos con el sistema de reviews
Ejecutar después de actualizar backend.py con las nuevas rutas de reviews
"""

import os
import sys
import bcrypt
from datetime import datetime, date, time, timedelta

# Importar los modelos del backend actualizado
from backend import app, db, User, PilotProfile, ServicePackage, AvailabilitySlot, PortfolioItem, Review, Booking

def update_database_with_reviews():
    with app.app_context():
        print("🔄 Actualizando base de datos con sistema de reviews...")
        
        # Crear todas las tablas (incluye la nueva tabla Review)
        db.create_all()
        print("✅ Tabla de reviews creada")
        
        # Obtener algunas reservas completadas para crear reviews de ejemplo
        completed_bookings = Booking.query.filter_by(status='completed').all()
        
        if len(completed_bookings) == 0:
            print("⚠️  No hay reservas completadas. Creando algunas...")
            # Marcar algunas reservas como completadas
            pending_bookings = Booking.query.filter_by(status='confirmed').limit(3).all()
            for booking in pending_bookings:
                booking.status = 'completed'
            db.session.commit()
            completed_bookings = pending_bookings
        
        # Crear reviews de ejemplo
        sample_reviews = [
            {
                'rating': 5,
                'comment': 'Excelente trabajo! Las fotos de mi boda quedaron espectaculares. Muy profesional y puntual.'
            },
            {
                'rating': 4,
                'comment': 'Muy buen servicio. Las tomas aéreas de mi evento corporativo fueron increíbles. Recomendado.'
            },
            {
                'rating': 5,
                'comment': 'Superó mis expectativas. La calidad de video es profesional y el trato fue excepcional.'
            },
            {
                'rating': 4,
                'comment': 'Gran trabajo en la inspección de mi tejado. Detectó varios problemas que no había visto.'
            },
            {
                'rating': 5,
                'comment': 'Perfecta ejecución del spot publicitario. Creatividad y técnica de primer nivel.'
            },
            {
                'rating': 3,
                'comment': 'Buen trabajo en general, aunque llegó un poco tarde. El resultado final fue satisfactorio.'
            }
        ]
        
        reviews_created = 0
        for i, booking in enumerate(completed_bookings[:len(sample_reviews)]):
            # Verificar que no existe ya una review para esta reserva
            existing_review = Review.query.filter_by(
                client_id=booking.client_id,
                pilot_profile_id=booking.pilot_profile_id,
                booking_id=booking.id
            ).first()
            
            if existing_review:
                print(f"⚠️  Ya existe review para reserva {booking.id}")
                continue
                
            review_data = sample_reviews[i]
            review = Review(
                rating=review_data['rating'],
                comment=review_data['comment'],
                client_id=booking.client_id,
                pilot_profile_id=booking.pilot_profile_id,
                booking_id=booking.id,
                created_at=datetime.utcnow() - timedelta(days=i*2)  # Fechas variadas
            )
            
            db.session.add(review)
            reviews_created += 1
            
        db.session.commit()
        print(f"✅ Creadas {reviews_created} reviews de ejemplo")
        
        # Mostrar estadísticas de reviews por piloto
        print("\n📊 Estadísticas de Reviews:")
        print("=" * 50)
        
        pilots = PilotProfile.query.all()
        for pilot in pilots:
            reviews = Review.query.filter_by(pilot_profile_id=pilot.id).all()
            if reviews:
                avg_rating = sum(r.rating for r in reviews) / len(reviews)
                print(f"{pilot.name}:")
                print(f"  - Total reviews: {len(reviews)}")
                print(f"  - Calificación promedio: {avg_rating:.1f}/5")
                print(f"  - Distribución: {[r.rating for r in reviews]}")
            else:
                print(f"{pilot.name}: Sin reviews")
            print()
        
        print("🎉 Sistema de reviews configurado correctamente!")
        print("\n💡 Para probar el sistema:")
        print("1. Inicia sesión como cliente")
        print("2. Haz una reserva con un piloto")
        print("3. El piloto debe marcar la reserva como 'Completada'")
        print("4. Entonces podrás escribir una reseña")
        print("\n📧 Cuentas de prueba disponibles:")
        print("Cliente: cliente@madrid.com | Contraseña: 123456")
        print("Pilotos: alex@pilotos.com, maria@pilotos.com, carlos@pilotos.com | Contraseña: 123456")

def show_review_statistics():
    """Función auxiliar para mostrar estadísticas de reviews"""
    with app.app_context():
        print("\n📈 ESTADÍSTICAS ACTUALES DE REVIEWS")
        print("=" * 60)
        
        total_reviews = Review.query.count()
        print(f"Total de reviews en el sistema: {total_reviews}")
        
        if total_reviews > 0:
            avg_global = db.session.query(db.func.avg(Review.rating)).scalar()
            print(f"Calificación promedio global: {avg_global:.2f}/5")
            
            # Distribución por calificación
            print("\nDistribución de calificaciones:")
            for rating in range(5, 0, -1):
                count = Review.query.filter_by(rating=rating).count()
                percentage = (count / total_reviews * 100) if total_reviews > 0 else 0
                bar = "█" * int(percentage / 5)
                print(f"{rating}⭐: {count:2d} ({percentage:5.1f}%) {bar}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stats":
        show_review_statistics()
    else:
        update_database_with_reviews()