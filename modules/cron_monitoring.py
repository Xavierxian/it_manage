from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from .auth import permission_required
from .database import get_db_connection
from .security_logger import log_user_action
from datetime import datetime, timedelta
import paramiko
import os
import sys
import re
from dotenv import load_dotenv

load_dotenv()

cron_monitoring_bp = Blueprint('cron_monitoring', __name__)

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

SSH_CONFIG = {
    'host': os.getenv('SSH_HOST'),
    'port': int(os.getenv('SSH_PORT')),
    'username': os.getenv('SSH_USERNAME'),
    'password': os.getenv('SSH_PASSWORD'),
    'key_filename': os.getenv('SSH_KEY_FILE')
}

ALLOWED_COMMANDS = [
    'crontab -l',
    'test -f',
    'cat',
    'journalctl',
    'touch',
    'grep',
    'echo',
    'bash -lc'
]

def validate_command(command):
    """
    验证SSH命令是否安全
    只允许预定义的安全命令
    """
    command = command.strip()
    
    for allowed_cmd in ALLOWED_COMMANDS:
        if command.startswith(allowed_cmd):
            return True
    
    return False

def sanitize_command_input(input_str):
    """
    清理用户输入，防止命令注入
    """
    if not input_str:
        return ""
    
    input_str = str(input_str)
    
    input_str = re.sub(r'[;&|`$(){}[\]<>]', '', input_str)
    
    input_str = re.sub(r'\s+', ' ', input_str).strip()
    
    return input_str

def get_ssh_connection():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    if SSH_CONFIG['key_filename'] and os.path.exists(SSH_CONFIG['key_filename']):
        ssh.connect(
            hostname=SSH_CONFIG['host'],
            port=SSH_CONFIG['port'],
            username=SSH_CONFIG['username'],
            key_filename=SSH_CONFIG['key_filename']
        )
    else:
        ssh.connect(
            hostname=SSH_CONFIG['host'],
            port=SSH_CONFIG['port'],
            username=SSH_CONFIG['username'],
            password=SSH_CONFIG['password']
        )
    
    return ssh

def execute_ssh_command(ssh, command):
    """
    执行SSH命令，带有安全验证
    """
    if not validate_command(command):
        print(f"Security Alert: Attempted to execute unauthorized command: {command}")
        raise ValueError(f"Unauthorized command: {command}")
    
    stdin, stdout, stderr = ssh.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')
    return exit_code, output, error

def get_cron_jobs(ssh):
    exit_code, output, error = execute_ssh_command(ssh, 'crontab -l')
    if exit_code != 0:
        return []
    
    jobs = []
    current_comment = ''
    job_order = 0
    
    for line in output.split('\n'):
        line = line.strip()
        if line.startswith('#'):
            current_comment = line[1:].strip()
        elif line and not line.startswith('@'):
            parts = line.split()
            if len(parts) >= 6:
                schedule = ' '.join(parts[:5])
                command = ' '.join(parts[5:])
                job_name = current_comment if current_comment else f'任务 {len(jobs) + 1}'
                
                jobs.append({
                    'job_name': job_name,
                    'schedule': schedule,
                    'command': command,
                    'order': job_order
                })
                job_order += 1
    
    return jobs

