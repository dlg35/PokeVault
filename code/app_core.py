import sys, sqlite3, json, urllib.parse, urllib.request, hashlib, shutil, datetime, os, time, unicodedata, logging, re, csv
from pathlib import Path
from PySide6.QtCore import Qt, QEvent, QThread, Signal, QTimer, QStringListModel
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont, QIcon, QPainterPath, QLinearGradient, QFontMetrics
from PySide6.QtWidgets import (QCompleter,QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,QLabel,QTableWidget,QTableWidgetItem,QTabWidget,QSpinBox,QComboBox,QMessageBox,QHeaderView,QDialog,QFormLayout,QAbstractItemView,QScrollArea,QGridLayout,QFrame,QSizePolicy,QListWidget,QStackedWidget,QFileDialog,QDialogButtonBox,QInputDialog,QMenu,QToolButton)

DATA=Path.home()/'.pokevault'; DATA.mkdir(exist_ok=True)
DB=DATA/'collection.db'; CACHE=DATA/'images'; CACHE.mkdir(exist_ok=True)
BACKUPS=DATA/'backups'; BACKUPS.mkdir(exist_ok=True)
logging.basicConfig(filename=str(DATA/'pokevault.log'), level=logging.WARNING, format='%(asctime)s %(levelname)s %(message)s')
APP_VERSION='5.2.0'
CARDTRADER_TOKEN_FILE=DATA/'cardtrader_token'

def load_cardtrader_token():
    try:
        if not CARDTRADER_TOKEN_FILE.is_file():return ''
        os.chmod(CARDTRADER_TOKEN_FILE,0o600)
        return CARDTRADER_TOKEN_FILE.read_text(encoding='utf-8').strip()
    except OSError:
        logging.exception('No se pudo leer el token local de CardTrader')
        return ''

