from Crypto.Cipher import AES
import hashlib
from config import SECRET_KEY


def pad(s):
    return s + (16 - len(s) % 16) * chr(16 - len(s) % 16)  # PKCS7 padding

def unpad(s):
    return s[:-ord(s[-1])]  # Убираем padding

def encrypt_data(queue_id, creator_id):
    data = f"{queue_id}:{creator_id}"
    cipher = AES.new(SECRET_KEY, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(data).encode())
    return encrypted.hex()[:32]  # Обрезаем до 32 символов

def decrypt_data(encrypted_data):
    encrypted_data = bytes.fromhex(encrypted_data)  # Восстанавливаем hex-данные
    cipher = AES.new(SECRET_KEY, AES.MODE_ECB)
    decrypted = unpad(cipher.decrypt(encrypted_data).decode())
    queue_id, creator_id = decrypted.split(":")
    return int(queue_id), int(creator_id)