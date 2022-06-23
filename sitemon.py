"""
Author: Terry Brown
Created: Mon Aug 20 2007
"""

import html
import os
import queue
import socket
import ssl
import sys
import threading
# import httplib2
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

templatetop = """<html lang="en"><head><title>SiteMon website monitor</title>
<style type="text/css" >
tr * { padding: 0.25ex; }
pre { margin: 1ex; border: solid #808080 2px; background: #f0e0a0; }
* { font-family: sans-serif; }
</style>
</head>
<body><table id="sitelist">
<tr><th>Site</th><th>Status</th><th>Time (sec.)</th></tr>"""

templatebot = """
</table>

<p>Updated %(updated)s</p>

<p>Hover over a site name to see the target text</p>
</body></html>
"""

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def emit(txt):
    sys.stdout.write(txt + "\n")
    sys.stdout.flush()


emit("Content-type: text/html\n")
emit(
    """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
   "http://www.w3.org/TR/html4/strict.dtd">"""
)

emit(templatetop % {"updated": time.asctime()})


conf = yaml.safe_load(Path(sys.argv[1]).open())
mode = conf.get("mode") or "unspecified"
no_log = conf.get("no_log") or False

saved = None
if conf.get("saveddata"):
    import shelve

    saved = shelve.open(conf["saveddata"])


class HTTPPasswordMgrWithFolderSpecificity(object):
    """urls like gisdata.nrri.umn.edu/LesterRiver don't seem to work
    in standard classes, and gisdata.nrri.umn.edu is too general"""

    def add_password(self, x0, x1, x2, x3):
        # needed, even though it's not used
        pass

    def find_user_password(self, realm, authuri):
        if "LesterRiver" in authuri:
            return ("LR1", "Superior")
        if "MNClimate" in authuri:
            return ("TerryBrown", "P1ckyW1k1")
        if "nrgisl" in authuri:
            return ("TerryBrown", "P1ckyW1k1")
        return (None, None)


class chatty(urllib.request.HTTPPasswordMgrWithDefaultRealm):
    def find_user_password(self, realm, authuri):
        global errlog
        errlog.append(realm + " " + authuri)
        return urllib.request.HTTPPasswordMgr.find_user_password(self, realm, authuri)


# h = httplib2.Http(".cache")
# pwm = urllib2.HTTPPasswordMgrWithDefaultRealm()
# pwm = chatty()
# pwm.add_password(None, 'gisdata.nrri.umn.edu',
#                  'LR1', 'Superior')
pwm = HTTPPasswordMgrWithFolderSpecificity()
h = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=ctx), urllib.request.HTTPBasicAuthHandler(pwm)
)
# h.add_credentials('LR1', 'Superior', 'LesterRiver')
# U, P = 'nrri\\tbrown', 'R0ckyMtn'
# U, P = 'TerryBrown', 'w1k1'
# h.add_credentials(U, P)

errmail = {}  # email to whom it may consern
# keys are email addresses, values are [msg, sites] where the
# sites is a set of affected site names

timestamp = time.asctime()