def get_cron_log(ssh, job_name, command, date):
    date_str = date.strftime('%Y-%m-%d')
    
    log_paths = []
    
    if 'it_manage' in command:
        log_paths.append(f'/var/log/cron/it_manage_cron_{date_str}.log')
    elif 'vanna-flask' in command:
        log_paths.append(f'/var/log/cron/vanna-flask_cron_{date_str}.log')
    elif 'yuming-yingshe' in command:
        log_paths.append(f'/var/log/cron/yuming-yingshe_cron_{date_str}.log')
    elif 'k8s_ResourceSynchronization' in command:
        log_paths.append(f'/var/log/cron/k8s_ResourceSynchronization_cron_{date_str}.log')
    elif 'duankou-yingshe' in command:
        log_paths.append(f'/var/log/cron/duankou-yingshe_cron_{date_str}.log')
    elif 'dd_kaoqindaka' in command:
        log_paths.append(f'/var/log/cron/dd_kaoqindaka_cron_{date_str}.log')
    elif 'dd_tongxunlu' in command:
        log_paths.append(f'/var/log/cron/dd_tongxunlu_cron_{date_str}.log')
    elif 'dd_kaoqinzucy' in command:
        log_paths.append(f'/var/log/cron/dd_kaoqinzucy_cron_{date_str}.log')
    elif 'dd_waiqin' in command:
        log_paths.append(f'/var/log/cron/dd_waiqin_cron_{date_str}.log')
    
    log_entries = []
    
    for log_path in log_paths:
        command_check = f"test -f {log_path} && cat {log_path} 2>/dev/null || echo 'File not found'"
        exit_code, output, error = execute_ssh_command(ssh, command_check)
        
        if exit_code == 0 and 'File not found' not in output:
            for line in output.split('\n'):
                line = line.strip()
                if line:
                    log_entries.append(f"[{log_path}] {line}")
            break
    
    if not log_entries:
        syslog_command = f"journalctl --since '{date_str} 00:00:00' --until '{date_str} 23:59:59' -u cron 2>/dev/null | grep -i '{job_name}' || echo 'No log found'"
        exit_code, output, error = execute_ssh_command(ssh, syslog_command)
        
        for line in output.split('\n'):
            line = line.strip()
            if line and 'No log found' not in line:
                log_entries.append(line)
    
    return log_entries

def parse_cron_schedule(schedule):
    parts = schedule.split()
    if len(parts) != 5:
        return schedule, None
    
    minute, hour, day, month, weekday = parts
    
    def parse_cron_field(field):
        if field == '*':
            return 0
        if ',' in field:
            return int(field.split(',')[0])
        if '-' in field:
            return int(field.split('-')[0])
        if '/' in field:
            parts = field.split('/')
            if parts[0] == '*':
                return 0
            return int(parts[0])
        return int(field)
    
    minute_val = parse_cron_field(minute)
    hour_val = parse_cron_field(hour)
    
    execute_time = f"{hour_val:02d}:{minute_val:02d}"
    
    return schedule, execute_time

