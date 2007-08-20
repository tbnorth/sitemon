#!/usr/bin/python

"""
"""

# sitemon.py $Id$
# Author: Terry Brown
# Created: Mon Aug 20 2007

import sys
import cgi
import cgitb; cgitb.enable()
import urllib
import time
import xml.etree.ElementTree as etree 

SUB = etree.SubElement
ELE = etree.Element

template = """
<html><head><title>SiteMon website monitor</title>
<style>
tr * { padding: 0.25ex; }
pre { margin: 1ex; border: solid #808080 2px; background: #f0e0a0; }
</style>
</head>
<body>

<p>Updated <span id='updated'/></p>

<table id="sitelist">
<tr><th>Site</th><th>Status</th><th>Time (sec.)</th></tr>
</table>
<p>Hover over a site name to see the target text</p>
</body></html>
"""

def ElementById(ele, Id):
    for i in ele.getiterator():
        if i.get('id') == Id: return i
    return None

print 'Content-type: text/html\n'

page = etree.XML(template)
ElementById(page, 'updated').text = time.asctime()

sitelist = ElementById(page, 'sitelist')
form = cgi.FieldStorage()
chklist = etree.parse(form.getfirst('conf'))

class MyOpener(urllib.FancyURLopener):
    def __init__(self):
        urllib.FancyURLopener.__init__(self, None, user='nrri\\tbrown')
    def prompt_user_passwd(self, host, realm):
        return 'MtZer0Here'

urllib._urlopener = MyOpener()

for i in chklist.findall('site'):

    # try to retrieve
    start = time.time()
    data = urllib.urlopen(i.get('href')).read()
    elapsed = time.time() - start
    # what to look for
    status = 'Good'
    expecttxt = []
    errlog = []
    for e in i.findall('expect'):
        expect = e.text.strip()
        expecttxt.append(expect)
        if expect not in data:
            status = '*ERROR*'
            errlog.append("Didn't see: "+expect)
    for e in i.findall('reject'):
        reject = e.text.strip()
        expecttxt.append('NOT '+reject)
        if reject in data:
            status = '*ERROR*'
            errlog.append('Saw: '+reject)
    
    expecttxt = ' and '.join(expecttxt)
    tr = SUB(sitelist, 'tr')
    
    SUB(SUB(tr, 'td'), 'a', href = i.get('href'),
        title = expecttxt).text = i.get('name')
    #D sys.stderr.write(i.get('name')+'\n')
    
    td = SUB(tr, 'td')
    td.text = status
    if status != 'Good': td.set('style', 'background:pink')

    SUB(tr, 'td').text = '%3.2f' % elapsed

    if errlog:
        errlog = '\n'.join(errlog)
        td = SUB(SUB(sitelist, 'tr'), 'td', colspan = '2')
        pre = SUB(td, 'pre')
        pre.text = errlog
    
etree.ElementTree(page).write(sys.stdout)
