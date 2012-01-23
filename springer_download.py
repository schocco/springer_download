#! /usr/bin/env python

# -*- coding: utf-8 -*-


from time import sleep
from urllib2 import HTTPError
import getopt
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib
import urllib2
import mimetypes


#CONFIG
#TODO: add global conf
tempDir = tempfile.mkdtemp()
cwd = os.getcwd()

# Set some kind of User-Agent so we don't get blocked by SpringerLink
class SpringerURLopener(urllib.FancyURLopener):
    version = "Mozilla 5.0"
    
class Book(object):
    '''
    Representation of a single e-book.
    '''
    book_hash = None
    url = None
    title = None
    subtitle = None
    isbn = None
    chapters = list()
    edition = None
    year = None
    publisher = None
    cover_link = None
    cover_path = None
    
    def __init__(self, book_hash):
        '''
        :param book_hash: Content code of the book
        :param url: absolute or relative url to the book
        '''
        self.book_hash = book_hash
        self.url = "http://springerlink.com/content/%s/contents" % book_hash
        self._fetch_book_info()
        self._load_chapters()
        
    def _load_chapters(self, page=None):
        'Creates chapter objects and appends them to self.chapters.'
        if page is None:
            page = self._get_page(self.url)
            front_matter = False
            
        for index, match in enumerate(re.finditer('href="([^"]+\.pdf)"', page)):
            chapterLink = match.group(1)
            if chapterLink[:7] == "http://": # skip external links
                continue
            
            if re.search(r'front-matter.pdf', chapterLink):
                if front_matter:
                    continue
                else:
                    front_matter = True
            
            if re.search(r'back-matter.pdf', chapterLink) and re.search(r'<a href="([^"#]+)"[^>]*>Next</a>', page):
                continue
                #skip backmatter if it is in list as second chapter - will be there at the end of the book also
            if re.search(r'back-matter.pdf', chapterLink):
                if len(self.chapters) < 2:
                    continue
            if chapterLink[0] == "/":
                chapterLink = "http://springerlink.com" + chapterLink
            else:
                chapterLink = "http://springerlink.com/content/" + hash + "/" + chapterLink
            chapterLink = re.sub("/[^/]+/\.\.", "", chapterLink)
            self.chapters.append(Chapter(chapterLink, index))

        # get next page
        match = re.search(r'<a href="([^"#]+)"[^>]*>Next</a>', page)
        if match:
            link = "http://springerlink.com" + match.group(1).replace("&amp;", "&")
            page = self._get_page(link)
            self._load_chapters(page)
        else:
            if len(self.chapters) == 0:
                error("No chapters found - bad link?")
            else:
                print "found %d chapters" % len(self.chapters)
        
    def _get_page(self, link):
        ':returns: html source of the given link.'
        try:
            print "get page..."
            loader = SpringerURLopener()
            page = loader.open(link).read()
        except IOError, e:
            error("Bad link given (%s)" % e)

        if re.search(r'403 Forbidden', page):
            error("Could not access page: 403 Forbidden error.")
        
        return page
          
    def _fetch_book_info(self):
        '''Parses the books Web page to retrieve its information'''

        page = self._get_page(self.url)
        # get title
        match = re.search(r'<h1[^<]+class="title">(.+?)(?:<br/>\s*<span class="subtitle">(.+?)</span>\s*)?</h1>', page, re.S)
        if not match or match.group(1).strip() == "":
            error("Could not evaluate book title - bad link %s" % self.url)
        else:
            self.title = match.group(1).strip()
            # remove tags, e.g. <sub>
            self.title = re.sub(r'<[^>]*?>', '', self.title)
            
        # get subtitle
        if match and match.group(2) and match.group(2).strip() != "":
            self.subtitle = match.group(2).strip()

        # coverimage
        match = re.search(r'<div class="coverImage" title="Cover Image" style="background-image: url\(/content/([^/]+)/cover-medium\.gif\)">', page)
        if match:
            self.cover_link = "http://springerlink.com/content/" + match.group(1) + "/cover-large.gif"
            #TODO: move cover download into a thread
            print "downloading front cover from %s" % self.cover_link
            dst = os.path.join(tempDir, "frontcover")
            download(self.cover_link, dst)
            if os.system("convert %s %s.pdf" % (dst, dst)) == 0:
                self.cover_path = os.path.join("%s.pdf" % dst)
        
    def download(self, merge):
        '''
        Downloads all chapters to disk.
        Starts one thread for each chapter
        '''
        if os.path.isfile(self.path):
            error("%s already downloaded" % self.path)

        print "\nNow Trying to download book '%s'\n" % self.title
       
        for c in self.chapters:
            print "downloading chapter %d/%d" % (c.index, len(self.chapters))
            c.setDaemon(True)
            c.start()
        
        #wait for threads to finish
        while threading.activeCount() > 1:
            sleep(1)
            print "sleeping"
            
        if merge:
            print "merging chapters"
            fileList = self.get_file_list()
            print fileList
            if len(fileList) == 1:
                shutil.move(fileList[0], self.path)
            else:
                pdfcat(fileList, self.path)
    
            # cleanup
            os.chdir(cwd)
            shutil.rmtree(tempDir)
    
            print "book %s was successfully downloaded, it was saved to %s" % (self.title, self.path)
            log("downloaded %s chapters (%.2fMiB) of %s\n" % (len(self.chapters), os.path.getsize(self.path) / 2.0 ** 20, self.title))
        else: #HL: if merge=False
            print "book %s was successfully downloaded, unmerged chapters can be found in %s" % (self.title, tempDir)
            log("downloaded %s chapters of %s\n" % (len(self.chapters), self.title))
            
    def get_path(self):
        '''
        :return: Path were the final pdf should be saved.
        '''
        return "%s/%s.pdf" % (cwd, sanitizeFilename(self.title))
    path = property(fget = get_path, doc = "Path were the final pdf should be saved.")
    
    def get_file_list(self):
        '''
        :return: A list of paths, one for each chapter.
          Chapters with an empty path attribute are left out.
        '''
        fileList = []
        if self.cover_path:
            fileList.append(self.cover_path)
        for c in self.chapters:
            if c.path:
                fileList.append(c.path)
        return fileList
            