def calculate_next_execute_time(schedule, current_date=None):
    if current_date is None:
        current_date = datetime.now()
    
    parts = schedule.split()
    if len(parts) != 5:
        return None
    
    minute, hour, day, month, weekday = parts
    
    def parse_minute_field(field):
        if field == '*':
            return list(range(60))
        if ',' in field:
            return [int(x) for x in field.split(',')]
        if '-' in field:
            start, end = field.split('-')
            return list(range(int(start), int(end) + 1))
        if '/' in field:
            parts = field.split('/')
            if parts[0] == '*':
                step = int(parts[1])
                return list(range(0, 60, step))
            start = int(parts[0])
            step = int(parts[1])
            return list(range(start, 60, step))
        return [int(field)]
    
    def parse_hour_field(field):
        if field == '*':
            return list(range(24))
        if ',' in field:
            return [int(x) for x in field.split(',')]
        if '-' in field:
            start, end = field.split('-')
            return list(range(int(start), int(end) + 1))
        if '/' in field:
            parts = field.split('/')
            if parts[0] == '*':
                step = int(parts[1])
                return list(range(0, 24, step))
            start = int(parts[0])
            step = int(parts[1])
            return list(range(start, 24, step))
        return [int(field)]
    
    def parse_day_field(field):
        if field == '*':
            return list(range(1, 32))
        if ',' in field:
            return [int(x) for x in field.split(',')]
        if '-' in field:
            start, end = field.split('-')
            return list(range(int(start), int(end) + 1))
        if '/' in field:
            parts = field.split('/')
            if parts[0] == '*':
                step = int(parts[1])
                return list(range(1, 32, step))
            start = int(parts[0])
            step = int(parts[1])
            return list(range(start, 32, step))
        return [int(field)]
    
    def parse_month_field(field):
        if field == '*':
            return list(range(1, 13))
        if ',' in field:
            return [int(x) for x in field.split(',')]
        if '-' in field:
            start, end = field.split('-')
            return list(range(int(start), int(end) + 1))
        if '/' in field:
            parts = field.split('/')
            if parts[0] == '*':
                step = int(parts[1])
                return list(range(1, 13, step))
            start = int(parts[0])
            step = int(parts[1])
            return list(range(start, 13, step))
        return [int(field)]
    
    def parse_weekday_field(field):
        if field == '*':
            return list(range(7))
        if ',' in field:
            return [int(x) for x in field.split(',')]
        if '-' in field:
            start, end = field.split('-')
            return list(range(int(start), int(end) + 1))
        if '/' in field:
            parts = field.split('/')
            if parts[0] == '*':
                step = int(parts[1])
                return list(range(0, 7, step))
            start = int(parts[0])
            step = int(parts[1])
            return list(range(start, 7, step))
        return [int(field)]
    
    minute_values = parse_minute_field(minute)
    hour_values = parse_hour_field(hour)
    day_values = parse_day_field(day)
    month_values = parse_month_field(month)
    weekday_values = parse_weekday_field(weekday)
    
    def find_next_execution():
        search_date = current_date
        max_days = 365
        
        for _ in range(max_days):
            year = search_date.year
            month = search_date.month
            day = search_date.day
            
            if month in month_values:
                if day in day_values:
                    weekday = search_date.weekday()
                    if weekday in weekday_values:
                        # 检查今天是否还有执行时间
                        if search_date.date() == current_date.date():
                            for hour in sorted(hour_values):
                                if hour > current_date.hour:
                                    # 今天的小时还没到
                                    for minute in sorted(minute_values):
                                        candidate_time = datetime(year, month, day, hour, minute)
                                        if candidate_time > current_date:
                                            return candidate_time
                                elif hour == current_date.hour:
                                    # 今天的当前小时
                                    for minute in sorted(minute_values):
                                        candidate_time = datetime(year, month, day, hour, minute)
                                        if candidate_time > current_date:
                                            return candidate_time
                        else:
                            # 明天及以后，使用第一个小时和第一个分钟
                            hour = sorted(hour_values)[0]
                            minute = sorted(minute_values)[0]
                            return datetime(year, month, day, hour, minute)
            
            search_date += timedelta(days=1)
        
        return None
    
    next_execute_time = find_next_execution()
    
    return next_execute_time

def parse_cron_log_status(log_entries):
    if not log_entries:
        return 'pending', None, None, None
    
    status = 'success'
    exit_code = 0
    error_message = None
    execute_time = None
    
    for entry in log_entries:
        if 'error' in entry.lower() or 'failed' in entry.lower():
            status = 'failed'
            error_message = entry
        elif 'exit code' in entry.lower():
            try:
                exit_code = int(entry.lower().split('exit code')[1].strip().split()[0])
                if exit_code != 0:
                    status = 'failed'
            except:
                pass
        
        if not execute_time:
            import re
            time_pattern = r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}'
            time_match = re.search(time_pattern, entry)
            if time_match:
                try:
                    execute_time = datetime.strptime(time_match.group(), '%Y-%m-%d %H:%M:%S')
                except:
                    pass
    
    return status, exit_code, error_message, execute_time

