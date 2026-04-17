from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import UserMixin, login_user, login_required, logout_user, current_user
from functools import wraps
import json
import bcrypt
import time
import re
from .database import get_db_connection
from .security_logger import log_login_attempt, log_user_action, log_permission_denied, log_data_modification
from .crypto_utils import password_crypto

auth_bp = Blueprint('auth', __name__)

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_TIME = 600

login_attempts = {}

def get_username_by_id(user_id):
    """根据用户ID获取用户名"""
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
        connection.close()
        return user['username'] if user else '未知用户'
    except:
        return '未知用户'

def validate_password_complexity(password):
    if len(password) < 8:
        return False, "密码长度至少需要8个字符"
    
    if not re.search(r'[A-Z]', password):
        return False, "密码必须包含至少一个大写字母"
    
    if not re.search(r'[a-z]', password):
        return False, "密码必须包含至少一个小写字母"
    
    if not re.search(r'\d', password):
        return False, "密码必须包含至少一个数字"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "密码必须包含至少一个特殊字符"
    
    return True, "密码符合要求"

class User(UserMixin):
    def __init__(self, id):
        self.id = id

def load_user(user_id):
    return User(user_id)

def permission_required(permission_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = current_user.id
            
            try:
                connection = get_db_connection()
                with connection.cursor() as cursor:
                    cursor.execute("SELECT role, permissions, is_active FROM users WHERE id = %s", (user_id,))
                    user = cursor.fetchone()
                    
                    if not user:
                        connection.close()
                        return jsonify({'success': False, 'message': '用户不存在'}), 404
                    
                    if not user['is_active']:
                        connection.close()
                        return jsonify({'success': False, 'message': '账户已被禁用'}), 403
                    
                    if user['role'] == 'admin':
                        connection.close()
                        return f(*args, **kwargs)
                    
                    try:
                        user_permissions = json.loads(user['permissions'])
                        if not isinstance(user_permissions, list):
                            user_permissions = []
                    except (json.JSONDecodeError, TypeError):
                        user_permissions = []
                    
                    if permission_name in user_permissions:
                        connection.close()
                        return f(*args, **kwargs)
                    else:
                        connection.close()
                        log_permission_denied(permission_name, user_id)
                        return render_template('403.html'), 403
                        
            except Exception as e:
                print(f"权限验证时出错: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({
                    'success': False, 
                    'message': '权限验证失败'
                }), 500
                
        return decorated_function
    return decorator

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = current_user.id
        
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT role, is_active FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                
                if not user:
                    connection.close()
                    return jsonify({'success': False, 'message': '用户不存在'}), 404
                
                if not user['is_active']:
                    connection.close()
                    return jsonify({'success': False, 'message': '账户已被禁用'}), 403
                
                if user['role'] != 'admin':
                    connection.close()
                    return jsonify({'success': False, 'message': '需要管理员权限'}), 403
                
                connection.close()
                return f(*args, **kwargs)
                
        except Exception as e:
            print(f"管理员权限验证时出错: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                'success': False, 
                'message': '权限验证失败'
            }), 500
            
    return decorated_function

def verify_password(stored_password_hash, provided_password):
    return bcrypt.checkpw(provided_password.encode('utf-8'), stored_password_hash.encode('utf-8'))

