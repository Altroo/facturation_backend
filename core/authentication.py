"""Custom authentication classes for handling JWT token-based authentication."""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import exceptions


class JWTQueryParamAuthentication(JWTAuthentication):
    """
    JWT Authentication class that supports token authentication via query parameter.
    This is useful for PDF endpoints that need to be opened in a new browser tab.
    
    The token can be provided either:
    - In the Authorization header (standard): Authorization: Bearer <token>
    - As a query parameter: ?token=<token>
    """
    
    def authenticate(self, request):
        # First try standard header authentication
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                validated_token = self.get_validated_token(raw_token)
                return self.get_user(validated_token), validated_token
        
        # If header auth failed, try query parameter
        raw_token = request.query_params.get('token')
        if raw_token:
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        
        return None