class Chapter(threading.Thread):
    '''
    Representation of a chapter in an e-book.
    '''
    url = None
    path = None
    index = 0
    
    def __init__(self, url, index):
        threading.Thread.__init__(self)
        self.url = url
        self.index = index
        self.path = os.path.join(tempDir, "%d.pdf" % self.index)
        print "initialized chapter with index %d and url %s" % (self.index, self.url)
        
    def run(self):
        'Downloads the chapter as pdf'
        download(self.url, self.path)      

def pdfcat(fileList, bookTitlePath):
    if findInPath("pdftk") != False:
        command = [findInPath("pdftk")]
        command.extend(fileList)
        command.extend(["cat", "output", bookTitlePath])
        subprocess.Popen(command, shell=False).wait()
    elif findInPath("stapler") != False:
        command = [findInPath("stapler"), "cat"]
        command.extend(fileList)
        command.append(bookTitlePath)
        subprocess.Popen(command, shell=False).wait()
    else:
        error("You have to install pdftk (http://www.accesspdf.com/pdftk/) or stapler (http://github.com/hellerbarde/stapler).")

# validate CLI arguments and start downloading
def main(argv):
    if not findInPath("iconv"):
        error("You have to install iconv.")

    #Test if convert is installed
    if os.system("convert --version > /dev/null 2>&1")!=0:
        error("You have to install the packet ImageMagick in order to use convert")

    try:
        opts, args = getopt.getopt(argv, "hl:c:n", ["help", "link=", "content=", "no-merge"])
    except getopt.GetoptError:
        error("Could not parse command line arguments.")

    link = ""
    book_hash = ""
    merge = True

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit()
        elif opt in ("-c", "--content"):
            if link != "":
                usage()
                error("-c and -l arguments are mutually exclusive")
            book_hash = arg
        elif opt in ("-l", "--link"):
            if book_hash != "":
                usage()
                error("-c and -l arguments are mutually exclusive")
            match = re.match("(https?://)?(www\.)?springer(link)?.(com|de)/(content|.*book)/(?P<book_hash>[a-z0-9\-]+)/?(\?[^/]*)?$", arg)
            if not match:
                usage()
                error("Bad link given. See example link.")
            book_hash = match.group("book_hash")
        elif opt in ("-n", "--no-merge"):
            merge = False

    if book_hash == "":
        usage()
        error("Either a link or a book_hash must be given.")

    if merge and not findInPath("pdftk") and not findInPath("stapler"):
        error("You have to install pdftk (http://www.accesspdf.com/pdftk/) or stapler (http://github.com/hellerbarde/stapler).")

    book = Book(book_hash)
    book.download(merge)

    sys.exit()

