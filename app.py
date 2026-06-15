from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from solver import solve_module1, solve_module3
import traceback
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'smart-geosynthetic-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth'

# ─── User Model ───
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── Create DB and Admin Account ───
with app.app_context():
    db.create_all()
    admin = User.query.filter_by(email='admin@geosmart.com').first()
    if not admin:
        hashed_pw = bcrypt.generate_password_hash('admin123').decode('utf-8')
        admin = User(username='Admin', email='admin@geosmart.com', password=hashed_pw, is_admin=True)
        db.session.add(admin)
        db.session.commit()
        print("Admin account created: admin@geosmart.com / admin123")

# ─── Auth Page (Login + Register) ───
@app.route('/auth')
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip()
    password = data.get('password', '')

    user = User.query.filter_by(email=email).first()
    if user and bcrypt.check_password_hash(user.password, password):
        login_user(user)
        return jsonify({'success': True, 'is_admin': user.is_admin})
    else:
        return jsonify({'success': False, 'message': 'Email ou mot de passe incorrect.'})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'success': False, 'message': 'Veuillez remplir tous les champs.'})

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Cet email est déjà utilisé.'})

    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Ce nom d\'utilisateur est déjà pris.'})

    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = User(username=username, email=email, password=hashed_pw, is_admin=False)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return jsonify({'success': True})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth'))

# ─── Main App (Protected) ───
@app.route('/')
@login_required
def index():
    return render_template('index.html')

# ─── Admin Panel (Protected) ───
@app.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    users = User.query.all()
    return render_template('admin.html', users=users)

@app.route('/admin/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Accès refusé.'})
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Utilisateur introuvable.'})
    if user.is_admin:
        return jsonify({'success': False, 'message': 'Impossible de supprimer le compte Admin.'})
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})

# ─── API Endpoints ───
@app.route('/api/module1', methods=['POST'])
@login_required
def module1_api():
    try:
        data = request.json
        C = float(data.get('C', 0))
        phi = float(data.get('phi', 0))
        gamma = float(data.get('gamma', 0))
        B = float(data.get('B', 0))
        L = float(data.get('L', 0))
        Df = float(data.get('Df', 0))
        F = float(data.get('F', 0))
        FS = float(data.get('FS', 3.0))

        result = solve_module1(C, phi, gamma, B, L, Df, F, FS)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/module3', methods=['POST'])
@login_required
def module3_api():
    try:
        data = request.json
        grs_data = data.get('grs_data')
        EA = float(data.get('EA', 0))
        UZ_ALLOW = float(data.get('UZ_ALLOW', 0))

        result = solve_module3(grs_data, EA, UZ_ALLOW)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
