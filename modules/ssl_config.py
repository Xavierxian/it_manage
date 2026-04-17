import os
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

def configure_ssl(app: Flask):
    """配置SSL/TLS支持"""
    
    ssl_enabled = os.getenv('SSL_ENABLED', 'false').lower() == 'true'
    
    if ssl_enabled:
        ssl_cert = os.getenv('SSL_CERT_PATH')
        ssl_key = os.getenv('SSL_KEY_PATH')
        
        if not ssl_cert or not ssl_key:
            raise ValueError("SSL_ENABLED is true but SSL_CERT_PATH or SSL_KEY_PATH is not set")
        
        if not os.path.exists(ssl_cert):
            raise FileNotFoundError(f"SSL certificate not found at {ssl_cert}")
        
        if not os.path.exists(ssl_key):
            raise FileNotFoundError(f"SSL key not found at {ssl_key}")
        
        app.config['SSL_CONTEXT'] = (ssl_cert, ssl_key)
        app.config['PREFERRED_URL_SCHEME'] = 'https'
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['FORCE_HTTPS'] = True
        
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
        
        print("SSL/TLS已启用")
    else:
        print("警告: SSL/TLS未启用，建议在生产环境中启用HTTPS")
        print("要启用HTTPS，请设置以下环境变量:")
        print("  SSL_ENABLED=true")
        print("  SSL_CERT_PATH=/path/to/cert.pem")
        print("  SSL_KEY_PATH=/path/to/key.pem")
    
    return app

def generate_self_signed_cert(output_dir='./ssl'):
    """生成自签名SSL证书（仅用于开发环境）"""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime
        
        os.makedirs(output_dir, exist_ok=True)
        
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Beijing"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Beijing"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IT Management Platform"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress("127.0.0.1"),
            ]),
            critical=False,
        ).sign(key, hashes.SHA256(), default_backend())
        
        cert_path = os.path.join(output_dir, 'cert.pem')
        key_path = os.path.join(output_dir, 'key.pem')
        
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        print(f"自签名证书已生成:")
        print(f"  证书: {cert_path}")
        print(f"  私钥: {key_path}")
        print(f"警告: 自签名证书仅用于开发环境，不要在生产环境中使用!")
        
        return cert_path, key_path
        
    except ImportError:
        print("错误: 需要安装cryptography库来生成自签名证书")
        print("请运行: pip install cryptography")
        return None, None
    except Exception as e:
        print(f"生成自签名证书时出错: {e}")
        return None, None