def save_cron_job_status(job_name, server_ip, cron_schedule, command, execute_date, status, exit_code=None, error_message=None, log_content=None, execute_time=None, cron_order=None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            execute_time_str = None
            next_execute_time = None
            
            if cron_schedule:
                _, execute_time_str = parse_cron_schedule(cron_schedule)
                next_execute_time = calculate_next_execute_time(cron_schedule)
                
                # 确保时间格式正确，去掉微秒
                if next_execute_time:
                    next_execute_time = next_execute_time.replace(microsecond=0)
            
            cursor.execute("""
                INSERT INTO cron_job_monitor 
                (job_name, server_ip, cron_schedule, command, execute_time, next_execute_time, last_execute_date, last_execute_time, status, exit_code, error_message, log_content, cron_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                cron_schedule = VALUES(cron_schedule),
                command = VALUES(command),
                execute_time = VALUES(execute_time),
                next_execute_time = VALUES(next_execute_time),
                last_execute_date = CASE WHEN VALUES(last_execute_time) IS NOT NULL THEN VALUES(last_execute_date) ELSE last_execute_date END,
                last_execute_time = CASE WHEN VALUES(last_execute_time) IS NOT NULL THEN VALUES(last_execute_time) ELSE last_execute_time END,
                status = VALUES(status),
                exit_code = VALUES(exit_code),
                error_message = VALUES(error_message),
                log_content = VALUES(log_content),
                cron_order = VALUES(cron_order),
                updated_at = CURRENT_TIMESTAMP
            """, (job_name, server_ip, cron_schedule, command, execute_time_str, next_execute_time, execute_date, execute_time, status, exit_code, error_message, '\n'.join(log_content) if log_content else None, cron_order))
        connection.commit()
    finally:
        connection.close()

def get_cron_job_list(page=1, per_page=10):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            offset = (page - 1) * per_page
            cursor.execute("""
                SELECT * FROM cron_job_monitor
                ORDER BY cron_order ASC
                LIMIT %s OFFSET %s
            """, (per_page, offset))
            
            results = cursor.fetchall()
            
            cursor.execute("SELECT COUNT(*) as total FROM cron_job_monitor")
            total = cursor.fetchone()['total']
        connection.close()
        
        return results, total
    finally:
        connection.close()

# 添加实时日志相关功能
import threading
import time

# 用于存储实时日志的字典
realtime_logs = {}

# 日志监控线程锁
log_lock = threading.Lock()

# 用于标记日志监控是否应该停止
log_stop_flags = {}

# 监控日志文件的函数
def monitor_log(ssh, log_path, job_id):
    buffer = ""

    with log_lock:
        realtime_logs[job_id] = []
        log_stop_flags[job_id] = False

    stdin, stdout, stderr = ssh.exec_command(
        f"tail -n 0 -f {log_path}",
        get_pty=True
    )

    channel = stdout.channel

    try:
        while True:
            with log_lock:
                if log_stop_flags.get(job_id):
                    break

            if channel.recv_ready():
                data = channel.recv(4096).decode("utf-8", errors="ignore")
                buffer += data

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.rstrip()
                    if line:
                        with log_lock:
                            realtime_logs[job_id].append(line)
            else:
                time.sleep(0.1)

    finally:
        try:
            stdin.close()
            stdout.close()
            stderr.close()
            ssh.close()
        except:
            pass

# 获取实时日志的API
@cron_monitoring_bp.route('/api/realtime-log/<int:job_id>', methods=['GET'])
def get_realtime_log(job_id):
    global realtime_logs
    with log_lock:
        logs = realtime_logs.get(job_id, [])
        # 返回新的日志并清空已返回的日志
        realtime_logs[job_id] = []
    return jsonify({'success': True, 'logs': logs})

@cron_monitoring_bp.route('/cron_monitoring')
@login_required
@permission_required('cron_monitoring')
def cron_monitoring():
    return render_template('cron_monitoring.html')

@cron_monitoring_bp.route('/api/cron-jobs', methods=['GET'])
@login_required
@permission_required('cron_monitoring')
def get_cron_jobs_api():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        
        jobs, total = get_cron_job_list(page, per_page)
        
        return jsonify({
            'success': True,
            'jobs': jobs,
            'total': total,
            'page': page,
            'per_page': per_page
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        })

@cron_monitoring_bp.route('/api/cron-job-detail/<int:job_id>', methods=['GET'])
@login_required
@permission_required('cron_monitoring')
def get_cron_job_detail(job_id):
    try:
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM cron_job_monitor WHERE id = %s", (job_id,))
                job = cursor.fetchone()
            
            if not job:
                return jsonify({
                    'success': False,
                    'message': '任务不存在'
                })
            
            return jsonify({
                'success': True,
                'job': job
            })
        finally:
            connection.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        })

