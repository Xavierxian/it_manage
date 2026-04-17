import requests
import time

PROM_URL = "http://192.168.145.23:9090"

QUERIES = {
    "systemTcpNum": ("TCP", 'avg by(instance) (systemTcpNum)'),
    "numCpu": ("CPU", 'avg by(instance) (numCpu or windows_cs_logical_processors)'),
    "numMem": ("MEM", 'avg by(instance) (numMem / 1024 or windows_cs_physical_memory_bytes / 1073741824)'),
    "numDisk": ("DISK", 'avg by(instance) (numDisk or windows_logical_disk_size_bytes{volume="C:"} / 1073741824)'),
    "systemUptime_days": ("UPTIME", 'systemUptime/60/24 or (time() - windows_system_system_up_time) / 86400'),
    "nodeCpuPer": ("CPU%", 'avg by(instance) (nodeCpuPer or (1-(sum(increase(windows_cpu_time_total{mode="idle"}[5m])) by(instance))/(sum(increase(windows_cpu_time_total[5m])) by(instance)))*100)'),
    "nodememPer": ("MEM%", 'avg by(instance) (nodememPer or (windows_cs_physical_memory_bytes - windows_os_physical_memory_free_bytes) / windows_cs_physical_memory_bytes * 100)'),
    "disk_root": ("ROOT%", 'avg by(instance) (diskNodePer{mountpoint="/"} or 100 - (windows_logical_disk_free_bytes{volume="C:"}/windows_logical_disk_size_bytes{volume="C:"})*100)'),
    "disk_data": ("DATA%", 'avg by(instance) (diskNodePer{mountpoint="/data"})'),
    "disk_home": ("HOME%", 'avg by(instance) (diskNodePer{mountpoint="/home"})'),
    "disk_mapper": ("XS%", 'avg by(instance) (diskNodePer{device=~"/dev/mapper/XS.*"})'),
    "nodeloadPer": ("LOAD", 'avg by(instance) (nodeloadPer)'),
    "firewalldStatus": ("FW", 'avg by(instance) (firewalldStatus)')
}

def query_prometheus(query, retries=3, timeout=30):
    """
    向Prometheus服务器发送查询请求，带重试机制
    """
    url = f"{PROM_URL}/api/v1/query"
    
    for attempt in range(retries):
        try:
            resp = requests.get(url, params={"query": query}, timeout=timeout)
            return resp.json()
        except requests.exceptions.Timeout:
            print(f"查询Prometheus超时 (尝试 {attempt + 1}/{retries}): {query[:100]}...")
            if attempt == retries - 1:
                return {"status": "error", "error": "连接超时"}
            time.sleep(2 ** attempt)
        except requests.exceptions.ConnectionError:
            print(f"无法连接到Prometheus服务器 (尝试 {attempt + 1}/{retries}): {query[:100]}...")
            if attempt == retries - 1:
                return {"status": "error", "error": "无法连接到监控服务器"}
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"查询Prometheus时出错 (尝试 {attempt + 1}/{retries}): {e}")
            if attempt == retries - 1:
                return {"status": "error", "error": str(e)}
            time.sleep(1)
    
    return {"status": "error", "error": "重试次数已用完"}

def query_prometheus_range(query, start, end, step, retries=3, timeout=30):
    """
    向Prometheus服务器发送时间范围查询请求，带重试机制
    """
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
            print(f"查询Prometheus时间范围超时 (尝试 {attempt + 1}/{retries}): {query[:100]}...")
            if attempt == retries - 1:
                return {"status": "error", "error": "连接超时"}
            time.sleep(2 ** attempt)
        except requests.exceptions.ConnectionError:
            print(f"无法连接到Prometheus服务器 (尝试 {attempt + 1}/{retries}): {query[:100]}...")
            if attempt == retries - 1:
                return {"status": "error", "error": "无法连接到监控服务器"}
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"查询Prometheus时间范围时出错 (尝试 {attempt + 1}/{retries}): {e}")
            if attempt == retries - 1:
                return {"status": "error", "error": str(e)}
            time.sleep(1)
    
    return {"status": "error", "error": "重试次数已用完"}

