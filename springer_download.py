#! /usr/bin/env python

# -*- coding: utf-8 -*-


from time import sleep
from urllib2 import HTTPError
import getopt
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib2


#CONFIG
tempDir = tempfile.mkdtemp()
cwd = os.getcwd()
    
class Book(object):
    '''
    Representation of a single e-book.
    '''
    BASE_URL_SPRINGER = "http://springerlink.com/"
    
    def __init__(self, book_hash):
        '''
        :param book_hash: Content code of the book
        :param url: absolute or relative url to the book
        '''
        self.book_hash = book_hash
        self.title = ""
        self.subtitle = ""
        self.chapters = []
        self.cover_link = None
        self.cover_base_path = os.path.join(tempDir, "frontcover.%s")
        
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
            if not self._get_springer_chapter_link(chapterLink):
                # skip external links
                continue    
             
            if re.search(r'front-matter.pdf', chapterLink):
                #add front_matter only once
                if front_matter:
                    continue
                else:
                    front_matter = True
            
            if (re.search(r'back-matter.pdf', chapterLink)
                and re.search(r'<a href="([^"#]+)"[^>]*>Next</a>', page)
                or
                re.search(r'back-matter.pdf', chapterLink) and len(self.chapters) < 2):
                # ignore occurrence of back_matter.pdf when there is another
                # page. Will be linked on the last page again.
                continue

            chapterLink = self._get_springer_chapter_link(chapterLink)
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
                
    def _get_springer_chapter_link(self, rel_link):
        '''
        :param rel_link: a relative link to a book chapter
        :return: absolute url to the linked chapter or False when the given
          link is absolute and not relative. 
        '''
        if rel_link.startswith("http://") or rel_link.startswith("https://"):
            return False
        if rel_link.startswith("/"):
            return "%s%s" % (Book.BASE_URL_SPRINGER, rel_link.lstrip("/"))
        else:
            base_link = "http://springerlink.com/content/%s/%s/"
            return base_link % (self.book_hash, rel_link.strip("/"))
        
    def _get_page(self, link):
        ':returns: html source of the given link.'
        txheaders = {'User-agent': 'Mozilla/5.0', }
        req = urllib2.Request(link, headers=txheaders)
        f = urllib2.urlopen(req)
        return f.read()
          
    def _fetch_book_info(self):
        '''
        Parses the books Web page to retrieve its information.
        
        Values being set are: `title`, `subtitle`, `cover_link`
        '''
        page = self._get_page(self.url)
        # get title
        match = re.search(r'<h1[^<]+class="title">(.+?)(?:<br/>\s*<span class="subtitle">(.+?)</span>\s*)?</h1>', page, re.S)
        if not match or match.group(1).strip() == "":
            error("Could not evaluate book title - bad link %s" % self.url)
        else:
            self.title = match.group(1).strip()
            # remove tags, e.g. <sub>
            self.title = re.sub(r'<[^>]*?>', '', self.title)
            try:
                unicode(self.title, "ascii")
            except UnicodeError:
                self.title = unicode(self.title, "utf-8")
            else:
                pass
            
        # get subtitle
        if match and match.group(2) and match.group(2).strip() != "":
            self.subtitle = match.group(2).strip()

        # coverimage
        match = re.search(r'<div class="coverImage" title="Cover Image" style="background-image: url\(/content/([^/]+)/cover-medium\.gif\)">', page)
        if match:
            self.cover_link = "http://springerlink.com/content/" + match.group(1) + "/cover-large.gif"
        
    def download(self, merge):
        '''
        Downloads all chapters to disk.
        Also downloads the cover image and converts it to pdf.        
        Uses one ```Downloader`` thread for each file.
        '''
        if os.path.isfile(self.path):
            error("%s already downloaded" % self.path)

        print "\nNow Trying to download book '%s'\n" % self.title
        #get cover
        if self.cover_link:
            d = Downloader(self.cover_link, self.cover_base_path % "gif",
                           mimes = ("image/png", "image/gif", "image/jpg"),
                           daemon = False)
            d.start()
        #get chapters
        for c in self.chapters:
            d = Downloader(c.url, c.path)
            d.start()
        
        #wait for threads to finish
        while threading.activeCount() > 1:
            sleep(1)
            
        if merge:
            print "\nmerging chapters..."
            fileList = self.get_file_list()
            if len(fileList) == 1:
                shutil.move(fileList[0], self.path)
            else:
                pdfcat(fileList, self.path)
    
            # cleanup
            os.chdir(cwd)
            shutil.rmtree(tempDir)
    
            print u"Book %s was successfully downloaded,\nit was saved to %s" % (self.title, self.path)
            log("downloaded %s chapters (%.2fMiB) of %s\n" % (len(self.chapters), os.path.getsize(self.path) / 2.0 ** 20, self.title))
        else: #HL: if merge=False
            print u"book %s was successfully downloaded,\nunmerged chapters can be found in %s" % (self.title, tempDir)
            log("downloaded %s chapters of %s\n" % (len(self.chapters), self.title))
            
    def get_path(self):
        '''
        :return: Path were the final pdf should be saved.
        '''
        return "%s/%s.pdf" % (cwd, normalize(self.title))
    path = property(fget = get_path, doc = "Path were the final pdf should be saved.")
    
    def get_file_list(self):
        '''
        Creates a list with the cover image as pdf and all downloaded
        chapters.
        :return: A list of paths, one for each chapter.
          Chapters with an empty path attribute are left out.
        '''
        fileList = []
        if self.cover_link:
            dst = self.cover_base_path % "pdf"
            if os.system("convert %s %s" % (self.cover_base_path % "gif", dst)) == 0:
                fileList.append(dst)
        for c in self.chapters:
            if c.path:
                fileList.append(c.path)
        return fileList
            