def save_cardtrader_token(token):
    token=str(token or '').strip()
    if not token:raise ValueError('El token está vacío')
    fd=os.open(str(CARDTRADER_TOKEN_FILE),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    try:
        if hasattr(os,'fchmod'):os.fchmod(fd,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as saved:saved.write(token)
    except Exception:
        try:os.close(fd)
        except OSError:pass
        raise

def delete_cardtrader_token():
    CARDTRADER_TOKEN_FILE.unlink(missing_ok=True)

def cardtrader_records(payload, endpoint):
    """Accept CardTrader list responses and common keyed/wrapped JSON variants."""
    if isinstance(payload,list):rows=payload
    elif isinstance(payload,dict):
        rows=None
        for key in ('results','data','items'):
            nested=payload.get(key)
            if isinstance(nested,list):rows=nested;break
            if isinstance(nested,dict):rows=list(nested.values());break
        if rows is None and all(isinstance(value,(dict,list)) for value in payload.values()):
            rows=[]
            for value in payload.values():rows.extend(value if isinstance(value,list) else [value])
        if rows is None:raise ValueError('Respuesta inesperada de CardTrader en '+endpoint+'.')
    else:raise ValueError('Respuesta inesperada de CardTrader en '+endpoint+'.')
    records=[row for row in rows if isinstance(row,dict)]
    if rows and not records:raise ValueError('CardTrader devolvió datos sin registros reconocibles en '+endpoint+'.')
    return records

def automatic_backup(db, force=False):
    """Keep a daily, consistent SQLite snapshot before schema changes."""
    if not DB.exists() or DB.stat().st_size == 0: return None
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    recent=[f for f in BACKUPS.glob('auto_*.db') if time.time()-f.stat().st_mtime < 20*3600]
    if recent and not force:return None
    dest=BACKUPS/f'auto_{stamp}.db'
    with sqlite3.connect(str(dest)) as copy: db.backup(copy)
    old=sorted(BACKUPS.glob('auto_*.db'),key=lambda x:x.stat().st_mtime,reverse=True)
    for extra in old[10:]:extra.unlink(missing_ok=True)
    return dest


def connect(db_path=DB,make_backup=True):
    db=sqlite3.connect(db_path, timeout=15)
    if make_backup and Path(db_path).resolve()==DB.resolve():automatic_backup(db)
    db.execute('''CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT NOT NULL, name TEXT NOT NULL, set_name TEXT, number TEXT, image TEXT, language TEXT, condition TEXT, variant TEXT, quantity INTEGER NOT NULL DEFAULT 1, physical_print_key TEXT NOT NULL DEFAULT '', UNIQUE(card_id,language,condition,variant,physical_print_key))''')
    card_columns={row[1] for row in db.execute('PRAGMA table_info(cards)').fetchall()}
    if 'physical_print_key' not in card_columns:
        db.execute('ALTER TABLE cards RENAME TO cards_old_schema')
        db.execute('''CREATE TABLE cards (id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT NOT NULL, name TEXT NOT NULL, set_name TEXT, number TEXT, image TEXT, language TEXT, condition TEXT, variant TEXT, quantity INTEGER NOT NULL DEFAULT 1, physical_print_key TEXT NOT NULL DEFAULT '', UNIQUE(card_id,language,condition,variant,physical_print_key))''')
        db.execute('''INSERT INTO cards(id,card_id,name,set_name,number,image,language,condition,variant,quantity,physical_print_key)
            SELECT id,card_id,name,set_name,number,image,language,condition,variant,quantity,'' FROM cards_old_schema''')
        db.execute('DROP TABLE cards_old_schema')
    # En versiones anteriores set_name se guardaba vacío. Se conserva el dato
    # sin modificarlo; el orden por expansión usa el identificador si falta.
    db.execute('''CREATE TABLE IF NOT EXISTS card_prices (card_id TEXT PRIMARY KEY, trend REAL, low REAL, avg REAL, avg1 REAL, avg7 REAL, avg30 REAL, updated TEXT, fetched_at INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'ok')''')
    db.execute('''CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT NOT NULL, fetched_at INTEGER NOT NULL, price REAL NOT NULL, source_updated TEXT DEFAULT '', UNIQUE(card_id, fetched_at))''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_history_card_time ON price_history(card_id,fetched_at)')
    # 3.0: isolated slots for verified, language+finish-specific quotes.
    # Existing card_prices/price_history remain untouched and are GENERAL references.
    db.execute('''CREATE TABLE IF NOT EXISTS specific_prices (
        card_id TEXT NOT NULL, language TEXT NOT NULL, variant TEXT NOT NULL,
        trend REAL, low REAL, avg REAL, avg1 REAL, avg7 REAL, avg30 REAL,
        updated TEXT, fetched_at INTEGER NOT NULL, status TEXT NOT NULL,
        source TEXT NOT NULL, PRIMARY KEY(card_id,language,variant))''')
    db.execute('''CREATE TABLE IF NOT EXISTS specific_price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT NOT NULL,
        language TEXT NOT NULL, variant TEXT NOT NULL, fetched_at INTEGER NOT NULL,
        price REAL NOT NULL, source_updated TEXT DEFAULT '', source TEXT NOT NULL,
        UNIQUE(card_id,language,variant,fetched_at))''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_specific_history ON specific_price_history(card_id,language,variant,fetched_at)')
    db.execute('''CREATE TABLE IF NOT EXISTS collection_history (id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at INTEGER NOT NULL, total REAL NOT NULL, priced_copies INTEGER NOT NULL, total_copies INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT 'prices')''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_collection_history_time ON collection_history(recorded_at)')
    db.execute('''CREATE TABLE IF NOT EXISTS wishlist (id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT NOT NULL, name TEXT NOT NULL, set_name TEXT DEFAULT '', number TEXT DEFAULT '', image TEXT DEFAULT '', language TEXT NOT NULL, condition TEXT NOT NULL, variant TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1, added_at INTEGER NOT NULL, UNIQUE(card_id,language,condition,variant))''')
    db.execute('''CREATE TABLE IF NOT EXISTS wishlist_albums (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE, created_at INTEGER NOT NULL)''')
    wishlist_columns={row[1] for row in db.execute('PRAGMA table_info(wishlist)').fetchall()}
    if 'album_id' not in wishlist_columns:
        db.execute('ALTER TABLE wishlist ADD COLUMN album_id INTEGER REFERENCES wishlist_albums(id) ON DELETE SET NULL')
    db.execute('CREATE INDEX IF NOT EXISTS idx_wishlist_album ON wishlist(album_id)')
    db.execute('''CREATE TABLE IF NOT EXISTS verified_valuations (
        card_row_id INTEGER PRIMARY KEY, amount REAL NOT NULL, source_url TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS api_valuations (card_row_id INTEGER PRIMARY KEY, product_id TEXT NOT NULL, amount REAL NOT NULL, floor REAL, offers INTEGER, language TEXT NOT NULL, source_url TEXT NOT NULL, fetched_at INTEGER NOT NULL, condition TEXT NOT NULL DEFAULT '', variant TEXT NOT NULL DEFAULT '')''')
    api_columns={row[1] for row in db.execute('PRAGMA table_info(api_valuations)').fetchall()}
    if 'condition' not in api_columns:db.execute("ALTER TABLE api_valuations ADD COLUMN condition TEXT NOT NULL DEFAULT ''")
    if 'variant' not in api_columns:db.execute("ALTER TABLE api_valuations ADD COLUMN variant TEXT NOT NULL DEFAULT ''")
    db.execute('''CREATE TABLE IF NOT EXISTS cardtrader_price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, card_row_id INTEGER NOT NULL,
        fetched_at INTEGER NOT NULL, price REAL NOT NULL, product_id TEXT NOT NULL DEFAULT '',
        condition TEXT NOT NULL DEFAULT '', variant TEXT NOT NULL DEFAULT '',
        UNIQUE(card_row_id,fetched_at))''')
    history_columns={row[1] for row in db.execute('PRAGMA table_info(cardtrader_price_history)').fetchall()}
    if 'product_id' not in history_columns:db.execute("ALTER TABLE cardtrader_price_history ADD COLUMN product_id TEXT NOT NULL DEFAULT ''")
    if 'condition' not in history_columns:db.execute("ALTER TABLE cardtrader_price_history ADD COLUMN condition TEXT NOT NULL DEFAULT ''")
    if 'variant' not in history_columns:db.execute("ALTER TABLE cardtrader_price_history ADD COLUMN variant TEXT NOT NULL DEFAULT ''")
    db.execute('CREATE INDEX IF NOT EXISTS idx_cardtrader_history ON cardtrader_price_history(card_row_id,fetched_at)')
    db.execute('''CREATE TABLE IF NOT EXISTS cardtrader_print_mappings (
        card_row_id INTEGER PRIMARY KEY, expansion_id TEXT NOT NULL,
        expansion_name TEXT NOT NULL, expansion_code TEXT NOT NULL DEFAULT '',
        blueprint_id TEXT NOT NULL, blueprint_name TEXT NOT NULL,
        collector_number TEXT NOT NULL DEFAULT '', language TEXT NOT NULL,
        confirmed INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS cardtrader_lookup_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, card_row_id INTEGER NOT NULL,
        card_id TEXT NOT NULL, language TEXT NOT NULL, attempted_at INTEGER NOT NULL,
        stage TEXT NOT NULL, outcome TEXT NOT NULL, message TEXT NOT NULL DEFAULT '')''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_cardtrader_attempts_row_time ON cardtrader_lookup_attempts(card_row_id,attempted_at)')
    db.execute('''CREATE TABLE IF NOT EXISTS cardtrader_expansion_mappings (
        catalog_language TEXT NOT NULL, source_set_id TEXT NOT NULL,
        catalog_set_id TEXT NOT NULL DEFAULT '', expansion_id TEXT NOT NULL,
        expansion_name TEXT NOT NULL, expansion_code TEXT NOT NULL DEFAULT '',
        updated_at INTEGER NOT NULL, origin TEXT NOT NULL DEFAULT 'auto',
        PRIMARY KEY(catalog_language,source_set_id))''')
    expansion_mapping_columns={row[1] for row in db.execute('PRAGMA table_info(cardtrader_expansion_mappings)').fetchall()}
    if 'origin' not in expansion_mapping_columns:
        db.execute("ALTER TABLE cardtrader_expansion_mappings ADD COLUMN origin TEXT NOT NULL DEFAULT 'auto'")
    db.execute('CREATE INDEX IF NOT EXISTS idx_ct_expansion_catalog_set ON cardtrader_expansion_mappings(catalog_language,catalog_set_id)')
    # Reuse only expansion mappings backed by a valid CardTrader quote for the
    # same confirmed blueprint; never seed from a zero-offer/failed lookup.
    for card_id,language,expansion_id,expansion_name,expansion_code in db.execute('''
        SELECT c.card_id,c.language,m.expansion_id,m.expansion_name,m.expansion_code
        FROM cards c JOIN cardtrader_print_mappings m ON m.card_row_id=c.id
        JOIN api_valuations v ON v.card_row_id=c.id AND v.product_id=m.blueprint_id
        WHERE m.confirmed=1 AND v.source_url LIKE 'https://api.cardtrader.com/api/v2/marketplace/products?%'
    ''').fetchall():
        catalog_language='en' if normalized_name(language)=='espanol' else tcgdex_locale(language)
        source_set_id=str(card_id).rsplit('-',1)[0] if '-' in str(card_id) else str(card_id)
        if catalog_language and source_set_id:
            db.execute('''INSERT OR IGNORE INTO cardtrader_expansion_mappings
                (catalog_language,source_set_id,catalog_set_id,expansion_id,expansion_name,expansion_code,updated_at)
                VALUES(?,?,?,?,?,?,?)''',(catalog_language,source_set_id,'',str(expansion_id),str(expansion_name),str(expansion_code),int(time.time())))
    db.execute('''CREATE TABLE IF NOT EXISTS edition_links (
        card_row_id INTEGER PRIMARY KEY, source_url TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL)''')
    # Los enlaces a ediciones solo se guardan cuando cada usuario los identifica.
    db.execute('''CREATE TRIGGER IF NOT EXISTS cleanup_deleted_card_row
        AFTER DELETE ON cards BEGIN
            DELETE FROM verified_valuations WHERE card_row_id=OLD.id;
            DELETE FROM api_valuations WHERE card_row_id=OLD.id;
            DELETE FROM cardtrader_price_history WHERE card_row_id=OLD.id;
            DELETE FROM cardtrader_print_mappings WHERE card_row_id=OLD.id;
            DELETE FROM cardtrader_lookup_attempts WHERE card_row_id=OLD.id;
            DELETE FROM edition_links WHERE card_row_id=OLD.id;
        END''')
    db.commit();return db

def normalized_name(value):
    """Compare complete Pokémon card names, ignoring case, accents and whitespace."""
    value=unicodedata.normalize('NFKD', str(value or ''))
    value=''.join(ch for ch in value if not unicodedata.combining(ch))
    return ' '.join(value.casefold().split())

def image_urls(base):
    if not base:return []
    base=base.rstrip('/')
    if base.endswith(('.png','.jpg','.jpeg','.webp')):return [base]
    return [base+'/low.webp',base+'/low.png',base+'/high.webp',base+'/high.png']

def fetch_catalog(language, resource, timeout=22):
    """TCGdex public list endpoint; a missing language is not a connection failure."""
    url='https://api.tcgdex.net/v2/'+language+'/'+resource
    req=urllib.request.Request(url,headers={'User-Agent':'PokeVault/3.6','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return json.load(response)

def card_matches(card,term):
    name=normalized_name(card.get('name',''))
    query=normalized_name(term)
    if not query:return True
    return query in name or all(word in name for word in query.split())

class Fetch(QThread):
    done=Signal(object,str)
    def __init__(self,term):super().__init__();self.term=term;self.result=([], '')
    def run(self):
        results={};errors=[];successful=0
        # Download list endpoints without undocumented query parameters.
        # The English index is primary; other languages fill coverage gaps.
        for language in ('en','es','zh-tw','zh-cn','ja'):
            if self.isInterruptionRequested():break
            try:
                cards=fetch_catalog(language,'cards')
                successful+=1
                if not isinstance(cards,list):continue
                for card in cards:
                    if card_matches(card,self.term):
                        cid=card.get('id')
                        if cid:results.setdefault(cid,card)
            except Exception as exc:errors.append(language+': '+str(exc))
        items=sorted(results.values(),key=lambda c:(normalized_name(c.get('name')),c.get('id','')))
        message='' if successful else 'No se pudo acceder al catálogo: '+'; '.join(errors[:2])
        self.result=(items[:1500],message)
        self.done.emit(*self.result)

def euros(value):
    if value is None:return 'Sin precio'
    return f'{value:,.2f} €'.replace(',', 'X').replace('.', ',').replace('X', '.')

def cardtrader_display_amount(amount,floor):
    """Use the cheapest offer when an average is dominated by a price outlier."""
    try:amount=float(amount);floor=float(floor)
    except (TypeError,ValueError):return amount
    return floor if floor>0 and amount>max(floor*10,floor+100) else amount

def market_language(language):
    """Map the collection's language label to Cardmarket API's language slug."""
    value=normalized_name(language)
    return {
        'espanol':'spanish','ingles':'english','japones':'japanese',
        'chino simplificado':'chinese-s','chinese simplified':'chinese-s',
        'chino tradicional':'chinese-t','chinese traditional':'chinese-t',
        'chino':'', 'chino (sin especificar)':'',
    }.get(value,'')

def cardtrader_language(language):
    """Map the collection language to CardTrader's marketplace locale."""
    value=normalized_name(language)
    return {
        'espanol':'es','ingles':'en','japones':'jp',
        'chino simplificado':'zh-CN','chinese simplified':'zh-CN',
        'chino tradicional':'zh-TW','chinese traditional':'zh-TW',
    }.get(value,'')

def cardtrader_query_language(language):
    """Return a marketplace language filter when CardTrader supports it."""
    locale=cardtrader_language(language)
    # CardTrader rejects zh as a marketplace query for Pokémon. Query broadly
    # for Chinese and require the listing itself to identify its script.
    return '' if locale in ('zh-CN','zh-TW') else locale

def cardtrader_finish_filter(variant):
    """Return CardTrader's supported foil filter when the finish is known."""
    value=normalized_name(variant)
    if value=='normal':return False
    if value in ('holo','reverse'):return True
    return None

def cardtrader_offer_compatibility(offer,language,condition,variant,market_locale=None,require_language=False):
    """Fail closed when an offer cannot be matched to the copy's key properties."""
    props=offer.get('properties_hash') or offer.get('properties') or {}
    if not isinstance(props,dict):props={}
    normalized_props={normalized_name(key).replace(' ','_'):value for key,value in props.items()}
    language_value=next((value for key,value in normalized_props.items() if 'language' in key),None)
    expected_language=market_locale or cardtrader_language(language)
    if require_language and language_value is None:return False,'idioma no verificable'
    if language_value is not None and normalize_market_language(language_value)!=normalize_market_language(expected_language):
        return False,'idioma'
    condition_value=next((value for key,value in normalized_props.items() if 'condition' in key),None)
    # CardTrader documents Near Mint as the default when a listing omits its
    # condition property. Treating an omitted property as unknown was hiding
    # valid NM offers from the language-filtered marketplace response.
    if condition_value is None:
        condition_value='Near Mint'
    condition_key=normalized_name(condition_value)
    condition_aliases={
        'near mint':{'near mint','nm'},'excellent':{'excellent','ex'},'good':{'good','gd'},
        'light played':{'light played','lightly played','slightly played','lp','sp'},
        'played':{'played','pl'},'poor':{'poor','damaged','po'},
    }
    aliases=condition_aliases.get(normalized_name(condition),{normalized_name(condition)})
    if condition_key not in aliases:return False,'estado de conservación'
    finish=normalized_name(variant)
    if finish in ('especial','sin verificar',''):return False,'acabado sin identificar'
    foil_value=next((value for key,value in normalized_props.items() if key.endswith('foil') or key=='foil'),None)
    expected_foil=cardtrader_finish_filter(variant)
    if expected_foil is not None and foil_value is not None:
        foil_flag=foil_value if isinstance(foil_value,bool) else str(foil_value).casefold() in ('true','1','yes')
        if foil_flag!=expected_foil:return False,'acabado'
    if finish=='reverse':
        reverse_value=next((value for key,value in normalized_props.items() if 'reverse' in key),None)
        if str(reverse_value).casefold() not in ('true','1','yes','reverse','reverse holo'):
            return False,'acabado reverse no verificable en CardTrader'
    elif finish=='holo':
        reverse_value=next((value for key,value in normalized_props.items() if 'reverse' in key),None)
        if str(reverse_value).casefold() in ('true','1','yes','reverse','reverse holo'):
            return False,'acabado reverse'
    return True,''

def cardtrader_lookup_hint(card_id,name,set_name,number,language):
    """Return a CardTrader expansion and collector-number hint when known."""
    card=normalized_name(name);set_value=normalized_name(set_name);cid=normalized_name(card_id)
    if (normalized_name(language)=='chino simplificado' and card=='sylveon ex'
            and ('sv08.5' in cid or ('156' in str(number) and 'prismatic evolutions' in set_value))):
        return 'Terastal Gathering','233/208'
    expansion=set_name or str(card_id or '').rsplit('-',1)[0]
    return expansion,str(number or '')

def collector_number_matches(text,number):
    value=re.sub(r'\s+','',str(number or ''))
    candidate=re.sub(r'\s+','',str(text or ''))
    if not value:return False
    def number_key(part):
        return str(part).lstrip('0') or '0'
    def digits(part):return re.sub(r'\D','',str(part or ''))
    # Some Simplified Chinese catalogs compress pack/card numbering such as
    # "11 07/07" to "1107"; CardTrader writes the same print as "11-07/07".
    # Compare the number groups on either side of the slash before falling
    # back to an exact numeric token match.
    if '/' in candidate:
        prefix,suffix=candidate.split('/',1)
        prefix_groups=re.findall(r'\d+',prefix)
        suffix_match=re.match(r'(\d+)',suffix)
        if prefix_groups and suffix_match:
            prefix_number=''.join(prefix_groups)
            suffix_number=suffix_match.group(1)
            if '/' in value:
                value_prefix,value_suffix=value.split('/',1)
                if (number_key(digits(prefix_number))==number_key(digits(value_prefix))
                        and number_key(suffix_number)==number_key(digits(value_suffix))):return True
            elif number_key(prefix_number)==number_key(digits(value)):
                return True
    if '/' in value:
        value_parts=value.split('/',1)
        for candidate_parts in re.findall(r'(?<!\d)(\d{1,4})/(\d{1,4})(?!\d)',candidate):
            if (number_key(digits(value_parts[0]))==number_key(candidate_parts[0])
                    and number_key(digits(value_parts[1]))==number_key(candidate_parts[1])):return True
        return False
    value=number_key(digits(value))
    if not value:return False
    return re.search(r'(?<!\d)'+re.escape(value)+r'(?!\d)',candidate) is not None

def tcgdex_locale(language):
    return {'espanol':'es','ingles':'en','japones':'ja','chino simplificado':'zh-cn',
            'chinese simplified':'zh-cn','chino tradicional':'zh-tw','chinese traditional':'zh-tw'}.get(normalized_name(language),'')

def tcgdex_get_card(card_id,language='en',timeout=18):
    url='https://api.tcgdex.net/v2/'+language+'/cards/'+urllib.parse.quote(str(card_id),safe='')
    request=urllib.request.Request(url,headers={'User-Agent':'PokeVault/5.0','Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=timeout) as response:
        data=json.load(response)
    return data if isinstance(data,dict) else None

def tcgdex_get_set(set_id,language='en',timeout=15):
    if not set_id:return None
    url='https://api.tcgdex.net/v2/'+language+'/sets/'+urllib.parse.quote(str(set_id),safe='')
    request=urllib.request.Request(url,headers={'User-Agent':'PokeVault/5.0.1','Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=timeout) as response:
        data=json.load(response)
    return data if isinstance(data,dict) else None

def localized_print_match(source_card,target_card):
    """Return whether two language catalog entries are a strong same-card match."""
    if not isinstance(source_card,dict) or not isinstance(target_card,dict):return False
    if normalized_name(source_card.get('category'))!=normalized_name(target_card.get('category')):return False
    source_dex={str(x) for x in (source_card.get('dexId') or [])}
    target_dex={str(x) for x in (target_card.get('dexId') or [])}
    if source_dex and target_dex and not source_dex.intersection(target_dex):return False
    source_artist=normalized_name(source_card.get('illustrator'))
    target_artist=normalized_name(target_card.get('illustrator'))
    if source_artist and source_artist!=target_artist:return False
    if source_card.get('hp') and target_card.get('hp') and str(source_card['hp'])!=str(target_card['hp']):return False
    if source_card.get('suffix') and target_card.get('suffix') and normalized_name(source_card['suffix'])!=normalized_name(target_card['suffix']):return False
    if source_card.get('stage') and target_card.get('stage') and normalized_name(source_card['stage'])!=normalized_name(target_card['stage']):return False
    same_species=bool(source_dex and target_dex and source_dex.intersection(target_dex))
    same_artist=bool(source_artist and target_artist and source_artist==target_artist)
    return same_species or same_artist

def localized_print_signature(card):
    """Comparable numeric attack signature across translated card text."""
    result=[]
    for attack in card.get('attacks') or []:
        if not isinstance(attack,dict):continue
        damage=re.sub(r'\D','',str(attack.get('damage') or ''))
        cost=len(attack.get('cost') or [])
        result.append((damage,cost))
    return tuple(result)

def catalog_secret_band(card):
    """Compare whether a print is numbered beyond its set's official card count."""
    set_data=card.get('set') or {}
    official=(set_data.get('cardCount') or {}).get('official')
    local_id=str(card.get('localId') or '').split('/',1)[0]
    try:return int(local_id)>int(official)
    except (TypeError,ValueError):return None

def mik_post(path,payload,timeout=30):
    """Read a public Simplified Chinese card-catalog endpoint."""
    body=json.dumps(payload,ensure_ascii=False).encode('utf-8')
    request=urllib.request.Request('https://tcg.mik.moe/api/v3/card/'+path,data=body,
        headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'PokeVault/5.0.5'})
    with urllib.request.urlopen(request,timeout=timeout) as response:data=json.load(response)
    if isinstance(data,dict) and 'code' in data and str(data.get('code')) not in ('0','200','None'):
        raise ValueError(str(data.get('msg') or 'El catálogo chino rechazó la consulta.'))
    return data.get('data') if isinstance(data,dict) and 'data' in data else data

def mik_records(payload):
    """Extract card rows from the public catalog's common response wrappers."""
    if isinstance(payload,list):return [row for row in payload if isinstance(row,dict)]
    if isinstance(payload,dict):
        for key in ('list','records','cards','items','rows'):
            value=payload.get(key)
            if isinstance(value,list):return [row for row in value if isinstance(row,dict)]
        nested=payload.get('data')
        if nested is not None:return mik_records(nested)
    return []

def mik_card_bridge(card):
    """Return English bridge tuples exposed on a Simplified Chinese card."""
    rows=[card]
    same=card.get('effectSameCards') or []
    if isinstance(same,list):rows.extend(item for item in same if isinstance(item,dict))
    return [(str(item.get('setCodeEn') or '').strip(),str(item.get('cardIndexEn') or '').strip(),
             str(item.get('nameEn') or '').strip()) for item in rows]

def find_simplified_chinese_print(source_card):
    """Resolve a Chinese print through mik.moe's English set/number bridge."""
    source_set=source_card.get('set') or {}
    source_set_code=str(source_set.get('tcgOnline') or source_set.get('id') or '').strip()
    source_number=str(source_card.get('localId') or '').split('/',1)[0].strip()
    source_name=str(source_card.get('name') or '').strip()
    if not source_name or not source_set_code or not source_number:
        raise ValueError('Faltan nombre, expansión o número en la carta inglesa para buscar la impresión china.')
    try:
        result=mik_post('card-basic-search',{'searchText':source_name,'exact':False,'unique':False,'page':1,'pageSize':100})
        rows=mik_records(result)
    except Exception as exc:
        raise ValueError('No se pudo consultar el catálogo chino gratuito: '+str(exc))
    # Search results may be short records, so fetch the full candidate before
    # trusting the cross-language bridge fields.
    exact=[];english_name_matches={}
    for row in rows[:100]:
        set_code=str(row.get('setCode') or '').strip()
        card_index=str(row.get('cardIndex') or '').strip()
        if not set_code or not card_index:continue
        try:detail=mik_post('card-detail',{'setCode':set_code,'cardIndex':card_index},timeout=20)
        except Exception:continue
        if not isinstance(detail,dict):continue
        for bridge_set,bridge_number,bridge_name in mik_card_bridge(detail):
            if normalized_name(bridge_name)!=normalized_name(source_name):continue
            english_name_matches[(set_code,card_index)]=detail
            if normalized_name(bridge_set).replace(' ','').replace('-','')==normalized_name(source_set_code).replace(' ','').replace('-','') and collector_number_matches(bridge_number,source_number):
                exact.append(detail)
                break
    # De-duplicate repeated search hits by physical Chinese set + number.
    unique={ (str(card.get('setCode') or ''),str(card.get('cardIndex') or '')):card for card in exact }
    if len(unique)!=1:
        if len(unique)>1:raise ValueError('El catálogo chino relaciona esta carta con varias impresiones; no se elegirá una al azar.')
        # Simplified Chinese products can re-number the same physical card and
        # print it in a different product than the international source set.
        # In that case use the English bridge name plus matching artist, HP and
        # attack signature, and continue only when that identifies one print.
        trait_matches=[]
        source_artist=normalized_name(source_card.get('illustrator'))
        source_hp=str(source_card.get('hp') or '')
        source_signature=localized_print_signature(source_card)
        for candidate in english_name_matches.values():
            attrs=candidate.get('pokemonAttr') or {}
            artist=normalized_name(candidate.get('artist'))
            hp=str(attrs.get('hp') or candidate.get('hp') or '')
            attacks=attrs.get('attack') or candidate.get('attacks') or []
            signature=[]
            for attack in attacks:
                if not isinstance(attack,dict):continue
                damage=re.sub(r'\D','',str(attack.get('damage') or ''))
                cost=attack.get('cost') or []
                signature.append((damage,len(cost) if isinstance(cost,(list,str)) else 0))
            if source_artist and artist!=source_artist:continue
            if source_hp and hp!=source_hp:continue
            if source_signature and tuple(signature)!=source_signature:continue
            if source_artist and source_hp and source_signature and signature:trait_matches.append(candidate)
        trait_unique={(str(card.get('setCode') or ''),str(card.get('cardIndex') or '')):card for card in trait_matches}
        if len(trait_unique)==1:
            unique=trait_unique
        elif len(trait_unique)>1:
            raise ValueError('El catálogo chino encontró varias impresiones con los mismos datos de carta; no se elegirá un precio al azar.')
        elif english_name_matches:
            raise ValueError('El catálogo chino encontró cartas con ese nombre, pero no pudo confirmar una impresión única por ilustrador, puntos de salud y ataques. No se consultará un precio de otra impresión.')
        else:raise ValueError('No se encontró una impresión china simplificada equivalente en el catálogo público.')
    card=next(iter(unique.values()))
    set_code=str(card.get('setCode') or '').strip();card_index=str(card.get('cardIndex') or '').strip()
    # Resolve the Chinese expansion title for CardTrader's expansion catalog.
    set_title=set_code
    try:
        products=mik_records(mik_post('product-list',{},timeout=25))
        product=next((item for item in products if str(item.get('setId') or item.get('setCode') or '').strip()==set_code),None)
        if product:set_title=str(product.get('name') or product.get('nameZh') or set_code)
    except Exception:pass
    card=dict(card)
    card['name']=card.get('nameEn') or source_name
    card['localId']=card_index
    card['set']={'id':set_code,'name':set_title}
    card['_cardtrader_number']=card_index
    return card

def find_localized_catalog_print(card_id,language):
    """Resolve a TCGdex print in another language; only return unique strong matches."""
    locale=tcgdex_locale(language)
    if not locale:raise ValueError('El catálogo no tiene datos para ese idioma.')
    try:source=tcgdex_get_card(card_id,'en')
    except Exception as exc:raise ValueError('No se pudo leer la carta de origen en TCGdex: '+str(exc))
    if not source:raise ValueError('TCGdex no encontró el identificador '+str(card_id)+'.')
    if locale=='en':target=source
    else:
        try:target=tcgdex_get_card(card_id,locale)
        except Exception:target=None
    if target and (target.get('id')==source.get('id') or localized_print_match(source,target)):return source,target

    if locale=='zh-cn':
        return source,find_simplified_chinese_print(source)

    # Spanish prints share the international set code and collector number.
    # TCGdex can lag on localized rows for new sets, so retain the exact EN
    # printing identity and let CardTrader's `language=es` filter select offers.
    if locale=='es':return source,source

    dex_ids=source.get('dexId') or []
    artist=source.get('illustrator')
    if not dex_ids and not artist:
        raise ValueError('No hay datos de especie o ilustrador suficientes para emparejar automáticamente esta impresión.')
    params={}
    if dex_ids:params['dexId']=str(dex_ids[0])
    if artist:params['illustrator']='eq:'+str(artist)
    url='https://api.tcgdex.net/v2/'+locale+'/cards?'+urllib.parse.urlencode(params)
    request=urllib.request.Request(url,headers={'User-Agent':'PokeVault/5.0','Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=25) as response:briefs=json.load(response)
    except Exception as exc:raise ValueError('No se pudo buscar la impresión en el catálogo '+locale+': '+str(exc))
    if not isinstance(briefs,list):briefs=[]
    if len(briefs)>50:
        raise ValueError('El catálogo devolvió demasiadas impresiones candidatas en '+locale+'; no se consultará un precio hasta tener una coincidencia más precisa.')
    candidates=[]
    for brief in briefs:
        cid=brief.get('id') if isinstance(brief,dict) else None
        if not cid:continue
        try:candidate=tcgdex_get_card(cid,locale,timeout=12)
        except Exception:continue
        if not localized_print_match(source,candidate):continue
        if source.get('dexId') and source.get('illustrator'):
            if not (set(map(str,source['dexId'])) & set(map(str,candidate.get('dexId') or []))):continue
            if normalized_name(candidate.get('illustrator'))!=normalized_name(source.get('illustrator')):continue
        if source.get('hp') and str(candidate.get('hp') or '')!=str(source['hp']):continue
        source_signature=localized_print_signature(source);target_signature=localized_print_signature(candidate)
        if source_signature and target_signature and source_signature!=target_signature:continue
        candidates.append(candidate)
    source_secret_band=catalog_secret_band(source)
    if source_secret_band is not None:
        same_rarity_band=[candidate for candidate in candidates if catalog_secret_band(candidate)==source_secret_band]
        if same_rarity_band:candidates=same_rarity_band
    # International sets often include several Japanese expansions, and the same
    # card can be reprinted later. Prefer the latest Japanese set released no later
    # than the international source set when the card traits alone leave a tie.
    if len(candidates)>1 and locale=='ja':
        try:
            source_set_id=(source.get('set') or {}).get('id')
            source_set=tcgdex_get_set(source_set_id,'en')
            source_date=str((source_set or {}).get('releaseDate') or '')
            if source_date:
                dated=[]
                for candidate in candidates:
                    target_set_id=(candidate.get('set') or {}).get('id')
                    target_set=tcgdex_get_set(target_set_id,locale)
                    release_date=str((target_set or {}).get('releaseDate') or '')
                    if release_date and release_date<=source_date:dated.append((release_date,candidate))
                if dated:
                    closest=max(date for date,_ in dated)
                    candidates=[candidate for date,candidate in dated if date==closest]
        except Exception:pass
    if len(candidates)!=1:
        if len(candidates)>1:raise ValueError('El catálogo encontró varias impresiones posibles en '+locale+'; no se elegirá un precio automáticamente para evitar mezclar ediciones.')
        raise ValueError('No se encontró una impresión equivalente única en el catálogo '+locale+'. Puedes abrir «Identificar impresión manualmente».')
    return source,candidates[0]

def normalize_market_language(value):
    value=normalized_name(value)
    aliases={
        'chinese simplified':'chinese-s','simplified chinese':'chinese-s','chinese-s':'chinese-s',
        'chino simplificado':'chinese-s',
        'chinese traditional':'chinese-t','traditional chinese':'chinese-t','chinese-t':'chinese-t',
        'chino tradicional':'chinese-t',
        'zh-cn':'chinese-s','zh-tw':'chinese-t',
        'spanish':'spanish','espanol':'spanish','es':'spanish',
        'english':'english','ingles':'english','en':'english',
        'japanese':'japanese','japones':'japanese','jp':'japanese','ja':'japanese',
    }
    return aliases.get(value,value)

def cardtrader_expansion_language(expansion_name,expansion_code=''):
    """Infer a market locale only when an expansion explicitly names it."""
    title=normalized_name(expansion_name)
    code=normalized_name(expansion_code)
    if any(term in title for term in ('simplified chinese','chinese simplified')):return 'zh-CN'
    if any(term in title for term in ('traditional chinese','chinese traditional')):return 'zh-TW'
    if '30thc' in code and 'simplified chinese' in title:return 'zh-CN'
    return ''

def cardtrader_language_mismatch(language,expansion):
    if not expansion:return ''
    expected=cardtrader_language(language)
    expansion_language=cardtrader_expansion_language(expansion.get('name',''),expansion.get('code',''))
    if expected and expansion_language and normalize_market_language(expected)!=normalize_market_language(expansion_language):
        labels={'zh-CN':'chino simplificado','zh-TW':'chino tradicional','es':'español','en':'inglés','jp':'japonés'}
        return (f"La expansión «{expansion.get('name')}» es para {labels.get(expansion_language,expansion_language)}, "
                f"pero esta copia está marcada como {language}. Corrige el idioma de la carta o identifica su expansión correcta.")
    return ''

class PriceFetch(QThread):
    done=Signal(object)
    def __init__(self,ids):super().__init__();self.ids=list(ids)
    def run(self):
        for cid in self.ids:
            if self.isInterruptionRequested():break
            error=None;values=None;responded=False
            # TCGdex card pricing can be missing from one language's detail.
            # Only retry other catalog languages when the primary entry has no quote.
            for language in ('en','es','fr','ja'):
                try:
                    url='https://api.tcgdex.net/v2/'+language+'/cards/'+urllib.parse.quote(cid,safe='')
                    req=urllib.request.Request(url,headers={'User-Agent':'PokeVault/2.4','Accept':'application/json'})
                    with urllib.request.urlopen(req,timeout=10) as res:card=json.load(res)
                    responded=True
                    market=(card.get('pricing') or {}).get('cardmarket') or {}
                    if not isinstance(market,dict):market={}
                    def numeric(key):
                        value=market.get(key)
                        try:return float(value) if value is not None else None
                        except (TypeError,ValueError):return None
                    current={k:numeric(k) for k in ('trend','low','avg','avg1','avg7','avg30')}
                    current.update(updated=str(market.get('updated') or ''),status='ok' if any(v is not None for v in current.values()) else 'missing')
                    if values is None:values=current
                    if current['status']=='ok':values=current;break
                except Exception as exc:error=str(exc)
            if values is None:
                if responded:
                    values={k:None for k in ('trend','low','avg','avg1','avg7','avg30')}
                    values.update(updated='',status='missing')
                else:self.done.emit([(cid,None,error or 'Error de conexión')]);continue
            self.done.emit([(cid,values,None)])

class SpeciesFetch(QThread):
    """Obtiene especies reales (no nombres de cartas) y las guarda localmente."""
    done=Signal(object,str)
    def run(self):
        cache=DATA/'pokemon_species.json'
        try:
            if cache.exists():
                species=json.loads(cache.read_text(encoding='utf-8'))
            else:
                req=urllib.request.Request('https://pokeapi.co/api/v2/pokemon-species?limit=2000',headers={'User-Agent':'PokeVault/1.10'})
                with urllib.request.urlopen(req,timeout=25) as res: data=json.load(res)
                species=sorted({x['name'].replace('-', ' ').title() for x in data.get('results',[]) if x.get('name')},key=str.casefold)
                if species:cache.write_text(json.dumps(species,ensure_ascii=False),encoding='utf-8')
            self.done.emit(species,'')
        except Exception as exc:self.done.emit([],str(exc))

class SetFetch(QThread):
    done=Signal(object,str)
    def __init__(self,term):super().__init__();self.term=term
    def run(self):
        results={};errors=[]
        for lang in ('en','es','zh-tw','zh-cn','ja'):
            try:
                data=fetch_catalog(lang,'sets')
                if isinstance(data,list):
                    for item in data:
                        sid=item.get('id')
                        if sid:results.setdefault(sid,item)
            except Exception as exc:errors.append(lang+': '+str(exc))
        matches=[x for x in results.values() if not self.term or normalized_name(self.term) in normalized_name(x.get('name')) or normalized_name(self.term) in normalized_name(x.get('id'))]
        self.done.emit(matches,'' if results else 'No se pudo cargar el catálogo de expansiones: '+'; '.join(errors[:2]))

class SetCardsFetch(QThread):
    done=Signal(object,str)
    def __init__(self,set_id,name):super().__init__();self.set_id=set_id;self.name=name;self.result=([], '')
    def run(self):
        found=False;errors=[]
        for language in ('en','es','zh-tw','zh-cn','ja'):
            try:
                data=fetch_catalog(language,'sets/'+urllib.parse.quote(self.set_id,safe=''))
                if not isinstance(data,dict):continue
                found=True
                cards=data.get('cards',[])
                if self.name:cards=[c for c in cards if card_matches(c,self.name)]
                self.result=(cards[:1500],'');self.done.emit(*self.result);return
            except urllib.error.HTTPError as exc:
                if exc.code!=404:errors.append(language+': '+str(exc))
            except Exception as exc:errors.append(language+': '+str(exc))
        self.result=([],('No existe la expansión «'+self.set_id+'» en los catálogos disponibles.' if not found and not errors else '; '.join(errors[:2])))
        self.done.emit(*self.result)

def image_candidates(card_id, base):
    """Try provided artwork, then the canonical card detail in several languages."""
    bases=[base] if base else []
    if card_id and card_id != 'detail':
        for language in ('en','fr','es','ja'):
            try:
                url='https://api.tcgdex.net/v2/'+language+'/cards/'+urllib.parse.quote(card_id,safe='')
                req=urllib.request.Request(url,headers={'User-Agent':'PokeVault/1.13'})
                with urllib.request.urlopen(req,timeout=5) as res: detail=json.load(res)
                candidate=detail.get('image')
                if candidate and candidate not in bases:bases.append(candidate)
            except Exception:pass
    return bases

class ImageFetch(QThread):
    received=Signal(str,bytes)
    failed=Signal(str,str)
    def __init__(self,entries):super().__init__();self.entries=entries
    def run(self):
        for cid,base in self.entries:
            if self.isInterruptionRequested():break
            if str(cid).startswith('manual-') and base and Path(base).is_file():
                try:self.received.emit(cid,Path(base).read_bytes())
                except OSError:self.failed.emit(cid,'No se puede leer la foto')
                continue
            key=hashlib.sha256((base or cid).encode()).hexdigest();path=CACHE/(key+'.img')
            if path.exists():
                content=path.read_bytes()
                if QImage().loadFromData(content):self.received.emit(cid,content);continue
                path.unlink(missing_ok=True)
            ok=False
            # Prefer the known image URL; only request alternate catalog entries on failure.
            bases=[base] if base else []
            def attempt(candidate):
                for url in image_urls(candidate):
                    if self.isInterruptionRequested():break
                    try:
                        req=urllib.request.Request(url,headers={'User-Agent':'PokeVault/1.13'})
                        with urllib.request.urlopen(req,timeout=6) as res:content=res.read(5_000_000)
                        if QImage().loadFromData(content):return content
                    except Exception:pass
                return None
            for candidate in bases:
                content=attempt(candidate)
                if content:ok=True;break
            if not ok and cid!='detail':
                for candidate in image_candidates(cid,None):
                    if candidate in bases:continue
                    content=attempt(candidate)
                    if content:ok=True;break
            if ok:
                try:path.write_bytes(content)
                except OSError:pass
                self.received.emit(cid,content)
            else:self.failed.emit(cid,'Imagen no disponible en el catálogo')

FINISH_LABELS={'Normal':'Normal','Holo':'Holográfica','Reverse':'Reverse holo','Especial':'Especial','Sin verificar':'Sin verificar'}

def detected_finishes(card):
    """Only use explicit TCGdex variant flags; unknown metadata is not a negative."""
    variants=card.get('variants')
    if not isinstance(variants,dict):return None
    flags={'Normal':variants.get('normal'),'Holo':variants.get('holo'),'Reverse':variants.get('reverse')}
    if not any(isinstance(v,bool) for v in flags.values()):return None
    available=[k for k,v in flags.items() if v is True]
    # If all flags are false, the catalog may be describing a promo/special card.
    return available or ['Especial']

class FinishFetch(QThread):
    done=Signal(object)
    def __init__(self,cid):super().__init__();self.cid=cid
    def run(self):
        for language in ('en','es'):
            try:
                url='https://api.tcgdex.net/v2/'+language+'/cards/'+urllib.parse.quote(self.cid,safe='')
                req=urllib.request.Request(url,headers={'User-Agent':'PokeVault/2.9'})
                with urllib.request.urlopen(req,timeout=8) as res:card=json.load(res)
                finishes=detected_finishes(card)
                if finishes is not None:self.done.emit(finishes);return
            except Exception:pass
        self.done.emit(None)

class CardDialog(QDialog):
    def __init__(self,parent,card=None,cid=None,wish_albums=None):
        super().__init__(parent);self.setWindowTitle('Datos de la carta');self.setMinimumWidth(360)
        f=QFormLayout(self);self.qty=QSpinBox();self.qty.setRange(1,9999);self.qty.setValue(card['quantity'] if card else 1)
        self.lang=QComboBox()
        for label,value in [('Español','Español'),('Inglés','Inglés'),('Chino (sin especificar)','Chino'),('Chino simplificado','Chino simplificado'),('Chino tradicional','Chino tradicional'),('Japonés','Japonés')]:self.lang.addItem(label,value)
        self.cond=QComboBox();self.cond.addItems(['Near Mint','Excellent','Good','Light Played','Played','Poor'])
        self.finish=QComboBox()
        self.saved_variant=(card.get('variant') or 'Sin verificar') if card else 'Sin verificar'
        self.finish.addItem(FINISH_LABELS.get(self.saved_variant,self.saved_variant),self.saved_variant)
        self.finish_note=QLabel('Comprobando acabados disponibles…' if cid else 'Acabado sin verificar')
        self.finish_note.setWordWrap(True);self.finish_note.setStyleSheet('color:#aab9d0;font-size:12px')
        self.finish.setEnabled(False)
        if cid and str(cid).startswith('manual-'):
            self.finish.clear()
            for finish in ('Sin verificar','Normal','Holo','Reverse','Especial'):
                self.finish.addItem(FINISH_LABELS.get(finish,finish),finish)
            self.finish.setEnabled(True)
            self.finish_note.setText('Carta manual: selecciona el acabado que corresponda.')
        if card:
            for box,key in ((self.lang,'language'),(self.cond,'condition')):
                if key=='language':
                    index=box.findData(card[key])
                    if index<0:index=box.findText(card[key])
                    box.setCurrentIndex(max(0,index))
                else:box.setCurrentIndex(max(0,box.findText(card[key])))
        for title,w in [('Cantidad',self.qty),('Idioma',self.lang),('Estado',self.cond),('Acabado',self.finish)]:f.addRow(title,w)
        f.addRow('',self.finish_note)
        self.wish_album=None
        if wish_albums is not None:
            self.wish_album=QComboBox();self.wish_album.addItem('Sin álbum',None)
            for album_id,album_name in wish_albums:self.wish_album.addItem(album_name,album_id)
            f.addRow('Álbum de deseos',self.wish_album)
        b=QPushButton('Guardar');b.clicked.connect(self.accept);f.addRow(b)
        self.finish_worker=None
        if cid and not str(cid).startswith('manual-'):
            self.finish_worker=FinishFetch(cid)
            self.finish_worker.done.connect(self.apply_finishes)
            self.finish_worker.start()
    def apply_finishes(self,available):
        self.finish.clear()
        if available is None:
            self.finish.addItem(FINISH_LABELS.get(self.saved_variant,self.saved_variant),self.saved_variant)
            self.finish.setEnabled(False)
            self.finish_note.setText('TCGdex no confirma los acabados de esta carta. Se conserva el acabado guardado.')
            return
        # Keep a legacy choice visible instead of silently changing the owner's inventory.
        if self.saved_variant not in available and self.saved_variant not in ('Normal','Sin verificar'):
            available=[self.saved_variant]+available
            self.finish_note.setText('El acabado guardado no está confirmado; comprueba tu carta.')
        else:
            self.finish_note.setText('Acabados confirmados por TCGdex.' if len(available)>1 else 'Solo un acabado confirmado por TCGdex.')
        for key in available:self.finish.addItem(FINISH_LABELS.get(key,key),key)
        index=self.finish.findData(self.saved_variant)
        self.finish.setCurrentIndex(index if index>=0 else 0)
        self.finish.setEnabled(len(available)>1)
    def values(self):return self.lang.currentData(),self.cond.currentText(),self.finish.currentData(),self.qty.value()
    def done(self,result):
        if self.finish_worker and self.finish_worker.isRunning():
            self.finish_worker.requestInterruption();self.finish_worker.wait(18000)
        super().done(result)

def empty_state(icon_text,title_text,message_text):
    page=QWidget();page_layout=QVBoxLayout(page);page_layout.setContentsMargins(12,12,12,12);page_layout.setSpacing(0)
    page_layout.addStretch(1)
    frame=QFrame();frame.setObjectName('emptyState');frame.setMinimumSize(420,204);frame.setMaximumWidth(560);frame.setFixedHeight(204)
    layout=QVBoxLayout(frame);layout.setContentsMargins(24,18,24,18);layout.setSpacing(5)
    layout.addStretch(1)
    icon=QLabel(icon_text);icon.setObjectName('emptyIcon');icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title=QLabel(title_text);title.setObjectName('emptyTitle');title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    message=QLabel(message_text);message.setObjectName('emptyMessage');message.setWordWrap(True);message.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(icon);layout.addWidget(title);layout.addWidget(message);layout.addStretch(1)
    page_layout.addWidget(frame,alignment=Qt.AlignmentFlag.AlignHCenter)
    page_layout.addStretch(1)
    return page

class Tile(QFrame):
    def __init__(self,card,callback,detail_cb=None,wish_cb=None):
        super().__init__();self.card=card;self.setObjectName('tile');self.setFixedWidth(230)
        layout=QVBoxLayout(self);layout.setSpacing(7)
        self.picture=QLabel('Cargando imagen...');self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter);self.picture.setFixedSize(202,262);self.picture.setWordWrap(True);self.picture.setObjectName('picture');layout.addWidget(self.picture,alignment=Qt.AlignmentFlag.AlignHCenter)
        name=QLabel(card.get('name','Sin nombre'));name.setObjectName('cardTitle');name.setWordWrap(True);name.setMinimumHeight(38);layout.addWidget(name)
        ident=QLabel(card.get('id',''));ident.setObjectName('muted');layout.addWidget(ident)
        b=QPushButton('Añadir a colección');b.setObjectName('primary');b.clicked.connect(lambda:callback(card));layout.addWidget(b)
        wish=QPushButton('♡ Añadir a deseos');wish.setObjectName('secondary');wish.clicked.connect(lambda:wish_cb(card) if wish_cb else None);layout.addWidget(wish)
        detail=QPushButton('Ver detalle');detail.setObjectName('secondary');detail.clicked.connect(lambda:detail_cb(card) if detail_cb else None);layout.addWidget(detail)
    def set_image(self,content):
        pix=QPixmap()
        if pix.loadFromData(content):self.picture.setPixmap(pix.scaled(198,258,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self.picture.setText('')
    def set_missing(self,message):self.picture.setText(message)

class OwnedTile(QFrame):
    def __init__(self, row, edit_cb, delete_cb, detail_cb=None, quantity_cb=None, price=None):
        super().__init__()
        self.setObjectName('tile')
        self.quantity_cb=quantity_cb or (lambda *_:None)
        pk,cid,name,lang,cond,var,qty,img=row
        self.row_id=pk;self.card_id=cid;self.language=lang;self.variant=var or "";self.quantity=qty
        self.setFixedWidth(250)
        v=QVBoxLayout(self);v.setContentsMargins(9,9,9,9);v.setSpacing(5)
        self.picture=QLabel('Cargando imagen...');self.picture.setObjectName('picture')
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter);self.picture.setWordWrap(True)
        self.picture.setFixedSize(222,288);v.addWidget(self.picture,alignment=Qt.AlignmentFlag.AlignHCenter)
        title=QLabel(name);title.setObjectName('cardTitle');title.setWordWrap(True)
        title.setMaximumHeight(38);v.addWidget(title)
        ident=QLabel(cid);ident.setObjectName('muted');v.addWidget(ident)
        info=QLabel(f'{lang}  ·  {cond}  ·  {FINISH_LABELS.get(var or "Sin verificar",var or "Sin verificar")}');info.setWordWrap(True)
        info.setObjectName('secondaryText');info.setStyleSheet('font-size:12px');v.addWidget(info)
        quantity_bar=QHBoxLayout();quantity_bar.setSpacing(4)
        minus=QPushButton('−');plus=QPushButton('+')
        minus.setToolTip('Quitar una copia (la última requiere confirmación)')
        plus.setToolTip('Añadir una copia')
        for b in (minus,plus):b.setFixedSize(33,32);b.setStyleSheet('padding:2px')
        minus.clicked.connect(lambda:self.quantity_cb(pk,-1))
        plus.clicked.connect(lambda:self.quantity_cb(pk,1))
        quantity_bar.addWidget(QLabel('Copias: '+str(qty)));quantity_bar.addStretch()
        quantity_bar.addWidget(minus);quantity_bar.addWidget(plus);v.addLayout(quantity_bar)
        self.price_label=QLabel();self.price_label.setWordWrap(True)
        self.price_label.setObjectName('cardPrice')
        v.addWidget(self.price_label);self.set_price(price,qty)
        buttons=QHBoxLayout();buttons.setSpacing(5)
        e=QPushButton('Editar');d=QPushButton('Eliminar')
        d.setObjectName('danger');e.clicked.connect(lambda:edit_cb(pk));d.clicked.connect(lambda:delete_cb(pk))
        e.setObjectName('secondary')
        for b in (e,d):b.setStyleSheet('padding:7px 5px')
        buttons.addWidget(e);buttons.addWidget(d);v.addLayout(buttons)
        detail=QPushButton('Ver detalle');detail.setObjectName('secondary');detail.setStyleSheet('padding:7px 5px')
        detail.clicked.connect(lambda:detail_cb(row) if detail_cb else None);v.addWidget(detail)
    def set_price(self,price,qty):
        if price is None:
            self.price_label.setText('Precio: pendiente de consulta')
            self.price_label.setToolTip('Aún no se ha consultado el precio de esta carta.')
        elif price.get('status')=='error':
            self.price_label.setText('Precio: error de conexión')
            self.price_label.setToolTip('La consulta falló. Pulsa Actualizar precios para reintentar.')
        elif price.get('trend') is None and price.get('avg') is None:
            self.price_label.setText('Precio: no disponible')
            self.price_label.setToolTip('Se consultó TCGdex, pero no se encontró cotización de Cardmarket para esta carta.')
        else:
            amount=price['trend'] if price['trend'] is not None else price['avg']
            label={'verified':'Verificado: ','market_api':'CardTrader: ','market_api_stale':'CardTrader (última): '}.get(price.get('status'),'Ref. general: ')
            date_value=price.get('fetched_at') or price.get('updated')
            try:date_text=datetime.datetime.fromtimestamp(int(float(date_value))).strftime('%d/%m %H:%M') if date_value else ''
            except (TypeError,ValueError,OSError):date_text=''
            date_suffix=(' · '+date_text) if date_text and price.get('status') in ('market_api','market_api_stale') else ''
            details=('\nCardTrader: '+str(price.get('cardtrader_reason'))) if price.get('status')=='general' and price.get('cardtrader_reason') else ''
            self.price_label.setText(label+euros(amount)+date_suffix+(('  ·  Total: '+euros(amount*qty)) if qty>1 else '')+details)
            tips={'verified':'Precio verificado para esta edición.','market_api':'Precio de ofertas CardTrader para la impresión física confirmada.','market_api_stale':'Última cotización guardada de CardTrader. El intento más reciente no encontró ofertas compatibles.'}
            tooltip=tips.get(price.get('status'),'Referencia general vía TCGdex: puede no corresponder al idioma o edición.')
            if price.get('status')=='general' and price.get('cardtrader_detail'):tooltip+='\n\nCardTrader: '+str(price['cardtrader_detail'])
            self.price_label.setToolTip(tooltip)
    def set_image(self,content):
        pix=QPixmap()
        if pix.loadFromData(content):
            self.picture.setPixmap(pix.scaled(218,284,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            self.picture.setText('')
    def set_missing(self,message):self.picture.setText(message)

class WishTile(QFrame):
    def __init__(self,row,price,remove_cb,move_cb,organize_cb):
        super().__init__();self.setObjectName('tile');self.setFixedWidth(250)
        pk,cid,name,lang,cond,var,qty,img,added=row[:9]
        v=QVBoxLayout(self);v.setSpacing(5)
        self.picture=QLabel('Cargando imagen…');self.picture.setObjectName('picture')
        self.picture.setFixedSize(222,282);self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.picture,alignment=Qt.AlignmentFlag.AlignHCenter)
        title=QLabel(name);title.setObjectName('cardTitle');title.setWordWrap(True);v.addWidget(title)
        v.addWidget(QLabel(cid))
        info=QLabel(f'{lang} · {cond} · {FINISH_LABELS.get(var,var)} · ×{qty}')
        info.setWordWrap(True);v.addWidget(info)
        self.price_label=QLabel();v.addWidget(self.price_label)
        self.set_price(price,qty)
        album_id=row[9] if len(row)>9 else None
        organize=QPushButton('Organizar en álbum');organize.setObjectName('secondary');organize.clicked.connect(lambda:organize_cb(pk,album_id));v.addWidget(organize)
        move=QPushButton('✓ Pasar a colección');move.setObjectName('primary');move.clicked.connect(lambda:move_cb(pk));v.addWidget(move)
        remove=QPushButton('Quitar de deseos');remove.setObjectName('danger');remove.clicked.connect(lambda:remove_cb(pk));v.addWidget(remove)
    def set_price(self,price,qty):
        amount=price.get('trend') if price else None
        if amount is None and price:amount=price.get('avg')
        self.price_label.setText(f'Precio general: {euros(amount)} · Total: {euros(amount*qty)}' if amount is not None else 'Precio general no disponible')
        self.price_label.setWordWrap(True)
    def set_image(self,data):
        pix=QPixmap()
        if pix.loadFromData(data):self.picture.setPixmap(pix.scaled(218,278,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self.picture.setText('')
    def set_missing(self,message):self.picture.setText(message)

class AlbumTile(QFrame):
    def __init__(self,row,open_cb,rename_cb,delete_cb):
        super().__init__();self.setObjectName('albumTile');self.setFixedSize(280,222)
        album_id,name,count=row[:3];preview_urls=list(row[3]) if len(row)>3 else [];self.open_cb=open_cb;self.album_id=album_id
        self.preview_targets={}
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,43,24,17);layout.setSpacing(3)
        header=QHBoxLayout();header.setContentsMargins(0,0,0,0);header.addStretch()
        settings=QToolButton();settings.setObjectName('albumMenu');settings.setFixedSize(38,38);settings.setText('⋮');settings.setToolTip('Opciones del álbum');settings.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(settings);rename_action=menu.addAction('Renombrar');delete_action=menu.addAction('Eliminar álbum')
        rename_action.triggered.connect(lambda _=False:rename_cb(album_id,name))
        delete_action.triggered.connect(lambda _=False:delete_cb(album_id,name))
        settings.setMenu(menu);header.addWidget(settings);layout.addLayout(header)
        title=QLabel(name);title.setObjectName('albumName');title.setText(QFontMetrics(title.font()).elidedText(name,Qt.TextElideMode.ElideRight,230));title.setToolTip(name);layout.addWidget(title)
        amount=QLabel(f'{count} '+('carta' if count==1 else 'cartas'));amount.setObjectName('albumCount');layout.addWidget(amount)
        if preview_urls:
            strip=QHBoxLayout();strip.setContentsMargins(0,3,0,0);strip.setSpacing(6)
            for url in preview_urls[:3]:
                preview=QLabel('Carta');preview.setObjectName('albumPreview');preview.setFixedSize(43,56);preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
                strip.addWidget(preview);self.preview_targets.setdefault(url,[]).append(preview)
            strip.addStretch();layout.addLayout(strip)
        self._open_targets=(self,title,amount)
        for target in self._open_targets:target.installEventFilter(self)

    def set_preview_image(self,label,data):
        pix=QPixmap()
        if pix.loadFromData(data):
            label.setPixmap(pix.scaled(label.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation))
            label.setText('')

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w=float(self.width());h=float(self.height())
        folder=QPainterPath();folder.moveTo(13,39);folder.lineTo(13,31);folder.quadTo(13,22,22,22)
        folder.lineTo(83,22);folder.lineTo(100,10);folder.lineTo(145,10);folder.quadTo(154,10,160,20)
        folder.lineTo(166,31);folder.lineTo(w-21,31);folder.quadTo(w-12,31,w-12,40)
        folder.lineTo(w-12,h-16);folder.quadTo(w-12,h-8,w-21,h-8);folder.lineTo(21,h-8)
        folder.quadTo(13,h-8,13,h-16);folder.closeSubpath()
        gradient=QLinearGradient(0,24,0,h-8)
        if self.underMouse():
            gradient.setColorAt(0,QColor('#735527'));gradient.setColorAt(1,QColor('#302b23'))
            edge=QColor('#f2c36e')
        else:
            gradient.setColorAt(0,QColor('#59431f'));gradient.setColorAt(1,QColor('#252638'))
            edge=QColor('#a88447')
        painter.setBrush(gradient);painter.setPen(QPen(edge,1.5));painter.drawPath(folder)
        painter.setPen(QPen(QColor(255,225,165,75),1))
        painter.drawLine(18,43,int(w-18),43)

    def enterEvent(self,event):
        self.update();super().enterEvent(event)

    def leaveEvent(self,event):
        self.update();super().leaveEvent(event)

    def eventFilter(self,target,event):
        if target in self._open_targets and event.type()==QEvent.Type.MouseButtonDblClick:
            self.open_cb(self.album_id);return True
        return super().eventFilter(target,event)

class PriceChart(QWidget):
    """Gráfica Qt sin dependencias extra. Solo dibuja cotizaciones realmente guardadas."""
    def __init__(self):
        super().__init__()
        self.points=[]
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)

    def set_points(self,points):
        self.points=list(points)
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=self.rect()
        painter.setPen(QColor('#9aadc5'))
        if not self.points:
            painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,'Todavía no hay consultas de CardTrader guardadas en este período.')
            return
        if len(self.points)==1:
            painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,'Primer precio registrado: '+euros(self.points[0][1])+'\nLa gráfica crecerá con las próximas actualizaciones.')
            return
        left,top,right,bottom=66,16,18,35
        w=max(1,rect.width()-left-right);h=max(1,rect.height()-top-bottom)
        vals=[float(v) for _,v in self.points]
        lo,hi=min(vals),max(vals)
        padding=max((hi-lo)*.12,hi*.01,0.05)
        lo=max(0,lo-padding);hi+=padding
        t0,t1=self.points[0][0],self.points[-1][0]
        def xy(ts,val):return (left+(ts-t0)/max(1,t1-t0)*w,top+(hi-val)/max(.001,hi-lo)*h)
        painter.setFont(QFont('Arial',9))
        for i in range(4):
            v=lo+(hi-lo)*i/3
            y=top+h-(h*i/3)
            painter.setPen(QPen(QColor('#2a3d56'),1))
            painter.drawLine(left,int(y),left+w,int(y))
            painter.setPen(QColor('#9aadc5'))
            painter.drawText(0,int(y)-10,left-8,20,Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,euros(v))
        painter.setPen(QColor('#9aadc5'))
        for ts,x,align in ((t0,left,Qt.AlignmentFlag.AlignLeft),(t1,left+w-80,Qt.AlignmentFlag.AlignRight)):
            label=datetime.datetime.fromtimestamp(ts).strftime('%d/%m/%y')
            painter.drawText(int(x),top+h+6,80,23,align,label)
        painter.setPen(QPen(QColor('#19b7a8'),3))
        coords=[xy(ts,v) for ts,v in self.points]
        for a,b in zip(coords,coords[1:]):painter.drawLine(int(a[0]),int(a[1]),int(b[0]),int(b[1]))
        painter.setPen(QPen(QColor('#b8fff4'),2))
        painter.setBrush(QColor('#19b7a8'))
        for x,y in coords:painter.drawEllipse(int(x)-3,int(y)-3,6,6)

class DetailPage(QWidget):
    """Ficha de carta con imagen e identidad a la izquierda y cotización a la derecha."""
    def __init__(self, back):
        super().__init__()
        outer=QVBoxLayout(self)
        outer.setContentsMargins(12,12,12,12)
        back_btn=QPushButton('← Volver')
        back_btn.setFixedWidth(140)
        back_btn.clicked.connect(back)
        outer.addWidget(back_btn,0,Qt.AlignmentFlag.AlignLeft)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll,1)
        content=QWidget()
        self.columns=QHBoxLayout(content)
        self.columns.setSpacing(28)
        self.columns.setContentsMargins(18,18,18,18)
        left=QWidget()
        left.setMinimumWidth(260)
        left.setMaximumWidth(460)
        left_layout=QVBoxLayout(left)
        left_layout.setSpacing(10)
        self.picture=QLabel('Cargando imagen...')
        self.picture.setObjectName('picture')
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setMinimumHeight(360)
        self.picture.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        left_layout.addWidget(self.picture)
        self.title=QLabel()
        self.title.setObjectName('detailTitle')
        self.title.setWordWrap(True)
        left_layout.addWidget(self.title)
        self.info=QLabel()
        self.info.setWordWrap(True)
        self.info.setObjectName('secondaryText');self.info.setStyleSheet('font-size:15px')
        left_layout.addWidget(self.info)
        left_layout.addStretch()
        self.columns.addWidget(left,2)
        right=QWidget()
        right.setMinimumWidth(330)
        right_layout=QVBoxLayout(right)
        right_layout.setSpacing(14)
        self.price_heading=QLabel('PRECIO CARDTRADER')
        self.price_heading.setObjectName('detailHeading')
        right_layout.addWidget(self.price_heading)
        self.current_price=QLabel('Sin consultar')
        self.current_price.setObjectName('detailPrice')
        right_layout.addWidget(self.current_price)
        self.price_subtitle=QLabel('Consulta filtrada por el idioma de esta carta')
        self.price_subtitle.setObjectName('secondaryText');self.price_subtitle.setStyleSheet('font-size:13px')
        self.price_subtitle.setWordWrap(True)
        right_layout.addWidget(self.price_subtitle)
        self.updated=QLabel('')
        self.updated.setWordWrap(True)
        self.updated.setObjectName('secondaryText');self.updated.setStyleSheet('font-size:12px')
        right_layout.addWidget(self.updated)
        graph=QFrame()
        graph.setObjectName('priceHistory')
        graph_layout=QVBoxLayout(graph)
        graph_heading=QLabel('Historial de precios CardTrader')
        graph_heading.setObjectName('sectionTitle')
        graph_layout.addWidget(graph_heading)
        filters=QHBoxLayout()
        filters.addWidget(QLabel('Período:'))
        self.range_buttons={}
        for days in (7,30,90):
            btn=QPushButton(f'{days} días')
            btn.setCheckable(True)
            btn.setChecked(days==30)
            btn.clicked.connect(lambda checked,d=days:self.change_range(d))
            self.range_buttons[days]=btn
            filters.addWidget(btn)
        filters.addStretch()
        graph_layout.addLayout(filters)
        self.chart=PriceChart()
        graph_layout.addWidget(self.chart)
        self.change_label=QLabel('')
        self.change_label.setStyleSheet('color:#aab9d0;font-size:13px')
        graph_layout.addWidget(self.change_label)
        self.range_days=30
        self.history_loader=None
        self.history_id=None
        right_layout.addWidget(graph)
        self.query_button=QToolButton()
        self.query_button.setText('Consultar precio en CardTrader')
        self.query_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.query_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.query_button.setMinimumHeight(42)
        self.query_button.setObjectName('primary')
        right_layout.addWidget(self.query_button)
        self.identify_button=QPushButton('Revisar / corregir impresión')
        self.identify_button.setToolTip('Busca la expansión y el blueprint exactos cuando el catálogo no reconoce esta impresión.')
        right_layout.addWidget(self.identify_button)
        right_layout.addStretch()
        self.columns.addWidget(right,3)
        scroll.setWidget(content)
        self.image_data=None
        self.worker=None

    def show_card(self,name,identifier,image,details,price=None):
        self.title.setText(name)
        self.info.setText('Identificador: '+identifier+'\n'+details)
        self.show_price(price)
        self.history_id=identifier
        self.refresh_history()
        self.picture.setText('Cargando imagen...')
        self.picture.setPixmap(QPixmap())
        self.image_data=None
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
        worker=ImageFetch([('detail',image)])
        self.worker=worker
        worker.received.connect(lambda _id,data,w=worker:self.image_loaded(data) if self.worker is w else None)
        worker.failed.connect(lambda _id,msg,w=worker:self.picture.setText(msg) if self.worker is w else None)
        worker.start()

    def show_price(self,price):
        self.updated.setText('')
        if price is None:
            self.price_heading.setText('PRECIO CARDTRADER')
            self.current_price.setText('Sin consultar')
            self.price_subtitle.setText('Pulsa el botón para buscar ofertas en CardTrader para el idioma de esta carta.')
            return
        status=price.get('status')
        failure_titles={
            'catalog_missing':'IMPRESIÓN NO ENCONTRADA','expansion_unmatched':'EXPANSIÓN NO ASOCIADA',
            'blueprint_unmatched':'IMPRESIÓN NO ASOCIADA','no_offers':'SIN OFERTAS EN ESTE IDIOMA',
            'language_mismatch':'IDIOMA Y EXPANSIÓN NO COINCIDEN',
            'api_error':'ERROR DE CONSULTA CARDTRADER','error':'ERROR DE CONSULTA CARDTRADER'}
        if status in failure_titles:
            self.price_heading.setText(failure_titles[status])
            self.current_price.setText('Sin ofertas' if status=='no_offers' else ('Revisar idioma' if status=='language_mismatch' else 'Sin cotización'))
            self.price_subtitle.setText(str(price.get('message') or 'Vuelve a consultar para actualizar el resultado.'))
            when=price.get('fetched_at')
            self.updated.setText('Último intento: '+datetime.datetime.fromtimestamp(int(when)).strftime('%d/%m/%Y %H:%M') if when else '')
            return
        amount=price.get('amount')
        if amount is None:amount=price.get('trend') if price.get('trend') is not None else price.get('avg')
        if status=='verified':
            self.price_heading.setText('PRECIO VERIFICADO MANUALMENTE')
            self.current_price.setText(euros(amount))
            self.price_subtitle.setText(price.get('note') or 'Valor manual · '+str(price.get('source','')))
            self.updated.setText('Última modificación: '+datetime.datetime.fromtimestamp(int(price.get('fetched_at') or price.get('updated_at'))).strftime('%d/%m/%Y %H:%M') if price.get('fetched_at') or price.get('updated_at') else '')
            return
        if status not in ('market_api','market_api_stale'):
            self.price_heading.setText('PRECIO CARDTRADER')
            self.current_price.setText('Sin consultar')
            self.price_subtitle.setText('Todavía no hay una cotización de CardTrader para esta carta.')
            return
        self.price_heading.setText('ÚLTIMA COTIZACIÓN CARDTRADER' if status=='market_api_stale' else 'PRECIO CARDTRADER')
        self.current_price.setText(euros(amount))
        if status=='market_api_stale':
            self.price_subtitle.setText(str(price.get('message') or 'Precio guardado de la última consulta válida; puede no estar disponible ahora.'))
        else:
            self.price_subtitle.setText('Idioma: '+str(price.get('language') or price.get('source') or '—')+((' · '+str(price['offers'])+' ofertas compatibles') if price.get('offers') else ''))
        when=price.get('fetched_at')
        self.updated.setText('Última consulta: '+datetime.datetime.fromtimestamp(int(when)).strftime('%d/%m/%Y %H:%M') if when else '')

    def change_range(self,days):
        self.range_days=days
        for value,button in self.range_buttons.items():button.setChecked(value==days)
        self.refresh_history()

    def refresh_history(self):
        if not self.history_loader or not self.history_id:return
        cutoff=int(time.time())-self.range_days*86400
        points=self.history_loader(self.history_id,cutoff)
        self.chart.set_points(points)
        if len(points)<2:
            if points:
                date=datetime.datetime.fromtimestamp(points[0][0]).strftime('%d/%m/%Y %H:%M')
                self.change_label.setText('1 precio registrado: '+euros(points[0][1])+' · '+date+' · La gráfica crecerá con las próximas consultas.')
            else:
                last=self.history_loader(self.history_id,0)
                if last:
                    date=datetime.datetime.fromtimestamp(last[-1][0]).strftime('%d/%m/%Y')
                    self.change_label.setText('Último precio registrado el '+date+' (fuera del período seleccionado). Prueba 90 días.')
                else:
                    self.change_label.setText('Aún no hay consultas anteriores de CardTrader para esta copia.')
            self.change_label.setStyleSheet('font-size:13px;color:#aab9d0')
            return
        old,new=points[0][1],points[-1][1]
        change=new-old
        percentage=f' ({change/old:+.2%})' if old else ''
        self.change_label.setText('Cambio en el período: '+('+' if change>0 else '')+euros(change)+percentage+' · '+str(len(points))+' registros')
        self.change_label.setStyleSheet('font-size:13px;color:'+('#65d6a0' if change>0 else '#ff9b9b' if change<0 else '#aab9d0'))

    def image_loaded(self,data):
        self.image_data=data
        self.resize_image()

    def resize_image(self):
        if not self.image_data:return
        pix=QPixmap()
        if not pix.loadFromData(self.image_data):return
        width=max(180,min(410,self.picture.width()-20))
        height=max(280,min(580,self.picture.height()-12))
        self.picture.setPixmap(pix.scaled(width,height,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.resize_image()

class CardTraderDialog(QDialog):
    """Keep the modal dialog alive until its network workers have stopped."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers=set()
        self._close_requested=False
        self._pending_result=None

    def track_worker(self, worker):
        self._workers.add(worker)
        worker.finished.connect(lambda current=worker:self._worker_finished(current))

    def _running_workers(self):
        running=[]
        for worker in tuple(self._workers):
            try:
                if worker.isRunning():running.append(worker)
            except RuntimeError:
                self._workers.discard(worker)
        return running

    def _defer_close(self, result):
        self._close_requested=True
        self._pending_result=result
        self.setEnabled(False)
        title=self.windowTitle()
        if 'finalizando consultas' not in title:
            self.setWindowTitle(title+' · finalizando consultas…')

    def _worker_finished(self, worker):
        self._workers.discard(worker)
        try:worker.deleteLater()
        except RuntimeError:pass
        if self._close_requested and not self._running_workers():
            result=self._pending_result
            self._close_requested=False
            self._pending_result=None
            QTimer.singleShot(0,lambda result=result:QDialog.done(self,result))

    def done(self, result):
        if self._running_workers():
            self._defer_close(result)
            return
        super().done(result)

    def reject(self):
        self.done(QDialog.DialogCode.Rejected)

    def accept(self):
        self.done(QDialog.DialogCode.Accepted)

    def closeEvent(self, event):
        if self._running_workers():
            event.ignore()
            self._defer_close(QDialog.DialogCode.Rejected)
            return
        super().closeEvent(event)


class CardTraderApiWorker(QThread):
    done=Signal(object,str)
    def __init__(self,key,action,term='',expansion_id='',blueprint_id='',language='',variant=''):
        super().__init__();self.key=key;self.action=action;self.term=term;self.expansion_id=expansion_id;self.blueprint_id=blueprint_id;self.language=language;self.variant=variant
    def run(self):
        try:
            if self.action=='info':path='/info'
            elif self.action=='expansions':
                req=urllib.request.Request('https://api.cardtrader.com/api/v2/games',headers={'Authorization':'Bearer '+self.key,'Accept':'application/json','User-Agent':'PokeVault/4.2'})
                with urllib.request.urlopen(req,timeout=25) as resp:games=cardtrader_records(json.load(resp),'/games')
                pokemon=next((g for g in games if normalized_name(g.get('name'))=='pokemon' or normalized_name(g.get('display_name'))=='pokemon'),None)
                if not pokemon:raise ValueError('CardTrader no devolvió el juego Pokémon en /games')
                req=urllib.request.Request('https://api.cardtrader.com/api/v2/expansions',headers={'Authorization':'Bearer '+self.key,'Accept':'application/json','User-Agent':'PokeVault/4.2'})
                with urllib.request.urlopen(req,timeout=45) as resp:all_expansions=cardtrader_records(json.load(resp),'/expansions')
                expansions=[x for x in all_expansions if str(x.get('game_id'))==str(pokemon.get('id'))]
                self.done.emit(expansions,'');return
            elif self.action=='blueprints':path='/blueprints/export?'+urllib.parse.urlencode({'expansion_id':self.expansion_id})
            elif self.action=='offers':
                params={'blueprint_id':self.blueprint_id}
                query_language=cardtrader_query_language(self.language)
                if query_language:params['language']=query_language
                foil=cardtrader_finish_filter(self.variant)
                if foil is not None:params['foil']='true' if foil else 'false'
                path='/marketplace/products?'+urllib.parse.urlencode(params)
            else:raise ValueError('Acción de CardTrader no reconocida')
            req=urllib.request.Request('https://api.cardtrader.com/api/v2'+path,headers={'Authorization':'Bearer '+self.key,'Accept':'application/json','User-Agent':'PokeVault/4.2'})
            with urllib.request.urlopen(req,timeout=45) as resp:data=json.load(resp)
            if self.action=='offers' and params.get('foil') is not None:
                rows=data.get(str(self.blueprint_id),[]) if isinstance(data,dict) else data if isinstance(data,list) else []
                if isinstance(rows,dict):rows=rows.get('products',rows.get('data',[]))
                if not rows:
                    params.pop('foil',None)
                    req=urllib.request.Request('https://api.cardtrader.com/api/v2/marketplace/products?'+urllib.parse.urlencode(params),headers={'Authorization':'Bearer '+self.key,'Accept':'application/json','User-Agent':'PokeVault/4.2'})
                    with urllib.request.urlopen(req,timeout=45) as resp:data=json.load(resp)
            self.done.emit(data,'')
        except urllib.error.HTTPError as exc:
            explanations={401:'Token JWT no válido o caducado. Copia uno nuevo desde CardTrader.',403:'CardTrader denegó el acceso. El token funciona, pero tu cuenta podría no tener permiso para la API de mercado.',404:'CardTrader no encontró esa expansión o blueprint.',429:'Límite de consultas alcanzado; espera un momento y vuelve a intentarlo.'}
            self.done.emit(None,explanations.get(exc.code,'Error HTTP '+str(exc.code)))
        except Exception as exc:self.done.emit(None,str(exc))

class CardTraderAutoPriceWorker(QThread):
    done=Signal(object,str)
    def __init__(self,token,card_id,name,set_name,number,language,condition='Near Mint',variant='Sin verificar',mapping=None,expansion_cache=None,catalog_cache=None):
        super().__init__();self.token=token;self.card_id=card_id;self.name=name;self.set_name=set_name;self.number=number;self.language=language;self.condition=condition;self.variant=variant;self.mapping=mapping;self.expansion_cache=expansion_cache or [];self.catalog_cache=catalog_cache or {};self.catalog_updates={};self.phase='validación del idioma'
    def get_json(self,path,timeout=45):
        req=urllib.request.Request('https://api.cardtrader.com/api/v2'+path,headers={'Authorization':'Bearer '+self.token,'Accept':'application/json','User-Agent':'PokeVault/4.4'})
        with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)
    def run(self):
        try:
            self.phase='validación del idioma'
            locale=cardtrader_language(self.language)
            if not locale:raise ValueError('No se puede cotizar automáticamente: idioma no especificado o no compatible.')
            if self.mapping:
                expansion={'id':self.mapping['expansion_id'],'name':self.mapping['expansion_name'],'code':self.mapping['expansion_code']}
                blueprint={'id':self.mapping['blueprint_id'],'name':self.mapping['blueprint_name']}
                number_hint=self.mapping['collector_number']
                mapping_confirmed=True
                self.phase='validación de idioma e impresión'
                mismatch=cardtrader_language_mismatch(self.language,expansion)
                if mismatch:raise ValueError(mismatch)
            else:
                self.phase='búsqueda de impresión en el catálogo'
                source_card,localized_card=find_localized_catalog_print(self.card_id,self.language)
                localized_set=localized_card.get('set') or {}
                set_id=str(localized_set.get('id') or '')
                source_set_id=str((source_card.get('set') or {}).get('id') or str(self.card_id).rsplit('-',1)[0])
                catalog_language='en' if locale=='es' else tcgdex_locale(self.language)
                set_name=str(localized_set.get('name') or self.set_name or '')
                set_aliases={normalized_name(set_name)} if set_name else set()
                # Some TCGdex card rows expose the translated set title even
                # when the card itself came from the English catalog. CardTrader
                # stores the expansion's English title, so resolve the canonical
                # set record before deciding that no CardTrader expansion exists.
                if set_id:
                    try:
                        english_set=tcgdex_get_set(set_id,'en')
                        english_title=str((english_set or {}).get('name') or '')
                        if english_title:set_aliases.add(normalized_name(english_title))
                    except Exception:pass
                local_id=str(localized_card.get('localId') or self.number or '')
                card_count=localized_set.get('cardCount') or {}
                official_count=str(card_count.get('official') or '')
                if localized_card.get('_cardtrader_number'):
                    number_hint=str(localized_card['_cardtrader_number'])
                else:
                    width=max(3,len(local_id),len(official_count))
                    number_hint=local_id.zfill(width)
                    if official_count:number_hint+='/'+official_count.zfill(width)
                self.phase='búsqueda de expansión CardTrader'
                cached=sorted((item for item in self.expansion_cache
                    if item.get('catalog_language')==catalog_language and
                    ((set_id and item.get('catalog_set_id')==set_id) or
                     (source_set_id and item.get('source_set_id')==source_set_id and
                      (catalog_language=='en' or (item.get('origin')=='manual' and not item.get('catalog_set_id')))))),
                    key=lambda item:(item.get('catalog_set_id')!=set_id,bool(item.get('catalog_set_id'))),reverse=False)
                if cached:
                    saved=cached[0]
                    expansion={'id':saved['expansion_id'],'name':saved['expansion_name'],'code':saved.get('expansion_code','')}
                else:
                    games=cardtrader_records(self.get_json('/games',25),'/games')
                    pokemon=next((g for g in games if normalized_name(g.get('name'))=='pokemon' or normalized_name(g.get('display_name'))=='pokemon'),None)
                    if not pokemon:raise ValueError('CardTrader no identificó el catálogo de Pokémon.')
                    all_expansions=cardtrader_records(self.get_json('/expansions'),'/expansions')
                    pokemon_expansions=[e for e in all_expansions if str(e.get('game_id'))==str(pokemon.get('id'))]
                    set_key=re.sub(r'[^a-z0-9]','',normalized_name(set_id))
                    set_code_keys={set_key} if set_key else set()
                    # Simplified Chinese set IDs commonly end in C while
                    # CardTrader's expansion code omits that market suffix
                    # (for example CSV9C -> CSV9). Exact IDs stay preferred.
                    if catalog_language=='zh-cn' and set_key.endswith('c') and len(set_key)>1:
                        set_code_keys.add(set_key[:-1])
                    set_titles=set_aliases or {normalized_name(set_name)}
                    candidates=[e for e in pokemon_expansions if
                        (re.sub(r'[^a-z0-9]','',normalized_name(e.get('code',''))) in set_code_keys)
                        or normalized_name(e.get('name','')) in set_titles]
                    if len(candidates)!=1:
                        raise ValueError('TCGdex encontró la impresión '+(set_name+' ('+set_id+')' if set_name else set_id)+', pero CardTrader no devolvió una única expansión equivalente. Usa «Identificar impresión manualmente».')
                    expansion=candidates[0]
                expansion_mapping={'catalog_language':catalog_language,'source_set_id':source_set_id,'catalog_set_id':set_id,
                    'expansion_id':str(expansion.get('id','')),'expansion_name':str(expansion.get('name','')),'expansion_code':str(expansion.get('code',''))}
                self.phase='validación de idioma e impresión'
                mismatch=cardtrader_language_mismatch(self.language,expansion)
                if mismatch:raise ValueError(mismatch)
                self.phase='búsqueda de blueprint e impresión'
                catalog_key=str(expansion.get('id'))
                cached_catalog=self.catalog_cache.get(catalog_key)
                if cached_catalog:
                    blueprints=cached_catalog.get('blueprints',[])
                    listings=cached_catalog.get('listings',[])
                else:
                    blueprints=cardtrader_records(self.get_json('/blueprints/export?'+urllib.parse.urlencode({'expansion_id':expansion.get('id')})),'/blueprints/export')
                    # Marketplace rows carry collector numbers, which are more reliable than blueprint.version.
                    marketplace=self.get_json('/marketplace/products?'+urllib.parse.urlencode({'expansion_id':expansion.get('id')}))
                    listings=[]
                    if isinstance(marketplace,dict):
                        for group_id,group in marketplace.items():
                            group=group.get('products',group.get('data',[])) if isinstance(group,dict) else group
                            for listing in group if isinstance(group,list) else []:
                                if isinstance(listing,dict):
                                    listing=dict(listing);listing.setdefault('blueprint_id',group_id);listings.append(listing)
                    elif isinstance(marketplace,list):listings=[x for x in marketplace if isinstance(x,dict)]
                    self.catalog_updates[catalog_key]={'blueprints':blueprints,'listings':listings}
                names={normalized_name(source_card.get('name')),normalized_name(localized_card.get('name')),normalized_name(self.name)}-{''}
                name_matches=[b for b in blueprints if normalized_name(b.get('name','')) in names or any(n and n in normalized_name(b.get('name','')) for n in names)]
                product_matches=[]
                for listing in listings:
                    listing_name=normalized_name(listing.get('name_en') or listing.get('name') or '')
                    listing_properties=listing.get('properties_hash') or listing.get('properties') or {}
                    listing_number=str(listing.get('collector_number') or (listing_properties.get('collector_number') if isinstance(listing_properties,dict) else '') or '')
                    same_name=listing_name in names or any(n and (n in listing_name or listing_name in n) for n in names)
                    same_number=collector_number_matches(listing_number,number_hint) or collector_number_matches(listing_number,local_id)
                    if same_name and same_number:product_matches.append(str(listing.get('blueprint_id') or ''))
                product_matches={value for value in product_matches if value}
                blueprint_by_id={str(item.get('id')):item for item in blueprints}
                exact=[blueprint_by_id[value] for value in product_matches if value in blueprint_by_id]
                if not exact:
                    exact=[]
                    for item in name_matches:
                        number_fields=' '.join(str(item.get(key) or '') for key in ('name','version','number','card_number','local_id','localId'))
                        if collector_number_matches(number_fields,number_hint) or collector_number_matches(number_fields,local_id):exact.append(item)
                if not exact and not number_hint and not local_id and len(name_matches)==1:exact=name_matches
                if len(exact)!=1:
                    raise ValueError('La impresión equivalente es '+set_name+' · '+number_hint+', pero CardTrader no devolvió un único blueprint compatible. Usa «Identificar impresión manualmente».')
                blueprint=exact[0]
                mapping_confirmed=True
            self.phase='búsqueda de ofertas por idioma'
            query={'blueprint_id':blueprint.get('id')}
            query_language=cardtrader_query_language(self.language)
            if query_language:query['language']=query_language
            foil_filter=cardtrader_finish_filter(self.variant)
            if foil_filter is not None:query['foil']='true' if foil_filter else 'false'
            params=urllib.parse.urlencode(query)
            data=self.get_json('/marketplace/products?'+params)
            rows=data.get(str(blueprint.get('id')),[]) if isinstance(data,dict) else data if isinstance(data,list) else []
            if isinstance(rows,dict):rows=rows.get('products',rows.get('data',[]))
            # Some CardTrader Pokémon blueprints have no usable generic foil
            # filter. Retry only when it returns an empty list, keeping the
            # server-side language filter and checking finish on each offer.
            if not rows and foil_filter is not None:
                query.pop('foil',None)
                params=urllib.parse.urlencode(query)
                data=self.get_json('/marketplace/products?'+params)
                rows=data.get(str(blueprint.get('id')),[]) if isinstance(data,dict) else data if isinstance(data,list) else []
                if isinstance(rows,dict):rows=rows.get('products',rows.get('data',[]))
            accepted=[];conflicts=[];rejections=[]
            for offer in rows if isinstance(rows,list) else []:
                if not isinstance(offer,dict):continue
                compatible,reason=cardtrader_offer_compatibility(offer,self.language,self.condition,self.variant,locale,not bool(query_language))
                if not compatible:
                    rejections.append(reason)
                    if reason=='idioma':
                        props=offer.get('properties_hash') or offer.get('properties') or {}
                        if isinstance(props,dict):conflicts.extend(v for k,v in props.items() if 'language' in str(k).casefold())
                    continue
                price=offer.get('price') or {}
                cents=price.get('cents') if isinstance(price,dict) else None
                currency=price.get('currency') if isinstance(price,dict) else None
                if cents is None:cents=offer.get('price_cents')
                if currency is None:currency=offer.get('price_currency')
                if cents is None or str(currency or '').upper()!='EUR':continue
                try:amount=float(cents)/100
                except (ValueError,TypeError):continue
                if 0<=amount<=1000000:accepted.append(amount)
            if not accepted:
                message=('La impresión CardTrader guardada no tiene ofertas EUR compatibles con idioma, estado y acabado.' if self.mapping else 'La impresión se identificó automáticamente, pero CardTrader no tiene ofertas EUR compatibles con idioma, estado y acabado.')+(' No hay ofertas que coincidan con el estado/acabado de la copia ('+self.condition+' · '+self.variant+').' if rejections else '')+(' La API devolvió ofertas de otro idioma.' if conflicts else '')
                if mapping_confirmed:
                    self.done.emit({'blueprint_id':str(blueprint.get('id')),'expansion_id':str(expansion.get('id','')),
                        'expansion':expansion.get('name',''),'expansion_code':str(expansion.get('code','')),
                        'card_name':blueprint.get('name',''),'collector_number':str(number_hint or ''),
                        'language':locale,'mapping_confirmed':True,'no_offers':True,'lookup_stage':self.phase,'expansion_mapping':locals().get('expansion_mapping'),'catalog_updates':self.catalog_updates},message)
                    return
                raise ValueError(message)
            accepted.sort();floor=accepted[0];used=accepted[:5]
            # Ignore extreme marketplace outliers so one implausible listing
            # cannot dominate a collection price (e.g. 3.31 € and 10,000 €).
            reasonable=[amount for amount in used if amount<=max(floor*10,floor+100)] or [floor]
            self.done.emit({'blueprint_id':str(blueprint.get('id')),'amount':sum(reasonable)/len(reasonable),'floor':floor,
                'offers':len(accepted),'language':locale,'expansion_id':str(expansion.get('id','')),'expansion':expansion.get('name',''),'expansion_code':str(expansion.get('code','')),
                'card_name':blueprint.get('name',''),'collector_number':str(number_hint or ''),'mapping_confirmed':mapping_confirmed,
                'source_url':'https://api.cardtrader.com/api/v2/marketplace/products?'+params,'lookup_stage':self.phase,
                'expansion_mapping':locals().get('expansion_mapping'),'catalog_updates':self.catalog_updates},'')
        except urllib.error.HTTPError as exc:
            explanations={401:'El token de CardTrader no es válido o ha caducado.',403:'CardTrader denegó la API de mercado; puede que tu cuenta necesite autorización para precios.',429:'Límite de consultas alcanzado. Inténtalo más tarde.'}
            self.done.emit({'lookup_stage':self.phase,'catalog_updates':self.catalog_updates},explanations.get(exc.code,'Error HTTP '+str(exc.code)))
        except Exception as exc:self.done.emit({'lookup_stage':self.phase,'catalog_updates':self.catalog_updates},str(exc))

