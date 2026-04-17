from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from .database import get_db_connection
from .cache_manager import cache_manager, clear_domain_cache
from .auth import permission_required
from io import BytesIO
import pandas as pd
import re

domain_bp = Blueprint('domain_mapping', __name__)

def validate_domain_name(domain):
    """验证域名格式"""
    if not domain:
        return False
    pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$'
    return re.match(pattern, domain) is not None

def validate_record_type(record_type):
    """验证记录类型"""
    if not record_type:
        return False
    return record_type.upper() in ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV']

def validate_domain_record_data(data):
    """验证域名记录数据"""
    errors = []
    
    if not data.get('platform'):
        errors.append('平台不能为空')
    
    if not data.get('domain_name') or not validate_domain_name(data.get('domain_name')):
        errors.append('域名格式不正确')
    
    if not data.get('sub_domain'):
        errors.append('子域名不能为空')
    
    if not validate_record_type(data.get('record_type')):
        errors.append('记录类型必须是A、AAAA、CNAME、MX、TXT、NS或SRV')
    
    if not data.get('record_value'):
        errors.append('记录值不能为空')
    
    if data.get('ttl'):
        try:
            ttl = int(data.get('ttl'))
            if ttl < 60 or ttl > 86400:
                errors.append('TTL值必须在60-86400之间')
        except ValueError:
            errors.append('TTL值必须是数字')
    
    return errors

@domain_bp.route('/domain_mapping')
@login_required
@permission_required('domain_mapping')
def domain_mapping():
    return render_template('domain_mapping_new.html')

@domain_bp.route('/api/domain-records')
@login_required
@permission_required('domain_mapping')
def get_domain_records():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM dns_records_all ORDER BY created_at DESC")
            records = cursor.fetchall()
        connection.close()
        
        for record in records:
            if record['created_at']:
                record['created_at'] = record['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            if record['updated_at']:
                record['updated_at'] = record['updated_at'].strftime('%Y-%m-%d %H:%M:%S')
            if record['last_sync_time']:
                record['last_sync_time'] = record['last_sync_time'].strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({'records': records})
    except Exception as e:
        print(f"获取域名记录数据时出错: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'records': []}), 500

@domain_bp.route('/api/domain-records', methods=['POST'])
@login_required
@permission_required('domain_mapping')
def add_domain_record():
    try:
        data = request.get_json()
        
        errors = validate_domain_record_data(data)
        if errors:
            return jsonify({'success': False, 'message': '; '.join(errors)})
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO dns_records_all (platform, domain_name, sub_domain, record_type, record_line, record_value, ttl, status, weight, mx_priority, comment, created_at, updated_at, last_sync_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
            """, (
                data['platform'],
                data['domain_name'],
                data['sub_domain'],
                data['record_type'],
                data['record_line'],
                data['record_value'],
                data['ttl'],
                data['status'],
                data['weight'],
                data['mx_priority'],
                data['comment']
            ))
            connection.commit()
        connection.close()
        
        clear_domain_cache()
        
        return jsonify({'success': True, 'message': '域名记录添加成功'})
    except Exception as e:
        print(f"添加域名记录时出错: {e}")
        return jsonify({'success': False, 'message': '添加失败'})

@domain_bp.route('/api/domain-records/<int:record_id>', methods=['PUT'])
@login_required
@permission_required('domain_mapping')
def update_domain_record(record_id):
    try:
        data = request.get_json()
        
        errors = validate_domain_record_data(data)
        if errors:
            return jsonify({'success': False, 'message': '; '.join(errors)})
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE dns_records_all 
                SET platform=%s, domain_name=%s, sub_domain=%s, record_type=%s, record_line=%s, record_value=%s, ttl=%s, status=%s, weight=%s, mx_priority=%s, comment=%s, updated_at=NOW(), last_sync_time=NOW()
                WHERE id=%s
            """, (
                data['platform'],
                data['domain_name'],
                data['sub_domain'],
                data['record_type'],
                data['record_line'],
                data['record_value'],
                data['ttl'],
                data['status'],
                data['weight'],
                data['mx_priority'],
                data['comment'],
                record_id
            ))
            connection.commit()
        connection.close()
        
        clear_domain_cache()
        
        return jsonify({'success': True, 'message': '域名记录更新成功'})
    except Exception as e:
        print(f"更新域名记录时出错: {e}")
        return jsonify({'success': False, 'message': '更新失败'})

@domain_bp.route('/api/domain-records/<int:record_id>', methods=['DELETE'])
@login_required
@permission_required('domain_mapping')
def delete_domain_record(record_id):
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM dns_records_all WHERE id=%s", (record_id,))
            connection.commit()
        connection.close()
        
        clear_domain_cache()
        
        return jsonify({'success': True, 'message': '域名记录删除成功'})
    except Exception as e:
        print(f"删除域名记录时出错: {e}")
        return jsonify({'success': False, 'message': '删除失败'})

@domain_bp.route('/api/domain-records/export')
@login_required
@permission_required('domain_mapping')
def export_domain_records():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM dns_records_all ORDER BY created_at DESC")
            records = cursor.fetchall()
        connection.close()
        
        df = pd.DataFrame(records)
        output = BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename=domain_records.csv'
        }
    except Exception as e:
        print(f"导出域名记录时出错: {e}")
        return jsonify({'error': '导出失败'})
