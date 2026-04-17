#!/usr/bin/env python3
"""
统一的缓存管理器
提供标准化的缓存键管理和实时刷新机制
"""

import redis
import os
from dotenv import load_dotenv
from functools import wraps
from flask import current_app
import json
import time
from datetime import datetime, date

# 加载环境变量
load_dotenv()

class DateTimeEncoder(json.JSONEncoder):
    """自定义 JSON 编码器，处理 datetime 对象"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

class CacheManager:
    """统一的缓存管理器"""
    
    # 缓存键前缀
    CACHE_PREFIX = 'it_manage_'
    
    # 缓存键定义
    CACHE_KEYS = {
        # 虚拟机相关
        'VM_LIST': 'api:assets:list',
        'VM_DETAIL': 'api:assets:detail:{}',
        'VM_STATS': 'api:assets:stats',
        'VM_HOST_STATS': 'api:assets:host_stats',
        'VM_DEPT_STATS': 'api:assets:dept_stats',
        
        # 实体机相关
        'PM_LIST': 'api:xenserver:list',
        'PM_DETAIL': 'api:xenserver:detail:{}',
        
        # NameSpace相关
        'NS_LIST': 'api:bseip:list',
        'NS_DETAIL': 'api:bseip:detail:{}',
        
        # 端口映射相关
        'PORT_LIST': 'api:port-mappings:list',
        'PORT_STATS': 'api:port-mappings:stats',
        
        # 域名映射相关
        'DOMAIN_LIST': 'api:domain-records:list',
        'DOMAIN_STATS': 'api:domain-records:stats',
        
        # 仪表板统计
        'DASHBOARD_STATS': 'api:dashboard:stats',
        'DASHBOARD_VM_RESOURCE': 'api:dashboard:vm-resource-stats',
        'DASHBOARD_VM_DEPARTMENT': 'api:dashboard:vm-department-stats',
        
        # 其他统计
        'RECENT_ACTIVITY': 'api:recent-activity',
        'TREND_DATA': 'api:trend-data'
    }
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            password=os.getenv('REDIS_PASSWORD'),
            db=int(os.getenv('REDIS_DB', 0)),
            decode_responses=True
        )
    
    def get_full_key(self, key_name, *args):
        """获取完整的缓存键名"""
        if key_name in self.CACHE_KEYS:
            key_template = self.CACHE_KEYS[key_name]
            if '{}' in key_template:
                return f"{self.CACHE_PREFIX}{key_template.format(*args)}"
            else:
                return f"{self.CACHE_PREFIX}{key_template}"
        return f"{self.CACHE_PREFIX}{key_name}"
    
    def clear_cache(self, key_name, *args):
        """清除指定缓存"""
        if key_name in self.CACHE_KEYS:
            key_template = self.CACHE_KEYS[key_name]
            if '{}' in key_template:
                pattern = f"{self.CACHE_PREFIX}{key_template.format('*')}"
            else:
                pattern = f"{self.CACHE_PREFIX}{key_template}"
        else:
            pattern = f"{self.CACHE_PREFIX}{key_name}"
        
        keys = self.redis_client.keys(pattern)
        if keys:
            self.redis_client.delete(*keys)
            print(f"已清除 {len(keys)} 个缓存键: {pattern}")
            return len(keys)
        return 0
    
    def clear_all_cache(self):
        """清除所有缓存"""
        keys = self.redis_client.keys(f"{self.CACHE_PREFIX}*")
        if keys:
            self.redis_client.delete(*keys)
            print(f"已清除 {len(keys)} 个缓存键")
            return len(keys)
        return 0
    
    def clear_related_cache(self, data_type):
        """清除与数据类型相关的所有缓存"""
        cleared_keys = 0
        
        if data_type == 'vm':
            cleared_keys += self.clear_cache('VM_LIST')
            cleared_keys += self.clear_cache('VM_STATS')
            cleared_keys += self.clear_cache('VM_HOST_STATS')
            cleared_keys += self.clear_cache('VM_DEPT_STATS')
            cleared_keys += self.clear_cache('DASHBOARD_STATS')
            cleared_keys += self.clear_cache('DASHBOARD_VM_RESOURCE')
            cleared_keys += self.clear_cache('DASHBOARD_VM_DEPARTMENT')
            
        elif data_type == 'pm':
            cleared_keys += self.clear_cache('PM_LIST')
            cleared_keys += self.clear_cache('DASHBOARD_STATS')
            
        elif data_type == 'ns':
            cleared_keys += self.clear_cache('NS_LIST')
            cleared_keys += self.clear_cache('DASHBOARD_STATS')
            
        elif data_type == 'port':
            cleared_keys += self.clear_cache('PORT_LIST')
            cleared_keys += self.clear_cache('PORT_STATS')
            cleared_keys += self.clear_cache('DASHBOARD_STATS')
            
        elif data_type == 'domain':
            cleared_keys += self.clear_cache('DOMAIN_LIST')
            cleared_keys += self.clear_cache('DOMAIN_STATS')
            cleared_keys += self.clear_cache('DASHBOARD_STATS')
            
        elif data_type == 'dashboard':
            cleared_keys += self.clear_cache('DASHBOARD_STATS')
            cleared_keys += self.clear_cache('DASHBOARD_VM_RESOURCE')
            cleared_keys += self.clear_cache('DASHBOARD_VM_DEPARTMENT')
            cleared_keys += self.clear_cache('RECENT_ACTIVITY')
            cleared_keys += self.clear_cache('TREND_DATA')
        
        return cleared_keys
    
    def get_cache_keys(self, pattern=None):
        """获取所有缓存键"""
        if pattern:
            keys = self.redis_client.keys(f"{self.CACHE_PREFIX}{pattern}")
        else:
            keys = self.redis_client.keys(f"{self.CACHE_PREFIX}*")
        
        result = []
        for key in sorted(keys):
            ttl = self.redis_client.ttl(key)
            size = self.redis_client.memory_usage(key) or 0
            result.append({
                'key': key,
                'ttl': ttl,
                'size': size,
                'human_size': self._format_bytes(size)
            })
        return result
    
    def get_cache_stats(self):
        """获取缓存统计信息"""
        try:
            info = self.redis_client.info()
            keys = self.get_cache_keys()
            
            total_size = sum(key['size'] for key in keys)
            
            return {
                'connection_status': '正常' if self.redis_client.ping() else '异常',
                'total_keys': len(keys),
                'total_size': total_size,
                'human_size': self._format_bytes(total_size),
                'memory_usage': info.get('used_memory_human', 'N/A'),
                'connected_clients': info.get('connected_clients', 'N/A'),
                'redis_version': info.get('redis_version', 'N/A'),
                'keys': keys
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _format_bytes(self, bytes_count):
        """格式化字节大小"""
        if bytes_count == 0:
            return "0 B"
        
        k = 1024
        sizes = ["B", "KB", "MB", "GB"]
        i = 0
        while bytes_count >= k and i < len(sizes) - 1:
            bytes_count /= k
            i += 1
        
        return f"{bytes_count:.2f} {sizes[i]}"
    
    def set_cache(self, key_name, value, timeout=300):
        """设置缓存值"""
        full_key = self.get_full_key(key_name)
        try:
            self.redis_client.setex(full_key, timeout, json.dumps(value, cls=DateTimeEncoder))
            return True
        except Exception as e:
            print(f"设置缓存失败: {e}")
            return False
    
    def get_cache(self, key_name, *args):
        """获取缓存值"""
        full_key = self.get_full_key(key_name, *args)
        try:
            value = self.redis_client.get(full_key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            print(f"获取缓存失败: {e}")
            return None

# 创建全局缓存管理器实例
cache_manager = CacheManager()

# 缓存装饰器
class CacheDecorator:
    """缓存装饰器类"""
    
    @staticmethod
    def cached(timeout=300):
        """缓存装饰器"""
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                # 生成缓存键
                cache_key = f"{CacheManager.CACHE_PREFIX}func:{f.__name__}:{hash(str(args) + str(kwargs))}"
                
                # 尝试从缓存获取
                cached_result = cache_manager.redis_client.get(cache_key)
                if cached_result:
                    return json.loads(cached_result)
                
                # 执行函数
                result = f(*args, **kwargs)
                
                # 缓存结果
                try:
                    cache_manager.redis_client.setex(cache_key, timeout, json.dumps(result, cls=DateTimeEncoder))
                except Exception as e:
                    print(f"缓存结果失败: {e}")
                
                return result
            
            # 添加清除缓存的方法
            wrapper.clear_cache = lambda: cache_manager.redis_client.delete(f"{CacheManager.CACHE_PREFIX}func:{f.__name__}:*")
            return wrapper
        return decorator

# 实用函数
def clear_vm_cache():
    """清除虚拟机相关缓存"""
    return cache_manager.clear_related_cache('vm')

def clear_pm_cache():
    """清除实体机相关缓存"""
    return cache_manager.clear_related_cache('pm')

def clear_ns_cache():
    """清除NameSpace相关缓存"""
    return cache_manager.clear_related_cache('ns')

def clear_port_cache():
    """清除端口映射相关缓存"""
    return cache_manager.clear_related_cache('port')

def clear_domain_cache():
    """清除域名映射相关缓存"""
    return cache_manager.clear_related_cache('domain')

def clear_dashboard_cache():
    """清除仪表板相关缓存"""
    return cache_manager.clear_related_cache('dashboard')

def clear_all_cache():
    """清除所有缓存"""
    return cache_manager.clear_all_cache()

def get_cache_info():
    """获取缓存信息"""
    return cache_manager.get_cache_stats()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "clear":
            count = clear_all_cache()
            print(f"已清除 {count} 个缓存键")
        elif command == "list":
            keys = cache_manager.get_cache_keys()
            if keys:
                print("当前缓存键:")
                for key_info in keys:
                    print(f"  {key_info['key']} (TTL: {key_info['ttl']}s, Size: {key_info['human_size']})")
            else:
                print("当前没有缓存")
        elif command == "stats":
            stats = get_cache_info()
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        elif command == "clear-type" and len(sys.argv) > 2:
            data_type = sys.argv[2]
            count = cache_manager.clear_related_cache(data_type)
            print(f"已清除 {count} 个 {data_type} 相关缓存键")
        else:
            print("用法:")
            print("  python cache_manager.py clear              - 清除所有缓存")
            print("  python cache_manager.py list               - 列出所有缓存键")
            print("  python cache_manager.py stats              - 显示缓存统计")
            print("  python cache_manager.py clear-type <type>  - 清除指定类型缓存")
            print("  支持类型: vm, pm, ns, port, domain, dashboard")
    else:
        stats = get_cache_info()
        print(json.dumps(stats, indent=2, ensure_ascii=False))