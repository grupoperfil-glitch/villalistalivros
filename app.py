import streamlit as st
import json
import time
from datetime import datetime
from github import Github, GithubException
import pandas as pd
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Reserva de Material Pedagógico - Escola Villa Criar",
    page_icon="🎒",
    layout="wide"
)

# --- ESTILIZAÇÃO CSS ---
st.markdown("""
    <style>
    div.stButton > button:first-child { background-color: #F26522; color: white; border: none; font-weight: bold; }
    div.stButton > button:first-child:hover { background-color: #D1490E; color: white; }
    .cancel-btn { border: 1px solid #ff4b4b; color: #ff4b4b; }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] { color: #F26522 !important; border-top-color: #F26522 !important; }
    .menu-card { background-color: #f0f2f6; padding: 20px; border-radius: 10px; text-align: center; border: 2px solid #ddd; transition: 0.3s; cursor: pointer; }
    .menu-card:hover { border-color: #F26522; background-color: #fff; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
    h1, h2, h3 { color: #006680; }
    /* Estilo para zona de perigo */
    .danger-zone { border: 2px solid #ff4b4b; padding: 15px; border-radius: 10px; background-color: #fff5f5; }
    </style>
""", unsafe_allow_html=True)

# --- CONSTANTES E MAPEAMENTOS ---
MAP_CURSO_CSV = {
    1: "Grupo 1", 2: "Grupo 2", 3: "Grupo 3", 4: "Grupo 4", 5: "Grupo 5",
    91: "1º Ano", 92: "2º Ano", 93: "3º Ano", 94: "4º Ano"
}
MAP_TURNO_CSV = {
    "M": "Matutino", 
    "V": "Vespertino"
}

TURMAS_LISTA = ["Matutino", "Vespertino", "A", "B", "D", "Integral"]
SERIES_LISTA = ["Grupo 1", "Grupo 2", "Grupo 3", "Grupo 4", "Grupo 5", "1º Ano", "2º Ano", "3º Ano", "4º Ano"]
CATEGORIAS = ["Livro", "Jogo", "Brinquedo"]
LIMITES_RESERVA = {
    "Infantil": {"Livro": 3, "Jogo": 1, "Brinquedo": 1},
    "Fundamental": {"Livro": 4, "Jogo": 1, "Brinquedo": 1}
}

def get_segmento(serie):
    if "Grupo" in str(serie): return "Infantil"
    return "Fundamental"

# --- CLASSE GITHUB ---
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
            st.error(f"Erro Secrets: {e}"); st.stop()

    def get_data(self):
        file_sha = None
        try:
            contents = self.repo.get_contents(self.file_path, ref=self.branch)
            file_sha = contents.sha
            if contents.decoded_content:
                json_data = json.loads(contents.decoded_content.decode("utf-8"))
            else:
                json_data = {}

            if "books" not in json_data: json_data["books"] = []
            if "reservations" not in json_data: json_data["reservations"] = []
            if "students_db" not in json_data: json_data["students_db"] = []
            if "admin_config" not in json_data: json_data["admin_config"] = {"password": "villa123"}

            for item in json_data["books"]:
                if "category" not in item: item["category"] = "Livro"
            for i, res in enumerate(json_data["reservations"]):
                if "reservation_id" not in res: res["reservation_id"] = f"legacy_{i}"
                if "class_name" not in res: res["class_name"] = "Indefinida"
                if "category" not in res: res["category"] = "Livro"
            
            return json_data, file_sha
        except Exception:
            return {"admin_config": {"password": "villa123"}, "books": [], "reservations": [], "students_db": []}, file_sha

    def update_data(self, new_data, sha, msg="Update"):
        try:
            content = json.dumps(new_data, indent=2, ensure_ascii=False)
            if sha: self.repo.update_file(self.file_path, msg, content, sha, branch=self.branch)
            else: self.repo.create_file(self.file_path, msg, content, branch=self.branch)
            return True
        except Exception as e:
            st.error(f"Erro GitHub: {e}"); return False

def process_cancellation(db, data, sha, item_id, user_parent, res_id=None):
    found = False
    for i in data['books']:
        if i['id'] == item_id:
            if i['reserved_by'] == user_parent or user_parent == "ADMIN_OVERRIDE":
                i['available'] = True; i['reserved_by'] = None; i['reserved_student'] = None
                found = True
            break
    if res_id: data['reservations'] = [r for r in data['reservations'] if r.get('reservation_id') != res_id]
    else: data['reservations'] = [r for r in data['reservations'] if r.get('book_id') != item_id]
    if found: return db.update_data(data, sha, f"Cancel: {item_id}")
    return False

