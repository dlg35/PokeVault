"""PokeVault application entry point and top-level window coordinator."""
import hashlib
import json
import zipfile
from app_core import *
from PySide6.QtSvg import QSvgRenderer
from search_tab import SearchTabMixin
from collection_tab import CollectionTabMixin
from wishlist_tab import WishlistTabMixin


class Window(SearchTabMixin, CollectionTabMixin, WishlistTabMixin, QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('PokeVault — Colección Pokémon');self.resize(1440,900);self.setMinimumSize(1120,720)
        self.db=connect();self.worker=None;self.image_workers=[];self.market_auto_workers=[];self.cardtrader_catalog_cache={};self.active_cardtrader_rows=set();self.active_cardtrader_context={};self.cardtrader_individual_queue=[];self.cardtrader_batch_queue=[];self.cardtrader_batch_ids=set();self.cardtrader_batch_accounted=set();self.cardtrader_batch_total=0;self.cardtrader_batch_done=0;self.cardtrader_batch_counts={'quoted':0,'no_offers':0,'catalog_missing':0,'expansion_unmatched':0,'blueprint_unmatched':0,'language_mismatch':0,'api_error':0};self.cardtrader_batch_active=False;self.generation=0;self.collection_generation=0
        self.price_worker=None;self.price_queue=[];self.price_busy=False;self.active_price_id=None;self.active_price_key=None
        self.search_tiles=[];self.owned_tiles=[];self.wish_tiles=[];self.wish_generation=0;self.album_generation=0;self.set_worker=None;self.set_cards_worker=None;self.set_options=[];self.search_serial=0;self.set_names=[];self.set_loading=False;self.set_request_serial=0
        tabs=QTabWidget()
        central=QWidget();root=QVBoxLayout(central);root.setContentsMargins(16,12,16,14);root.setSpacing(10)
        header=QFrame();header.setObjectName('appHeader');header.setFixedHeight(88)
        header_layout=QHBoxLayout(header);header_layout.setContentsMargins(16,7,20,7);header_layout.setSpacing(14)
        logo_root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
        logo_path=logo_root/'assets'/'pokevault-mark.svg'
        mark_frame=QFrame();mark_frame.setObjectName('brandMarkFrame');mark_frame.setFixedSize(72,72)
        mark_layout=QVBoxLayout(mark_frame);mark_layout.setContentsMargins(2,2,2,2)
        logo=QLabel();logo.setObjectName('brandLogo');logo.setFixedSize(68,68);logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap=QPixmap(68,68);logo_pixmap.fill(Qt.GlobalColor.transparent)
        renderer=QSvgRenderer(str(logo_path))
        if renderer.isValid():
            logo_painter=QPainter(logo_pixmap);renderer.render(logo_painter);logo_painter.end()
        if not logo_pixmap.isNull():logo.setPixmap(logo_pixmap)
        mark_layout.addWidget(logo);header_layout.addWidget(mark_frame)
        brand=QVBoxLayout();brand.setSpacing(2)
        brand_title=QLabel('PokeVault');brand_title.setObjectName('brandTitle')
        brand_subtitle=QLabel('Tu biblioteca de cartas Pokémon');brand_subtitle.setObjectName('brandSubtitle')
        brand.addWidget(brand_title);brand.addWidget(brand_subtitle);header_layout.addLayout(brand);header_layout.addStretch()
        root.addWidget(header);root.addWidget(tabs,1);self.setCentralWidget(central)
        if not logo_pixmap.isNull():self.setWindowIcon(QIcon(str(logo_path)))
        self.build_search_tab(tabs)
        self.build_collection_tab(tabs)
        self.build_wishlist_tab(tabs)
        self.search_scroll.viewport().installEventFilter(self)
        self.collection_scroll.viewport().installEventFilter(self)
        self.wish_scroll.viewport().installEventFilter(self)
        self.album_scroll.viewport().installEventFilter(self)
        self.setStyleSheet('''
            QWidget{background:#0b1120;color:#e7edf7;font-family:"Inter","Segoe UI",sans-serif;font-size:13px}
            QMainWindow{background:#0b1120}
            QLabel{background:transparent}
            QFrame#appHeader{background:#111b2d;border:1px solid #59492f;border-radius:19px}
            QFrame#brandMarkFrame{background:#0d1727;border:1px solid #8a6837;border-radius:19px}
            QLabel#brandTitle{font-size:27px;font-weight:850;color:#fff5df}
            QLabel#brandSubtitle{font-size:13px;color:#bdad91}
            QTabWidget::pane{background:#0e1727;border:1px solid #263750;border-radius:14px;top:-1px}
            QTabBar{background:transparent}
            QTabBar::tab{background:#111b2d;color:#94a6bf;padding:12px 22px;margin:0 6px 0 0;border:1px solid #25354c;border-bottom:0;border-top-left-radius:11px;border-top-right-radius:11px;font-weight:700}
            QTabBar::tab:selected{background:#302719;color:#f4c66d;border-color:#b1833e;border-bottom:3px solid #e2a63d}
            QTabBar::tab:hover:!selected{background:#172338;color:#dce8f6}
            QLineEdit,QComboBox,QSpinBox{background:#111c2e;color:#e7edf7;border:1px solid #2a3a52;border-radius:8px;padding:8px 10px;selection-background-color:#0e9f91;min-height:20px}
            QLineEdit:focus,QComboBox:focus,QSpinBox:focus{border:1px solid #e6ad4b}
            QComboBox::drop-down{border:0;width:24px}
            QPushButton{background:#192941;color:#edf4ff;border:1px solid #304863;border-radius:9px;padding:9px 14px;font-weight:650}
            QPushButton:hover{background:#223752;border-color:#52718f}
            QPushButton:pressed{background:#142338;padding-top:10px;padding-bottom:8px}
            QPushButton:disabled{background:#182335;color:#65758d;border-color:#243249}
            QPushButton#primary{background:#e2a63d;color:#211809;border:1px solid #f5c66d;font-weight:750}
            QPushButton#primary:hover{background:#f0b84f;border-color:#ffda8e}
            QPushButton#secondary{background:#17263b;border-color:#2b415d;color:#d9e6f5}
            QPushButton#secondary:hover{background:#20334a;border-color:#566d88}
            QToolButton#primary{background:#e2a63d;color:#211809;border:1px solid #f5c66d;font-weight:750}
            QToolButton#primary:hover{background:#f0b84f;border-color:#ffda8e}
            QPushButton#danger{background:#7d2f42;color:#fff1f3;border-color:#a2475c}
            QPushButton#danger:hover{background:#96384e}
            QToolButton{background:#192941;color:#edf4ff;border:1px solid #304863;border-radius:9px;padding:8px 12px;font-weight:650}
            QToolButton:hover{background:#223752;border-color:#52718f}
            QFrame#tile{background:#121e30;border:1px solid #283950;border-radius:14px}
            QFrame#tile:hover{background:#1a293d;border-color:#e2a63d}
            QFrame#albumTile,QFrame#albumTile:hover{background:transparent;border:0}
            QLabel#albumName{background:transparent;color:#fff5df;font-size:19px;font-weight:800}
            QLabel#albumCount{background:transparent;color:#f0c878;font-size:13px;font-weight:650}
            QLabel#albumPreview{background:#101827;border:1px solid #886d40;border-radius:6px;color:#9aadc5;font-size:9px}
            QToolButton#albumMenu{background:#17263b;color:#fff2d6;border:1px solid #8e6b35;border-radius:9px;padding:2px;font-size:23px;font-weight:800}
            QToolButton#albumMenu:hover{background:#49391f;border-color:#f2c36e}
            QToolButton#albumMenu::menu-indicator{image:none;width:0;height:0}
            QFrame#emptyState{background:#111d2e;border:1px solid #293b53;border-radius:15px}
            QLabel#emptyIcon{font-size:31px;color:#e2a63d}
            QLabel#emptyTitle{font-size:18px;font-weight:750;color:#f1f5fb}
            QLabel#emptyMessage{font-size:13px;color:#9aadc5}
            QDialog,QMessageBox,QInputDialog{background:#101827;color:#e7edf7}
            QDialog QLabel,QMessageBox QLabel,QInputDialog QLabel{color:#dce6f2}
            QDialogButtonBox QPushButton,QMessageBox QPushButton{min-width:84px}
            QLabel#picture{background:#0c1422;border:1px solid #1e3047;border-radius:10px;color:#8ea1bb}
            QLabel#muted,QLabel#secondaryText{color:#92a3ba}
            QLabel#cardTitle{font-size:15px;font-weight:750;color:#f0f5fc}
            QLabel#cardPrice{font-size:13px;font-weight:700;color:#5de0ce}
            QFrame#collectionOverview,QFrame#priceHistory{background:#121f32;border:1px solid #2b415d;border-radius:14px}
            QLabel#metricTitle{color:#9db0c9;font-size:11px;font-weight:750;letter-spacing:1px}
            QLabel#metricValue{font-size:30px;font-weight:800;color:#ffffff}
            QLabel#metricMeta{color:#aebdd3;font-size:12px}
            QLabel#summaryPanel{background:#121f32;border:1px solid #2b415d;border-radius:12px;padding:12px 16px;font-size:14px;font-weight:650}
            QLabel#detailPrice{font-size:38px;font-weight:800;color:#ffffff}
            QLabel#detailTitle{font-size:26px;font-weight:800;color:#f0f5fc}
            QLabel#detailHeading{font-size:15px;font-weight:750;color:#b7c8dc}
            QLabel#sectionTitle{font-size:19px;font-weight:750;color:#f0f5fc}
            QMenu{background:#17263b;color:#e7edf7;border:1px solid #38516d;padding:5px}
            QMenu::item{padding:7px 24px;border-radius:5px}
            QMenu::item:selected{background:#234456;color:#ffffff}
            QScrollBar:vertical{background:#0d1726;width:11px;margin:2px;border-radius:5px}
            QScrollBar::handle:vertical{background:#70552b;min-height:28px;border-radius:5px}
            QScrollBar::handle:vertical:hover{background:#b1833e}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0}
            QScrollArea{border:0;background:transparent}
            QTableWidget{background:#111c2e;alternate-background-color:#152238;gridline-color:#263750;border:1px solid #263750;border-radius:9px}
            QHeaderView::section{background:#17263b;color:#b9c9dc;border:0;border-bottom:1px solid #2a3d56;padding:8px;font-weight:650}
            QStatusBar{background:#0a101d;color:#93a5bd;border-top:1px solid #202e42}
            QToolTip{background:#17263b;color:#eef5ff;border:1px solid #38516d;padding:5px}
        ''')
        self.refresh()
        self.refresh_wishlist()
        self.backup_timer=QTimer(self);self.backup_timer.setInterval(6*60*60*1000)
        self.backup_timer.timeout.connect(self.make_silent_backup);self.backup_timer.start()
        # Keep daily checks active while the desktop app remains open.
        self.daily_price_timer=QTimer(self)
        self.daily_price_timer.setInterval(60*60*1000)
        self.daily_price_timer.timeout.connect(self.update_prices)
        self.daily_price_timer.timeout.connect(self.refresh_stale_cardtrader_quotes)
        self.daily_price_timer.start()
        self.seed_cached_price_history()
        QTimer.singleShot(250,self.update_prices)
        QTimer.singleShot(1400,self.refresh_stale_cardtrader_quotes)

    def make_silent_backup(self):
        try:automatic_backup(self.db)
        except Exception:logging.exception('No se pudo crear la copia automatica')

    def show_about(self):
        QMessageBox.information(self,'Acerca de PokeVault',
            f'PokeVault {APP_VERSION}\nColección Pokémon TCG para Windows y Ubuntu.\n\n'
            'Precios generales orientativos de Cardmarket mediante TCGdex. Para cotizaciones por idioma puedes conectar CardTrader desde el detalle de una carta.\n'
            f'Datos: {DATA}\nCopias automáticas: {BACKUPS}\n'
            'Las referencias generales no necesitan cuenta ni clave API.')

    def export_backup(self):
        filename='pokevault_copia_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.pvbackup'
        target,_=QFileDialog.getSaveFileName(self,'Guardar copia de seguridad',str(Path.home()/filename),'Copia PokeVault (*.pvbackup)')
        if not target:return
        dest=Path(target)
        if dest.suffix.casefold()!='.pvbackup':dest=dest.with_suffix('.pvbackup')
        staged=DATA/('export_stage_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
        temporary=dest.with_name(dest.name+'.tmp')
        try:
            backup=sqlite3.connect(str(staged))
            try:self.db.backup(backup)
            finally:backup.close()
            attachments=[]
            cache_root=CACHE.resolve()
            for table in ('cards','wishlist'):
                for row_id,image in self.db.execute(f"SELECT id,image FROM {table} WHERE COALESCE(image,'')<>''").fetchall():
                    source=Path(image)
                    try:source.resolve().relative_to(cache_root)
                    except (OSError,ValueError):continue
                    if not source.is_file():continue
                    suffix=source.suffix.lower()
                    if suffix not in ('.png','.jpg','.jpeg','.webp'):suffix='.img'
                    member=f'images/{table}_{int(row_id)}{suffix}'
                    attachments.append((table,int(row_id),member,source))
            image_total=sum(source.stat().st_size for _,_,_,source in attachments)
            if image_total>512*1024*1024:raise ValueError('Las fotos locales superan el límite de 512 MB para una copia portátil.')
            if staged.stat().st_size+image_total>1024*1024*1024:raise ValueError('La base de datos y sus fotos superan el límite de 1 GB para una copia portátil.')
            manifest={'format_version':1,'images':[{'table':table,'row_id':row_id,'path':member} for table,row_id,member,_ in attachments]}
            with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
                archive.write(staged,'collection.db')
                archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False).encode('utf-8'))
                for _,_,member,source in attachments:archive.write(source,member)
            temporary.replace(dest)
            QMessageBox.information(self,'Copia creada',f'Copia de seguridad guardada en:\n{dest}\nFotos locales incluidas: {len(attachments)}')
        except Exception as exc:
            QMessageBox.critical(self,'Error al exportar',str(exc))
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
        finally:
            for suffix in ('','-wal','-shm'):Path(str(staged)+suffix).unlink(missing_ok=True)

    def restore_backup(self):
        source,_=QFileDialog.getOpenFileName(self,'Seleccionar copia de seguridad',str(Path.home()),'Copias PokeVault (*.pvbackup *.db);;Todos los archivos (*)')
        if not source:return
        staged_path=DATA/('restore_stage_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.db')
        staged_db=None;archived_images=[]
        try:
            if Path(source).resolve()==DB.resolve():raise ValueError('Esta es la base de datos activa.')
            if Path(source).suffix.casefold()=='.pvbackup':
                with zipfile.ZipFile(source,'r') as archive:
                    infos=archive.infolist();names=[info.filename for info in infos]
                    if names.count('collection.db')!=1 or names.count('manifest.json')!=1:
                        raise ValueError('La copia PokeVault debe contener una base de datos y un manifiesto únicos.')
                    if sum(info.file_size for info in infos)>1024*1024*1024:
                        raise ValueError('La copia supera el límite de 1 GB.')
                    manifest_info=next(info for info in infos if info.filename=='manifest.json')
                    if manifest_info.file_size>2*1024*1024:raise ValueError('El manifiesto de la copia es demasiado grande.')
                    manifest=json.loads(archive.read('manifest.json').decode('utf-8'))
                    if manifest.get('format_version')!=1 or not isinstance(manifest.get('images'),list):
                        raise ValueError('El formato de la copia PokeVault no es compatible.')
                    seen=set();image_total=0
                    for item in manifest['images']:
                        if not isinstance(item,dict):raise ValueError('La lista de fotos de la copia no es válida.')
                        table=item.get('table');row_id=int(item.get('row_id',0));member=item.get('path')
                        match=re.fullmatch(r'images/(cards|wishlist)_(\d+)\.(?:png|jpg|jpeg|webp|img)',str(member or ''))
                        if table not in ('cards','wishlist') or row_id<1 or not match or match.group(1)!=table or int(match.group(2))!=row_id or member in seen or names.count(member)!=1:
                            raise ValueError('La copia contiene una referencia de foto no válida.')
                        seen.add(member)
                        info=next(info for info in infos if info.filename==member)
                        image_total+=info.file_size
                        if image_total>512*1024*1024:raise ValueError('Las fotos de la copia superan el límite de 512 MB.')
                        suffix=Path(member).suffix.lower()
                        image_data=archive.read(member)
                        if not QImage().loadFromData(image_data):raise ValueError('La copia contiene una foto que no se puede leer.')
                        archived_images.append((table,row_id,suffix,image_data))
                    with archive.open('collection.db','r') as input_db,open(staged_path,'wb') as staged_file:
                        shutil.copyfileobj(input_db,staged_file)
            else:
                with sqlite3.connect(f'file:{urllib.parse.quote(str(Path(source).resolve()))}?mode=ro',uri=True) as check:
                    integrity=check.execute('PRAGMA integrity_check').fetchone()[0]
                    columns={r[1] for r in check.execute('PRAGMA table_info(cards)').fetchall()}
                    required={'id','card_id','name','set_name','number','image','language','condition','variant','quantity'}
                    if integrity!='ok' or not required.issubset(columns):raise ValueError('El archivo no es una copia válida de PokeVault.')
                stage=sqlite3.connect(str(staged_path))
                try:
                    original=sqlite3.connect(source)
                    try:original.backup(stage)
                    finally:original.close()
                finally:stage.close()
            # Migrate and validate the candidate before touching the live database.
            staged_db=connect(staged_path,make_backup=False)
            integrity=staged_db.execute('PRAGMA integrity_check').fetchone()[0]
            if integrity!='ok':raise ValueError('La copia no superó la comprobación de integridad de SQLite.')
            for table,row_id,_,_ in archived_images:
                if not staged_db.execute(f'SELECT 1 FROM {table} WHERE id=?',(row_id,)).fetchone():
                    raise ValueError('Una foto de la copia no corresponde a ninguna carta de la base de datos.')
            reply=QMessageBox.question(self,'Restaurar colección','Se sustituirá tu colección actual por la copia seleccionada.\nSe guardará automáticamente una copia de seguridad de la colección actual. ¿Continuar?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
            if reply!=QMessageBox.StandardButton.Yes:return
            for table,row_id,suffix,data in archived_images:
                digest=hashlib.sha256(data).hexdigest()
                image_path=CACHE/('restored_'+digest+suffix)
                if not image_path.exists():
                    temporary=image_path.with_name(image_path.name+'.tmp')
                    temporary.write_bytes(data);temporary.replace(image_path)
                staged_db.execute(f'UPDATE {table} SET image=? WHERE id=?',(str(image_path),row_id))
            staged_db.commit()
            safety=DATA/('collection_antes_restaurar_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
            backup=sqlite3.connect(str(safety))
            try:self.db.backup(backup)
            finally:backup.close()
            staged_db.backup(self.db)
            self.db.commit();self.collection_stack.setCurrentIndex(0);self.refresh()
            self.update_prices()
            QMessageBox.information(self,'Restauración completada',f'Colección restaurada.\nCopia de seguridad previa en:\n{safety}')
        except Exception as exc:QMessageBox.critical(self,'Error al restaurar',str(exc))
        finally:
            if staged_db:
                try:staged_db.close()
                except Exception:pass
            for suffix in ('','-wal','-shm'):Path(str(staged_path)+suffix).unlink(missing_ok=True)

    def eventFilter(self,obj,event):
        if event.type()==event.Type.Resize:
            if obj is self.search_scroll.viewport():self.reflow(self.gallery_layout,self.search_tiles,230,self.search_scroll)
            if obj is self.collection_scroll.viewport():self.reflow(self.collection_layout,self.owned_tiles,250,self.collection_scroll)
            if obj is self.wish_scroll.viewport():self.reflow(self.wish_layout,self.wish_tiles,250,self.wish_scroll)
            if obj is self.album_scroll.viewport():self.reflow(self.album_layout,self.album_tiles,280,self.album_scroll)
        return super().eventFilter(obj,event)

    def reflow(self,layout,tiles,width,scroll):
        available=max(1,scroll.viewport().width()-24)
        cols=max(1,(available+layout.spacing())//(width+layout.spacing()))
        while layout.count():layout.takeAt(0)
        for i,tile in enumerate(tiles):layout.addWidget(tile,i//cols,i%cols)

    def images(self,entries,targets,generation=None,collection=False,album=False):
        worker=ImageFetch(list(dict(entries).items()))
        def valid():
            current=self.album_generation if album else self.collection_generation if collection else self.generation
            return generation is None or generation==current
        def received(cid,data):
            if not valid():return
            for target in targets.get(cid,[]):
                if album:target[0].set_preview_image(target[1],data)
                else:target.set_image(data)
        def failed(cid,message):
            if not valid():return
            if not album:
                for target in targets.get(cid,[]):target.set_missing(message)
        worker.received.connect(received);worker.failed.connect(failed)
        worker.finished.connect(lambda:self.image_workers.remove(worker) if worker in self.image_workers else None)
        self.image_workers.append(worker);worker.start()

    def closeEvent(self,event):
        if getattr(self,'_close_ready',False):
            self.db.close();super().closeEvent(event);return
        event.ignore()
        if getattr(self,'_closing',False):return
        self._closing=True
        self.cardtrader_batch_active=False;self.cardtrader_batch_queue.clear();self.cardtrader_individual_queue.clear();self.price_queue.clear()
        self.setEnabled(False)
        if hasattr(self,'statusBar'):self.statusBar().showMessage('Cerrando con seguridad: esperando a que terminen las consultas en curso…')
        running=[w for w in ([self.price_worker,self.worker,self.species_worker,self.set_worker,self.set_cards_worker]+self.image_workers+self.market_auto_workers) if w and w.isRunning()]
        for worker in running:worker.requestInterruption()
        QTimer.singleShot(100,self.finish_close_when_workers_stop)

    def finish_close_when_workers_stop(self):
        running=[w for w in ([self.price_worker,self.worker,self.species_worker,self.set_worker,self.set_cards_worker]+self.image_workers+self.market_auto_workers) if w and w.isRunning()]
        if running:
            QTimer.singleShot(250,self.finish_close_when_workers_stop)
            return
        try:self.make_silent_backup()
        except Exception:logging.exception('Fallo en backup de cierre')
        self._close_ready=True
        self.close()


if __name__=='__main__':
    def exception_hook(typ,value,tb):
        logging.error('Error no controlado',exc_info=(typ,value,tb))
        QMessageBox.critical(None,'Error en PokeVault',f'Se ha producido un error. Consulta el registro en {DATA / "pokevault.log"}\n\n{value}')
    sys.excepthook=exception_hook
    app=QApplication(sys.argv);w=Window();w.show();sys.exit(app.exec())
