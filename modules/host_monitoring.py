from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from .auth import permission_required
from .database import get_db_connection
from .email_notifier import email_notifier
from datetime import datetime
import requests
import time
import pymysql

PROM_URL = "http://192.168.145.23:9090"

QUERIES = {
    "systemTcpNum": ("TCP", 'avg by(instance) (node_netstat_Tcp_CurrEstab)'),
    "numCpu": ("CPU", 'count by (instance) (node_cpu_seconds_total{mode="idle"})'),
    "numMem": ("MEM", 'avg by(instance) (node_memory_MemTotal_bytes{instance!~"xenenterprise.*"} / 1073741824 or numMem{instance=~"xenenterprise.*"} / 1024)'),
    "numDisk": ("DISK", 'sum by(instance) (node_filesystem_size_bytes{fstype!~"tmpfs|squashfs|overlay", instance!~"xenenterprise.*"} / 1073741824 or numDisk{instance=~"xenenterprise.*"} / 1024)'),
    "systemUptime_days": ("UPTIME", 'sum by (instance) ((time() - node_boot_time_seconds) / 86400)'),
    "nodeCpuPer": ("CPU%", '100 * (1 - avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])))'),
    "nodememPer": ("MEM%", '(sum by (instance) (100 * (1 - (node_memory_MemAvailable_bytes{instance!~"xenenterprise.*"} / on(instance) node_memory_MemTotal_bytes{instance!~"xenenterprise.*"})))) or (avg by (instance) (nodememPer{instance=~"xenenterprise.*"}))'),
    "disk_root": ("ROOT%", 'avg by (instance) (100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}))'),
    "disk_data": ("DATA%", 'avg by (instance) (100 * (1 - node_filesystem_avail_bytes{mountpoint="/data"} / node_filesystem_size_bytes{mountpoint="/data"}))'),
    "disk_home": ("HOME%", 'avg by (instance) (100 * (1 - node_filesystem_avail_bytes{mountpoint="/home"} / node_filesystem_size_bytes{mountpoint="/home"}))'),
    "disk_mapper": ("XS%", 'avg by(instance) (100 * (1 - node_filesystem_avail_bytes{device=~"/dev/mapper/XS.*"} / node_filesystem_size_bytes{device=~"/dev/mapper/XSLocalEXT.*"}))'),
    "nodeloadPer": ("IO%", 'avg by (instance, device) (rate(node_disk_io_time_seconds_total{device!~"loop.*|ram.*"}[5m])) * 100'),
    "firewalldStatus": ("流量", 'sum by (instance) (rate(node_network_transmit_bytes_total{device!~"lo|docker.*|veth.*|cni.*"}[5m]) + rate(node_network_receive_bytes_total{device!~"lo|docker.*|veth.*|cni.*"}[5m])) / 1024 / 1024')
}

host_monitoring_bp = Blueprint('host_monitoring', __name__)

@host_monitoring_bp.route('/host_monitoring')
@login_required
@permission_required('host_monitoring')
def host_monitoring():
    results, metrics = get_all_metrics()
    return render_template('host_monitoring.html', results=results, metrics=metrics)

@host_monitoring_bp.route('/api/host-monitoring-data')
@login_required
@permission_required('host_monitoring')
def get_host_monitoring_data():
    try:
        results, metrics = get_all_metrics()
        return jsonify({
            'success': True,
            'results': results,
            'metrics': metrics,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取主机监控数据失败: {str(e)}',
            'results': {},
            'metrics': []
        })

