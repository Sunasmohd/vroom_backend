import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from core.models import User
from vroom_backend import settings

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"

def decode_jwt(token):
    """Decodes and verifies a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("user_id")
    except jwt.ExpiredSignatureError:
        
        return None  # Token has expired
    except jwt.InvalidTokenError:
        
        return None
class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')

        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]
        user_id = decode_jwt(token)

        if not user_id:
            raise AuthenticationFailed('Invalid or expired token')

        try:
            user = User.objects.get(id=user_id)
            return (user, token)
        except User.DoesNotExist:
            raise AuthenticationFailed('User not found')

    def authenticate_header(self, request):
        return 'Bearer'