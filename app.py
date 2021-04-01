import sqlite3, json
from flask import Flask, render_template, request, url_for, flash, redirect, jsonify, make_response
from werkzeug.exceptions import abort
import musicbrainzngs
from musicdb import *
import os.path
import random

musicbrainzngs.set_useragent("dbchart", "0.1", "https://github.com/tschmoderer/musicdb/",)

app = Flask(__name__, static_url_path='/static')
try:
    app.config.from_pyfile('config.py')
except:
    app.config.from_pyfile('config.default.py')

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_post(post_id):
    conn = get_db_connection()
    post = conn.execute('SELECT * FROM posts WHERE id = ?',
                        (post_id,)).fetchone()
    conn.close()
    if post is None:
        abort(404)
    return post

@app.route('/')
def index():
    conn = get_db_connection()
    posts = conn.execute('SELECT * FROM posts').fetchall()
    conn.close()
    return render_template('index.html', posts=posts)

@app.route('/<int:post_id>')
def post(post_id):
    post = get_post(post_id)
    return render_template('post.html', post=post)

@app.route('/create', methods=('GET', 'POST'))
def create():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        if not title:
            flash('Title is required!')
        else:
            conn = get_db_connection()
            conn.execute('INSERT INTO posts (title, content) VALUES (?, ?)',
                         (title, content))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))

    return render_template('create.html')

@app.route('/<int:id>/edit', methods=('GET', 'POST'))
def edit(id):
    post = get_post(id)

    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        if not title:
            flash('Title is required!')
        else:
            conn = get_db_connection()
            conn.execute('UPDATE posts SET title = ?, content = ?'
                         ' WHERE id = ?',
                         (title, content, id))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))

    return render_template('edit.html', post=post)

@app.route('/<int:id>/delete', methods=('POST',))
def delete(id):
    post = get_post(id)
    conn = get_db_connection()
    conn.execute('DELETE FROM posts WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('"{}" was successfully deleted!'.format(post['title']))
    return redirect(url_for('index'))
    
    
@app.route('/artist', methods=('GET',))
def artist_main():
    return render_template('artist/home.html')

@app.route('/artist/search/<string:query>', methods=('GET',))
def search_artist(query):
    data = {
        "errors": [],
        "results": []
    }
    if (query == None) or (query == ''):
        # Default page 
        data["errors"].append({'err': True, 'err-message': 'No valid artist search'})
    else:
        res  = musicbrainzngs.search_artists(query=query, limit=5, offset=0, strict=False)
        if (res['artist-count'] != 0):
            data['errors'].append({'err': False})
            print("\nResults:")
            k = 0
            for artist in res['artist-list']:
                data["results"].append({'name': artist['name'], 'id': artist['id']})
                print("[" + str(k) + "]: " + artist['name'])
                k += 1
        else:
            data["errors"].append({'err': True, 'err-message': 'No results found for ' + query})

    print(data)
    return jsonify(data)


@app.route('/artist/<uuid:artist_id>/data.json', methods=('GET',))
def generate_artist_data(artist_id):
    if not os.path.exists('music-database.db'):
        database   = sqlite3.connect('music-database.db')
        db_cursor = database.cursor()
        db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS artists(
                artist_mbid TEXT PRIMARY KEY,
                name TEXT,
                treated BOOLEAN NOT NULL DEFAULT FALSE)""")
        db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS featuring(
                id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
                artist1Id REFERENCES artists(id),
                artist2Id REFERENCES artists(id),
                title TEXT, 
                artistcredit TEXT, 
                recording_mbid TEXT)""")
        database.commit()
    else:
        database  = sqlite3.connect('music-database.db')
        db_cursor = database.cursor()
    
    theartistdb = db_cursor.execute("""SELECT artist_mbid, name, treated FROM artists WHERE artist_mbid = ?""", (str(artist_id),)).fetchall()
    if (len(theartistdb) == 0) or (theartistdb[0][2] == 0): # l'artiste n'est pas dans la db ou il n'a pas encore été traité
        add_artist_featurings(artist=str(artist_id), cursor=db_cursor, database=database) 
        
    db_cursor.execute("""SELECT * FROM featuring WHERE artist1Id = ? OR artist2Id = ?""", (str(artist_id),str(artist_id),))
    edges = db_cursor.fetchall()

    db_cursor.execute("""
        SELECT ROW_NUMBER () OVER (ORDER BY artist_mbid) id, artist_mbid, name
        FROM artists WHERE
            artist_mbid IN (
                SELECT artist1Id FROM featuring WHERE artist1Id = ? or artist2Id = ?) OR
            artist_mbid IN (
                SELECT artist2Id FROM featuring where artist1Id = ? or artist2Id = ?)"""
            , (str(artist_id), str(artist_id), str(artist_id), str(artist_id),))
    nodes = db_cursor.fetchall()

    data = {
        "nodes": [],
        "edges": []
    }

    for n in nodes:
        if n[1] == str(artist_id):
            data["nodes"].append(
                {'id': str(n[1]),
                'label': n[2], 
                'color': "rgb(255,45,0)", 
                'size': 100, 
                'x':random.randint(-10, 10),
                'y':random.randint(-10, 10)
                })
        else:
            data["nodes"].append(
                {'id': str(n[1]),
                'label': n[2], 
                'color': "rgb(90,90,90)", 
                'size': 100, 
                'x':random.randint(-10, 10),
                'y':random.randint(-10, 10)
                })
    
    for e in edges:
        data["edges"].append(
        {
            'id': str(e[0]),
            'label': e[3],
            'source': e[1],
            'target': e[2],
            'color': 'rgb(0,0,0)'
        })

        # data["edges"].append({'label': , 'source': , 'target': ,'color': rgb(int,int,int)})

    print(nodes)

    database.close()
    return jsonify(data)


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)