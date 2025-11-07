from rest_framework.pagination import PageNumberPagination


class CompanyPagination(PageNumberPagination):
    # default size when the client does not specify one
    page_size = 10
    # allow the client to set the size with the `page_size` query param
    page_size_query_param = "page_size"
    # optional maximum to prevent abuse
    max_page_size = 100
