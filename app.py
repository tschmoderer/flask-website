import sqlite3, json
from flask import Flask, render_template, request, url_for, flash, redirect, jsonify, make_response
from werkzeug.exceptions import abort
import musicbrainzngs
from musicdb import *
import os.path
import random
import networkx
import community
import matplotlib.colors as mpcolors
import matplotlib.cm as mpcm
from fa2 import ForceAtlas2

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

@app.route('/artist/full', methods=('GET',))
def artist_full():
    return render_template('artist/full.html')

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

@app.route('/artist/full/data.json', methods=('GET',))
def get_full_graph():
    database   = sqlite3.connect('music-database.db')
    db_cursor = database.cursor()

    db_cursor.execute("""SELECT artist1Id, artist2Id, count(*) as nb from featuring GROUP by artist1Id, artist2Id;""") # il y a pleins de doublons !!
    edges = db_cursor.fetchall()
    # e[0]: src node id, e[1]: dst node id, e[2]: weight int 

    db_cursor.execute("""
        SELECT ROW_NUMBER () OVER (ORDER BY artist_mbid) id, artist_mbid, name
        FROM artists""")
    nodes = db_cursor.fetchall()

    data = {
        "nodes": [],
        "edges": []
    }

    for n in nodes:
        data["nodes"].append(
            {'id': str(n[1]),
            'label': n[2], 
            'color': "rgb(" + str(random.randint(0, 255)) + "," + str(random.randint(0, 255))+"," +str(random.randint(0, 255))+")",
            'size': 100, 
            'x':random.randint(-10, 10),
            'y':random.randint(-10, 10)
            })
    k = 0
    for e in edges:
        data["edges"].append(
        {
            'id': str(k),
            'label': str(e[2]) + ' feat(s)',
            'source': e[0],
            'target': e[1],
            'size': e[2]*5,
        })
        k += 1
    
    G = networkx.Graph()
    for n in data['nodes']:
        G.add_node(n['id'], name=n['label'])
    for e in data['edges']:
        G.add_edge(e['source'], e['target'])
    part = community.best_partition(G, randomize=True)
    part = community.best_partition(G, partition=part)

    modularity = {}
    for p in part: 
        modularity[part[p]] = {'name': 'empty', 'id_max_w': 0}
    
    for p in part:
        mod_class = part[p]
        nd_degree = G.degree(p)
        if (nd_degree >= modularity[mod_class]['id_max_w']):
            modularity[mod_class]['id_max_w'] = nd_degree
            modularity[mod_class]['name'] = G.nodes[p]['name']

    cmap = mpcm.get_cmap('tab20c')
    for n in data['nodes']:
        n['color'] = mpcolors.rgb2hex(cmap(part[n['id']]))
        n['attributes'] = {'Modularity Class': modularity[part[n['id']]]['name']}
        n['size'] = G.degree(n['id'])*10
    
    forceatlas2 = ForceAtlas2(
        # Behavior alternatives
        outboundAttractionDistribution=True,  # Dissuade hubs
        linLogMode=False,  # NOT IMPLEMENTED
        adjustSizes=False,  # Prevent overlap (NOT IMPLEMENTED)
        edgeWeightInfluence=0, # 0 or 1?

        # Performance
        jitterTolerance=1.0,  # Tolerance
        barnesHutOptimize=True,
        barnesHutTheta=1.2,
        multiThreaded=False,  # NOT IMPLEMENTED

        # Tuning
        scalingRatio=2.0,
        strongGravityMode=False,
        gravity=1.0,

        # Log
        verbose=True)
    positions = forceatlas2.forceatlas2_networkx_layout(G, pos=None, iterations=100)

    for n in data['nodes']:
        n['x'] = positions[n['id']][0]
        n['y'] = positions[n['id']][1]

    database.close()
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
    app.run(host='0.0.0.0')