@host_monitoring_bp.route('/api/host-alerts')
@login_required
@permission_required('host_monitoring')
def get_host_alerts():
    try:
        results, metrics = get_all_metrics()
        alerts = []
        threshold = 90
        
        for instance, data in results.items():
            ip = instance.split('-')[-1] if '-' in instance else instance
            host_alerts = {
                'instance': instance,
                'ip': ip,
                'system_type': data.get('系统类型', '未知'),
                'user': data.get('使用人', '未知'),
                'department': data.get('部门', '未知'),
                'alerts': []
            }
            
            if 'ROOT%' in data and data['ROOT%'] >= threshold:
                host_alerts['alerts'].append({
                    'type': 'ROOT分区',
                    'value': data['ROOT%'],
                    'threshold': threshold
                })
            
            if 'DATA%' in data and data['DATA%'] >= threshold:
                host_alerts['alerts'].append({
                    'type': 'DATA分区',
                    'value': data['DATA%'],
                    'threshold': threshold
                })
            
            if 'HOME%' in data and data['HOME%'] >= threshold:
                host_alerts['alerts'].append({
                    'type': 'HOME分区',
                    'value': data['HOME%'],
                    'threshold': threshold
                })
            
            if host_alerts['alerts']:
                alerts.append(host_alerts)
        
        alerts.sort(key=lambda x: len(x['alerts']), reverse=True)
        
        return jsonify({
            'success': True,
            'alerts': alerts,
            'total_hosts': len(alerts),
            'total_alerts': sum(len(a['alerts']) for a in alerts),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'获取告警数据失败: {str(e)}',
            'alerts': [],
            'total_hosts': 0,
            'total_alerts': 0
        })

@host_monitoring_bp.route('/api/host-alerts/send-email', methods=['POST'])
@login_required
@permission_required('host_monitoring')
def send_alert_emails():
    try:
        data = request.get_json()
        selected_ips = data.get('ips', [])
        
        if not selected_ips:
            return jsonify({
                'success': False,
                'message': '请选择要发送邮件的主机'
            })
        
        results, metrics = get_all_metrics()
        alerts = []
        threshold = 90
        
        for instance, host_data in results.items():
            ip = instance.split('-')[-1] if '-' in instance else instance
            
            if ip not in selected_ips:
                continue
            
            host_alerts = {
                'ip': ip,
                'user': host_data.get('使用人', '未知'),
                'department': host_data.get('部门', '未知'),
                'alerts': []
            }
            
            if 'ROOT%' in host_data and host_data['ROOT%'] >= threshold:
                host_alerts['alerts'].append({
                    'type': 'ROOT分区',
                    'value': host_data['ROOT%'],
                    'threshold': threshold
                })
            
            if 'DATA%' in host_data and host_data['DATA%'] >= threshold:
                host_alerts['alerts'].append({
                    'type': 'DATA分区',
                    'value': host_data['DATA%'],
                    'threshold': threshold
                })
            
            if 'HOME%' in host_data and host_data['HOME%'] >= threshold:
                host_alerts['alerts'].append({
                    'type': 'HOME分区',
                    'value': host_data['HOME%'],
                    'threshold': threshold
                })
            
            if host_alerts['alerts']:
                alerts.append(host_alerts)
        
        if not alerts:
            return jsonify({
                'success': False,
                'message': '所选主机当前没有告警'
            })
        
        connection = get_db_connection()
        try:
            with connection.cursor() as cursor:
                for alert in alerts:
                    ip = alert['ip']
                    cursor.execute(
                        "SELECT 申请人 FROM assets WHERE 虚拟机IP = %s AND 是否在用 = '是'",
                        (ip,)
                    )
                    asset = cursor.fetchone()
                    
                    if asset and asset['申请人']:
                        alert['user'] = asset['申请人'] or alert['user']
                        cursor.execute(
                            "SELECT email FROM BS_DD_USER_BS WHERE `name` = %s",
                            (alert['user'],)
                        )
                        user_info = cursor.fetchone()
                        alert['email'] = user_info['email'] if user_info else None
                    else:
                        alert['email'] = None
        finally:
            connection.close()
        
        alerts_with_email = [a for a in alerts if a.get('email')]
        
        if not alerts_with_email:
            return jsonify({
                'success': False,
                'message': '所选主机未配置对接人邮箱，无法发送邮件'
            })
        
        result = email_notifier.send_alerts_by_user(alerts_with_email)
        
        return jsonify({
            'success': result['success'],
            'message': f'成功发送 {result["success_count"]} 封邮件，失败 {result["fail_count"]} 封',
            'total': result['total'],
            'success_count': result['success_count'],
            'fail_count': result['fail_count']
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'发送邮件失败: {str(e)}'
        })