def get_all_metrics(get_db_connection):
    """
    获取所有指标数据，并添加使用人信息
    """
    print("get_all_metrics 函数开始执行")
    results = {}
    
    for key, (label, q) in QUERIES.items():
        print(f"正在查询 {key} ({label}): {q[:100]}...")
        data = query_prometheus(q)
        print(f"{key} 查询结果: {data.get('status', 'unknown')}")
        
        if data["status"] == "success":
            result_count = len(data.get("data", {}).get("result", []))
            print(f"{key} 返回 {result_count} 个实例")
            
            for r in data["data"]["result"]:
                instance = r["metric"].get("instance", "unknown")
                value = float(r["value"][1])
                if instance not in results:
                    results[instance] = {}
                results[instance][label] = value
        else:
            print(f"{key} 查询失败: {data.get('error', '未知错误')}")
    
    print(f"初始收集完成，获取到 {len(results)} 个实例")
    
    try:
        windows_query = 'windows_cs_logical_processors'
        windows_data = query_prometheus(windows_query)
        windows_instances = set()
        if windows_data["status"] == "success":
            for r in windows_data["data"]["result"]:
                instance = r["metric"].get("instance", "unknown")
                windows_instances.add(instance)
        
        linux_query = 'numCpu'
        linux_data = query_prometheus(linux_query)
        linux_instances = set()
        if linux_data["status"] == "success":
            for r in linux_data["data"]["result"]:
                instance = r["metric"].get("instance", "unknown")
                linux_instances.add(instance)
        
        for instance in results:
            if instance in windows_instances:
                results[instance]['系统类型'] = 'Windows'
            elif instance in linux_instances:
                results[instance]['系统类型'] = 'Linux'
            else:
                results[instance]['系统类型'] = '未知'
                
    except Exception as e:
        print(f"检测系统类型时出错: {e}")
        for instance in results:
            results[instance]['系统类型'] = '未知'
    
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            ip_to_user = {}
            
            cursor.execute("""
                SELECT DISTINCT 虚拟机IP, 申请人 
                FROM assets 
                WHERE 虚拟机IP IS NOT NULL AND 虚拟机IP != '' AND 申请人 IS NOT NULL AND 申请人 != ''
            """)
            vm_users = cursor.fetchall()
            for row in vm_users:
                ip = row['虚拟机IP']
                user = row['申请人']
                if ip and user:
                    ip_to_user[ip] = user
            
            cursor.execute("""
                SELECT DISTINCT 服务器IP 
                FROM xenserver 
                WHERE 服务器IP IS NOT NULL AND 服务器IP != ''
            """)
            pm_ips = cursor.fetchall()
            for row in pm_ips:
                ip = row['服务器IP']
                if ip:
                    ip_to_user[ip] = "鲜鑫"
            
            for instance in results:
                user_info = "未知"
                if instance in ip_to_user:
                    user_info = ip_to_user[instance]
                else:
                    ip_part = instance.split(':')[0] if ':' in instance else instance
                    if ip_part in ip_to_user:
                        user_info = ip_to_user[ip_part]
                
                ip_to_check = instance.split(':')[0] if ':' in instance else instance
                
                if ip_to_check.startswith('10.'):
                    user_info = "李希哲"
                elif ip_to_check in [row['服务器IP'] for row in pm_ips if row['服务器IP']]:
                    user_info = "鲜鑫"
                
                results[instance]['使用人'] = user_info
        
        connection.close()
    except Exception as e:
        print(f"获取使用人信息时出错: {e}")
        for instance in results:
            results[instance]['使用人'] = "未知"
    
    metrics = [v[0] for v in QUERIES.values()]
    metrics.insert(1, '使用人')
    metrics.insert(2, '系统类型')
    
    print(f"get_all_metrics 函数完成，返回 {len(results)} 个实例，{len(metrics)} 个指标")
    print(f"指标列表: {metrics}")
    print(f"实例示例: {list(results.keys())[:3] if results else '无数据'}")
    
    return results, metrics
