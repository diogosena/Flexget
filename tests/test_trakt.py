from __future__ import unicode_literals, division, absolute_import

from flexget.manager import Session
from flexget.plugins.api_trakt import ApiTrakt, TraktActor
from tests import FlexGetBase, use_vcr


lookup_series = ApiTrakt.lookup_series


class TestTraktShowLookup(FlexGetBase):
    __yaml__ = """
        templates:
          global:
            trakt_lookup: yes
            # Access a tvdb field to cause lazy loading to occur
            set:
              afield: "{{tvdb_id}}{{trakt_ep_name}}"
        tasks:
          test:
            mock:
              - {title: 'House.S01E02.HDTV.XViD-FlexGet'}
              - {title: 'Doctor.Who.2005.S02E03.PDTV.XViD-FlexGet'}
            series:
              - House
              - Doctor Who 2005
          test_unknown_series:
            mock:
              - {title: 'Aoeu.Htns.S01E01.htvd'}
            series:
              - Aoeu Htns
          test_date:
            mock:
              - title: the daily show 2012-6-6
            series:
              - the daily show (with jon stewart)
          test_absolute:
            mock:
              - title: naruto 128
            series:
              - naruto
    """

    @use_vcr
    def test_lookup_name(self):
        """trakt: Test Lookup (ONLINE)"""
        self.execute_task('test')
        entry = self.task.find_entry(title='House.S01E02.HDTV.XViD-FlexGet')
        assert entry['trakt_show_id'] == 1399, \
            'Trakt_ID should be 1339 is %s for %s' % (entry['trakt_show_id'], entry['series_name'])
        assert entry['trakt_series_status'] == 'ended', 'Series Status should be "ENDED" returned %s' \
                                                        % (entry['trakt_series_status'])

    @use_vcr
    def test_lookup(self):
        """trakt: Test Lookup (ONLINE)"""
        self.execute_task('test')
        entry = self.task.find_entry(title='House.S01E02.HDTV.XViD-FlexGet')
        assert entry['trakt_ep_name'] == 'Paternity', \
            '%s trakt_ep_name should be Paternity' % entry['title']
        assert entry['trakt_series_status'] == 'ended', \
            'runtime for %s is %s, should be "ended"' % (entry['title'], entry['trakt_series_status'])
        assert entry['afield'] == '73255Paternity', 'afield was not set correctly'
        assert self.task.find_entry(trakt_ep_name='School Reunion'), \
            'Failed imdb lookup Doctor Who 2005 S02E03'

    @use_vcr
    def test_unknown_series(self):
        # Test an unknown series does not cause any exceptions
        self.execute_task('test_unknown_series')
        # Make sure it didn't make a false match
        entry = self.task.find_entry('accepted', title='Aoeu.Htns.S01E01.htvd')
        assert entry.get('tvdb_id') is None, 'should not have populated tvdb data'

    # @use_vcr
    # def test_date(self):
    #     self.execute_task('test_date')
    #     entry = self.task.find_entry(title='the daily show 2012-6-6')
    #     # TODO what is the point of this test?
    #     # assert entry.get('tvdb_id') is None, 'should not have populated trakt data'
    #
    # @use_vcr
    # def test_absolute(self):
    #     self.execute_task('test_absolute')
    #     entry = self.task.find_entry(title='naruto 128')
    #     # assert entry.get('tvdb_id') is None, 'should not have populated trakt data'

    @use_vcr
    def test_lookup_actors(self):
        self.execute_task('test')
        actors = ['Hugh Laurie',
                  'Jesse Spencer',
                  'Jennifer Morrison',
                  'Omar Epps',
                  'Robert Sean Leonard',
                  'Peter Jacobson',
                  'Olivia Wilde',
                  'Odette Annable',
                  'Charlyne Yi',
                  'Anne Dudek',
                  'Kal Penn',
                  'Jennifer Crystal Foley',
                  'Bobbin Bergstrom',
                  'Sela Ward']
        entry = self.task.find_entry(title='House.S01E02.HDTV.XViD-FlexGet')
        trakt_actors = entry['trakt_series_actors'].values()
        trakt_actors = [trakt_actor['name'] for trakt_actor in trakt_actors]
        assert entry['series_name'] == 'House', 'series lookup failed'
        assert set(trakt_actors) == set(actors), 'looking up actors for %s failed' % entry.get('title')
        assert entry['trakt_series_actors']['297390']['name'] == 'Hugh Laurie', 'trakt id mapping failed'
        assert entry['trakt_series_actors']['297390']['imdb_id'] == 'nm0491402', 'fetching imdb id for actor failed'
        assert entry['trakt_series_actors']['297390']['tmdb_id'] == '41419', 'fetching tmdb id for actor failed'
        with Session() as session:
            actor = session.query(TraktActor).filter(TraktActor.name == 'Hugh Laurie').first()
            assert actor is not None, 'adding actor to actors table failed'
            assert actor.imdb_id == 'nm0491402', 'saving imdb_id for actors in table failed'
            assert actor.trakt_id == '297390', 'saving trakt_id for actors in table failed'
            assert actor.tmdb_id == '41419', 'saving tmdb_id for actors table failed'


