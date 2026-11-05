"""CollectionTab tab behavior for PokeVault.

Methods use the shared widgets, services and database helpers in app_core.
"""
from app_core import *


class CollectionTabMixin:
    def detail_owned(self,row):
        pk,cid,name,lang,cond,var,qty,img=row
        self.active_owned_row=row
        self.active_price_id=cid
        self.active_price_key=(cid,lang,var or "")
        manual=self.db.execute('SELECT amount,source_url,note,updated_at FROM verified_valuations WHERE card_row_id=?',(pk,)).fetchone()
        quote=self.db.execute('SELECT amount,offers,language,fetched_at,source_url,product_id,condition,variant,floor FROM api_valuations WHERE card_row_id=?',(pk,)).fetchone()
        mapping=self.get_cardtrader_print_mapping(pk,lang)
        mismatch=cardtrader_language_mismatch(lang,mapping)
        quote_matches_print=False
        if manual:
            price={'status':'verified','amount':manual[0],'source':manual[1],'note':manual[2],'fetched_at':manual[3]}
        else:
            expected_language=cardtrader_language(lang)
            quote_language_ok=bool(quote and ((expected_language and normalize_market_language(quote[2])==normalize_market_language(expected_language)) or (not expected_language and normalized_name(lang) in ('chino','chino sin especificar') and normalize_market_language(quote[2]) in ('chinese-s','chinese-t'))))
            quote_matches_print=(not mismatch and bool(mapping and mapping.get('confirmed')) and bool(quote) and str(quote[4]).startswith('https://api.cardtrader.com/api/v2/marketplace/products?') and str(mapping['blueprint_id'])==str(quote[5]) and quote[6]==cond and quote[7]==var and quote_language_ok)
            if quote_matches_print:
                latest=self.db.execute('SELECT outcome,message,attempted_at FROM cardtrader_lookup_attempts WHERE card_row_id=? ORDER BY attempted_at DESC,id DESC LIMIT 1',(pk,)).fetchone()
                stale=bool(latest and latest[0]=='no_offers' and int(latest[2] or 0)>int(quote[3] or 0))
                price={'status':'market_api_stale' if stale else 'market_api','amount':cardtrader_display_amount(quote[0],quote[8]),'offers':quote[1],'language':quote[2],'fetched_at':quote[3],'source':quote[4],'message':latest[1] if stale else ''}
            else:price=None
            if price is None and not mismatch and mapping and mapping.get('confirmed'):
                history=self.last_cardtrader_quote(pk,mapping,cond,var)
                if history:
                    price={'status':'market_api_stale','amount':history[1],'offers':0,'language':mapping['language'],'fetched_at':history[0],
                           'source':'historial CardTrader','message':'No hay una oferta compatible ahora; se conserva la última cotización guardada.'}
        if mismatch and not manual:
            price={'status':'language_mismatch','message':mismatch}
        elif price is None:
            attempt=self.db.execute('SELECT outcome,message,attempted_at FROM cardtrader_lookup_attempts WHERE card_row_id=? ORDER BY attempted_at DESC,id DESC LIMIT 1',(pk,)).fetchone()
            if attempt:
                price={'status':attempt[0],'message':attempt[1],'fetched_at':attempt[2]}
        if quote_matches_print:
            self.db.execute('INSERT OR IGNORE INTO cardtrader_price_history(card_row_id,fetched_at,price,product_id,condition,variant) VALUES(?,?,?,?,?,?)',(pk,int(quote[3]),float(quote[0]),str(quote[5]),quote[6],quote[7]))
            self.db.commit()
        if mapping:
            mapping_state='confirmada' if mapping['confirmed'] else 'propuesta automática · pendiente de confirmar'
            physical_print='Impresión CardTrader: '+str(mapping['expansion_name'])+' · '+str(mapping['collector_number'])+' · '+str(mapping['blueprint_name'])+' ('+mapping_state+')'
            if mismatch:physical_print+='\nAviso: '+mismatch
        else:
            physical_print='Impresión física de CardTrader: pendiente de identificar'
        if not manual and quote and not (mapping and mapping.get('confirmed')):
            physical_print+='\nLa cotización automática está pendiente de confirmar la impresión; no se usa como precio de esta copia.'
        elif not manual and quote and mapping and mapping.get('confirmed') and not quote_matches_print:
            physical_print+='\nLa cotización guardada corresponde a otro blueprint; vuelve a consultar esta impresión.'
        self.collection_detail.query_button.setEnabled(True)
        self.collection_detail.query_button.setText('Consultar precio en CardTrader')
        self.collection_detail.identify_button.setToolTip(str((price or {}).get('message') or 'Revisa la expansión, número e idioma asociados y corrige la impresión de CardTrader si hace falta.'))
        self.collection_detail.show_card(name,cid,img,f'Idioma: {lang}  ·  Estado: {cond}\nAcabado: {FINISH_LABELS.get(var,var)}  ·  Cantidad: {qty}\n{physical_print}',price)
        self.collection_detail.history_id=pk
        self.collection_detail.refresh_history()
        self.collection_stack.setCurrentIndex(1)

    def build_collection_tab(self,tabs):
        coll=QWidget();cl=QVBoxLayout(coll);cl.setContentsMargins(16,16,16,14);cl.setSpacing(12)
        controls=QHBoxLayout();controls.setSpacing(8)
        controls.addWidget(QLabel('Ordenar por:'))
        self.sort_by=QComboBox()
        self.sort_by.addItem('Nombre','name')
        self.sort_by.addItem('Idioma','language')
        self.sort_by.addItem('Expansión','set_name')
        self.sort_by.addItem('Estado','condition')
        self.sort_by.addItem('Cantidad','quantity')
        self.sort_by.addItem('Fecha de incorporación','id')
        self.sort_by.addItem('Valor total','value')
        self.sort_by.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.sort_by)
        self.sort_direction=QComboBox()
        self.sort_direction.addItem('Ascendente','ASC')
        self.sort_direction.addItem('Descendente','DESC')
        self.sort_direction.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.sort_direction)
        controls.addStretch()
        filters=QHBoxLayout();filters.setSpacing(8)
        filters.addWidget(QLabel('FILTRAR'))
        self.collection_search=QLineEdit();self.collection_search.setPlaceholderText('Filtrar mi colección por nombre o ID')
        self.collection_search.textChanged.connect(self.refresh);filters.addWidget(self.collection_search,4)
        self.filter_language=QComboBox();self.filter_language.addItem('Todos los idiomas','')
        for lang in ('Español','Inglés','Japonés','Chino simplificado','Chino tradicional'):self.filter_language.addItem(lang,lang)
        self.filter_language.addItem('Chino (sin especificar)','Chino')
        self.filter_language.currentIndexChanged.connect(self.refresh);filters.addWidget(self.filter_language)
        self.filter_finish=QComboBox();self.filter_finish.addItem('Todos los acabados','')
        for label in ('Normal','Holo','Reverse','Especial','Sin verificar'):self.filter_finish.addItem(label,label)
        self.filter_finish.currentIndexChanged.connect(self.refresh);filters.addWidget(self.filter_finish)
        filters_secondary=QHBoxLayout();filters_secondary.setSpacing(8)
        self.filter_condition=QComboBox();self.filter_condition.addItem('Todos los estados','')
        for condition in ('Near Mint','Excellent','Good','Light Played','Played','Poor'):self.filter_condition.addItem(condition,condition)
        self.filter_condition.currentIndexChanged.connect(self.refresh);filters_secondary.addWidget(self.filter_condition)
        self.filter_set=QLineEdit();self.filter_set.setPlaceholderText('Expansión / set')
        self.filter_set.textChanged.connect(self.refresh);filters_secondary.addWidget(self.filter_set,2)
        self.filter_no_price=QComboBox();self.filter_no_price.addItem('Todos los precios',False);self.filter_no_price.addItem('Sin precio',True)
        self.filter_no_price.currentIndexChanged.connect(self.refresh);filters_secondary.addWidget(self.filter_no_price)
        self.filter_count=QLabel('');self.filter_count.setObjectName('countStatus');filters_secondary.addWidget(self.filter_count)
        cl.addLayout(filters);cl.addLayout(filters_secondary)
        self.prices_btn=QPushButton('Actualizar precios');self.prices_btn.setObjectName('primary');self.prices_btn.setMinimumHeight(40);self.prices_btn.clicked.connect(self.update_all_prices)
        controls.addWidget(self.prices_btn)
        backup_btn=QPushButton('Exportar copia');backup_btn.clicked.connect(self.export_backup)
        restore_btn=QPushButton('Restaurar copia');restore_btn.clicked.connect(self.restore_backup)
        controls.addWidget(backup_btn);controls.addWidget(restore_btn)
        about_btn=QPushButton('Acerca de');about_btn.clicked.connect(self.show_about);controls.addWidget(about_btn)
        cl.addLayout(controls)
        # Panel de valoración de la colección (se actualiza con cada cotización).
        self.collection_overview=QFrame()
        self.collection_overview.setObjectName('collectionOverview')
        overview_layout=QHBoxLayout(self.collection_overview)
        overview_layout.setContentsMargins(22,14,22,14)
        overview_text=QVBoxLayout()
        heading=QLabel('VALOR ESTIMADO DE LA COLECCIÓN')
        heading.setObjectName('metricTitle')
        overview_text.addWidget(heading)
        self.total_value_label=QLabel('—')
        self.total_value_label.setObjectName('metricValue')
        overview_text.addWidget(self.total_value_label)
        self.summary=QLabel('')
        self.price_status=QLabel('Precios: comprobando…');self.price_status.setObjectName('metricMeta')
        overview_text.addWidget(self.price_status)
        self.price_status.hide()
        self.summary.setObjectName('metricMeta')
        overview_text.addWidget(self.summary)
        self.summary.hide()
        overview_layout.addLayout(overview_text)
        overview_layout.addStretch()
        cl.addWidget(self.collection_overview)
        self.collection_scroll=QScrollArea();self.collection_scroll.setWidgetResizable(True)
        self.collection_area=QWidget();self.collection_layout=QGridLayout(self.collection_area)
        self.collection_layout.setContentsMargins(8,8,8,8);self.collection_layout.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignHCenter);self.collection_layout.setSpacing(14)
        self.collection_scroll.setWidget(self.collection_area)
        self.collection_stack=QStackedWidget();self.collection_stack.addWidget(self.collection_scroll)
        self.collection_empty=empty_state('▦','Tu colección está vacía','Añade una carta desde Buscar cartas y aparecerá aquí.')
        self.collection_stack.addWidget(self.collection_empty)
        self.collection_detail=DetailPage(lambda:self.collection_stack.setCurrentIndex(2 if self.collection_empty_active else 0))
        self.collection_stack.addWidget(self.collection_detail)
        self.collection_empty_active=False
        self.collection_stack.currentChanged.connect(self.collection_page_changed)
        self.collection_detail.history_loader=self.get_history
        self.collection_detail.query_button.setText('Consultar precio en CardTrader')
        self.collection_detail.price_menu=QMenu(self.collection_detail.query_button)
        edit_action=self.collection_detail.price_menu.addAction('Modificar precio manualmente')
        edit_action.triggered.connect(self.edit_valuation)
        identify_action=self.collection_detail.price_menu.addAction('Identificar impresión / buscar manualmente')
        identify_action.triggered.connect(self.open_api_price)
        self.collection_detail.query_button.setMenu(self.collection_detail.price_menu)
        self.collection_detail.query_button.clicked.connect(self.query_current_cardtrader)
        self.collection_detail.identify_button.clicked.connect(self.open_api_price)
        cl.addWidget(self.collection_stack)
        tabs.addTab(coll,'▦  Mi colección')

    def query_current_cardtrader(self):
        if not hasattr(self,'active_owned_row'):return
        if not load_cardtrader_token():
            self.open_api_price()
            return
        pk=self.active_owned_row[0]
        self.collection_detail.query_button.setEnabled(False)
        self.collection_detail.query_button.setText('Consultando CardTrader…')
        self.collection_detail.current_price.setText('Consultando…')
        self.queue_auto_cardtrader_price(pk,force=True)

    def add_card(self,card):
        dlg=CardDialog(self,cid=card.get('id',''))
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        lang,cond,var,qty=dlg.values()
        cid=card.get('id','')
        matches=self.db.execute('SELECT id,quantity,physical_print_key FROM cards WHERE card_id=? AND language=? AND condition=? AND variant=? ORDER BY id',(cid,lang,cond,var)).fetchall()
        previous=next((row[:2] for row in matches if not row[2]),None)
        mapped=[row for row in matches if row[2]]
        if not previous and len(mapped)==1:
            mapping=self.get_cardtrader_print_mapping(mapped[0][0],lang)
            description=(mapping['expansion_name']+' · '+mapping['collector_number']+' · '+mapping['blueprint_name']) if mapping else ('Blueprint '+str(mapped[0][2]))
            same=QMessageBox.question(self,'Impresión ya registrada',f'Ya tienes «{description}» en la colección. ¿La nueva copia es exactamente esa misma impresión?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
            if same==QMessageBox.StandardButton.Yes:previous=mapped[0][:2]
        elif not previous and len(mapped)>1:
            labels=[];row_by_label={}
            for row in mapped:
                mapping=self.get_cardtrader_print_mapping(row[0],lang)
                label=((mapping['expansion_name']+' · '+mapping['collector_number']+' · '+mapping['blueprint_name']) if mapping else ('Blueprint '+str(row[2])))+' · registro '+str(row[0])
                labels.append(label);row_by_label[label]=row
            labels.append('Otra impresión / todavía sin identificar')
            choice,ok=QInputDialog.getItem(self,'Elige la impresión','¿Esta copia coincide con una impresión ya registrada?',labels,0,False)
            if ok and choice in row_by_label:previous=row_by_label[choice][:2]
        if previous:
            if previous[1]+qty>9999:
                QMessageBox.warning(self,'Límite','La cantidad combinada supera 9999 copias.');return
            self.db.execute('UPDATE cards SET quantity=quantity+? WHERE id=?',(qty,previous[0]))
            card_row_id=previous[0]
        else:
            cursor=self.db.execute('''INSERT INTO cards(card_id,name,set_name,number,image,language,condition,variant,quantity) VALUES(?,?,?,?,?,?,?,?,?)''',(cid,card.get('name',''),card.get('set',{}).get('name','') if isinstance(card.get('set'),dict) else '',card.get('localId',''),card.get('image',''),lang,cond,var,qty))
            card_row_id=cursor.lastrowid
        self.db.commit();self.refresh()
        if not str(cid).startswith('manual-'):
            self.update_prices(ids=[cid])
            self.queue_auto_cardtrader_price(card_row_id)
        else:self.statusBar().showMessage('Carta manual añadida; no se puede resolver una impresión automáticamente sin datos de catálogo.',9000)

    def queue_auto_cardtrader_price(self,card_row_id,force=False,batch_item=False,start_now=False):
        if card_row_id in self.active_cardtrader_rows:
            if not batch_item:
                if self.cardtrader_batch_active and card_row_id in self.cardtrader_batch_ids and card_row_id not in self.cardtrader_batch_accounted:return True
                queued={item[0]:index for index,item in enumerate(self.cardtrader_individual_queue)}
                if card_row_id in queued:
                    index=queued[card_row_id]
                    self.cardtrader_individual_queue[index]=(card_row_id,force or self.cardtrader_individual_queue[index][1])
                else:self.cardtrader_individual_queue.append((card_row_id,force))
            return True
        if not batch_item and (self.active_cardtrader_rows or self.cardtrader_batch_active) and not start_now:
            queued_ids={item[0] for item in self.cardtrader_individual_queue}
            if card_row_id not in queued_ids:self.cardtrader_individual_queue.append((card_row_id,force))
            if force and hasattr(self,'active_owned_row') and self.active_owned_row[0]==card_row_id:
                self.collection_detail.query_button.setText('En cola de CardTrader…')
            return True
        row=self.db.execute('SELECT card_id,name,set_name,number,language,condition,variant,physical_print_key FROM cards WHERE id=?',(card_row_id,)).fetchone()
        if not row:return False
        cid,name,set_name,number,language,condition,variant,physical_print_key=row
        request_context=(cid,set_name or '',number or '',language,condition,variant,physical_print_key or '')
        if not load_cardtrader_token():
            self.statusBar().showMessage('Guarda y valida el token de CardTrader para obtener precios por idioma.',10000)
            if force and hasattr(self,'active_owned_row') and self.active_owned_row[0]==card_row_id:
                self.collection_detail.query_button.setEnabled(True)
                self.collection_detail.query_button.setText('Consultar precio en CardTrader')
                self.collection_detail.current_price.setText('Falta el token')
                self.collection_detail.updated.setText('Guarda el token de CardTrader para poder consultar ofertas.')
            return False
        cached=self.db.execute('SELECT fetched_at,source_url,product_id,condition,variant FROM api_valuations WHERE card_row_id=?',(card_row_id,)).fetchone()
        token=load_cardtrader_token()
        mapping=self.get_cardtrader_print_mapping(card_row_id,language)
        if mapping and not mapping.get('confirmed'):mapping=None
        cache_matches_print=bool(mapping and cached and str(cached[2])==str(mapping['blueprint_id']) and cached[3]==condition and cached[4]==variant)
        if not force and cached and cache_matches_print and str(cached[1]).startswith('https://api.cardtrader.com/api/v2/marketplace/products?') and int(time.time())-int(cached[0])<24*3600:
            self.statusBar().showMessage('Carta añadida. Ya hay una cotización reciente de CardTrader para este idioma.',7000)
            return
        if not self.cardtrader_batch_active:
            self.statusBar().showMessage('Consultando CardTrader usando la impresión confirmada…' if mapping else 'Carta añadida. Buscando impresión y precio en CardTrader…',10000)
        expansion_cache=[dict(zip(('catalog_language','source_set_id','catalog_set_id','expansion_id','expansion_name','expansion_code','origin'),item))
            for item in self.db.execute('SELECT catalog_language,source_set_id,catalog_set_id,expansion_id,expansion_name,expansion_code,origin FROM cardtrader_expansion_mappings').fetchall()]
        worker=CardTraderAutoPriceWorker(token,cid,name,set_name or '',number or '',language,condition,variant,mapping,expansion_cache,dict(self.cardtrader_catalog_cache))
        self.market_auto_workers.append(worker)
        self.active_cardtrader_rows.add(card_row_id)
        self.active_cardtrader_context[card_row_id]=request_context
        worker.done.connect(lambda result,error,row_id=card_row_id,card_id=cid,card_name=name,card_language=language,context=request_context:self.cardtrader_auto_price_received(row_id,card_id,card_name,card_language,result,error,context))
        worker.finished.connect(lambda w=worker,row_id=card_row_id:self.cardtrader_worker_finished(w,row_id))
        worker.start()
        return True

    def cardtrader_worker_finished(self,worker,row_id):
        if worker in self.market_auto_workers:self.market_auto_workers.remove(worker)
        self.active_cardtrader_rows.discard(row_id)
        self.active_cardtrader_context.pop(row_id,None)
        if self.cardtrader_batch_active:
            if row_id in self.cardtrader_batch_ids and row_id not in self.cardtrader_batch_accounted:
                self.cardtrader_batch_queue.insert(0,row_id)
            QTimer.singleShot(500,self.start_next_cardtrader_batch_item)
        else:QTimer.singleShot(250,self.start_next_individual_cardtrader)

    def start_next_individual_cardtrader(self):
        if getattr(self,'_closing',False) or self.cardtrader_batch_active or self.active_cardtrader_rows or not self.cardtrader_individual_queue:return
        while self.cardtrader_individual_queue:
            row_id,force=self.cardtrader_individual_queue.pop(0)
            if self.db.execute('SELECT 1 FROM cards WHERE id=?',(row_id,)).fetchone():
                self.queue_auto_cardtrader_price(row_id,force=force,start_now=True)
                return

    def update_all_prices(self):
        # Keep the existing TCGdex/general refresh and add one official
        # CardTrader lookup per owned physical row.
        if self.cardtrader_batch_active:
            self.statusBar().showMessage('La actualización de CardTrader ya está en curso.',5000);return
        self.update_prices(force=True)
        if not load_cardtrader_token():
            self.statusBar().showMessage('Precios generales en actualización; valida primero el token para consultar CardTrader.',10000);return
        ids=[int(row[0]) for row in self.db.execute("SELECT id FROM cards WHERE card_id NOT LIKE 'manual-%' ORDER BY id").fetchall()]
        if not ids:
            self.statusBar().showMessage('No hay cartas de catálogo en la colección para consultar en CardTrader.',7000);return
        self.start_cardtrader_batch(ids)

    def start_next_cardtrader_batch_item(self):
        if not self.cardtrader_batch_active:return
        if not self.cardtrader_batch_queue:
            self.cardtrader_batch_active=False
            counts=self.cardtrader_batch_counts
            prefix='Revisión automática CardTrader' if getattr(self,'cardtrader_batch_automatic',False) else 'CardTrader'
            summary=(f"{prefix}: {counts['quoted']} con precio · {counts['no_offers']} sin ofertas · "
                     f"{counts['catalog_missing']} sin impresión · {counts['expansion_unmatched']} sin expansión · "
                     f"{counts['blueprint_unmatched']} sin impresión exacta · {counts['language_mismatch']} idioma/expansión incompatibles · {counts['api_error']} errores "
                     f"({self.cardtrader_batch_total} cartas).")
            self.prices_btn.setEnabled(True);self.prices_btn.setText('Actualizar precios')
            self.cardtrader_batch_automatic=False
            if hasattr(self,'sort_by') and self.sort_by.currentData()=='value':self.refresh()
            self.statusBar().showMessage(summary,20000)
            QTimer.singleShot(250,self.start_next_individual_cardtrader)
            return
        row_id=self.cardtrader_batch_queue.pop(0)
        row=self.db.execute('SELECT name,language FROM cards WHERE id=?',(row_id,)).fetchone()
        if not row:
            self.cardtrader_batch_done+=1;QTimer.singleShot(0,self.start_next_cardtrader_batch_item);return
        if row_id in self.active_cardtrader_rows:
            # Let the already-running individual query satisfy this batch item.
            return
        self.prices_btn.setText(f'CardTrader {self.cardtrader_batch_done+1}/{self.cardtrader_batch_total}…')
        if not self.queue_auto_cardtrader_price(row_id,force=True,batch_item=True):
            self.cardtrader_batch_counts['api_error']+=1;self.cardtrader_batch_done+=1
            QTimer.singleShot(0,self.start_next_cardtrader_batch_item)

    def record_cardtrader_attempt(self,row_id,cid,language,result,error):
        if error:
            if result and result.get('no_offers'):outcome='no_offers'
            else:
                stage=(result or {}).get('lookup_stage','').casefold()
                msg=str(error).casefold()
                if 'búsqueda de impresión en el catálogo' in stage and ('no se encontró' in msg or 'no hay datos' in msg):outcome='catalog_missing'
                elif 'búsqueda de expansión cardtrader' in stage and 'única expansión equivalente' in msg:outcome='expansion_unmatched'
                elif 'búsqueda de blueprint' in stage and 'único blueprint compatible' in msg:outcome='blueprint_unmatched'
                elif 'validación de idioma e impresión' in stage:outcome='language_mismatch'
                else:outcome='api_error'
        else:outcome='quoted' if result and result.get('amount') is not None else 'error'
        stage=(result or {}).get('lookup_stage') or ('guardado' if outcome=='quoted' else 'desconocido')
        message=str(error or '')[:1500]
        with self.db:
            self.db.execute('INSERT INTO cardtrader_lookup_attempts(card_row_id,card_id,language,attempted_at,stage,outcome,message) VALUES(?,?,?,?,?,?,?)',
                (row_id,str(cid),str(language or ''),int(time.time()),stage,outcome,message))
        if self.cardtrader_batch_active and row_id in self.cardtrader_batch_ids and row_id not in self.cardtrader_batch_accounted:
            self.cardtrader_batch_accounted.add(row_id)
            self.cardtrader_batch_counts[outcome if outcome in self.cardtrader_batch_counts else 'api_error']+=1
            self.cardtrader_batch_done+=1
            self.prices_btn.setText(f'CardTrader {self.cardtrader_batch_done}/{self.cardtrader_batch_total}…')

    def update_owned_row_price(self,row_id):
        for tile in self.owned_tiles:
            if tile.row_id==row_id:
                tile.set_price(self.get_display_price(tile.card_id,tile.language,tile.variant,row_id),tile.quantity)

    def cardtrader_auto_price_received(self,row_id,cid,name,language,result,error,request_context=None):
        for key,value in (result or {}).get('catalog_updates',{}).items():
            self.cardtrader_catalog_cache[key]=value
        while len(self.cardtrader_catalog_cache)>4:
            self.cardtrader_catalog_cache.pop(next(iter(self.cardtrader_catalog_cache)))
        current=self.db.execute('SELECT card_id,set_name,number,language,condition,variant,physical_print_key FROM cards WHERE id=?',(row_id,)).fetchone()
        if not current:return
        current_context=(current[0],current[1] or '',current[2] or '',current[3],current[4],current[5],current[6] or '')
        if request_context is not None and current_context!=request_context:
            # Discard results for the old language/condition/finish/print. The
            # queued refresh starts after this worker has fully finished.
            self.queue_auto_cardtrader_price(row_id,force=True)
            return
        self.record_cardtrader_attempt(row_id,cid,language,result,error)
        if error:
            if result and result.get('mapping_confirmed') and result.get('no_offers'):
                # Preserve the last quote; the UI marks it as historical when
                # this newer lookup found no currently compatible offers.
                existing_mapping=self.get_cardtrader_print_mapping(row_id,language)
                if not (existing_mapping and existing_mapping.get('confirmed')):
                    try:self.save_cardtrader_print_mapping(row_id,result,language,True)
                    except ValueError as exc:error+=' No se guardó la impresión: '+str(exc)
                self.save_cardtrader_expansion_mapping((result or {}).get('expansion_mapping'))
                self.db.commit();self.update_owned_row_price(row_id);self.update_summary()
                if hasattr(self,'sort_by') and self.sort_by.currentData()=='value':self.refresh()
                if not self.cardtrader_batch_active:self.statusBar().showMessage(error,15000)
                if hasattr(self,'active_owned_row') and self.active_owned_row[0]==row_id:
                    current=self.db.execute('SELECT id,card_id,name,language,condition,variant,quantity,image FROM cards WHERE id=?',(row_id,)).fetchone()
                    if current:self.detail_owned(current)
                return
            if not self.cardtrader_batch_active:self.statusBar().showMessage('Carta añadida; precio automático no disponible: '+error,15000)
            if hasattr(self,'active_owned_row') and self.active_owned_row[0]==row_id:
                current=self.db.execute('SELECT id,card_id,name,language,condition,variant,quantity,image FROM cards WHERE id=?',(row_id,)).fetchone()
                if current:self.detail_owned(current)
            return
        if not result:return
        existing_mapping=self.get_cardtrader_print_mapping(row_id,language)
        if not (existing_mapping and existing_mapping.get('confirmed')):
            try:self.save_cardtrader_print_mapping(row_id,result,language,bool(result.get('mapping_confirmed')))
            except ValueError as exc:
                if not self.cardtrader_batch_active:self.statusBar().showMessage('Se encontró una impresión, pero no se aplicó para evitar duplicar registros: '+str(exc),15000)
                return
        self.save_cardtrader_expansion_mapping(result.get('expansion_mapping'))
        current=self.db.execute('SELECT condition,variant FROM cards WHERE id=?',(row_id,)).fetchone()
        if not current:return
        self.db.execute("""INSERT INTO api_valuations(card_row_id,product_id,amount,floor,offers,language,source_url,fetched_at,condition,variant) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(card_row_id) DO UPDATE SET product_id=excluded.product_id,amount=excluded.amount,floor=excluded.floor,offers=excluded.offers,language=excluded.language,source_url=excluded.source_url,fetched_at=excluded.fetched_at,condition=excluded.condition,variant=excluded.variant""",
            (row_id,result['blueprint_id'],result['amount'],result['floor'],result['offers'],result['language'],result['source_url'],int(time.time()),current[0],current[1]))
        self.db.execute('INSERT OR IGNORE INTO cardtrader_price_history(card_row_id,fetched_at,price,product_id,condition,variant) VALUES(?,?,?,?,?,?)',(row_id,int(time.time()),float(result['amount']),str(result['blueprint_id']),current[0],current[1]))
        self.db.commit()
        if self.cardtrader_batch_active:
            self.update_owned_row_price(row_id);self.update_summary()
        else:
            self.refresh()
            self.statusBar().showMessage('Precio CardTrader guardado automáticamente: '+name+' · '+language+' · '+euros(result['amount'])+' (media de hasta 5 ofertas).',12000)
        if hasattr(self,'active_owned_row') and self.active_owned_row[0]==row_id:
            current=self.db.execute('SELECT id,card_id,name,language,condition,variant,quantity,image FROM cards WHERE id=?',(row_id,)).fetchone()
            if current:self.detail_owned(current)

    def get_cardtrader_print_mapping(self,card_row_id,language=None):
        row=self.db.execute('SELECT expansion_id,expansion_name,expansion_code,blueprint_id,blueprint_name,collector_number,language,confirmed,updated_at FROM cardtrader_print_mappings WHERE card_row_id=?',(card_row_id,)).fetchone()
        if not row:return None
        keys=('expansion_id','expansion_name','expansion_code','blueprint_id','blueprint_name','collector_number','language','confirmed','updated_at')
        mapping=dict(zip(keys,row))
        if language is not None:
            expected=cardtrader_language(language)
            actual=normalize_market_language(mapping['language'])
            ambiguous_chinese=normalized_name(language) in ('chino','chino sin especificar') and actual in ('chinese-s','chinese-t')
            if (expected and actual!=normalize_market_language(expected)) or (not expected and not ambiguous_chinese):return None
        return mapping

    def last_cardtrader_quote(self,card_row_id,mapping,condition,variant):
        """Return the last known quote for this confirmed print, including legacy rows."""
        row=self.db.execute('''SELECT fetched_at,price FROM cardtrader_price_history
            WHERE card_row_id=? AND product_id=? AND (condition=? OR condition='') AND (variant=? OR variant='')
            ORDER BY fetched_at DESC,id DESC LIMIT 1''',
            (card_row_id,str(mapping.get('blueprint_id') or ''),condition,variant)).fetchone()
        return row

    def save_cardtrader_print_mapping(self,card_row_id,selection,language,confirmed):
        blueprint_id=str(selection.get('blueprint_id',''))
        if confirmed:
            card=self.db.execute('SELECT card_id,language,condition,variant FROM cards WHERE id=?',(card_row_id,)).fetchone()
            duplicate=self.db.execute('SELECT id FROM cards WHERE card_id=? AND language=? AND condition=? AND variant=? AND physical_print_key=? AND id<>?',(*card,blueprint_id,card_row_id)).fetchone() if card else None
            if duplicate:raise ValueError('Ya existe otra fila de esta carta con esa misma impresión (registro '+str(duplicate[0])+'). No se mezclaron las copias.')
        with self.db:
            self.db.execute('''INSERT INTO cardtrader_print_mappings(card_row_id,expansion_id,expansion_name,expansion_code,blueprint_id,blueprint_name,collector_number,language,confirmed,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(card_row_id) DO UPDATE SET expansion_id=excluded.expansion_id,expansion_name=excluded.expansion_name,
                expansion_code=excluded.expansion_code,blueprint_id=excluded.blueprint_id,blueprint_name=excluded.blueprint_name,collector_number=excluded.collector_number,
                language=excluded.language,confirmed=excluded.confirmed,updated_at=excluded.updated_at''',
                (card_row_id,str(selection.get('expansion_id','')),str(selection.get('expansion','')),str(selection.get('expansion_code','')),
                 blueprint_id,str(selection.get('card_name','')),str(selection.get('collector_number','')),
                 str(language),1 if confirmed else 0,int(time.time())))
            if confirmed:self.db.execute('UPDATE cards SET physical_print_key=? WHERE id=?',(blueprint_id,card_row_id))

    def save_cardtrader_expansion_mapping(self,mapping,origin='auto'):
        if not isinstance(mapping,dict) or not mapping.get('catalog_language') or not mapping.get('source_set_id') or not mapping.get('expansion_id'):return
        with self.db:
            self.db.execute('''INSERT INTO cardtrader_expansion_mappings
                (catalog_language,source_set_id,catalog_set_id,expansion_id,expansion_name,expansion_code,updated_at,origin)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(catalog_language,source_set_id) DO UPDATE SET
                catalog_set_id=CASE WHEN excluded.catalog_set_id<>'' THEN excluded.catalog_set_id ELSE cardtrader_expansion_mappings.catalog_set_id END,
                expansion_id=excluded.expansion_id,expansion_name=excluded.expansion_name,
                expansion_code=excluded.expansion_code,updated_at=excluded.updated_at,origin=excluded.origin''',
                (str(mapping['catalog_language']),str(mapping['source_set_id']),str(mapping.get('catalog_set_id') or ''),
                 str(mapping['expansion_id']),str(mapping.get('expansion_name') or ''),str(mapping.get('expansion_code') or ''),int(time.time()),str(origin)))

    def save_manual_expansion_mapping(self,card_row_id,selection,language):
        card=self.db.execute('SELECT card_id FROM cards WHERE id=?',(card_row_id,)).fetchone()
        if not card:return
        source_set_id=str(card[0]).rsplit('-',1)[0] if '-' in str(card[0]) else str(card[0])
        market_language=normalize_market_language(language)
        catalog_language={'spanish':'en','english':'en','japanese':'ja','chinese-s':'zh-cn','chinese-t':'zh-tw'}.get(market_language,'')
        if not catalog_language:return
        self.save_cardtrader_expansion_mapping({'catalog_language':catalog_language,'source_set_id':source_set_id,'catalog_set_id':'',
            'expansion_id':str(selection.get('expansion_id','')),'expansion_name':str(selection.get('expansion','')),
            'expansion_code':str(selection.get('expansion_code',''))},origin='manual')

    def refresh(self):
        self.collection_generation+=1;generation=self.collection_generation
        while self.collection_layout.count():
            item=self.collection_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        allowed={'name','language','set_name','condition','quantity','id','value'}
        order=self.sort_by.currentData() if hasattr(self,'sort_by') else 'name'
        order=order if order in allowed else 'name'
        direction=self.sort_direction.currentData() if hasattr(self,'sort_direction') else 'ASC'
        direction='DESC' if direction=='DESC' else 'ASC'
        sort_expr="COALESCE(NULLIF(set_name,''), substr(card_id,1,instr(card_id,'-')-1))" if order=='set_name' else ('name' if order=='value' else order)
        collate='' if order in ('quantity','id') else ' COLLATE NOCASE'
        self.rows=self.db.execute(f'SELECT id,card_id,name,language,condition,variant,quantity,image FROM cards ORDER BY {sort_expr}{collate} {direction}, name COLLATE NOCASE ASC, id ASC').fetchall()
        visible=list(self.rows)
        if order=='value':
            def row_value(r):
                value=self.get_collection_sort_price(r)
                return (value or 0)*r[6]
            visible.sort(key=row_value,reverse=direction=='DESC')
        needle=self.collection_search.text().strip().casefold() if hasattr(self,'collection_search') else ''
        language=self.filter_language.currentData() if hasattr(self,'filter_language') else ''
        finish=self.filter_finish.currentData() if hasattr(self,'filter_finish') else ''
        condition=self.filter_condition.currentData() if hasattr(self,'filter_condition') else ''
        set_query=self.filter_set.text().strip().casefold() if hasattr(self,'filter_set') else ''
        no_price=self.filter_no_price.currentData() if hasattr(self,'filter_no_price') else False
        if needle:visible=[r for r in visible if needle in (r[2] or '').casefold() or needle in (r[1] or '').casefold()]
        if language:visible=[r for r in visible if (r[3] or '')==language]
        if finish:visible=[r for r in visible if (r[5] or 'Sin verificar').casefold()==finish.casefold()]
        if condition:visible=[r for r in visible if r[4]==condition]
        if set_query:
            set_ids={r[0] for r in self.db.execute('SELECT id FROM cards WHERE LOWER(set_name) LIKE ? OR LOWER(card_id) LIKE ?',('%'+set_query+'%','%'+set_query+'%'))}
            visible=[r for r in visible if r[0] in set_ids]
        if no_price:
            def has_display_price(r):
                price=self.get_display_price(r[1],r[3],r[5],r[0])
                return bool(price and (price.get('trend') is not None or price.get('avg') is not None))
            visible=[r for r in visible if not has_display_price(r)]
        self.owned_tiles=[];targets={};entries=[]
        for row in visible:
            tile=OwnedTile(row,self.edit,self.delete,self.detail_owned,self.change_quantity,self.get_display_price(row[1],row[3],row[5],row[0]));self.owned_tiles.append(tile)
            targets.setdefault(row[1],[]).append(tile);entries.append((row[1],row[7]))
        self.reflow(self.collection_layout,self.owned_tiles,250,self.collection_scroll)
        if entries:self.images(entries,targets,generation,True)
        self.update_summary()
        if hasattr(self,'filter_count'):self.filter_count.setText(f'Mostrando {len(visible)} de {len(self.rows)} registros')
        self.collection_empty_active=not bool(visible)
        if not visible:
            title=self.collection_empty.findChild(QLabel,'emptyTitle');message=self.collection_empty.findChild(QLabel,'emptyMessage')
            if self.rows:
                title.setText('No hay coincidencias');message.setText('Cambia o limpia los filtros para volver a ver tus cartas.')
            else:
                title.setText('Tu colección está vacía');message.setText('Añade una carta desde Buscar cartas y aparecerá aquí.')
        if self.collection_stack.currentIndex()!=1:
            self.collection_stack.setCurrentIndex(2 if self.collection_empty_active else 0)

    def collection_page_changed(self,index):
        self.collection_overview.setVisible(index!=1)

    def seed_cached_price_history(self):
        """Import existing cached quotes as the first real observation, never fabricated history."""
        for cid,trend,avg,updated,fetched_at,status in self.db.execute(
            "SELECT card_id,trend,avg,updated,fetched_at,status FROM card_prices WHERE status='ok'").fetchall():
            quote=trend if trend is not None else avg
            if quote is None:continue
            exists=self.db.execute('SELECT 1 FROM price_history WHERE card_id=? LIMIT 1',(cid,)).fetchone()
            if not exists:
                self.db.execute('INSERT OR IGNORE INTO price_history(card_id,fetched_at,price,source_updated) VALUES(?,?,?,?)',
                                (cid,int(fetched_at),float(quote),updated or ''))
        self.db.commit()

    def get_display_price(self,cid,language=None,variant=None,card_row_id=None):
        if card_row_id is not None:
            card=self.db.execute('SELECT card_id,language,variant,condition FROM cards WHERE id=?',(card_row_id,)).fetchone()
            if not card:return self.get_price(cid)
            cid,language,variant,condition=card
            manual=self.db.execute('SELECT amount,source_url,updated_at FROM verified_valuations WHERE card_row_id=?',(card_row_id,)).fetchone()
            if manual:return {'status':'verified','trend':manual[0],'avg':manual[0],'updated':str(manual[2]),'source':manual[1]}
            mapping=self.get_cardtrader_print_mapping(card_row_id,language)
            api=self.db.execute('SELECT product_id,amount,source_url,fetched_at,language,condition,variant,floor FROM api_valuations WHERE card_row_id=?',(card_row_id,)).fetchone()
            expected=market_language(language)
            language_ok=api and ((expected and normalize_market_language(api[4])==expected) or (not expected and normalized_name(language) in ('chino','chino sin especificar') and normalize_market_language(api[4]) in ('chinese-s','chinese-t')))
            mismatch=cardtrader_language_mismatch(language,mapping)
            if not mismatch and mapping and mapping.get('confirmed') and api and str(mapping['blueprint_id'])==str(api[0]) and str(api[2]).startswith('https://api.cardtrader.com/api/v2/marketplace/products?') and language_ok and api[5]==condition and api[6]==variant:
                amount=cardtrader_display_amount(api[1],api[7])
                latest=self.db.execute('SELECT outcome,attempted_at FROM cardtrader_lookup_attempts WHERE card_row_id=? ORDER BY attempted_at DESC,id DESC LIMIT 1',(card_row_id,)).fetchone()
                stale=bool(latest and latest[0]=='no_offers' and int(latest[1] or 0)>int(api[3] or 0))
                return {'status':'market_api_stale' if stale else 'market_api','trend':amount,'avg':amount,'updated':str(api[3]),'source':api[4]}
            if not mismatch and mapping and mapping.get('confirmed'):
                history=self.last_cardtrader_quote(card_row_id,mapping,condition,variant)
                if history:return {'status':'market_api_stale','trend':history[1],'avg':history[1],'updated':str(history[0]),'source':'historial CardTrader'}
            general=self.get_price(cid)
            if general and general.get('status')=='ok':
                reason,detail=self.cardtrader_fallback_reason(card_row_id,language,mismatch)
                general=dict(general,status='general',cardtrader_reason=reason,cardtrader_detail=detail)
            return general
        if language is not None:
            row=self.db.execute("SELECT v.amount,v.source_url,v.updated_at FROM verified_valuations v JOIN cards c ON c.id=v.card_row_id WHERE c.card_id=? AND c.language=? AND c.variant=? ORDER BY v.updated_at DESC LIMIT 1",(cid,language,variant or '')).fetchone()
            if row:return {'status':'verified','trend':row[0],'avg':row[0],'updated':str(row[2]),'source':row[1]}
        if language is not None:
            api=self.db.execute("SELECT a.amount,a.source_url,a.fetched_at,a.language,a.floor FROM api_valuations a JOIN cards c ON c.id=a.card_row_id JOIN cardtrader_print_mappings m ON m.card_row_id=c.id WHERE c.card_id=? AND c.language=? AND c.variant=? AND a.condition=c.condition AND a.variant=c.variant AND m.confirmed=1 AND m.blueprint_id=a.product_id ORDER BY a.fetched_at DESC LIMIT 1",(cid,language,variant or '')).fetchone()
            expected=market_language(language)
            from_cardtrader=api and str(api[1]).startswith('https://api.cardtrader.com/api/v2/marketplace/products?')
            compatible=(from_cardtrader and ((expected and normalize_market_language(api[3])==expected) or (not expected and normalized_name(language) in ('chino','chino sin especificar') and normalize_market_language(api[3]) in ('chinese-s','chinese-t'))))
            if compatible:
                amount=cardtrader_display_amount(api[0],api[4])
                return {'status':'market_api','trend':amount,'avg':amount,'updated':str(api[2]),'source':api[3]}
        general=self.get_price(cid)
        return dict(general,status='general') if general and general.get('status')=='ok' else general

    def cardtrader_fallback_reason(self,row_id,language,mismatch=''):
        if mismatch:return 'Idioma e impresión no coinciden',mismatch
        attempt=self.db.execute('SELECT outcome,message FROM cardtrader_lookup_attempts WHERE card_row_id=? ORDER BY attempted_at DESC,id DESC LIMIT 1',(row_id,)).fetchone()
        if not attempt:return 'Aún no consultado','Todavía no se ha intentado consultar esta carta en CardTrader.'
        labels={'no_offers':'Sin ofertas compatibles','catalog_missing':'Impresión no encontrada en el catálogo',
                'expansion_unmatched':'Expansión no asociada','blueprint_unmatched':'Impresión exacta sin identificar',
                'language_mismatch':'Idioma e impresión no coinciden','api_error':'Error al consultar CardTrader',
                'error':'No se pudo completar la consulta'}
        return labels.get(attempt[0],'Sin cotización de CardTrader'),str(attempt[1] or 'Revisa la impresión seleccionada.')

    def refresh_stale_cardtrader_quotes(self):
        """Refresh only rows without a recent confirmed CardTrader quote/attempt."""
        if not load_cardtrader_token() or self.cardtrader_batch_active:return
        now=int(time.time());day=24*3600;ids=[]
        rows=self.db.execute("SELECT id,language,condition,variant FROM cards WHERE card_id NOT LIKE 'manual-%' ORDER BY id").fetchall()
        for row_id,language,condition,variant in rows:
            quote=self.db.execute('SELECT fetched_at,source_url,product_id,condition,variant FROM api_valuations WHERE card_row_id=?',(row_id,)).fetchone()
            mapping=self.get_cardtrader_print_mapping(row_id,language)
            quote_valid=bool(mapping and mapping.get('confirmed') and quote and
                str(quote[1]).startswith('https://api.cardtrader.com/api/v2/marketplace/products?') and
                str(mapping['blueprint_id'])==str(quote[2]) and quote[3]==condition and quote[4]==variant)
            if quote_valid and now-int(quote[0] or 0)<day:continue
            attempt=self.db.execute('SELECT attempted_at FROM cardtrader_lookup_attempts WHERE card_row_id=? ORDER BY attempted_at DESC,id DESC LIMIT 1',(row_id,)).fetchone()
            if attempt and now-int(attempt[0] or 0)<day:continue
            ids.append(int(row_id))
        if ids:self.start_cardtrader_batch(ids,automatic=True)

    def start_cardtrader_batch(self,ids,automatic=False):
        if self.cardtrader_batch_active:return
        ids=[int(row_id) for row_id in ids]
        if not ids:return
        ids_set=set(ids)
        self.cardtrader_individual_queue=[item for item in self.cardtrader_individual_queue if item[0] not in ids_set]
        self.cardtrader_batch_queue=ids
        self.cardtrader_batch_ids=ids_set;self.cardtrader_batch_accounted=set()
        self.cardtrader_batch_total=len(ids);self.cardtrader_batch_done=0
        self.cardtrader_batch_counts={'quoted':0,'no_offers':0,'catalog_missing':0,'expansion_unmatched':0,'blueprint_unmatched':0,'language_mismatch':0,'api_error':0}
        self.cardtrader_batch_automatic=automatic;self.cardtrader_batch_active=True
        self.prices_btn.setEnabled(False)
        self.start_next_cardtrader_batch_item()

    def open_api_price(self):
        if not hasattr(self,'active_owned_row'):return
        pk,cid,name,lang,cond,var,qty,img=self.active_owned_row
        set_name,card_number=self.db.execute('SELECT COALESCE(set_name,\'\'),COALESCE(number,\'\') FROM cards WHERE id=?',(pk,)).fetchone()
        expected=cardtrader_language(lang)
        saved_mapping=self.get_cardtrader_print_mapping(pk,lang)
        mapping_mismatch=cardtrader_language_mismatch(lang,saved_mapping)
        hinted_expansion,hinted_number=cardtrader_lookup_hint(cid,name,set_name,card_number,lang)
        lookup_expansion=(saved_mapping.get('expansion_code') or saved_mapping.get('expansion_name')) if saved_mapping and not mapping_mismatch else hinted_expansion
        lookup_number=saved_mapping.get('collector_number') if saved_mapping and not mapping_mismatch else hinted_number
        dlg=CardTraderDialog(self);dlg.setWindowTitle('Precio por idioma — CardTrader · '+name);dlg.setMinimumWidth(680)
        form=QFormLayout(dlg)
        help_message='La consulta principal busca automáticamente la impresión equivalente usando el código de la carta y su idioma. Este formulario permite revisar o identificar manualmente una impresión cuando el catálogo no encuentra una coincidencia única. El token se guarda fuera del proyecto en ~/.pokevault.'
        if mapping_mismatch:help_message='Aviso: '+mapping_mismatch+' El formulario no precarga esa expansión; busca la impresión correcta para el idioma real de la copia.'
        helptext=QLabel(help_message);helptext.setWordWrap(True);form.addRow(helptext)
        key=QLineEdit(getattr(self,'cardtrader_api_token','') or load_cardtrader_token());key.setEchoMode(QLineEdit.EchoMode.Password);key.setPlaceholderText('Pega aquí el Bearer Auth Token JWT');form.addRow('Token CardTrader:',key)
        token_buttons=QHBoxLayout();check=QPushButton('Validar y guardar token');forget=QPushButton('Borrar token guardado');forget.setEnabled(CARDTRADER_TOKEN_FILE.exists());token_buttons.addWidget(check);token_buttons.addWidget(forget);form.addRow(token_buttons)
        expansion_query=QLineEdit(lookup_expansion or '');expansion_query.setPlaceholderText('Nombre o código de la expansión CardTrader');form.addRow('Expansión física:',expansion_query)
        auto_btn=QPushButton('Buscar expansión por nombre o código');form.addRow(auto_btn)
        expansion_btn=QPushButton('Cargar expansiones');form.addRow(expansion_btn)
        expansions=QComboBox();expansions.setMinimumContentsLength(35);expansions.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);form.addRow('Expansión:',expansions)
        blueprints_btn=QPushButton('Cargar cartas de la expansión');form.addRow(blueprints_btn)
        card_query=QLineEdit(name);form.addRow('Nombre de la carta:',card_query)
        physical_number=QLineEdit(str(lookup_number or ''));physical_number.setPlaceholderText('Número de colección de esta impresión física');form.addRow('Número físico:',physical_number)
        blueprints=QComboBox();blueprints.setMinimumContentsLength(50);blueprints.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);form.addRow('Blueprint / impresión:',blueprints)
        langs=QComboBox();langs.addItem('Selecciona idioma de las ofertas','')
        for label,code in (('Español','es'),('Inglés','en'),('Japonés','jp'),('Chino simplificado','zh-CN'),('Chino tradicional','zh-TW')):langs.addItem(label,code)
        if expected:
            code=cardtrader_language(lang);index=langs.findData(code)
            if index>=0:langs.setCurrentIndex(index)
        form.addRow('Idioma de la carta:',langs)
        number_note=('La expansión y el número se guardarán como impresión física confirmada al guardar la selección. ID del catálogo: '+str(cid)+'.')
        status=QLabel(number_note);status.setWordWrap(True);form.addRow(status)
        buttons=QHBoxLayout();offers_btn=QPushButton('Consultar ofertas por idioma');save_print_btn=QPushButton('Guardar impresión exacta');save_print_btn.setEnabled(False);buttons.addWidget(offers_btn);buttons.addWidget(save_print_btn);form.addRow(buttons)
        result=QLabel('La consulta filtra por idioma y acabado cuando CardTrader lo permite; además, solo cuentan ofertas con estado de conservación compatible. Se promedia un máximo de cinco ofertas en EUR. CardTrader devuelve como máximo las 25 más baratas, así que podrían quedar fuera ofertas compatibles más caras.');result.setWordWrap(True);form.addRow(result)
        save=QPushButton('Guardar esta cotización');save.setEnabled(False);form.addRow(save)
        def invalidate_quote(*_):
            if hasattr(dlg,'market_quote'):del dlg.market_quote
            save.setEnabled(False)
        physical_number.textEdited.connect(invalidate_quote)
        def set_api_busy(busy):
            dlg._api_busy=busy
            enabled=not busy and not dlg._close_requested
            for widget in (key,check,forget,expansion_query,auto_btn,expansion_btn,expansions,blueprints_btn,card_query,physical_number,blueprints,langs,offers_btn):
                widget.setEnabled(enabled)
            save_print_btn.setEnabled(enabled and bool(expansions.currentData() and blueprints.currentData()))
            save.setEnabled(enabled and hasattr(dlg,'market_quote'))
            if enabled:forget.setEnabled(CARDTRADER_TOKEN_FILE.exists())
        def entered_token():
            value=key.text().strip()
            return value.split(None,1)[1].strip() if value.casefold().startswith('bearer ') else value
        blueprints.currentIndexChanged.connect(invalidate_quote);langs.currentIndexChanged.connect(invalidate_quote);expansions.currentIndexChanged.connect(invalidate_quote)
        def run_request(action):
            if getattr(dlg,'_api_busy',False):return
            token=entered_token()
            if not token:QMessageBox.warning(dlg,'Falta token','Pega tu Bearer Auth Token de CardTrader.');return
            self.cardtrader_api_token=token
            if action in ('expansions','auto') and len(expansion_query.text().strip())<2:
                QMessageBox.warning(dlg,'Busca una expansión','Escribe parte del nombre o el código de la expansión.');return
            if action=='blueprints' and not expansions.currentData():
                QMessageBox.warning(dlg,'Selecciona expansión','Carga y selecciona una expansión primero.');return
            selected_language=langs.currentData()
            if action=='offers':
                if not expected and normalized_name(lang) not in ('chino','chino sin especificar'):
                    QMessageBox.warning(dlg,'Idioma no compatible','La carta no tiene un idioma reconocido.');return
                if not selected_language or (expected and normalize_market_language(selected_language)!=normalize_market_language(expected)):
                    QMessageBox.warning(dlg,'Idioma no coincide','Selecciona el mismo idioma que figura en la carta. Para «Chino (sin especificar)», confirma si el ejemplar es simplificado o tradicional.');return
                if not blueprints.currentData():QMessageBox.warning(dlg,'Selecciona impresión','Carga y selecciona el blueprint de la impresión exacta.');return
            invalidate_quote();status.setText('Consultando CardTrader…')
            set_api_busy(True)
            worker_action='expansions' if action=='auto' else action
            worker=CardTraderApiWorker(token,worker_action,expansion_query.text().strip(),expansions.currentData() or '',blueprints.currentData() or '',selected_language or '',var)
            dlg.track_worker(worker)
            def received(data,error):
                set_api_busy(False)
                if dlg._close_requested:return
                if error:status.setText('No se pudo consultar: '+error);return
                if action=='info':
                    try:
                        save_cardtrader_token(token);forget.setEnabled(True)
                        status.setText('Token validado y guardado en este equipo'+(' · App '+str(data.get('name')) if data.get('name') else '')+'.')
                    except OSError as exc:
                        status.setText('Token validado, pero no se pudo guardar localmente: '+str(exc))
                    return
                if action in ('expansions','auto'):
                    dlg.expansion_catalog={str(x.get('id','')):x for x in data}
                    term=normalized_name(expansion_query.text())
                    candidates=[x for x in data if term in normalized_name(x.get('name','')) or term in normalized_name(x.get('code',''))]
                    if action=='auto' and candidates:
                        locale=normalized_name(lang)
                        if locale in ('espanol','ingles'):
                            preferred=[x for x in candidates if normalized_name(x.get('name',''))=='30th celebration' or normalized_name(x.get('code',''))=='30c']
                            if preferred:candidates=preferred
                        elif locale=='chino simplificado':
                            preferred=[x for x in candidates if 'simplified chinese' in normalized_name(x.get('name','')) or normalized_name(x.get('code',''))=='30th-ch']
                            if preferred:candidates=preferred
                        elif locale=='japones':
                            preferred=[x for x in candidates if ' jp ' in (' '+normalized_name(x.get('name',''))+' ') or normalized_name(x.get('code',''))=='m6a']
                            if preferred:candidates=preferred
                    expansions.blockSignals(True);expansions.clear()
                    for item in candidates[:300]:expansions.addItem('{} · {}'.format(item.get('name',''),item.get('code','')),str(item.get('id','')))
                    if saved_mapping:
                        saved_index=expansions.findData(str(saved_mapping['expansion_id']))
                        if saved_index>=0:expansions.setCurrentIndex(saved_index)
                    expansions.blockSignals(False)
                    status.setText(str(len(candidates))+' expansiones coincidentes. Comprueba que corresponde a la edición de la carta.')
                    if not candidates:status.setText('No hay coincidencias. Prueba el nombre o código de expansión que usa CardTrader.')
                    elif action=='auto' and len(candidates)==1:
                        dlg.auto_lookup=True
                        status.setText('Expansión detectada: '+expansions.currentText()+' · buscando blueprint por nombre y número '+physical_number.text().strip()+'…')
                        QTimer.singleShot(0,load_blueprints)
                    elif action=='auto':
                        status.setText('Encontré varias expansiones. Elige la que corresponda; después pulsa «Cargar cartas de la expansión».')
                    return
                if action=='blueprints':
                    term=normalized_name(card_query.text())
                    candidates=[x for x in data if term in normalized_name(x.get('name',''))]
                    candidates.sort(key=lambda x:(normalized_name(x.get('name',''))!=term,normalized_name(x.get('version','')),str(x.get('id',''))))
                    blueprints.clear()
                    for item in candidates[:500]:
                        label='{}{} · ID {}'.format(item.get('name',''),(' · '+str(item.get('version')) if item.get('version') else ''),item.get('id',''))
                        blueprints.addItem(label,str(item.get('id','')))
                    status.setText(str(len(candidates))+' blueprints coincidentes. Comprueba número, expansión e ilustración antes de consultar.')
                    if not candidates:status.setText('No hay blueprints coincidentes por nombre en esta expansión. Prueba el nombre en inglés que usa CardTrader.')
                    return
                if action=='offers':
                    bid=str(blueprints.currentData());rows=data.get(bid,[]) if isinstance(data,dict) else []
                    accepted=[];conflicts=[];rejections=[]
                    for offer in rows if isinstance(rows,list) else []:
                        compatible,reason=cardtrader_offer_compatibility(offer,lang,cond,var,selected_language,not bool(cardtrader_query_language(lang)))
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
                        if cents is None:continue
                        try:amount=float(cents)/100
                        except (ValueError,TypeError):continue
                        if str(currency or '').upper()!='EUR' or amount<0 or amount>1000000:continue
                        accepted.append((amount,offer))
                    accepted.sort(key=lambda x:x[0])
                    if not accepted:
                        suffix=(' No se pudo confirmar el estado/acabado ('+cond+' · '+var+').' if rejections else '')
                        status.setText('No hay ofertas EUR compatibles con el idioma, estado y acabado entre las 25 más baratas devueltas por CardTrader.'+suffix+(' El proveedor devolvió ofertas de otro idioma; no se guardaron.' if conflicts else ''))
                        return
                    prices=[x[0] for x in accepted[:5]];amount=sum(prices)/len(prices);floor=prices[0]
                    if langs.currentData()!=selected_language or str(blueprints.currentData())!=bid:
                        status.setText('Cambió la impresión o el idioma mientras se consultaba. Vuelve a consultar.');return
                    dlg.market_quote=(bid,amount,floor,len(accepted),selected_language)
                    result.setText('Idioma, estado y acabado compatibles: {} · {} · {} · ofertas compatibles: {} · mínimo: {} · media de las {} más baratas: {} EUR.\nComprueba que el blueprint coincide con número, expansión e ilustración.'.format(langs.currentText(),cond,var,len(accepted),euros(floor),len(prices),euros(amount)))
                    status.setText('Cotización recibida. Todavía no se ha guardado.')
                    save.setEnabled(True)
            worker.done.connect(received);worker.start()
        check.clicked.connect(lambda:run_request('info'))
        def forget_saved_token():
            try:
                delete_cardtrader_token();self.cardtrader_api_token='';key.clear();forget.setEnabled(False)
                status.setText('Token local borrado. Tendrás que volver a pegarlo para la próxima consulta.')
            except OSError as exc:status.setText('No se pudo borrar el token local: '+str(exc))
        forget.clicked.connect(forget_saved_token)
        expansion_btn.clicked.connect(lambda:run_request('expansions'))
        auto_btn.clicked.connect(lambda:run_request('auto'))
        def refresh_blueprint_filter():
            if not hasattr(dlg,'blueprint_catalog'):return False
            term=normalized_name(card_query.text())
            matches=[x for x in dlg.blueprint_catalog if term in normalized_name(x.get('name',''))]
            candidates=matches if matches else list(dlg.blueprint_catalog)
            candidates.sort(key=lambda x:(normalized_name(x.get('name',''))!=term,normalized_name(x.get('version','')),str(x.get('id',''))))
            blueprints.blockSignals(True);blueprints.clear()
            for item in candidates[:500]:blueprints.addItem('{}{} · ID {}'.format(item.get('name',''),(' · '+str(item.get('version')) if item.get('version') else ''),item.get('id','')),str(item.get('id','')))
            blueprints.blockSignals(False);invalidate_quote()
            update_print_button()
            return bool(matches)
        card_query.textEdited.connect(refresh_blueprint_filter)
        def load_blueprints():
            if getattr(dlg,'_api_busy',False) or not expansions.currentData():return
            token=entered_token()
            if not token:QMessageBox.warning(dlg,'Falta token','Pega tu Bearer Auth Token de CardTrader.');return
            self.cardtrader_api_token=token;status.setText('Cargando cartas de la expansión…')
            set_api_busy(True)
            worker=CardTraderApiWorker(token,'blueprints',expansion_id=expansions.currentData());dlg.track_worker(worker)
            def loaded(data,error):
                set_api_busy(False)
                if dlg._close_requested:return
                if error:status.setText('No se pudo cargar la expansión: '+error);return
                dlg.blueprint_catalog=data if isinstance(data,list) else []
                has_name_match=refresh_blueprint_filter()
                status.setText((str(len(dlg.blueprint_catalog))+' cartas cargadas. Verifica el número físico '+physical_number.text().strip()+'.') if has_name_match else ('No hubo coincidencia exacta por nombre; muestro el catálogo completo ('+str(len(dlg.blueprint_catalog))+' blueprints). Puedes elegirlo manualmente.'))
                if saved_mapping and str(expansions.currentData())==str(saved_mapping['expansion_id']):
                    saved_blueprint=blueprints.findData(str(saved_mapping['blueprint_id']))
                    if saved_blueprint>=0:
                        blueprints.setCurrentIndex(saved_blueprint)
                        status.setText('Impresión guardada cargada. Comprueba que sigue coincidiendo con la copia física.')
                if getattr(dlg,'auto_lookup',False):
                    term=normalized_name(card_query.text())
                    name_matches=[item for item in dlg.blueprint_catalog if term in normalized_name(item.get('name',''))]
                    exact=[item for item in name_matches if collector_number_matches(str(item.get('name',''))+' '+str(item.get('version','')),physical_number.text().strip())]
                    dlg.auto_lookup=False
                    if len(exact)==1:
                        index=blueprints.findData(str(exact[0].get('id','')))
                        if index>=0:blueprints.setCurrentIndex(index)
                        status.setText('Blueprint propuesto automáticamente: {} · comprueba que coinciden arte e idioma antes de consultar.'.format(blueprints.currentText()))
                    elif len(exact)>1:
                        status.setText('Hay varias impresiones con ese nombre y número. Elige manualmente la ilustración exacta.')
                    else:
                        status.setText('No encontré una coincidencia única por nombre y número. Elige el blueprint manualmente y comprueba la ilustración.')
            worker.done.connect(loaded);worker.start()
        def expansion_changed(*_):
            dlg.blueprint_catalog=[]
            blueprints.clear()
            invalidate_quote()
        expansions.currentIndexChanged.connect(expansion_changed)
        blueprints_btn.clicked.connect(load_blueprints)
        def update_print_button(*_):
            save_print_btn.setEnabled(bool(expansions.currentData() and blueprints.currentData()))
        expansions.currentIndexChanged.connect(update_print_button);blueprints.currentIndexChanged.connect(update_print_button)
        def selected_printing():
            expansion=dlg.expansion_catalog.get(str(expansions.currentData()),{}) if hasattr(dlg,'expansion_catalog') else {}
            blueprint=next((item for item in getattr(dlg,'blueprint_catalog',[]) if str(item.get('id',''))==str(blueprints.currentData())),{})
            if not expansion or not blueprint:return None
            blueprint_name=str(blueprint.get('name',''))
            if blueprint.get('version'):blueprint_name+=' · '+str(blueprint.get('version'))
            return {'expansion_id':expansion.get('id',''),'expansion':expansion.get('name',''),
                'expansion_code':expansion.get('code',''),'blueprint_id':blueprint.get('id',''),
                'card_name':blueprint_name,'collector_number':physical_number.text().strip()}
        def persist_printing():
            selection=selected_printing()
            if not selection or not selection['collector_number']:
                QMessageBox.warning(dlg,'Impresión incompleta','Carga la expansión, selecciona el blueprint y escribe el número físico antes de guardar.');return
            chosen_language=langs.currentData()
            if not chosen_language or (expected and normalize_market_language(chosen_language)!=normalize_market_language(expected)):
                QMessageBox.warning(dlg,'Idioma no coincide','Elige el idioma real de la carta antes de guardar la impresión.');return
            reply=QMessageBox.question(dlg,'Confirmar impresión física','¿Has comprobado que coinciden el nombre, expansión, número e ilustración con tu carta?')
            if reply!=QMessageBox.StandardButton.Yes:return
            try:self.save_cardtrader_print_mapping(pk,selection,chosen_language,True)
            except ValueError as exc:QMessageBox.warning(dlg,'Impresión ya registrada',str(exc));return
            self.save_manual_expansion_mapping(pk,selection,chosen_language)
            current=self.db.execute('SELECT id,card_id,name,language,condition,variant,quantity,image FROM cards WHERE id=?',(pk,)).fetchone()
            if current:self.refresh();self.detail_owned(current)
            status.setText('Impresión exacta guardada. Las próximas consultas usarán este blueprint directamente.')
        save_print_btn.clicked.connect(persist_printing)
        # The catalogue lookup is deliberately explicit; don't query offers until a blueprint is selected.
        offers_btn.clicked.connect(lambda:run_request('offers'))
        def persist():
            if not hasattr(dlg,'market_quote'):return
            product_id,amount,floor,offers,chosen_lang=dlg.market_quote
            if QMessageBox.question(dlg,'Confirmar edición','¿Has comprobado que el blueprint seleccionado corresponde al número, expansión e ilustración exactos de tu carta?')!=QMessageBox.StandardButton.Yes:return
            try:floor=float(floor) if floor is not None else None
            except (TypeError,ValueError):floor=None
            source_params={'blueprint_id':product_id,'language':chosen_lang}
            foil_filter=cardtrader_finish_filter(var)
            if foil_filter is not None:source_params['foil']='true' if foil_filter else 'false'
            source_url='https://api.cardtrader.com/api/v2/marketplace/products?'+urllib.parse.urlencode(source_params)
            selection=selected_printing()
            if not selection or not selection['collector_number']:
                QMessageBox.warning(dlg,'Impresión incompleta','Selecciona el blueprint exacto y escribe el número físico antes de guardar.');return
            try:self.save_cardtrader_print_mapping(pk,selection,chosen_lang,True)
            except ValueError as exc:QMessageBox.warning(dlg,'Impresión ya registrada',str(exc));return
            self.save_manual_expansion_mapping(pk,selection,chosen_lang)
            self.db.execute("""INSERT INTO api_valuations(card_row_id,product_id,amount,floor,offers,language,source_url,fetched_at,condition,variant) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(card_row_id) DO UPDATE SET product_id=excluded.product_id,amount=excluded.amount,floor=excluded.floor,offers=excluded.offers,language=excluded.language,source_url=excluded.source_url,fetched_at=excluded.fetched_at,condition=excluded.condition,variant=excluded.variant""",(pk,str(product_id),amount,floor,offers,chosen_lang,source_url,int(time.time()),cond,var))
            self.db.execute('INSERT OR IGNORE INTO cardtrader_price_history(card_row_id,fetched_at,price,product_id,condition,variant) VALUES(?,?,?,?,?,?)',(pk,int(time.time()),float(amount),str(product_id),cond,var))
            self.db.commit();dlg.accept();self.refresh();self.detail_owned(self.active_owned_row)
        save.clicked.connect(persist)
        dlg.exec()

    def edit_edition_link(self):
        if not hasattr(self,'active_owned_row'):return
        pk,cid,name,lang,cond,var,qty,img=self.active_owned_row
        previous=self.db.execute('SELECT source_url,note FROM edition_links WHERE card_row_id=?',(pk,)).fetchone()
        dlg=QDialog(self);dlg.setWindowTitle('Identificar impresión exacta — '+name);dlg.setMinimumWidth(550)
        form=QFormLayout(dlg)
        info=QLabel(f'{name} · {cid}\nIdioma: {lang} · Estado: {cond} · Acabado: {var}')
        info.setWordWrap(True);form.addRow(info)
        link=QLineEdit(previous[0] if previous else '')
        link.setPlaceholderText('https://www.cardmarket.com/es/Pokemon/Products/...')
        note=QLineEdit(previous[1] if previous else '')
        note.setPlaceholderText('Ej.: CSV9.5C · 233/208 · chino simplificado')
        form.addRow('Ficha de Cardmarket:',link);form.addRow('Edición / número:',note)
        warning=QLabel('La ficha identifica la impresión, pero no garantiza un precio automático. Comprueba que coinciden ilustración, código e idioma.')
        warning.setWordWrap(True);form.addRow(warning)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        remove=buttons.addButton('Quitar vínculo',QDialogButtonBox.ButtonRole.ResetRole)
        def unlink():
            self.db.execute('DELETE FROM edition_links WHERE card_row_id=?',(pk,));self.db.commit()
            dlg.reject();self.detail_owned(self.active_owned_row)
        remove.clicked.connect(unlink)
        buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        url=link.text().strip()
        if url and not (url.startswith('https://www.cardmarket.com/') or url.startswith('https://cardmarket.com/')):
            QMessageBox.warning(self,'Enlace incorrecto','Introduce una ficha HTTPS de Cardmarket.');return
        if not url:
            QMessageBox.warning(self,'Falta enlace','Introduce el enlace de la impresión exacta.');return
        self.db.execute('''INSERT INTO edition_links(card_row_id,source_url,note,updated_at) VALUES(?,?,?,?)
            ON CONFLICT(card_row_id) DO UPDATE SET source_url=excluded.source_url,
            note=excluded.note,updated_at=excluded.updated_at''',
            (pk,url,note.text().strip(),int(time.time())))
        self.db.commit();self.detail_owned(self.active_owned_row)

    def edit_valuation(self):
        if not hasattr(self,'active_owned_row'):return
        pk,cid,name,lang,cond,var,qty,img=self.active_owned_row
        previous=self.db.execute('SELECT amount,source_url,note FROM verified_valuations WHERE card_row_id=?',(pk,)).fetchone()
        dlg=QDialog(self);dlg.setWindowTitle('Precio verificado — '+name);dlg.setMinimumWidth(490)
        form=QFormLayout(dlg)
        info=QLabel(f'{name}\nID: {cid} | Idioma: {lang} | Estado: {cond} | Acabado: {var}');info.setWordWrap(True)
        form.addRow(info)
        amount=QLineEdit(str(previous[0]).replace('.',',') if previous else '');amount.setPlaceholderText('Ej.: 57,93')
        linked=self.db.execute('SELECT source_url FROM edition_links WHERE card_row_id=?',(pk,)).fetchone()
        url=QLineEdit(previous[1] if previous else (linked[0] if linked else ''));url.setPlaceholderText('https://www.cardmarket.com/...')
        note=QLineEdit(previous[2] if previous else '');note.setPlaceholderText('Edición y estado comprobados')
        form.addRow('Precio en €:',amount);form.addRow('URL de la edición exacta:',url);form.addRow('Notas:',note)
        warning=QLabel('Introduce un precio solo tras verificar la impresión y el idioma. No se consulta automáticamente.');warning.setWordWrap(True)
        form.addRow(warning)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        remove=buttons.addButton('Quitar valoración',QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject)
        remove.clicked.connect(lambda:(self.db.execute('DELETE FROM verified_valuations WHERE card_row_id=?',(pk,)),self.db.commit(),dlg.reject(),self.refresh(),self.detail_owned(self.active_owned_row)))
        form.addRow(buttons)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        try:
            value=float(amount.text().strip().replace(',','.'))
            if not (0<=value<10000000):raise ValueError()
        except ValueError:
            QMessageBox.warning(self,'Precio incorrecto','Introduce un precio válido en euros.');return
        link=url.text().strip()
        if not link.startswith('https://'):
            QMessageBox.warning(self,'Fuente requerida','Introduce un enlace HTTPS a la edición exacta.');return
        self.db.execute('''INSERT INTO verified_valuations(card_row_id,amount,source_url,note,updated_at)
            VALUES(?,?,?,?,?) ON CONFLICT(card_row_id) DO UPDATE SET amount=excluded.amount,
            source_url=excluded.source_url,note=excluded.note,updated_at=excluded.updated_at''',
            (pk,value,link,note.text().strip(),int(time.time())))
        self.db.commit();self.refresh();self.detail_owned(self.active_owned_row)

    def get_history(self,cid,cutoff):
        if isinstance(cid,int):
            mapping=self.get_cardtrader_print_mapping(cid)
            if not mapping or not mapping.get('confirmed'):return []
            card=self.db.execute('SELECT condition,variant FROM cards WHERE id=?',(cid,)).fetchone()
            if not card:return []
            return self.db.execute('SELECT fetched_at,price FROM cardtrader_price_history WHERE card_row_id=? AND product_id=? AND condition=? AND variant=? AND fetched_at>=? ORDER BY fetched_at,id',(cid,str(mapping['blueprint_id']),card[0],card[1],cutoff)).fetchall()
        if isinstance(cid,tuple):cid=cid[0]
        # Older installations can contain a valid cached quote but no historical row.
        # Reconcile it at read time too, so the detail page never loses that observation.
        cached=self.get_price(cid)
        if cached and cached.get('status')=='ok':
            quote=cached.get('trend') if cached.get('trend') is not None else cached.get('avg')
            if quote is not None:
                recorded=int(cached.get('fetched_at') or time.time())
                existing=self.db.execute('SELECT 1 FROM price_history WHERE card_id=? LIMIT 1',(cid,)).fetchone()
                if not existing:
                    self.db.execute('INSERT OR IGNORE INTO price_history(card_id,fetched_at,price,source_updated) VALUES(?,?,?,?)',
                                    (cid,recorded,float(quote),cached.get('updated') or ''))
                    self.db.commit()
        return self.db.execute('SELECT fetched_at,price FROM price_history WHERE card_id=? AND fetched_at>=? ORDER BY fetched_at,id',(cid,cutoff)).fetchall()

    def get_price(self,cid):
        row=self.db.execute('SELECT trend,low,avg,avg1,avg7,avg30,updated,fetched_at,status FROM card_prices WHERE card_id=?',(cid,)).fetchone()
        if not row:return None
        return dict(zip(('trend','low','avg','avg1','avg7','avg30','updated','fetched_at','status'),row))

    def get_collection_sort_price(self,row):
        """Use the same verified/CardTrader/general priority as the visible card price."""
        price=self.get_display_price(row[1],row[3],row[5],row[0])
        amount=price.get('trend') if price else None
        if amount is None and price:amount=price.get('avg')
        try:return float(amount) if amount is not None else None
        except (TypeError,ValueError):return None

    def update_summary(self):
        total=verified_total=0.0
        verified=cardtrader=general=missing=0
        for row in self.rows:
            p=self.get_display_price(row[1],row[3],row[5],row[0]);qty=row[6]
            amount=(p.get('trend') if p else None)
            if amount is None and p:amount=p.get('avg')
            if amount is None:missing+=qty
            else:
                total+=amount*qty
                if p.get('status')=='verified':verified+=qty;verified_total+=amount*qty
                elif p.get('status') in ('market_api','market_api_stale'):cardtrader+=qty
                else:general+=qty
        count=sum(r[6] for r in self.rows)
        self.total_value_label.setText(euros(total) if verified+cardtrader+general else 'Sin precios disponibles')
        self.summary.setText(f'{count} cartas · {len(self.rows)} registros · {verified} verificadas · {cardtrader} CardTrader · {general} referencia general · {missing} sin precio')
        self.total_value_label.setToolTip('Total orientativo: suma precio verificado, ofertas CardTrader por idioma/impresión y, cuando falta una cotización, referencia general. Solo verificado: '+euros(verified_total))

    def update_prices(self,force=False,ids=None):
        if ids is None:ids=list(dict.fromkeys([row[1] for row in self.rows]+[r[0] for r in self.db.execute('SELECT DISTINCT card_id FROM wishlist')]))
        now=int(time.time())
        pending=[]
        for cid in ids:
            if str(cid).startswith('manual-'):continue
            old=self.get_price(cid)
            if force or old is None or now-old['fetched_at']>(3600 if old['status']=='error' else 24*3600):pending.append(cid)
        for cid in pending:
            if cid not in self.price_queue:self.price_queue.append(cid)
        if hasattr(self,'price_status'):
            self.price_status.setText(f'Precios: {len(pending)} pendientes de actualización' if pending else 'Precios: actualizados o en caché (máx. 24 h)')
        self.start_price_batch()

    def start_price_batch(self):
        if getattr(self,'_closing',False) or self.price_busy or not self.price_queue:return
        # Small batches keep the interface responsive, and avoid flooding the API.
        batch=self.price_queue[:15];del self.price_queue[:15]
        self.price_busy=True
        worker=PriceFetch(batch);self.price_worker=worker
        worker.done.connect(self.prices_received)
        worker.finished.connect(self.price_batch_finished)
        worker.start()

    def prices_received(self,results):
        now=int(time.time())
        for cid,values,error in results:
            if error:
                # Preserve previously valid quotes if the connection fails.
                if self.get_price(cid) is None:
                    values=dict.fromkeys(('trend','low','avg','avg1','avg7','avg30'))
                    values.update(updated='',status='error')
                else:continue
            self.db.execute("""INSERT INTO card_prices(card_id,trend,low,avg,avg1,avg7,avg30,updated,fetched_at,status)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(card_id) DO UPDATE SET
                trend=excluded.trend,low=excluded.low,avg=excluded.avg,avg1=excluded.avg1,
                avg7=excluded.avg7,avg30=excluded.avg30,updated=excluded.updated,
                fetched_at=excluded.fetched_at,status=excluded.status""",
                (cid,*(values.get(k) for k in ('trend','low','avg','avg1','avg7','avg30','updated')),now,values['status']))
            # Registrar solo cotizaciones válidas, nunca errores ni precios ausentes.
            # Evitar duplicar el mismo valor de la misma actualización de la fuente.
            quote=values.get('trend') if values.get('trend') is not None else values.get('avg')
            if values.get('status')=='ok' and quote is not None:
                last=self.db.execute('SELECT price,source_updated FROM price_history WHERE card_id=? ORDER BY fetched_at DESC,id DESC LIMIT 1',(cid,)).fetchone()
                source_updated=values.get('updated') or ''
                if not last or last[0]!=quote or (source_updated and last[1]!=source_updated):
                    # Source timestamp is used for deduplication; local capture time is accurate.
                    self.db.execute('INSERT OR IGNORE INTO price_history(card_id,fetched_at,price,source_updated) VALUES(?,?,?,?)',(cid,now,quote,source_updated))
            for tile in self.owned_tiles:
                if tile.card_id==cid:tile.set_price(self.get_display_price(cid,tile.language,tile.variant,tile.row_id),tile.quantity)
            if self.active_price_id==cid:
                row_id=getattr(self,'active_owned_row',(None,))[0]
                self.collection_detail.show_price(self.get_display_price(*getattr(self,'active_price_key',(cid,'','')),card_row_id=row_id))
                self.collection_detail.refresh_history()
        self.db.commit();self.update_summary()
        if hasattr(self,'wish_summary'):self.refresh_wishlist()
        if hasattr(self,'price_status'):self.price_status.setText('Precios: última comprobación '+datetime.datetime.now().strftime('%d/%m/%Y %H:%M'))
        # The graph can be open during a refresh; update it after persisting data.
        if self.active_price_id:self.collection_detail.refresh_history()

    def price_batch_finished(self):
        self.price_busy=False
        self.price_worker=None
        if self.price_queue:QTimer.singleShot(150,self.start_price_batch)

    def change_quantity(self,pk,delta):
        row=self.get_row(pk)
        if not row:return
        new_qty=row[6]+delta
        if new_qty<1:
            if QMessageBox.question(self,'Última copia',f'¿Eliminar la última copia de {row[2]}?')!=QMessageBox.StandardButton.Yes:return
            self.db.execute('DELETE FROM cards WHERE id=?',(pk,))
        elif new_qty<=9999:
            self.db.execute('UPDATE cards SET quantity=? WHERE id=?',(new_qty,pk))
        else:
            QMessageBox.information(self,'Límite','Máximo 9999 copias por registro.')
            return
        self.db.commit();self.refresh()

    def get_row(self,pk):return next((r for r in self.rows if r[0]==pk),None)

    def merge_card_row_data(self,source_id,target_id):
        """Keep the newest per-copy price data when two identical prints merge."""
        for table,time_column,columns in (
            ('verified_valuations','updated_at','amount,source_url,note,updated_at'),
            ('api_valuations','fetched_at','product_id,amount,floor,offers,language,source_url,fetched_at,condition,variant'),
            ('cardtrader_print_mappings','updated_at','expansion_id,expansion_name,expansion_code,blueprint_id,blueprint_name,collector_number,language,confirmed,updated_at'),
        ):
            source=self.db.execute(f'SELECT {columns} FROM {table} WHERE card_row_id=?',(source_id,)).fetchone()
            target=self.db.execute(f'SELECT {time_column} FROM {table} WHERE card_row_id=?',(target_id,)).fetchone()
            timestamp_index=columns.split(',').index(time_column)
            if source and (not target or int(source[timestamp_index])>int(target[0])):
                placeholders=','.join('?' for _ in source)
                update_cols=columns.split(',')
                assignments=','.join(f'{col}=?' for col in update_cols)
                self.db.execute(f'INSERT INTO {table}(card_row_id,{columns}) VALUES(?,{placeholders}) ON CONFLICT(card_row_id) DO UPDATE SET {assignments}',
                    (target_id,*source,*source))
        self.db.execute('INSERT OR IGNORE INTO cardtrader_price_history(card_row_id,fetched_at,price,product_id,condition,variant) SELECT ?,fetched_at,price,product_id,condition,variant FROM cardtrader_price_history WHERE card_row_id=?',(target_id,source_id))
        self.db.execute('UPDATE cardtrader_lookup_attempts SET card_row_id=? WHERE card_row_id=?',(target_id,source_id))
        source_link=self.db.execute('SELECT source_url,note,updated_at FROM edition_links WHERE card_row_id=?',(source_id,)).fetchone()
        target_link=self.db.execute('SELECT updated_at FROM edition_links WHERE card_row_id=?',(target_id,)).fetchone()
        if source_link and (not target_link or int(source_link[2])>int(target_link[0])):
            self.db.execute('INSERT INTO edition_links(card_row_id,source_url,note,updated_at) VALUES(?,?,?,?) ON CONFLICT(card_row_id) DO UPDATE SET source_url=excluded.source_url,note=excluded.note,updated_at=excluded.updated_at',(target_id,*source_link))

    def edit(self,pk):
        r=self.get_row(pk)
        if not r:return
        pk,cid,name,lang,cond,var,qty,img=r;dlg=CardDialog(self,dict(language=lang,condition=cond,variant=var,quantity=qty),cid=cid)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        lang,cond,var,qty=dlg.values()
        physical_key=self.db.execute('SELECT physical_print_key FROM cards WHERE id=?',(pk,)).fetchone()
        physical_key=physical_key[0] if physical_key else ''
        existing=self.db.execute('SELECT id,quantity FROM cards WHERE card_id=? AND language=? AND condition=? AND variant=? AND physical_print_key=? AND id<>?',(cid,lang,cond,var,physical_key,pk)).fetchone()
        if existing:
            combined=existing[1]+qty
            if combined>9999:
                QMessageBox.warning(self,'Límite','La cantidad combinada supera 9999 copias.');return
            self.merge_card_row_data(pk,existing[0])
            self.db.execute('UPDATE cards SET quantity=? WHERE id=?',(combined,existing[0]))
            self.db.execute('DELETE FROM cards WHERE id=?',(pk,))
        else:
            changed_quote_identity=(lang!=r[3] or cond!=r[4] or var!=r[5])
            if lang!=r[3]:
                self.db.execute('DELETE FROM verified_valuations WHERE card_row_id=?',(pk,))
                self.db.execute('DELETE FROM api_valuations WHERE card_row_id=?',(pk,))
                self.db.execute('DELETE FROM cardtrader_price_history WHERE card_row_id=?',(pk,))
                self.db.execute('DELETE FROM cardtrader_print_mappings WHERE card_row_id=?',(pk,))
                self.db.execute('DELETE FROM cardtrader_lookup_attempts WHERE card_row_id=?',(pk,))
                self.db.execute('DELETE FROM edition_links WHERE card_row_id=?',(pk,))
                self.db.execute('UPDATE cards SET physical_print_key=? WHERE id=?',('',pk))
            elif cond!=r[4] or var!=r[5]:
                self.db.execute('DELETE FROM verified_valuations WHERE card_row_id=?',(pk,))
                self.db.execute('DELETE FROM api_valuations WHERE card_row_id=?',(pk,))
                self.db.execute('DELETE FROM cardtrader_price_history WHERE card_row_id=?',(pk,))
                self.db.execute('DELETE FROM cardtrader_lookup_attempts WHERE card_row_id=?',(pk,))
            self.db.execute('UPDATE cards SET language=?,condition=?,variant=?,quantity=? WHERE id=?',(lang,cond,var,qty,pk))
        self.db.commit();self.refresh()
        if not existing and changed_quote_identity:self.queue_auto_cardtrader_price(pk,force=True)

    def delete(self,pk):
        r=self.get_row(pk)
        if not r:return
        if QMessageBox.question(self,'Confirmar',f'¿Eliminar {r[2]} de tu colección?')!=QMessageBox.StandardButton.Yes:return
        self.db.execute('DELETE FROM cards WHERE id=?',(pk,));self.db.commit();self.refresh()
