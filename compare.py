#!/usr/bin/env python
# coding: utf-8

import argparse
import cgi
import difflib
import logging
import re
import sys
import tarfile
from xml.dom import minidom

def tarfiles(archive, filter):
  for info in archive.getmembers():
    if info.isfile():
      name = re.sub(r'^\.\/', '', info.name)
      if filter(name):
        yield name

def filter_generic(name):
  return re.search(r'^(?!js)\w\w(_\w\w)?/', name)

def filter_anwiki(name):
  return '/_include/' not in name and filter_generic(name)

def filter_cms(name):
  if '/animations/' in name:
    return False
  if '/' in name and name.rsplit('/', 1)[1] == 'index':
    return False
  return filter_generic(name)

def cms_to_anwiki(name):
  if '/' in name:
    dir, file = name.rsplit('/', 1)
    if file in ('firefox', 'chrome', 'opera', 'safari', 'internet-explorer', 'android', 'yandex-browser', 'maxthon'):
      return '/'.join((dir, 'index'))
  return name

def sort_attributes(data):
  def do_sort(match):
    source = '%s</%s>' % (re.sub(r'/>$', '>', match.group(0)), match.group(1))
    element = minidom.parseString(source).documentElement
    attributes = []
    for name, value in sorted(element.attributes.items()):
      attributes.append('%s="%s"' % (cgi.escape(name).encode('utf-8'), cgi.escape(value).encode('utf-8')))
    return '<%s %s>' % (match.group(1), ' '.join(attributes))
  return re.sub(r'<(\w+)\s+[^>]*[^>/]/?>', do_sort, data)

def normalize_contents(data):
  data = sort_attributes(data)

  # KNOWN ISSUE: Ideographic full stop  shouldn't be followed up by whitespace,
  # yet the CMS will occasionally insert it nevertheless. Ignore this issue to
  # reduce noise.
  data = data.replace(u'\u3002 '.encode('utf-8'), u'\u3002'.encode('utf-8'))

  # Normalize whitespace
  data = data.replace(u'\u3000'.encode('utf-8'), ' ')   # ideographic space
  data = re.sub(r'^\s+', '', data, flags=re.M)
  data = re.sub(r'\s+$', '', data, flags=re.M)
  data = re.sub(r'[\t ]+', ' ', data)
  data = re.sub(r'>\s+', '>\n', data, flags=re.S)
  data = re.sub(r'\s+<', '\n<', data, flags=re.S)
  data = re.sub(r'>\s*<', '>\n<', data, flags=re.S)
  data = re.sub(r'(<(?:p|div|li|td|dd|dt|h1|h2|h3|h4)\b[^>]*>)\s*', '\\1\n', data, flags=re.S)
  data = re.sub(r'\s*(</(?:p|div|li|td|dd|dt|h1|h2|h3|h4)>)', '\n\\1', data, flags=re.S)
  data = re.sub(r'\s*(<(?:br|hr)>)\s*', '\n\\1\n', data, flags=re.S)
  data = re.sub(r'([^>])[\r\n]+([^<])', r'\1 \2', data)

  # Normalize entities
  data = re.sub(r'&mdash;', u'\u2014'.encode('utf-8'), data)
  data = re.sub(r'&nbsp;', u'\u00A0'.encode('utf-8'), data)
  data = re.sub(r'&copy;', u'\u00A9'.encode('utf-8'), data)
  data = re.sub(r'&euro;', u'\u20AC'.encode('utf-8'), data)
  data = re.sub(r'&#215;', u'\u00D7'.encode('utf-8'), data)
  data = re.sub(r'&#34;', '&quot;', data)
  data = re.sub(r'&#(?:42|x2A);', '*', data)
  data = re.sub(r'&#x40;', '@', data)

  # %2F => / in URL parameters
  data = re.sub(r' href=".*?"', lambda m: m.group(0).replace('%2F', '/'), data)

  return data.strip()

