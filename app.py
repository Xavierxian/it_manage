from flask import Flask, render_template, jsonify, send_from_directory, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
import os
import pymysql
from dotenv import load_dotenv
from dbutils.pooled_db import PooledDB
from flask_caching import Cache

from modules.cache_manager import cache_manager
from modules import config
from modules.database import get_db_connection, get_k8s_db_connection, init_db_pool
from modules.ssl_config import configure_ssl
from modules.security_logger import init_log_management

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# 增强 CSRF 配置
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # CSRF token 有效期（秒）
app.config['WTF_CSRF_SSL_STRICT'] = True  # 在 HTTPS 下严格验证

csrf = CSRFProtect(app)

# 配置 CORS
cors = CORS(app, resources={
    r"/api/*": {
        "origins": [],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-CSRFToken"],
        "supports_credentials": True
    }
})

cache_instance = Cache(app, config=config.cache_config)
config.cache = cache_instance

from modules.auth import auth_bp, User, load_user, permission_required, admin_required
from modules.port_mapping import port_bp as port_mapping_bp
from modules.domain_mapping import domain_bp as domain_mapping_bp
from modules.virtual_machines import virtual_machines_bp, clear_password_cache
from modules.physical_machines import physical_machines_bp
from modules.namespaces import namespaces_bp
from modules.dashboard import dashboard_bp
from modules.host_monitoring import host_monitoring_bp
from modules.k8s_monitoring import k8s_monitoring_bp
from modules.cron_monitoring import cron_monitoring_bp
from modules.bsecp import bsecp_bp
from modules.jumpserver import jumpserver_bp
from modules.qualification_management import qualification_management_bp

db_config = {
    'host': os.getenv('MYSQL_HOST'),
    'user': os.getenv('MYSQL_USER'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'port': int(os.getenv('MYSQL_PORT')),
    'database': os.getenv('MYSQL_DATABASE')
}

db_pool = PooledDB(
    creator=pymysql,
    maxconnections=20,
    mincached=2,
    maxcached=5,
    maxshared=3,
    blocking=True,
    maxusage=None,
    setsession=['SET time_zone = \'+08:00\''],
    ping=0,
    host=db_config['host'],
    user=db_config['user'],
    password=db_config['password'],
    port=db_config['port'],
    database=db_config['database'],
    cursorclass=pymysql.cursors.DictCursor,
    charset='utf8mb4',
    use_unicode=True
)

init_db_pool(db_pool)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.user_loader(load_user)

app.register_blueprint(auth_bp)
app.register_blueprint(port_mapping_bp)
app.register_blueprint(domain_mapping_bp)
app.register_blueprint(virtual_machines_bp)
app.register_blueprint(physical_machines_bp)
app.register_blueprint(namespaces_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(host_monitoring_bp)
app.register_blueprint(k8s_monitoring_bp)
app.register_blueprint(bsecp_bp)
app.register_blueprint(jumpserver_bp)
app.register_blueprint(cron_monitoring_bp)
app.register_blueprint(qualification_management_bp)

@app.before_request
def check_referrer():
    if request.path.startswith('/static/') or request.path == '/login':
        return
    
    origin = request.headers.get('Origin')
    if origin:
        pass
    
    referer = request.headers.get('Referer')
    if referer:
        pass

init_log_management()

@app.errorhandler(403)
def forbidden(error):
    return render_template('403.html'), 403

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
        'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.after_request
def set_security_headers(response):
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;"
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response
if __name__ == '__main__':
    clear_password_cache()

    ssl_enabled = os.getenv('SSL_ENABLED', 'false').lower() == 'true'

    if ssl_enabled:
        configure_ssl(app)
        ssl_context = app.config.get('SSL_CONTEXT')
        app.run(host='0.0.0.0', port=8888, ssl_context=ssl_context, debug=False)
    else:
        print("警告: 当前使用HTTP协议，建议在生产环境中启用HTTPS")
        app.run(host='0.0.0.0', port=8888, debug=False)
