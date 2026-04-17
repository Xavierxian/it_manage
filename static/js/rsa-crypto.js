// RSA 加密实现
class RSACrypto {
    constructor() {
        this.publicKey = null;
    }

    // 设置公钥
    setPublicKey(publicKeyPem) {
        this.publicKey = publicKeyPem;
    }

    // 使用公钥加密密码
    encryptPassword(password) {
        if (!this.publicKey) {
            throw new Error('公钥未设置');
        }

        // 使用 Web Crypto API 进行 RSA 加密
        return this.encryptWithWebCrypto(password);
    }

    // 使用 Web Crypto API 加密
    async encryptWithWebCrypto(password) {
        try {
            // 将 PEM 格式的公钥转换为 ArrayBuffer
            const publicKeyPem = this.publicKey
                .replace('-----BEGIN PUBLIC KEY-----', '')
                .replace('-----END PUBLIC KEY-----', '')
                .replace(/\s/g, '');
            
            const publicKeyBinary = this.base64ToArrayBuffer(publicKeyPem);
            
            // 导入公钥
            const crypto = window.crypto || window.msCrypto;
            const publicKey = await crypto.subtle.importKey(
                'spki',
                publicKeyBinary,
                {
                    name: 'RSA-OAEP',
                    hash: 'SHA-256'
                },
                false,
                ['encrypt']
            );

            // 加密密码
            const encodedPassword = new TextEncoder().encode(password);
            const encrypted = await crypto.subtle.encrypt(
                {
                    name: 'RSA-OAEP'
                },
                publicKey,
                encodedPassword
            );

            // 转换为 Base64
            return this.arrayBufferToBase64(encrypted);
        } catch (error) {
            console.error('加密失败:', error);
            throw error;
        }
    }

    // Base64 转 ArrayBuffer
    base64ToArrayBuffer(base64) {
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return bytes.buffer;
    }

    // ArrayBuffer 转 Base64
    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }
}

// 全局 RSA 加密实例
const rsaCrypto = new RSACrypto();