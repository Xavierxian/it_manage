import os
from dotenv import load_dotenv
from flask import Flask
from flask_caching import Cache
from flask_login import LoginManager
from dbutils.pooled_db import PooledDB
import pymysql

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv('SECRET_KEY')
    return app

def configure_cache(app):
    cache_config = {
        'CACHE_TYPE': 'redis',
        'CACHE_REDIS_HOST': os.getenv('REDIS_HOST', 'localhost'),
        'CACHE_REDIS_PORT': int(os.getenv('REDIS_PORT', 6379)),
        'CACHE_REDIS_PASSWORD': os.getenv('REDIS_PASSWORD'),
        'CACHE_REDIS_DB': int(os.getenv('REDIS_DB', 0)),
        'CACHE_DEFAULT_TIMEOUT': 300,
        'CACHE_KEY_PREFIX': 'it_manage_'
    }
    return Cache(app, config=cache_config)

cache_config = {
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_HOST': os.getenv('REDIS_HOST', 'localhost'),
    'CACHE_REDIS_PORT': int(os.getenv('REDIS_PORT', 6379)),
    'CACHE_REDIS_PASSWORD': os.getenv('REDIS_PASSWORD'),
    'CACHE_REDIS_DB': int(os.getenv('REDIS_DB', 0)),
    'CACHE_DEFAULT_TIMEOUT': 300,
    'CACHE_KEY_PREFIX': 'it_manage_'
}

cache = None

def get_db_config():
    return {
        'host': os.getenv('MYSQL_HOST'),
        'user': os.getenv('MYSQL_USER'),
        'password': os.getenv('MYSQL_PASSWORD'),
        'port': int(os.getenv('MYSQL_PORT')),
        'database': os.getenv('MYSQL_DATABASE')
    }

def create_db_pool(db_config):
    return PooledDB(
        creator=pymysql,
        maxconnections=20,
        mincached=2,
        maxcached=5,
        maxshared=3,
        blocking=True,
        maxusage=None,
        setsession=[],
        ping=0,
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password'],
        port=db_config['port'],
        database=db_config['database'],
        cursorclass=pymysql.cursors.DictCursor,
        charset='utf8mb4'
    )

def configure_login_manager(app):
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    return login_manager