@auth_bp.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # 支持表单数据和 JSON 数据
        if request.is_json:
            data = request.get_json()
            username = data.get('username')
            
            # 检查是否使用加密
            if data.get('use_encryption') and data.get('encrypted_password'):
                try:
                    encrypted_password = data.get('encrypted_password')
                    password = password_crypto.decrypt_password(encrypted_password)
                except Exception as e:
                    print(f"密码解密失败: {e}")
                    return jsonify({'success': False, 'message': '密码解密失败'}), 400
            else:
                password = data.get('password')
        else:
            username = request.form['username']
            password = request.form['password']
        
        if not username or not username.strip():
            flash('请输入用户名')
            return render_template('login.html')
            
        if not password:
            flash('请输入密码')
            return render_template('login.html')
            
        username = username.strip()
        
        if username in login_attempts:
            attempts, lock_time = login_attempts[username]
            if attempts >= MAX_LOGIN_ATTEMPTS and time.time() - lock_time < LOCKOUT_TIME:
                remaining_time = int((LOCKOUT_TIME - (time.time() - lock_time)) / 60)
                flash(f'登录尝试次数过多，账户已锁定 {remaining_time} 分钟')
                return render_template('login.html')
            elif time.time() - lock_time >= LOCKOUT_TIME:
                del login_attempts[username]
        
        try:
            connection = get_db_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, username, password, role, is_active FROM users WHERE username = %s", (username,))
                user_record = cursor.fetchone()
                
                if not user_record:
                    if username not in login_attempts:
                        login_attempts[username] = [1, time.time()]
                    else:
                        login_attempts[username][0] += 1
                        login_attempts[username][1] = time.time()
                    
                    log_login_attempt(username, False)
                    
                    if login_attempts[username][0] >= MAX_LOGIN_ATTEMPTS:
                        flash(f'登录失败次数过多，账户已锁定 {int(LOCKOUT_TIME / 60)} 分钟')
                    else:
                        remaining_attempts = MAX_LOGIN_ATTEMPTS - login_attempts[username][0]
                        flash(f'用户名或密码错误，剩余尝试次数：{remaining_attempts}')
                    connection.close()
                    return render_template('login.html')
                
                if not user_record['is_active']:
                    flash('账户已被禁用，请联系管理员')
                    connection.close()
                    return render_template('login.html')
                
                if verify_password(user_record['password'], password):
                    user = User(user_record['id'])
                    login_user(user)
                    
                    if username in login_attempts:
                        del login_attempts[username]
                    
                    cursor.execute("""
                        UPDATE users 
                        SET last_login = NOW() 
                        WHERE id = %s
                        """, (user_record['id'],))
                    connection.commit()
                    
                    log_login_attempt(username, True, user_record['id'])
                    
                    return redirect(url_for('dashboard.dashboard'))
                else:
                    if username not in login_attempts:
                        login_attempts[username] = [1, time.time()]
                    else:
                        login_attempts[username][0] += 1
                        login_attempts[username][1] = time.time()
                    
                    log_login_attempt(username, False)
                    
                    if login_attempts[username][0] >= MAX_LOGIN_ATTEMPTS:
                        flash(f'登录失败次数过多，账户已锁定 {int(LOCKOUT_TIME / 60)} 分钟')
                    else:
                        remaining_attempts = MAX_LOGIN_ATTEMPTS - login_attempts[username][0]
                        flash(f'用户名或密码错误，剩余尝试次数：{remaining_attempts}')
                    
            connection.close()
            
        except Exception as e:
            print(f"登录验证时出错: {e}")
            import traceback
            traceback.print_exc()
            flash('登录过程中发生错误，请稍后重试')
    
    return render_template('login.html')

@auth_bp.route('/api/public-key')
def get_public_key():
    """获取RSA公钥用于客户端密码加密"""
    public_key = password_crypto.get_public_key_pem()
    return jsonify({
        'public_key': public_key,
        'success': True
    })

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/user_management')
@login_required
@permission_required('user_management')
def user_management():
    return render_template('user_management.html')

@auth_bp.route('/api/users')
@login_required
def get_users():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, username, email, role, permissions, is_active, created_at, last_login FROM users ORDER BY id")
            users = cursor.fetchall()
        connection.close()
        
        return jsonify({
            'success': True,
            'users': users
        })
    except Exception as e:
        print(f"获取用户列表时出错: {e}")
        return jsonify({
            'success': False,
            'message': str(e),
            'users': []
        })