@host_monitoring_bp.route('/api/host-metrics/<path:ip>')
@login_required
@permission_required('host_monitoring')
def get_host_metrics(ip):
    try:
        time_range = request.args.get('range', '1h')
        
        time_configs = {
            '5m': {'seconds': 300, 'step': 15, 'label': '最近5分钟'},
            '1h': {'seconds': 3600, 'step': 60, 'label': '过去1小时'},
            '3h': {'seconds': 10800, 'step': 60, 'label': '过去3小时'},
            '6h': {'seconds': 21600, 'step': 60, 'label': '过去6小时'}
        }
        
        config = time_configs.get(time_range, time_configs['1h'])
        
        end = int(time.time())
        start = end - config['seconds']
        step = config['step']
        
        linux_prefixes = ['centos', 'ubuntu', 'xenenterprise']
        os_type = 'windows'
        for prefix in linux_prefixes:
            if ip.startswith(prefix):
                os_type = 'linux'
                break
        
        queries = {
            "linux": {
                "cpu": ("CPU使用率-Linux", f'(1 - avg by(instance) (rate(node_cpu_seconds_total{{mode="idle",instance="{ip}"}}[1m]))) * 100'),
                "mem": ("内存使用率-Linux", f'(1 - (node_memory_MemAvailable_bytes{{instance="{ip}"}} / node_memory_MemTotal_bytes{{instance="{ip}"}})) * 100'),
                "disk": ("磁盘使用率-Linux", f'(1 - node_filesystem_avail_bytes{{mountpoint="/",instance="{ip}"}} / node_filesystem_size_bytes{{mountpoint="/",instance="{ip}"}}) * 100')
            },
            "windows": {
                "cpu": ("CPU使用率-Windows",
                        f'(1 - (sum(increase(windows_cpu_time_total{{mode="idle",instance="{ip}"}}[5m])) by(instance) / sum(increase(windows_cpu_time_total{{instance="{ip}"}}[5m])) by(instance))) * 100'),
                "mem": ("内存使用率-Windows",
                        f'((windows_cs_physical_memory_bytes{{instance="{ip}"}} - windows_os_physical_memory_free_bytes{{instance="{ip}"}}) / windows_cs_physical_memory_bytes{{instance="{ip}"}} * 100)'),
                "disk": ("C盘使用率-Windows",
                         f'(100 - (windows_logical_disk_free_bytes{{volume="C:",instance="{ip}"}} / windows_logical_disk_size_bytes{{volume="C:",instance="{ip}"}}) * 100)')
            }
        }
        
        query_config = queries[os_type]
        results = {}
        timestamps = []
        
        first_successful_query = None
        
        for key, (label, query) in query_config.items():
            data = query_prometheus_range(query, start, end, step)
            
            if data.get("status") == "success" and data.get("data", {}).get("result"):
                result_data = data["data"]["result"]
                if result_data:
                    for result in result_data:
                        if "values" in result and result["values"]:
                            series = []
                            times = []
                            
                            for ts, value in result["values"]:
                                ts_fmt = time.strftime("%H:%M", time.localtime(float(ts)))
                                try:
                                    val = float(value)
                                except (ValueError, TypeError):
                                    val = None
                                series.append(val)
                                times.append(ts_fmt)
                            
                            results[key] = {"label": label, "data": series}
                            
                            if not timestamps:
                                timestamps = times
                                first_successful_query = key
            else:
                pass
        
        if not results:
            return jsonify({
                'success': False,
                'message': f'未能获取到主机 {ip} 的监控数据，请检查该主机是否在线或监控配置是否正确',
                'ip': ip,
                'results': {},
                'timestamps': []
            })
        
        return jsonify({
            'success': True,
            'ip': ip,
            'os_type': os_type,
            'results': results,
            'timestamps': timestamps,
            'title': f'主机 {ip} ({os_type.upper()}) {config["label"]}资源走势'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'获取监控数据失败: {str(e)}',
            'ip': ip,
            'results': {},
            'timestamps': []
        })