# give a usage message
def usage():
    print """Usage:
%s [OPTIONS]

Options:
  -h, --help              Display this usage message
  -l LINK, --link=LINK    defines the link of the book you intend to download
  -c ISBN, --content=ISBN builds the link from a given ISBN (see below)

  -n, --no-merge          Only download the chapters but don't merge them into a single PDF.

You have to set exactly one of these options.

LINK:
  The link to your the detail page of the ebook of your choice on SpringerLink.
  It lists book metadata and has a possibly paginated list of the chapters of the book.
  It has the form:
    http://springerlink.com/content/ISBN/STUFF
  Where: ISBN is a string consisting of lower-case, latin chars and numbers.
         It alone identifies the book you intent do download.
         STUFF is optional and looks like #section=... or similar. It will be stripped.
""" % os.path.basename(sys.argv[0])

# raise an error and quit
def error(msg=""):
    if msg != "":
        log("ERR: " + msg + "\n")
        print "\nERROR: %s\n" % msg
    sys.exit(2)

    return None

# log to file
def log(msg=""):
    logFile = open(os.path.join(cwd, 'springer_download.log'), 'a')
    logFile.write(msg)
    logFile.close()

# based on http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
def findInPath(prog):
    for path in os.environ["PATH"].split(os.pathsep):
        exe_file = os.path.join(path, prog)
        if os.path.exists(exe_file) and os.access(exe_file, os.X_OK):
            return exe_file
    return False

# based on http://mail.python.org/pipermail/python-list/2005-April/319818.html
def _reporthook(numblocks, blocksize, filesize, url=None):
    #XXX Should handle possible filesize=-1.
    try:
        percent = min((numblocks*blocksize*100)/filesize, 100)
    except:
        percent = 100
    if numblocks != 0:
        sys.stdout.write("\b"*70)
    sys.stdout.write("%-66s%3d%%" % (url, percent))

def download(url, dst, mime=None):
    '''
    Uses urllib2 to get a remote file.
    Prints a progress bar and removes the tempFolder if an HttpException occurs.
    '''
    if mime is None:
        mime = mimetypes.guess_type(dst)[0]
    txheaders = {   
                 'User-agent': 'Mozilla/5.0',
                 'Accept-Language': 'en-us',
                 'Accept-Encoding': 'gzip, deflate, compress;q=0.9',
                 'Keep-Alive': '300',
                 'Connection': 'keep-alive',
                 'Cache-Control': 'max-age=0',
    }
    req = urllib2.Request(url, headers=txheaders)
    f = open(dst, 'wb')
    try:
        u = urllib2.urlopen(req)        
        meta = u.info()
        file_size = int(meta.getheaders("Content-Length")[0])
        if mime and meta.gettype() != mime:
            error("Expected mimetype is %s, got %s instead!" % (mime, meta.gettype()))
        print "Downloading: %s Bytes: %s" % (dst, file_size)
    
        file_size_dl = 0
        block_sz = 8192
        while True:
            dl_buffer = u.read(block_sz)
            if not dl_buffer:
                break
    
            file_size_dl += len(dl_buffer)
            f.write(dl_buffer)
            status = r"%10d  [%3.2f%%]" % (file_size_dl, file_size_dl * 100. / file_size)
            status = status + chr(8)*(len(status)+1)
            print status,
    except HTTPError, e:
        print e
        try:
            shutil.rmtree(tempDir)
        except IOError:
            #already deleted
            pass
        error("%s - occured while downloading %s" % (e, url))
    finally:
        f.close()



def geturl(url, dst):
    ":DEPRECATED:"
    downloader = SpringerURLopener()
    if sys.stdout.isatty():
        response = downloader.retrieve(url, dst,
                           lambda nb, bs, fs, url=url: _reporthook(nb,bs,fs,url))
        sys.stdout.write("\n")
    else:
        response = downloader.retrieve(url, dst)

    return response

def sanitizeFilename(filename):
    p1 = subprocess.Popen(["echo", filename], stdout=subprocess.PIPE)
    p2 = subprocess.Popen(["iconv", "-f", "UTF-8", "-t" ,"ASCII//TRANSLIT"], stdin=p1.stdout, stdout=subprocess.PIPE)
    return re.sub("\s+", "_", p2.communicate()[0].strip().replace("/", "-"))

# start program
if __name__ == "__main__":
    main(sys.argv[1:])

# kate: indent-width 4; replace-tabs on;
