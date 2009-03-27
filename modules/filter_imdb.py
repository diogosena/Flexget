import urllib
import urllib2
import logging
import re
import string
import difflib
import time
from manager import ModuleWarning
from socket import timeout
from BeautifulSoup import BeautifulSoup

__pychecker__ = 'unusednames=parser'

log = logging.getLogger('imdb')

class ImdbSearch:

    def __init__(self):
        # depriorize aka matches a bit
        self.aka_weight = 0.9
        # priorize popular matches a bit
        self.unpopular_weight = 0.95
        self.min_match = 0.5
        self.min_diff = 0.01
        self.debug = False
        self.cutoffs = ['dvdrip', 'dvdscr', 'cam', 'r5', 'limited',
                        'xvid', 'h264', 'x264', 'h.264', 'x.264', 
                        'dvd', 'screener', 'unrated', 'repack', 
                        'rerip', 'proper', '720p', '1080p', '1080i',
                        'bluray']
        self.remove = ['imax']
        
        self.ignore_types = ['VG']
        
    def ireplace(self, str, old, new, count=0):
        """Case insensitive string replace"""
        pattern = re.compile(re.escape(old), re.I)
        return re.sub(pattern, new, str, count)

    def parse_name(self, s):
        """Sanitizes movie name from all kinds of crap"""
        for char in ['[', ']', '_']:
            s = s.replace(char, ' ')
        # if there are no spaces, start making begining from dots
        if s.find(' ') == -1:
            s = s.replace('.', ' ')
        if s.find(' ') == -1:
            s = s.replace('-', ' ')

        # remove unwanted words
        for word in self.remove:
            s = self.ireplace(s, word, '')
            
        # remove extra and duplicate spaces!
        s = s.strip()
        while s.find('  ') != -1:
            s = s.replace('  ', ' ')

        # split to parts        
        parts = s.split(' ')
        year = None
        cut_pos = 256
        for part in parts:
            # check for year
            if part.isdigit():
                n = int(part)
                if n>1930 and n<2050:
                    year = part
                    if parts.index(part) < cut_pos:
                        cut_pos = parts.index(part)
            # if length > 3 and whole word in uppers, consider as cutword (most likelly a group name)
            if len(part) > 3 and part.isupper() and part.isalpha():
                if parts.index(part) < cut_pos:
                    cut_pos = parts.index(part)
            # check for cutoff words
            if part.lower() in self.cutoffs:
                if parts.index(part) < cut_pos:
                    cut_pos = parts.index(part)
        # make cut
        s = string.join(parts[:cut_pos], ' ')
        return s, year

    def smart_match(self, raw_name):
        """Accepts messy name, cleans it and uses information available to make smartest and best match"""
        name, year = self.parse_name(raw_name)
        if name=='':
            log.critical('Failed to parse name from %s' % raw_name)
            return None
        log.debug('smart_match name=%s year=%s' % (name, str(year)))
        return self.best_match(name, year)

    def best_match(self, name, year=None):
        """Return single movie that best matches name criteria or None"""
        movies = self.search(name)
        
        if not movies:
            log.debug('search did not return any movies')
            return None

        # remove all movies below min_match, and different year
        for movie in movies[:]:
            if year and movie.get('year'):
                if movie['year'] != str(year):
                    log.debug('best_match removing %s - %s (wrong year: %s)' % (movie['name'], movie['url'], str(movie['year'])))
                    movies.remove(movie)
                    continue
            if movie['match'] < self.min_match:
                log.debug('best_match removing %s (min_match)' % movie['name'])
                movies.remove(movie)
                continue
            if movie.get('type', None) in self.ignore_types:
                log.debug('best_match removing %s (ignored type)' % movie['name'])
                movies.remove(movie)
                continue

        if not movies:
            log.debug('no movies remain')
            return None
        
        # if only one remains ..        
        if len(movies) == 1:
            log.debug('only one movie remains')
            return movies[0]

        # check min difference between best two hits
        diff = movies[0]['match'] - movies[1]['match']
        if diff < self.min_diff:
            log.debug('unable to determine correct movie, min_diff too small')
            for m in movies:
                log.debug('remain: %s (match: %s) %s' % (m['name'], m['match'], m['url']))
            return None
        else:
            return movies[0]

    def search(self, name):
        """Return array of movie details (dict)"""
        log.debug('Searching: %s' % name)
        url = u'http://www.imdb.com/find?' + urllib.urlencode({'q':name.encode('latin1'), 's':'all'})
        log.debug('Serch query: %s' % repr(url))
        page = urllib2.urlopen(url)
        actual_url = page.geturl()

        movies = []
        # incase we got redirected to movie page (perfect match)
        re_m = re.match('.*\.imdb\.com\/title\/tt\d+\/', actual_url)
        if re_m:
            actual_url = re_m.group(0)
            log.debug('Perfect hit. Search got redirected to %s' % actual_url)
            movie = {}
            movie['match'] = 1.0
            movie['name'] = name
            movie['url'] = actual_url
            movie['year'] = None # skips year check
            movies.append(movie)
            return movies

        soup = BeautifulSoup(page)

        sections = ['Popular Titles', 'Titles (Exact Matches)',
                    'Titles (Partial Matches)', 'Titles (Approx Matches)']

        for section in sections:
            section_tag = soup.find('b', text=section)
            if not section_tag:
                log.debug('section %s not found' % section)
                continue
            log.debug('processing section %s' % section)
            try:
                section_p = section_tag.parent.parent
            except AttributeError:
                log.debug('Section % does not have parent?' % section)
                continue
            
            links = section_p.findAll('a', attrs={'href': re.compile('\/title\/tt')})
            if not links:
                log.debug('section %s does not have links' % section)
            for link in links:
                # skip links with div as a parent (not movies, somewhat rare links in additional details)
                if link.parent.name==u'div': 
                    continue
                    
                # skip links without text value, these are small pictures before title
                if not link.string:
                    continue

                #log.debug('processing link %s' % link)
                    
                movie = {}
                additional = re.findall('\((.*?)\)', link.next.next)
                if len(additional) > 0:
                    movie['year'] = filter(unicode.isdigit, additional[0]) # strip non numbers ie. 2008/I
                if len(additional) > 1:
                    movie['type'] = additional[1]
                
                movie['name'] = link.string
                movie['url'] = "http://www.imdb.com" + link.get('href')
                log.debug('processing name: %s url: %s' % (movie['name'], movie['url']))
                # calc & set best matching ratio
                seq = difflib.SequenceMatcher(lambda x: x==' ', movie['name'], name)
                ratio = seq.ratio()
                # check if some of the akas have better ratio
                for aka in link.parent.findAll('em', text=re.compile('".*"')):
                    aka = aka.replace('"', '')
                    seq = difflib.SequenceMatcher(lambda x: x==' ', aka.lower(), name.lower())
                    aka_ratio = seq.ratio() * self.aka_weight
                    if aka_ratio > ratio:
                        log.debug('- aka %s has better ratio %s' % (aka, aka_ratio))
                        ratio = aka_ratio
                # priorize popular titles
                if section!=sections[0]:
                    ratio = ratio * self.unpopular_weight
                else:
                    log.debug('- priorizing popular title')
                # store ratio
                movie['match'] = ratio
                movies.append(movie)

        def cmp_movie(m1, m2):
            return cmp (m2['match'], m1['match'])
        movies.sort(cmp_movie)
        return movies

