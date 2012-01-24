======================================================
Download Script for e-books hosted on Springerlink.com
======================================================

:author: Rocco Schulz <schocco.rulz(ät)gmail.com> / <http://is-gr8.com>
:author of original script: Milian Wolff <mail@milianw.de> / <http://milianw.de>

:licencse: GPL v3 (http://www.gnu.org/licenses/gpl.html)
:language: Python

Explanation
=============
This is a modified version of `milanw's` download script. It has been 
restructured for better extensibility and was enhanced with multi-threading 
support to speed up downloads.

``springer_download.py`` is a command-line utility to download educational e-books
from <http://springerlink.com>. You must have permissions to access the contents
hosted on springerlink.com in order to use this script.

The script cannot be used to obtain illegal copies of those ebooks.
It is intended to be used from your university network which might
have free access to the contents of SpringerLink if your institution has a license.

The script downloads all chapters of a book and merges them into one PDF file.

Usage
======

|./springer_download.py [OPTIONS]::
|
|Options:
|  -h, --help              Display this usage message
| -l LINK, --link=LINK    define the link of the book to start downloading
|  -c ISBN, --content=ISBN define the book to download by it's ISBN
|
|LINK:
|  The link to your the detail page of the ebook of your choice on SpringerLink.
|  It lists book metadata and has a possibly paginated list of the chapters of the book.
|  It has the form:
|    http://springerlink.com/content/HASH/STUFF
|  Where: HASH is a string consisting of lower-case, latin chars and numbers.
|         STUFF is optional and looks like ?p=...&p_o=... or similar. Will be stripped.

Thanks
======
A big thank you goes to Springer for hosting all these books _and_ allowing
access to students/educational institutions.

Legal Note
============
Springerlink is © Springer and part of Springer Science+Business Media.