@host_monitoring_bp.route('/api/pushgateway/status')
@login_required
def get_pushgateway_status():
    try:
        url = f"{PROM_URL}/api/v1/targets"
        resp = requests.get(url, timeout=30)
        data = resp.json()
        
        if data["status"] == "success":
            active_targets = data["data"]["activeTargets"]
            targets_info = []
            
            for target in active_targets:
                targets_info.append({
                    'endpoint': target["scrapeUrl"],
                    'health': target["health"].lower()
                })
            
            return jsonify({
                'success': True,
                'targets': targets_info,
                'total': len(targets_info),
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Prometheus API调用失败: {data.get("error", "未知错误")}',
                'targets': []
            })
            
    except requests.exceptions.Timeout:
        return jsonify({
            'success': False,
            'message': '连接Prometheus服务器超时',
            'targets': []
        })
    except requests.exceptions.ConnectionError:
        return jsonify({
            'success': False,
            'message': '无法连接到Prometheus服务器',
            'targets': []
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取PushGateway状态失败: {str(e)}',
            'targets': []
        })

def query_prometheus(query, retries=3, timeout=30):
    url = f"{PROM_URL}/api/v1/query"
    
    for attempt in range(retries):
        try:
            resp = requests.get(url, params={"query": query}, timeout=timeout)
            return resp.json()
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return {"status": "error", "error": "连接超时"}
            time.sleep(2 ** attempt)
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                return {"status": "error", "error": "无法连接到监控服务器"}
            time.sleep(2 ** attempt)
        except Exception as e:
            if attempt == retries - 1:
                return {"status": "error", "error": str(e)}
            time.sleep(1)
    
    return {"status": "error", "error": "重试次数已用完"}

def query_prometheus_range(query, start, end, step, retries=3, timeout=30):
    url = f"{PROM_URL}/api/v1/query_range"
    
    for attempt in range(retries):
        try:
            resp = requests.get(url, params={
                "query": query,
                "start": start,
                "end": end,
                "step": step
            }, timeout=timeout)
            return resp.json()
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                return {"status": "error", "error": "连接超时"}
            time.sleep(2 ** attempt)
        except requests.exceptions.ConnectionError:
            if attempt == retries - 1:
                return {"status": "error", "error": "无法连接到监控服务器"}
            time.sleep(2 ** attempt)
        except Exception as e:
            if attempt == retries - 1:
                return {"status": "error", "error": str(e)}
            time.sleep(1)
    
    return {"status": "error", "error": "重试次数已用完"}

def get_all_metrics():
    results = {}
    
    for key, (label, q) in QUERIES.items():
        data = query_prometheus(q)
        
        if data["status"] == "success":
            result_count = len(data.get("data", {}).get("result", []))
            
            for r in data["data"]["result"]:
                instance = r["metric"].get("instance", "unknown")
                value = float(r["value"][1])
                if instance not in results:
                    results[instance] = {}
                results[instance][label] = value
        else:
            pass
    
    try:
        linux_prefixes = ['centos', 'ubuntu', 'xenenterprise']
        
        for instance in results:
            os_type = 'Windows'
            for prefix in linux_prefixes:
                if instance.startswith(prefix):
                    os_type = 'Linux'
                    break
            results[instance]["系统类型"] = os_type
    except Exception as e:
        pass
    
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 虚拟机IP, 申请人, 部门 FROM assets WHERE 是否在用 = '是'")
            asset_records = cursor.fetchall()
            
            ip_to_user = {}
            for asset in asset_records:
                ip = asset['虚拟机IP']
                user = asset['申请人']
                department = asset['部门']
                if ip not in ip_to_user:
                    ip_to_user[ip] = {'user': user, 'department': department}
        connection.close()
        
        for instance in results:
            ip = instance.split('-')[-1] if '-' in instance else instance
            if ip in ip_to_user:
                results[instance]["使用人"] = ip_to_user[ip]['user']
                results[instance]["部门"] = ip_to_user[ip]['department']
            else:
                results[instance]["使用人"] = "未知"
                results[instance]["部门"] = "未知"
    except Exception as e:
        for instance in results:
            if "使用人" not in results[instance]:
                results[instance]["使用人"] = "未知"
                results[instance]["部门"] = "未知"
    
    metrics = [label for label, q in QUERIES.values()]
    
    return results, metrics