@cron_monitoring_bp.route('/api/cron-monitoring-data', methods=['GET'])
@login_required
@permission_required('cron_monitoring')
def get_cron_monitoring_data():
    try:
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                # 获取所有任务的统计信息
                cursor.execute("SELECT status, COUNT(*) as count FROM cron_job_monitor GROUP BY status")
                status_counts = cursor.fetchall()
            
            # 初始化计数
            success_count = 0
            failed_count = 0
            pending_count = 0
            
            # 根据数据库结果设置计数
            for row in status_counts:
                if row['status'] == 'success':
                    success_count = row['count']
                elif row['status'] == 'failed':
                    failed_count = row['count']
                elif row['status'] == 'pending':
                    pending_count = row['count']
            
            return jsonify({
                'success': True,
                'success_data': [success_count],  # 兼容前端期望的数组格式
                'failed_data': [failed_count],    # 兼容前端期望的数组格式
                'pending_data': [pending_count]   # 兼容前端期望的数组格式
            })
        finally:
            connection.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        })

@cron_monitoring_bp.route('/api/refresh-cron-jobs', methods=['POST'])
@login_required
@permission_required('cron_monitoring')
def refresh_cron_jobs():
    try:
        ssh = get_ssh_connection()
        
        jobs = get_cron_jobs(ssh)
        
        today = datetime.now().date()
        
        results = []
        for job in jobs:
            job_name = job.get('job_name', 'unknown')
            command = job.get('command', '')
            schedule = job.get('schedule', '')
            order = job.get('order', 0)
            
            log_entries = get_cron_log(ssh, job_name, command, today)
            status, exit_code, error_message, execute_time = parse_cron_log_status(log_entries)
            
            save_cron_job_status(
                job_name=job_name,
                server_ip=SSH_CONFIG['host'],
                cron_schedule=schedule,
                command=command,
                execute_date=today,
                status=status,
                exit_code=exit_code,
                error_message=error_message,
                log_content=log_entries,
                execute_time=execute_time,
                cron_order=order
            )
            
            results.append({
                'job_name': job_name,
                'schedule': schedule,
                'status': status
            })
        
        ssh.close()
        
        return jsonify({
            'success': True,
            'message': f'成功刷新 {len(results)} 个定时任务',
            'jobs': results
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': str(e)
        })

