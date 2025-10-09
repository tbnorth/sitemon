"""Asynchronous site monitor."""
import asyncio
import sys
import time
from pathlib import Path

import httpx
import yaml

type SiteID = str
type Site = dict

HTTP_OK = 200

TEMPLATETOP = """<html lang="en"><head><title>SiteMon website monitor</title>
<style type="text/css" >
tr * { padding: 0.25ex; }
pre { margin: 1ex; border: solid #808080 2px; background: #f0e0a0; }
.not_ok { background: pink; }
* { font-family: sans-serif; }
</style>
</head>
<body><table id="sitelist">
<tr><th>Site</th><th>Status</th><th>Time (sec.)</th></tr>"""

TEMPLATEBOT = """
</table>

<p>Updated %(updated)s</p>

<p>Hover over a site name to see the target text</p>
</body></html>
"""


def emit(txt: str) -> None:
    """Write output."""
    sys.stdout.write(txt + "\n")


async def check_site(
    client: httpx.AsyncClient, site_id: SiteID, site: Site, log_url: str | None
) -> None:
    """Check a site."""
    start = time.time()
    try:
        response = await client.get(site["href"], timeout=10.0, follow_redirects=True)
        loggable = response
    except httpx.RequestError:
        loggable = httpx.RequestError
    except httpx.TimeoutException:
        loggable = httpx.TimeoutException
    elapsed = time.time() - start

    ok = isinstance(loggable, httpx.Response) and loggable.status_code == HTTP_OK
    if ok:
        ok = site["expect"].encode("utf-8") in response.content

    if ok:
        class_ = "ok"
        msg = "Good"
        status = "OK"
    else:
        class_ = "not_ok"
        msg = "*ERROR*"
        status = "FAIL"

    emit(
        "<tr>"
        f"""<tr><td><a target="{site_id}" title="{site['expect']}" """
        f"""href="{site['href']}">{site['name']}</a></td>"""
        f"<td class='{class_}'>{msg}</td>"
        f"<td>{elapsed:.2g}</td>"
        "</tr>"
    )
    if not ok:
        emit(f"<tr><td colspan='3'>Did not see '{site['expect']}'.</td></tr>")
    if log_url:
        try:
            url = (
                f"{log_url}/log/{site_id}/status/{status}/SITE: {site['name']} "
                f"in {elapsed:.2g}"
            )
            await client.get(url)
        except Exception:
            sys.stderr.write(f"Logging failed on {url}.\n")


async def main() -> None:
    """Queue sites and check them asynchronously."""
    emit(TEMPLATETOP % {"updated": time.asctime()})
    conf = yaml.safe_load(Path(sys.argv[1]).open())
    tasks = []  # asyncio keeps weakrefs only, ruff says
    async with httpx.AsyncClient() as client:
        for site_id, site in conf["sites"].items():
            tasks.append(
                asyncio.create_task(
                    check_site(client, site_id, site, conf.get("logging_url"))
                )
            )

        await asyncio.gather(*asyncio.all_tasks() - {asyncio.current_task()})
    emit(TEMPLATEBOT % {"updated": time.asctime()})


asyncio.run(main())
