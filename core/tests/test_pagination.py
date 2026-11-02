from core.pagination import CustomPagination


class TestCustomPagination:
    def test_custom_pagination_defaults(self):
        p = CustomPagination()
        assert p.page_size == 10
        assert p.page_size_query_param == "page_size"
        assert p.max_page_size == 100

    def test_custom_pagination_page_size_query_param(self):
        p = CustomPagination()

        # Verify the query param name is correct
        assert p.page_size_query_param == "page_size"

        # This allows clients to request different page sizes via ?page_size=20

    def test_custom_pagination_max_page_size_limit(self):
        p = CustomPagination()

        # Verify max_page_size prevents abuse
        assert p.max_page_size == 100