class ImdbParser:
    """Quick-hack to parse relevant imdb details"""

    yaml_serialized = ['genres', 'languages', 'score', 'votes', 'year', 'plot_outline', 'name']
    
    def __init__(self):
        self.genres = []
        self.languages = []
        self.score = 0.0
        self.votes = 0
        self.year = 0
        self.plot_outline = None
        self.name = None

    def to_yaml(self):
        """Serializes imdb details into yaml compatible structure"""
        d = {}
        for n in self.yaml_serialized:
            d[n] = getattr(self, n)
        return d

    def from_yaml(self, yaml):
        """Builds object from yaml serialized data"""
        undefined = object()
        for n in self.yaml_serialized:
            # undefined check allows adding new fields without breaking things ..
            value = yaml.get(n, undefined)
            if value is undefined: continue
            setattr(self, n, value)

    def parse(self, url):
        try:
            page = urllib2.urlopen(url)
        except ValueError:
            raise ValueError('Invalid url %s' % url)
            
        soup = BeautifulSoup(page)

        # get name
        tag_name = soup.find('h1')
        if tag_name:
            if tag_name.next:
                self.name = tag_name.next.string.strip()
                log.debug('Detected name: %s' % self.name)
        else:
            log.warning('Unable to get name for %s, module needs update?' % url)
            
        # get votes
        tag_votes = soup.find('b', text=re.compile('\d votes'))
        if tag_votes:
            str_votes = ''.join([c for c in tag_votes.string if c.isdigit()])
            self.votes = int(str_votes)
            log.debug('Detected votes: %s' % self.votes)
        else:
            log.warning('Unable to get votes for %s, module needs update?' % url)

        # get score
        tag_score = soup.find('b', text=re.compile('\d.\d/10'))
        if tag_score:
            str_score = tag_score.string
            re_score = re.compile("(\d.\d)\/10")
            match = re_score.search(str_score)
            if match:
                str_score = match.group(1)
                self.score = float(str_score)
                log.debug('Detected score: %s' % self.score)
        else:
            log.warning('Unable to get score for %s, module needs update?' % url)

        # get genres
        for link in soup.findAll('a', attrs={'href': re.compile('^/Sections/Genres/')}):
            # skip links that have javascipr onclick (not in genrelist)
            if 'onclick' in link: 
                continue
            self.genres.append(link.string.lower())

        # get languages
        for link in soup.findAll('a', attrs={'href': re.compile('^/Sections/Languages/')}):
            lang = link.string.lower()
            if not lang in self.languages:
                self.languages.append(lang.strip())

        # get year
        tag_year = soup.find('a', attrs={'href': re.compile('^/Sections/Years/\d*')})
        if tag_year:
            self.year = int(tag_year.string)
            log.debug('Detected year: %s' % self.year)
        else:
            log.warning('Unable to get year for %s, module needs update?' % url)

        # get plot outline
        tag_outline = soup.find('h5', text=re.compile('Plot.*:'))
        if tag_outline:
            if tag_outline.next:
                self.plot_outline = tag_outline.next.string.strip()
                log.debug('Detected plot outline: %s' % self.plot_outline)

        log.debug('Detected genres: %s' % self.genres)
        log.debug('Detected languages: %s' % self.languages)