class Chapter(object):
    '''
    Representation of a chapter in an e-book.
    '''
    url = None
    path = None
    index = 0
    
    def __init__(self, url, index):
        self.url = url
        self.index = index
        self.path = os.path.join(tempDir, "%d.pdf" % self.index)

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
    logFile.write(msg.encode("utf-8"))
    logFile.close()

# based on http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
def findInPath(prog):
    for path in os.environ["PATH"].split(os.pathsep):
        exe_file = os.path.join(path, prog)
        if os.path.exists(exe_file) and os.access(exe_file, os.X_OK):
            return exe_file
    return False


class Downloader(threading.Thread):
    '''
    Downloader thread.
    '''
    total_bytes = 0
    total_bytes_dl = 0
    shutdown = False # flag for thread termination
    
    def __init__(self, url, dst, mimes = [], daemon = True):
        threading.Thread.__init__(self)
        self.url = url
        self.dst = dst
        self.setDaemon(daemon)
        if not mimes:
            self.mimes = mimes.append(mimetypes.guess_type(dst)[0])
        else:
            self.mimes = mimes
    
    @staticmethod
    def print_status():
        '''
        Static method which prints the overall download progress.
        '''
        status = r"%10d of %10d Bytes  [%3.2f%%]" % (Downloader.total_bytes_dl, Downloader.total_bytes, Downloader.total_bytes_dl * 100. / Downloader.total_bytes)
        status = status + chr(8)*(len(status)+1)
        print status,
    
    def run(self):
        '''
        Starts the download from the specified url. And adds itself to the
        static list of threads.
        '''
        txheaders = {   
                 'User-agent': 'Mozilla/5.0',
        }
        req = urllib2.Request(self.url, headers=txheaders)
        f = open(self.dst, 'wb')
        try:
            u = urllib2.urlopen(req)        
            meta = u.info()
            file_size = int(meta.getheaders("Content-Length")[0])
            if self.mimes and meta.gettype() not in self.mimes:
                error("Expected mimetype is %s, got %s instead!" % (self.mimes, meta.gettype()))
            print "Downloading: %s : (%s Bytes)" % (self.url, file_size)
            Downloader.total_bytes += file_size
        
            file_size_dl = 0
            block_sz = 8192
            while True:
                dl_buffer = u.read(block_sz)
                if not dl_buffer:
                    break
        
                file_size_dl += len(dl_buffer)
                Downloader.total_bytes_dl += len(dl_buffer)
                f.write(dl_buffer)
                Downloader.print_status()
        except HTTPError, e:
            print e
            try:
                shutil.rmtree(tempDir)
            except IOError:
                #already deleted
                pass
            error("%s - occured while downloading %s" % (e, self.url))
        finally:
            f.close()


def normalize(value):
    """
    Removes non-alpha characters, and converts spaces to hyphens.
    """
    value = unicode(re.sub('[^\w\s-]', '', value).strip())
    return re.sub('[-\s]+', '-', value)


# start program
if __name__ == "__main__":
    main(sys.argv[1:])

# kate: indent-width 4; replace-tabs on;
