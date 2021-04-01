# -*- coding: utf-8 -*-

import musicbrainzngs
import sys
import sqlite3

#musicbrainzngs.set_useragent("dbchart", "0.1", "https://github.com/tschmoderer/musicdb/",)
#database = sqlite3.connect('database.db')

def init_db(db = None):
    if db == None: 
        sys.exit("Error with database initialisation")
    
    cursor = db.cursor()
    # cursor.execute("""DROP TABLE IF EXISTS artists""")
    # cursor.execute("""DROP TABLE IF EXISTS featuring""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS artists(
            artist_mbid TEXT PRIMARY KEY,
            name TEXT,
            treated BOOLEAN NOT NULL DEFAULT FALSE)""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS featuring(
            id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
            artist1Id REFERENCES artists(id),
            artist2Id REFERENCES artists(id),
            title TEXT, 
            artistcredit TEXT, 
            recording_mbid TEXT)""")
    db.commit()
    return cursor

def create_nodes(db = None): 
    if db == None: 
        sys.exit("Error with database creation of nodes")
    
    cursor = db.cursor()
    cursor.execute("""DROP TABLE IF EXISTS nodes""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nodes(
        id TEXT,
        label TEXT,
        FOREIGN KEY(id) REFERENCES artists(artist_mbid)
        );
        """)
    cursor.execute("""
        insert into nodes select artist_mbid as id, name as label from artists 
        where id in (select artist1Id from featuring) 
                or id in (select artist2Id from featuring);""")
    db.commit()

def create_edges(db = None): 
    if db == None: 
        sys.exit("Error with database creation of edges")
    
    cursor = db.cursor()
    cursor.execute("""DROP TABLE IF EXISTS edges""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS edges(
        id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE, 
        source TEXT,
        target TEXT,
        label TEXT,
        FOREIGN KEY(source) REFERENCES artists(artist_mbid),
        FOREIGN KEY(target) REFERENCES artists(artist_mbid)
        );
        """)
    cursor.execute("""
        insert into edges(source, target, label) SELECT DISTINCT artist1Id as source, artist2Id as target, title as label FROM featuring
    """)
    db.commit()

def download_tracks(artist = None):
    if artist == None: 
        sys.exit("You must provide a valid artist in order to download its tracks")   
    limit  = 100
    offset = 0
    releasegrp  = []
    release = []
    tracks  = []

    # download all releases of type album linked to seed
    relizegrp = musicbrainzngs.browse_release_groups(artist=artist, release_type=['album'], includes=[], limit=limit, offset=offset)
    releasegrp += relizegrp['release-group-list']
    count_current = len(relizegrp['release-group-list'])
    while (count_current < relizegrp['release-group-count']):
        offset += limit
        relizegrp = musicbrainzngs.browse_release_groups(artist=artist, release_type=['album'], includes=[], limit=limit, offset=offset)
        releasegrp += relizegrp['release-group-list']
        count_current += len(relizegrp['release-group-list'])

    # for each release take the first album
    for rgrp in releasegrp:
        relize = musicbrainzngs.browse_releases(release_group=rgrp['id'], release_status=['official'], release_type=['album'], includes=[], limit=1, offset=0)
        release += relize['release-list']

    # for each album download its tracks 
    for r in release: 
        offset = 0
        rcrdng = musicbrainzngs.browse_recordings(release=r['id'], includes=['artist-credits'], limit=limit, offset=offset) 
        tracks += rcrdng['recording-list']
        count_current = len(rcrdng['recording-list'])
        while (count_current < rcrdng['recording-count']):
            offset += limit
            rcrdng = musicbrainzngs.browse_recordings(release=r['id'], includes=['artist-credits'], limit=limit, offset=offset) 
            tracks += rcrdng['recording-list']
            count_current += len(rcrdng['recording-list'])
    
    return tracks

def add_artist_featurings(artist = None, cursor = None, database = None): 
    if cursor == None: 
        sys.exit("You must provide a cursor")
    if artist == None: 
        sys.exit("You must provide a valid artist")   

    tracks = download_tracks(artist)
    for tr in tracks: 
        for a in tr['artist-credit']:
            if 'artist' in a:
                try:
                    cursor.execute("""INSERT INTO artists(artist_mbid, name) VALUES(?, ?)""", (a['artist']['id'],a['artist']['name']))
                except sqlite3.IntegrityError:
                    pass
                    # print(a['artist']['name'] + ' already in database.')
                database.commit()

        if len(tr['artist-credit']) > 1:
            try: 
                assert(len(tr['artist-credit']) > 2)
                artist1Id = tr['artist-credit'][0]['artist']['id']
                tr['artist-credit'].pop(0)
                for dd in tr['artist-credit']:
                    if 'artist' in dd:
                        cursor.execute("""INSERT INTO featuring(artist1Id, artist2Id, title, artistcredit, recording_mbid) VALUES(?,?,?,?,?)""",
                        (artist1Id,dd['artist']['id'],tr['title'],tr['artist-credit-phrase'],tr['id']))
                        database.commit()

            except AssertionError:
                print('ERROR with ' + tr['artist-credit-phrase'])
    
    # mark the artist as treated in the database
    cursor.execute("""UPDATE artists SET treated = TRUE where artist_mbid = ?""", (artist,))
    database.commit()

def search_artist(txt = None):
    return musicbrainzngs.search_artists(query=txt, limit=5, offset=0, strict=False)

if __name__ == '__main__':
    # initialize database
    cursor = init_db(db=database)

    # seed
    # seeds = ['b97677ab-8c5d-40ea-a5e4-f501997597d7','b97677ab-8c5d-40ea-a5e4-f501997597d7', '93a128e6-80eb-49b3-ab77-485518a0c45e', '6cad3ce5-6380-4594-a8da-ae7d273b683d', 'e52815f0-0db9-49b2-acb7-1af6b2dfa936', '8e6c44df-06fc-4852-83d0-ef0efed6630a', 'cf33388f-96db-4f15-83eb-f5faacbf8f99']
    # for seed in seeds: 
    #     add_artist_featurings(seed, cursor) 
    
    # cursor.execute("""SELECT artist_mbid, name FROM artists WHERE treated = FALSE""")
    # rows = cursor.fetchall()
    # count = 0
    # for row in rows: 
    #    count += 1
    #    print("Treat artist " + str(count) + " / " + str(len(rows)) + " : " + row[1])
    #    add_artist_featurings(row[0], cursor) 

    txt = input("Search an artist name: ")
    results = search_artist(txt)

    if (results['artist-count'] == 0):
        print("no result found")
    else:
        print("\nResults:")
        k = 0
        for artist in results['artist-list']:
            print("[" + str(k) + "]: " + artist['name'])
            k += 1
        txt = input("\nSelect an artist: ")

        theartist = results['artist-list'][int(txt)]
        cursor.execute("""SELECT artist_mbid, name, treated FROM artists WHERE artist_mbid = ?""", (theartist['id'],))
        theartistdb = cursor.fetchall()

        if (len(theartistdb) == 0) or (theartistdb[0][2] == 0): # l'artiste n'est pas dans la db ou il n'a pas encore été traité
            add_artist_featurings(theartist['id'], cursor) 
        
        # create graph from the values of this artist 
        cursor.execute("""SELECT * FROM featuring WHERE artist1Id = ? OR artist2Id = ?""", (theartist['id'],theartist['id'],))
        edges = cursor.fetchall()

        cursor.execute("""
            SELECT * from artists WHERE
	            artist_mbid IN (
                    SELECT artist1Id FROM featuring WHERE artist1Id = ? or artist1Id = ?) OR
	            artist_mbid IN (
                    SELECT artist2Id FROM featuring where artist1Id = ? or artist2Id = ?)"""
                , (theartist['id'],theartist['id'],theartist['id'],theartist['id'],))
        nodes = cursor.fetchall()

    # TODO: create json files for sigma.js and serve this

    # Create data for gephi
    create_nodes(database)
    create_edges(database)

    # close databse
    database.close()