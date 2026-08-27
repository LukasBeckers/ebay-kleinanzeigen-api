"""IP-block page vs genuine empty search."""

from scrapers.search_listings import is_ip_block_page


BAN_HTML = """
<!doctype html>
<html>
  <body>
    <div id="error">
      <h1>IP-Bereich vorübergehend gesperrt.</h1>
      <p>In deinem IP-Bereich kam es vor Kurzem mehrfach zu unsicheren Versuchen.</p>
    </div>
  </body>
</html>
"""

EMPTY_SEARCH_HTML = """
<!DOCTYPE html>
<html lang="de">
<body>
  <ul id="srchrslt-adtable"></ul>
</body>
</html>
"""


class TestIsIpBlockPage:
    def test_http_403_is_block(self):
        assert is_ip_block_page("<html></html>", 403) is True

    def test_ban_html_is_block_even_on_200(self):
        assert is_ip_block_page(BAN_HTML, 200) is True

    def test_empty_results_table_is_not_block(self):
        assert is_ip_block_page(EMPTY_SEARCH_HTML, 200) is False

    def test_normal_listing_html_is_not_block(self):
        html = '<ul id="srchrslt-adtable"><article data-adid="1"></article></ul>'
        assert is_ip_block_page(html, 200) is False