# --- SESSION ---
if 'user' not in st.session_state: st.session_state.user = None
if 'page' not in st.session_state: st.session_state.page = "login"
if 'login_search_triggered' not in st.session_state: st.session_state.login_search_triggered = False

def login_email(student_obj, parent_name):
    final_parent = parent_name if parent_name else student_obj.get('parent_csv', 'Responsável')
    st.session_state.user = {
        'type': 'family', 'parent': final_parent, 
        'student': student_obj['name'], 'grade': student_obj['grade'],
        'class_name': student_obj['class_name'], 'email': student_obj['email'],
        'segment': get_segmento(student_obj['grade'])
    }
    st.session_state.page = "menu"; st.rerun()

def login_admin(pwd, data):
    if pwd == data.get("admin_config", {}).get("password", "villa123"):
        st.session_state.user = {'type': 'admin'}
        st.session_state.page = "admin"; st.rerun()
    else: st.error("Senha incorreta.")

def logout(): 
    st.session_state.user = None
    st.session_state.page = "login"
    st.session_state.login_search_triggered = False
    st.rerun()

def go_menu(): st.session_state.page = "menu"; st.rerun()

# --- MAIN ---
def main():
    db = GitHubConnection()
    data, sha = db.get_data()

    st.markdown("""
    <div style='background: linear-gradient(135deg, #006680 0%, #F26522 100%); padding: 25px; border-radius: 12px; color: white; text-align: center; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);'>
        <h1 style='margin:0; font-size: 2.2em; color: white;'>Reserva de Material Pedagógico</h1>
        <p style='margin-top:5px; font-size: 1.1em; opacity: 0.9;'>Escola Villa Criar</p>
    </div>
    """, unsafe_allow_html=True)

    # LOGIN
    if st.session_state.page == "login":
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown("### 👨‍👩‍👧‍👦 Acesso Família")
            st.caption("Utilize o e-mail cadastrado na escola.")
            
            email_in = st.text_input("E-mail Cadastrado")
            if st.button("Continuar / Buscar Aluno"):
                st.session_state.login_search_triggered = True
            
            if email_in:
                s_db = data.get('students_db', [])
                found = []
                target_email = email_in.lower().strip()
                for s in s_db:
                    e1 = str(s.get('email', '')).lower().strip()
                    e2 = str(s.get('email2', '')).lower().strip()
                    if target_email and (target_email == e1 or target_email == e2):
                        found.append(s)
                
                if not found:
                    if st.session_state.login_search_triggered:
                        st.warning("E-mail não encontrado. Verifique a digitação ou contate a escola.")
                else:
                    st.success(f"Encontramos {len(found)} aluno(s)!")
                    st.markdown("---")
                    opts = {f"{s['name']} ({s['grade']} - {s['class_name']})": s for s in found}
                    sel = st.selectbox("Selecione o Aluno:", list(opts.keys()))
                    suggested_parent = opts[sel].get('parent_csv', '')
                    p_name = st.text_input("Nome do Responsável", value=suggested_parent)
                    st.write("")
                    if st.button("Entrar no Sistema", type="primary"):
                        if p_name: login_email(opts[sel], p_name)
                        else: st.error("Por favor, confirme seu nome.")

        with c2:
            st.markdown("### 🛡️ Admin")
            with st.form("adm"):
                pwd = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar"): login_admin(pwd, data)

    # MENU
    elif st.session_state.page == "menu" and st.session_state.user['type'] == 'family':
        user = st.session_state.user
        c_i, c_l = st.columns([4,1])
        c_i.info(f"Olá, **{user['parent']}**! Aluno: **{user['student']}** ({user['grade']} - {user['class_name']})")
        if c_l.button("Sair"): logout()

        c_b, c_t = st.columns(2)
        with c_b:
            st.markdown("<div class='menu-card'><h2>📚</h2><h3>Livros</h3></div>", unsafe_allow_html=True)
            if st.button("Acessar Livros", use_container_width=True):
                st.session_state.page = "view_books"; st.rerun()
        with c_t:
            st.markdown("<div class='menu-card'><h2>🎲</h2><h3>Jogos/Brinquedos</h3></div>", unsafe_allow_html=True)
            if st.button("Acessar Jogos", use_container_width=True):
                st.session_state.page = "view_toys"; st.rerun()

        st.divider(); st.markdown("#### 📋 Suas Reservas")
        my_res = [r for r in data.get('reservations', []) if str(r.get('student_name')) == str(user['student'])]
        if not my_res: st.caption("Sem reservas.")
        else:
            for r in my_res:
                c1, c2, c3, c4 = st.columns([1,4,2,1])
                icon = "📚" if r.get('category')=="Livro" else "🎲"
                c1.write(f"{icon} {r.get('category')}")
                c2.write(r.get('book_title'))
                c3.write(r.get('timestamp'))
                if c4.button("❌", key=f"c_m_{r.get('reservation_id')}"):
                    if process_cancellation(db, data, sha, r.get('book_id'), user['parent'], r.get('reservation_id')):
                        st.success("Removido!"); time.sleep(1); st.rerun()
                st.markdown("<hr style='margin:5px 0'>", unsafe_allow_html=True)

    # VIEW ITEMS
    elif st.session_state.page in ["view_books", "view_toys"]:
        user = st.session_state.user
        is_book = (st.session_state.page == "view_books")
        cats = ["Livro"] if is_book else ["Jogo", "Brinquedo"]
        
        c_b, c_t, c_o = st.columns([1,4,1])
        if c_b.button("⬅️ Voltar"): go_menu()
        c_t.markdown(f"<h2 style='text-align:center'>{'Livros' if is_book else 'Jogos e Brinquedos'}</h2>", unsafe_allow_html=True)
        if c_o.button("Sair"): logout()

        my_res = [r for r in data.get('reservations',[]) if str(r.get('student_name')) == str(user['student'])]
        counts = {c:0 for c in ["Livro","Jogo","Brinquedo"]}
        for r in my_res: counts[r.get('category','Livro')] += 1
        limits = LIMITES_RESERVA[user['segment']]

        cols = st.columns(len(cats))
        for i, c in enumerate(cats):
            cols[i].metric(f"Seus {c}s", f"{counts[c]} / {limits[c]}")
            if counts[c] >= limits[c]: cols[i].success("Completo!")

        st.divider()
        items = data.get('books', [])
        visible = [
            i for i in items 
            if i['grade'] == user['grade'] and i.get('class_name') == user['class_name']
            and i.get('category','Livro') in cats
            and (i['available'] or str(i.get('reserved_student')) == str(user['student']))
        ]
        visible.sort(key=lambda x: x['available'], reverse=True)

        if not visible: st.info(f"Sem itens disponíveis para {user['grade']} - {user['class_name']}.")
        else:
            for item in visible:
                cat = item.get('category','Livro')
                is_mine = (str(item.get('reserved_student')) == str(user['student']))
                with st.container(border=True):
                    c1, c2, c3 = st.columns([0.5, 3, 1.5])
                    c1.markdown(f"### {'📚' if cat=='Livro' else '🎲'}")
                    with c2:
                        st.markdown(f"**{item['title']}**")
                        st.caption(cat)
                        if is_mine: st.success("✅ SEU")
                    with c3:
                        st.write("")
                        if is_mine:
                            if st.button("DESFAZER", key=f"u_{item['id']}", type="secondary"):
                                if process_cancellation(db, data, sha, item['id'], user['parent']):
                                    st.success("Feito!"); time.sleep(1); st.rerun()
                        elif item['available']:
                            if counts[cat] < limits[cat]:
                                if st.button("RESERVAR", key=f"r_{item['id']}", type="primary"):
                                    idx = next((i for i, b in enumerate(data['books']) if b['id']==item['id']), -1)
                                    if idx!=-1 and data['books'][idx]['available']:
                                        data['books'][idx]['available'] = False
                                        data['books'][idx]['reserved_by'] = user['parent']
                                        data['books'][idx]['reserved_student'] = user['student']
                                        data['reservations'].append({
                                            "reservation_id": int(time.time()), "book_id": item['id'],
                                            "category": cat, "parent_name": user['parent'],
                                            "student_name": user['student'], "grade": user['grade'],
                                            "class_name": user['class_name'], "book_title": item['title'],
                                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
                                        })
                                        if db.update_data(data, sha, f"Res: {item['title']}"):
                                            st.balloons(); time.sleep(1); st.rerun()
                                    else: st.error("Perdeu!"); time.sleep(1); st.rerun()
                            else: st.button("Limite", key=f"l_{item['id']}", disabled=True)

    # ADMIN
    elif st.session_state.page == "admin":
        st.success("Admin")
        if st.button("Sair"): logout()
        data, sha = db.get_data()

        t0, t1, t2, t3, t4, t5 = st.tabs(["👥 Alunos", "➕ Itens", "📋 Reservas", "📄 Listas", "📊 Estoque", "⚙️ Config"])

        with t0:
            total_alunos = len(data.get('students_db', []))
            st.markdown(f"### 👥 Base de Alunos")
            st.metric(label="Total de Alunos Matriculados", value=total_alunos)
            
            with st.expander("📥 Importar CSV / Cadastro Manual", expanded=False):
                c_man, c_csv = st.columns(2)
                with c_man:
                    st.markdown("#### Cadastro Manual")
                    with st.form("manual_student"):
                        m_name = st.text_input("Nome Aluno")
                        c_em1, c_em2 = st.columns(2)
                        m_email1 = c_em1.text_input("E-mail 1")
                        m_email2 = c_em2.text_input("E-mail 2 (Opcional)")
                        c_p1, c_p2 = st.columns(2)
                        m_parent1 = c_p1.text_input("Responsável 1")
                        m_parent2 = c_p2.text_input("Responsável 2 (Opcional)")
                        m_grade = st.selectbox("Série", SERIES_LISTA)
                        m_class = st.selectbox("Turno/Turma", TURMAS_LISTA)
                        if st.form_submit_button("Cadastrar"):
                            final_parents = m_parent1
                            if m_parent2: final_parents += f" / {m_parent2}"
                            new_s = {"email": m_email1, "email2": m_email2, "name": m_name, "grade": m_grade, "class_name": m_class, "parent_csv": final_parents}
                            data['students_db'].append(new_s)
                            if db.update_data(data, sha, f"Add {m_name}"): st.success("OK!"); st.rerun()

                with c_csv:
                    st.markdown("#### Importar CSV")
                    uploaded_file = st.file_uploader("Arquivo .csv", type="csv")
                    if uploaded_file and st.button("Processar"):
                        try:
                            try: df = pd.read_csv(uploaded_file, sep=',')
                            except: uploaded_file.seek(0); df = pd.read_csv(uploaded_file, sep=',', encoding='latin-1')
                            
                            df.columns = df.columns.str.replace('#', '').str.strip()
                            required_cols = ['Email', 'NomeAluno', 'Curso', 'CodTurno', 'NomeResponsavel']
                            if not all(col in df.columns for col in required_cols):
                                st.error(f"Colunas incorretas.")
                            else:
                                current_db = data.get('students_db', [])
                                added = 0
                                existing_keys = {f"{s['email']}|{s['name']}".lower() for s in current_db}
                                for _, row in df.iterrows():
                                    mg = MAP_CURSO_CSV.get(row['Curso'], str(row['Curso']))
                                    mc = MAP_TURNO_CSV.get(row['CodTurno'], str(row['CodTurno']))
                                    # Tratamento de erro para valores nulos/NaN
                                    email_raw = str(row['Email']).strip()
                                    if email_raw.lower() == 'nan': email_raw = ""
                                    
                                    aluno = str(row['NomeAluno']).strip()
                                    resp = str(row['NomeResponsavel']).strip()
                                    
                                    key = f"{email_raw}|{aluno}".lower()
                                    if key not in existing_keys:
                                        current_db.append({
                                            "email": email_raw, 
                                            "email2": "", # Garante campo vazio para evitar KeyErrors
                                            "name": aluno, 
                                            "grade": mg, 
                                            "class_name": mc, 
                                            "parent_csv": resp
                                        })
                                        added += 1
                                data['students_db'] = current_db
                                if db.update_data(data, sha, f"CSV {added}"): st.success(f"{added} novos!"); time.sleep(2); st.rerun()
                        except Exception as e: st.error(f"Erro: {e}")

            st.divider()
            st.markdown("### ✏️ Gerenciar/Editar Alunos")
            search_query = st.text_input("🔍 Buscar aluno por nome ou e-mail", placeholder="Digite para buscar...")
            if search_query:
                s_db = data.get('students_db', [])
                filtered_students = [(i, s) for i, s in enumerate(s_db) if search_query.lower() in s['name'].lower() or search_query.lower() in str(s.get('email','')).lower() or search_query.lower() in str(s.get('email2','')).lower()]
                st.caption(f"{len(filtered_students)} encontrados.")
                for index, student in filtered_students:
                    with st.expander(f"👤 {student['name']} ({student['grade']})"):
                        with st.form(key=f"edit_student_{index}"):
                            new_name = st.text_input("Nome do Aluno", value=student['name'])
                            c_em_e1, c_em_e2 = st.columns(2)
                            new_email = c_em_e1.text_input("E-mail 1", value=student['email'])
                            new_email2 = c_em_e2.text_input("E-mail 2", value=student.get('email2', ''))
                            c_e3, c_e4 = st.columns(2)
                            curr_g = student['grade'] if student['grade'] in SERIES_LISTA else SERIES_LISTA[0]
                            curr_c = student['class_name'] if student['class_name'] in TURMAS_LISTA else TURMAS_LISTA[0]
                            new_grade = c_e3.selectbox("Série", SERIES_LISTA, index=SERIES_LISTA.index(curr_g))
                            new_class = c_e4.selectbox("Turma/Turno", TURMAS_LISTA, index=TURMAS_LISTA.index(curr_c))
                            new_parent = st.text_input("Responsáveis", value=student.get('parent_csv', ''))
                            col_save, col_del = st.columns([1,1])
                            if col_save.form_submit_button("💾 Salvar"):
                                data['students_db'][index] = {"email": new_email, "email2": new_email2, "name": new_name, "grade": new_grade, "class_name": new_class, "parent_csv": new_parent}
                                if db.update_data(data, sha, f"Edit Student {new_name}"): st.success("Salvo!"); time.sleep(1); st.rerun()
                        if st.button("🗑️ Excluir Aluno", key=f"del_stud_{index}"):
                            data['students_db'].pop(index)
                            if db.update_data(data, sha, f"Deleted Student"): st.success("Removido."); time.sleep(1); st.rerun()

        with t1:
            st.markdown("### Cadastro Itens")
            mode = st.radio("Modo", ["Individual", "Lote"])
            if mode=="Individual":
                with st.form("fi"):
                    cat=st.selectbox("Cat", CATEGORIAS); tit=st.text_input("Nome")
                    sg=st.selectbox("Série", SERIES_LISTA); stt=st.selectbox("Turma", TURMAS_LISTA)
                    if st.form_submit_button("Salvar"):
                        data['books'].append({"id": int(time.time()), "category": cat, "title": tit, "grade": sg, "class_name": stt, "available": True, "reserved_by": None})
                        db.update_data(data, sha, "Add"); st.success("OK"); st.rerun()
            else:
                c1,c2,c3 = st.columns(3)
                bc=c1.selectbox("Cat", CATEGORIAS); bg=c2.selectbox("Série", SERIES_LISTA); bt=c3.selectbox("Turma", TURMAS_LISTA)
                txt = st.text_area("Lista")
                if st.button("Proc"):
                    lines = txt.strip().split('\n'); count = 0
                    for l in lines:
                        if l.strip():
                            data['books'].append({"id": int(time.time())+count, "category": bc, "title": l.strip(), "grade": bg, "class_name": bt, "available": True, "reserved_by": None})
                            count+=1
                    if count>0: db.update_data(data, sha, "Batch"); st.success("OK"); st.rerun()

        with t2:
            st.markdown("### Reservas")
            c1, c2, c3 = st.columns(3)
            fc = c1.selectbox("Categoria", ["Todas"] + CATEGORIAS, key="res_cat")
            fg = c2.selectbox("Série", ["Todas"] + SERIES_LISTA, key="res_grade")
            ft = c3.selectbox("Turma", ["Todas"] + TURMAS_LISTA, key="res_class")
            filtered_res = [r for r in data.get('reservations',[]) if (fc=="Todas" or r.get('category')==fc) and (fg=="Todas" or r.get('grade')==fg) and (ft=="Todas" or r.get('class_name')==ft)]
            st.write(f"Total: {len(filtered_res)}")
            for r in filtered_res:
                with st.expander(f"{r.get('book_title')} -> {r.get('student_name')}"):
                    st.write(f"**Item:** {r.get('book_title')}")
                    st.write(f"**Aluno:** {r.get('student_name')} ({r.get('grade')} - {r.get('class_name')})")
                    if st.button("Cancelar Reserva", key=f"adm_canc_{r.get('reservation_id')}"):
                        process_cancellation(db, data, sha, r.get('book_id'), "ADMIN_OVERRIDE", r.get('reservation_id'))
                        st.success("Cancelado!"); time.sleep(1); st.rerun()

        with t3:
            st.markdown("### Gerar Relatórios")
            c1, c2, c3 = st.columns(3)
            sc = c1.selectbox("Cat Lista", ["Todas"] + CATEGORIAS, key="list_cat")
            sg = c2.selectbox("Série Lista", ["Todas"] + SERIES_LISTA, key="list_grade")
            stt = c3.selectbox("Turma Lista", ["Todas"] + TURMAS_LISTA, key="list_class")
            if st.button("Gerar Lista na Tela"):
                lst = [r for r in data.get('reservations',[]) if (sg=="Todas" or r.get('grade')==sg) and (stt=="Todas" or r.get('class_name')==stt) and (sc=="Todas" or r.get('category')==sc)]
                if lst: st.dataframe(pd.DataFrame(lst)[['category','student_name','parent_name','book_title','timestamp']], use_container_width=True)
                else: st.warning("Vazio")

        with t4:
            st.markdown("### Estoque")
            c1, c2, c3 = st.columns(3)
            ec = c1.selectbox("Categoria Est", ["Todas"] + CATEGORIAS, key="stk_cat")
            eg = c2.selectbox("Série Est", ["Todas"] + SERIES_LISTA, key="stk_grade")
            et = c3.selectbox("Turma Est", ["Todas"] + TURMAS_LISTA, key="stk_class")
            
            items = [i for i in data.get('books',[]) if (ec=="Todas" or i.get('category')==ec) and (eg=="Todas" or i.get('grade')==eg) and (et=="Todas" or i.get('class_name')==et)]
            items.sort(key=lambda x: (x['grade'], x.get('class_name',''), x['title']))
            st.caption(f"Filtrados: {len(items)}")
            
            # --- ZONA DE PERIGO: EXCLUSÃO EM LOTE ---
            if items:
                st.divider()
                st.markdown(f"#### 🗑️ Exclusão em Massa ({len(items)} itens filtrados)")
                with st.expander("⚠️ Abrir Zona de Perigo"):
                    st.warning("Atenção: Esta ação apagará TODOS os itens listados acima que não estejam reservados. Ação irreversível.")
                    if st.button(f"CONFIRMAR EXCLUSÃO DE {len(items)} ITENS"):
                        # Logica de exclusão segura (mantém os reservados)
                        ids_to_keep = []
                        deleted_count = 0
                        skipped_count = 0
                        
                        # Lista de IDs que QUEREMOS excluir (os filtrados)
                        target_ids = {i['id'] for i in items}
                        
                        # Reconstrói a lista principal
                        new_book_list = []
                        for b in data['books']:
                            if b['id'] in target_ids:
                                if b['available']:
                                    # Pode excluir
                                    deleted_count += 1
                                else:
                                    # Está reservado, NÃO exclui, mantém na lista
                                    new_book_list.append(b)
                                    skipped_count += 1
                            else:
                                # Não faz parte do filtro, mantém
                                new_book_list.append(b)
                        
                        data['books'] = new_book_list
                        
                        if db.update_data(data, sha, f"Batch delete: {deleted_count} items"):
                            msg = f"Sucesso! {deleted_count} itens excluídos."
                            if skipped_count > 0:
                                msg += f" ({skipped_count} itens foram mantidos pois estão reservados)."
                            st.success(msg)
                            time.sleep(3)
                            st.rerun()

            # LISTA NORMAL DE ITENS
            st.divider()
            for i in items:
                icon = "🟢" if i['available'] else "🔴"
                with st.expander(f"{icon} {i['title']} ({i['grade']} {i.get('class_name')})"):
                    with st.form(key=f"edit_stk_{i['id']}"):
                        n_tit = st.text_input("Título", value=i['title'])
                        if st.form_submit_button("Salvar"):
                            i['title'] = n_tit
                            db.update_data(data, sha, f"Edit {i['id']}")
                            st.success("Salvo!"); time.sleep(1); st.rerun()
                    if st.button("Excluir", key=f"del_i_{i['id']}"):
                        if i['available']:
                            data['books'] = [b for b in data['books'] if b['id']!=i['id']]
                            db.update_data(data, sha, f"Del {i['id']}"); st.rerun()
                        else: st.error("Reservado!")
            
        with t5:
            with st.form("pw"):
                p = st.text_input("Nova Senha")
                if st.form_submit_button("Mudar"):
                    data['admin_config']['password'] = p
                    db.update_data(data, sha, "Pwd"); st.success("OK"); logout()

if __name__ == "__main__":
    main()
