import streamlit as st
import json
import time
from datetime import datetime
from github import Github, GithubException
import pandas as pd

# --- CONFIGURAÇÃO DA PÁGINA E CORES ---
st.set_page_config(
    page_title="Reserva de Material Pedagógico - Escola Villa Criar",
    page_icon="🎒",
    layout="wide"
)

# --- ESTILIZAÇÃO CSS (IDENTIDADE VILLA CRIAR) ---
st.markdown("""
    <style>
    /* Botão Primário - Laranja */
    div.stButton > button:first-child {
        background-color: #F26522;
        color: white;
        border: none;
        font-weight: bold;
    }
    div.stButton > button:first-child:hover {
        background-color: #D1490E;
        color: white;
    }
    /* Botão Secundário (Cancelar) - Vermelho Claro */
    .cancel-btn {
        border: 1px solid #ff4b4b;
        color: #ff4b4b;
    }
    /* Abas Selecionadas - Azul Petróleo */
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        color: #F26522 !important;
        border-top-color: #F26522 !important;
    }
    /* Cards de Menu */
    .menu-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        border: 2px solid #ddd;
        transition: 0.3s;
        cursor: pointer;
    }
    .menu-card:hover {
        border-color: #F26522;
        background-color: #fff;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    }
    h1, h2, h3 { color: #006680; }
    </style>
""", unsafe_allow_html=True)

# --- CONSTANTES E REGRAS ---
REGRAS_TURMAS = {
    "Grupo 1": ["D"],
    "Grupo 2": ["A", "B", "D"],
    "Grupo 3": ["A", "B", "D"],
    "Grupo 4": ["A", "B", "D"],
    "Grupo 5": ["A", "B", "D"],
    "1º Ano": ["A", "B", "D"],
    "2º Ano": ["A", "B", "D"],
    "3º Ano": ["A", "B", "D"],
    "4º Ano": ["A", "B", "D"]
}

SERIES_LISTA = list(REGRAS_TURMAS.keys())
TURMAS_LISTA = ["A", "B", "D"]
CATEGORIAS = ["Livro", "Jogo", "Brinquedo"]

LIMITES_RESERVA = {
    "Infantil": {"Livro": 3, "Jogo": 1, "Brinquedo": 1},
    "Fundamental": {"Livro": 4, "Jogo": 1, "Brinquedo": 1}
}

def get_segmento(serie):
    if "Grupo" in serie:
        return "Infantil"
    return "Fundamental"

# --- CLASSE DE CONEXÃO COM GITHUB ---
class GitHubConnection:
    def __init__(self):
        try:
            self.token = st.secrets["GH_TOKEN"]
            self.repo_name = st.secrets["GH_REPO"]
            self.file_path = st.secrets["GH_PATH"]
            self.branch = st.secrets["GH_BRANCH"]
            self.g = Github(self.token)
            self.repo = self.g.get_repo(self.repo_name)
        except Exception as e:
            st.error(f"❌ Erro crítico na configuração dos Segredos: {e}")
            st.stop()

    def get_data(self):
        file_sha = None
        try:
            contents = self.repo.get_contents(self.file_path, ref=self.branch)
            file_sha = contents.sha
            
            if contents.decoded_content:
                json_data = json.loads(contents.decoded_content.decode("utf-8"))
            else:
                json_data = {"books": [], "reservations": [], "admin_config": {"password": "villa123"}}

            # --- MIGRATION ---
            updated = False
            if "books" in json_data:
                for item in json_data["books"]:
                    if "category" not in item:
                        item["category"] = "Livro"
                        updated = True
            
            if "reservations" in json_data:
                for i, res in enumerate(json_data["reservations"]):
                    if "reservation_id" not in res:
                        clean_name = str(res.get('student_name', 'aluno')).replace(" ", "")
                        res["reservation_id"] = f"legacy_{i}_{clean_name}"
                    if "class_name" not in res:
                        res["class_name"] = "Indefinida"
                    if "category" not in res:
                        res["category"] = "Livro"
            
            if "admin_config" not in json_data:
                json_data["admin_config"] = {"password": "villa123"}
                
            return json_data, file_sha

        except Exception as e:
            return {
                "admin_config": {"password": "villa123"},
                "books": [], 
                "reservations": []
            }, file_sha

    def update_data(self, new_data, sha, commit_message="Update via Streamlit"):
        try:
            json_content = json.dumps(new_data, indent=2, ensure_ascii=False)
            if sha:
                self.repo.update_file(self.file_path, commit_message, json_content, sha, branch=self.branch)
            else:
                self.repo.create_file(self.file_path, commit_message, json_content, branch=self.branch)
            return True
        except GithubException as e:
            st.error(f"❌ Erro ao salvar no GitHub: {e}")
            return False

