from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """
    Custom pagination class that supports dynamic page sizes from client requests.

    This fixes the issue where frontend requests with page_size parameter
    were being ignored due to the default PageNumberPagination not supporting
    dynamic page sizes.
    """

    page_size = 5  # Default page size for tests
    page_size_query_param = "page_size"  # Allow client to override page size
    max_page_size = 100  # Maximum allowed page size for tests
