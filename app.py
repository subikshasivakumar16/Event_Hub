from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///college_events.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="student")


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    venue = db.Column(db.String(150), nullable=False)
    event_date = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id"), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    certificate_status = db.Column(db.String(30), default="Pending")

    user = db.relationship("User", backref="registrations")
    event = db.relationship("Event", backref="registrations")

    __table_args__ = (
        db.UniqueConstraint("user_id", "event_id", name="unique_registration"),
    )


@app.context_processor
def inject_user():
    user = None
    if "user_id" in session:
        user = db.session.get(User, session["user_id"])
    return {"current_user": user}


@app.route("/")
def index():
    category = request.args.get("category", "")
    query = request.args.get("q", "")

    events = Event.query.order_by(Event.event_date.asc())

    if category:
        events = events.filter_by(category=category)

    if query:
        events = events.filter(
            db.or_(
                Event.title.ilike(f"%{query}%"),
                Event.description.ilike(f"%{query}%"),
                Event.venue.ilike(f"%{query}%")
            )
        )

    return render_template("index.html", events=events.all())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))

        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            role="student",
        )
        db.session.add(user)
        db.session.commit()
        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = db.session.get(User, session["user_id"])
    registrations = Registration.query.filter_by(user_id=user.id).all()

    return render_template(
        "dashboard.html",
        user=user,
        registrations=registrations
    )


@app.route("/events/<int:event_id>")
def event_details(event_id):
    event = db.get_or_404(Event, event_id)
    registered = False

    if "user_id" in session:
        registered = Registration.query.filter_by(
            user_id=session["user_id"], event_id=event.id
        ).first() is not None

    return render_template(
        "event_details.html",
        event=event,
        registered=registered
    )


@app.route("/events/<int:event_id>/register", methods=["POST"])
def register_event(event_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    event = db.get_or_404(Event, event_id)

    existing = Registration.query.filter_by(
        user_id=session["user_id"], event_id=event.id
    ).first()

    if existing:
        flash("You are already registered for this event.", "warning")
        return redirect(url_for("event_details", event_id=event.id))

    count = Registration.query.filter_by(event_id=event.id).count()

    if count >= event.capacity:
        flash("This event is full.", "danger")
        return redirect(url_for("event_details", event_id=event.id))

    registration = Registration(
        user_id=session["user_id"],
        event_id=event.id
    )
    db.session.add(registration)
    db.session.commit()

    flash("Event registration successful.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin")
def admin():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = db.session.get(User, session["user_id"])

    if user.role != "admin":
        flash("Admin access required.", "danger")
        return redirect(url_for("dashboard"))

    events = Event.query.order_by(Event.event_date.desc()).all()
    registrations = Registration.query.order_by(
        Registration.registered_at.desc()
    ).all()

    return render_template(
        "admin.html",
        events=events,
        registrations=registrations
    )


@app.route("/admin/events/new", methods=["GET", "POST"])
def create_event():
    if not is_admin():
        return redirect(url_for("login"))

    if request.method == "POST":
        event = Event(
            title=request.form["title"],
            description=request.form["description"],
            category=request.form["category"],
            venue=request.form["venue"],
            event_date=datetime.strptime(
                request.form["event_date"], "%Y-%m-%dT%H:%M"
            ),
            capacity=int(request.form["capacity"])
        )

        db.session.add(event)
        db.session.commit()
        flash("Event created successfully.", "success")
        return redirect(url_for("admin"))

    return render_template("create_event.html")


@app.route("/admin/events/<int:event_id>/delete", methods=["POST"])
def delete_event(event_id):
    if not is_admin():
        return redirect(url_for("login"))

    event = db.get_or_404(Event, event_id)

    Registration.query.filter_by(event_id=event.id).delete()
    db.session.delete(event)
    db.session.commit()

    flash("Event deleted.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/registrations/<int:registration_id>/certificate", methods=["POST"])
def update_certificate(registration_id):
    if not is_admin():
        return redirect(url_for("login"))

    registration = db.get_or_404(Registration, registration_id)
    registration.certificate_status = request.form["status"]
    db.session.commit()

    flash("Certificate status updated.", "success")
    return redirect(url_for("admin"))


def is_admin():
    if "user_id" not in session:
        return False

    user = db.session.get(User, session["user_id"])
    return user and user.role == "admin"


@app.route("/api/events")
def api_events():
    events = Event.query.order_by(Event.event_date.asc()).all()

    return jsonify([
        {
            "id": event.id,
            "title": event.title,
            "description": event.description,
            "category": event.category,
            "venue": event.venue,
            "event_date": event.event_date.isoformat(),
            "capacity": event.capacity,
            "registered": len(event.registrations)
        }
        for event in events
    ])


@app.route("/api/health")
def health():
    return jsonify({
        "status": "UP",
        "service": "College Event Hub"
    })


with app.app_context():
    db.create_all()

    if not User.query.filter_by(email="admin@college.com").first():
        admin_user = User(
            name="College Admin",
            email="admin@college.com",
            password=generate_password_hash("admin123"),
            role="admin"
        )
        db.session.add(admin_user)

    if Event.query.count() == 0:
        sample_events = [
            Event(
                title="AI & Machine Learning Workshop",
                description="Hands-on workshop covering AI, ML and real-world applications.",
                category="Technical",
                venue="AI Lab",
                event_date=datetime(2026, 10, 20, 10, 0),
                capacity=100
            ),
            Event(
                title="Web Development Hackathon",
                description="Build an innovative web application within 24 hours.",
                category="Hackathon",
                venue="Innovation Centre",
                event_date=datetime(2026, 10, 25, 9, 0),
                capacity=80
            ),
            Event(
                title="Cultural Fest 2026",
                description="Music, dance, drama and cultural performances by students.",
                category="Cultural",
                venue="College Auditorium",
                event_date=datetime(2026, 11, 5, 16, 0),
                capacity=500
            )
        ]
        db.session.add_all(sample_events)

    db.session.commit()


if __name__ == "__main__":
    app.run(debug=True)
