"""Dump the HTML tables of a saved FAO-56 page as rows of cell text.

Usage: python3 -I tools/fao56_html_tables.py PAGE.htm TABLE_TITLE_PREFIX
Reads a page saved from https://www.fao.org/3/x0490e/ and prints the first
table whose preceding text starts with TABLE_TITLE_PREFIX (e.g. "TABLE 11").
"""

import html
import re
import sys
from html.parser import HTMLParser


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.in_cell = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.in_cell, self.cell = True, []
            span = dict(attrs).get("colspan")
            self.colspan = int(span) if span and span.isdigit() else 1
        elif tag == "br" and self.in_cell:
            self.cell.append(" ")
        elif tag == "sup" and self.in_cell:
            self.cell.append("[^")   # footnote markers kept apart from numbers

    def handle_endtag(self, tag):
        if tag == "sup" and self.in_cell:
            self.cell.append("]")
            return
        if tag in ("td", "th") and self.row is not None:
            text = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            self.row.append(text)
            self.row.extend([""] * (self.colspan - 1))
            self.in_cell = False
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)


def table_rows(page_html, title):
    start = page_html.find(title)
    if start < 0:
        raise SystemExit("title not found: " + title)
    lower = page_html.lower()
    t0 = lower.find("<table", start)
    t1 = lower.find("</table>", t0)
    p = TableParser()
    p.feed(html.unescape(page_html[t0:t1 + 8]))
    return p.rows


if __name__ == "__main__":
    with open(sys.argv[1], encoding="latin-1") as fh:
        for r in table_rows(fh.read(), sys.argv[2]):
            print(" | ".join(r))
