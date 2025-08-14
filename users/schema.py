"""
OpenAPI schema extensions for authentication
"""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class HybridAuthenticationScheme(OpenApiAuthenticationExtension):
    """Schema for HybridAuthentication"""

    target_class = "users.authentication.HybridAuthentication"
    name = "hybridAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "Token",
            "description": "Hybrid auth: Token (Authorization: Token ...) + optional X-Device-Token",
        }


class DeviceTokenAuthenticationScheme(OpenApiAuthenticationExtension):
    """Schema for DeviceTokenAuthentication"""

    target_class = "users.authentication.DeviceTokenAuthentication"
    name = "deviceToken"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "X-Device-Token",
            "description": "Device token header for mobile authentication",
        }
