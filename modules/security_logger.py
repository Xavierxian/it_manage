import logging
import os
import shutil
from datetime import datetime, timedelta
from flask import request, session
from functools import wraps

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
BACKUP_DIR = os.path.join(LOG_DIR, 'backup')
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

SECURITY_LOG_FILE = os.path.join(LOG_DIR, 'security.log')

LOG_RETENTION_DAYS = 180
LOG_MAX_SIZE = 50 * 1024 * 1024
LOG_BACKUP_COUNT = 10

security_logger = logging.getLogger('security')
security_logger.setLevel(logging.INFO)

from logging.handlers import RotatingFileHandler

file_handler = RotatingFileHandler(
    SECURITY_LOG_FILE,
    maxBytes=LOG_MAX_SIZE,
    backupCount=LOG_BACKUP_COUNT,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

if not security_logger.handlers:
    security_logger.addHandler(file_handler)

def log_security_event(event_type, details, user_id=None, username=None, success=True):
    """记录安全事件"""
    ip_address = request.remote_addr if request else 'N/A'
    user_agent = request.headers.get('User-Agent', 'N/A') if request else 'N/A'
    
    user_info = username if username else f"ID: {user_id or 'N/A'}"
    log_message = f"[{event_type}] IP: {ip_address}, 操作人: {user_info}, Success: {success}, Details: {details}, User-Agent: {user_agent}"
    
    if success:
        security_logger.info(log_message)
    else:
        security_logger.warning(log_message)

def log_login_attempt(username, success, user_id=None):
    """记录登录尝试"""
    event_type = "LOGIN_SUCCESS" if success else "LOGIN_FAILURE"
    log_security_event(event_type, f"Username: {username}", user_id, username, success)

def log_user_action(action, details, user_id=None, username=None):
    """记录用户操作"""
    log_security_event(f"USER_ACTION_{action}", details, user_id, username, True)

def log_permission_denied(resource, user_id=None):
    """记录权限拒绝"""
    log_security_event("PERMISSION_DENIED", f"Resource: {resource}", user_id, False)

def log_data_modification(table, operation, record_id, user_id=None):
    """记录数据修改"""
    log_security_event("DATA_MODIFICATION", f"Table: {table}, Operation: {operation}, Record_ID: {record_id}", user_id, True)

def log_security_violation(violation_type, details, user_id=None):
    """记录安全违规"""
    log_security_event(f"SECURITY_VIOLATION_{violation_type}", details, user_id, False)

def audit_log(action):
    """审计日志装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = getattr(session, 'user_id', None) if hasattr(session, 'user_id') else None
            
            try:
                result = f(*args, **kwargs)
                
                if hasattr(request, 'method') and request.method in ['POST', 'PUT', 'DELETE']:
                    endpoint = request.endpoint or 'unknown'
                    log_user_action(action, f"Endpoint: {endpoint}", user_id)
                
                return result
            except Exception as e:
                log_security_event("ERROR", f"Action: {action}, Error: {str(e)}", user_id, False)
                raise
        
        return decorated_function
    return decorator

def cleanup_old_logs():
    """清理超过保留期限的日志文件"""
    try:
        cutoff_date = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
        
        for filename in os.listdir(LOG_DIR):
            if filename.startswith('security.log') or filename.startswith('security.log.'):
                filepath = os.path.join(LOG_DIR, filename)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                
                if file_mtime < cutoff_date:
                    backup_filepath = os.path.join(BACKUP_DIR, filename)
                    shutil.move(filepath, backup_filepath)
                    print(f"已将旧日志移动到备份目录: {filename}")
        
        for filename in os.listdir(BACKUP_DIR):
            filepath = os.path.join(BACKUP_DIR, filename)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            if file_mtime < cutoff_date:
                os.remove(filepath)
                print(f"已删除过期的备份日志: {filename}")
                
    except Exception as e:
        print(f"清理旧日志时出错: {e}")

def backup_logs():
    """备份日志文件到备份目录"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        for filename in os.listdir(LOG_DIR):
            if filename.startswith('security.log'):
                source = os.path.join(LOG_DIR, filename)
                if os.path.isfile(source):
                    backup_name = f"{filename}_{timestamp}"
                    destination = os.path.join(BACKUP_DIR, backup_name)
                    shutil.copy2(source, destination)
                    print(f"已备份日志文件: {filename} -> {backup_name}")
                    
    except Exception as e:
        print(f"备份日志时出错: {e}")

def init_log_management():
    """初始化日志管理"""
    cleanup_old_logs()