# --- FUNÇÃO AUXILIAR DE CANCELAMENTO ---
def process_cancellation(db, data, sha, item_id, user_parent_name, reservation_id=None):
    item_found = False
    for item in data['books']:
        if item['id'] == item_id:
            if item['reserved_by'] == user_parent_name or user_parent_name == "ADMIN_OVERRIDE":
                item['available'] = True
                item['reserved_by'] = None
                item['reserved_student'] = None
                item_found = True
            break
    
    if reservation_id:
        data['reservations'] = [r for r in data['reservations'] if r.get('reservation_id') != reservation_id]
    else:
        data['reservations'] = [r for r in data['reservations'] if r.get('book_id') != item_id]

    if item_found:
        return db.update_data(data, sha, f"Cancelamento: {item_id}")
    return False

# --- GERENCIAMENTO DE SESSÃO ---
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = "login"

def login_family(parent, student, grade, class_name):
    turmas_permitidas = REGRAS_TURMAS.get(grade, [])
    if class_name not in turmas_permitidas:
        st.error(f"A série {grade} não possui a Turma {class_name}. Turmas permitidas: {', '.join(turmas_permitidas)}")
        return

    if parent and student and grade and class_name:
        st.session_state.user = {
            'type': 'family',
            'parent': parent,
            'student': student,
            'grade': grade,
            'class_name': class_name,
            'segment': get_segmento(grade)
        }
        st.session_state.page = "menu"
        st.rerun()
    else:
        st.warning("Preencha todos os campos.")

def login_admin(password_input, db_data):
    stored_password = db_data.get("admin_config", {}).get("password", "villa123")
    if password_input == stored_password:
        st.session_state.user = {'type': 'admin'}
        st.session_state.page = "admin"
        st.rerun()
    else:
        st.error("Senha incorreta.")

def logout():
    st.session_state.user = None
    st.session_state.page = "login"
    st.rerun()

def go_to_menu():
    st.session_state.page = "menu"
    st.rerun()

