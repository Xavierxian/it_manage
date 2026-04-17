import os
import base64
import json
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
# 当前选区为空，无需重写

class PasswordCrypto:
    def __init__(self, key_file='./crypto_keys.json'):
        self.private_key = None
        self.public_key = None
        self.key_size = 2048
        self.key_file = key_file
        self.load_or_generate_keys()
        
    def load_or_generate_keys(self):
        """加载或生成RSA密钥对"""
        try:
            if os.path.exists(self.key_file):
                # 尝试加载现有密钥
                with open(self.key_file, 'r') as f:
                    keys = json.load(f)
                    
                # 加载私钥
                self.private_key = serialization.load_pem_private_key(
                    keys['private_key'].encode('utf-8'),
                    password=None
                )
                
                # 加载公钥
                self.public_key = serialization.load_pem_public_key(
                    keys['public_key'].encode('utf-8')
                )
            else:
                # 生成新密钥对
                self.generate_key_pair()
                self.save_keys()
        except Exception as e:
            print(f"加载密钥失败，生成新密钥: {e}")
            self.generate_key_pair()
            self.save_keys()
        
    def generate_key_pair(self):
        """生成RSA密钥对"""
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.key_size
        )
        self.public_key = self.private_key.public_key()
        
    def save_keys(self):
        """保存密钥到文件"""
        try:
            # 获取PEM格式的密钥
            private_pem = self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')
            
            public_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')
            
            # 保存到文件
            with open(self.key_file, 'w') as f:
                json.dump({
                    'private_key': private_pem,
                    'public_key': public_pem
                }, f)
                
            print(f"RSA密钥对已保存到 {self.key_file}")
        except Exception as e:
            print(f"保存密钥失败: {e}")
        
    def get_public_key_pem(self):
        """获取公钥PEM格式"""
        if not self.public_key:
            self.load_or_generate_keys()
        
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
    
    def encrypt_password(self, password, public_key_pem):
        """使用公钥加密密码"""
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode('utf-8')
        )
        
        encrypted = public_key.encrypt(
            password.encode('utf-8'),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return base64.b64encode(encrypted).decode('utf-8')
    
    def decrypt_password(self, encrypted_password):
        """使用私钥解密密码"""
        if not self.private_key:
            raise ValueError("私钥未初始化")
            
        encrypted_bytes = base64.b64decode(encrypted_password)
        
        decrypted = self.private_key.decrypt(
            encrypted_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return decrypted.decode('utf-8')

# 全局实例
password_crypto = PasswordCrypto()