class TestTraktList(FlexGetBase):
    __yaml__ = """
        tasks:
          test_trakt_movies:
            trakt_list:
              username: flexgettest
              list: watchlist
              type: movies
    """

    @use_vcr
    def test_trakt_movies(self):
        self.execute_task('test_trakt_movies')
        assert len(self.task.entries) == 1
        entry = self.task.entries[0]
        assert entry['title'] == '12 Angry Men (1957)'
        assert entry['movie_name'] == '12 Angry Men'
        assert entry['movie_year'] == 1957
        assert entry['imdb_id'] == 'tt0050083'


class TestTraktWatched(FlexGetBase):
    __yaml__ = """
        tasks:
          test_trakt_watched:
            metainfo_series: yes
            mock:
              - {title: 'Hawaii.Five-0.S04E13.HDTV-FlexGet'}
            if:
              - trakt_watched: accept
            trakt_watched_lookup:
              username: flexgettest
              type: shows
    """

    @use_vcr
    def test_trakt_watched_lookup(self):
        self.execute_task('test_trakt_watched')
        assert len(self.task.accepted) == 1
        entry = self.task.accepted[0]
        assert entry['title'] == 'Hawaii.Five-0.S04E13.HDTV-FlexGet', 'title was not accepted?'
        assert entry['series_name'] == 'Hawaii Five-0', 'wrong series was accepted'
        assert entry['trakt_watched'] == True, 'episode should be marked as watched'


class TestTraktMovieLookup(FlexGetBase):
    __yaml__ = """
        templates:
          global:
            trakt_lookup: yes
        tasks:
          test_lookup_sources:
            mock:
            - title: trakt id
              trakt_movie_id: 481
            - title: tmdb id
              tmdb_id: 603
            - title: imdb id
              imdb_id: tt0133093
            - title: slug
              trakt_movie_slug: the-matrix-1999
            - title: movie_name and movie_year
              movie_name: The Matrix
              movie_year: 1999
            - title: The Matrix (1999)
          test_lookup_actors:
            mock:
            - title: The Matrix (1999)
    """

    @use_vcr
    def test_lookup_sources(self):
        self.execute_task('test_lookup_sources')
        for e in self.task.all_entries:
            assert e['movie_name'] == 'The Matrix', 'looking up based on %s failed' % e['title']

    @use_vcr
    def test_lookup_actors(self):
        self.execute_task('test_lookup_actors')
        assert len(self.task.entries) == 1
        entry = self.task.entries[0]
        actors = ['Keanu Reeves',
                  'Laurence Fishburne',
                  'Carrie-Anne Moss',
                  'Hugo Weaving',
                  'Gloria Foster',
                  'Joe Pantoliano',
                  'Marcus Chong',
                  'Julian Arahanga',
                  'Matt Doran',
                  'Belinda McClory',
                  'Anthony Ray Parker',
                  'Paul Goddard',
                  'Robert Taylor',
                  'David Aston',
                  'Marc Aden',
                  'Ada Nicodemou',
                  'Deni Gordon',
                  'Rowan Witt',
                  'Bill Young',
                  'Eleanor Witt',
                  'Tamara Brown',
                  'Janaya Pender',
                  'Adryn White',
                  'Natalie Tjen',
                  'David O\'Connor',
                  'Jeremy Ball',
                  'Fiona Johnson',
                  'Harry Lawrence',
                  'Steve Dodd',
                  'Luke Quinton',
                  'Lawrence Woodward',
                  'Michael Butcher',
                  'Bernard Ledger',
                  'Robert Simper',
                  'Chris Pattinson',
                  'Nigel Harbach',
                  'Rana Morrison']
        trakt_actors = entry['trakt_movie_actors'].values()
        trakt_actors = [trakt_actor['name'] for trakt_actor in trakt_actors]
        assert entry['movie_name'] == 'The Matrix', 'movie lookup failed'
        assert set(trakt_actors) == set(actors), 'looking up actors for %s failed' % entry.get('title')
        assert entry['trakt_movie_actors']['7134']['name'] == 'Keanu Reeves', 'trakt id mapping failed'
        assert entry['trakt_movie_actors']['7134']['imdb_id'] == 'nm0000206', 'fetching imdb id for actor failed'
        assert entry['trakt_movie_actors']['7134']['tmdb_id'] == '6384', 'fetching tmdb id for actor failed'
        with Session() as session:
            actor = session.query(TraktActor).filter(TraktActor.name == 'Keanu Reeves').first()
            assert actor is not None, 'adding actor to actors table failed'
            assert actor.imdb_id == 'nm0000206', 'saving imdb_id for actors in table failed'
            assert actor.trakt_id == '7134', 'saving trakt_id for actors in table failed'
            assert actor.tmdb_id == '6384', 'saving tmdb_id for actors table failed'
