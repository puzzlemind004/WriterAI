"""
Chiffrement symétrique des données sensibles (clés API).
Utilise Fernet (AES-128-CBC + HMAC) de la lib cryptography.

La clé de chiffrement est lue depuis la variable d'environnement
WRITERAI_SECRET_KEY. Si absente, une clé temporaire est générée
et un avertissement est loggué (acceptable en dev, interdit en prod).
"""
import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    raw_key = os.environ.get("WRITERAI_SECRET_KEY")
    if raw_key:
        _fernet = Fernet(raw_key.encode())
    else:
        logger.warning(
            "WRITERAI_SECRET_KEY non définie — utilisation d'une clé temporaire. "
            "Les données chiffrées ne survivront pas au redémarrage. "
            "Définissez cette variable en production."
        )
        _fernet = Fernet(Fernet.generate_key())

    return _fernet


def encrypt(plaintext: str) -> str:
    """Chiffre une chaîne et retourne le token base64 sous forme de str."""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Déchiffre un token produit par encrypt(). Lève ValueError si invalide."""
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except Exception as e:
        raise ValueError(f"Impossible de déchiffrer la valeur : {e}") from e


def generate_secret_key() -> str:
    """Génère une nouvelle clé secrète à mettre dans WRITERAI_SECRET_KEY."""
    return Fernet.generate_key().decode()
