#!/usr/bin/python

"""
"""

# sitemon.py $Id$
# Author: Terry Brown
# Created: Mon Aug 20 2007

import sys, os
import cgi
import cgitb; cgitb.enable()
import httplib2
import time
import xml.etree.ElementTree as etree 

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

def emit(txt):
    sys.stdout.write(txt+'\n')
    sys.stdout.flush()

emit('Content-type: text/html\n')
emit('''<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"
   "http://www.w3.org/TR/html4/strict.dtd">''')

emit(templatetop % {'updated': time.asctime()})

form = cgi.FieldStorage()
conf = form.getfirst('conf')
mode = form.getfirst('mode') or 'unspecified'
if not conf: conf = sys.argv[1]
chklist = etree.parse(conf)

U, P = 'nrri\\tbrown', 'MtZer0Here'
h = httplib2.Http(".cache")
h.add_credentials(U, P)

errmail = {}  # email to whom it may consern

timestamp = time.asctime()

for site in chklist.findall('site'):

    # try to retrieve
    start = time.time()
    resp, data = h.request(site.get('href'), "GET")
    elapsed = time.time() - start
    # what to look for
    status = 'Good'
    expecttxt = []
    errlog = []
    for e in site.findall('expect'):
        expect = e.text.strip()
        expecttxt.append(expect)
        if expect not in data:
            status = '*ERROR*'
            errlog.append("Didn't see: "+expect)
    for e in site.findall('reject'):
        reject = e.text.strip()
        expecttxt.append('NOT '+reject)
        if reject in data:
            status = '*ERROR*'
            errlog.append('Saw: '+reject)
    
    expecttxt = ' and '.join(expecttxt)

    url = cgi.escape(site.get('href'))
    name = site.get('name')
    colour = '' if status == 'Good' else ' style="background:pink"'
    
    emit('''<tr><td><a href="%(url)s" title="%(expecttxt)s">%(name)s</a></td><td%(colour)s>%(status)s</td><td>%(elapsed)3.2f</td></tr>''' % locals())

    if errlog:
        errlog = '\n'.join(errlog)
        emit('<tr><td colspan="3"><pre>%s</pre></td></tr>' % errlog)

        if 'email' in mode:

            worried = set(chklist.findall('email')).union(
                site.findall('email'))
            for worrier in worried:
                errmail.setdefault(worrier.text, '')
                errmail[worrier.text] += ('Error on %s\n%s\n%s\n'
                    % (name, url, errlog))

emit(templatebot % {'updated': timestamp})

if 'email' in mode and errmail:
    
    import smtplib  # avoid if possible, slow to init?

    url = chklist.findall('url')
    if url:
        url = url[0].text
    else:
        url = 'http://%s%s' % (os.environ['HTTP_HOST'],
            os.environ['REQUEST_URI'].replace('&mode=email',''))

    server = smtplib.SMTP('tyr.nrri.umn.edu')
    server.set_debuglevel(1)
    for k, v in errmail.iteritems():
        msg = '''From: SiteMon\nSubject: SiteMon: error on monitored web site\n\n
At %s the following error reports were generated:\n\n%s
See %s for more information.
''' % (timestamp, v, url)
        server.sendmail('tbrown@nrri.umn.edu', k, msg)
    server.quit()
