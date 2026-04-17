import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

db_pool = None

def init_db_pool(pool):
    global db_pool
    db_pool = pool

def get_db_connection():
    if db_pool is None:
        print("错误: 数据库连接池未初始化")
        return None
    try:
        connection = db_pool.connection()
        return connection
    except Exception as e:
        print(f"获取数据库连接失败: {e}")
        return None

def get_k8s_db_connection():
    try:
        k8s_db_config = {
            'host': os.getenv('K8S_MYSQL_HOST', 'localhost'),
            'port': int(os.getenv('K8S_MYSQL_PORT', 3306)),
            'user': os.getenv('K8S_MYSQL_USER', 'root'),
            'password': os.getenv('K8S_MYSQL_PASSWORD', ''),
            'database': os.getenv('K8S_MYSQL_DATABASE', 'it_asset_management'),
            'charset': 'utf8mb4'
        }
        if not k8s_db_config['password']:
            raise ValueError("K8S_MYSQL_PASSWORD environment variable is required")
        conn = pymysql.connect(**k8s_db_config)
        return conn
    except Exception as e:
        print(f"K8S数据库连接失败: {e}")
        return None