def process_anwiki_contents(data, pagename, existant_files):
  locale, pagename = pagename.split('/', 1)

  # Remove boilerplate
  data = re.sub(r'^.*?<div class="viewcontent [^>]*>', '', data, flags=re.S)
  data = re.sub(r'</div>\s*</div>\s*<footer>.*', '', data, flags=re.S)

  if re.sub(r'.*/', '', pagename) in ('acceptable-ads-manifesto', 'customize-facebook', 'customize-youtube', 'share'):
    data = re.sub(r'^\s*<h1>.*?</h1>', '', data, flags=re.S)

  data = re.sub(r'<!--.*?-->', '', data, flags=re.S)

  # Sort interface members
  if '<hr />' in data:
    def get_member_name(source):
      match = re.search(r'<p id="(?:prop|method)_(\w+)">', source)
      return match.group(1)
    parts = data.split('<hr />')
    parts = parts[0:1] + sorted(parts[1:], key=get_member_name)
    data = '<hr />'.join(parts)

  # Fix unescaped ampersands
  data = re.sub(r'&(?!#?\w+;)', '&amp;', data)

  # <br />   =>   <br>
  data = data.replace('<br />', '<br>')

  # <hr />   =>   <hr>
  data = data.replace('<hr />', '<hr>')

  # Fix unresolved links to home page
  data = re.sub(r' href="(firefox|chrome|opera|safari|internet-explorer|android|yandex-browser|maxthon)"', r' href="/%s/\1" hreflang="%s"' % (locale, locale), data)

  # Add trailing slash to language roots links
  data = re.sub(r'( href="/\w\w(?:_\w\w)?)(")', r'\1/\2', data)

  # Fix missing hreflang in <anwtoc> output
  data = re.sub(r'(<a href="/(\w\w(_\w\w)?)/[^"]+")(?! hreflang)', r'\1 hreflang="\2"', data)

  # Fix Anwiki linking to non-existant pages
  def check_link(match):
    if cms_to_anwiki(re.sub(r'#.*', '', match.group(1))) in existant_files:
      return match.group(0)
    else:
      locale, pagename = match.group(1).split('/', 1)
      return ' href="/en/%s" hreflang="en"' % pagename
  data = re.sub(r' href="/(%s/[^"]+)" hreflang="%s"' % (locale, locale), check_link, data)

  # Remove unnecessary list items in ToC
  data = re.sub(r'</li>\s*<li>\s*<ul>', '<ul>', data, flags=re.S)

  # Add <tbody> in preference table
  data = re.sub(r'<table id="preftable">(.*?)</table>', r'<table id="preftable"><tbody>\1</tbody></table>', data, flags=re.S)

  # Remove pointless <tt> tags in preference table
  data = re.sub(r'<td><tt></tt></td>', r'<td>&nbsp;</td>', data, flags=re.S)
  data = re.sub(r'<td><tt>(.*?)</tt></td>', r'<td>\1</td>', data, flags=re.S)

  # Remove duplicated hreflang attributes
  data = re.sub(r'(hreflang="[^">]*")(?:\s+hreflang="[^">]*")+', r'\1', data)

  # Escape quotation marks outside of tags
  def escape_quotes(match):
    match = match.group(0)
    if match.startswith('<'):
      return match
    return match.replace('"', '&quot;').replace("'", '&#39;').replace(">", '&gt;')
  data = re.sub(r'<.*?>|[^<]+', escape_quotes, data)

  # Remove "untranslated" markers
  data = re.sub(r'<span class="untranslated">(.*?)</span>', r'\1', data, flags=re.S)

  # Remove animation.js includes
  data = re.sub(r'<script src="/animation.js[^>]*></script>', '', data, flags=re.S)

  # Simplify script and image URLs
  data = data.replace('/_override-static/global/global', '')
  data = re.sub(r'\?a=show("(?:>|\s))', r'\1', data)
  data = re.sub(r'\?\d+("(?:>|\s))', r'\1', data)

  return normalize_contents(data)

def process_cms_contents(data, pagename):
  # Remove boilerplate
  if re.sub(r'.*/', '', pagename) in ('acceptable-ads-manifesto', 'customize-facebook', 'customize-youtube', 'share'):
    data = re.sub(r'.*<body>', '', data, flags=re.S)
    data = re.sub(r'</body>.*', '', data, flags=re.S)
  else:
    data = re.sub(r'^.*?<div id="content"[^>]*>', '', data, flags=re.S)
    data = re.sub(r'</div>\s*<footer>.*', '', data, flags=re.S)

  # Simplify script and image URLs
  data = re.sub(r'\?\d+("(?:>|\s))', r'\1', data)

  return normalize_contents(data)

def compare_file(anwiki, anwiki_name, anwiki_files, cms, cms_name):
  anwiki_data = anwiki.extractfile('./' + anwiki_name).read()
  if not anwiki_name.endswith('.png'):
    anwiki_data = process_anwiki_contents(anwiki_data, anwiki_name, anwiki_files)

  cms_data = cms.extractfile('./' + cms_name).read()
  if not cms_name.endswith('.png'):
    cms_data = process_cms_contents(cms_data, cms_name)

  if anwiki_data != cms_data:
    logging.warn("Anwiki file %s and CMS file %s differ" % (anwiki_name, cms_name))
    for line in difflib.unified_diff(anwiki_data.splitlines(True), cms_data.splitlines(True), anwiki_name, cms_name):
      sys.stdout.write(line if line.endswith('\n') else line + '\n')
    print
    print

def compare(anwiki, cms):
  anwiki_files = sorted(tarfiles(anwiki, filter_anwiki))
  cms_files = sorted(tarfiles(cms, filter_cms))
  seen = set()
  for name in cms_files:
    translated = cms_to_anwiki(name)
    if translated in anwiki_files:
      if not translated in seen:
        compare_file(anwiki, translated, anwiki_files, cms, name)
        seen.add(translated)
    else:
      logging.warn('CMS file %s has no Anwiki correspondence' % name)

  for name in anwiki_files:
    if name not in seen:
      logging.warn('Anwiki file %s has no CMS correspondence' % name)


parser = argparse.ArgumentParser(description='Compare static content')
parser.add_argument('anwiki', metavar='anwiki.tgz', help='Anwiki-generated pages')
parser.add_argument('cms', metavar='cms.tgz', help='CMS-generated pages')
args = parser.parse_args()

anwiki = tarfile.open(args.anwiki, 'r:gz')
cms = tarfile.open(args.cms, 'r:gz')
compare(anwiki, cms)