# --- INTERFACE PRINCIPAL ---
def main():
    db = GitHubConnection()
    data_cache, sha_cache = db.get_data()

    # Cabeçalho
    st.markdown("""
    <div style='background: linear-gradient(135deg, #006680 0%, #F26522 100%); padding: 25px; border-radius: 12px; color: white; text-align: center; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
        <h1 style='margin:0; font-size: 2.2em; color: white;'>Reserva de Material Pedagógico</h1>
        <p style='margin-top:5px; font-size: 1.1em; opacity: 0.9;'>Escola Villa Criar</p>
    </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # TELA 1: LOGIN
    # ---------------------------------------------------------
    if st.session_state.page == "login":
        c1, c2 = st.columns(2, gap="large")
        
        with c1:
            st.markdown("### 👨‍👩‍👧‍👦 Acesso Família")
            with st.form("login_family"):
                parent_in = st.text_input("Nome do Responsável")
                student_in = st.text_input("Nome do Estudante")
                cc1, cc2 = st.columns(2)
                grade_in = cc1.selectbox("Série do Aluno", SERIES_LISTA)
                class_in = cc2.selectbox("Turma", TURMAS_LISTA)
                
                st.markdown("<br>", unsafe_allow_html=True)
                if st.form_submit_button("Entrar no Sistema", type="primary"):
                    login_family(parent_in, student_in, grade_in, class_in)

        with c2:
            st.markdown("### 🛡️ Acesso Administrativo")
            with st.form("login_admin"):
                pass_in = st.text_input("Senha Admin", type="password")
                st.markdown("<br>", unsafe_allow_html=True)
                if st.form_submit_button("Acessar Painel"):
                    login_admin(pass_in, data_cache)

    # ---------------------------------------------------------
    # TELA 2: MENU DE ESCOLHA (FAMÍLIA)
    # ---------------------------------------------------------
    elif st.session_state.page == "menu" and st.session_state.user['type'] == 'family':
        user = st.session_state.user
        
        c_info, c_logout = st.columns([4,1])
        c_info.info(f"Bem-vindo, **{user['parent']}**! Aluno: {user['student']} ({user['grade']} {user['class_name']})")
        if c_logout.button("Sair"): logout()

        st.markdown("### O que deseja reservar agora?")
        
        col_book, col_toys = st.columns(2)
        
        with col_book:
            st.markdown("""
            <div class="menu-card">
                <h2 style='margin:0;'>📚</h2>
                <h3>Livros de Literatura</h3>
                <p>Escolha os livros para o ano letivo.</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Acessar Livros", use_container_width=True):
                st.session_state.page = "view_books"
                st.rerun()

        with col_toys:
            st.markdown("""
            <div class="menu-card">
                <h2 style='margin:0;'>🎲</h2>
                <h3>Jogos e Brinquedos</h3>
                <p>Escolha o jogo e o brinquedo pedagógico.</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Acessar Jogos/Brinquedos", use_container_width=True):
                st.session_state.page = "view_toys"
                st.rerun()
        
        st.divider()
        st.markdown("#### 📋 Suas Reservas Atuais")
        
        my_res = [r for r in data_cache.get('reservations', []) if r['student_name'] == user['student'] and r['parent_name'] == user['parent']]
        
        if not my_res:
            st.caption("Nenhuma reserva realizada ainda.")
        else:
            c_h1, c_h2, c_h3, c_h4 = st.columns([1, 4, 2, 1])
            c_h1.markdown("**Tipo**")
            c_h2.markdown("**Item**")
            c_h3.markdown("**Data**")
            c_h4.markdown("**Ação**")
            st.divider()

            for res in my_res:
                c1, c2, c3, c4 = st.columns([1, 4, 2, 1])
                icon = "📚" if res.get('category') == "Livro" else "🎲"
                
                c1.write(f"{icon} {res.get('category', '-')}")
                c2.write(res.get('book_title'))
                c3.write(res.get('timestamp'))
                
                if c4.button("❌ Cancelar", key=f"cancel_menu_{res.get('reservation_id')}"):
                    data, sha = db.get_data()
                    success = process_cancellation(
                        db, data, sha, 
                        item_id=res.get('book_id'), 
                        user_parent_name=user['parent'], 
                        reservation_id=res.get('reservation_id')
                    )
                    if success:
                        st.success("Reserva removida!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Erro ao cancelar.")
                st.markdown("<hr style='margin: 5px 0'>", unsafe_allow_html=True)

    # ---------------------------------------------------------
    # TELA 3: RESERVA (LIVROS OU BRINQUEDOS)
    # ---------------------------------------------------------
    elif st.session_state.page in ["view_books", "view_toys"]:
        user = st.session_state.user
        is_book_mode = (st.session_state.page == "view_books")
        
        target_categories = ["Livro"] if is_book_mode else ["Jogo", "Brinquedo"]
        title_page = "Livros de Literatura" if is_book_mode else "Jogos e Brinquedos"
        
        c_back, c_title, c_out = st.columns([1, 4, 1])
        if c_back.button("⬅️ Voltar ao Menu"): go_to_menu()
        c_title.markdown(f"<h2 style='text-align:center'>{title_page}</h2>", unsafe_allow_html=True)
        if c_out.button("Sair"): logout()

        data, sha = db.get_data()

        my_reservations = [r for r in data.get('reservations', []) if r['student_name'] == user['student'] and r['parent_name'] == user['parent']]
        
        counts = {"Livro": 0, "Jogo": 0, "Brinquedo": 0}
        for r in my_reservations:
            cat = r.get('category', 'Livro')
            counts[cat] = counts.get(cat, 0) + 1

        limits = LIMITES_RESERVA[user['segment']]
        
        st.write("---")
        cols_quota = st.columns(len(target_categories))
        for idx, cat in enumerate(target_categories):
            current = counts[cat]
            limit = limits[cat]
            cols_quota[idx].metric(f"Seus {cat}s", f"{current} / {limit}", delta_color="off")
            if current >= limit:
                cols_quota[idx].success(f"Você já escolheu todos os {cat}s necessários!")

        st.divider()

        all_items = data.get('books', [])
        
        # --- ALTERAÇÃO AQUI: FILTRO DE VISIBILIDADE ---
        # Só mostra itens que:
        # 1. Pertencem a série/turma/categoria
        # 2. E (Estão Disponíveis OU São Minhas Reservas)
        # Itens reservados por OUTROS não entram nesta lista.
        visible_items = [
            b for b in all_items 
            if b['grade'] == user['grade'] 
            and b.get('class_name') == user['class_name']
            and b.get('category', 'Livro') in target_categories
            and (b['available'] or (b.get('reserved_by') == user['parent'] and b.get('reserved_student') == user['student']))
        ]
        
        # Ordenação: Disponíveis primeiro
        visible_items.sort(key=lambda x: x['available'], reverse=True)

        if not visible_items:
            # Se a lista estiver vazia, significa que tudo foi reservado por outros
            st.info(f"No momento, não há opções disponíveis para reserva nesta categoria.")
        else:
            for item in visible_items:
                cat = item.get('category', 'Livro')
                is_mine = (item.get('reserved_by') == user['parent'] and item.get('reserved_student') == user['student'])
                
                with st.container(border=True):
                    c_icon, c_txt, c_act = st.columns([0.5, 3, 1.5])
                    
                    icon = "📚" if cat == "Livro" else "🎲" if cat == "Jogo" else "🧸"
                    c_icon.markdown(f"### {icon}")
                    
                    with c_txt:
                        st.markdown(f"**{item['title']}**")
                        st.caption(f"Tipo: {cat} | Cód: {item['id']}")
                        if is_mine:
                            st.success("✅ RESERVADO PARA VOCÊ")
                    
                    with c_act:
                        st.write("") 
                        
                        if is_mine:
                            if st.button("DESFAZER RESERVA", key=f"undo_{item['id']}", type="secondary"):
                                success = process_cancellation(
                                    db, data, sha, item['id'], user['parent']
                                )
                                if success:
                                    st.success("Item removido!")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("Erro ao remover.")
                        
                        elif item['available']:
                            can_reserve = counts[cat] < limits[cat]
                            
                            if can_reserve:
                                if st.button(f"RESERVAR", key=f"btn_{item['id']}", type="primary"):
                                    item_index = next((i for i, b in enumerate(data['books']) if b['id'] == item['id']), -1)
                                    
                                    if item_index != -1 and data['books'][item_index]['available']:
                                        data['books'][item_index]['available'] = False
                                        data['books'][item_index]['reserved_by'] = user['parent']
                                        data['books'][item_index]['reserved_student'] = user['student']
                                        
                                        new_res = {
                                            "reservation_id": int(time.time()),
                                            "book_id": item['id'],
                                            "category": cat,
                                            "parent_name": user['parent'],
                                            "student_name": user['student'],
                                            "grade": user['grade'],
                                            "class_name": user['class_name'],
                                            "book_title": item['title'],
                                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        }
                                        data['reservations'].append(new_res)

                                        if db.update_data(data, sha, f"Reserva: {item['title']}"):
                                            st.balloons()
                                            st.success("✅ Reservado!")
                                            time.sleep(1.5)
                                            st.rerun()
                                        else:
                                            st.error("Erro ao salvar.")
                                    else:
                                        st.error("Alguém reservou antes.")
                                        time.sleep(2)
                                        st.rerun()
                            else:
                                st.button(f"Limite Atingido", key=f"full_{item['id']}", disabled=True)

    # ---------------------------------------------------------
    # TELA 4: ADMINISTRAÇÃO
    # ---------------------------------------------------------
    elif st.session_state.page == "admin":
        st.success("🔒 Painel de Gestão - Villa Criar")
        if st.button("Sair"): logout()
            
        data, sha = db.get_data()
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "➕ Cadastrar Itens", 
            "📋 Reservas Realizadas", 
            "📄 Listas por Turma", 
            "📊 Estoque / Editar",
            "⚙️ Configurações"
        ])

        with tab1:
            st.markdown("### Cadastro de Itens")
            mode = st.radio("Modo de Cadastro", ["Individual", "Em Lote (Rápido)"], horizontal=True)
            
            if mode == "Individual":
                with st.form("add_single"):
                    c_cat, c_title = st.columns([1, 3])
                    cat = c_cat.selectbox("Categoria", CATEGORIAS)
                    title = c_title.text_input("Nome do Item")
                    c_grade, c_class = st.columns(2)
                    grade_sel = c_grade.selectbox("Série Destino", SERIES_LISTA)
                    class_sel = c_class.selectbox("Turma Destino", TURMAS_LISTA)
                    if st.form_submit_button("Salvar Item"):
                        new_id = int(time.time())
                        new_item = {
                            "id": new_id, "category": cat, "title": title, "grade": grade_sel, "class_name": class_sel,
                            "available": True, "reserved_by": None, "reserved_student": None
                        }
                        if 'books' not in data: data['books'] = []
                        data['books'].append(new_item)
                        if db.update_data(data, sha, f"Admin add: {title}"):
                            st.success("Item cadastrado!")
                            time.sleep(1)
                            st.rerun()

            else: 
                st.markdown("#### Configuração do Lote")
                c_b1, c_b2, c_b3 = st.columns(3)
                batch_cat = c_b1.selectbox("Categoria", CATEGORIAS)
                batch_grade = c_b2.selectbox("Série", SERIES_LISTA)
                batch_class = c_b3.selectbox("Turma", TURMAS_LISTA)
                st.info(f"Cole abaixo a lista de nomes. Cadastro: **{batch_cat} - {batch_grade} - Turma {batch_class}**")
                batch_text = st.text_area("Lista de Nomes")
                if st.button("Processar Lote Agora"):
                    lines = batch_text.strip().split('\n')
                    added_count = 0
                    if 'books' not in data: data['books'] = []
                    for line in lines:
                        name_item = line.strip()
                        if name_item:
                            new_item = {
                                "id": int(time.time()) + added_count, "category": batch_cat, "title": name_item,
                                "grade": batch_grade, "class_name": batch_class,
                                "available": True, "reserved_by": None, "reserved_student": None
                            }
                            data['books'].append(new_item)
                            added_count += 1
                    if added_count > 0:
                        if db.update_data(data, sha, f"Batch add: {added_count}"):
                            st.success(f"{added_count} cadastrados!")
                            time.sleep(2)
                            st.rerun()

        with tab2:
            st.markdown("### Gerenciar Reservas")
            c_f1, c_f2, c_f3 = st.columns(3)
            f_cat = c_f1.selectbox("Filtro Categoria", ["Todas"] + CATEGORIAS, key="f_res_cat")
            f_grade = c_f2.selectbox("Filtro Série", ["Todas"] + SERIES_LISTA, key="f_res_grade")
            f_class = c_f3.selectbox("Filtro Turma", ["Todas"] + TURMAS_LISTA, key="f_res_class")
            
            reservations = data.get('reservations', [])
            filtered_res = [r for r in reservations if 
                            ((f_cat == "Todas") or (r.get('category') == f_cat)) and
                            ((f_grade == "Todas") or (r.get('grade') == f_grade)) and
                            ((f_class == "Todas") or (r.get('class_name') == f_class))]
            
            st.caption(f"Mostrando {len(filtered_res)} reservas.")
            for res in filtered_res:
                label = f"{res.get('category', 'Item')} | {res.get('book_title')} -> {res.get('student_name')}"
                with st.expander(label):
                    c_det, c_canc = st.columns([3, 1])
                    c_det.write(f"**Resp:** {res.get('parent_name')}")
                    if c_canc.button("Cancelar", key=f"del_{res.get('reservation_id')}"):
                        process_cancellation(db, data, sha, res.get('book_id'), "ADMIN_OVERRIDE", res.get('reservation_id'))
                        st.success("Cancelado!")
                        time.sleep(1)
                        st.rerun()

        with tab3:
            st.markdown("### Lista de Conferência")
            c1, c2, c3 = st.columns(3)
            sel_cat = c1.selectbox("Categoria", ["Todas"] + CATEGORIAS, key="rep_cat")
            sel_grade = c2.selectbox("Série", SERIES_LISTA, key="rep_grade")
            sel_class = c3.selectbox("Turma", TURMAS_LISTA, key="rep_class")
            if st.button("Gerar Lista"):
                filtered = [r for r in data.get('reservations', []) if r.get('grade') == sel_grade and r.get('class_name') == sel_class and (sel_cat == "Todas" or r.get('category', 'Livro') == sel_cat)]
                if filtered:
                    df = pd.DataFrame(filtered)
                    cols_map = {"category": "Tipo", "student_name": "Aluno", "parent_name": "Responsável", "book_title": "Item", "timestamp": "Data"}
                    existing = [c for c in cols_map.keys() if c in df.columns]
                    st.dataframe(df[existing].rename(columns=cols_map), hide_index=True, use_container_width=True)
                else:
                    st.warning("Nenhum dado encontrado.")

        with tab4:
            st.markdown("### Gerenciar Estoque")
            cf1, cf2, cf3 = st.columns(3)
            fg_cat = cf1.selectbox("Categoria", ["Todas"] + CATEGORIAS, key="est_cat")
            fg_grade = cf2.selectbox("Série", ["Todas"] + SERIES_LISTA, key="est_grade")
            fg_class = cf3.selectbox("Turma", ["Todas"] + TURMAS_LISTA, key="est_class")
            
            all_items = data.get('books', [])
            filtered_items = [i for i in all_items if 
                              ((fg_cat == "Todas") or (i.get('category', 'Livro') == fg_cat)) and
                              ((fg_grade == "Todas") or (i.get('grade') == fg_grade)) and
                              ((fg_class == "Todas") or (i.get('class_name') == fg_class))]
            filtered_items.sort(key=lambda x: (x.get('grade',''), x.get('class_name',''), x.get('title','')))
            
            st.caption(f"Itens encontrados: {len(filtered_items)}")
            for item in filtered_items:
                status_icon = "🟢" if item['available'] else "🔴"
                cat_icon = "📚" if item.get('category') == "Livro" else "🎲"
                label = f"{status_icon} {cat_icon} {item['title']} | {item['grade']} {item.get('class_name', '-')}"
                with st.expander(label):
                    with st.form(key=f"edit_{item['id']}"):
                        new_cat = st.selectbox("Categoria", CATEGORIAS, index=CATEGORIAS.index(item.get('category', 'Livro')))
                        new_title = st.text_input("Título", value=item['title'])
                        if st.form_submit_button("💾 Atualizar"):
                            item['category'] = new_cat
                            item['title'] = new_title
                            db.update_data(data, sha, f"Edit: {item['title']}")
                            st.success("Salvo!")
                            time.sleep(1)
                            st.rerun()
                    if st.button("🗑️ Excluir", key=f"del_est_{item['id']}"):
                        if not item['available']:
                            st.error("Item reservado.")
                        else:
                            data['books'] = [b for b in data['books'] if b['id'] != item['id']]
                            db.update_data(data, sha, f"Del: {item['id']}")
                            st.success("Excluído.")
                            time.sleep(1)
                            st.rerun()

        with tab5:
            st.markdown("### Alterar Senha Admin")
            with st.form("pass_chg"):
                p1 = st.text_input("Nova Senha", type="password")
                p2 = st.text_input("Confirmar", type="password")
                if st.form_submit_button("Alterar"):
                    if p1 == p2 and len(p1) > 3:
                        data["admin_config"]["password"] = p1
                        db.update_data(data, sha, "Senha alterada")
                        st.success("Alterada com sucesso! Logue novamente.")
                        logout()
                    else:
                        st.error("Erro na senha.")

if __name__ == "__main__":
    main()
