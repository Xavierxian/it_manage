from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from .database import get_db_connection
from .cache_manager import cache_manager, clear_port_cache
from .auth import permission_required
from io import BytesIO
import pandas as pd
import re

port_bp = Blueprint('port_mapping', __name__)

def validate_ip_address(ip):
    """验证IP地址格式"""
    if not ip:
        return True
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, ip):
        return False
    parts = ip.split('.')
    return all(0 <= int(part) <= 255 for part in parts)

def validate_port(port):
    """验证端口号"""
    if not port:
        return False
    try:
        port_num = int(port)
        return 1 <= port_num <= 65535
    except ValueError:
        return False

def validate_protocol(protocol):
    """验证协议类型"""
    if not protocol:
        return False
    protocol_upper = protocol.upper()
    return protocol_upper in ['TCP', 'UDP', 'TCP/UDP']

def validate_port_mapping_data(data):
    """验证端口映射数据"""
    errors = []
    
    if not data.get('interface'):
        errors.append('接口不能为空')
    
    if not validate_protocol(data.get('protocol')):
        errors.append('协议类型必须是TCP、UDP或TCP/UDP')
    
    if not validate_ip_address(data.get('public_ip')):
        errors.append('公网IP格式不正确')
    
    if not validate_port(data.get('public_port')):
        errors.append('公网端口必须在1-65535之间')
    
    if not validate_ip_address(data.get('private_ip')):
        errors.append('内网IP格式不正确')
    
    if not validate_port(data.get('private_port')):
        errors.append('内网端口必须在1-65535之间')
    
    return errors

@port_bp.route('/port_mapping')
@login_required
@permission_required('port_mapping')
def port_mapping():
    return render_template('port_mapping_new.html')

@port_bp.route('/api/port-mappings')
@login_required
@permission_required('port_mapping')
def get_port_mappings():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM nat_mappings ORDER BY created_at DESC")
            mappings = cursor.fetchall()
        connection.close()
        
        for mapping in mappings:
            if mapping['created_at']:
                mapping['created_at'] = mapping['created_at'].strftime('%Y-%m-%d %H:%M:%S')
            if mapping['updated_at']:
                mapping['updated_at'] = mapping['updated_at'].strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({'mappings': mappings})
    except Exception as e:
        print(f"获取端口映射数据时出错: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'mappings': []}), 500

@port_bp.route('/api/port-mappings', methods=['POST'])
@login_required
@permission_required('port_mapping')
def add_port_mapping():
    try:
        data = request.get_json()
        
        errors = validate_port_mapping_data(data)
        if errors:
            return jsonify({'success': False, 'message': '; '.join(errors)})
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO nat_mappings (interface, protocol, public_ip, public_port, private_ip, private_port, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
            """, (
                data['interface'],
                data['protocol'],
                data['public_ip'],
                data['public_port'],
                data['private_ip'],
                data['private_port']
            ))
            connection.commit()
        connection.close()
        
        clear_port_cache()
        
        return jsonify({'success': True, 'message': '端口映射添加成功'})
    except Exception as e:
        print(f"添加端口映射时出错: {e}")
        return jsonify({'success': False, 'message': '添加失败'})

@port_bp.route('/api/port-mappings/<int:mapping_id>', methods=['PUT'])
@login_required
@permission_required('port_mapping')
def update_port_mapping(mapping_id):
    try:
        data = request.get_json()
        
        errors = validate_port_mapping_data(data)
        if errors:
            return jsonify({'success': False, 'message': '; '.join(errors)})
        
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE nat_mappings 
                SET interface=%s, protocol=%s, public_ip=%s, public_port=%s, private_ip=%s, private_port=%s, updated_at=NOW()
                WHERE id=%s
            """, (
                data['interface'],
                data['protocol'],
                data['public_ip'],
                data['public_port'],
                data['private_ip'],
                data['private_port'],
                mapping_id
            ))
            connection.commit()
        connection.close()
        
        clear_port_cache()
        
        return jsonify({'success': True, 'message': '端口映射更新成功'})
    except Exception as e:
        print(f"更新端口映射时出错: {e}")
        return jsonify({'success': False, 'message': '更新失败'})

@port_bp.route('/api/port-mappings/<int:mapping_id>', methods=['DELETE'])
@login_required
@permission_required('port_mapping')
def delete_port_mapping(mapping_id):
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM nat_mappings WHERE id=%s", (mapping_id,))
            connection.commit()
        connection.close()
        
        clear_port_cache()
        
        return jsonify({'success': True, 'message': '端口映射删除成功'})
    except Exception as e:
        print(f"删除端口映射时出错: {e}")
        return jsonify({'success': False, 'message': '删除失败'})

@port_bp.route('/api/port-mappings/export')
@login_required
@permission_required('port_mapping')
def export_port_mappings():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM nat_mappings ORDER BY created_at DESC")
            mappings = cursor.fetchall()
        connection.close()
        
        df = pd.DataFrame(mappings)
        output = BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return output.getvalue(), 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename=port_mappings.csv'
        }
    except Exception as e:
        print(f"导出端口映射时出错: {e}")
        return jsonify({'error': '导出失败'})
