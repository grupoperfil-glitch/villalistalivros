import streamlit as st
import json
import time
from datetime import datetime
from github import Github, GithubException
import pandas as pd

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Reserva de Livros - Villa",
    page_icon="📚",
    layout="wide"
)

# --- CONSTANTES ---
SERIES_DISPONIVEIS = ["1º Ano", "2º Ano", "3º Ano", "4º Ano"]
TURMAS_DISPONIVEIS = ["A", "B", "D"]

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

            # --- AUTO-CORREÇÃO (MIGRATION) ---
            if "reservations" in json_data:
                for i, res in enumerate(json_data["reservations"]):
                    if "reservation_id" not in res:
                        clean_name = str(res.get('student_name', 'aluno')).replace(" ", "")
                        res["reservation_id"] = f"legacy_{i}_{clean_name}"
                    if "class_name" not in res:
                        res["class_name"] = "Indefinida"

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

def login_family(parent, student, grade, class_name):
    if parent and student and grade and class_name:
        st.session_state.user = {
            'type': 'family',
            'parent': parent,
            'student': student,
            'grade': grade,
            'class_name': class_name
        }
        st.rerun()
    else:
        st.warning("Preencha todos os campos.")

def login_admin(password_input, db_data):
    stored_password = db_data.get("admin_config", {}).get("password", "villa123")
    if password_input == stored_password:
        st.session_state.user = {'type': 'admin'}
        st.rerun()
    else:
        st.error("Senha incorreta.")

def logout():
    st.session_state.user = None
    st.rerun()

