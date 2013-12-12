#!/usr/bin/python

"""
"""

# sitemon.py $Id$
# Author: Terry Brown
# Created: Mon Aug 20 2007

import sys, os
import cgi
import cgitb; cgitb.enable()
# import httplib2
import time
import xml.etree.ElementTree as etree
from xml.sax.saxutils import escape
import socket
import urllib2
import threading
import Queue

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
no_log = form.getfirst('no_log') or False

if not conf: conf = sys.argv[1]
chklist = etree.parse(conf)

saved = None
if (chklist.find('saveddata') != None
    and chklist.find('saveddata').text.strip()):
    import shelve
    saved = shelve.open(chklist.find('saveddata').text)

class HTTPPasswordMgrWithFolderSpecificity(object):
    """urls like gisdata.nrri.umn.edu/LesterRiver don't seem to work
    in standard classes, and gisdata.nrri.umn.edu is too general"""
    def add_password(self, x0, x1, x2, x3):
        # needed, even though it's not used
        pass

    def find_user_password(self, realm, authuri):
        if 'LesterRiver' in authuri:
            return ('LR1', 'Superior')
        if 'MNClimate' in authuri:
            return ('TerryBrown', 'P1ckyW1k1')
        if 'nrgisl' in authuri:
            return ('TerryBrown', 'P1ckyW1k1')
        return (None,None)

class chatty(urllib2.HTTPPasswordMgrWithDefaultRealm):

    def find_user_password(self, realm, authuri):
        global errlog
        errlog.append(realm + ' ' + authuri)
        return urllib2.HTTPPasswordMgr.find_user_password(self, realm, authuri)


# h = httplib2.Http(".cache")
# pwm = urllib2.HTTPPasswordMgrWithDefaultRealm()
# pwm = chatty()
# pwm.add_password(None, 'gisdata.nrri.umn.edu', 
#                  'LR1', 'Superior')
pwm = HTTPPasswordMgrWithFolderSpecificity()
h = urllib2.build_opener(
    urllib2.HTTPBasicAuthHandler(pwm)
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
        self.queue = kwargs['queue']
        del kwargs['queue']
        threading.Thread.__init__(self, *args, **kwargs)
    def run(self):
        
        while True:
            try:
                site = self.queue.get(block=False)
            except Queue.Empty:
                sys.stderr.write("%s %s thread done\n"%(time.strftime("%M:%S"), self.name))
                return

            sys.stderr.write("%s %s Got %s\n"%
                (time.strftime("%M:%S"), self.name, site.get('href')))

            expecttxt = []
            errlog = []
        
            # try to retrieve
            start = time.time()
            try:
                post = site.findall('post')
                if post:
                    post = post[0]
                    data = h.open(site.get('href'), post.text).read()
                else:
                    data = h.open(site.get('href')).read()
            except (urllib2.HTTPError, socket.error, urllib2.URLError):
                data = ''
            elapsed = time.time() - start
            # what to look for
            status = 'Good'
            
            sys.stderr.write("%s %s Loaded %s\n"%
                (time.strftime("%M:%S"), self.name, site.get('href')))
        
            for e in site.findall('expect'):
                expect = e.text.strip()
                expecttxt.append(expect)
                if expect not in data:
                    status = '*ERROR*'
                    errlog.append("Didn't see: "+expect)
                    if data:
                        errlog.append('Got: %s...'%(data[:100]))
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
        
            logurl = 'http://beaver.nrri.umn.edu:8111/log/%s/status/%s/WEBSITE: %s' % (
                 name.replace(' ','')[:10], ('OK' if status == 'Good' else 'FAIL'),
                 name)
            logurl = logurl.replace(' ','%20')
            sys.stderr.write("%s %s Logging %s\n"%
                (time.strftime("%M:%S"), self.name, site.get('href')))
            if not no_log:
                urllib2.urlopen(logurl)
            sys.stderr.write("%s %s Logged %s\n"%
                (time.strftime("%M:%S"), self.name, site.get('href')))
        
            #emit('''<tr><td>%s %s</td></tr>''' % (logurl, 
            #    urllib2.urlopen(logurl).read()))
        
            if errlog:
                errlog = escape('\n'.join(errlog))
                emit('<tr><td colspan="3"><pre>%s</pre></td></tr>' % errlog)
        
                if 'email' in mode:
        
                    worried = set(chklist.findall('email')).union(
                        site.findall('email'))
                    for worrier in worried:
                        errmail.setdefault(worrier.text, ['', set([])])
                        errmail[worrier.text][0] += ('Error on %s\n%s\n%s\n'
                            % (name, url, errlog))
                        errmail[worrier.text][1].add(name)    
        
            self.queue.task_done()

site_queue = Queue.Queue()

for site in chklist.findall('site'):

    site_queue.put(site, block=False)
    
for n in range(min(len(chklist.findall('site')), 15)):
    
    runner = CheckSite(queue=site_queue)
    runner.name = str(n)
    runner.start()
    
site_queue.join()

if 'email' in mode and errmail:

    emit('<div>Checking email</div>')

    import smtplib  # avoid if possible, slow to init?

    url = chklist.findall('url')
    if url:
        url = url[0].text
    else:
        url = 'http://%s%s' % (os.environ['HTTP_HOST'],
            os.environ['REQUEST_URI'].replace('&mode=email',''))

    server = smtplib.SMTP('tyr.nrri.umn.edu')
    server.set_debuglevel(1)

    for addr, v in errmail.iteritems():
        emit('<div>Checking %s</div>' % addr)
        msg, sites = v
        emit('<div>Checking %s</div>' % str(sites))
        doEmail = Trueauto
        if saved != None:  # then check when addr was last emailed about sites
            doEmail = False
            now = time.time()
            for site in sites:  # must find one not sent in 4hrs
                key = '%s:%s' % (addr, site)
                emit('<div>Checking %s</div>' % key)
                lastmail = 0
                if saved.has_key(key):
                    lastmail = saved[key]
                if now - lastmail > 4*3600: doEmail = True
            if doEmail:
                for site in sites:
                    key = '%s:%s' % (addr, site)
                    saved[key] = now

        if doEmail:

            msg = '''From: SiteMon
Subject: SiteMon: error on monitored web site

At %s the following error reports were generated:

%s

See %s for more information.

Errors on the above sites will not be sent again for four hours.
''' % (timestamp, msg, url)

            server.sendmail('tbrown@nrri.umn.edu', addr, msg)

    server.quit()

emit(templatebot % {'updated': timestamp})