class CheckSite(threading.Thread):
    def __init__(self, *args, **kwargs):
        self.queue = kwargs["queue"]
        del kwargs["queue"]
        threading.Thread.__init__(self, *args, **kwargs)

    def run(self):

        while True:
            try:
                site = self.queue.get(block=False)
            except queue.Empty:
                sys.stderr.write(
                    "%s %s thread done\n" % (time.strftime("%M:%S"), self.name)
                )
                return

            sys.stderr.write(
                "%s %s Got %s\n" % (time.strftime("%M:%S"), self.name, site.get("href"))
            )

            expecttxt = []
            errlog = []

            # try to retrieve
            start = time.time()
            try:
                post = site.get("post")
                if post:
                    data = h.open(site.get("href"), post.encode("utf8")).read()
                else:
                    data = h.open(site.get("href")).read()
            except (urllib.error.HTTPError, socket.error, urllib.error.URLError):
                data = ""
            if isinstance(data, str):
                data = data.encode("utf8")
            elapsed = time.time() - start
            # what to look for
            status = "Good"

            sys.stderr.write(
                "%s %s Loaded %s\n"
                % (time.strftime("%M:%S"), self.name, site.get("href"))
            )

            expects = site.get("expect", [])
            if not isinstance(expects, list):
                expects = [expects]
            for e in expects:
                expect = e.strip()
                expecttxt.append(expect)
                if expect.encode("utf8") not in data:
                    status = "*ERROR*"
                    errlog.append("Didn't see: " + expect)
                    if data:
                        errlog.append("Got: %s..." % (data[:100]))
            rejects = site.get("rejects", [])
            if not isinstance(rejects, list):
                rejects = [rejects]
            for e in rejects:
                reject = e.strip()
                expecttxt.append("NOT " + reject)
                if reject in data:
                    status = "*ERROR*"
                    errlog.append("Saw: " + reject)

            expecttxt = " and ".join(expecttxt)

            url = html.escape(site.get("href"))
            name = site.get("name", site["site_id"])
            colour = "" if status == "Good" else ' style="background:pink"'

            emit(
                """<tr><td><a href="%(url)s" title="%(expecttxt)s">%(name)s</a></td>"""
                """<td%(colour)s>%(status)s</td><td>%(elapsed)3.2f</td></tr>"""
                % locals()
            )

            if conf.get("logging_url"):
                logurl = (
                    "{logto}/log/{site_id}/status/{status}/SITE: {name} "
                    "in {elapsed:3.1f} secs."
                ).format(
                    logto=conf["logging_url"],
                    site_id=site["site_id"],
                    status=("OK" if status == "Good" else "FAIL"),
                    name=site.get("name", site["site_id"]),
                    elapsed=elapsed,
                )
                logurl = logurl.replace(" ", "%20")
                sys.stderr.write(
                    "%s %s Logging %s\n"
                    % (time.strftime("%M:%S"), self.name, site.get("href"))
                )
                if not no_log:
                    urllib.request.urlopen(logurl, None, 300)
                sys.stderr.write(
                    "%s %s Logged %s\n"
                    % (time.strftime("%M:%S"), self.name, site.get("href"))
                )

            # emit('''<tr><td>%s %s</td></tr>''' % (logurl,
            #    urllib2.urlopen(logurl).read()))

            if errlog:
                errlog = escape("\n".join(errlog))
                emit('<tr><td colspan="3"><pre>%s</pre></td></tr>' % errlog)

                if "email" in mode:

                    worried = set(conf.get("email", [])).union(site.get("email", []))
                    for worrier in worried:
                        errmail.setdefault(worrier.text, ["", set([])])
                        errmail[worrier.text][0] += "Error on %s\n%s\n%s\n" % (
                            name,
                            url,
                            errlog,
                        )
                        errmail[worrier.text][1].add(name)

            self.queue.task_done()


site_queue = queue.Queue()

for site_id, site in conf["sites"].items():
    site["site_id"] = site_id

    site_queue.put(site, block=False)

for n in range(min(len(conf["sites"]), 15)):

    runner = CheckSite(queue=site_queue)
    runner.name = str(n)
    runner.start()

site_queue.join()

if "email" in mode and errmail:

    emit("<div>Checking email</div>")

    import smtplib  # avoid if possible, slow to init?

    url = conf.get("url")
    if not url:
        url = "http://%s%s" % (
            os.environ["HTTP_HOST"],
            os.environ["REQUEST_URI"].replace("&mode=email", ""),
        )

    server = smtplib.SMTP("tyr.nrri.umn.edu")
    server.set_debuglevel(1)

    for addr, v in errmail.items():
        emit("<div>Checking %s</div>" % addr)
        msg, sites = v
        emit("<div>Checking %s</div>" % str(sites))
        doEmail = True
        if saved is not None:  # then check when addr was last emailed about sites
            doEmail = False
            now = time.time()
            for site in sites:  # must find one not sent in 4hrs
                key = "%s:%s" % (addr, site)
                emit("<div>Checking %s</div>" % key)
                lastmail = 0
                if key in saved:
                    lastmail = saved[key]
                if now - lastmail > 4 * 3600:
                    doEmail = True
            if doEmail:
                for site in sites:
                    key = "%s:%s" % (addr, site)
                    saved[key] = now

        if doEmail:

            msg = """From: SiteMon
Subject: SiteMon: error on monitored web site

At %s the following error reports were generated:

%s

See %s for more information.

Errors on the above sites will not be sent again for four hours.
""" % (
                timestamp,
                msg,
                url,
            )

            server.sendmail("tbrown@nrri.umn.edu", addr, msg)

    server.quit()

emit(templatebot % {"updated": timestamp})