@cron_monitoring_bp.route('/api/execute-cron-job/<int:job_id>', methods=['POST'])
@login_required
@permission_required('cron_monitoring')
def execute_cron_job(job_id):
    try:
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM cron_job_monitor WHERE id = %s", (job_id,))
                job = cursor.fetchone()
            connection.close()
            
            if not job:
                return jsonify({
                    'success': False,
                    'message': '任务不存在'
                })
            
            command = job.get('command')
            if not command:
                return jsonify({
                    'success': False,
                    'message': '任务命令为空，请先点击"刷新任务状态"按钮更新数据'
                })
            
            # 验证命令安全性
            if not validate_command(command):
                return jsonify({
                    'success': False,
                    'message': '任务命令包含不安全的内容，无法执行'
                })
            
            job_name = job.get('job_name', 'unknown')
            
            # 确定日志文件路径
            today = datetime.now().date()
            date_str = today.strftime('%Y-%m-%d')
            log_path = None
            
            # 根据任务名称确定日志文件路径
            if 'it_manage' in command:
                log_path = f'/var/log/cron/it_manage_cron_{date_str}.log'
            elif 'vanna-flask' in command:
                log_path = f'/var/log/cron/vanna-flask_cron_{date_str}.log'
            elif 'yuming-yingshe' in command:
                log_path = f'/var/log/cron/yuming-yingshe_cron_{date_str}.log'
            elif 'k8s_ResourceSynchronization' in command:
                log_path = f'/var/log/cron/k8s_ResourceSynchronization_cron_{date_str}.log'
            elif 'duankou-yingshe' in command:
                log_path = f'/var/log/cron/duankou-yingshe_cron_{date_str}.log'
            elif 'dd_kaoqindaka' in command:
                log_path = f'/var/log/cron/dd_kaoqindaka_cron_{date_str}.log'
            elif 'dd_tongxunlu' in command:
                log_path = f'/var/log/cron/dd_tongxunlu_cron_{date_str}.log'
            elif 'dd_kaoqinzucy' in command:
                log_path = f'/var/log/cron/dd_kaoqinzucy_cron_{date_str}.log'
            elif 'dd_waiqin' in command:
                log_path = f'/var/log/cron/dd_waiqin_cron_{date_str}.log'
            
            # 准备实时日志存储
            global realtime_logs
            with log_lock:
                realtime_logs[job_id] = []
            
            # 为任务执行创建独立的SSH连接
            execute_ssh = get_ssh_connection()
            execute_start_time = datetime.now()
            
            # 创建并清空日志文件，确保只记录本次执行的日志
            if log_path:
                execute_ssh_command(execute_ssh, f"touch {log_path} && > {log_path}")
            
            # 启动日志监控线程（如果找到日志文件）
            log_thread = None
            if log_path:
                # 为日志监控创建独立的SSH连接
                monitor_ssh = get_ssh_connection()
                log_thread = threading.Thread(target=monitor_log, args=(monitor_ssh, log_path, job_id))
                log_thread.daemon = True
                log_thread.start()
            
            # 添加任务开始执行的日志
            if log_path:
                start_log_command = f'echo "=== 任务开始执行于 $(date) ===" >> {log_path}'
                execute_ssh_command(execute_ssh, start_log_command)
            
            # 将命令输出重定向到日志文件
            if log_path:
                command_with_log = (f"bash -lc 'exec stdbuf -oL -eL {command} >> {log_path} 2>&1'")

                exit_code, output, error = execute_ssh_command(execute_ssh, command_with_log)
            else:
                exit_code, output, error = execute_ssh_command(execute_ssh, command)
            
            # 添加任务执行完成的日志
            if log_path:
                end_log_command = f'echo "=== 任务执行结束于 $(date) ===" >> {log_path}'
                execute_ssh_command(execute_ssh, end_log_command)
            
            # 关闭任务执行的SSH连接
            execute_ssh.close()
            
            # 等待日志线程收集更多日志
            time.sleep(1)
            
            # 设置停止标志，通知日志监控线程停止
            if log_path:
                with log_lock:
                    if job_id in log_stop_flags:
                        log_stop_flags[job_id] = True
            
            # 等待日志线程结束
            if log_thread:
                log_thread.join(timeout=3)  # 最多等待3秒
            
            # 获取所有日志
            with log_lock:
                log_entries = realtime_logs.get(job_id, [])
                # 清理实时日志和停止标志
                if job_id in realtime_logs:
                    del realtime_logs[job_id]
                if job_id in log_stop_flags:
                    del log_stop_flags[job_id]
            
            status, exit_code, error_message, _ = parse_cron_log_status(log_entries)
            
            save_cron_job_status(
                job_name=job_name,
                server_ip=job.get('server_ip'),
                cron_schedule=job.get('cron_schedule'),
                command=command,
                execute_date=today,
                status=status,
                exit_code=exit_code,
                error_message=error_message,
                log_content=log_entries,
                execute_time=execute_start_time
            )
            
            operator_username = get_username_by_id(current_user.id)
            status_text = '成功' if status == 'success' else '失败'
            log_user_action('EXECUTE_CRON_JOB', f'执行定时任务: 任务名称={job_name}, 状态={status_text}, 操作人: {operator_username}', current_user.id, operator_username)
            
            return jsonify({
                'success': True,
                'message': f'任务 {job_name} 已执行',
                'status': status,
                'exit_code': exit_code,
                'output': output,
                'error': error,
                'log': ''
            })
        finally:
            connection.close()
    except Exception as e:
        import traceback
        traceback.print_exc()
        # 清理实时日志
        with log_lock:
            if job_id in realtime_logs:
                del realtime_logs[job_id]
        return jsonify({
                'success': False,
                'message': f'执行失败: {str(e)}',
                'log': ''
            })
