"""Material's right sidebar lists only the first H1's children, so the H1s that
`--8<--` pulls in from rules/ and skills/ would vanish from it; nest them under the page title."""


def on_page_content(html, page, **_):
    if len(page.toc.items) > 1:
        title, *included = page.toc.items
        title.children.extend(included)
        del page.toc.items[1:]
    return html
