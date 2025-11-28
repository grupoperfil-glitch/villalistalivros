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
# Definição das Séries e suas Turmas permitidas
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

# Regras de Quantidade (Cotas)
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

            # --- MIGRATION (AUTO-CORREÇÃO) ---
            updated = False
            # 1. Garante Categoria nos Itens
            if "books" in json_data:
                for item in json_data["books"]:
                    if "category" not in item:
                        item["category"] = "Livro" # Legado vira Livro
                        updated = True
            
            # 2. Garante Categoria nas Reservas
            if "reservations" in json_data:
                for i, res in enumerate(json_data["reservations"]):
                    if "reservation_id" not in res:
                        clean_name = str(res.get('student_name', 'aluno')).replace(" ", "")
                        res["reservation_id"] = f"legacy_{i}_{clean_name}"
                    if "class_name" not in res:
                        res["class_name"] = "Indefinida"
                    if "category" not in res:
                        res["category"] = "Livro" # Assume livro para legados
            
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

# --- GERENCIAMENTO DE SESSÃO ---
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = "login" # login, menu, books, toys

def login_family(parent, student, grade, class_name):
    # Validação de Turma para Grupo 1
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
        
        # Resumo das Reservas
        st.divider()
        st.markdown("#### 📋 Suas Reservas Atuais")
        my_res = [r for r in data_cache.get('reservations', []) if r['student_name'] == user['student'] and r['parent_name'] == user['parent']]
        
        if my_res:
            df_res = pd.DataFrame(my_res)
            st.dataframe(
                df_res[['category', 'book_title', 'timestamp']],
                column_config={"category": "Tipo", "book_title": "Item", "timestamp": "Data"},
                hide_index=True,
                use_container_width=True
            )
        else:
            st.caption("Nenhuma reserva realizada ainda.")

    # ---------------------------------------------------------
    # TELA 3: RESERVA (LIVROS OU BRINQUEDOS)
    # ---------------------------------------------------------
    elif st.session_state.page in ["view_books", "view_toys"]:
        user = st.session_state.user
        is_book_mode = (st.session_state.page == "view_books")
        
        # Configuração do Modo
        target_categories = ["Livro"] if is_book_mode else ["Jogo", "Brinquedo"]
        title_page = "Livros de Literatura" if is_book_mode else "Jogos e Brinquedos"
        
        # Header com Voltar
        c_back, c_title, c_out = st.columns([1, 4, 1])
        if c_back.button("⬅️ Voltar ao Menu"): go_to_menu()
        c_title.markdown(f"<h2 style='text-align:center'>{title_page}</h2>", unsafe_allow_html=True)
        if c_out.button("Sair"): logout()

        # Dados Frescos
        data, sha = db.get_data()

        # Contagem de Cotas
        my_reservations = [r for r in data.get('reservations', []) if r['student_name'] == user['student'] and r['parent_name'] == user['parent']]
        
        counts = {"Livro": 0, "Jogo": 0, "Brinquedo": 0}
        for r in my_reservations:
            cat = r.get('category', 'Livro')
            counts[cat] = counts.get(cat, 0) + 1

        limits = LIMITES_RESERVA[user['segment']]
        
        # Barra de Progresso das Cotas
        st.write("---")
        cols_quota = st.columns(len(target_categories))
        for idx, cat in enumerate(target_categories):
            current = counts[cat]
            limit = limits[cat]
            cols_quota[idx].metric(f"Seus {cat}s", f"{current} / {limit}", delta_color="off")
            if current >= limit:
                cols_quota[idx].success(f"Você já escolheu todos os {cat}s necessários!")

        st.divider()

        # Filtro de Itens Disponíveis
        all_items = data.get('books', []) # Nota: chave no JSON continua 'books' para itens em geral
        
        # Filtra por Série, Turma e Categorias da Tela
        visible_items = [
            b for b in all_items 
            if b['grade'] == user['grade'] 
            and b.get('class_name') == user['class_name']
            and b.get('category', 'Livro') in target_categories
        ]
        
        available_items = [b for b in visible_items if b['available']]

        if not available_items:
            if not visible_items:
                st.warning(f"Não há itens cadastrados para {user['grade']} Turma {user['class_name']} nesta categoria.")
            else:
                st.warning("⚠️ Todos os itens disponíveis já foram reservados.")
        else:
            # Grid de exibição
            for item in available_items:
                cat = item.get('category', 'Livro')
                
                # Checa se o usuário já atingiu o limite para ESTA categoria específica
                can_reserve = counts[cat] < limits[cat]
                
                with st.container(border=True):
                    c_icon, c_txt, c_act = st.columns([0.5, 3, 1.5])
                    
                    icon = "📚" if cat == "Livro" else "🎲" if cat == "Jogo" else "🧸"
                    c_icon.markdown(f"### {icon}")
                    
                    with c_txt:
                        st.markdown(f"**{item['title']}**")
                        st.caption(f"Tipo: {cat} | Cód: {item['id']}")
                    
                    with c_act:
                        st.write("") 
                        if can_reserve:
                            if st.button(f"RESERVAR", key=f"btn_{item['id']}", type="primary"):
                                item_index = next((i for i, b in enumerate(data['books']) if b['id'] == item['id']), -1)
                                
                                # Verifica novamente atômico
                                if item_index != -1 and data['books'][item_index]['available']:
                                    # Atualiza
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
                                    st.error("Item já reservado.")
                                    time.sleep(2)
                                    st.rerun()
                        else:
                            st.button(f"Limite Atingido", key=f"dis_{item['id']}", disabled=True)

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

        # --- ABA 1: CADASTRO (COM LOTE) ---
        with tab1:
            st.markdown("### Cadastro de Itens")
            
            mode = st.radio("Modo de Cadastro", ["Individual", "Em Lote (Vários)"], horizontal=True)
            
            if mode == "Individual":
                with st.form("add_single"):
                    c_cat, c_title = st.columns([1, 3])
                    cat = c_cat.selectbox("Categoria", CATEGORIAS)
                    title = c_title.text_input("Nome do Item")
                    
                    c_grade, c_class = st.columns(2)
                    grade_sel = c_grade.selectbox("Série", SERIES_LISTA)
                    class_sel = c_class.selectbox("Turma", TURMAS_LISTA)
                    
                    if st.form_submit_button("Salvar Item"):
                        new_id = int(time.time())
                        new_item = {
                            "id": new_id,
                            "category": cat,
                            "title": title,
                            "grade": grade_sel,
                            "class_name": class_sel,
                            "available": True,
                            "reserved_by": None,
                            "reserved_student": None
                        }
                        if 'books' not in data: data['books'] = []
                        data['books'].append(new_item)
                        if db.update_data(data, sha, f"Admin add: {title}"):
                            st.success("Item cadastrado!")
                            time.sleep(1)
                            st.rerun()

            else: # Modo Lote
                st.info("Formato: Nome do Item; Série; Turma (Um por linha). A categoria selecionada abaixo será aplicada a todos.")
                cat_batch = st.selectbox("Categoria para o Lote", CATEGORIAS)
                batch_text = st.text_area("Cole aqui a lista (Ex: Banco Imobiliário; Grupo 5; A)")
                
                if st.button("Processar Lote"):
                    lines = batch_text.strip().split('\n')
                    added_count = 0
                    if 'books' not in data: data['books'] = []
                    
                    for line in lines:
                        parts = line.split(';')
                        if len(parts) >= 3:
                            t = parts[0].strip()
                            g = parts[1].strip()
                            c = parts[2].strip()
                            
                            # Validação básica
                            if g in SERIES_LISTA and c in TURMAS_LISTA:
                                new_item = {
                                    "id": int(time.time()) + added_count, # Hack p/ IDs unicos no loop
                                    "category": cat_batch,
                                    "title": t,
                                    "grade": g,
                                    "class_name": c,
                                    "available": True,
                                    "reserved_by": None,
                                    "reserved_student": None
                                }
                                data['books'].append(new_item)
                                added_count += 1
                    
                    if added_count > 0:
                        if db.update_data(data, sha, f"Batch add: {added_count} items"):
                            st.success(f"{added_count} itens cadastrados com sucesso!")
                            time.sleep(2)
                            st.rerun()
                    else:
                        st.error("Nenhum item válido encontrado ou formato incorreto.")

        # --- ABA 2: RESERVAS COM FILTROS ---
        with tab2:
            st.markdown("### Gerenciar Reservas")
            
            c_f1, c_f2, c_f3 = st.columns(3)
            f_cat = c_f1.selectbox("Filtro Categoria", ["Todas"] + CATEGORIAS, key="f_res_cat")
            f_grade = c_f2.selectbox("Filtro Série", ["Todas"] + SERIES_LISTA, key="f_res_grade")
            f_class = c_f3.selectbox("Filtro Turma", ["Todas"] + TURMAS_LISTA, key="f_res_class")
            
            reservations = data.get('reservations', [])
            
            # Aplica Filtros
            filtered_res = []
            for r in reservations:
                match_cat = (f_cat == "Todas") or (r.get('category', 'Livro') == f_cat)
                match_grade = (f_grade == "Todas") or (r.get('grade') == f_grade)
                match_class = (f_class == "Todas") or (r.get('class_name') == f_class)
                
                if match_cat and match_grade and match_class:
                    filtered_res.append(r)
            
            st.caption(f"Mostrando {len(filtered_res)} reservas.")

            if not filtered_res:
                st.info("Nenhuma reserva encontrada com estes filtros.")
            else:
                for res in filtered_res:
                    res_id = res.get('reservation_id')
                    label = f"{res.get('category', 'Item')} | {res.get('book_title')} -> {res.get('student_name')}"
                    
                    with st.expander(label):
                        c_det, c_canc = st.columns([3, 1])
                        c_det.write(f"**Data:** {res.get('timestamp')}")
                        c_det.write(f"**Responsável:** {res.get('parent_name')}")
                        c_det.write(f"**Local:** {res.get('grade')} - Turma {res.get('class_name')}")
                        
                        if c_canc.button("Cancelar", key=f"del_{res_id}"):
                            # Libera item
                            for item in data['books']:
                                match = False
                                # Tenta pelo ID (novo) ou Título (legado)
                                if 'book_id' in res and item['id'] == res['book_id']: match = True
                                elif item['title'] == res['book_title'] and item['reserved_by'] == res['parent_name']: match = True
                                
                                if match:
                                    item['available'] = True
                                    item['reserved_by'] = None
                                    item['reserved_student'] = None
                                    break
                            
                            data['reservations'] = [r for r in data['reservations'] if r.get('reservation_id') != res_id]
                            if db.update_data(data, sha, "Cancelamento Admin"):
                                st.success("Cancelado!")
                                time.sleep(1)
                                st.rerun()

        # --- ABA 3: RELATÓRIOS ---
        with tab3:
            st.markdown("### Lista de Conferência")
            c1, c2, c3 = st.columns(3)
            sel_cat = c1.selectbox("Categoria", ["Todas"] + CATEGORIAS, key="rep_cat")
            sel_grade = c2.selectbox("Série", SERIES_LISTA, key="rep_grade")
            sel_class = c3.selectbox("Turma", TURMAS_LISTA, key="rep_class")
            
            if st.button("Gerar Lista"):
                filtered = [
                    r for r in data.get('reservations', []) 
                    if r.get('grade') == sel_grade 
                    and r.get('class_name') == sel_class
                    and (sel_cat == "Todas" or r.get('category', 'Livro') == sel_cat)
                ]
                
                if filtered:
                    df = pd.DataFrame(filtered)
                    cols_map = {"category": "Tipo", "student_name": "Aluno", "parent_name": "Responsável", "book_title": "Item", "timestamp": "Data"}
                    existing = [c for c in cols_map.keys() if c in df.columns]
                    st.dataframe(df[existing].rename(columns=cols_map), hide_index=True, use_container_width=True)
                else:
                    st.warning("Nenhum dado encontrado.")

        # --- ABA 4: ESTOQUE ---
        with tab4:
            st.markdown("### Gerenciar Estoque")
            
            cf1, cf2, cf3 = st.columns(3)
            fg_cat = cf1.selectbox("Categoria", ["Todas"] + CATEGORIAS, key="est_cat")
            fg_grade = cf2.selectbox("Série", ["Todas"] + SERIES_LISTA, key="est_grade")
            fg_class = cf3.selectbox("Turma", ["Todas"] + TURMAS_LISTA, key="est_class")
            
            all_items = data.get('books', [])
            
            filtered_items = []
            for item in all_items:
                m_cat = (fg_cat == "Todas") or (item.get('category', 'Livro') == fg_cat)
                m_grade = (fg_grade == "Todas") or (item.get('grade') == fg_grade)
                m_class = (fg_class == "Todas") or (item.get('class_name') == fg_class)
                
                if m_cat and m_grade and m_class:
                    filtered_items.append(item)
            
            filtered_items.sort(key=lambda x: (x.get('grade',''), x.get('class_name',''), x.get('title','')))
            st.caption(f"Itens encontrados: {len(filtered_items)}")
            
            for item in filtered_items:
                status_icon = "🟢" if item['available'] else "🔴"
                cat_icon = "📚" if item.get('category') == "Livro" else "🎲"
                
                label = f"{status_icon} {cat_icon} {item['title']} | {item['grade']} {item.get('class_name', '-')}"
                
                with st.expander(label):
                    with st.form(key=f"edit_{item['id']}"):
                        c_e1, c_e2 = st.columns([1, 3])
                        new_cat = c_e1.selectbox("Categoria", CATEGORIAS, index=CATEGORIAS.index(item.get('category', 'Livro')))
                        new_title = c_e2.text_input("Título", value=item['title'])
                        
                        c_e3, c_e4 = st.columns(2)
                        # Index safe finding
                        curr_g = item['grade'] if item['grade'] in SERIES_LISTA else SERIES_LISTA[0]
                        curr_c = item.get('class_name', 'A') if item.get('class_name') in TURMAS_LISTA else 'A'
                        
                        new_grade = c_e3.selectbox("Série", SERIES_LISTA, index=SERIES_LISTA.index(curr_g))
                        new_class = c_e4.selectbox("Turma", TURMAS_LISTA, index=TURMAS_LISTA.index(curr_c))
                        
                        if st.form_submit_button("💾 Atualizar"):
                            item['category'] = new_cat
                            item['title'] = new_title
                            item['grade'] = new_grade
                            item['class_name'] = new_class
                            db.update_data(data, sha, f"Edit: {item['title']}")
                            st.success("Salvo!")
                            time.sleep(1)
                            st.rerun()
                    
                    if st.button("🗑️ Excluir", key=f"del_est_{item['id']}"):
                        if not item['available']:
                            st.error("Item reservado. Cancele a reserva antes.")
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
                        st.success("Senha alterada! Faça login novamente.")
                        logout()
                    else:
                        st.error("Erro na senha.")

if __name__ == "__main__":
    main()
