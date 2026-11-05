"""SearchTab tab behavior for PokeVault.

Methods use the shared widgets, services and database helpers in app_core.
"""
from app_core import *


class SearchTabMixin:
    def on_query_edited(self,text):
        self.suggest_timer.stop()
        self.suggest_model.setStringList([])
        if len(text.strip())>=2:self.suggest_timer.start()

    def build_search_tab(self,tabs):
        search=QWidget();sl=QVBoxLayout(search);sl.setContentsMargins(16,16,16,14);sl.setSpacing(12)
        top=QHBoxLayout();top.setSpacing(8);self.query=QLineEdit();self.query.setPlaceholderText('Buscar por nombre, por ejemplo Charizard');self.query.returnPressed.connect(self.search)
        # Autocompletado consultando nombres reales del catálogo, sin bloquear la interfaz.
        self.suggest_model=QStringListModel(self)
        self.completer=QCompleter(self.suggest_model,self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.query.setCompleter(self.completer)
        self.completer.activated.connect(lambda _name: self.search())
        self.suggest_timer=QTimer(self);self.suggest_timer.setSingleShot(True)
        self.suggest_timer.setInterval(350)
        self.suggest_timer.timeout.connect(self.load_suggestions)
        self.query.textEdited.connect(self.on_query_edited)
        self.species_worker=None;self.species_names=[];self.species_loading=False
        self.search_active_worker=None;self.pending_search=False
        btn=QPushButton('Buscar');btn.setObjectName('primary');btn.setMinimumHeight(40);btn.clicked.connect(self.search);top.addWidget(self.query);top.addWidget(btn);clear_btn=QPushButton('Limpiar búsqueda');clear_btn.clicked.connect(self.clear_search);top.addWidget(clear_btn);manual_btn=QPushButton('＋ Añadir carta manualmente');manual_btn.clicked.connect(self.add_manual_card);top.addWidget(manual_btn);sl.addLayout(top)
        setbar=QHBoxLayout();setbar.setSpacing(8)
        self.set_query=QLineEdit();self.set_query.setPlaceholderText('Expansión por nombre o código: csv9, sv08, 151...')
        self.set_query.returnPressed.connect(self.expansion_entered)
        self.selected_set_id=None
        self.set_suggest_model=QStringListModel(self)
        self.set_completer=QCompleter(self.set_suggest_model,self)
        self.set_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.set_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.set_query.setCompleter(self.set_completer)
        self.set_completer.activated.connect(self.expansion_selected)
        self.set_query.textEdited.connect(self.expansion_edited)
        self.set_timer=QTimer(self);self.set_timer.setSingleShot(True);self.set_timer.setInterval(300)
        self.set_timer.timeout.connect(self.load_set_suggestions)
        self.set_matches={}
        self.set_button=QPushButton('Buscar expansión');self.set_button.setObjectName('primary');self.set_button.clicked.connect(self.find_sets)
        setbar.addWidget(self.set_query);setbar.addWidget(self.set_button);sl.addLayout(setbar)
        self.status=QLabel('');self.status.setWordWrap(True);sl.addWidget(self.status)
        self.search_scroll=QScrollArea();self.search_scroll.setWidgetResizable(True)
        self.gallery=QWidget();self.gallery_layout=QGridLayout(self.gallery)
        self.gallery_layout.setContentsMargins(8,8,8,8);self.gallery_layout.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignHCenter);self.gallery_layout.setSpacing(14)
        self.search_scroll.setWidget(self.gallery)
        self.search_stack=QStackedWidget();self.search_stack.addWidget(self.search_scroll)
        self.search_detail=DetailPage(lambda:self.search_stack.setCurrentIndex(0))
        self.search_stack.addWidget(self.search_detail)
        self.search_empty=empty_state('⌕','Busca cartas para empezar','Escribe un nombre o el código de una expansión para explorar el catálogo.')
        self.search_stack.addWidget(self.search_empty);self.search_stack.setCurrentWidget(self.search_empty)
        sl.addWidget(self.search_stack);tabs.addTab(search,'⌕  Buscar cartas')

    def load_suggestions(self):
        term=self.query.text().strip()
        if len(term)<2:return
        if self.species_names:
            self.show_species_suggestions(term)
        elif not self.species_loading:
            self.species_loading=True
            self.species_worker=SpeciesFetch()
            self.species_worker.done.connect(self.species_ready)
            self.species_worker.start()

    def species_ready(self,names,error):
        self.species_loading=False
        self.species_names=names
        if names:self.show_species_suggestions(self.query.text().strip())

    def show_species_suggestions(self,term):
        if len(term)<2:return
        term=term.casefold()
        matches=[name for name in self.species_names if name.casefold().startswith(term)]
        self.suggest_model.setStringList(matches[:30] if not term.startswith('meg') else ['Mega '+name for name in self.species_names if name.casefold().startswith(term[5:].strip())][:30] if len(term)>5 else [])
        if matches and self.query.hasFocus():self.completer.complete()

    def expansion_edited(self,text):
        self.selected_set_id=None
        self.set_timer.stop()
        if len(text.strip())>=2:
            self.set_timer.start()
        else:
            self.set_suggest_model.setStringList([])

    def load_set_suggestions(self):
        term=self.set_query.text().strip()
        if len(term)<2:return
        if self.set_names:
            self.show_set_suggestions(term)
        elif not self.set_loading:
            self.set_loading=True
            self.set_worker=SetFetch('')
            self.set_worker.done.connect(self.all_sets_ready)
            self.set_worker.start()

    def all_sets_ready(self,sets,error):
        self.set_loading=False
        if error:
            # La búsqueda manual sigue disponible aunque falle el autocompletado.
            return
        self.set_names=sorted(sets,key=lambda x:x.get('name','').casefold())
        self.show_set_suggestions(self.set_query.text().strip())

    def show_set_suggestions(self,term):
        if len(term)<2:return
        term=term.casefold()
        matches=[x for x in self.set_names if term in x.get('name','').casefold() or term in x.get('id','').casefold()]
        self.set_matches={x.get('name','')+' ('+x.get('id','')+')':x.get('id') for x in matches[:40]}
        options=list(self.set_matches)
        self.set_suggest_model.setStringList(options)
        if options and self.set_query.hasFocus():self.set_completer.complete()

    def expansion_selected(self,text):
        self.selected_set_id=self.set_matches.get(text)
        if self.selected_set_id:
            self.set_query.setText(text)
            self.search()

    def expansion_entered(self):
        if self.selected_set_id:self.search()
        else:self.find_sets()

    def find_sets(self):
        term=self.set_query.text().strip()
        if len(term)<2:return
        if self.set_names:
            self.show_set_suggestions(term)
            if any(x.get('id','').casefold()==term.casefold() for x in self.set_names):self.search_set_code(term)
            elif len(self.set_matches)==1:self.expansion_selected(next(iter(self.set_matches)))
            elif not self.set_matches and term:self.search_set_code(term)
        else:
            self.search_set_code(term)

    def search_set_code(self,term):
        # Direct expansion IDs also work if the autocomplete catalog is incomplete.
        self.selected_set_id=term.strip().casefold()
        self.search()

    def clear_search(self):
        self.suggest_timer.stop()
        self.set_timer.stop()
        self.pending_search=False
        self.search_stack.setCurrentIndex(0)
        self.query.clear()
        self.set_query.clear()
        self.selected_set_id=None
        self.set_matches={}
        self.set_suggest_model.setStringList([])
        self.search_serial+=1
        self.show_results([], '')

    def search(self):
        self.search_serial+=1
        serial=self.search_serial
        self.search_stack.setCurrentIndex(0)
        term=self.query.text().strip()
        set_id=self.selected_set_id
        if set_id:
            if self.defer_search_if_busy():return
            self.status.setText('Cargando cartas de la expansión...')
            worker=SetCardsFetch(set_id,term);self.set_cards_worker=worker;self.search_active_worker=worker
            worker.finished.connect(lambda w=worker,s=serial:self.search_worker_finished(w,s))
            worker.start()
            return
        if len(term)<2:
            self.pending_search=False
            self.show_results([], '')
            self.status.setText('Escribe al menos dos caracteres o selecciona una expansión.')
            return
        if self.defer_search_if_busy():return
        self.status.setText('Buscando nombres completos en los catálogos (puede tardar)...')
        worker=Fetch(term);self.worker=worker;self.search_active_worker=worker
        worker.finished.connect(lambda w=worker,s=serial:self.search_worker_finished(w,s))
        worker.start()

    def defer_search_if_busy(self):
        worker=self.search_active_worker
        if worker and worker.isRunning():
            self.pending_search=True
            self.status.setText('La búsqueda anterior está terminando; esta búsqueda empezará automáticamente enseguida.')
            return True
        self.pending_search=False
        return False

    def search_worker_finished(self,worker,serial):
        if self.worker is worker:self.worker=None
        if self.set_cards_worker is worker:self.set_cards_worker=None
        if self.search_active_worker is worker:self.search_active_worker=None
        result=getattr(worker,'result',None)
        if serial==self.search_serial and result is not None:self.show_results(*result)
        active=self.search_active_worker
        if self.pending_search and not (active and active.isRunning()):
            self.pending_search=False
            QTimer.singleShot(0,self.search)

    def show_results(self,items,error):
        self.generation+=1;generation=self.generation
        while self.gallery_layout.count():
            item=self.gallery_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.search_tiles=[];targets={};entries=[]
        for card in items:
            tile=Tile(card,self.add_card,self.detail_search,self.add_wish);self.search_tiles.append(tile)
            cid=card.get('id','');targets.setdefault(cid,[]).append(tile);entries.append((cid,card.get('image','')))
        self.reflow(self.gallery_layout,self.search_tiles,230,self.search_scroll)
        if entries:self.images(entries,targets,generation)
        self.status.setText('Error de conexión: '+error if error else f'{len(items)} cartas encontradas. Pulsa «Añadir a colección» en la carta deseada.')
        if items:
            self.search_stack.setCurrentIndex(0)
        else:
            title=self.search_empty.findChild(QLabel,'emptyTitle')
            message=self.search_empty.findChild(QLabel,'emptyMessage')
            if error:
                title.setText('No se pudo completar la búsqueda');message.setText(error)
            elif not self.query.text().strip() and not self.selected_set_id:
                title.setText('Busca cartas para empezar');message.setText('Escribe un nombre o el código de una expansión para explorar el catálogo.')
            else:
                title.setText('No encontramos cartas');message.setText('Prueba con otro nombre, número o código de expansión.')
            self.search_stack.setCurrentIndex(2)

    def detail_search(self,card):
        self.search_detail.show_card(card.get('name',''),card.get('id',''),card.get('image',''),
                                     'Número: '+str(card.get('localId','—')))
        self.search_stack.setCurrentIndex(1)

    def add_manual_card(self):
        dlg=QDialog(self);dlg.setWindowTitle('Añadir carta que no aparece en el catálogo');dlg.setMinimumWidth(460)
        form=QFormLayout(dlg)
        name=QLineEdit();name.setPlaceholderText('Ej.: Mega Floette ex')
        set_name=QLineEdit();set_name.setPlaceholderText('Nombre o código de expansión (opcional)')
        number=QLineEdit();number.setPlaceholderText('Número de la carta (opcional)')
        photo=QLineEdit();photo.setReadOnly(True)
        def pick_photo():
            filename,_=QFileDialog.getOpenFileName(dlg,'Fotografía de la carta',str(Path.home()),'Imágenes (*.png *.jpg *.jpeg *.webp)')
            if filename:photo.setText(filename)
        pick=QPushButton('Elegir fotografía');pick.clicked.connect(pick_photo)
        destination=QComboBox();destination.addItems(['Mi colección','Lista de deseos'])
        form.addRow('Nombre de la carta',name);form.addRow('Expansión',set_name);form.addRow('Número',number)
        form.addRow('Fotografía',photo);form.addRow('',pick);form.addRow('Guardar en',destination)
        save=QPushButton('Continuar: idioma, estado y cantidad');save.clicked.connect(dlg.accept);form.addRow(save)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        if not name.text().strip():QMessageBox.warning(self,'Falta nombre','Indica el nombre de la carta.');return
        cid='manual-'+hashlib.sha256((normalized_name(name.text())+'|'+normalized_name(set_name.text())+'|'+normalized_name(number.text())).encode()).hexdigest()[:20]
        image=''
        if photo.text():
            try:
                src=Path(photo.text());target=CACHE/('manual_'+cid+src.suffix.lower())
                shutil.copy2(src,target);image=str(target)
            except Exception as exc:QMessageBox.warning(self,'Fotografía','No se pudo copiar la imagen: '+str(exc))
        card={'id':cid,'name':name.text().strip(),'localId':number.text().strip(),'image':image,'set':{'name':set_name.text().strip()}}
        if destination.currentIndex()==0:self.add_card(card)
        else:self.add_wish(card)