class FilterImdb:

    """
        This module allows filtering based on IMDB score, votes and genres etc.

        Configuration:
        
            Note: All parameters are optional. Some are mutually exclusive.
        
            min_score: <num>
            min_votes: <num>
            min_year: <num>

            # reject if genre contains any of these
            reject_genres:
                - genre1
                - genre2

            # reject if language contain any of these
            reject_languages:
                - language1

            # accept only this language
            accept_languages:
                - language1

            # filter all entries which are not imdb-compatible
            # this has default value (True) even when key not present
            filter_invalid: True / False

        Entry fields (module developers):
        
            All fields are optional, but lack of required fields will
            result in filtering usually in default configuration (see reject_invalid).
        
            imdb_url       : Most important field, should point to imdb-movie-page (string)
            imdb_score     : Pre-parsed score/rating value (float)
            imdb_votes     : Pre-parsed number of votes (int)
            imdb_year      : Pre-parsed production year (int)
            imdb_genres    : Pre-parsed genrelist (array)
            imdb_languages : Pre-parsed languagelist (array)
            
            Supplying pre-parsed values may avoid checking and parsing from imdb_url.
            So supply them in your input-module if it's practical!
    """

    def register(self, manager, parser):
        manager.register('imdb')

    def validator(self):
        """Validate given configuration"""
        import validator
        imdb = validator.factory('dict')
        imdb.accept('number', key='min_year')
        imdb.accept('number', key='min_votes')
        imdb.accept('number', key='min_score')
        imdb.accept('list', key='reject_genres').accept('text')
        imdb.accept('list', key='reject_languages').accept('text')
        imdb.accept('list', key='accept_languages').accept('text')
        imdb.accept('boolean', key='filter_invalid')
        return imdb

    def imdb_required(self, entry, config):
        """Return True if config contains conditions that are not available in preparsed fields"""
        # TODO: make dict (mapping min_votes <->imdb_votes) and loop it
        # check that entry values are VALID (None is considered as having value, this is a small bug!)
        if 'min_votes' in config and not 'imdb_votes' in entry: return True
        if 'min_score' in config and not 'imdb_score' in entry: return True
        if 'min_year' in config and not 'imdb_year' in entry: return True
        if 'reject_genres' in config and not 'imdb_genres' in entry: return True
        if 'reject_languages' in config and not 'imdb_languages' in entry: return True
        if 'accept_languages' in config and not 'imdb_languages' in entry: return True
        return False
        
    def clean_url(self, url):
        """Cleans imdb url, returns valid clean url or False"""
        m = re.search('(http://.*imdb\.com\/title\/tt\d*\/)', url)
        if m:
            return m.group()
        return False

    def feed_filter(self, feed):
        config = feed.config['imdb']
        for entry in feed.entries:
        
            # sanity checks
            if 'imdb_votes' in entry:
                if not isinstance(entry['imdb_votes'], int):
                    raise ModuleWarning('imdb_votes should be int!')
            if 'imdb_score' in entry:
                if not isinstance(entry['imdb_score'], float):
                    raise ModuleWarning('imdb_score should be float!')
        
            # make sure imdb url is valid
            if 'imdb_url' in entry:
                clean = self.clean_url(entry['imdb_url'])
                if not clean:
                    del(entry['imdb_url'])
                else:
                    entry['imdb_url'] = clean

            # if no url for this entry, look from cache and try to use imdb search
            if not entry.get('imdb_url'):
                cached = feed.shared_cache.get(entry['title'])
                if cached == 'WILL_FAIL':
                    # this movie cannot be found, not worth trying again ...
                    log.debug('%s will fail search, filtering' % entry['title'])
                    feed.filter(entry)
                    continue
                if cached:
                    log.debug('Setting imdb url for %s from cache' % entry['title'])
                    entry['imdb_url'] = cached

            # no imdb url, but information required
            if not entry.get('imdb_url') and self.imdb_required(entry, config):
                # try searching from imdb
                feed.verbose_progress('Searching from imdb %s' % entry['title'])
                movie = {}
                try:
                    search = ImdbSearch()
                    movie = search.smart_match(entry['title'])
                except IOError, e:
                    if hasattr(e, 'reason'):
                        log.error('Failed to reach server. Reason: %s' % e.reason)
                    elif hasattr(e, 'code'):
                        log.error('The server couldn\'t fulfill the request. Error code: %s' % e.code)
                    feed.filter(entry)
                    continue
                if movie:
                    entry['imdb_url'] = movie['url']
                    # store url for this movie, so we don't have to search on every run
                    feed.shared_cache.store(entry['title'], entry['imdb_url'])
                    log.info('Found %s' % (entry['imdb_url']))
                else:
                    feed.log_once('Imdb search failed for %s' % entry['title'], log)
                    # store FAIL for this title
                    feed.shared_cache.store(entry['title'], 'WILL_FAIL')
                    # act depending configuration
                    if config.get('filter_invalid', True):
                        feed.log_once('Filtering %s because of undeterminable imdb url' % entry['title'], log)
                        feed.filter(entry)
                    else:
                        log.debug('Unable to check %s due missing imdb url, configured to pass (filter_invalid is False)' % entry['title'])
                    continue

            imdb = ImdbParser()
            if self.imdb_required(entry, config):
                # check if this imdb page has been parsed & cached
                cached = feed.shared_cache.get(entry['imdb_url'])
                if not cached:
                    feed.verbose_progress('Parsing from imdb %s' % entry['title'])
                    try:
                        imdb.parse(entry['imdb_url'])
                    except UnicodeDecodeError:
                        log.error('Unable to determine encoding for %s. Installing chardet library may help.' % entry['imdb_url'])
                        feed.filter(entry)
                        # store cache so this will be skipped
                        feed.shared_cache.store(entry['imdb_url'], imdb.to_yaml())
                        continue
                    except ValueError:
                        log.error('Invalid parameter: %s' % entry['imdb_url'])
                        feed.filter(entry)
                        continue
                    except IOError, e:
                        if hasattr(e, 'reason'):
                            log.error('Failed to reach server. Reason: %s' % e.reason)
                        elif hasattr(e, 'code'):
                            log.error('The server couldn\'t fulfill the request. Error code: %s' % e.code)
                        feed.filter(entry)
                        continue
                    except Exception, e:
                        feed.filter(entry)
                        log.error('Unable to process url %s' % entry['imdb_url'])
                        log.exception(e)
                        continue
                else:
                    imdb.from_yaml(cached)
                # store to cache
                feed.shared_cache.store(entry['imdb_url'], imdb.to_yaml())
            else:
                # Set few required fields manually from entry, and thus avoiding request & parse
                # Note: It doesn't matter even if some fields are missing, previous imdb_required
                # checks that those aren't required in condition check. So just set them all! :)
                imdb.votes = entry.get('imdb_votes', 0)
                imdb.score = entry.get('imdb_score', 0.0)
                imdb.year = entry.get('imdb_year', 0)
                imdb.languages = entry.get('imdb_languages', [])
                imdb.genres = entry.get('imdb_genres', [])

            # Check defined conditions, TODO: rewrite into functions?
            
            reasons = []
            if 'min_score' in config:
                if imdb.score < config['min_score']:
                    reasons.append('min_score (%s < %s)' % (imdb.score, config['min_score']))
            if 'min_votes' in config:
                if imdb.votes < config['min_votes']:
                    reasons.append('min_votes (%s < %s)' % (imdb.votes, config['min_votes']))
            if 'min_year' in config:
                if imdb.year < config['min_year']:
                    reasons.append('min_year')
            if 'reject_genres' in config:
                rejected = config['reject_genres']
                for genre in imdb.genres:
                    if genre in rejected:
                        reasons.append('reject_genres')
                        break
            if 'reject_languages' in config:
                rejected = config['reject_languages']
                for language in imdb.languages:
                    if language in rejected:
                        reasons.append('relect_languages')
                        break
            if 'accept_languages' in config:
                accepted = config['accept_languages']
                for language in imdb.languages:
                    if language not in accepted:
                        reasons.append('accept_languages')
                        break

            # populate some fields from imdb results, incase someone wants to use them later
            entry['imdb_plot_outline'] = imdb.plot_outline
            entry['imdb_name'] = imdb.name

            if reasons:
                feed.log_once('Filtering %s because of rule(s) %s' % (entry['title'], string.join(reasons, ', ')), log)
                feed.filter(entry)
            else:
                log.debug('Accepting %s' % (entry))
                feed.accept(entry)

            # give imdb a little break between requests (see: http://flexget.com/ticket/129#comment:1)
            # TODO: improve ?
            if not feed.manager.options.debug:
                time.sleep(3)