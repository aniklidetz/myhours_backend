# integrations tests package - conditional import
try:
    from .test_external_apis import *  # noqa: F401,F403
except ImportError:
    pass
