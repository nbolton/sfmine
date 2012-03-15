import sqlite3, os, httplib, re, time, sys, traceback
from xml.dom import minidom
from datetime import date
from optparse import OptionParser

def initDb():
  dbFile = "sfmine.db3"
  create = not os.path.exists(dbFile)
  connection = sqlite3.connect(dbFile)
  cursor = connection.cursor()
  if create:
    cursor.execute("create table projects(name text unique, downloads int, lastFile int)")
  return connection

def readPage(server, path):
  httpConn = httplib.HTTPConnection(server)
  httpConn.request("GET", path)
  r = httpConn.getresponse()
  return r.read()
  
def getText(node):
  return " ".join(t.nodeValue for t in node.childNodes if t.nodeType == t.TEXT_NODE)

def getLastFileTime(name):
  data = readPage("sourceforge.net", "/projects/%s/files/" % name)
  # first date is always the most recent
  m = re.search("<abbr.*>((\d+)-(\d+)-(\d+))", data)
  print "  mod: " + (m.group(1) if m is not None else "?")
  if m:
    year = int(m.group(2))
    month = int(m.group(3))
    day = int(m.group(4))
    timestamp = time.mktime(date(year, month, day).timetuple())
    ts = int(timestamp)
    print "  ts: " + str(ts)
    return ts
  return None

def insertProject(connection, name, downloads, lastFile):
  cursor = connection.cursor()
  cursor.execute(
    "insert into projects (name, downloads, lastFile) values ('%s', %i, %i)" %
    (name, downloads, lastFile))
  connection.commit()
  print "  id: " + str(cursor.lastrowid)

def updateLastFile(connection, name, lastFile):
  cursor = connection.cursor()
  cursor.execute(
    "update projects set lastFile = %d where name = '%s'" %
    (lastFile, name))
  connection.commit()
  
def readProject(name, connection):
  data = readPage("sourceforge.net", "/projects/%s/" % name)
  m = re.search("([\d,]+) Download", data)
  downloadsText = m.group(1).replace(",", "") if m is not None else None
  if downloadsText is not None:
    downloads = int(downloadsText)
    print "  dl: " + str(downloads)
    if downloads != 0:
      lastFile = getLastFileTime(name) if downloads > 0 else 0
      if lastFile is not None:
        insertProject(connection, name, downloads, lastFile)
  
def mine(connection, reset, limit, startPage, maxPage):
  if reset:
    print "reset database"
    cursor = connection.cursor()
    cursor.execute("delete from projects")
  
  pcount = 0
  for i in range(startPage, maxPage):
    data = readPage(
      "sourceforge.net",
      "/api/project/index/updated_since/1104537600/limit/%s/offset/%s/rss" % (limit, (i * limit)))
    
    dom = minidom.parseString(data)
    rss = dom.getElementsByTagName("rss")[0]
    channel = rss.getElementsByTagName("channel")[0]
    items = channel.getElementsByTagName("item")
    for item in items:
      linkNode = item.getElementsByTagName("link")[0]
      link = getText(linkNode)
      m = re.search("name/(.*)/", link)
      name = m.group(1)
      
      pcount += 1
      print "%i/%i, %s" % (pcount, i, name)
      
      if name.endswith(".u"):
        print "  type: user"
        continue
      
      try:
        readProject(name, connection)
      except KeyboardInterrupt:
        print "user quit"
        return
      except sqlite3.IntegrityError:
        print "  error: sqlite3 integrity error"
      except:
        traceback.print_exc()

def list(connection, html, minDownloads):
  cursor = connection.cursor()
  cursor.execute("select * from projects where downloads > %d order by lastFile asc" % minDownloads)
  rows = cursor.fetchall()
  
  if html:
    print ("<p>results: %i</p>"
      "<table><tr><th>name</th><th>downloads</th><th>last release</th></tr>") % len(rows)
    
  for row in rows:
    name = row[0]
    downloads = row[1]
    lastFile = date.fromtimestamp(row[2]) if row[2] is not 0 else '?'
    
    if html:
      format = "<tr><td><a href=\"%(u)s\">%(n)s</a></td><td>%(d)s</td><td>%(l)s</td></tr>" 
    else:
      format = "%(n)s:\n  dl: %(d)i\n  last: %(l)s\n  url: %(u)s"
  
    url = "http://sourceforge.net/projects/%s/" % name
    print format % { "n" : name, "d" : downloads, "l" : lastFile, "u" : url }
  
  if html:
    print "</table>"

def refresh(connection, minDownloads, start):
  cursor = connection.cursor()
  cursor.execute("select * from projects where downloads > " + str(minDownloads) + " order by name")
  rows = cursor.fetchall()
  
  i = 0
  for row in rows:
    i += 1
    if (i < start):
      continue
    name = row[0]
    print "%d/%d, %s:" % (i, len(rows), name)
    lastFile = getLastFileTime(name)
    if lastFile:
      updateLastFile(connection, name, lastFile)
    
def main():
  parser = OptionParser()
  parser.add_option(
    "-m", "--mine", action="store_true", dest="mine",
    default=False, help="mine sf.net")
  parser.add_option(
    "-l", "--list", action="store_true", dest="list",
    default=False, help="list mined results")
  parser.add_option(
    "", "--refresh", action="store_true", dest="refresh",
    default=False, help="refresh existng records")
  parser.add_option(
    "", "--html", action="store_true", dest="html",
    default=False, help="if -l, output html")
  parser.add_option(
    "", "--reset", action="store_true", dest="reset",
    default=False, help="if -m, reset database")
  parser.add_option(
    "", "--start", dest="start", default=0, help="start at item")

  (options, args) = parser.parse_args()

  connection = initDb()
  
  if options.mine:
    mine(connection, options.reset, 100, int(options.start), 6000)

  if options.list:
    list(connection, options.html, 1000)
    
  if options.refresh:
    refresh(connection, 5000, int(options.start))
    
  connection.close()

main()