@auth_bp.route('/api/users', methods=['POST'])
@login_required
@admin_required
def add_user():
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        encrypted_password = data.get('encrypted_password')
        use_encryption = data.get('use_encryption', False)
        role = data.get('role', 'user')
        
        if use_encryption and encrypted_password:
            password = password_crypto.decrypt_password(encrypted_password)
        
        is_valid, message = validate_password_complexity(password)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': message
            })
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                connection.close()
                return jsonify({
                    'success': False,
                    'message': '用户名已存在'
                })
            
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            if role == 'admin':
                permissions = '["dashboard", "user_management", "auth_query", "bsecp_modules", "domain_mapping", "port_mapping", "physical_machines", "virtual_machines", "namespaces", "qualification_management", "bastion_management", "host_monitoring", "k8s_monitoring", "cron_monitoring"]'
            else:
                permissions = '["dashboard"]'
            
            cursor.execute("""
                INSERT INTO users (username, email, password, role, permissions) 
                VALUES (%s, %s, %s, %s, %s)
            """, (username, email, hashed_password, role, permissions))
            connection.commit()
            
            new_user_id = cursor.lastrowid
        connection.close()
        
        operator_username = get_username_by_id(current_user.id)
        log_user_action('ADD_USER', f'添加用户: {username}, 邮箱: {email}, 角色: {role}, 操作人: {operator_username}', current_user.id, operator_username)
        
        return jsonify({
            'success': True,
            'message': '用户添加成功'
        })
    except Exception as e:
        print(f"添加用户时出错: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@auth_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    try:
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        role = data.get('role', 'user')
        is_active = int(data.get('is_active', 1))
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username = %s AND id != %s", (username, user_id))
            existing_user = cursor.fetchone()
            
            if existing_user:
                connection.close()
                return jsonify({
                    'success': False,
                    'message': '用户名已存在'
                })
            
            if role == 'admin':
                permissions = '["dashboard", "user_management", "auth_query", "bsecp_modules", "domain_mapping", "port_mapping", "physical_machines", "virtual_machines", "namespaces", "qualification_management", "bastion_management", "host_monitoring", "k8s_monitoring", "cron_monitoring"]'
            else:
                permissions = '["dashboard"]'
            
            cursor.execute("""
                UPDATE users 
                SET username=%s, email=%s, role=%s, is_active=%s, permissions=%s 
                WHERE id=%s
            """, (username, email, role, is_active, permissions, user_id))
            connection.commit()
            
        connection.close()
        
        operator_username = get_username_by_id(current_user.id)
        log_user_action('UPDATE_USER', f'更新用户信息: ID={user_id}, 用户名: {username}, 邮箱: {email}, 角色: {role}, 状态: {"启用" if is_active else "禁用"}, 操作人: {operator_username}', current_user.id, operator_username)
        
        return jsonify({
            'success': True,
            'message': '用户信息更新成功'
        })
    except Exception as e:
        print(f"更新用户信息时出错: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@auth_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    try:
        if user_id == int(current_user.id):
            return jsonify({
                'success': False,
                'message': '不能删除当前登录用户'
            })
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT username FROM users WHERE id=%s", (user_id,))
            deleted_user = cursor.fetchone()
            
            if not deleted_user:
                connection.close()
                return jsonify({
                    'success': False,
                    'message': '用户不存在'
                })
            
            deleted_username = deleted_user['username']
            cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
            connection.commit()
            
        connection.close()
        
        operator_username = get_username_by_id(current_user.id)
        log_user_action('DELETE_USER', f'删除用户: {deleted_username}, 操作人: {operator_username}', current_user.id, operator_username)
        
        return jsonify({
            'success': True,
            'message': '用户删除成功'
        })
    except Exception as e:
        print(f"删除用户时出错: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@auth_bp.route('/api/users/<int:user_id>/password', methods=['PUT'])
@login_required
def change_user_password(user_id):
    try:
        data = request.get_json()
        password = data.get('password')
        encrypted_password = data.get('encrypted_password')
        use_encryption = data.get('use_encryption', False)
        
        if use_encryption and encrypted_password:
            password = password_crypto.decrypt_password(encrypted_password)
        
        is_valid, message = validate_password_complexity(password)
        if not is_valid:
            return jsonify({
                'success': False,
                'message': message
            })
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT username FROM users WHERE id=%s", (user_id,))
            user = cursor.fetchone()
            
            if not user:
                connection.close()
                return jsonify({
                    'success': False,
                    'message': '用户不存在'
                })
            
            username = user['username']
            cursor.execute("""
                UPDATE users 
                SET password=%s 
                WHERE id=%s
            """, (hashed_password, user_id))
            connection.commit()
            
        connection.close()
        
        operator_username = get_username_by_id(current_user.id)
        target_user = "自己" if user_id == int(current_user.id) else username
        log_user_action('CHANGE_PASSWORD', f'修改密码: 目标用户={target_user}, 操作人: {operator_username}', current_user.id, operator_username)
        
        return jsonify({
            'success': True,
            'message': '密码修改成功'
        })
    except Exception as e:
        print(f"修改用户密码时出错: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@auth_bp.route('/api/users/<int:user_id>/permissions', methods=['PUT'])
@login_required
@admin_required
def update_user_permissions(user_id):
    try:
        data = request.get_json()
        permissions = data.get('permissions', [])
        
        if not isinstance(permissions, list):
            return jsonify({
                'success': False,
                'message': '权限格式不正确'
            })
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT role, username FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            
            if not user:
                connection.close()
                return jsonify({
                    'success': False,
                    'message': '用户不存在'
                })
            
            if user['role'] == 'admin':
                connection.close()
                return jsonify({
                    'success': False,
                    'message': '管理员权限不可修改'
                })
            
            username = user['username']
            cursor.execute("""
                UPDATE users 
                SET permissions=%s 
                WHERE id=%s
            """, (json.dumps(permissions), user_id))
            connection.commit()
            
        connection.close()
        
        operator_username = get_username_by_id(current_user.id)
        permissions_str = ', '.join(permissions) if permissions else '无'
        log_user_action('UPDATE_PERMISSIONS', f'更新权限: 用户={username}, 权限列表={permissions_str}, 操作人: {operator_username}', current_user.id, operator_username)
        
        return jsonify({
            'success': True,
            'message': '权限更新成功'
        })
    except Exception as e:
        print(f"更新用户权限时出错: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@auth_bp.route('/api/current-user')
@login_required
def get_current_user():
    try:
        user_id = current_user.id
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, username, email, role, permissions FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
        connection.close()
        
        if user:
            return jsonify({
                'success': True,
                'username': user['username'],
                'email': user['email'],
                'role': user['role'],
                'permissions': user['permissions']
            })
        else:
            return jsonify({
                'success': False,
                'message': '用户不存在'
            }), 404
    except Exception as e:
        print(f"获取当前用户信息时出错: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
