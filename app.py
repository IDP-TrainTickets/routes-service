from typing import List, Tuple
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import jwt

app = Flask(__name__)

# Testing values
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://admin:password123@db:5432/db'
app.config['SECRET_KEY'] = 'secret-key-test-123'

db = SQLAlchemy(app)

def get_requesting_user() -> Tuple[str, str] | None:
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return None

    token = auth_header.removeprefix('Bearer ').strip()
    claims = jwt.decode(token, options={'verify_signature': False})
    return claims['user_id'], claims['user_type']

def transform_price(price: int, user_type: str) -> int:
    if user_type == "Student":
        return int(price * 0.9)
    return price


class User(db.Model):
    __tablename__ = "app_user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    user_type = db.Column(db.String(20), default='Adult')
    reservations = db.relationship("Reservation", back_populates="user")

class Route(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_station = db.Column(db.String(255), nullable=False)
    to_station = db.Column(db.String(255), nullable=False)
    leave_at = db.Column(db.Time, nullable=False)
    arrive_by = db.Column(db.Time, nullable=False)
    price = db.Column(db.Integer, nullable=False)

    trips = db.relationship("Trip", back_populates="route")


class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(
        db.Integer,
        db.ForeignKey("route.id"),
        nullable=False,
    )
    trip_day = db.Column(db.Date, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    route = db.relationship("Route", back_populates="trips")
    reservations = db.relationship("Reservation", back_populates="trip")


class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(
        db.Integer,
        db.ForeignKey("trip.id"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    trip = db.relationship("Trip", back_populates="reservations")
    user = db.relationship("User", back_populates="reservations")


# example: /routes?from_station=Bucharest"
@app.get('/routes')
def list_routes():
    user = get_requesting_user()
    if not user:
        return {"error": "Could not identify requesting user"}, 403
    
    _, user_type = user
    
    from_station = request.args.get("from_station")
    to_station = request.args.get("to_station")
    day_str = request.args.get("day")
    query = Route.query
    
    if from_station and to_station and day_str:
        try:
            target_day = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400

        trips = Trip.query.join(Route).filter(
            Route.from_station == from_station,
            Route.to_station == to_station,
            Trip.trip_day == target_day
        ).all()

        data = []
        for trip in trips:
            available_seats = trip.capacity - len(trip.reservations)
            dummy_date = datetime.today()
            leave_dt = datetime.combine(dummy_date, trip.route.leave_at)
            arrive_dt = datetime.combine(dummy_date, trip.route.arrive_by)
            if arrive_dt < leave_dt:
                from datetime import timedelta
                arrive_dt += timedelta(days=1)
            duration_minutes = int((arrive_dt - leave_dt).total_seconds() / 60)

            data.append({
                "trip_id": trip.id,
                "from_station": trip.route.from_station,
                "to_station": trip.route.to_station,
                "leave_at": trip.route.leave_at.strftime("%H:%M:%S"),
                "arrive_by": trip.route.arrive_by.strftime("%H:%M:%S"),
                "duration_minutes": duration_minutes,
                "available_seats": available_seats,
                "price": transform_price(trip.route.price, user_type),
            })
        return jsonify(data), 200

    if from_station is not None:
        query = query.filter(Route.from_station == from_station)

    routes = query.all()

    data = [{
        "from_station": route.from_station,
        "to_station": route.to_station,
        "leave_at": route.leave_at.strftime("%H:%M:%S"),
        "arrive_by": route.arrive_by.strftime("%H:%M:%S"),
        "price": transform_price(route.price, user_type),
    }
    for route in routes]

    return jsonify(data), 200

@app.get('/reservations')
def list_reservations():
    user = get_requesting_user()
    if not user:
        return {"error": "Could not identify requesting user"}, 403
    
    user_id, _ = user
 
    query = Reservation.query
    query = query.filter(Reservation.user_id == user_id)
    reservations: List[Reservation]= query.all()

    data = [{
        "from_station": reservation.trip.route.from_station,
        "to_station": reservation.trip.route.to_station,
        "leave_at": reservation.trip.route.leave_at.strftime("%H:%M:%S"),
        "arrive_by": reservation.trip.route.arrive_by.strftime("%H:%M:%S"),
        "day": reservation.trip.trip_day
    }
    for reservation in reservations]

    return jsonify(data), 200
    
@app.post('/reservations')
def create_reservation():
    data = request.get_json()
    trip_id = data.get('trip_id')
    user_id = data.get('user_id')

    trip = Trip.query.get(trip_id)
    if not trip:
        return {"error": "Trip not found"}, 404
    
    if len(trip.reservations) >= trip.capacity:
        return {"error": "No more seats available"}, 400

    new_res = Reservation(trip_id=trip_id, user_id=user_id)
    db.session.add(new_res)
    db.session.commit()

    return {"message": "Success", "reservation_id": new_res.id}, 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