# --- INTERFACE PRINCIPAL ---
def main():
    db = GitHubConnection()
    data_cache, sha_cache = db.get_data()

    st.markdown("""
    <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px; color: white; text-align: center; margin-bottom: 25px;'>
        <h1>📚 Sistema de Reserva - Fundamental I</h1>
    </div>
    """, unsafe_allow_html=True)

    # 1. TELA DE LOGIN
    if st.session_state.user is None:
        c1, c2 = st.columns(2, gap="large")
        
        with c1:
            st.subheader("👨‍👩‍👧‍👦 Acesso Família")
            with st.form("login_family"):
                parent_in = st.text_input("Nome do Responsável")
                student_in = st.text_input("Nome do Estudante")
                cc1, cc2 = st.columns(2)
                grade_in = cc1.selectbox("Série do Aluno", SERIES_DISPONIVEIS)
                class_in = cc2.selectbox("Turma", TURMAS_DISPONIVEIS)
                
                if st.form_submit_button("Entrar", type="primary"):
                    login_family(parent_in, student_in, grade_in, class_in)

        with c2:
            st.subheader("🛡️ Área Administrativa")
            with st.form("login_admin"):
                pass_in = st.text_input("Senha Admin", type="password")
                if st.form_submit_button("Acessar Painel"):
                    login_admin(pass_in, data_cache)

    # 2. PAINEL DA FAMÍLIA
    elif st.session_state.user['type'] == 'family':
        user = st.session_state.user
        
        col_info, col_btn = st.columns([4, 1])
        col_info.info(f"👤 **{user['parent']}** | Aluno: {user['student']} ({user['grade']} - Turma {user['class_name']})")
        if col_btn.button("Sair"):
            logout()

        st.divider()
        st.subheader(f"📖 Livros Disponíveis para {user['grade']} {user['class_name']}")

        data, sha = db.get_data()

        # Filtro: Série E Turma
        books_for_grade = [
            b for b in data.get('books', []) 
            if b['grade'] == user['grade'] and b.get('class_name') == user['class_name']
        ]
        available_books = [b for b in books_for_grade if b['available']]

        if not available_books:
            if not books_for_grade:
                st.warning(f"Não há livros cadastrados especificamente para o {user['grade']} Turma {user['class_name']}.")
            else:
                st.warning("⚠️ Todos os livros da sua turma já foram reservados.")
        else:
            for book in available_books:
                with st.container(border=True):
                    c_txt, c_act = st.columns([3, 1])
                    with c_txt:
                        st.markdown(f"### {book['title']}")
                        st.caption(f"Cód: {book['id']} | Destinado a: {book['grade']} {book.get('class_name', '-')}")
                    
                    with c_act:
                        st.write("") 
                        if st.button(f"RESERVAR", key=f"btn_{book['id']}", type="primary"):
                            book_index = next((i for i, b in enumerate(data['books']) if b['id'] == book['id']), -1)
                            
                            if book_index != -1 and data['books'][book_index]['available']:
                                # Atualiza Livro
                                data['books'][book_index]['available'] = False
                                data['books'][book_index]['reserved_by'] = user['parent']
                                data['books'][book_index]['reserved_student'] = user['student']
                                
                                # Cria Reserva com ID
                                new_reservation = {
                                    "reservation_id": int(time.time()),
                                    "book_id": book['id'],
                                    "parent_name": user['parent'],
                                    "student_name": user['student'],
                                    "grade": user['grade'],
                                    "class_name": user['class_name'],
                                    "book_title": book['title'],
                                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                data['reservations'].append(new_reservation)

                                with st.spinner("Confirmando reserva..."):
                                    if db.update_data(data, sha, f"Reserva: {book['title']}"):
                                        st.success("✅ Reserva confirmada!")
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("Erro ao salvar.")
                            else:
                                st.error("Livro já reservado.")
                                time.sleep(2)
                                st.rerun()

    # 3. PAINEL ADMIN
    elif st.session_state.user['type'] == 'admin':
        st.success("🔒 Painel de Gestão")
        c_logout, c_config = st.columns([1, 5])
        if c_logout.button("Sair"):
            logout()
            
        data, sha = db.get_data()
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "➕ Cadastrar", 
            "📋 Reservas", 
            "📄 Listas por Turma", 
            "📊 Estoque / Editar",
            "⚙️ Configurações"
        ])

        with tab1:
            st.markdown("### Adicionar Novo Título")
            with st.form("add_book_form"):
                title = st.text_input("Título do Livro")
                c_grade, c_class = st.columns(2)
                grade_sel = c_grade.selectbox("Série Destino", SERIES_DISPONIVEIS)
                class_sel = c_class.selectbox("Turma Destino", TURMAS_DISPONIVEIS)

                if st.form_submit_button("Salvar no Sistema"):
                    if title:
                        new_id = int(time.time())
                        new_book = {
                            "id": new_id,
                            "title": title,
                            "grade": grade_sel,
                            "class_name": class_sel,
                            "available": True,
                            "reserved_by": None,
                            "reserved_student": None
                        }
                        if 'books' not in data: data['books'] = []
                        data['books'].append(new_book)
                        
                        if db.update_data(data, sha, f"Admin add: {title}"):
                            st.success(f"Cadastrado: {title}")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.error("Título é obrigatório.")

        with tab2:
            st.markdown("### Gerenciar Reservas")
            reservations = data.get('reservations', [])
            if not reservations:
                st.info("Sem reservas.")
            else:
                for res in reservations:
                    res_id = res.get('reservation_id')
                    with st.expander(f"{res.get('timestamp')} | {res.get('student_name')}"):
                        c_det, c_canc = st.columns([3, 1])
                        c_det.write(f"**Livro:** {res.get('book_title')}")
                        c_det.write(f"**Resp:** {res.get('parent_name')}")
                        c_det.write(f"**Turma:** {res.get('grade')} - {res.get('class_name', 'Indefinida')}")
                        
                        if c_canc.button("Cancelar", key=f"del_{res_id}"):
                            for book in data['books']:
                                match = False
                                if 'book_id' in res and book['id'] == res['book_id']:
                                    match = True
                                elif book['title'] == res['book_title'] and book['reserved_by'] == res['parent_name']:
                                    match = True
                                
                                if match:
                                    book['available'] = True
                                    book['reserved_by'] = None
                                    book['reserved_student'] = None
                                    break
                            
                            data['reservations'] = [r for r in data['reservations'] if r.get('reservation_id') != res_id]
                            if db.update_data(data, sha, "Cancelamento Admin"):
                                st.success("Cancelado!")
                                time.sleep(1)
                                st.rerun()

        with tab3:
            st.markdown("### Lista de Entrega")
            c_rep1, c_rep2 = st.columns(2)
            sel_grade = c_rep1.selectbox("Série", SERIES_DISPONIVEIS, key="rep_grade")
            sel_class = c_rep2.selectbox("Turma", TURMAS_DISPONIVEIS, key="rep_class")
            
            if st.button("Gerar Lista"):
                filtered = [
                    r for r in data.get('reservations', []) 
                    if r.get('grade') == sel_grade and r.get('class_name') == sel_class
                ]
                
                if filtered:
                    df = pd.DataFrame(filtered)
                    cols_map = {
                        "student_name": "Aluno", 
                        "parent_name": "Responsável", 
                        "book_title": "Livro",
                        "timestamp": "Data"
                    }
                    existing = [c for c in cols_map.keys() if c in df.columns]
                    st.dataframe(df[existing].rename(columns=cols_map), hide_index=True, use_container_width=True)
                else:
                    st.warning("Nenhum registro para esta turma.")

        # --- NOVA ABA DE ESTOQUE/EDIÇÃO ---
        with tab4:
            st.markdown("### Gerenciar Estoque")
            books = data.get('books', [])
            
            if not books:
                st.info("Nenhum livro cadastrado.")
            else:
                # Ordena para visualização (Série -> Turma)
                books_sorted = sorted(books, key=lambda x: (x.get('grade', ''), x.get('class_name', '')))
                
                st.caption(f"Total de livros: {len(books_sorted)}")

                for book in books_sorted:
                    # Ícone de status
                    status_icon = "🟢" if book['available'] else "🔴"
                    status_text = "Disponível" if book['available'] else f"Reservado por {book.get('reserved_by')}"
                    
                    # Criação do Cartão Expansível
                    label = f"{status_icon} {book['title']} | {book['grade']} - Turma {book.get('class_name', '-')}"
                    
                    with st.expander(label):
                        # Formulário de Edição
                        with st.form(key=f"edit_form_{book['id']}"):
                            st.write(f"**Status:** {status_text}")
                            
                            c_edit1, c_edit2, c_edit3 = st.columns([3, 1, 1])
                            new_title = c_edit1.text_input("Título", value=book['title'])
                            
                            # Índices seguros para os selectbox
                            idx_grade = SERIES_DISPONIVEIS.index(book['grade']) if book['grade'] in SERIES_DISPONIVEIS else 0
                            idx_class = TURMAS_DISPONIVEIS.index(book.get('class_name', 'A')) if book.get('class_name') in TURMAS_DISPONIVEIS else 0
                            
                            new_grade = c_edit2.selectbox("Série", SERIES_DISPONIVEIS, index=idx_grade)
                            new_class = c_edit3.selectbox("Turma", TURMAS_DISPONIVEIS, index=idx_class)
                            
                            col_save, col_del = st.columns([1, 1])
                            
                            # Botão Salvar (Atualizar)
                            if col_save.form_submit_button("💾 Salvar Alterações"):
                                # Atualiza o objeto na lista
                                book['title'] = new_title
                                book['grade'] = new_grade
                                book['class_name'] = new_class
                                
                                if db.update_data(data, sha, f"Edit: {book['id']}"):
                                    st.success("Livro atualizado!")
                                    time.sleep(1)
                                    st.rerun()

                        # Botão Excluir (Fora do form para segurança visual)
                        if st.button("🗑️ Excluir este livro", key=f"del_btn_{book['id']}", type="secondary"):
                            if not book['available']:
                                st.error("❌ Não é possível excluir um livro reservado. Cancele a reserva primeiro.")
                            else:
                                # Filtra a lista removendo este ID
                                data['books'] = [b for b in data['books'] if b['id'] != book['id']]
                                if db.update_data(data, sha, f"Deleted: {book['id']}"):
                                    st.success("Livro excluído com sucesso.")
                                    time.sleep(1)
                                    st.rerun()

        with tab5:
            st.markdown("### Senha Admin")
            with st.form("change_pass"):
                p1 = st.text_input("Nova Senha", type="password")
                p2 = st.text_input("Confirmar", type="password")
                if st.form_submit_button("Alterar"):
                    if p1 == p2 and len(p1) > 3:
                        data["admin_config"]["password"] = p1
                        if db.update_data(data, sha, "Senha alterada"):
                            st.success("Sucesso! Logue novamente.")
                            logout()
                    else:
                        st.error("Senhas inválidas.")

if __name__ == "__main__":
    main()
