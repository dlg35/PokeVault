"""WishlistTab tab behavior for PokeVault.

Methods use the shared widgets, services and database helpers in app_core.
"""
from app_core import *


class WishlistTabMixin:
    def add_wish(self,card):
        albums=self.db.execute('SELECT id,name FROM wishlist_albums ORDER BY name COLLATE NOCASE').fetchall()
        dlg=CardDialog(self,cid=card.get('id',''),wish_albums=albums)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        lang,cond,var,qty=dlg.values();cid=card.get('id','');album_id=dlg.wish_album.currentData()
        previous=self.db.execute('SELECT id,quantity FROM wishlist WHERE card_id=? AND language=? AND condition=? AND variant=?',(cid,lang,cond,var)).fetchone()
        if previous:
            if previous[1]+qty>9999:QMessageBox.warning(self,'Límite','Máximo 9999 copias.');return
            self.db.execute('UPDATE wishlist SET quantity=quantity+?,album_id=? WHERE id=?',(qty,album_id,previous[0]))
        else:
            set_name=card.get('set',{}).get('name','') if isinstance(card.get('set'),dict) else ''
            self.db.execute('INSERT INTO wishlist(card_id,name,set_name,number,image,language,condition,variant,quantity,added_at,album_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cid,card.get('name',''),set_name,card.get('localId',''),card.get('image',''),lang,cond,var,qty,int(time.time()),album_id))
        self.db.commit();self.refresh_wishlist();self.refresh_wish_albums()
        if not cid.startswith('manual-'):self.update_prices(ids=[cid])
        QMessageBox.information(self,'Lista de deseos','Carta guardada en tu lista de deseos.')

    def build_wishlist_tab(self,tabs):
        wish=QWidget();wl=QVBoxLayout(wish);wl.setContentsMargins(16,16,16,14);wl.setSpacing(12)
        wishbar=QHBoxLayout();wishbar.setSpacing(8)
        self.wish_view=QComboBox();self.wish_view.addItem('Ver álbumes','albums');self.wish_view.addItem('Todas las cartas','all');self.wish_view.addItem('Sin álbum','unassigned');wishbar.addWidget(self.wish_view)
        self.create_album_button=QPushButton('＋ Crear álbum');self.create_album_button.setObjectName('primary');self.create_album_button.clicked.connect(self.create_wish_album);wishbar.addWidget(self.create_album_button)
        self.wish_search=QLineEdit();self.wish_search.setPlaceholderText('Buscar en deseos por nombre o ID')
        self.wish_search.textChanged.connect(self.refresh_wishlist);wishbar.addWidget(self.wish_search,1)
        wish_filters=QHBoxLayout();wish_filters.setSpacing(8);wish_filters.addWidget(QLabel('ORDENAR Y FILTRAR'))
        self.wish_sort=QComboBox()
        for label,key in [('Fecha: recientes','new'),('Fecha: antiguos','old'),('Precio: menor a mayor','price_asc'),('Precio: mayor a menor','price_desc'),('Nombre A-Z','name'),('Expansión','set')]:self.wish_sort.addItem(label,key)
        self.wish_sort.currentIndexChanged.connect(self.refresh_wishlist);wish_filters.addWidget(self.wish_sort,2)
        self.wish_language=QComboBox();self.wish_language.addItem('Todos los idiomas','')
        for lang in ('Español','Inglés','Japonés','Chino simplificado','Chino tradicional'):self.wish_language.addItem(lang,lang)
        self.wish_language.addItem('Chino (sin especificar)','Chino')
        self.wish_language.currentIndexChanged.connect(self.refresh_wishlist);wish_filters.addWidget(self.wish_language)
        self.wish_finish=QComboBox();self.wish_finish.addItem('Todos los acabados','')
        for finish in ('Normal','Holo','Reverse','Especial','Sin verificar'):self.wish_finish.addItem(finish,finish)
        self.wish_finish.currentIndexChanged.connect(self.refresh_wishlist);wish_filters.addWidget(self.wish_finish)
        wl.addLayout(wishbar);wl.addLayout(wish_filters)
        self.wish_stack=QStackedWidget()
        cards_page=QWidget();cards_page_layout=QVBoxLayout(cards_page);cards_page_layout.setContentsMargins(0,0,0,0)
        album_nav=QHBoxLayout()
        self.wish_back_button=QPushButton('← Volver a álbumes');self.wish_back_button.clicked.connect(self.back_to_wish_albums);self.wish_back_button.hide();album_nav.addWidget(self.wish_back_button)
        self.wish_album_title=QLabel('');self.wish_album_title.setObjectName('sectionTitle');album_nav.addWidget(self.wish_album_title)
        self.export_wish_album_button=QPushButton('Exportar álbum CSV');self.export_wish_album_button.clicked.connect(self.export_current_wish_album);self.export_wish_album_button.hide();album_nav.addWidget(self.export_wish_album_button);album_nav.addStretch()
        cards_page_layout.addLayout(album_nav)
        self.wish_summary=QLabel('');self.wish_summary.setObjectName('summaryPanel')
        cards_page_layout.addWidget(self.wish_summary)
        self.wish_scroll=QScrollArea();self.wish_scroll.setWidgetResizable(True)
        self.wish_area=QWidget();self.wish_layout=QGridLayout(self.wish_area)
        self.wish_layout.setContentsMargins(8,8,8,8);self.wish_layout.setSpacing(14);self.wish_layout.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignHCenter)
        self.wish_scroll.setWidget(self.wish_area);cards_page_layout.addWidget(self.wish_scroll)
        self.wish_stack.addWidget(cards_page)
        albums_page=QWidget();albums_page_layout=QVBoxLayout(albums_page);albums_page_layout.setContentsMargins(0,0,0,0)
        self.album_summary=QLabel('Crea álbumes y organiza tus cartas deseadas.');self.album_summary.setObjectName('summaryPanel');albums_page_layout.addWidget(self.album_summary)
        self.album_scroll=QScrollArea();self.album_scroll.setWidgetResizable(True)
        self.album_area=QWidget();self.album_layout=QGridLayout(self.album_area);self.album_layout.setContentsMargins(8,8,8,8);self.album_layout.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignHCenter);self.album_layout.setSpacing(16)
        self.album_scroll.setWidget(self.album_area);albums_page_layout.addWidget(self.album_scroll)
        self.wish_stack.addWidget(albums_page);wl.addWidget(self.wish_stack,1)
        self.wish_tiles=[];self.album_tiles=[];self.selected_wish_album_id=None;self.show_unassigned_wishes=False
        self.wish_view.currentIndexChanged.connect(self.change_wish_view)
        self.change_wish_view()
        tabs.addTab(wish,'♡  Lista de deseos')

    def change_wish_view(self,index=None):
        mode=self.wish_view.currentData()
        self.selected_wish_album_id=None
        if mode=='albums':
            self.show_unassigned_wishes=False
            self.wish_back_button.hide();self.wish_album_title.setText('')
            self.export_wish_album_button.hide()
            self.wish_stack.setCurrentIndex(1)
            self.refresh_wish_albums()
        else:
            self.show_unassigned_wishes=(mode=='unassigned')
            self.wish_back_button.hide();self.export_wish_album_button.hide()
            self.wish_album_title.setText('Sin álbum' if self.show_unassigned_wishes else '')
            self.wish_stack.setCurrentIndex(0)
            self.refresh_wishlist()

    def create_wish_album(self):
        name,ok=QInputDialog.getText(self,'Crear álbum','Nombre del álbum:')
        name=name.strip()
        if not ok or not name:return
        try:
            self.db.execute('INSERT INTO wishlist_albums(name,created_at) VALUES(?,?)',(name,int(time.time())))
            self.db.commit()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self,'Nombre repetido','Ya existe un álbum con ese nombre.')
            return
        self.refresh_wish_albums()

    def refresh_wish_albums(self):
        self.album_generation+=1;generation=self.album_generation
        while self.album_layout.count():
            item=self.album_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        rows=self.db.execute('SELECT a.id,a.name,COUNT(w.id) FROM wishlist_albums a LEFT JOIN wishlist w ON w.album_id=a.id GROUP BY a.id,a.name ORDER BY a.name COLLATE NOCASE').fetchall()
        self.album_tiles=[];targets={};entries=[]
        for row in rows:
            previews=[image_row[0] for image_row in self.db.execute('SELECT image FROM wishlist WHERE album_id=? AND COALESCE(image,\'\')<>\'\' ORDER BY added_at DESC,id DESC LIMIT 3',(row[0],)).fetchall()]
            tile=AlbumTile((*row,previews),self.open_wish_album,self.rename_wish_album,self.delete_wish_album)
            self.album_tiles.append(tile)
            for url,labels in tile.preview_targets.items():
                targets[url]=[(tile,label) for label in labels]
                entries.append((url,url))
        self.reflow(self.album_layout,self.album_tiles,280,self.album_scroll)
        if entries:self.images(entries,targets,generation=generation,album=True)
        count=sum(row[2] for row in rows)
        self.album_summary.setText(f'{len(rows)} álbumes · {count} cartas organizadas' if rows else 'Aún no tienes álbumes. Pulsa «＋ Crear álbum» para empezar.')

    def open_wish_album(self,album_id):
        row=self.db.execute('SELECT name FROM wishlist_albums WHERE id=?',(album_id,)).fetchone()
        if not row:return
        self.selected_wish_album_id=album_id
        self.show_unassigned_wishes=False
        self.wish_album_title.setText(row[0])
        self.wish_back_button.show()
        self.export_wish_album_button.show()
        self.wish_stack.setCurrentIndex(0)
        self.refresh_wishlist()

    def back_to_wish_albums(self):
        self.selected_wish_album_id=None
        self.show_unassigned_wishes=False
        self.wish_back_button.hide();self.wish_album_title.setText('')
        self.export_wish_album_button.hide()
        self.wish_stack.setCurrentIndex(1)
        self.refresh_wish_albums()

    def export_current_wish_album(self):
        if self.selected_wish_album_id is not None:self.export_wish_album(self.selected_wish_album_id)

    def export_wish_album(self,album_id):
        album=self.db.execute('SELECT name FROM wishlist_albums WHERE id=?',(album_id,)).fetchone()
        if not album:return
        safe_name=re.sub(r'[\\/:*?"<>|]+','_',album[0]).strip() or 'album'
        filename,_=QFileDialog.getSaveFileName(self,'Exportar álbum a CSV',str(Path.home()/(safe_name+'.csv')),'CSV (*.csv)')
        if not filename:return
        rows=self.db.execute('SELECT name,set_name,number,language,condition,variant,quantity,card_id FROM wishlist WHERE album_id=? ORDER BY name COLLATE NOCASE',(album_id,)).fetchall()
        try:
            with open(filename,'w',newline='',encoding='utf-8-sig') as output:
                fields=['Nombre','Expansión','Número','Idioma','Estado','Acabado','Cantidad','Precio general unitario (EUR)','Valor general total (EUR)','Fuente del precio']
                writer=csv.DictWriter(output,fieldnames=fields,delimiter=';')
                writer.writeheader()
                for name,set_name,number,language,condition,variant,quantity,card_id in rows:
                    price=self.get_price(card_id)
                    amount=price.get('trend') if price else None
                    if amount is None and price:amount=price.get('avg')
                    writer.writerow({'Nombre':name,'Expansión':set_name or card_id.split('-',1)[0],'Número':number,'Idioma':language,'Estado':condition,'Acabado':FINISH_LABELS.get(variant,variant),'Cantidad':quantity,'Precio general unitario (EUR)':f'{amount:.2f}' if amount is not None else '', 'Valor general total (EUR)':f'{amount*quantity:.2f}' if amount is not None else '', 'Fuente del precio':'TCGdex / Cardmarket (general)' if amount is not None else 'Sin precio'})
        except OSError as exc:
            QMessageBox.critical(self,'Error al exportar','No se pudo guardar el CSV: '+str(exc));return
        self.statusBar().showMessage(f'Álbum «{album[0]}» exportado a CSV ({len(rows)} cartas).',8000)

    def rename_wish_album(self,album_id,current_name):
        name,ok=QInputDialog.getText(self,'Renombrar álbum','Nombre del álbum:',text=current_name)
        name=name.strip()
        if not ok or not name:return
        try:
            self.db.execute('UPDATE wishlist_albums SET name=? WHERE id=?',(name,album_id));self.db.commit()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self,'Nombre repetido','Ya existe un álbum con ese nombre.')
            return
        if self.selected_wish_album_id==album_id:self.wish_album_title.setText(name)
        self.refresh_wish_albums()

    def delete_wish_album(self,album_id,name):
        count=self.db.execute('SELECT COUNT(*) FROM wishlist WHERE album_id=?',(album_id,)).fetchone()[0]
        reply=QMessageBox.question(self,'Eliminar álbum',f'¿Eliminar «{name}»? Las {count} cartas seguirán en tu lista, pero quedarán sin álbum.',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
        if reply!=QMessageBox.StandardButton.Yes:return
        with self.db:
            self.db.execute('UPDATE wishlist SET album_id=NULL WHERE album_id=?',(album_id,))
            self.db.execute('DELETE FROM wishlist_albums WHERE id=?',(album_id,))
        if self.selected_wish_album_id==album_id:self.back_to_wish_albums()
        else:self.refresh_wish_albums()

    def organize_wish_card(self,card_row_id,current_album_id=None):
        albums=self.db.execute('SELECT id,name FROM wishlist_albums ORDER BY name COLLATE NOCASE').fetchall()
        if not albums:
            QMessageBox.information(self,'Crea un álbum','Primero crea un álbum con «＋ Crear álbum».')
            return
        unassigned_label='— Sin álbum —'
        labels=[unassigned_label]+[row[1] for row in albums]
        current=0
        if current_album_id is not None:
            for i,row in enumerate(albums,1):
                if row[0]==current_album_id:current=i;break
        choice,ok=QInputDialog.getItem(self,'Organizar carta','Álbum:',labels,current,False)
        if not ok:return
        album_id=None if choice==unassigned_label else next((row[0] for row in albums if row[1]==choice),None)
        self.db.execute('UPDATE wishlist SET album_id=? WHERE id=?',(album_id,card_row_id));self.db.commit()
        self.refresh_wishlist();self.refresh_wish_albums()

    def refresh_wishlist(self):
        self.wish_generation+=1;generation=self.wish_generation
        while self.wish_layout.count():
            item=self.wish_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        rows=self.db.execute('SELECT id,card_id,name,language,condition,variant,quantity,image,added_at,album_id,set_name FROM wishlist').fetchall()
        if self.selected_wish_album_id is not None:
            scope_rows=[r for r in rows if r[9]==self.selected_wish_album_id]
        elif self.show_unassigned_wishes:
            scope_rows=[r for r in rows if r[9] is None]
        else:
            scope_rows=rows
        term=self.wish_search.text().strip().casefold()
        lang=self.wish_language.currentData();finish=self.wish_finish.currentData()
        visible=[r for r in scope_rows if (not term or term in r[2].casefold() or term in r[1].casefold()) and (not lang or r[3]==lang) and (not finish or (r[5] or 'Sin verificar')==finish)]
        def amount(r):
            p=self.get_price(r[1]);v=p.get('trend') if p else None
            if v is None and p:v=p.get('avg')
            return v
        mode=self.wish_sort.currentData()
        if mode in ('price_asc','price_desc'):
            visible.sort(key=lambda r:(amount(r) is None, -(amount(r) or 0) if mode=='price_desc' else (amount(r) or 0),r[2]))
        elif mode=='name':visible.sort(key=lambda r:r[2].casefold())
        elif mode=='set':visible.sort(key=lambda r:(r[10] or r[1].split('-',1)[0]).casefold())
        else:visible.sort(key=lambda r:r[8],reverse=mode=='new')
        self.wish_tiles=[];targets={};entries=[]
        for r in visible:
            tile=WishTile(r,self.get_price(r[1]),self.remove_wish,self.move_wish,self.organize_wish_card)
            self.wish_tiles.append(tile);targets.setdefault(r[1],[]).append(tile);entries.append((r[1],r[7]))
        self.reflow(self.wish_layout,self.wish_tiles,250,self.wish_scroll)
        if entries:
            worker=ImageFetch(list(dict(entries).items()))
            def received(cid,data):
                if generation==self.wish_generation:
                    for t in targets.get(cid,[]):t.set_image(data)
            def failed(cid,message):
                if generation==self.wish_generation:
                    for t in targets.get(cid,[]):t.set_missing(message)
            worker.received.connect(received);worker.failed.connect(failed)
            worker.finished.connect(lambda:self.image_workers.remove(worker) if worker in self.image_workers else None)
            self.image_workers.append(worker);worker.start()
        total=sum((amount(r) or 0)*r[6] for r in scope_rows)
        missing=sum(r[6] for r in scope_rows if amount(r) is None)
        title=(self.wish_album_title.text()+' · ' if self.selected_wish_album_id is not None or self.show_unassigned_wishes else '')
        self.wish_summary.setText(f'{title}{sum(r[6] for r in scope_rows)} cartas deseadas · Valor general estimado: {euros(total)}'+(f' · {missing} sin precio' if missing else '')+f' · Mostrando {len(visible)} registros')

    def remove_wish(self,pk):
        if QMessageBox.question(self,'Quitar de deseos','¿Eliminar esta carta de la lista de deseos?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        self.db.execute('DELETE FROM wishlist WHERE id=?',(pk,));self.db.commit();self.refresh_wishlist();self.refresh_wish_albums()

    def move_wish(self,pk):
        r=self.db.execute('SELECT card_id,name,set_name,number,image,language,condition,variant,quantity FROM wishlist WHERE id=?',(pk,)).fetchone()
        if not r:return
        cid,name,set_name,number,image,lang,cond,var,qty=r
        if QMessageBox.question(self,'Pasar a colección',f'¿Mover {qty} copia(s) de {name} a tu colección?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:return
        # Wish-list entries have no confirmed physical blueprint. Merge only
        # into an unidentified row; never attach them to an arbitrary print.
        existing=self.db.execute("SELECT id,quantity FROM cards WHERE card_id=? AND language=? AND condition=? AND variant=? AND physical_print_key='' ORDER BY id LIMIT 1",(cid,lang,cond,var)).fetchone()
        if existing and existing[1]+qty>9999:QMessageBox.warning(self,'Límite','Máximo 9999 copias.');return
        with self.db:
            if existing:
                card_row_id=existing[0]
                self.db.execute('UPDATE cards SET quantity=quantity+? WHERE id=?',(qty,card_row_id))
            else:
                cursor=self.db.execute('INSERT INTO cards(card_id,name,set_name,number,image,language,condition,variant,quantity) VALUES(?,?,?,?,?,?,?,?,?)',r)
                card_row_id=cursor.lastrowid
            self.db.execute('DELETE FROM wishlist WHERE id=?',(pk,))
        self.refresh();self.refresh_wishlist();self.refresh_wish_albums()
        if not cid.startswith('manual-'):
            self.update_prices(ids=[cid]);self.queue_auto_cardtrader_price(card_row_id)
