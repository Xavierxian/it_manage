from flask import Blueprint, render_template, jsonify
from flask_login import login_required
from .database import get_db_connection
from .auth import permission_required
from .cache_manager import cache_manager
from . import config
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

cache = config.cache

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@dashboard_bp.route('/api/dashboard/stats')
@cache.cached(timeout=300, key_prefix=lambda: cache_manager.get_full_key('DASHBOARD_STATS'))
def dashboard_stats():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM nat_mappings")
            port_total = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as tcp FROM nat_mappings WHERE protocol LIKE '%tcp%' OR protocol = 'TCP' OR protocol = '6(tcp)'")
            port_tcp = cursor.fetchone()['tcp']
            
            cursor.execute("SELECT COUNT(*) as udp FROM nat_mappings WHERE protocol LIKE '%udp%' OR protocol = 'UDP' OR protocol = '17(udp)'")
            port_udp = cursor.fetchone()['udp']
            
            cursor.execute("SELECT COUNT(*) as total FROM dns_records_all")
            domain_total = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as a_records FROM dns_records_all WHERE record_type = 'A'")
            domain_a = cursor.fetchone()['a_records']
            
            cursor.execute("SELECT COUNT(*) as cname FROM dns_records_all WHERE record_type = 'CNAME'")
            domain_cname = cursor.fetchone()['cname']
            
            cursor.execute("SELECT COUNT(*) as enabled FROM dns_records_all WHERE status = 'ENABLE' OR status = 'enabled'")
            domain_enabled = cursor.fetchone()['enabled']
            
            cursor.execute("SELECT * FROM assets")
            all_vms = cursor.fetchall()
            vm_total = len(all_vms)
            vm_active = len([vm for vm in all_vms if vm.get('是否在用') == '是'])
            
            cursor.execute("SELECT COUNT(*) as total FROM xenserver")
            pm_total = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as total FROM bseip")
            ns_total = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as active FROM bseip WHERE 是否停用 = '否'")
            ns_active = cursor.fetchone()['active']
            
            trend_data = {
                'labels': [],
                'portMappings': [],
                'domainMappings': []
            }
            
            for i in range(7):
                date = datetime.now() - timedelta(days=i)
                date_str = date.strftime('%m-%d')
                trend_data['labels'].insert(0, date_str)
                
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM nat_mappings 
                    WHERE DATE(created_at) <= %s
                """, (date.strftime('%Y-%m-%d'),))
                port_count = cursor.fetchone()['count']
                trend_data['portMappings'].insert(0, port_count)
                
                cursor.execute("""
                    SELECT COUNT(*) as count 
                    FROM dns_records_all 
                    WHERE DATE(created_at) <= %s
                """, (date.strftime('%Y-%m-%d'),))
                domain_count = cursor.fetchone()['count']
                trend_data['domainMappings'].insert(0, domain_count)
            
            recent_activity = []
            cursor.execute("""
                SELECT '端口映射' as type, '创建' as action, CONCAT(interface, ':', public_port, '->', private_ip, ':', private_port) as description, 
                       created_at as timestamp, 'success' as status
                FROM nat_mappings 
                ORDER BY created_at DESC LIMIT 5
            """)
            port_activities = cursor.fetchall()
            
            cursor.execute("""
                SELECT '域名记录' as type, '创建' as action, CONCAT(sub_domain, '.', domain_name, ' -> ', record_value) as description,
                       created_at as timestamp, 'success' as status
                FROM dns_records_all 
                ORDER BY created_at DESC LIMIT 5
            """)
            domain_activities = cursor.fetchall()
            
            recent_activity = port_activities + domain_activities
            recent_activity.sort(key=lambda x: x['timestamp'], reverse=True)
            recent_activity = recent_activity[:5]
            
        connection.close()
        
        return jsonify({
            'portMappings': {
                'total': port_total,
                'active': port_total,
                'tcp': port_tcp,
                'udp': port_udp,
                'commonPorts': 0
            },
            'domainMappings': {
                'total': domain_total,
                'active': domain_enabled,
                'aRecords': domain_a,
                'cnameRecords': domain_cname,
                'enabled': domain_enabled
            },
            'vmStats': {
                'total': vm_total,
                'active': vm_active
            },
            'pmStats': {
                'total': pm_total
            },
            'nsStats': {
                'total': ns_total,
                'active': ns_active
            },
            'trends': trend_data,
            'recentActivity': recent_activity,
            'lastSync': datetime.now().isoformat(),
            'lastUpdate': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"获取仪表板统计数据时出错: {e}")
        return jsonify({
            'error': '获取数据失败',
            'portMappings': {'total': 0, 'active': 0, 'tcp': 0, 'udp': 0, 'commonPorts': 0},
            'domainMappings': {'total': 0, 'active': 0, 'aRecords': 0, 'cnameRecords': 0, 'enabled': 0},
            'vmStats': {'total': 0, 'active': 0},
            'pmStats': {'total': 0},
            'nsStats': {'total': 0, 'active': 0},
            'trends': {'labels': [], 'portMappings': [], 'domainMappings': []},
            'recentActivity': [],
            'lastSync': datetime.now().isoformat(),
            'lastUpdate': datetime.now().isoformat()
        })

@dashboard_bp.route('/api/dashboard/vm-resource-stats')
@cache.cached(timeout=300, key_prefix=lambda: cache_manager.get_full_key('DASHBOARD_VM_RESOURCE'))
def vm_resource_stats():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT `主机IP`, COUNT(*) as vm_count
                FROM assets 
                WHERE `主机IP` IS NOT NULL AND `主机IP` != ''
                GROUP BY `主机IP`
                ORDER BY vm_count DESC
            """)
            
            host_stats = {}
            for row in cursor.fetchall():
                host_ip = row['主机IP']
                count = row['vm_count']
                host_stats[host_ip] = count
                
        connection.close()
        
        return jsonify({
            'success': True,
            'hostStats': host_stats,
            'totalHosts': len(host_stats),
            'totalVMs': sum(host_stats.values())
        })
        
    except Exception as e:
        print(f"获取虚拟机资源统计数据时出错: {e}")
        return jsonify({
            'success': False,
            'message': str(e),
            'hostStats': {},
            'totalHosts': 0,
            'totalVMs': 0
        })

@dashboard_bp.route('/api/dashboard/vm-department-stats')
@cache.cached(timeout=300, key_prefix=lambda: cache_manager.get_full_key('DASHBOARD_VM_DEPARTMENT'))
def vm_department_stats():
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 部门, COUNT(*) as vm_count
                FROM assets 
                WHERE 部门 IS NOT NULL AND 部门 != ''
                GROUP BY 部门
                ORDER BY vm_count DESC
            """)
            
            department_stats = {}
            for row in cursor.fetchall():
                department = row['部门']
                count = row['vm_count']
                department_stats[department] = count
                
        connection.close()
        
        return jsonify({
            'success': True,
            'departmentStats': department_stats,
            'totalDepartments': len(department_stats),
            'totalVMs': sum(department_stats.values())
        })
        
    except Exception as e:
        print(f"获取虚拟机部门统计数据时出错: {e}")
        return jsonify({
            'success': False,
            'message': str(e),
            'departmentStats': {},
            'totalDepartments': 0,
            'totalVMs': 0
        })
